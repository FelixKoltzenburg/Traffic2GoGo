"""Tests für Teil 4: realistische Fahrzeiten und Ticketpreise."""
from __future__ import annotations

import asyncio
from datetime import date, datetime

from pendel.decision import evaluate
from pendel.demo import demo_data
from pendel.models import Mode, Place, Preferences
from pendel.services import fares, routing
from pendel.storage import default_settings

BAD_CANNSTATT = Place("Bad Cannstatt", 48.8047, 9.2149)
DHBW = Place("DHBW Stuttgart", 48.7757, 9.1718)
LEINFELDEN = Place("Leinfelden-Echterdingen", 48.6925, 9.1640)
EISLINGEN = Place("Eislingen (Fils)", 48.6935, 9.7048)
ULM = Place("Ulm", 48.3984, 9.9916)
DEP = datetime(2026, 11, 18, 7, 45)


# --- Fahrzeiten ------------------------------------------------------------


def test_eislingen_estimate_is_realistic():
    """Früher: 83 min. Real (B10/B29): gut 40 Minuten."""
    car = routing.estimate_leg(BAD_CANNSTATT, EISLINGEN, "car")
    assert 35 <= car.duration_min <= 55 and car.estimated


def test_short_city_trip_estimate():
    car = routing.estimate_leg(BAD_CANNSTATT, DHBW, "car")
    bike = routing.estimate_leg(BAD_CANNSTATT, DHBW, "bike")
    assert 10 <= car.duration_min <= 20 and 15 <= bike.duration_min <= 30


def test_car_routing_falls_back_to_second_server(monkeypatch):
    calls = []

    async def fake(url, params=None, ttl=300):
        calls.append(url)
        if "routing.openstreetmap.de" in url:
            raise RuntimeError("Server down")
        return {"code": "Ok", "routes": [{"distance": 41000, "duration": 2460,
                "geometry": {"coordinates": [[9.21, 48.80], [9.70, 48.69]]}, "legs": []}]}

    monkeypatch.setattr(routing, "get_json", fake)
    leg, _ = asyncio.run(routing.fetch_route(BAD_CANNSTATT, EISLINGEN, "car"))
    assert leg.duration_min == 41 and "router.project-osrm.org" in calls[-1]


# --- Ticketpreise ----------------------------------------------------------


def test_vvs_zone_prices():
    assert fares.estimate_fare(BAD_CANNSTATT, DHBW).amount == 3.70  # innerhalb Stuttgart: 1 Zone
    assert fares.estimate_fare(BAD_CANNSTATT, LEINFELDEN).amount == 4.90  # Filder: 2 Zonen
    assert fares.vvs_zones(BAD_CANNSTATT, EISLINGEN) >= 5  # weit draußen im Kreis Göppingen
    assert fares.estimate_fare(DHBW, BAD_CANNSTATT).amount == fares.estimate_fare(BAD_CANNSTATT, DHBW).amount


def test_outside_vvs_is_marked_as_rough_estimate():
    f = fares.estimate_fare(BAD_CANNSTATT, ULM)
    assert f.amount >= fares.VVS_EINZEL[7] and "außerhalb VVS" in f.label


def test_deutschlandticket_price_by_date():
    assert fares.deutschlandticket_price(date(2026, 11, 18)) == 63.00
    assert fares.deutschlandticket_price(date(2027, 1, 1)) == 66.80


def _bahn(dticket: bool):
    route = default_settings().routes[0]
    data = demo_data(route, DEP, "sonne")
    fares.attach_fares(route.origin, route.destination, data.transit)
    rec = evaluate(route, Preferences(has_deutschlandticket=dticket), data, DEP)
    return next(s for s in rec.scores if s.mode == Mode.TRANSIT)


def test_deutschlandticket_switch_makes_trips_free():
    ohne, mit = _bahn(False), _bahn(True)
    assert ohne.cost_eur == 3.70 and mit.cost_eur == 0.0
    assert ohne.total_min == mit.total_min  # der Preis ändert nie die angezeigten Minuten
    assert any("Ticket 3,70 €" in n for n in ohne.notes)
    assert any("Deutschlandticket" in n for n in mit.notes)


def test_brightsky_ersatz_wetter():
    from datetime import datetime

    from pendel.services.weather import parse_brightsky

    data = {"weather": [
        {"timestamp": "2026-11-18T07:00:00+01:00", "temperature": 3.0, "precipitation": 0.0,
         "precipitation_probability": 10, "wind_speed": 12.0, "wind_gust_speed": 25.0,
         "condition": "dry", "icon": "cloudy"},
        {"timestamp": "2026-11-18T08:00:00+01:00", "temperature": 4.0, "precipitation": 1.5,
         "precipitation_probability": 80, "wind_speed": 15.0, "wind_gust_speed": 30.0,
         "condition": "rain", "icon": "rain"},
    ]}
    w = parse_brightsky(data, datetime(2026, 11, 18, 8, 15))
    assert w.at_departure.time == datetime(2026, 11, 18, 8, 0)
    assert w.at_departure.code == 63 and w.at_departure.precip_mm == 1.5
    assert w.at_departure.apparent_c < 4.0  # Windchill
