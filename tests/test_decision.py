"""Tests für Entscheidungslogik und Parser. Starten mit:  pytest -q"""
from datetime import datetime, timedelta

from pendel.decision import evaluate, is_rush_hour
from pendel.demo import demo_data
from pendel.models import Mode, Preferences
from pendel.services.routing import near_line, parse_route
from pendel.services.traffic import parse_item
from pendel.services.transit import decode_polyline, parse_plan
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


def test_rain_rules_out_bike():
    r = rec_for("regen")
    bike = next(s for s in r.scores if s.mode == Mode.BIKE)
    assert not bike.available and "Regen" in bike.excluded_reason


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
    assert jam.total_min > calm.total_min + 15


def test_long_route_exceeds_bike_limit():
    prefs = Preferences(bike_max_km=5)
    r = rec_for("sonne", route=LONG, prefs=prefs)
    bike = next(s for s in r.scores if s.mode == Mode.BIKE)
    assert not bike.available and "Maximum" in bike.excluded_reason


def test_minutes_are_sum_of_parts():
    for s in rec_for("regen").scores:
        if s.available:
            assert abs(s.total_min - sum(p.minutes for p in s.parts)) < 1e-9


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


def test_parse_transitous_plan():
    """Antwort im Format der MOTIS-API (Transitous), gekürzt auf die genutzten Felder."""
    data = {
        "itineraries": [
            {
                "duration": 1560, "startTime": "2026-11-04T06:40:00Z", "endTime": "2026-11-04T07:06:00Z",
                "transfers": 0,
                "legs": [
                    {"mode": "WALK", "from": {"name": "START", "lat": 48.80, "lon": 9.21},
                     "to": {"name": "Wilhelmsplatz", "lat": 48.80, "lon": 9.22},
                     "startTime": "2026-11-04T06:40:00Z", "endTime": "2026-11-04T06:46:00Z",
                     "scheduledStartTime": "2026-11-04T06:40:00Z", "scheduledEndTime": "2026-11-04T06:46:00Z",
                     "realTime": False, "scheduled": True, "duration": 360, "distance": 412.5,
                     "legGeometry": {"points": "_p~iF~ps|U_ulLnnqC", "precision": 5, "length": 2},
                     "steps": [{"relativeDirection": "DEPART", "streetName": "Marktstraße", "distance": 120},
                               {"relativeDirection": "LEFT", "streetName": "", "distance": 2},
                               {"relativeDirection": "RIGHT", "streetName": "König-Karl-Straße", "distance": 290}]},
                    {"mode": "SUBWAY", "from": {"name": "Wilhelmsplatz", "lat": 48.80, "lon": 9.22, "track": "2"},
                     "to": {"name": "Stadtmitte", "lat": 48.77, "lon": 9.17, "scheduledTrack": "1"},
                     "startTime": "2026-11-04T06:48:00Z", "endTime": "2026-11-04T07:02:00Z",
                     "scheduledStartTime": "2026-11-04T06:47:00Z", "scheduledEndTime": "2026-11-04T07:00:00Z",
                     "realTime": True, "scheduled": True, "duration": 840, "displayName": "U2",
                     "headsign": "Hölderlinplatz", "routeColor": "e3000f", "routeTextColor": "FFFFFF",
                     "intermediateStops": [{"name": "A", "lat": 0, "lon": 0}, {"name": "B", "lat": 0, "lon": 0}],
                     "legGeometry": {"points": "", "precision": 6, "length": 0}},
                    {"mode": "WALK", "from": {"name": "Stadtmitte", "lat": 48.77, "lon": 9.17},
                     "to": {"name": "END", "lat": 48.77, "lon": 9.16},
                     "startTime": "2026-11-04T07:02:00Z", "endTime": "2026-11-04T07:06:00Z",
                     "scheduledStartTime": "2026-11-04T07:00:00Z", "scheduledEndTime": "2026-11-04T07:04:00Z",
                     "realTime": False, "scheduled": True, "duration": 240, "distance": 250,
                     "legGeometry": {"points": "", "precision": 6, "length": 0}},
                ],
            },
            {   # reiner Fußweg ohne Bahn → wird nicht als Bahnverbindung gezählt
                "duration": 4000, "startTime": "2026-11-04T06:40:00Z", "endTime": "2026-11-04T07:46:00Z",
                "transfers": 0,
                "legs": [{"mode": "WALK", "from": {"name": "S", "lat": 0, "lon": 0}, "to": {"name": "E", "lat": 0, "lon": 0},
                          "startTime": "2026-11-04T06:40:00Z", "endTime": "2026-11-04T07:46:00Z",
                          "scheduledStartTime": "2026-11-04T06:40:00Z", "scheduledEndTime": "2026-11-04T07:46:00Z",
                          "realTime": False, "scheduled": True, "duration": 4000,
                          "legGeometry": {"points": "", "precision": 6, "length": 0}}],
            },
        ]
    }
    (opt,) = parse_plan(data)
    assert opt.lines == ["U2"] and opt.transfers == 0
    assert opt.departure == datetime(2026, 11, 4, 7, 40)  # UTC → deutsche Zeit (Winterzeit +1 h)
    assert opt.delay_min == 2 and opt.duration_min == 26
    walk, ride, _ = opt.legs
    assert walk.walking and walk.distance_m == 412.5
    assert walk.steps == ["Losgehen auf Marktstraße (120 m)", "Rechts abbiegen auf König-Karl-Straße (290 m)"]
    assert walk.path == [(38.5, -120.2), (40.7, -120.95)]  # Beispiel aus der Google-Polyline-Doku
    assert ride.kind == "U" and ride.color == "#e3000f" and ride.track_from == "2" and ride.track_to == "1"
    assert ride.headsign == "Hölderlinplatz" and ride.stops_between == 2
    assert opt.planned_departure == datetime(2026, 11, 4, 7, 39)  # erster Zug 1 min verspätet


