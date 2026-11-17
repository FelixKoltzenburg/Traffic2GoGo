"""Einstellungen: Strecken, Vorlieben, Datenquellen."""
from __future__ import annotations

from nicegui import ui

from .. import state, storage
from ..demo import SCENARIOS
from ..models import Mode, Place, Route
from ..services import geocode
from ..timeutil import WEEKDAYS
from . import seasons, theme


def register() -> None:
    @ui.page("/einstellungen")
    def settings_page():
        if not state.check_login():
            return
        with theme.frame("/einstellungen"):
            ui.label("Einstellungen").classes("text-2xl font-extrabold tracking-tight")
            routes_section()
            prefs_section()
            look_section()
            sources_section()


# ---------------------------------------------------------------------------
# Darstellung
# ---------------------------------------------------------------------------


def look_section() -> None:
    s = state.settings()

    def set_season(e) -> None:
        s.season = e.value
        state.save()
        ui.navigate.reload()  # Farben gelten für die ganze Seite

    def set_anim(e) -> None:
        s.animations = bool(e.value)
        state.save()
        ui.navigate.reload()

    with ui.column().classes("card w-full gap-3"):
        ui.label("Darstellung").classes("h-title")
        ui.label(
            f"Farben und Rand-Animation wechseln mit der Jahreszeit. Gerade: {theme.season().icon} {theme.season().label}."
        ).classes("tiny muted")
        with ui.row().classes("w-full items-center gap-6"):
            ui.select(seasons.CHOICES, value=s.season if s.season in seasons.CHOICES else "auto",
                      label="Jahreszeit", on_change=set_season).props("outlined dense").classes("min-w-[240px]")
            ui.switch("Animationen am Rand", value=s.animations, on_change=set_anim)


# ---------------------------------------------------------------------------
# Strecken
# ---------------------------------------------------------------------------


