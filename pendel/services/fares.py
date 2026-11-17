"""Ticketpreise für Bus und Bahn – mit oder ohne Deutschlandticket.

Mit Deutschlandticket kostet jede Fahrt 0 € (der Monatspreis ist schon bezahlt).
Ohne Deutschlandticket schätzt die App den Preis eines EinzelTickets:

* **Im VVS-Gebiet** (Stuttgart und die Kreise Böblingen, Esslingen, Göppingen,
  Ludwigsburg, Rems-Murr): Der Preis hängt an der Zahl der Tarifzonen,
  Start- und Zielzone zählen mit. Stuttgart ist Zone 1, die übrigen Zonen
  liegen grob ringförmig darum. Die Zonen schätzen wir aus der Entfernung
  zum Stuttgarter Hauptbahnhof – deshalb steht in der App „ca.“.
* **Außerhalb des VVS:** grobe Schätzung nach Kilometern (bwtarif/DB-Nahverkehr).

Quellen der Preise:
* VVS EinzelTicket: https://www.vvs.de/tickets-und-abos/einzelticket
* Deutschlandticket: https://regional.bahn.de/tickets/Deutschlandticket
Preise ändern sich meist zum Jahreswechsel – dann einfach die Tabellen anpassen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from ..models import Place, TransitOption
from .routing import haversine_km

# EinzelTicket Erwachsene (Kauf am Automaten) nach Anzahl Zonen; 7 = „7 und mehr (Netz)“
VVS_EINZEL = {1: 3.70, 2: 4.90, 3: 6.30, 4: 7.80, 5: 9.50, 6: 10.80, 7: 11.90}

# Deutschlandticket pro Monat: (gültig ab, Preis)
DEUTSCHLANDTICKET = [(date(2025, 1, 1), 58.00), (date(2026, 1, 1), 63.00), (date(2027, 1, 1), 66.80)]

STUTTGART_HBF = (48.7840, 9.1815)
ZONE1_RADIUS_KM = 8.5  # ungefähr die Stuttgarter Stadtgrenze
RING_KM = 7.0  # grobe Breite eines Zonenrings
VVS_RADIUS_KM = 50.0  # grob die Außengrenze des VVS (z. B. Geislingen, Herrenberg)


@dataclass
class Fare:
    amount: float
    label: str  # z. B. "VVS 2 Zonen (geschätzt)"


def deutschlandticket_price(day: date | None = None) -> float:
    day = day or date.today()
    price = DEUTSCHLANDTICKET[0][1]
    for since, p in DEUTSCHLANDTICKET:
        if day >= since:
            price = p
    return price


def vvs_ring(p: Place) -> int:
    """Grobe Zonen-„Ringnummer“: 1 = Stuttgart, 2 = erster Ring drumherum usw."""
    d = haversine_km(STUTTGART_HBF, (p.lat, p.lon))
    if d <= ZONE1_RADIUS_KM:
        return 1
    return 1 + math.ceil((d - ZONE1_RADIUS_KM) / RING_KM)


def _bearing(p: Place) -> float:
    """Himmelsrichtung vom Hauptbahnhof aus (0° = Norden), für „gleiche Seite der Stadt?“."""
    lat1, lon1 = map(math.radians, STUTTGART_HBF)
    lat2, lon2 = math.radians(p.lat), math.radians(p.lon)
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.degrees(math.atan2(y, x)) % 360


def vvs_zones(a: Place, b: Place) -> int:
    """Wie viele Zonen werden befahren? (Start- und Zielzone zählen mit.)

    Seit der VVS-Tarifreform 2019 ist jeder Ring *eine* Zone. Wer auf derselben
    Seite der Stadt bleibt, fährt nur durch die Ringe dazwischen. Wer quer durch
    Stuttgart (Zone 1) fährt, berührt alle Ringe von 1 bis zum äußersten –
    jeder Ring zählt aber nur einmal.
    """
    ra, rb = vvs_ring(a), vvs_ring(b)
    angle = abs(_bearing(a) - _bearing(b)) % 360
    angle = min(angle, 360 - angle)
    if ra > 1 and rb > 1 and angle < 70:
        zones = abs(ra - rb) + 1  # gleiche Seite der Stadt
    else:
        zones = max(ra, rb)  # von/nach/durch Stuttgart
    return max(1, min(zones, 7))


def in_vvs(p: Place) -> bool:
    return haversine_km(STUTTGART_HBF, (p.lat, p.lon)) <= VVS_RADIUS_KM


def estimate_fare(origin: Place, dest: Place) -> Fare:
    """Preis eines EinzelTickets für Erwachsene (Schätzung)."""
    if in_vvs(origin) and in_vvs(dest):
        z = vvs_zones(origin, dest)
        name = "Netz" if z >= 7 else ("1 Zone" if z == 1 else f"{z} Zonen")
        return Fare(VVS_EINZEL[z], f"VVS EinzelTicket, {name} (geschätzt)")
    # Außerhalb des VVS: grob 0,21 €/km Bahnstrecke plus Grundpreis, mindestens Netzpreis
    km = haversine_km((origin.lat, origin.lon), (dest.lat, dest.lon)) * 1.2
    amount = max(VVS_EINZEL[7], round(2.0 + 0.21 * km, 1))
    return Fare(amount, "Nahverkehr außerhalb VVS (grob geschätzt)")


def attach_fares(origin: Place, dest: Place, options: list[TransitOption]) -> None:
    """Trägt den geschätzten Ticketpreis an jeder Verbindung ein."""
    fare = estimate_fare(origin, dest)
    for opt in options:
        opt.fare_eur = fare.amount
        opt.fare_label = fare.label
