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
        return {"rad": "#10b981", "bahn": "#6366f1", "auto": "#f59e0b"}[self.value]


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
    notify_time: str = "06:45"  # wann die Tages-Empfehlung im Verlauf gespeichert wird


@dataclass
class Preferences:
    """Persönliche Vorlieben – sie steuern die Entscheidungslogik."""

    # Abwägung Zeit gegen Geld bei der Empfehlung: Was ist dir eine Stunde wert?
    # (Die angezeigten Fahrzeiten bleiben echte Minuten.)
    value_of_time_eur_h: float = 12.0

    # Rad
    bike_max_km: float = 15.0
    bike_min_temp_c: float = 2.0
    bike_max_rain_mm: float = 0.5  # mm pro Stunde, darüber kein Rad (0,5 = mehr als Nieselregen)
    bike_max_gusts_kmh: float = 55.0
    bike_speed_factor: float = 1.0  # <1 = du fährst schneller als das Routing annimmt

    # Bahn
    has_deutschlandticket: bool = False  # an = Bahnfahren kostet 0 €, aus = echten Ticketpreis schätzen

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
    demo_mode: bool = False  # Standard: echte Daten. Demo nur zum Ausprobieren ohne Internet.
    demo_scenario: str = "auto"  # auto | sonne | regen | stau | bahnchaos | winter
    season: str = "auto"  # Design-Jahreszeit: auto | fruehling | sommer | herbst | winter
    animations: bool = True  # Blätter, Schnee usw. am Seitenrand
    transit_api_base: str = "https://api.transitous.org"  # freier ÖPNV-Routingdienst (MOTIS)


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
    departure: datetime  # tatsächliche (prognostizierte) Zeit
    arrival: datetime
    delay_min: int = 0  # Ankunftsverspätung dieses Abschnitts
    walking: bool = False
    cancelled: bool = False
    # --- Details für die Verbindungsansicht ---------------------------------
    kind: str = ""  # "S", "U", "B", "R", "F" (Fernverkehr) – steuert die Farbe des Linien-Chips
    headsign: str = ""  # Fahrtrichtung, z. B. "Vaihingen"
    planned_departure: datetime | None = None
    track_from: str = ""  # Gleis/Steig bei Abfahrt
    track_to: str = ""  # Gleis/Steig bei Ankunft
    stops_between: int = 0  # Anzahl Zwischenhalte
    distance_m: float = 0.0  # bei Fußwegen: Länge in Metern
    steps: list[str] = field(default_factory=list)  # bei Fußwegen: Abbiegehinweise
    path: list[tuple[float, float]] = field(default_factory=list)  # Linienverlauf (lat, lon) für die Karte
    color: str = ""  # Linienfarbe aus dem Fahrplan, z. B. "#1d9d4c"
    text_color: str = ""

    @property
    def duration_min(self) -> float:
        return (self.arrival - self.departure).total_seconds() / 60


@dataclass
class TransitOption:
    departure: datetime  # tatsächliche (prognostizierte) Abfahrt
    arrival: datetime
    planned_departure: datetime
    legs: list[TransitLeg]
    delay_min: int = 0  # Ankunftsverspätung
    cancelled: bool = False
    fare_eur: float | None = None  # EinzelTicket-Preis (ohne Deutschlandticket)
    fare_label: str = ""  # Woher der Preis stammt, z. B. "VVS EinzelTicket, 2 Zonen (geschätzt)"

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
    total_min: float = 0.0  # echte Reisezeit von Tür zu Tür in Minuten
    travel_min: float = 0.0  # echte Reisezeit
    cost_eur: float = 0.0
    parts: list[ScorePart] = field(default_factory=list)
    excluded_reason: str = ""
    notes: list[str] = field(default_factory=list)
    option: TransitOption | None = None  # bei der Bahn: die gewählte Verbindung (für die Detailansicht)


@dataclass
class Recommendation:
    best: Mode | None
    scores: list[ModeScore]
    headline: str
    reasons: list[str]
    confidence: str  # "klar" | "knapp" | "keine"
    margin_min: float = 0.0
