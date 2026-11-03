"""Datenmodelle des Pendel-Beraters.

Alle Daten werden als ``dataclass`` beschrieben. So sieht man auf einen Blick,
welche Felder es gibt, und bekommt Typ-Hinweise im Editor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Mode(str, Enum):
    """Die drei Verkehrsmittel, die verglichen werden."""

    BIKE = "rad"
    TRANSIT = "bahn"
    CAR = "auto"

    @property
    def label(self) -> str:
        return {"rad": "Rad", "bahn": "Bahn", "auto": "Auto"}[self.value]

    @property
    def icon(self) -> str:  # Material-Icon-Name für NiceGUI
        return {"rad": "directions_bike", "bahn": "train", "auto": "directions_car"}[self.value]

    @property
    def color(self) -> str:  # Akzentfarbe in der Oberfläche
        return {"rad": "#16a34a", "bahn": "#2563eb", "auto": "#ea580c"}[self.value]


# ---------------------------------------------------------------------------
# Einstellungen (werden in data/settings.json gespeichert)
# ---------------------------------------------------------------------------


@dataclass
class Place:
    """Ein Ort mit Koordinaten (z. B. „Zuhause“ oder „DHBW“)."""

    name: str
    lat: float
    lon: float


@dataclass
class Route:
    """Eine Pendelstrecke, die der Nutzer selbst anlegt."""

    id: str
    name: str
    origin: Place
    destination: Place
    departure: str = "07:30"  # gewünschte Abfahrt, Format HH:MM
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # 0 = Montag
    modes: list[str] = field(default_factory=lambda: ["rad", "bahn", "auto"])
    notify_time: str = "06:45"  # wann die Morgen-Empfehlung berechnet wird


@dataclass
class Preferences:
    """Persönliche Vorlieben – sie steuern die Entscheidungslogik."""

    # Was ist dir eine Stunde Zeit wert? Damit werden Euro in Minuten umgerechnet.
    value_of_time_eur_h: float = 12.0

    # Rad
    bike_max_km: float = 15.0
    bike_min_temp_c: float = 2.0
    bike_max_rain_mm: float = 2.0  # mm pro Stunde, darüber kein Rad
    bike_max_gusts_kmh: float = 55.0
    bike_rain_penalty_min_per_mm: float = 10.0
    bike_cold_below_c: float = 8.0
    bike_sport_bonus_min: float = 5.0  # Bewegung zählt als Pluspunkt
    bike_speed_factor: float = 1.0  # <1 = du fährst schneller als das Routing annimmt

    # Bahn
    transit_cost_eur: float = 0.0  # 0 = Deutschlandticket o. ä. (keine Zusatzkosten)
    transit_transfer_penalty_min: float = 4.0
    transit_delay_risk_factor: float = 0.5  # Aufschlag für Unsicherheit bei Verspätungen

    # Auto
    fuel_price_eur_l: float = 1.75
    consumption_l_100km: float = 6.5
    parking_cost_eur: float = 0.0
    parking_search_min: float = 5.0
    rush_hour_factor: float = 1.35  # Fahrzeit-Aufschlag im Berufsverkehr
    incident_default_delay_min: float = 8.0


@dataclass
class Settings:
    routes: list[Route] = field(default_factory=list)
    prefs: Preferences = field(default_factory=Preferences)
    user_name: str = ""
    demo_mode: bool = True
    demo_scenario: str = "auto"  # auto | sonne | regen | stau | bahnchaos | winter
    ntfy_topic: str = ""  # optional: Push-Nachricht über ntfy.sh
    transit_api_base: str = "https://v6.db.transport.rest"


# ---------------------------------------------------------------------------
# Ergebnisse der Datenquellen
# ---------------------------------------------------------------------------


@dataclass
class HourWeather:
    time: datetime
    temp_c: float
    apparent_c: float
    precip_mm: float
    precip_prob: int
    wind_kmh: float
    gusts_kmh: float
    code: int


@dataclass
class WeatherInfo:
    at_departure: HourWeather
    hours: list[HourWeather]  # die nächsten Stunden für das Diagramm

    @property
    def description(self) -> str:
        from .weather_codes import describe

        return describe(self.at_departure.code)


@dataclass
class TransitLeg:
    line: str  # z. B. "S1" oder "Fußweg"
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    delay_min: int = 0
    walking: bool = False
    cancelled: bool = False


@dataclass
class TransitOption:
    departure: datetime  # tatsächliche (prognostizierte) Abfahrt
    arrival: datetime
    planned_departure: datetime
    legs: list[TransitLeg]
    delay_min: int = 0  # Ankunftsverspätung
    cancelled: bool = False

    @property
    def duration_min(self) -> float:
        return (self.arrival - self.departure).total_seconds() / 60

    @property
    def transfers(self) -> int:
        rides = [leg for leg in self.legs if not leg.walking]
        return max(0, len(rides) - 1)

    @property
    def lines(self) -> list[str]:
        return [leg.line for leg in self.legs if not leg.walking]


@dataclass
class Incident:
    """Meldung der Autobahn GmbH (Stau, Baustelle, Sperrung)."""

    road: str
    kind: str  # warning | closure | roadworks
    title: str
    subtitle: str
    delay_min: float | None = None
    blocked: bool = False


@dataclass
class RouteLeg:
    distance_km: float
    duration_min: float  # ohne Verkehr (Freifluss)
    roads: list[str] = field(default_factory=list)  # z. B. ["A8", "A81"]
    estimated: bool = False  # True = nur über Luftlinie geschätzt (Routing nicht erreichbar)


@dataclass
class TravelData:
    """Alles, was für eine Entscheidung gesammelt wird."""

    weather: WeatherInfo | None
    transit: list[TransitOption]
    car: RouteLeg | None
    bike: RouteLeg | None
    incidents: list[Incident]
    errors: dict[str, str] = field(default_factory=dict)  # Quelle -> Fehlermeldung
    fetched_at: datetime = field(default_factory=datetime.now)
    demo: bool = False


# ---------------------------------------------------------------------------
# Ergebnis der Entscheidungslogik
# ---------------------------------------------------------------------------


@dataclass
class ScorePart:
    label: str
    minutes: float  # positiv = schlechter, negativ = Bonus


@dataclass
class ModeScore:
    mode: Mode
    available: bool
    felt_min: float = 0.0  # „gefühlte Minuten“ – kleiner ist besser
    travel_min: float = 0.0  # echte Reisezeit
    cost_eur: float = 0.0
    parts: list[ScorePart] = field(default_factory=list)
    excluded_reason: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    best: Mode | None
    scores: list[ModeScore]
    headline: str
    reasons: list[str]
    confidence: str  # "klar" | "knapp" | "keine"
    margin_min: float = 0.0
