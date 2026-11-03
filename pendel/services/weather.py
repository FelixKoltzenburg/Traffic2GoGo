"""Wetter von Open-Meteo (kostenlos, ohne API-Schlüssel, nutzt u. a. DWD-Modelle).

Doku: https://open-meteo.com/en/docs
"""
from __future__ import annotations

from datetime import datetime

from ..models import HourWeather, WeatherInfo
from .http import get_json

URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,apparent_temperature,precipitation,precipitation_probability,weather_code,wind_speed_10m,wind_gusts_10m"


async def fetch_weather(lat: float, lon: float, departure: datetime) -> WeatherInfo:
    data = await get_json(
        URL,
        {
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "hourly": HOURLY,
            "timezone": "Europe/Berlin",
            "forecast_days": 2,
            "wind_speed_unit": "kmh",
        },
        ttl=900,
    )
    return parse_weather(data, departure)


def parse_weather(data: dict, departure: datetime) -> WeatherInfo:
    """Wandelt die Spalten-Struktur von Open-Meteo in eine Liste von Stunden um."""
    h = data["hourly"]
    hours: list[HourWeather] = []
    for i, t in enumerate(h["time"]):
        hours.append(
            HourWeather(
                time=datetime.fromisoformat(t),
                temp_c=_num(h["temperature_2m"][i]),
                apparent_c=_num(h["apparent_temperature"][i]),
                precip_mm=_num(h["precipitation"][i]),
                precip_prob=int(_num(h["precipitation_probability"][i])),
                wind_kmh=_num(h["wind_speed_10m"][i]),
                gusts_kmh=_num(h["wind_gusts_10m"][i]),
                code=int(_num(h["weather_code"][i])),
            )
        )
    # Stunde finden, in der die Abfahrt liegt
    dep_hour = departure.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    idx = next((i for i, x in enumerate(hours) if x.time >= dep_hour), 0)
    window = hours[max(0, idx - 2) : idx + 12]
    return WeatherInfo(at_departure=hours[idx], hours=window)


def _num(v) -> float:
    return float(v) if v is not None else 0.0
