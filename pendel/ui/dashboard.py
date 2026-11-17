"""Startseite: die Empfehlung des Tages mit allen Details."""
from __future__ import annotations

import html
from datetime import timedelta

from nicegui import ui

from .. import state, timeutil
from ..decision import de
from ..engine import Result, recommend
from ..models import Mode, ModeScore
from . import journey, search, theme

SOURCE_NAMES = {"wetter": "Wetter", "bahn": "Bahn", "auto": "Autoroute", "rad": "Radroute", "autobahn": "Autobahn-Meldungen"}


def register() -> None:
    @ui.page("/")
    async def dashboard_page():
        if not state.check_login():
            return
        with theme.frame("/"):
            query = search.load_query()

            async def run(q: search.Query) -> None:
                content.clear()
                if not q.complete:
                    with content:
                        _empty_state()
                    return
                with content:
                    _skeleton()
                route = q.to_route()
                if q.arrive:
                    result = await recommend(route, state.settings(), arrive_by=q.when)
                else:
                    result = await recommend(route, state.settings(), departure=q.when)
                state.remember(result)
                content.clear()
                with content:
                    _render(result)

            search.search_card(query, run)  # oben: Von, Nach, Zeit – wie bei der DB
            content = ui.column().classes("w-full gap-[22px]")  # darunter: das Ergebnis
            await run(query)


def _empty_state() -> None:
    with ui.column().classes("card w-full items-center text-center py-14 gap-2"):
        ui.icon("travel_explore").classes("text-5xl muted")
        ui.label("Wohin soll es gehen?").classes("text-xl font-extrabold")
        ui.label("Gib oben Start und Ziel ein und wähle sie aus den Vorschlägen aus.").classes("muted")


def _skeleton() -> None:
    with ui.element("div").classes("result"):
        ui.skeleton().classes("w-full h-[270px]").props("square")
        ui.skeleton().classes("w-full h-[200px]").props("square")
    ui.skeleton().classes("w-full h-[130px]").props("square")


# ---------------------------------------------------------------------------
# Darstellung
# ---------------------------------------------------------------------------


def _render(result: Result) -> None:
    data, rec = result.data, result.rec

    if data.errors:
        names = ", ".join(SOURCE_NAMES.get(k, k) for k in data.errors)
        with ui.row().classes("notice items-center gap-3 no-wrap"):
            ui.icon("cloud_off").classes("text-xl").style("color: var(--warn)")
            with ui.column().classes("gap-0"):
                ui.label(f"Nicht erreichbar: {names}").classes("font-bold")
                ui.label("Die Empfehlung nutzt nur die übrigen Daten.").classes("tiny muted")
            ui.space()
            with ui.button("Details").props("flat dense no-caps").classes("link-btn"):
                with ui.menu().classes("p-3 max-w-[420px]"):
                    for k, v in data.errors.items():
                        ui.label(f"{SOURCE_NAMES.get(k, k)}: {v}").classes("tiny")

    if rec.best is None:
        with ui.column().classes("card w-full items-center py-10"):
            ui.icon("help_outline").classes("text-5xl muted")
            ui.label(rec.headline).classes("text-xl font-extrabold")
            for r in rec.reasons:
                ui.label(r).classes("muted")
        _info_row(result)
        return

    best = next(s for s in rec.scores if s.mode == rec.best)
    with ui.element("div").classes("result fade-in"):
        _verdict(result, best)
        _alternatives(result, best)
    _info_row(result)
    stamp = "Demo-Daten" if data.demo else f"Daten von {data.fetched_at:%H:%M} Uhr"
    ui.label(f"{stamp} · {result.route.origin.name} → {result.route.destination.name}").classes("tiny muted")


def _verdict(result: Result, best: ModeScore) -> None:
    """Die große Empfehlungsfläche links."""
    rec = result.rec
    icon = theme.season().icon
    with ui.element("div").classes("verdict"):
        with ui.element("div").classes("v-main"):
            ui.label(_when_text(result)).classes("kicker")
            ui.label(f"{best.mode.label}.").classes("v-word")
            for r in rec.reasons[:4]:
                with ui.element("div").classes("v-reason"):
                    ui.label(icon).classes("ic")
                    ui.label(r)
            ui.button("So setzt sich die Zeit zusammen", on_click=lambda: _breakdown_dialog(result)).props(
                "flat no-caps dense"
            ).classes("v-link tiny mt-3 self-start")
        ui.label("Beste Wahl" if rec.confidence == "klar" else "Knappe Sache").classes("stamp")

        with ui.element("div").classes("v-side"):
            with ui.column().classes("gap-0"):
                ui.label("Tür zu Tür").classes("kicker")
                ui.label(f"{best.total_min:.0f}").classes("v-time")
                ui.label(_time_line(result, best)).classes("v-small")
            with ui.column().classes("gap-0"):
                ui.label(f"{de(best.cost_eur, 2)} €").classes("v-cost")
                ui.label(_cost_line(best)).classes("v-small")
                if best.option is not None:
                    ui.button("Verbindung ansehen →", on_click=lambda o=best.option: journey.open_journey(o)).props(
                        "flat no-caps dense"
                    ).classes("v-link tiny mt-2")


