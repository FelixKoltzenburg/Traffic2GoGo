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
    lines = [("U2", "S1"), ("U1",), ("S1", "Bus 42"), ("U2",)]
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
        legs.append(TransitLeg("Fußweg", route.origin.name, "Haltestelle", t, t + timedelta(minutes=5), walking=True))
        t += timedelta(minutes=5)
        part = ride / len(chosen)
        for j, ln in enumerate(chosen):
            if j:
                t += timedelta(minutes=4)  # Umstiegszeit
            legs.append(TransitLeg(ln, "Halt", "Halt", t, t + timedelta(minutes=part), delay_min=delay, cancelled=cancelled))
            t += timedelta(minutes=part)
        t += timedelta(minutes=delay)
        legs.append(TransitLeg("Fußweg", "Haltestelle", route.destination.name, t, t + timedelta(minutes=4), walking=True))
        t += timedelta(minutes=4)
        options.append(
            TransitOption(
                departure=planned + timedelta(minutes=0),
                arrival=t,
                planned_departure=planned,
                legs=legs,
                delay_min=delay,
                cancelled=cancelled,
            )
        )
    return options


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
