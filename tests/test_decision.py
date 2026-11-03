"""Tests für Entscheidungslogik und Parser. Starten mit:  pytest -q"""
from datetime import datetime

from pendel.decision import evaluate, is_rush_hour
from pendel.demo import demo_data
from pendel.models import Mode, Preferences
from pendel.services.routing import near_line, parse_route
from pendel.services.traffic import parse_item
from pendel.services.transit import parse_journeys
from pendel.services.weather import parse_weather
from pendel.storage import default_settings
from pendel.timeutil import next_departure

ROUTE = default_settings().routes[0]  # kurze Stadtstrecke (~6 km)
LONG = default_settings().routes[1]  # längere Strecke (~15 km)
DEP = datetime(2026, 11, 4, 7, 45)  # Mittwoch, Berufsverkehr


def rec_for(scenario, route=ROUTE, prefs=None):
    data = demo_data(route, DEP, scenario)
    return evaluate(route, prefs or Preferences(), data, DEP)


def test_sunny_day_prefers_bike_on_short_route():
    assert rec_for("sonne").best == Mode.BIKE


def test_rain_rules_out_or_penalises_bike():
    r = rec_for("regen")
    assert r.best != Mode.BIKE


def test_winter_excludes_bike():
    r = rec_for("winter")
    bike = next(s for s in r.scores if s.mode == Mode.BIKE)
    assert not bike.available


def test_rail_chaos_pushes_away_from_transit():
    r = rec_for("bahnchaos", route=LONG)
    assert r.best != Mode.TRANSIT


def test_traffic_jam_penalises_car():
    calm = next(s for s in rec_for("bahnchaos", LONG).scores if s.mode == Mode.CAR)
    jam = next(s for s in rec_for("stau", LONG).scores if s.mode == Mode.CAR)
    assert jam.felt_min > calm.felt_min + 15


def test_long_route_exceeds_bike_limit():
    prefs = Preferences(bike_max_km=5)
    r = rec_for("sonne", route=LONG, prefs=prefs)
    bike = next(s for s in r.scores if s.mode == Mode.BIKE)
    assert not bike.available and "Maximum" in bike.excluded_reason


def test_felt_minutes_are_sum_of_parts():
    for s in rec_for("regen").scores:
        if s.available:
            assert abs(s.felt_min - sum(p.minutes for p in s.parts)) < 1e-9


def test_disabled_mode_is_not_scored():
    route = default_settings().routes[0]
    route.modes = ["bahn", "auto"]
    r = evaluate(route, Preferences(), demo_data(route, DEP, "sonne"), DEP)
    assert all(s.mode != Mode.BIKE for s in r.scores)


def test_rush_hour():
    assert is_rush_hour(datetime(2026, 11, 4, 7, 45))
    assert not is_rush_hour(datetime(2026, 11, 7, 7, 45))  # Samstag
    assert not is_rush_hour(datetime(2026, 11, 4, 11, 0))


def test_next_departure_skips_weekend():
    sat = datetime(2026, 11, 7, 6, 0)
    assert next_departure("07:30", [0, 1, 2, 3, 4], sat).weekday() == 0


# --- Parser mit Beispielantworten im Format der echten APIs -----------------


def test_parse_open_meteo():
    data = {
        "hourly": {
            "time": ["2026-11-04T06:00", "2026-11-04T07:00", "2026-11-04T08:00"],
            "temperature_2m": [5.1, 6.0, 7.2],
            "apparent_temperature": [2.0, 3.1, 4.4],
            "precipitation": [0, 0.4, 0],
            "precipitation_probability": [10, 55, 20],
            "weather_code": [3, 61, 3],
            "wind_speed_10m": [10, 12, 9],
            "wind_gusts_10m": [20, 25, 18],
        }
    }
    w = parse_weather(data, datetime(2026, 11, 4, 7, 45))
    assert w.at_departure.precip_mm == 0.4 and w.at_departure.code == 61


def test_parse_db_rest_journey():
    data = {
        "journeys": [
            {
                "legs": [
                    {"walking": True, "origin": {"name": "Zuhause"}, "destination": {"name": "Wilhelmsplatz"},
                     "departure": "2026-11-04T07:40:00+01:00", "arrival": "2026-11-04T07:46:00+01:00"},
                    {"line": {"name": "U2"}, "origin": {"name": "Wilhelmsplatz"}, "destination": {"name": "Stadtmitte"},
                     "departure": "2026-11-04T07:48:00+01:00", "plannedDeparture": "2026-11-04T07:47:00+01:00",
                     "arrival": "2026-11-04T08:02:00+01:00", "arrivalDelay": 120},
                ]
            }
        ]
    }
    (opt,) = parse_journeys(data)
    assert opt.lines == ["U2"] and opt.transfers == 0 and opt.delay_min == 2
    assert opt.duration_min == 22


def test_parse_osrm_and_autobahn_detection():
    data = {"code": "Ok", "routes": [{"distance": 15200, "duration": 1260,
            "geometry": {"coordinates": [[9.21, 48.80], [9.17, 48.72], [9.16, 48.69]]},
            "legs": [{"steps": [{"name": "Neue Weinsteige", "ref": "B 27"}, {"name": "", "ref": "A 8"}]}]}]}
    leg, line = parse_route(data)
    assert leg.roads == ["A8"] and round(leg.distance_km, 1) == 15.2 and line[0] == (48.80, 9.21)


def test_autobahn_item_near_route():
    line = [(48.80, 9.21), (48.69, 9.16)]
    item = {"coordinate": {"lat": "48.745", "long": "9.185"}, "title": "A8 | Stuttgart → München",
            "subtitle": "Stau", "isBlocked": "false", "description": ["Verzögerung 12 Minuten"]}
    inc = parse_item("A8", "warning", item, line)
    assert inc is not None and inc.delay_min == 12
    far = dict(item, coordinate={"lat": "49.5", "long": "10.0"})
    assert parse_item("A8", "warning", far, line) is None


def test_near_line():
    assert near_line((48.75, 9.19), [(48.80, 9.21), (48.69, 9.16)], 1.0)
