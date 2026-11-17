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
# Ersatz-Server, falls routing.openstreetmap.de nicht antwortet (nur Auto)
FALLBACK_CAR = "https://router.project-osrm.org/route/v1/driving"
AUTOBAHN_RE = re.compile(r"\bA\s?(\d{1,3})\b")


async def fetch_route(origin: Place, dest: Place, profile: str) -> tuple[RouteLeg, list[tuple[float, float]]]:
    """Gibt die Route und ihre Linie (Liste aus (lat, lon)) zurück.

    Erst routing.openstreetmap.de, fürs Auto notfalls der OSRM-Demoserver.
    Klappt beides nicht, wirft die Funktion einen Fehler – die App rechnet dann
    mit ``estimate_leg`` weiter.
    """
    coords = f"{origin.lon},{origin.lat};{dest.lon},{dest.lat}"
    params = {"overview": "simplified", "geometries": "geojson", "steps": "true"}
    urls = [f"{BASE}/{PROFILES[profile]}/route/v1/driving/{coords}"]
    if profile == "car":
        urls.append(f"{FALLBACK_CAR}/{coords}")
    error: Exception | None = None
    for url in urls:
        try:
            data = await get_json(url, params, ttl=86400)
        except Exception as e:  # noqa: BLE001 – nächsten Server probieren
            error = e
            continue
        if data.get("code") == "Ok" and data.get("routes"):
            return parse_route(data)
        error = RuntimeError(f"Keine Route gefunden ({data.get('code')})")
    raise error or RuntimeError("Keine Route gefunden")


def estimate_leg(origin: Place, dest: Place, profile: str) -> RouteLeg:
    """Notfall-Schätzung ohne Routing-Server – bewusst realistisch statt pessimistisch.

    Auto: die ersten 6 km Stadtverkehr (~30 km/h), der Rest über Bundesstraße
    oder Autobahn (~85 km/h), dazu 3 min fürs Losfahren und Abstellen.
    Rad: Umwegfaktor 1,2 und 15 km/h.
    Beispiel Bad Cannstatt → Eislingen (38 km Luftlinie): ca. 45 min statt 83.
    """
    air = haversine_km((origin.lat, origin.lon), (dest.lat, dest.lon))
    if profile == "car":
        km = air * 1.25
        city = min(km, 6.0)
        minutes = city / 30 * 60 + max(km - city, 0) / 85 * 60 + 3
        return RouteLeg(km, minutes, estimated=True)
    km = air * 1.2
    return RouteLeg(km, km / 15 * 60, estimated=True)


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
