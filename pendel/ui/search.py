"""Verbindungssuche wie in der DB-App: Von, Nach, Datum, Uhrzeit, Abfahrt/Ankunft.

Die Suche steht oben auf der Startseite. Gespeicherte Strecken lassen sich mit
einem Klick übernehmen, und jede Suche kann selbst als Strecke gespeichert werden.
Die letzte Suche merkt sich der Browser (``app.storage.user``).
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable

from nicegui import app, ui

from .. import state, storage, timeutil
from ..decision import de
from ..models import Mode, Place, Route
from ..services import fares, geocode

STORAGE_KEY = "search"


# ---------------------------------------------------------------------------
# Datenmodell der Suche
# ---------------------------------------------------------------------------


@dataclass
class Query:
    origin: Place | None
    destination: Place | None
    when: datetime
    arrive: bool = False  # False = „Abfahrt ab“, True = „Ankunft bis“
    route_id: str | None = None  # gesetzt, wenn die Suche aus einer gespeicherten Strecke stammt

    @property
    def complete(self) -> bool:
        return self.origin is not None and self.destination is not None

    def to_route(self) -> Route:
        """Baut aus der Suche eine Strecke für die Berechnung."""
        saved = next((r for r in state.settings().routes if r.id == self.route_id), None)
        same = saved and saved.origin == self.origin and saved.destination == self.destination
        return Route(
            id=saved.id if same else "suche",
            name=saved.name if same else f"{short(self.origin.name)} → {short(self.destination.name)}",
            origin=self.origin,
            destination=self.destination,
            departure=f"{self.when:%H:%M}",
            weekdays=list(range(7)),
            modes=saved.modes if same else [m.value for m in Mode],
        )

    def save(self) -> None:
        data = {
            "origin": asdict(self.origin) if self.origin else None,
            "destination": asdict(self.destination) if self.destination else None,
            "when": self.when.isoformat(timespec="minutes"),
            "arrive": self.arrive,
            "route_id": self.route_id,
        }
        app.storage.user[STORAGE_KEY] = data


def from_route(route: Route) -> Query:
    when = timeutil.next_departure(route.departure, route.weekdays)
    return Query(route.origin, route.destination, when, arrive=False, route_id=route.id)


def load_query() -> Query:
    """Letzte Suche aus dem Browser – sonst die erste gespeicherte Strecke."""
    raw = app.storage.user.get(STORAGE_KEY)
    routes = state.settings().routes
    if raw:
        try:
            when = datetime.fromisoformat(raw["when"])
            if when < timeutil.now() - timedelta(hours=1):  # alte Suche: auf jetzt setzen
                when = timeutil.now().replace(second=0, microsecond=0)
            return Query(
                Place(**raw["origin"]) if raw.get("origin") else None,
                Place(**raw["destination"]) if raw.get("destination") else None,
                when,
                bool(raw.get("arrive")),
                raw.get("route_id"),
            )
        except (KeyError, TypeError, ValueError):
            pass  # kaputter Eintrag – einfach neu anfangen
    if routes:
        return from_route(routes[0])
    return Query(None, None, timeutil.now().replace(second=0, microsecond=0))


def short(name: str) -> str:
    """„DHBW Stuttgart, Rotebühlplatz 41, 70178 Stuttgart“ → „DHBW Stuttgart“."""
    return name.split(",")[0].strip()


def _rest(place: Place | None) -> str:
    """Alles nach dem ersten Komma: „Rotebühlplatz 41, 70178 Stuttgart“."""
    if not place:
        return ""
    return place.name[len(short(place.name)):].lstrip(", ")


def known_places() -> list[Place]:
    """Alle Orte aus den gespeicherten Strecken (ohne Doppelte)."""
    seen: dict[tuple[float, float], Place] = {}
    for r in state.settings().routes:
        for p in (r.origin, r.destination):
            seen.setdefault((round(p.lat, 4), round(p.lon, 4)), p)
    return list(seen.values())


# ---------------------------------------------------------------------------
# Eingabefeld mit Adressvorschlägen
# ---------------------------------------------------------------------------


class PlaceInput:
    """Textfeld, das beim Tippen Adressen vorschlägt (wie bei der DB-App).

    Die Vorschläge sind eine eigene Liste direkt unter dem Feld. Sie geht auf,
    wenn man ins Feld klickt oder tippt, und schließt sich, sobald man einen
    Vorschlag wählt, woanders hinklickt oder Esc drückt.
    """

    def __init__(self, label: str, icon: str, place: Place | None, on_change: Callable[[], None]) -> None:
        self.place = place
        self._on_change = on_change
        self._muted = False
        self._seq = 0  # zählt Suchanfragen hoch; veraltete Antworten werden ignoriert
        with ui.element("div").classes("relative w-full min-w-0"):
            ui.label(label).classes("place-label")
            self.input = (
                ui.input(value=short(place.name) if place else "", placeholder="Ort oder Adresse")
                .props(f'borderless clearable debounce=350 autocomplete=off aria-label="{label}"')
                .classes("w-full big-input")
            )
            self.sub = ui.label(_rest(place)).classes("place-sub")
            self.box = ui.column().classes("search-menu gap-0")
            self.box.set_visibility(False)
        self.input.on("focus", lambda: self._suggest(""))
        self.input.on("blur", self._blurred)
        self.input.on("keydown.esc", self.hide)
        self.input.on_value_change(self._typed)

    def set(self, place: Place | None) -> None:
        self._muted = True
        self.place = place
        self.input.value = short(place.name) if place else ""
        self.sub.text = _rest(place)
        self._muted = False

    def hide(self) -> None:
        self._seq += 1  # laufende Suchen sollen die Liste nicht wieder öffnen
        self.box.set_visibility(False)

    async def _blurred(self) -> None:
        # kurz warten, damit ein Klick auf einen Vorschlag noch ankommt
        await asyncio.sleep(0.25)
        self.hide()

    async def _typed(self, e) -> None:
        if self._muted:
            return
        text = (e.value or "").strip()
        if self.place and text in (self.place.name, short(self.place.name)):
            return
        self.place = None  # getippt, aber noch nichts ausgewählt
        self.sub.text = "Bitte einen Vorschlag auswählen"
        await self._suggest(text)

    async def _suggest(self, text: str) -> None:
        self._seq += 1
        seq = self._seq
        q = text.lower()
        saved = [p for p in known_places() if not q or q in p.name.lower()]
        found: list[Place] = []
        error = False
        if len(text) >= 3:
            try:
                found = await geocode.search(text)
            except Exception:  # noqa: BLE001 – ohne Internet gibt es eben nur gespeicherte Orte
                error = True
        if seq != self._seq:
            return  # inzwischen wurde weitergetippt, gewählt oder woanders hingeklickt
        self.box.clear()
        with self.box:
            if saved:
                ui.label("Gespeichert").classes("tiny muted px-4 pt-2")
                for p in saved[:5]:
                    self._item(p, "star")
            if found:
                ui.label("Adressen").classes("tiny muted px-4 pt-2")
                for p in found:
                    self._item(p, "place")
            if not saved and not found:
                msg = (
                    "Adresssuche gerade nicht erreichbar"
                    if error
                    else "Mindestens 3 Buchstaben eingeben" if len(text) < 3 else "Nichts gefunden"
                )
                ui.label(msg).classes("tiny muted px-4 py-3")
        self.box.set_visibility(True)

    def _item(self, p: Place, icon: str) -> None:
        with ui.item(on_click=lambda p=p: self._choose(p)).classes("search-item w-full"):
            with ui.item_section().props("avatar").classes("min-w-0"):
                ui.icon(icon).classes("text-[color:var(--muted)]")
            with ui.item_section():
                ui.item_label(short(p.name)).classes("font-medium")
                rest = p.name[len(short(p.name)):].lstrip(", ")
                if rest:
                    ui.item_label(rest).props("caption").classes("truncate")

    def _choose(self, p: Place) -> None:
        self.set(p)
        self.hide()
        self._on_change()


# ---------------------------------------------------------------------------
# Die komplette Suchkarte
# ---------------------------------------------------------------------------


def search_card(query: Query, on_search: Callable[[Query], Awaitable[None]]) -> None:
    """Zeichnet die Suche als Fahrschein. ``on_search`` wird mit der fertigen Suche aufgerufen."""
    prefs = state.settings().prefs

    def changed() -> None:
        query.origin = origin.place
        query.destination = dest.place
        query.route_id = query.route_id if _matches_saved(query) else None
        fare_box.refresh()

    with ui.element("div").classes("ticket fade-in"):
        # ===== linker Teil: Strecke und Zeit ==================================
        with ui.element("div").classes("t-main"):
            with ui.element("div").classes("t-top"):
                ui.label("Fahrschein-Anfrage").classes("kicker")
                date_label = ui.label(_date_text(query.when.date())).classes("kicker")
            with ui.element("div").classes("route"):
                origin = PlaceInput("Von", "trip_origin", query.origin, changed)

                def swap() -> None:
                    a, b = origin.place, dest.place
                    origin.set(b)
                    dest.set(a)
                    changed()

                ui.button(icon="swap_horiz", on_click=swap).props("flat round").classes("swap-btn").tooltip(
                    "Start und Ziel tauschen"
                )
                dest = PlaceInput("Nach", "place", query.destination, changed)

            with ui.element("div").classes("meta"):
                with ui.column().classes("gap-0"):
                    ui.label("Datum").classes("tiny muted")
                    day = _date_input(query.when.date())
                with ui.column().classes("gap-0"):
                    ui.label("Uhrzeit").classes("tiny muted")
                    clock = _time_input(f"{query.when:%H:%M}")
                mode = ui.toggle({False: "Abfahrt", True: "Ankunft"}, value=query.arrive).props(
                    "unelevated no-caps toggle-color=primary"
                ).classes("seg")

                def now() -> None:
                    n = timeutil.now()
                    day.value = n.strftime("%d.%m.%Y")
                    clock.value = n.strftime("%H:%M")
                    mode.value = False

                ui.button("Jetzt", on_click=now).props("flat no-caps dense").classes("link-btn mb-1")

            routes = state.settings().routes
            with ui.element("div").classes("mine"):
                ui.label("Meine Strecken").classes("kicker mr-1")
                for r in routes:
                    async def pick(r: Route = r) -> None:
                        q = from_route(r)
                        origin.set(q.origin)
                        dest.set(q.destination)
                        day.value = q.when.strftime("%d.%m.%Y")
                        clock.value = q.when.strftime("%H:%M")
                        mode.value = False
                        query.route_id = r.id
                        await submit()

                    ui.chip(f"★ {r.name}", on_click=pick).props("clickable square").classes("route-chip")
                if not routes:
                    ui.label("noch keine").classes("tiny muted")
                ui.space()
                save_btn = ui.button("+ Als Strecke speichern").props("flat no-caps dense").classes("link-btn")

        # ===== rechter Abschnitt: Deutschlandticket, Preis, Los geht's ===========
        with ui.element("div").classes("t-stub"):
            with ui.column().classes("gap-1"):
                with ui.element("div").classes("dt-row"):
                    ui.label("Deutschlandticket")
                    dticket = ui.switch(value=prefs.has_deutschlandticket).props("dense").classes("dt-switch")
                dt_hint = ui.label(_dt_hint(prefs.has_deutschlandticket)).classes("tiny muted")

            @ui.refreshable
            def fare_box() -> None:
                with ui.column().classes("fare gap-0"):
                    ui.label("Dein Ticket für diese Strecke").classes("kicker")
                    if not query.complete:
                        ui.label("–").classes("fare-price")
                        ui.label("Start und Ziel auswählen").classes("tiny muted")
                        return
                    f = fares.estimate_fare(query.origin, query.destination)
                    dt_price = fares.deutschlandticket_price()
                    with ui.row().classes("items-baseline gap-2"):
                        if prefs.has_deutschlandticket:
                            ui.label("0,00 €").classes("fare-price")
                            ui.label("mit Deutschlandticket").classes("tiny muted")
                        else:
                            ui.label(f"{de(f.amount, 2)} €").classes("fare-price")
                            ui.label(_fare_short(f.label)).classes("tiny muted")
                    if prefs.has_deutschlandticket:
                        ui.label(f"Einzeln würde die Fahrt {de(f.amount, 2)} € kosten.").classes("tiny muted")
                    else:
                        trips = math.ceil(dt_price / f.amount)
                        ui.label(
                            f"Deutschlandticket ({de(dt_price, 0)} €/Monat) lohnt sich ab {trips} Fahrten im Monat."
                        ).classes("tiny muted")

            fare_box()
            go = ui.button("Verbindung prüfen").props("unelevated no-caps").classes("go")

    async def toggle_dticket(e) -> None:
        prefs.has_deutschlandticket = bool(e.value)
        state.save()
        dt_hint.text = _dt_hint(prefs.has_deutschlandticket)
        fare_box.refresh()
        await submit()  # Empfehlung mit dem neuen Preis neu berechnen

    async def submit() -> None:
        changed()
        if not query.complete:
            ui.notify("Bitte Start und Ziel aus den Vorschlägen auswählen", type="warning")
            return
        try:
            d = datetime.strptime(day.value or "", "%d.%m.%Y").date()
            t = datetime.strptime(clock.value or "", "%H:%M").time()
        except ValueError:
            ui.notify("Bitte Datum (TT.MM.JJJJ) und Uhrzeit (HH:MM) prüfen", type="warning")
            return
        query.when = datetime.combine(d, t)
        query.arrive = bool(mode.value)
        query.save()
        date_label.text = _date_text(d)
        await on_search(query)

    def save_as_route() -> None:
        changed()
        if not query.complete:
            ui.notify("Bitte erst Start und Ziel auswählen", type="warning")
            return
        with ui.dialog() as dlg, ui.card().classes("w-[420px] max-w-[95vw] gap-3 p-6"):
            ui.label("Strecke speichern").classes("text-lg font-extrabold")
            ui.label(f"{short(query.origin.name)} → {short(query.destination.name)}").classes("muted")
            name = ui.input("Name", placeholder="z. B. Zur Uni").props("outlined dense autofocus").classes("w-full")

            def ok() -> None:
                r = Route(
                    id=storage.new_route_id(),
                    name=(name.value or "").strip() or f"{short(query.origin.name)} → {short(query.destination.name)}",
                    origin=query.origin,
                    destination=query.destination,
                    departure=clock.value or "07:30",
                )
                state.settings().routes.append(r)
                state.save()
                query.route_id = r.id
                dlg.close()
                ui.notify(f"„{r.name}“ gespeichert", type="positive")
                ui.navigate.reload()

            name.on("keydown.enter", ok)
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Abbrechen", on_click=dlg.close).props("flat no-caps")
                ui.button("Speichern", on_click=ok).props("unelevated no-caps").classes("go w-auto px-5")
        dlg.open()

    go.on_click(submit)
    dticket.on_value_change(toggle_dticket)
    save_btn.on_click(save_as_route)
    for field in (origin.input, dest.input):
        field.on("keydown.enter", submit)


WEEKDAYS_SHORT = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]


def _date_text(d: date) -> str:
    return f"{WEEKDAYS_SHORT[d.weekday()]} {d:%d.%m.%Y}"


def _dt_hint(on: bool) -> str:
    return "An: Bahnfahrten kosten 0 €." if on else "Aus: Die App rechnet mit dem EinzelTicket."


def _fare_short(label: str) -> str:
    """„VVS EinzelTicket, 2 Zonen (geschätzt)“ → „VVS · 2 Zonen“."""
    if label.startswith("VVS") and "," in label:
        return "VVS · " + label.split(",", 1)[1].replace("(geschätzt)", "").strip()
    return "geschätzt"


def _matches_saved(q: Query) -> bool:
    r = next((r for r in state.settings().routes if r.id == q.route_id), None)
    return bool(r and r.origin == q.origin and r.destination == q.destination)


def _date_input(value: date):
    with ui.input(value=value.strftime("%d.%m.%Y")).props('borderless dense mask=##.##.#### aria-label="Datum"').classes(
        "meta-field w-[150px]"
    ) as inp:
        with inp.add_slot("append"):
            ui.icon("event").classes("cursor-pointer").on("click", lambda: menu.open())
            with ui.menu() as menu:
                ui.date(mask="DD.MM.YYYY").props("first-day-of-week=1 minimal").bind_value(inp)
    return inp


def _time_input(value: str):
    with ui.input(value=value).props('borderless dense mask=time aria-label="Uhrzeit"').classes("meta-field w-[96px]") as inp:
        with inp.add_slot("append"):
            ui.icon("schedule").classes("cursor-pointer").on("click", lambda: menu.open())
            with ui.menu() as menu:
                ui.time().props("format24h").bind_value(inp)
    return inp
