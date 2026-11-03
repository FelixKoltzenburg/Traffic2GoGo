"""Auto- und Radrouten über OSRM-Server auf Basis von OpenStreetMap.

Der Dienst routing.openstreetmap.de (FOSSGIS e.V.) bietet Profile für Auto,
Rad und Fuß. Die Fahrzeiten gelten ohne aktuellen Verkehr – deshalb
ergänzt die Entscheidungslogik Berufsverkehr und Autobahn-Meldungen.
"""
from __future__ import annotations

import math
import re

from ..models import Place, RouteLeg
from .http import get_json

BASE = "https://routing.openstreetmap.de"
PROFILES = {"car": "routed-car", "bike": "routed-bike"}
AUTOBAHN_RE = re.compile(r"\bA\s?(\d{1,3})\b")


async def fetch_route(origin: Place, dest: Place, profile: str) -> tuple[RouteLeg, list[tuple[float, float]]]:
    """Gibt die Route und ihre Linie (Liste aus (lat, lon)) zurück."""
    coords = f"{origin.lon},{origin.lat};{dest.lon},{dest.lat}"
    url = f"{BASE}/{PROFILES[profile]}/route/v1/driving/{coords}"
    data = await get_json(url, {"overview": "simplified", "geometries": "geojson", "steps": "true"}, ttl=86400)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"Keine Route gefunden ({data.get('code')})")
    return parse_route(data)


def parse_route(data: dict) -> tuple[RouteLeg, list[tuple[float, float]]]:
    r = data["routes"][0]
    roads: set[str] = set()
    for leg in r.get("legs", []):
        for step in leg.get("steps", []):
            for text in (step.get("ref", ""), step.get("name", "")):
                for m in AUTOBAHN_RE.finditer(text or ""):
                    roads.add(f"A{m.group(1)}")
    line = [(lat, lon) for lon, lat in r["geometry"]["coordinates"]]
    leg = RouteLeg(distance_km=r["distance"] / 1000, duration_min=r["duration"] / 60, roads=sorted(roads))
    return leg, line


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Luftlinie zwischen zwei Punkten auf der Erdkugel."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def near_line(point: tuple[float, float], line: list[tuple[float, float]], max_km: float = 2.0) -> bool:
    """Liegt ein Punkt nah an der Route? (Vereinfachung: Abstand zu den Stützpunkten
    plus Zwischenpunkten alle ~500 m.)"""
    for a, b in zip(line, line[1:]):
        seg = haversine_km(a, b)
        steps = max(1, int(seg / 0.5))
        for i in range(steps + 1):
            t = i / steps
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if haversine_km(point, p) <= max_km:
                return True
    return len(line) == 1 and haversine_km(point, line[0]) <= max_km
