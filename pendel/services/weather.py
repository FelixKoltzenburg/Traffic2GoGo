"""Wetter: zuerst Open-Meteo, bei Problemen Bright Sky (beide kostenlos, ohne Schlüssel).

Open-Meteo begrenzt Anfragen pro IP-Adresse. Auf Render teilen sich viele Apps
dieselben IP-Adressen, deshalb kommt dort manchmal „429 Too Many Requests“.
Dann fragen wir Bright Sky (Daten vom Deutschen Wetterdienst) als Ersatz.

Doku: https://open-meteo.com/en/docs · https://brightsky.dev/docs/
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..models import HourWeather, WeatherInfo
from .http import get_json

URL = "https://api.open-meteo.com/v1/forecast"
BRIGHTSKY_URL = "https://api.brightsky.dev/weather"
HOURLY = "temperature_2m,apparent_temperature,precipitation,precipitation_probability,weather_code,wind_speed_10m,wind_gusts_10m"

TTL = 1800  # Wetter ändert sich langsam: 30 Minuten zwischenspeichern
STALE = 6 * 3600  # bei Ausfall darf ein bis zu 6 Stunden alter Wert genutzt werden


async def fetch_weather(lat: float, lon: float, departure: datetime) -> WeatherInfo:
    # Auf 2 Nachkommastellen (~1 km) runden: Nachbar-Anfragen teilen sich den Cache.
    lat, lon = round(lat, 2), round(lon, 2)
    try:
        data = await get_json(
            URL,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": HOURLY,
                "timezone": "Europe/Berlin",
                "forecast_days": 2,
                "wind_speed_unit": "kmh",
            },
            ttl=TTL,
            stale_ok=STALE,
        )
        return parse_weather(data, departure)
    except Exception as first_error:  # noqa: BLE001 – Ersatzdienst versuchen
        try:
            return await fetch_brightsky(lat, lon, departure)
        except Exception:  # noqa: BLE001
            raise first_error from None


async def fetch_brightsky(lat: float, lon: float, departure: datetime) -> WeatherInfo:
    day = departure.date()
    data = await get_json(
        BRIGHTSKY_URL,
        {
            "lat": lat,
            "lon": lon,
            "date": day.isoformat(),
            "last_date": (day + timedelta(days=2)).isoformat(),
            "tz": "Europe/Berlin",
        },
        ttl=TTL,
        stale_ok=STALE,
    )
    return parse_brightsky(data, departure)


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
    return _around(hours, departure)


def parse_brightsky(data: dict, departure: datetime) -> WeatherInfo:
    """Bright Sky liefert eine Liste von Stunden. Wetterlage wird in WMO-Codes übersetzt."""
    hours: list[HourWeather] = []
    for row in data["weather"]:
        temp = _num(row.get("temperature"))
        wind = _num(row.get("wind_speed"))
        precip = _num(row.get("precipitation"))
        hours.append(
            HourWeather(
                time=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=None),
                temp_c=temp,
                apparent_c=_wind_chill(temp, wind),
                precip_mm=precip,
                precip_prob=int(_num(row.get("precipitation_probability"))),
                wind_kmh=wind,
                gusts_kmh=_num(row.get("wind_gust_speed")),
                code=_wmo_code(row.get("condition"), row.get("icon"), precip),
            )
        )
    if not hours:
        raise ValueError("Bright Sky: keine Wetterdaten")
    return _around(hours, departure)


def _around(hours: list[HourWeather], departure: datetime) -> WeatherInfo:
    """Stunde der Abfahrt finden und ein Fenster um sie herum zurückgeben."""
    dep_hour = departure.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    idx = next((i for i, x in enumerate(hours) if x.time >= dep_hour), 0)
    window = hours[max(0, idx - 2) : idx + 12]
    return WeatherInfo(at_departure=hours[idx], hours=window)


def _wmo_code(condition: str | None, icon: str | None, precip: float) -> int:
    """Bright-Sky-Wetterlage grob auf die WMO-Codes abbilden, die der Rest der App kennt."""
    if condition == "thunderstorm":
        return 95
    if condition == "hail":
        return 96
    if condition == "snow":
        return 75 if precip >= 2 else 71
    if condition == "sleet":
        return 66
    if condition == "rain":
        return 65 if precip >= 4 else 63 if precip >= 1 else 61
    if condition == "fog" or icon == "fog":
        return 45
    if icon in ("clear-day", "clear-night"):
        return 0
    if icon in ("partly-cloudy-day", "partly-cloudy-night"):
        return 2
    return 3


def _wind_chill(temp: float, wind_kmh: float) -> float:
    """Gefühlte Temperatur (Windchill-Formel, gilt nur bei Kälte und Wind)."""
    if temp > 10 or wind_kmh < 5:
        return temp
    v = wind_kmh ** 0.16
    return round(13.12 + 0.6215 * temp - 11.37 * v + 0.3965 * temp * v, 1)


def _num(v) -> float:
    return float(v) if v is not None else 0.0
