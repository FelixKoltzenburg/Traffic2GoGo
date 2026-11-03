"""Verkehrsmeldungen der Autobahn GmbH des Bundes.

Doku (inoffiziell, bund.dev): https://autobahn.api.bund.dev
Pro Autobahn gibt es Listen für Warnungen (Staus), Sperrungen und Baustellen.
Wir behalten nur Meldungen, die nahe an der eigenen Autoroute liegen.
"""
from __future__ import annotations

import asyncio
import re

from ..models import Incident
from .http import get_json
from .routing import near_line

BASE = "https://verkehr.autobahn.de/o/autobahn"
KINDS = {"warning": "warning", "closure": "closure", "roadworks": "roadworks"}
DELAY_RE = re.compile(r"(\d+)\s*Minuten")


async def fetch_incidents(roads: list[str], route_line: list[tuple[float, float]]) -> list[Incident]:
    tasks = [_fetch_one(road, kind) for road in roads for kind in KINDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    incidents: list[Incident] = []
    for res in results:
        if isinstance(res, Exception):
            continue  # eine fehlende Liste ist kein Beinbruch
        for road, kind, item in res:
            inc = parse_item(road, kind, item, route_line)
            if inc:
                incidents.append(inc)
    # Sperrungen zuerst, dann nach Verzögerung
    incidents.sort(key=lambda i: (not i.blocked, -(i.delay_min or 0)))
    return incidents


async def _fetch_one(road: str, kind: str):
    data = await get_json(f"{BASE}/{road}/services/{kind}", ttl=300)
    return [(road, kind, item) for item in data.get(KINDS[kind], [])]


def parse_item(road: str, kind: str, item: dict, route_line: list[tuple[float, float]]) -> Incident | None:
    coord = item.get("coordinate") or {}
    try:
        point = (float(coord["lat"]), float(coord["long"]))
    except (KeyError, TypeError, ValueError):
        return None
    if route_line and not near_line(point, route_line, max_km=1.5):
        return None
    if kind == "roadworks" and item.get("future"):
        return None  # Baustellen, die erst später beginnen, ignorieren
    delay = item.get("delayTimeValue")
    if delay is None:
        m = DELAY_RE.search(" ".join(item.get("description") or []))
        delay = float(m.group(1)) if m else None
    return Incident(
        road=road,
        kind=kind,
        title=(item.get("title") or "").strip(),
        subtitle=(item.get("subtitle") or "").strip(),
        delay_min=float(delay) if delay is not None else None,
        blocked=str(item.get("isBlocked", "false")).lower() == "true",
    )