@ui.refreshable
def routes_section() -> None:
    s = state.settings()
    with ui.column().classes("card w-full gap-3"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Deine Strecken").classes("h-title")
                ui.label("Start, Ziel, Abfahrtszeit und welche Verkehrsmittel verglichen werden.").classes("tiny muted")
            ui.button("Neue Strecke", icon="add", on_click=lambda: route_dialog(None)).props("unelevated rounded no-caps")
        if not s.routes:
            ui.label("Noch keine Strecke angelegt.").classes("muted")
        for r in s.routes:
            with ui.row().classes("w-full items-center gap-4 no-wrap p-3 rounded-2xl").style("background: var(--soft)"):
                ui.icon("route").classes("text-2xl").style("color: var(--bahn)")
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    ui.label(r.name).classes("font-bold")
                    ui.label(f"{r.origin.name} → {r.destination.name}").classes("tiny muted truncate w-full")
                    days = " ".join(WEEKDAYS[d] for d in sorted(r.weekdays))
                    modes = " · ".join(Mode(m).label for m in r.modes)
                    ui.label(f"Abfahrt {r.departure} · {days} · {modes} · im Verlauf um {r.notify_time}").classes("tiny muted")
                ui.button(icon="edit", on_click=lambda r=r: route_dialog(r)).props("flat round dense").tooltip("Bearbeiten")
                ui.button(icon="delete", on_click=lambda r=r: delete_route(r)).props("flat round dense color=negative").tooltip("Löschen")


def delete_route(r: Route) -> None:
    s = state.settings()
    s.routes = [x for x in s.routes if x.id != r.id]
    state.save()
    ui.notify(f"„{r.name}“ gelöscht", type="info")
    routes_section.refresh()


def place_picker(label: str, initial: Place | None, target: dict, key: str) -> None:
    """Eingabefeld mit Adresssuche (Photon/OpenStreetMap)."""
    with ui.column().classes("w-full gap-1"):
        current = ui.label(f"Gewählt: {initial.name}" if initial else "Noch nichts gewählt").classes("tiny muted")
        with ui.row().classes("w-full items-center no-wrap gap-2"):
            inp = ui.input(label, placeholder="z. B. Rotebühlplatz 41, Stuttgart").props("outlined dense clearable").classes("flex-1")
            btn = ui.button(icon="search").props("unelevated round dense")
        results = ui.column().classes("w-full gap-1")

        async def run_search():
            results.clear()
            q = (inp.value or "").strip()
            if len(q) < 3:
                ui.notify("Bitte mindestens 3 Zeichen eingeben", type="warning")
                return
            btn.props("loading")
            try:
                places = await geocode.search(q)
            except Exception as e:  # noqa: BLE001
                places = []
                ui.notify(f"Adresssuche nicht erreichbar ({type(e).__name__})", type="negative")
            finally:
                btn.props(remove="loading")
            with results:
                if not places:
                    ui.label("Nichts gefunden – Koordinaten unten manuell eintragen geht auch.").classes("tiny muted")
                for p in places:
                    def choose(p=p):
                        target[key] = p
                        current.text = f"Gewählt: {p.name}"
                        lat.value, lon.value = p.lat, p.lon
                        results.clear()
                    ui.button(p.name, on_click=choose).props("flat dense no-caps align=left").classes("w-full text-left")

        btn.on_click(run_search)
        inp.on("keydown.enter", run_search)
        with ui.expansion("Koordinaten manuell").props("dense").classes("w-full tiny"):
            with ui.row().classes("w-full gap-2 no-wrap"):
                lat = ui.number("Breite (lat)", value=initial.lat if initial else None, format="%.5f").props("outlined dense").classes("flex-1")
                lon = ui.number("Länge (lon)", value=initial.lon if initial else None, format="%.5f").props("outlined dense").classes("flex-1")

            def manual():
                if lat.value is None or lon.value is None:
                    return
                name = (inp.value or "").strip() or (target.get(key).name if target.get(key) else f"{lat.value:.4f}, {lon.value:.4f}")
                target[key] = Place(name, float(lat.value), float(lon.value))
                current.text = f"Gewählt: {name}"

            lat.on("blur", manual)
            lon.on("blur", manual)


def route_dialog(existing: Route | None) -> None:
    picked: dict[str, Place | None] = {
        "origin": existing.origin if existing else None,
        "destination": existing.destination if existing else None,
    }
    with ui.dialog() as dlg, ui.card().classes("w-[620px] max-w-[95vw] gap-4 p-6 rounded-3xl"):
        ui.label("Strecke bearbeiten" if existing else "Neue Strecke").classes("text-xl font-extrabold")
        name = ui.input("Name", value=existing.name if existing else "", placeholder="z. B. Zur DHBW").props("outlined dense").classes("w-full")
        place_picker("Start suchen", picked["origin"], picked, "origin")
        place_picker("Ziel suchen", picked["destination"], picked, "destination")
        with ui.row().classes("w-full gap-3 no-wrap"):
            dep = _time_input("Abfahrt", existing.departure if existing else "07:30")
            notify = _time_input("Täglich im Verlauf speichern um", existing.notify_time if existing else "06:45")
        ui.label("Pendeltage").classes("tiny muted -mb-2")
        day_set = set(existing.weekdays if existing else [0, 1, 2, 3, 4])
        with ui.row().classes("gap-1"):
            chips = {}
            for i, d in enumerate(WEEKDAYS):
                chips[i] = ui.chip(d, selectable=True, selected=i in day_set, color="primary", text_color="white")
        ui.label("Verkehrsmittel vergleichen").classes("tiny muted -mb-2")
        with ui.row().classes("gap-4"):
            mode_boxes = {m: ui.checkbox(m.label, value=(m.value in (existing.modes if existing else [x.value for x in Mode]))) for m in Mode}

        def save():
            if not (name.value or "").strip():
                ui.notify("Bitte einen Namen eingeben", type="warning")
                return
            if not picked["origin"] or not picked["destination"]:
                ui.notify("Bitte Start und Ziel auswählen", type="warning")
                return
            modes = [m.value for m, cb in mode_boxes.items() if cb.value]
            if not modes:
                ui.notify("Mindestens ein Verkehrsmittel auswählen", type="warning")
                return
            weekdays = [i for i, c in chips.items() if c.selected]
            r = Route(
                id=existing.id if existing else storage.new_route_id(),
                name=name.value.strip(),
                origin=picked["origin"],
                destination=picked["destination"],
                departure=dep.value or "07:30",
                weekdays=weekdays,
                modes=modes,
                notify_time=notify.value or "06:45",
            )
            s = state.settings()
            if existing:
                s.routes = [r if x.id == existing.id else x for x in s.routes]
            else:
                s.routes.append(r)
            state.save()
            ui.notify("Strecke gespeichert", type="positive")
            dlg.close()
            routes_section.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=dlg.close).props("flat no-caps")
            ui.button("Speichern", icon="check", on_click=save).props("unelevated rounded no-caps")
    dlg.open()


def _time_input(label: str, value: str):
    with ui.input(label, value=value).props("outlined dense mask=time").classes("flex-1") as inp:
        with inp.add_slot("append"):
            ui.icon("schedule").classes("cursor-pointer").on("click", lambda: menu.open())
            with ui.menu() as menu:
                ui.time(value=value).props("format24h").bind_value(inp)
    return inp


# ---------------------------------------------------------------------------
# Vorlieben
# ---------------------------------------------------------------------------

