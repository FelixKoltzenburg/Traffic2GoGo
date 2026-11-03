"""Startseite: die Empfehlung des Tages mit allen Details."""
from __future__ import annotations

import math

from nicegui import app, ui

from .. import state, timeutil
from ..decision import de
from ..engine import Result, recommend
from ..models import Mode, ModeScore, TravelData
from ..weather_codes import icon as wx_icon
from . import theme

SOURCE_NAMES = {"wetter": "Wetter", "bahn": "Bahn", "auto": "Autoroute", "rad": "Radroute", "autobahn": "Autobahn-Meldungen"}


def register() -> None:
    @ui.page("/")
    async def dashboard_page():
        if not state.check_login():
            return
        settings = state.settings()
        with theme.frame("/", demo=settings.demo_mode):
            if not settings.routes:
                _empty_state()
                return

            selected = {"id": app.storage.user.get("route_id", settings.routes[0].id)}
            if selected["id"] not in {r.id for r in settings.routes}:
                selected["id"] = settings.routes[0].id

            # --- Kopf: Streckenwahl + Aktualisieren ---------------------------
            with ui.row().classes("w-full items-end justify-between gap-4 wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(f"Guten {_greeting()}" + (f", {settings.user_name}" if settings.user_name else "")).classes("text-2xl font-extrabold tracking-tight")
                    info = ui.label("").classes("muted")
                with ui.row().classes("items-center gap-2"):
                    toggle = ui.toggle(
                        {r.id: r.name for r in settings.routes}, value=selected["id"]
                    ).props("rounded unelevated toggle-color=primary no-caps").classes("bg-[color:var(--card)]")
                    refresh_btn = ui.button(icon="refresh").props("round unelevated color=primary").tooltip("Neu berechnen")

            content = ui.column().classes("w-full gap-5")

            async def load(force: bool = False):
                content.clear()
                with content:
                    _skeleton()
                route = next(r for r in settings.routes if r.id == selected["id"])
                if force:
                    state.clear_cache()
                result = await recommend(route, state.settings())
                state.remember(result)
                dep = result.departure
                info.text = (
                    f"{route.origin.name} → {route.destination.name} · Abfahrt {timeutil.day_label(dep)} um {dep:%H:%M} Uhr"
                )
                content.clear()
                with content:
                    _render(result)

            async def on_route(e):
                selected["id"] = e.value
                app.storage.user["route_id"] = e.value
                await load()

            toggle.on_value_change(on_route)
            refresh_btn.on_click(lambda: load(force=True))
            await load()


def _greeting() -> str:
    h = timeutil.now().hour
    return "Morgen" if h < 11 else "Tag" if h < 18 else "Abend"


def _empty_state() -> None:
    with ui.column().classes("card w-full items-center text-center py-16 gap-3"):
        ui.icon("add_road").classes("text-5xl muted")
        ui.label("Noch keine Strecke angelegt").classes("text-xl font-bold")
        ui.label("Lege in den Einstellungen deinen Weg an, z. B. Wohnung → DHBW.").classes("muted")
        ui.button("Strecke anlegen", icon="add", on_click=lambda: ui.navigate.to("/einstellungen")).props("unelevated rounded no-caps")


def _skeleton() -> None:
    ui.skeleton().classes("w-full h-[230px] rounded-[26px]")
    with ui.row().classes("w-full gap-5 no-wrap max-md:flex-col"):
        for _ in range(3):
            ui.skeleton().classes("flex-1 h-[220px] rounded-[20px] max-md:w-full")


# ---------------------------------------------------------------------------
# Darstellung
# ---------------------------------------------------------------------------


def _render(result: Result) -> None:
    data, rec = result.data, result.rec

    if data.errors:
        names = ", ".join(SOURCE_NAMES.get(k, k) for k in data.errors)
        with ui.row().classes("card w-full items-center gap-3 py-3").style("border-color: var(--warn)"):
            ui.icon("cloud_off").classes("text-xl").style("color: var(--warn)")
            with ui.column().classes("gap-0"):
                ui.label(f"Nicht erreichbar: {names}").classes("font-semibold")
                ui.label("Die Empfehlung nutzt nur die übrigen Daten. Tipp: Demo-Modus in den Einstellungen.").classes("tiny muted")
            ui.space()
            with ui.button("Details", icon="info").props("flat dense no-caps"):
                with ui.menu().classes("p-3 max-w-[420px]"):
                    for k, v in data.errors.items():
                        ui.label(f"{SOURCE_NAMES.get(k, k)}: {v}").classes("tiny")

    _hero(result)

    available = [s for s in rec.scores if s.available]
    worst = max((s.felt_min for s in available), default=1)
    with ui.element("div").classes("w-full grid gap-5 grid-cols-1 md:grid-cols-3 items-start"):
        for i, s in enumerate(rec.scores):
            _mode_card(s, winner=(s.mode == rec.best), scale=worst, delay=i + 1)

    with ui.element("div").classes("w-full grid gap-5 grid-cols-1 lg:grid-cols-5"):
        with ui.column().classes("card lg:col-span-3 gap-3 fade-in"):
            _weather_card(data, result)
        with ui.column().classes("lg:col-span-2 gap-5"):
            with ui.column().classes("card w-full gap-1 fade-in d1"):
                _transit_card(data)
            with ui.column().classes("card w-full gap-1 fade-in d2"):
                _traffic_card(data)

    stamp = "Demo-Daten" if data.demo else f"Daten von {data.fetched_at:%H:%M} Uhr"
    ui.label(f"{stamp} · Empfehlung für {result.route.name}").classes("tiny muted")


def _hero(result: Result) -> None:
    rec = result.rec
    if rec.best is None:
        with ui.column().classes("card w-full items-center py-10"):
            ui.icon("help_outline").classes("text-5xl muted")
            ui.label(rec.headline).classes("text-xl font-bold")
            for r in rec.reasons:
                ui.label(r).classes("muted")
        return

    color = rec.best.color
    gradient = f"linear-gradient(135deg, {color} 0%, color-mix(in srgb, {color} 70%, #0f172a) 100%)"
    with ui.element("div").classes("hero w-full fade-in").style(f"background:{gradient}; --accent:{color}"):
        with ui.row().classes("w-full gap-6 items-stretch no-wrap max-md:flex-col relative z-[1]"):
            with ui.column().classes("flex-1 gap-4"):
                with ui.row().classes("items-center gap-5 no-wrap"):
                    with ui.element("div").classes("hero-icon shrink-0"):
                        ui.icon(rec.best.icon).classes("text-5xl text-white")
                    with ui.column().classes("gap-1"):
                        ui.label(
                            f"Empfehlung für {timeutil.day_label(result.departure)}, {result.departure:%H:%M} Uhr"
                        ).classes("text-sm opacity-90 font-medium")
                        ui.label(rec.headline).classes("hero-mode")
                        conf = {"klar": ("verified", "Klare Sache"), "knapp": ("balance", "Knappe Entscheidung")}
                        ic, txt = conf.get(rec.confidence, ("help", "Unsicher"))
                        ui.html(f'<span class="pill on-dark"><span class="material-icons" style="font-size:15px">{ic}</span>{txt}</span>')
                with ui.column().classes("gap-2"):
                    for r in rec.reasons[:5]:
                        with ui.element("div").classes("hero-reason"):
                            ui.icon("check_circle").classes("text-lg opacity-90 shrink-0 mt-[1px]")
                            ui.label(r)
            with ui.column().classes("hero-panel w-[320px] max-md:w-full gap-3 shrink-0"):
                ui.label("Gefühlte Minuten").classes("text-sm font-semibold opacity-90")
                avail = [s for s in rec.scores if s.available]
                mx = max((s.felt_min for s in avail), default=1)
                for s in sorted(rec.scores, key=lambda x: (not x.available, x.felt_min)):
                    with ui.column().classes("w-full gap-1"):
                        with ui.row().classes("w-full justify-between items-center"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon(s.mode.icon).classes("text-lg")
                                ui.label(s.mode.label).classes("font-semibold")
                            ui.label(f"{s.felt_min:.0f} min" if s.available else "entfällt").classes("num font-bold")
                        width = max(4, s.felt_min / mx * 100) if s.available and mx > 0 else 0
                        opacity = 1 if s.mode == rec.best else 0.55
                        ui.html(
                            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.0f}%;opacity:{opacity}"></div></div>'
                        ).classes("w-full")
                ui.label("Weniger ist besser: Reisezeit + Aufschläge + Kosten.").classes("tiny opacity-80")


def _mode_card(s: ModeScore, winner: bool, scale: float, delay: int) -> None:
    cls = "card mode-card gap-3 fade-in d" + str(delay)
    if winner:
        cls += " winner"
    if not s.available:
        cls += " off"
    with ui.column().classes(cls).style(f"--accent:{s.mode.color}"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.row().classes("items-center gap-3 no-wrap"):
                with ui.element("div").classes("mode-badge"):
                    ui.icon(s.mode.icon).classes("text-2xl")
                ui.label(s.mode.label).classes("text-lg font-bold")
            if winner:
                ui.html('<span class="pill good"><span class="material-icons" style="font-size:14px">emoji_events</span>Empfohlen</span>')
            elif not s.available:
                ui.html('<span class="pill bad">Entfällt</span>')

        if not s.available:
            with ui.row().classes("items-start gap-2 no-wrap"):
                ui.icon("block").classes("muted mt-[2px]")
                ui.label(s.excluded_reason).classes("muted")
            return

        with ui.row().classes("items-baseline gap-2"):
            ui.label(f"{s.felt_min:.0f}").classes("big-num num")
            ui.label("gefühlte min").classes("muted font-medium")
        with ui.row().classes("gap-2 wrap"):
            ui.html(f'<span class="pill"><span class="material-icons" style="font-size:14px">schedule</span>ca. {s.travel_min:.0f} min</span>')
            ui.html(f'<span class="pill"><span class="material-icons" style="font-size:14px">euro</span>{de(s.cost_eur, 2)} €</span>')
        for n in s.notes[:2]:
            ui.label(n).classes("tiny muted leading-snug")
        with ui.expansion("Wie kommt die Zahl zustande?", icon="calculate").props("dense header-class='px-0 text-[color:var(--muted)]'").classes("w-full tiny"):
            for p in s.parts:
                sign = "plus" if p.minutes > 0 and not p.label.startswith("Fahrzeit") else "minus" if p.minutes < 0 else ""
                txt = f"{p.minutes:+.1f}".replace(".", ",") if p.label != s.parts[0].label else f"{p.minutes:.1f}".replace(".", ",")
                ui.html(f'<div class="part-row"><span>{p.label}</span><span class="num {sign}">{txt} min</span></div>').classes("w-full")
            ui.html(f'<div class="part-row" style="font-weight:700"><span>Summe</span><span class="num">{de(s.felt_min)} min</span></div>').classes("w-full")


def _weather_card(data: TravelData, result: Result) -> None:
    with ui.row().classes("w-full items-center justify-between"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("wb_cloudy").classes("text-xl").style("color: var(--bahn)")
            ui.label("Wetter am Start").classes("h-title")
        ui.label(result.route.origin.name).classes("tiny muted")
    if not data.weather:
        ui.label("Keine Wetterdaten verfügbar.").classes("muted")
        return
    w = data.weather.at_departure
    with ui.row().classes("w-full items-center gap-5 wrap"):
        with ui.row().classes("items-center gap-3 no-wrap"):
            ui.icon(wx_icon(w.code)).classes("text-5xl").style(f"color: {'var(--bahn)' if w.precip_mm > 0 or w.code >= 45 else 'var(--warn)'}")
            with ui.column().classes("gap-0"):
                ui.label(f"{w.temp_c:.0f} °C").classes("text-3xl font-extrabold num leading-none")
                ui.label(f"{data.weather.description} · gefühlt {w.apparent_c:.0f} °C").classes("muted text-sm")
        ui.space()
        with ui.row().classes("gap-2 wrap"):
            for ic, label, val in (
                ("water_drop", "Regen", f"{de(w.precip_mm)} mm/h"),
                ("umbrella", "Risiko", f"{w.precip_prob} %"),
                ("air", "Wind", f"{w.wind_kmh:.0f} km/h"),
                ("storm", "Böen", f"{w.gusts_kmh:.0f} km/h"),
            ):
                with ui.column().classes("wx-stat gap-0 min-w-[86px]"):
                    with ui.row().classes("items-center gap-1"):
                        ui.icon(ic).classes("text-sm muted")
                        ui.label(label).classes("tiny muted")
                    ui.label(val).classes("font-bold num")

    hours = data.weather.hours
    dep_label = f"{w.time:%H} Uhr"
    dark = bool(app.storage.user.get("dark", False))
    axis = "#94a3b8"
    grid = "#243049" if dark else "#eef1f6"
    ui.echart(
        {
            "animationDuration": 700,
            "grid": {"left": 36, "right": 40, "top": 30, "bottom": 28},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Temperatur °C", "Regen mm/h"], "right": 0, "top": 0, "textStyle": {"color": axis, "fontSize": 11}, "itemWidth": 14},
            "xAxis": {
                "type": "category",
                "data": [f"{h.time:%H} Uhr" for h in hours],
                "axisLine": {"lineStyle": {"color": grid}},
                "axisLabel": {"color": axis, "fontSize": 11},
                "axisTick": {"show": False},
            },
            "yAxis": [
                {"type": "value", "splitLine": {"lineStyle": {"color": grid}}, "axisLabel": {"color": axis, "fontSize": 11, "formatter": "{value}°"}},
                {"type": "value", "min": 0, "max": max(2, math.ceil(max((h.precip_mm for h in hours), default=0) * 1.4)),
                 "splitLine": {"show": False}, "axisLabel": {"color": axis, "fontSize": 11}},
            ],
            "series": [
                {
                    "name": "Regen mm/h", "type": "bar", "yAxisIndex": 1, "barWidth": "45%",
                    "data": [h.precip_mm for h in hours],
                    "itemStyle": {"color": "rgba(37,99,235,.45)", "borderRadius": [4, 4, 0, 0]},
                },
                {
                    "name": "Temperatur °C", "type": "line", "smooth": True, "symbol": "circle", "symbolSize": 6,
                    "data": [h.temp_c for h in hours],
                    "lineStyle": {"width": 3, "color": "#ea580c"}, "itemStyle": {"color": "#ea580c"},
                    "areaStyle": {"color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                  "colorStops": [{"offset": 0, "color": "rgba(234,88,12,.25)"}, {"offset": 1, "color": "rgba(234,88,12,0)"}]}},
                    "markLine": {"symbol": "none", "label": {"formatter": "Abfahrt", "color": axis, "fontSize": 11},
                                 "lineStyle": {"color": "#16a34a", "type": "dashed", "width": 1.5},
                                 "data": [{"xAxis": dep_label}]},
                },
            ],
        }
    ).classes("w-full h-[230px]")


def _transit_card(data: TravelData) -> None:
    with ui.row().classes("items-center gap-2 mb-1"):
        ui.icon("train").classes("text-xl").style("color: var(--bahn)")
        ui.label("Nächste Verbindungen").classes("h-title")
    if not data.transit:
        ui.label("Keine Verbindungsdaten." + (" Dienst nicht erreichbar." if "bahn" in data.errors else "")).classes("muted")
        return
    for opt in data.transit[:4]:
        chips = "".join(
            f'<span class="line-chip {(_line_kind(ln))}">{ln}</span>' for ln in opt.lines
        ) or '<span class="muted tiny">zu Fuß</span>'
        if opt.cancelled:
            status = '<span class="pill bad">Fällt aus</span>'
        elif opt.delay_min >= 5:
            status = f'<span class="pill bad">+{opt.delay_min} min</span>'
        elif opt.delay_min >= 2:
            status = f'<span class="pill warn">+{opt.delay_min} min</span>'
        else:
            status = '<span class="pill good">pünktlich</span>'
        strike = "text-decoration:line-through;opacity:.6;" if opt.cancelled else ""
        ui.html(
            f'<div class="conn"><div style="{strike}"><div class="font-bold num">{opt.planned_departure:%H:%M}</div>'
            f'<div class="tiny muted num">an {opt.arrival:%H:%M}</div></div>'
            f'<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;{strike}">{chips}'
            f'<span class="tiny muted">{opt.duration_min:.0f} min · {opt.transfers}× um</span></div>'
            f"<div>{status}</div></div>"
        ).classes("w-full")


def _line_kind(line: str) -> str:
    first = line.strip()[:1].upper()
    if line.startswith("Bus"):
        return "B"
    return first if first in {"S", "U", "R"} else ""


def _traffic_card(data: TravelData) -> None:
    with ui.row().classes("items-center gap-2 mb-1"):
        ui.icon("traffic").classes("text-xl").style("color: var(--auto)")
        ui.label("Verkehr auf deiner Autoroute").classes("h-title")
    if "autobahn" in data.errors:
        ui.label("Autobahn-Meldungen nicht erreichbar.").classes("muted")
        return
    if data.car is None or data.car.estimated:
        ui.label("Autoroute nicht verfügbar – Autobahn-Meldungen können nicht zugeordnet werden.").classes("muted text-sm")
        return
    if not data.incidents:
        with ui.row().classes("items-start gap-2 no-wrap"):
            ui.icon("check_circle").classes("mt-[2px]").style("color: var(--good)")
            roads = ", ".join(data.car.roads) if data.car and data.car.roads else ""
            ui.label(f"Keine Meldungen auf {roads}." if roads else "Keine Autobahn auf deiner Route – nur Berufsverkehr wird geschätzt.").classes("muted text-sm")
        return
    for inc in data.incidents[:4]:
        icon, color = {
            "closure": ("block", "var(--bad)"),
            "roadworks": ("construction", "var(--warn)"),
        }.get(inc.kind, ("warning", "var(--bad)" if inc.blocked else "var(--warn)"))
        delay = f'<span class="pill bad">+{inc.delay_min:.0f} min</span>' if inc.delay_min else ""
        ui.html(
            f'<div class="incident"><span class="material-icons" style="color:{color}">{icon}</span>'
            f'<div style="flex:1"><div class="font-semibold text-sm">{_esc(inc.title)}</div>'
            f'<div class="tiny muted">{_esc(inc.subtitle)}</div></div>{delay}</div>'
        ).classes("w-full")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
