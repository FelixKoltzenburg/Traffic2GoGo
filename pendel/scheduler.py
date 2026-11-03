"""Hintergrund-Job: berechnet jeden Pendeltag zur eingestellten Uhrzeit die
Empfehlung, speichert sie im Verlauf und schickt optional eine Push-Nachricht.

Bewusst ohne Zusatzbibliothek: eine Schleife, die jede Minute prüft, ob es
Zeit ist. (Ausbaustufe: APScheduler mit Cron-Ausdrücken.)
"""
from __future__ import annotations

import asyncio
import logging

from . import state, storage, timeutil
from .engine import recommend
from .notify import send_push

log = logging.getLogger("pendel.scheduler")
_done: set[tuple[str, str]] = set()  # (Datum, Strecken-ID) – heute schon erledigt?


async def run_forever() -> None:
    log.info("Morgen-Scheduler gestartet")
    while True:
        try:
            await tick()
        except Exception:  # noqa: BLE001 – der Scheduler darf nie abstürzen
            log.exception("Fehler im Scheduler")
        await asyncio.sleep(60 - timeutil.now().second)  # immer zur vollen Minute


async def tick() -> None:
    now = timeutil.now()
    hhmm = now.strftime("%H:%M")
    settings = state.settings()
    for route in settings.routes:
        key = (now.date().isoformat(), route.id)
        if key in _done or route.notify_time != hhmm or now.weekday() not in route.weekdays:
            continue
        _done.add(key)
        result = await recommend(route, settings)
        rec, data = result.rec, result.data
        w = data.weather.at_departure if data.weather else None
        weather_text = f"{data.weather.description}, {w.temp_c:.0f} °C" if w else ""
        storage.add_history(route, rec, weather_text)
        log.info("Empfehlung für %s: %s", route.name, rec.headline)
        if settings.ntfy_topic and rec.best:
            body = "\n".join(rec.reasons[:4])
            await send_push(
                settings.ntfy_topic,
                f"{route.name}: heute {rec.best.label} ({result.departure:%H:%M})",
                body,
                tags={"rad": "bike", "bahn": "train", "auto": "car"}[rec.best.value],
            )