PREF_GROUPS = [
    ("Zeit oder Geld?", "balance", "#64748b", [
        ("value_of_time_eur_h", "Was ist dir eine Stunde wert?", "€/h", 1, 50, 1,
         "Nur für die Empfehlung: Lohnt es sich, für weniger Geld etwas länger unterwegs zu sein? "
         "Die angezeigten Fahrzeiten bleiben echte Minuten."),
    ]),
    ("Rad", "directions_bike", "#10b981", [
        ("bike_max_km", "Maximale Strecke", "km", 1, 40, 0.5, "Darüber wird das Rad nicht vorgeschlagen."),
        ("bike_min_temp_c", "Mindesttemperatur", "°C", -10, 15, 1, "Darunter kein Rad."),
        ("bike_max_rain_mm", "Maximaler Regen", "mm/h", 0, 10, 0.1, "Darüber kein Rad."),
        ("bike_speed_factor", "Tempo-Faktor", "×", 0.6, 1.5, 0.05, "< 1 = du fährst schneller als das Routing annimmt."),
    ]),
    ("Auto", "directions_car", "#f59e0b", [
        ("fuel_price_eur_l", "Spritpreis", "€/l", 1, 3, 0.01, ""),
        ("consumption_l_100km", "Verbrauch", "l/100 km", 3, 15, 0.1, ""),
        ("parking_cost_eur", "Parkkosten am Ziel", "€", 0, 30, 0.5, ""),
        ("parking_search_min", "Parkplatzsuche", "min", 0, 30, 1, ""),
        ("rush_hour_factor", "Berufsverkehr-Faktor", "×", 1, 2, 0.05, "Mo–Fr 6:30–9:00 und 16:00–18:30."),
    ]),
]


def prefs_section() -> None:
    p = state.settings().prefs
    with ui.column().classes("card w-full gap-4"):
        with ui.column().classes("gap-0"):
            ui.label("Deine Vorlieben").classes("h-title")
            ui.label("Diese Werte steuern die Entscheidung. Änderungen werden sofort gespeichert.").classes("tiny muted")
        with ui.element("div").classes("w-full grid gap-4 grid-cols-1 md:grid-cols-2"):
            for title, icon, color, fields in PREF_GROUPS:
                with ui.column().classes("gap-2 p-4 rounded-2xl").style("background: var(--soft)"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon(icon).style(f"color:{color}").classes("text-xl")
                        ui.label(title).classes("font-bold")
                    for key, label, unit, lo, hi, step, hint in fields:
                        _pref_slider(p, key, label, unit, lo, hi, step, hint)


def _pref_slider(p, key, label, unit, lo, hi, step, hint) -> None:
    with ui.column().classes("w-full gap-0"):
        with ui.row().classes("w-full justify-between items-center"):
            ui.label(label).classes("text-sm font-medium")
            val = ui.label().classes("text-sm font-bold num")
        slider = ui.slider(min=lo, max=hi, step=step, value=getattr(p, key)).props("color=primary")

        def fmt(v):
            digits = 2 if step < 0.1 else 1 if step < 1 else 0
            val.text = f"{v:.{digits}f} {unit}".replace(".", ",")

        fmt(getattr(p, key))

        def changed(e, key=key):
            setattr(p, key, float(e.value))
            fmt(e.value)
            state.save()

        slider.on_value_change(changed)
        if hint:
            ui.label(hint).classes("tiny muted")


# ---------------------------------------------------------------------------
# Datenquellen
# ---------------------------------------------------------------------------


def sources_section() -> None:
    s = state.settings()
    with ui.column().classes("card w-full gap-4"):
        with ui.column().classes("gap-0"):
            ui.label("Datenquellen").classes("h-title")
            ui.label("Live-Daten aus offenen APIs oder Demo-Daten zum Ausprobieren.").classes("tiny muted")

        with ui.row().classes("w-full items-center gap-6 wrap"):
            demo = ui.switch("Demo-Modus", value=s.demo_mode)
            scen = ui.select(SCENARIOS, value=s.demo_scenario, label="Demo-Szenario").props("outlined dense").classes("min-w-[240px]")
            scen.bind_visibility_from(demo, "value")

        def on_demo(e):
            s.demo_mode = bool(e.value)
            state.save()
            ui.notify("Demo-Modus an – es werden Beispieldaten genutzt" if s.demo_mode else "Live-Modus – echte APIs werden abgefragt")

        def on_scen(e):
            s.demo_scenario = e.value
            state.save()

        demo.on_value_change(on_demo)
        scen.on_value_change(on_scen)

        api = ui.input("ÖPNV-Routing (Transitous/MOTIS, Basis-URL)", value=s.transit_api_base).props("outlined dense").classes("w-full")
        api.on("blur", lambda: (setattr(s, "transit_api_base", (api.value or "").strip() or "https://api.transitous.org"), state.save()))

