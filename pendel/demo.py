"""Demo-Daten: realistische Beispielwerte, damit die App auch ohne Internet
(oder wenn eine API gerade streikt) ausprobiert werden kann.

Über die Szenarien lässt sich die Entscheidungslogik gezielt testen:
Bei „Regen“ sollte das Rad verlieren, bei „Bahnchaos“ die Bahn usw.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from .models import HourWeather, Incident, Route, RouteLeg, TransitLeg, TransitOption, TravelData, WeatherInfo
from .services.routing import haversine_km

SCENARIOS = {
    "auto": "Zufällig (wechselt täglich)",
    "sonne": "Sonnig & mild",
    "regen": "Regentag",
    "stau": "Stau & Unfall",
    "bahnchaos": "Bahnchaos",
    "winter": "Glätte & Frost",
}

# (Temperatur, Regen mm/h, Regenwahrscheinlichkeit, Wind, Böen, Wettercode)
WEATHER = {
    "sonne": (14, 0.0, 5, 8, 18, 1),
    "regen": (9, 1.6, 85, 18, 38, 63),
    "stau": (11, 0.0, 15, 12, 25, 2),
    "bahnchaos": (12, 0.0, 10, 10, 22, 2),
    "winter": (-2, 0.3, 60, 9, 20, 71),
}


def demo_data(route: Route, departure: datetime, scenario: str) -> TravelData:
    seed = f"{departure.date()}-{route.id}-{scenario}"
    rnd = random.Random(seed)
    if scenario == "auto" or scenario not in WEATHER:
        scenario = rnd.choice(list(WEATHER))

    air = haversine_km((route.origin.lat, route.origin.lon), (route.destination.lat, route.destination.lon))
    car_km = max(0.8, air * 1.35)
    bike_km = max(0.6, air * 1.25)
    car_speed = 24 if car_km < 8 else 40  # km/h ohne Verkehr, Stadt vs. Umland
    car = RouteLeg(car_km, car_km / car_speed * 60 + 2, roads=["A8"] if car_km > 8 else [])
    bike = RouteLeg(bike_km, bike_km / 16 * 60)

    return TravelData(
        weather=_weather(departure, scenario, rnd),
        transit=_transit(route, departure, air, scenario, rnd),
        car=car,
        bike=bike,
        incidents=_incidents(car_km, scenario),
        demo=True,
    )


def _weather(dep: datetime, scenario: str, rnd: random.Random) -> WeatherInfo:
    t, rain, prob, wind, gust, code = WEATHER[scenario]
    start = dep.replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    hours: list[HourWeather] = []
    for i in range(14):
        ti = start + timedelta(hours=i)
        warm = 4 * math.sin((ti.hour - 9) / 24 * 2 * math.pi)  # Tagesgang der Temperatur
        r = max(0.0, rain * (0.6 + 0.8 * math.sin(i / 2.5)) + rnd.uniform(-0.2, 0.2)) if rain else 0.0
        hours.append(
            HourWeather(
                time=ti,
                temp_c=round(t + warm + rnd.uniform(-0.5, 0.5), 1),
                apparent_c=round(t + warm - wind / 8, 1),
                precip_mm=round(r if i != 2 else rain, 1),
                precip_prob=int(min(100, max(0, prob + rnd.randint(-10, 10)))),
                wind_kmh=round(wind + rnd.uniform(-3, 3), 0),
                gusts_kmh=round(gust + rnd.uniform(-5, 5), 0),
                code=code if (rain == 0 or r > 0.1 or i == 2) else 3,
            )
        )
    return WeatherInfo(at_departure=hours[2], hours=hours)


def _transit(route: Route, dep: datetime, air_km: float, scenario: str, rnd: random.Random) -> list[TransitOption]:
    o, d = (route.origin.lat, route.origin.lon), (route.destination.lat, route.destination.lon)
    # Haltestellen liegen ein Stück vom Start/Ziel entfernt auf der direkten Linie
    stop_a = _between(o, d, 0.08)
    stop_b = _between(o, d, 0.55)
    stop_c = _between(o, d, 0.93)
    lines = [(("U2", "U", "#e3000f", "Hölderlinplatz"), ("S1", "S", "#4fa832", "Herrenberg")),
             (("U1", "U", "#e3000f", "Vaihingen"),),
             (("S1", "S", "#4fa832", "Kirchheim (T)"), ("Bus 42", "B", "#a6338b", "Erwin-Schoettle-Platz")),
             (("U2", "U", "#e3000f", "Botnang"),)]
    ride = air_km / 22 * 60 + 4
    options: list[TransitOption] = []
    first = dep + timedelta(minutes=rnd.randint(2, 7))
    for k in range(4):
        planned = first + timedelta(minutes=10 * k)
        chosen = lines[k % len(lines)]
        delay = rnd.choice([0, 0, 1, 2, 4])
        cancelled = False
        if scenario == "bahnchaos":
            delay = rnd.choice([12, 18, 25])
            cancelled = k in (0, 2)
        legs: list[TransitLeg] = []
        t = planned
        legs.append(TransitLeg(
            "Fußweg", route.origin.name, "Haltestelle Wilhelmsplatz", t, t + timedelta(minutes=5), walking=True,
            distance_m=380, path=[o, stop_a],
            steps=["Losgehen auf Marktstraße (120 m)", "Rechts abbiegen auf König-Karl-Straße (210 m)",
                   "Links abbiegen auf Wilhelmsplatz (50 m)"],
        ))
        t += timedelta(minutes=5)
        part = ride / len(chosen)
        stops = [stop_a, stop_b, stop_c] if len(chosen) == 2 else [stop_a, stop_c]
        names = ["Wilhelmsplatz", "Hauptbahnhof", "Stadtmitte"] if len(chosen) == 2 else ["Wilhelmsplatz", "Stadtmitte"]
        for j, (ln, kind, color, head) in enumerate(chosen):
            if j:
                legs.append(TransitLeg("Fußweg", names[j], names[j], t, t + timedelta(minutes=4), walking=True,
                                       distance_m=150, steps=["Zum Gleis 101 (Treppe nehmen)"], path=[stops[j]]))
                t += timedelta(minutes=4)
            legs.append(TransitLeg(
                ln, names[j], names[j + 1], t + timedelta(minutes=delay if j == 0 else 0),
                t + timedelta(minutes=part + (delay if j == 0 else 0)), delay_min=delay, cancelled=cancelled,
                kind=kind, headsign=head, planned_departure=t, track_from=str(rnd.choice([1, 2, 101, 102])),
                track_to=str(rnd.choice([1, 2])), stops_between=max(1, int(part / 2.5)),
                path=[stops[j], stops[j + 1]], color=color, text_color="#ffffff",
            ))
            t += timedelta(minutes=part + (delay if j == 0 else 0))  # Verspätung wirkt ab dem ersten Zug
        legs.append(TransitLeg("Fußweg", "Stadtmitte", route.destination.name, t, t + timedelta(minutes=4), walking=True,
                               distance_m=290, path=[stop_c, d],
                               steps=["Ausgang Rotebühlplatz (Treppe nehmen)", "Geradeaus weiter auf Rotebühlplatz (240 m)"]))
        t += timedelta(minutes=4)
        options.append(
            TransitOption(
                departure=planned,
                arrival=t,
                planned_departure=planned,
                legs=legs,
                delay_min=delay,
                cancelled=cancelled,
            )
        )
    return options


def _between(a: tuple[float, float], b: tuple[float, float], f: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def _incidents(car_km: float, scenario: str) -> list[Incident]:
    if scenario == "stau":
        road = "A8" if car_km > 8 else "B14"
        return [
            Incident(road, "warning", f"{road} Stuttgart → Karlsruhe", "Unfall, linker Fahrstreifen blockiert", delay_min=18),
            Incident(road, "roadworks", f"{road} Anschlussstelle Degerloch", "Tagesbaustelle", None),
        ]
    if scenario == "winter":
        return [Incident("A8" if car_km > 8 else "B10", "warning", "Glätte", "Streudienst im Einsatz", delay_min=6)]
    return []
