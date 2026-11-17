"""Detailansicht einer Bahnverbindung: alle Abschnitte, Gleise, Fußwege und eine Karte.

Öffnet sich als Dialog, wenn man auf eine Verbindung klickt (wie in der DB-App).
"""
from __future__ import annotations

import html

from nicegui import ui

from ..models import TransitLeg, TransitOption

# Farben der Linien-Chips, falls der Fahrplan keine eigene Linienfarbe mitliefert
KIND_COLORS = {"S": "#16a34a", "U": "#2563eb", "B": "#c026d3", "R": "#64748b", "F": "#dc2626"}


def line_chip(leg: TransitLeg) -> str:
    """HTML für einen farbigen Linien-Chip (z. B. „U2“ in Rot)."""
    bg = leg.color or KIND_COLORS.get(leg.kind, "var(--bahn)")
    fg = leg.text_color or "#ffffff"
    return f'<span class="line-chip" style="background:{bg};color:{fg}">{html.escape(leg.line)}</span>'


def open_journey(opt: TransitOption) -> None:
    """Zeigt die Verbindung Schritt für Schritt in einem Dialog."""
    with ui.dialog() as dlg, ui.card().classes("journey-card w-[760px] max-w-[96vw] p-0 gap-0"):
        # --- Kopf ----------------------------------------------------------------
        with ui.row().classes("w-full items-center justify-between px-6 pt-5 pb-3 no-wrap"):
            with ui.column().classes("gap-0"):
                ui.label(f"{opt.departure:%H:%M} – {opt.arrival:%H:%M}").classes("text-2xl font-extrabold num")
                info = f"{opt.duration_min:.0f} min · {opt.transfers}× umsteigen"
                if opt.delay_min >= 2:
                    info += f" · aktuell +{opt.delay_min} min"
                ui.label(info).classes("muted")
            ui.button(icon="close", on_click=dlg.close).props("flat round dense")
        if opt.cancelled:
            ui.html('<div class="pill bad mx-6 mb-2">Diese Verbindung fällt (teilweise) aus</div>', sanitize=False)

        with ui.element("div").classes("journey-body w-full"):
            # --- Ablauf links ------------------------------------------------------
            with ui.column().classes("journey-steps gap-0"):
                for leg in opt.legs:
                    _walk(leg) if leg.walking else _ride(leg)
            # --- Karte rechts ------------------------------------------------------
            _map(opt)
    dlg.open()


def _ride(leg: TransitLeg) -> None:
    color = leg.color or KIND_COLORS.get(leg.kind, "var(--bahn)")
    delay = f' <span class="tiny" style="color:var(--bad)">+{leg.delay_min}</span>' if leg.delay_min >= 2 else ""
    strike = "text-decoration:line-through;opacity:.6;" if leg.cancelled else ""
    track_from = f'<span class="track">Gl. {html.escape(leg.track_from)}</span>' if leg.track_from else ""
    track_to = f'<span class="track">Gl. {html.escape(leg.track_to)}</span>' if leg.track_to else ""
    head = f" → {html.escape(leg.headsign)}" if leg.headsign else ""
    stops = f" · {leg.stops_between} Zwischenhalte" if leg.stops_between else ""
    ui.html(
        f'<div class="jleg ride" style="--line-c:{color};{strike}">'
        f'<div class="jtime num">{leg.departure:%H:%M}</div><div class="jdot"></div>'
        f'<div class="jtext"><b>{html.escape(leg.origin)}</b> {track_from}</div>'
        f'<div></div><div class="jbar"></div>'
        f'<div class="jtext jmid">{line_chip(leg)}<span class="muted">{head}</span>'
        f'<div class="tiny muted">{leg.duration_min:.0f} min{stops}</div></div>'
        f'<div class="jtime num">{leg.arrival:%H:%M}{delay}</div><div class="jdot"></div>'
        f'<div class="jtext"><b>{html.escape(leg.destination)}</b> {track_to}</div>'
        f"</div>",
        sanitize=False,
    ).classes("w-full")


def _walk(leg: TransitLeg) -> None:
    dist = f"{leg.distance_m:.0f} m · " if leg.distance_m else ""
    label = f"Fußweg · {dist}{max(1, round(leg.duration_min))} min"
    with ui.element("div").classes("jleg walk w-full"):
        ui.html('<div class="jtime"></div><div class="jbar dotted"></div>', sanitize=False).classes("contents")
        with ui.column().classes("jtext gap-0"):
            if leg.steps:
                with ui.expansion(label, icon="directions_walk").props("dense").classes("walk-exp w-full"):
                    for i, step in enumerate(leg.steps[:12], 1):
                        ui.label(f"{i}. {step}").classes("tiny")
            else:
                with ui.row().classes("items-center gap-2 py-1"):
                    ui.icon("directions_walk").classes("muted")
                    ui.label(label).classes("tiny muted")


def _map(opt: TransitOption) -> None:
    points = [p for leg in opt.legs for p in leg.path]
    if len(points) < 2:
        return
    lat = sum(p[0] for p in points) / len(points)
    lon = sum(p[1] for p in points) / len(points)
    m = ui.leaflet(center=(lat, lon), zoom=13).classes("journey-map")
    for leg in opt.legs:
        if len(leg.path) < 2:
            continue
        style = (
            {"color": "#64748b", "weight": 4, "dashArray": "4 8"}
            if leg.walking
            else {"color": leg.color or KIND_COLORS.get(leg.kind, "#6366f1"), "weight": 6, "opacity": 0.9}
        )
        m.generic_layer(name="polyline", args=[[list(p) for p in leg.path], style])
    m.marker(latlng=points[0])
    m.marker(latlng=points[-1])
    south, north = min(p[0] for p in points), max(p[0] for p in points)
    west, east = min(p[1] for p in points), max(p[1] for p in points)
    # Karte erst nach dem Öffnen auf den ganzen Weg zoomen (sonst ist sie noch 0 px groß)
    def fit() -> None:
        m.run_map_method("invalidateSize")
        m.run_map_method("fitBounds", [[south, west], [north, east]], {"padding": [24, 24]})

    ui.timer(0.4, fit, once=True)
