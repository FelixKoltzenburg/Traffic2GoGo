"""Bahn-Verbindungen über die offene REST-API db.transport.rest.

Doku: https://v6.db.transport.rest/getting-started.html
Start und Ziel werden als Adresse mit Koordinaten übergeben – so braucht man
keine Haltestellen-IDs und Fußwege werden automatisch eingerechnet.
Hinweis: Der Dienst ist ein Community-Projekt ohne Garantie; die Basis-URL
lässt sich in den Einstellungen ändern.
"""
from __future__ import annotations

from datetime import datetime

from ..models import Place, TransitLeg, TransitOption
from ..timeutil import aware, to_local
from .http import get_json


async def fetch_journeys(base: str, origin: Place, dest: Place, departure: datetime, results: int = 4) -> list[TransitOption]:
    params = {
        "from.latitude": origin.lat,
        "from.longitude": origin.lon,
        "from.address": origin.name,
        "to.latitude": dest.lat,
        "to.longitude": dest.lon,
        "to.address": dest.name,
        "departure": aware(departure).isoformat(),
        "results": results,
        "stopovers": "false",
        "remarks": "false",
        "language": "de",
    }
    data = await get_json(f"{base.rstrip('/')}/journeys", params, ttl=120)
    return parse_journeys(data)


def parse_journeys(data: dict) -> list[TransitOption]:
    options: list[TransitOption] = []
    for j in data.get("journeys", []):
        legs: list[TransitLeg] = []
        for leg in j.get("legs", []):
            dep = _time(leg.get("departure") or leg.get("plannedDeparture"))
            arr = _time(leg.get("arrival") or leg.get("plannedArrival"))
            if dep is None or arr is None:
                continue
            walking = bool(leg.get("walking"))
            line = "Fußweg" if walking else ((leg.get("line") or {}).get("name") or "?")
            legs.append(
                TransitLeg(
                    line=line,
                    origin=(leg.get("origin") or {}).get("name", ""),
                    destination=(leg.get("destination") or {}).get("name", ""),
                    departure=dep,
                    arrival=arr,
                    delay_min=round((leg.get("arrivalDelay") or 0) / 60),
                    walking=walking,
                    cancelled=bool(leg.get("cancelled")),
                )
            )
        if not legs:
            continue
        first, last = j["legs"][0], j["legs"][-1]
        options.append(
            TransitOption(
                departure=legs[0].departure,
                arrival=legs[-1].arrival,
                planned_departure=_time(first.get("plannedDeparture")) or legs[0].departure,
                legs=legs,
                delay_min=round((last.get("arrivalDelay") or 0) / 60),
                cancelled=any(leg.cancelled for leg in legs),
            )
        )
    return options


def _time(s: str | None) -> datetime | None:
    if not s:
        return None
    return to_local(datetime.fromisoformat(s.replace("Z", "+00:00")))
