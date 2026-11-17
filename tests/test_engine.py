"""Testet den kompletten Live-Ablauf mit nachgebauten API-Antworten
(ohne Internet). So sieht man, ob alle Teile zusammenspielen."""
from __future__ import annotations

import asyncio
from datetime import datetime

from pendel import engine
from pendel.models import Mode, Settings
from pendel.services import http
from pendel.storage import default_settings

DEP = datetime(2026, 11, 4, 7, 45)


def fake_responses(url: str, params: dict | None):
    if "open-meteo" in url:
        times = [f"2026-11-04T{h:02d}:00" for h in range(0, 24)]
        n = len(times)
        return {"hourly": {"time": times, "temperature_2m": [11] * n, "apparent_temperature": [10] * n,
                           "precipitation": [0] * n, "precipitation_probability": [5] * n, "weather_code": [1] * n,
                           "wind_speed_10m": [8] * n, "wind_gusts_10m": [15] * n}}
    if "routed-car" in url:
        return {"code": "Ok", "routes": [{"distance": 17600, "duration": 1500,
                "geometry": {"coordinates": [[9.21, 48.80], [9.17, 48.73], [9.16, 48.69]]},
                "legs": [{"steps": [{"name": "", "ref": "A 8"}]}]}]}
    if "routed-bike" in url:
        return {"code": "Ok", "routes": [{"distance": 6100, "duration": 1380,
                "geometry": {"coordinates": [[9.21, 48.80], [9.17, 48.77]]}, "legs": []}]}
    if "/plan" in url:
        return {"itineraries": [{"duration": 1320, "startTime": "2026-11-04T06:50:00Z", "endTime": "2026-11-04T07:12:00Z",
                "transfers": 0, "legs": [
                    {"mode": "SUBWAY", "displayName": "U2", "from": {"name": "A", "lat": 48.8, "lon": 9.2},
                     "to": {"name": "B", "lat": 48.77, "lon": 9.17},
                     "startTime": "2026-11-04T06:50:00Z", "endTime": "2026-11-04T07:12:00Z",
                     "scheduledStartTime": "2026-11-04T06:50:00Z", "scheduledEndTime": "2026-11-04T07:12:00Z",
                     "realTime": True, "scheduled": True, "duration": 1320,
                     "legGeometry": {"points": "", "precision": 6, "length": 0}}]}]}
    if "A8/services/warning" in url:
        return {"warning": [{"coordinate": {"lat": "48.74", "long": "9.17"}, "title": "A8 | Stuttgart → Karlsruhe",
                             "subtitle": "Stau", "isBlocked": "false", "delayTimeValue": "20", "description": []}]}
    if "/services/" in url:
        return {}
    raise AssertionError(url)


def test_live_pipeline(monkeypatch):
    async def fake_get_json(url, params=None, ttl=300, stale_ok=0):
        return fake_responses(url, params)

    monkeypatch.setattr(http, "get_json", fake_get_json)
    for mod in ("weather", "routing", "traffic", "transit"):
        monkeypatch.setattr(f"pendel.services.{mod}.get_json", fake_get_json)

    s: Settings = default_settings()
    s.demo_mode = False
    route = s.routes[1]
    result = asyncio.run(engine.recommend(route, s, DEP))
    assert not result.data.errors
    assert result.data.car.roads == ["A8"]
    assert len(result.data.incidents) == 1 and result.data.incidents[0].delay_min == 20
    car = next(x for x in result.rec.scores if x.mode == Mode.CAR)
    assert any("A8" in p.label and p.minutes == 20 for p in car.parts)  # Stau fließt in die Bewertung ein
    assert result.rec.best == Mode.BIKE  # sonnig, 6 km → Rad


def test_routing_down_uses_estimate(monkeypatch):
    async def failing(url, params=None, ttl=300):
        if "routing" in url:
            raise RuntimeError("down")
        return fake_responses(url, params)

    for mod in ("weather", "routing", "traffic", "transit"):
        monkeypatch.setattr(f"pendel.services.{mod}.get_json", failing)
    s = default_settings()
    s.demo_mode = False
    result = asyncio.run(engine.recommend(s.routes[0], s, DEP))
    assert result.data.car.estimated and "auto" in result.data.errors
    assert result.rec.best is not None


def test_arrival_is_sent_to_bahn_api(monkeypatch):
    seen = {}

    async def fake(url, params=None, ttl=300):
        if "/plan" in url:
            seen.update(params)
        return fake_responses(url, params)

    for mod in ("weather", "routing", "traffic", "transit"):
        monkeypatch.setattr(f"pendel.services.{mod}.get_json", fake)
    s = default_settings()
    s.demo_mode = False
    arrive = datetime(2026, 11, 4, 8, 30)
    result = asyncio.run(engine.recommend(s.routes[0], s, arrive_by=arrive))
    assert seen["time"].startswith("2026-11-04T08:30") and seen["arriveBy"] == "true"
    assert result.arrive_by == arrive


def test_transitous_falls_back_to_older_api_version(monkeypatch):
    """Kennt der Server /api/v6 noch nicht, wird automatisch /api/v5 usw. probiert."""
    import httpx

    from pendel.services import transit

    calls = []

    async def fake(url, params=None, ttl=300):
        calls.append(url)
        if "/api/v6/" in url:
            req = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))
        return fake_responses(url, params)

    monkeypatch.setattr("pendel.services.transit.get_json", fake)
    transit._working_version.clear()
    s = default_settings()
    route = s.routes[0]
    opts = asyncio.run(transit.fetch_journeys("https://api.transitous.org", route.origin, route.destination, DEP))
    assert len(opts) == 1 and any("/api/v5/plan" in c for c in calls)
    calls.clear()
    asyncio.run(transit.fetch_journeys("https://api.transitous.org", route.origin, route.destination, DEP))
    assert calls == ["https://api.transitous.org/api/v5/plan"]  # gemerkt, kein zweiter Fehlversuch


def test_old_db_rest_settings_are_migrated(tmp_path, monkeypatch):
    import json
    from dataclasses import asdict

    from pendel import storage

    monkeypatch.setattr(storage, "SETTINGS_FILE", tmp_path / "settings.json")
    raw = asdict(default_settings())
    raw.update(demo_mode=True, transit_api_base="https://v6.db.transport.rest", user_name="Felix", ntfy_topic="x")
    (tmp_path / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    s = storage.load_settings()
    assert s.transit_api_base == "https://api.transitous.org" and s.demo_mode is False
