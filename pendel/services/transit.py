"""Bahn- und ÖPNV-Verbindungen über Transitous.

Transitous (https://transitous.org) ist ein freier, von einer Community betriebener
Routing-Dienst für Bus und Bahn in ganz Deutschland – inklusive Echtzeitdaten,
Fußweg-Anweisungen und Linienverlauf für die Karte. Technisch steckt die
Software MOTIS dahinter.

Doku (OpenAPI): https://github.com/motis-project/motis/blob/master/openapi.yaml
Nutzungsregeln: https://transitous.org/api/ – kostenlos für nichtkommerzielle
Open-Source-Projekte, sparsam abfragen (deutlich unter 720 Suchen pro Tag),
Quelle verlinken (siehe Fußzeile der App).

Warum nicht mehr db.transport.rest? Der Dienst ist abgeschaltet, seit die
Deutsche Bahn die alte HAFAS-Schnittstelle dahinter vom Netz genommen hat.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from ..models import Place, TransitLeg, TransitOption
from ..timeutil import aware, to_local
from .http import get_json

DEFAULT_BASE = "https://api.transitous.org"
# Die API ist versioniert; neuere Server kennen /api/v6, ältere nur /api/v5 usw.
# Wir probieren von neu nach alt und merken uns, was funktioniert.
PLAN_VERSIONS = ["v6", "v5", "v4", "v3", "v2"]
_working_version: dict[str, str] = {}

# Verkehrsmittel → Kürzel für den farbigen Linien-Chip
KIND = {
    "SUBURBAN": "S", "METRO": "S",
    "SUBWAY": "U", "TRAM": "U",  # in Stuttgart fährt die Stadtbahn als „U“
    "BUS": "B", "COACH": "B", "ODM": "B", "FLEX": "B",
    "REGIONAL_RAIL": "R", "REGIONAL_FAST_RAIL": "R", "RAIL": "R",
    "HIGHSPEED_RAIL": "F", "LONG_DISTANCE": "F", "NIGHT_RAIL": "F",
}
NAMES = {"S": "S-Bahn", "U": "Stadtbahn", "B": "Bus", "R": "Regionalzug", "F": "Fernzug"}

# Abbiegehinweise auf Deutsch (Werte aus dem OpenAPI-Schema „Direction“)
DIRECTIONS = {
    "DEPART": "Losgehen",
    "CONTINUE": "Geradeaus weiter",
    "SLIGHTLY_LEFT": "Leicht links halten",
    "LEFT": "Links abbiegen",
    "HARD_LEFT": "Scharf links abbiegen",
    "SLIGHTLY_RIGHT": "Leicht rechts halten",
    "RIGHT": "Rechts abbiegen",
    "HARD_RIGHT": "Scharf rechts abbiegen",
    "CIRCLE_CLOCKWISE": "In den Kreisverkehr",
    "CIRCLE_COUNTERCLOCKWISE": "In den Kreisverkehr",
    "STAIRS": "Treppe nehmen",
    "ELEVATOR": "Aufzug nehmen",
    "UTURN_LEFT": "Wenden",
    "UTURN_RIGHT": "Wenden",
}


async def fetch_journeys(
    base: str, origin: Place, dest: Place, departure: datetime, results: int = 5, arrive_by: datetime | None = None
) -> list[TransitOption]:
    """Verbindungen ab ``departure`` – oder, wenn ``arrive_by`` gesetzt ist, mit Ankunft bis dahin."""
    base = (base or DEFAULT_BASE).rstrip("/")
    if "transport.rest" in base:  # alte, abgeschaltete Adresse aus früheren Einstellungen
        base = DEFAULT_BASE
    when = arrive_by or departure
    params = {
        "fromPlace": f"{origin.lat:.6f},{origin.lon:.6f}",
        "toPlace": f"{dest.lat:.6f},{dest.lon:.6f}",
        "time": aware(when).isoformat(timespec="seconds"),
        "arriveBy": "true" if arrive_by else "false",
        "numItineraries": results,
        "searchWindow": 3600,  # eine Stunde rund um die Wunschzeit
        "detailedTransfers": "true",  # Fußwege mit Abbiegehinweisen und Linienverlauf
        "language": "de",
    }
    versions = [_working_version[base]] if base in _working_version else PLAN_VERSIONS
    last_error: Exception | None = None
    for v in versions:
        try:
            data = await get_json(f"{base}/api/{v}/plan", params, ttl=120)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):  # Version gibt es auf dem Server (noch) nicht
                last_error = e
                continue
            raise
        _working_version[base] = v
        return parse_plan(data)
    raise last_error or RuntimeError("Keine passende API-Version gefunden")


def parse_plan(data: dict) -> list[TransitOption]:
    options: list[TransitOption] = []
    for it in data.get("itineraries", []):
        legs = [_parse_leg(leg) for leg in it.get("legs", [])]
        legs = [leg for leg in legs if leg is not None]
        rides = [leg for leg in legs if not leg.walking]
        if not legs or not rides:
            continue  # reine Fußwege gehören nicht zur Bahn-Bewertung
        first_ride = rides[0]
        last = legs[-1]
        options.append(
            TransitOption(
                departure=legs[0].departure,
                arrival=last.arrival,
                planned_departure=_shift(legs[0].departure, first_ride),
                legs=legs,
                delay_min=rides[-1].delay_min,
                cancelled=any(leg.cancelled for leg in legs),
            )
        )
    options.sort(key=lambda o: o.departure)
    return options


def _shift(dep: datetime, first_ride: TransitLeg) -> datetime:
    """Planmäßige Abfahrt der ganzen Verbindung (falls der erste Zug Verspätung hat)."""
    if first_ride.planned_departure is None:
        return dep
    delay = first_ride.departure - first_ride.planned_departure
    return dep - delay


def _parse_leg(leg: dict) -> TransitLeg | None:
    dep = _time(leg.get("startTime"))
    arr = _time(leg.get("endTime"))
    if dep is None or arr is None:
        return None
    mode = leg.get("mode", "")
    frm, to = leg.get("from") or {}, leg.get("to") or {}
    path = decode_polyline(leg.get("legGeometry") or {})
    if mode in ("WALK", "BIKE", "CAR", "RENTAL"):
        return TransitLeg(
            line="Fußweg",
            origin=frm.get("name", ""),
            destination=to.get("name", ""),
            departure=dep,
            arrival=arr,
            walking=True,
            distance_m=float(leg.get("distance") or 0),
            steps=_steps(leg.get("steps") or []),
            path=path,
        )
    planned_arr = _time(leg.get("scheduledEndTime")) or arr
    line = (
        leg.get("displayName")
        or leg.get("routeShortName")
        or leg.get("tripShortName")
        or NAMES.get(KIND.get(mode, ""), "Zug")
    )
    return TransitLeg(
        line=line,
        origin=frm.get("name", ""),
        destination=to.get("name", ""),
        departure=dep,
        arrival=arr,
        delay_min=max(0, round((arr - planned_arr).total_seconds() / 60)),
        cancelled=bool(leg.get("cancelled") or frm.get("cancelled") or to.get("cancelled")),
        kind=KIND.get(mode, ""),
        headsign=leg.get("headsign") or "",
        planned_departure=_time(leg.get("scheduledStartTime")),
        track_from=frm.get("track") or frm.get("scheduledTrack") or "",
        track_to=to.get("track") or to.get("scheduledTrack") or "",
        stops_between=len(leg.get("intermediateStops") or []),
        path=path,
        color=_hex(leg.get("routeColor")),
        text_color=_hex(leg.get("routeTextColor")),
    )


def _steps(steps: list[dict]) -> list[str]:
    """Wandelt die Abbiegehinweise in kurze deutsche Sätze um."""
    out: list[str] = []
    for st in steps:
        verb = DIRECTIONS.get(st.get("relativeDirection", ""), "Weiter")
        street = (st.get("streetName") or "").strip()
        dist = float(st.get("distance") or 0)
        if dist < 5 and verb not in ("Treppe nehmen", "Aufzug nehmen"):
            continue  # winzige Schritte weglassen
        text = f"{verb} auf {street}" if street else verb
        out.append(f"{text} ({dist:.0f} m)" if dist >= 5 else text)
    return out


def decode_polyline(geo: dict) -> list[tuple[float, float]]:
    """Google-Polyline dekodieren (Genauigkeit steht in ``precision``, meist 6 oder 7)."""
    points = geo.get("points") or ""
    factor = 10 ** int(geo.get("precision") or 5)
    coords: list[tuple[float, float]] = []
    index = lat = lon = 0
    while index < len(points):
        for is_lat in (True, False):
            shift = result = 0
            while True:
                b = ord(points[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lat:
                lat += delta
            else:
                lon += delta
        coords.append((lat / factor, lon / factor))
    return coords


def _hex(color: str | None) -> str:
    if not color:
        return ""
    color = color.strip().lstrip("#")
    return f"#{color}" if len(color) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in color) else ""


def _time(s: str | None) -> datetime | None:
    if not s:
        return None
    return to_local(datetime.fromisoformat(s.replace("Z", "+00:00")))