def _alternatives(result: Result, best: ModeScore) -> None:
    """Die anderen Verkehrsmittel – klein und knapp."""
    colors = ["var(--a2)", "var(--a3)"]
    others = [s for s in result.rec.scores if s is not best]
    others.sort(key=lambda s: (not s.available, s.total_min))
    longest = max([s.total_min for s in result.rec.scores if s.available] or [1])
    with ui.element("div").classes("alts"):
        ui.label("Alternativen").classes("kicker")
        for i, s in enumerate(others):
            color = colors[i % 2]
            cls = "alt" + ("" if s.available else " off")
            with ui.element("div").classes(cls).style(f"--c:{color}") as row:
                ui.label(s.mode.label).classes("n")
                ui.label(f"{s.total_min:.0f} min" if s.available else "entfällt").classes("v")
                ui.label(_why(s, best)).classes("why")
                ui.label(f"{de(s.cost_eur, 2)} €" if s.available else "").classes("c")
                width = s.total_min / longest * 100 if s.available else 0
                theme.html(f'<div class="bar"><i style="width:{width:.0f}%"></i></div>').classes("contents")
            if s.available and s.option is not None:
                row.on("click", lambda o=s.option: journey.open_journey(o))
            elif s.available:
                row.on("click", lambda s=s: _breakdown_dialog(result, only=s))
        if not others:
            ui.label("Keine weiteren Verkehrsmittel gewählt.").classes("tiny muted")
        transit = next((s for s in result.rec.scores if s.mode == Mode.TRANSIT and s.option is not None), None)
        if transit and transit is not best:
            ui.button("Verbindungen & Fußwege ansehen →", on_click=lambda: journey.open_journey(transit.option)).props(
                "flat no-caps dense"
            ).classes("link-btn tiny self-start")


def _info_row(result: Result) -> None:
    """Schmale Detailzeile: nächste Bahnen, Wetter, Straße."""
    data = result.data
    with ui.element("div").classes("info"):
        # --- Nächste Bahnen
        with ui.element("div"):
            ui.label(f"Ankunft bis {result.arrive_by:%H:%M}" if result.arrive_by else "Nächste Bahnen").classes("kicker mb-2")
            options = data.transit
            if result.arrive_by:
                in_time = [o for o in options if (o.arrival - result.arrive_by).total_seconds() <= 60]
                options = sorted(in_time, key=lambda o: o.arrival, reverse=True) or options
            if not options:
                ui.label("Keine Verbindungsdaten." + (" Dienst nicht erreichbar." if "bahn" in data.errors else "")).classes(
                    "tiny muted"
                )
            for opt in options[:3]:
                chips = "".join(journey.line_chip(leg) for leg in opt.legs if not leg.walking)
                if opt.cancelled:
                    status = '<span style="color:var(--bad)">fällt aus</span>'
                elif opt.delay_min >= 2:
                    status = f'<span style="color:var(--bad)">+{opt.delay_min}</span>'
                else:
                    status = '<span class="muted">pünktl.</span>'
                strike = "text-decoration:line-through;opacity:.6" if opt.cancelled else ""
                row = theme.html(
                    f'<div class="conn"><span style="{strike}">{chips}<b>{opt.planned_departure:%H:%M}</b> '
                    f'<span class="muted">→ {opt.arrival:%H:%M} · {opt.duration_min:.0f} min</span></span>{status}</div>'
                ).classes("conn-click")
                row.on("click", lambda o=opt: journey.open_journey(o))

        # --- Wetter
        with ui.element("div"):
            ui.label("Wetter am Start").classes("kicker mb-2")
            if not data.weather:
                ui.label("Keine Wetterdaten.").classes("tiny muted")
            else:
                w = data.weather.at_departure
                with ui.row().classes("items-center gap-4 no-wrap"):
                    ui.label(f"{w.temp_c:.0f}°").classes("temp")
                    with ui.column().classes("gap-0"):
                        ui.label(f"{data.weather.description} · gefühlt {w.apparent_c:.0f}°").classes("text-sm")
                        ui.label(f"Regen {de(w.precip_mm)} mm/h · Wind {w.wind_kmh:.0f} km/h").classes("tiny muted")

        # --- Straße
        with ui.element("div"):
            ui.label("Straße").classes("kicker mb-2")
            ui.label(_road_text(result)).classes("text-sm")


