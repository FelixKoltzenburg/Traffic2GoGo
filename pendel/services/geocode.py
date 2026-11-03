"""Adresssuche über Photon (komoot), basiert auf OpenStreetMap.

Doku: https://photon.komoot.io
"""
from __future__ import annotations

from ..models import Place
from .http import get_json

URL = "https://photon.komoot.io/api/"


async def search(query: str, limit: int = 6) -> list[Place]:
    if len(query.strip()) < 3:
        return []
    # Ergebnisse rund um Stuttgart bevorzugen
    data = await get_json(URL, {"q": query, "limit": limit, "lang": "de", "lat": 48.78, "lon": 9.18}, ttl=86400)
    return [parse_feature(f) for f in data.get("features", [])]


def parse_feature(f: dict) -> Place:
    p = f.get("properties", {})
    lon, lat = f["geometry"]["coordinates"]
    street = " ".join(x for x in (p.get("street"), p.get("housenumber")) if x)
    city = " ".join(x for x in (p.get("postcode"), p.get("city") or p.get("district")) if x)
    parts = [p.get("name"), street, city]
    label = ", ".join(dict.fromkeys(x for x in parts if x))  # Dopplungen entfernen
    return Place(name=label or "Unbenannter Ort", lat=float(lat), lon=float(lon))
