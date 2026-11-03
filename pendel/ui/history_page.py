"""Verlauf: Welche Empfehlungen gab es an den letzten Tagen?"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from nicegui import app, ui

from .. import state, storage
from ..decision import evaluate
from ..demo import demo_data
from ..models import Mode
from ..timeutil import WEEKDAYS
from . import theme


def register() -> None:
    @ui.page("/verlauf")
    def history_page():
        if not state.check_login():
            return
        s = state.settings()
        with theme.frame("/verlauf", demo=s.demo_mode):
            with ui.row().classes("w-full items-end justify-between"):
                with ui.column().classes("gap-0"):
                    ui.label("Verlauf").classes("text-2xl font-extrabold tracking-tight")
                    ui.label("Jeden Pendeltag wird die Morgen-Empfehlung automatisch gespeichert.").classes("muted")
                if s.demo_mode:
                    ui.button("Demo-Verlauf erzeugen", icon="auto_awesome", on_click=lambda: (_fake_history(), content.refresh())).props(
                        "unelevated rounded no-caps"
                    ).tooltip("Simuliert die letzten 30 Tage mit Demo-Daten")
            content()


@ui.refreshable
def content() -> None:
    entries = storage.load_history()
    routes = {r.id: r.name for r in state.settings().routes}
    if not entries:
        with ui.column().classes("card w-full items-center text-center py-14 gap-2"):
            ui.icon("insights").classes("text-5xl muted")
            ui.label("Noch kein Verlauf").classes("text-xl font-bold")
            ui.label("Sobald die App morgens läuft, sammeln sich hier die Empfehlungen.").classes("muted")
        return

    counts = Counter(e["best"] for e in entries if e["best"])
    total = sum(counts.values()) or 1
    with ui.element("div").classes("w-full grid gap-5 grid-cols-1 md:grid-cols-3"):
        for m in Mode:
            n = counts.get(m.value, 0)
            with ui.column().classes("card mode-card gap-1").style(f"--accent:{m.color}"):
                with ui.row().classes("items-center gap-3"):
                    with ui.element("div").classes("mode-badge"):
                        ui.icon(m.icon).classes("text-2xl")
                    ui.label(m.label).classes("text-lg font-bold")
                with ui.row().classes("items-baseline gap-2"):
                    ui.label(str(n)).classes("big-num num")
                    ui.label(f"Tage · {n / total * 100:.0f} %").classes("muted")

    dark = bool(app.storage.user.get("dark", False))
    axis, grid = "#94a3b8", ("#243049" if dark else "#eef1f6")
    days = sorted({e["date"] for e in entries})[-30:]
    with ui.column().classes("card w-full gap-2"):
        ui.label("Gefühlte Minuten pro Tag").classes("h-title")
        ui.label("Je niedriger, desto besser. Die Empfehlung ist jeweils der tiefste Punkt.").classes("tiny muted")
        route_id = entries[-1]["route_id"]
        sel = [e for e in entries if e["route_id"] == route_id and e["date"] in days]
        series = []
        for m in Mode:
            series.append({
                "name": m.label, "type": "line", "smooth": 0.25, "symbol": "circle", "symbolSize": 6, "connectNulls": False,
                "lineStyle": {"width": 2.5, "color": m.color}, "itemStyle": {"color": m.color},
                "data": [next((e["scores"].get(m.value) for e in sel if e["date"] == d), None) for d in days],
            })
        ui.echart({
            "grid": {"left": 40, "right": 16, "top": 36, "bottom": 30},
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 0, "right": 0, "textStyle": {"color": axis}},
            "xAxis": {"type": "category", "data": [datetime.fromisoformat(d).strftime("%d.%m.") for d in days],
                      "axisLabel": {"color": axis}, "axisLine": {"lineStyle": {"color": grid}}, "axisTick": {"show": False}},
            "yAxis": {"type": "value", "axisLabel": {"color": axis}, "splitLine": {"lineStyle": {"color": grid}}},
            "series": series,
        }).classes("w-full h-[280px]")
        ui.label(f"Strecke: {routes.get(route_id, entries[-1]['route_name'])}").classes("tiny muted")

    with ui.column().classes("card w-full gap-2"):
        ui.label("Letzte Empfehlungen").classes("h-title")
        rows = [
            {
                "datum": f"{WEEKDAYS[date.fromisoformat(e['date']).weekday()]} {date.fromisoformat(e['date']):%d.%m.}",
                "strecke": routes.get(e["route_id"], e["route_name"]),
                "empfehlung": Mode(e["best"]).label if e["best"] else "–",
                "sicherheit": e["confidence"].capitalize(),
                "wetter": e["weather"],
            }
            for e in reversed(entries[-60:])
        ]
        ui.table(
            columns=[
                {"name": "datum", "label": "Datum", "field": "datum", "align": "left"},
                {"name": "strecke", "label": "Strecke", "field": "strecke", "align": "left"},
                {"name": "empfehlung", "label": "Empfehlung", "field": "empfehlung", "align": "left"},
                {"name": "sicherheit", "label": "Entscheidung", "field": "sicherheit", "align": "left"},
                {"name": "wetter", "label": "Wetter", "field": "wetter", "align": "left"},
            ],
            rows=rows,
            pagination=10,
        ).props("flat").classes("w-full bg-transparent")


def _fake_history() -> None:
    """Simuliert 30 Tage mit Demo-Daten (nur zum Ausprobieren der Ansicht)."""
    s = state.settings()
    if not s.routes:
        return
    route = s.routes[0]
    h, m = map(int, route.departure.split(":"))
    for i in range(30, 0, -1):
        d = date.today() - timedelta(days=i)
        if d.weekday() not in route.weekdays:
            continue
        dep = datetime(d.year, d.month, d.day, h, m)
        data = demo_data(route, dep, "auto")
        rec = evaluate(route, s.prefs, data, dep)
        w = data.weather.at_departure if data.weather else None
        storage.add_history(route, rec, f"{data.weather.description}, {w.temp_c:.0f} °C" if w else "", day=d)
    ui.notify("30 Tage Demo-Verlauf erzeugt", type="positive")
