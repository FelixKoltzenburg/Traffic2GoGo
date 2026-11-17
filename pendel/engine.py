"""Sammelt die Daten aller Quellen parallel und berechnet die Empfehlung.

Jede Quelle darf ausfallen: Der Fehler wird gemerkt und in der Oberfläche
angezeigt, die übrigen Daten werden trotzdem genutzt.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import timeutil
from .decision import evaluate
from .demo import demo_data
from .models import Recommendation, Route, Settings, TravelData
from .services import fares, routing, traffic, transit, weather

log = logging.getLogger("pendel")


@dataclass
class Result:
    route: Route
    departure: datetime  # gewünschte Abfahrt (im Ankunft-Modus: geschätzt)
    data: TravelData
    rec: Recommendation
    arrive_by: datetime | None = None


async def collect_live(
    route: Route, settings: Settings, departure: datetime, arrive_by: datetime | None = None
) -> TravelData:
    errors: dict[str, str] = {}

    async def safe(name: str, coro):
        try:
            return await coro
        except Exception as e:  # noqa: BLE001 – wir wollen jeden Fehler abfangen
            log.warning("Quelle %s fehlgeschlagen: %s", name, e)
            errors[name] = _short(e)
            return None

    o, d = route.origin, route.destination
    w, journeys, car_res, bike_res = await asyncio.gather(
        safe("wetter", weather.fetch_weather(o.lat, o.lon, departure)),
        safe("bahn", transit.fetch_journeys(settings.transit_api_base, o, d, departure, arrive_by=arrive_by)),
        safe("auto", routing.fetch_route(o, d, "car")),
        safe("rad", routing.fetch_route(o, d, "bike")),
    )
    car_leg, car_line = car_res if car_res else (None, [])
    bike_leg = bike_res[0] if bike_res else None
    # Fallback: Ist kein Routing-Server erreichbar, schätzen wir (siehe routing.estimate_leg).
    if car_leg is None:
        car_leg = routing.estimate_leg(o, d, "car")
    if bike_leg is None:
        bike_leg = routing.estimate_leg(o, d, "bike")

    incidents = []
    if car_leg and car_leg.roads:
        incidents = await safe("autobahn", traffic.fetch_incidents(car_leg.roads, car_line)) or []

    return TravelData(
        weather=w,
        transit=journeys or [],
        car=car_leg,
        bike=bike_leg,
        incidents=incidents,
        errors=errors,
        fetched_at=timeutil.now(),
    )


async def recommend(
    route: Route, settings: Settings, departure: datetime | None = None, arrive_by: datetime | None = None
) -> Result:
    """Empfehlung für eine Abfahrtszeit – oder mit ``arrive_by`` für eine Ankunftszeit."""
    if arrive_by:
        # Abfahrt grob schätzen (fürs Wetter und die Demo-Daten): Luftlinie, ca. 20 km/h
        air = routing.haversine_km((route.origin.lat, route.origin.lon), (route.destination.lat, route.destination.lon))
        departure = arrive_by - timedelta(minutes=air * 1.35 / 20 * 60 + 20)
    departure = departure or timeutil.next_departure(route.departure, route.weekdays)
    if settings.demo_mode:
        data = demo_data(route, departure, settings.demo_scenario)
    else:
        data = await collect_live(route, settings, departure, arrive_by)
    fares.attach_fares(route.origin, route.destination, data.transit)  # Ticketpreise (Teil 4)
    rec = evaluate(route, settings.prefs, data, departure, arrive_by)
    return Result(route, departure, data, rec, arrive_by)


def _short(e: Exception) -> str:
    text = f"{type(e).__name__}: {e}"
    return text if len(text) < 140 else text[:137] + "…"