def test_decode_polyline_precision():
    assert decode_polyline({"points": "_p~iF~ps|U", "precision": 5}) == [(38.5, -120.2)]
    assert decode_polyline({"points": "", "precision": 6}) == []

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


# --- Ankunft-Modus (Teil 2: Verbindungssuche wie bei der DB) ---------------


def test_arrive_by_only_counts_trains_arriving_in_time():
    arrive = datetime(2026, 11, 4, 8, 30)
    data = demo_data(ROUTE, arrive - timedelta(minutes=50), "sonne")
    r = evaluate(ROUTE, Preferences(), data, arrive - timedelta(minutes=50), arrive_by=arrive)
    bahn = next(s for s in r.scores if s.mode == Mode.TRANSIT)
    assert bahn.available
    ankunft = bahn.notes[0].split("an")[0]  # "07:54 ab, 08:24 an · ..."
    assert "ab" in ankunft
    late = [o for o in data.transit if o.arrival > arrive]
    assert late, "Testdaten sollten auch zu späte Züge enthalten"
    for o in late:
        assert f"{o.departure:%H:%M} ab" not in bahn.notes[0]


def test_arrive_by_tells_when_to_leave_by_car_and_bike():
    arrive = datetime(2026, 11, 4, 8, 30)
    data = demo_data(ROUTE, arrive - timedelta(minutes=50), "sonne")
    r = evaluate(ROUTE, Preferences(), data, arrive - timedelta(minutes=50), arrive_by=arrive)
    for mode in (Mode.CAR, Mode.BIKE):
        s = next(x for x in r.scores if x.mode == mode)
        leave = datetime.combine(arrive.date(), datetime.strptime(s.notes[0][-5:], "%H:%M").time())
        assert s.notes[0].startswith("Losfahren um")
        assert abs((arrive - leave).total_seconds() / 60 - s.travel_min) < 1.01


def test_arrive_by_without_any_train_in_time():
    arrive = datetime(2026, 11, 4, 6, 0)
    data = demo_data(ROUTE, datetime(2026, 11, 4, 7, 45), "sonne")  # alle Züge nach 7:45
    r = evaluate(ROUTE, Preferences(), data, arrive, arrive_by=arrive)
    bahn = next(s for s in r.scores if s.mode == Mode.TRANSIT)
    assert not bahn.available and "06:00" in bahn.excluded_reason


# --- Echte Minuten + Abwägung Zeit/Geld nur in der Empfehlung --------------


def test_minutes_contain_no_money():
    """Die Minuten sind reine Reisezeit – kein Teil enthält Euro."""
    for scen in ("sonne", "stau", "bahnchaos"):
        for s in rec_for(scen, LONG).scores:
            assert all("€" not in p.label for p in s.parts)


def _score(mode, minutes, cost):
    from pendel.models import ModeScore, ScorePart

    s = ModeScore(mode, available=True, total_min=minutes, travel_min=minutes, cost_eur=cost)
    s.parts = [ScorePart("Fahrzeit", minutes)]
    return s


def test_tradeoff_slower_but_much_cheaper_wins(monkeypatch):
    import pendel.decision as d

    fast_car = _score(Mode.CAR, 20, 6.00)  # 3 min schneller, aber 6 € teurer
    bike = _score(Mode.BIKE, 23, 0.00)
    monkeypatch.setattr(d, "score_car", lambda *a, **k: fast_car)
    monkeypatch.setattr(d, "score_bike", lambda *a, **k: bike)
    monkeypatch.setattr(d, "score_transit", lambda *a, **k: _score(Mode.TRANSIT, 60, 0))
    r = d.evaluate(ROUTE, Preferences(value_of_time_eur_h=12), demo_data(ROUTE, DEP, "sonne"), DEP)
    assert r.best == Mode.BIKE
    assert r.reasons[0] == "3 min langsamer als Auto, spart aber 6,00 €"
    assert bike.total_min == 23 and fast_car.total_min == 20  # angezeigte Minuten bleiben echt
    # wer seine Zeit sehr hoch bewertet, bekommt das schnellere Auto
    r2 = d.evaluate(ROUTE, Preferences(value_of_time_eur_h=200), demo_data(ROUTE, DEP, "sonne"), DEP)
    assert r2.best == Mode.CAR and r2.reasons[0].startswith("3 min schneller als Rad – kostet 6,00 € mehr")
