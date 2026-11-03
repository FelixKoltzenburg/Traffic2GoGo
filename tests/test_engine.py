"""Testet den kompletten Live-Ablauf mit nachgebauten API-Antworten
(ohne Internet). So sieht man, ob alle Teile zusammenspielen."""
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
    if "/journeys" in url:
        return {"journeys": [{"legs": [
            {"line": {"name": "U2"}, "origin": {"name": "A"}, "destination": {"name": "B"},
             "departure": "2026-11-04T07:50:00+01:00", "plannedDeparture": "2026-11-04T07:50:00+01:00",
             "arrival": "2026-11-04T08:12:00+01:00", "arrivalDelay": 0}]}]}
    if "A8/services/warning" in url:
        return {"warning": [{"coordinate": {"lat": "48.74", "long": "9.17"}, "title": "A8 | Stuttgart → Karlsruhe",
                             "subtitle": "Stau", "isBlocked": "false", "delayTimeValue": "20", "description": []}]}
    if "/services/" in url:
        return {}
    raise AssertionError(url)


def test_live_pipeline(monkeypatch):
    async def fake_get_json(url, params=None, ttl=300):
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