def _breakdown_dialog(result: Result, only: ModeScore | None = None) -> None:
    """Zeigt, aus welchen echten Minuten sich jede Zeit zusammensetzt."""
    scores = [only] if only else [s for s in result.rec.scores]
    with ui.dialog() as dlg, ui.card().classes("w-[460px] max-w-[95vw] gap-3 p-6"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("So setzt sich die Zeit zusammen").classes("text-lg font-extrabold")
            ui.button(icon="close", on_click=dlg.close).props("flat round dense")
        for s in scores:
            ui.label(s.mode.label).classes("kicker mt-2")
            if not s.available:
                ui.label(s.excluded_reason).classes("tiny muted")
                continue
            for p in s.parts:
                theme.html(f'<div class="part-row"><span>{_esc(p.label)}</span><span>{de(p.minutes)} min</span></div>').classes("w-full")
            theme.html(
                f'<div class="part-row" style="font-weight:800"><span>Tür zu Tür</span><span>{de(s.total_min)} min · '
                f"{de(s.cost_eur, 2)} €</span></div>"
            ).classes("w-full")
        ui.label("Kosten werden nicht in Minuten umgerechnet. Nur die Empfehlung wägt Zeit gegen Geld ab.").classes(
            "tiny muted"
        )
    dlg.open()


# ---------------------------------------------------------------------------
# Kleine Text-Helfer
# ---------------------------------------------------------------------------


def _when_text(result: Result) -> str:
    if result.arrive_by:
        t = result.arrive_by
        return f"Unsere Empfehlung · Ankunft {timeutil.day_label(t)} bis {t:%H:%M}"
    t = result.departure
    return f"Unsere Empfehlung · Abfahrt {timeutil.day_label(t)} {t:%H:%M}"


def _time_line(result: Result, s: ModeScore) -> str:
    if s.option is not None:  # Bahn: echte Abfahrt und Ankunft
        return f"Minuten · {s.option.departure:%H:%M} ab, {s.option.arrival:%H:%M} an"
    if result.arrive_by:
        return f"Minuten · los um {result.arrive_by - timedelta(minutes=s.total_min):%H:%M}"
    return f"Minuten · an ca. {result.departure + timedelta(minutes=s.total_min):%H:%M}"


def _cost_line(s: ModeScore) -> str:
    if s.mode == Mode.BIKE:
        return "Kein Ticket, kein Sprit."
    if s.mode == Mode.CAR:
        return "Sprit (und Parken, falls eingestellt)."
    if state.settings().prefs.has_deutschlandticket:
        return "Mit Deutschlandticket."
    if s.option is not None and s.option.fare_label:
        return s.option.fare_label
    return "EinzelTicket"


def _why(s: ModeScore, best: ModeScore) -> str:
    """Kurzer Grund für eine Alternative, z. B. „2 min langsamer · Berufsverkehr“."""
    if not s.available:
        return s.excluded_reason
    dt = round(s.total_min) - round(best.total_min)
    head = f"{dt} min langsamer" if dt > 0 else f"{-dt} min schneller" if dt < 0 else "gleich schnell"
    if s.option is not None:
        lines = " → ".join(s.option.lines)
        return f"{head} · {s.option.departure:%H:%M} {lines}"
    extra = max((p for p in s.parts if not p.label.startswith("Fahrzeit")), key=lambda p: p.minutes, default=None)
    return f"{head} · {extra.label}" if extra and extra.minutes >= 1 else head


def _road_text(result: Result) -> str:
    data = result.data
    if "autobahn" in data.errors:
        return "Autobahn-Meldungen gerade nicht erreichbar."
    car = next((s for s in result.rec.scores if s.mode == Mode.CAR and s.available), None)
    extras = [p for p in (car.parts if car else []) if not p.label.startswith("Fahrzeit")]
    parts = ", ".join(f"{p.label} +{p.minutes:.0f} min" for p in extras)
    if data.incidents:
        first = data.incidents[0]
        head = first.title + (f" – {first.subtitle}" if first.subtitle else "")
        return f"{head}. {parts}." if parts else head
    return f"Keine Meldungen. {parts}." if parts else "Keine Meldungen."


def _esc(s: str) -> str:
    return html.escape(s)
