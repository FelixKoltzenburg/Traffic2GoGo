"""Entscheidungslogik: Welches Verkehrsmittel ist heute das beste?

Idee: „gefühlte Minuten“ (in der Verkehrsplanung heißt das *generalisierte
Kosten*). Alles wird in Minuten umgerechnet und addiert:

    gefühlte Minuten = Reisezeit
                     + Aufschläge (Regen, Kälte, Umstiege, Stau, Parksuche …)
                     + Kosten in Minuten (Euro ÷ Wert deiner Zeit)
                     − Boni (z. B. Bewegung beim Radfahren)

Das Verkehrsmittel mit den wenigsten gefühlten Minuten gewinnt. Bestimmte
Bedingungen schließen ein Verkehrsmittel ganz aus (z. B. Gewitter beim Rad).

Jede Zahl wird als ``ScorePart`` gespeichert. So kann die Oberfläche genau
zeigen, *warum* die App sich entschieden hat.
"""
from __future__ import annotations # hallo

from datetime import datetime, time

from .models import (
    HourWeather,
    Mode,
    ModeScore,
    Preferences,
    Recommendation,
    Route,
    ScorePart,
    TravelData,
)
from .weather_codes import ICE_OR_SNOW, THUNDER, describe


def de(x: float, digits: int = 1) -> str:
    """Zahl mit deutschem Dezimalkomma, z. B. 1,6."""
    return f"{x:.{digits}f}".replace(".", ",")

CLEAR_MARGIN_MIN = 5.0  # ab diesem Vorsprung gilt die Empfehlung als „klar“


def is_rush_hour(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return time(6, 30) <= t <= time(9, 0) or time(16, 0) <= t <= time(18, 30)


def _money_to_min(eur: float, prefs: Preferences) -> float:
    return eur / max(prefs.value_of_time_eur_h, 1.0) * 60


# ---------------------------------------------------------------------------
# Rad
# ---------------------------------------------------------------------------


def score_bike(data: TravelData, prefs: Preferences) -> ModeScore:
    s = ModeScore(Mode.BIKE, available=True)
    if data.bike is None:
        return _excluded(s, "Keine Radroute verfügbar")
    if data.bike.distance_km > prefs.bike_max_km:
        return _excluded(s, f"{de(data.bike.distance_km)} km sind mehr als dein Maximum von {prefs.bike_max_km:.0f} km")

    travel = data.bike.duration_min * prefs.bike_speed_factor
    s.travel_min = travel
    s.parts.append(ScorePart("Fahrzeit", travel))

    w: HourWeather | None = data.weather.at_departure if data.weather else None
    if w is None:
        s.notes.append("Ohne Wetterdaten bewertet")
    else:
        if w.code in THUNDER:
            return _excluded(s, "Gewitter angesagt")
        if w.code in ICE_OR_SNOW or (w.temp_c <= 0.5 and w.precip_mm > 0):
            return _excluded(s, "Schnee oder Glätte")
        if w.temp_c < prefs.bike_min_temp_c:
            return _excluded(s, f"Nur {w.temp_c:.0f} °C – unter deiner Grenze von {prefs.bike_min_temp_c:.0f} °C")
        if w.precip_mm > prefs.bike_max_rain_mm:
            return _excluded(s, f"Starker Regen ({de(w.precip_mm)} mm/h)")
        if w.gusts_kmh > prefs.bike_max_gusts_kmh:
            return _excluded(s, f"Sturmböen bis {w.gusts_kmh:.0f} km/h")

        if w.precip_mm >= 0.1:
            s.parts.append(ScorePart(f"Regen {de(w.precip_mm)} mm/h", w.precip_mm * prefs.bike_rain_penalty_min_per_mm))
        if w.precip_prob >= 40:
            s.parts.append(ScorePart(f"Regenrisiko {w.precip_prob} %", (w.precip_prob - 40) / 60 * 4))
        if w.apparent_c < prefs.bike_cold_below_c:
            s.parts.append(ScorePart(f"Kälte (gefühlt {w.apparent_c:.0f} °C)", (prefs.bike_cold_below_c - w.apparent_c) * 0.6))
        if w.wind_kmh > 20:
            s.parts.append(ScorePart(f"Wind {w.wind_kmh:.0f} km/h", (w.wind_kmh - 20) * 0.25))
        s.notes.append(f"{describe(w.code)}, {w.temp_c:.0f} °C")

    if prefs.bike_sport_bonus_min:
        s.parts.append(ScorePart("Bonus: Bewegung", -prefs.bike_sport_bonus_min))
    s.notes.append(f"{de(data.bike.distance_km)} km, ca. {travel:.0f} min")
    if data.bike.estimated:
        s.notes.append("Strecke nur geschätzt (Routing nicht erreichbar)")
    return _finish(s)


# ---------------------------------------------------------------------------
# Bahn
# ---------------------------------------------------------------------------


def score_transit(data: TravelData, prefs: Preferences, departure: datetime) -> ModeScore:
    s = ModeScore(Mode.TRANSIT, available=True)
    if not data.transit:
        return _excluded(s, "Keine Verbindungsdaten" + (" (Dienst nicht erreichbar)" if "bahn" in data.errors else ""))

    candidates = [o for o in data.transit if not o.cancelled and (o.departure - departure).total_seconds() > -120]
    if not candidates:
        return _excluded(s, "Alle passenden Verbindungen fallen aus")

    best_parts: list[ScorePart] | None = None
    best_total = float("inf")
    best_opt = None
    for opt in candidates:
        wait = max(0.0, (opt.departure - departure).total_seconds() / 60)
        parts = [ScorePart("Fahrzeit inkl. Fußwege", opt.duration_min)]
        if wait >= 1:
            parts.append(ScorePart(f"Warten bis {opt.departure:%H:%M} (halb gewertet)", wait * 0.5))
        if opt.transfers:
            parts.append(ScorePart(f"{opt.transfers}× Umsteigen", opt.transfers * prefs.transit_transfer_penalty_min))
        if opt.delay_min >= 3:
            parts.append(ScorePart(f"Unsicherheit ({opt.delay_min} min Verspätung)", opt.delay_min * prefs.transit_delay_risk_factor))
        if prefs.transit_cost_eur > 0:
            parts.append(ScorePart(f"Ticket {de(prefs.transit_cost_eur, 2)} €", _money_to_min(prefs.transit_cost_eur, prefs)))
        total = sum(p.minutes for p in parts)
        if total < best_total:
            best_total, best_parts, best_opt = total, parts, opt

    assert best_opt is not None and best_parts is not None
    s.parts = best_parts
    s.travel_min = best_opt.duration_min
    s.cost_eur = prefs.transit_cost_eur
    lines = " → ".join(best_opt.lines) or "Fußweg"
    s.notes.append(f"{best_opt.departure:%H:%M} ab, {best_opt.arrival:%H:%M} an · {lines}")
    if best_opt.delay_min >= 3:
        s.notes.append(f"aktuell +{best_opt.delay_min} min")
    cancelled = sum(1 for o in data.transit if o.cancelled)
    if cancelled:
        s.notes.append(f"{cancelled} Verbindung(en) fallen aus")
    return _finish(s)


# ---------------------------------------------------------------------------
# Auto
# ---------------------------------------------------------------------------


def score_car(data: TravelData, prefs: Preferences, departure: datetime) -> ModeScore:
    s = ModeScore(Mode.CAR, available=True)
    if data.car is None:
        return _excluded(s, "Keine Autoroute verfügbar")

    base = data.car.duration_min
    s.parts.append(ScorePart("Fahrzeit ohne Verkehr", base))
    travel = base
    if is_rush_hour(departure):
        extra = base * (prefs.rush_hour_factor - 1)
        s.parts.append(ScorePart("Berufsverkehr", extra))
        travel += extra

    inc_min = 0.0
    for inc in data.incidents:
        if inc.kind == "roadworks":
            inc_min += 1.5
        elif inc.blocked or inc.kind == "closure":
            inc_min += inc.delay_min or 15
        else:
            inc_min += inc.delay_min or prefs.incident_default_delay_min
    if inc_min:
        n = len(data.incidents)
        roads = ", ".join(sorted({i.road for i in data.incidents}))
        s.parts.append(ScorePart(f"{n} Meldung(en) auf {roads}", inc_min))
        travel += inc_min

    w = data.weather.at_departure if data.weather else None
    if w and (w.code in ICE_OR_SNOW or (w.temp_c <= 0.5 and w.precip_mm > 0)):
        s.parts.append(ScorePart("Glätte", base * 0.25))
        travel += base * 0.25
    elif w and w.precip_mm >= 2:
        s.parts.append(ScorePart("Starkregen", base * 0.1))
        travel += base * 0.1

    if prefs.parking_search_min:
        s.parts.append(ScorePart("Parkplatzsuche", prefs.parking_search_min))
        travel += prefs.parking_search_min

    fuel = data.car.distance_km * prefs.consumption_l_100km / 100 * prefs.fuel_price_eur_l
    cost = fuel + prefs.parking_cost_eur
    s.cost_eur = cost
    s.parts.append(ScorePart(f"Kosten {de(cost, 2)} €", _money_to_min(cost, prefs)))
    s.travel_min = travel
    s.notes.append(f"{de(data.car.distance_km)} km, ca. {travel:.0f} min, {de(cost, 2)} €")
    if data.car.estimated:
        s.notes.append("Strecke nur geschätzt (Routing nicht erreichbar)")
    if data.incidents:
        s.notes.append(data.incidents[0].title + (f" – {data.incidents[0].subtitle}" if data.incidents[0].subtitle else ""))
    return _finish(s)


# ---------------------------------------------------------------------------
# Gesamtentscheidung
# ---------------------------------------------------------------------------


def evaluate(route: Route, prefs: Preferences, data: TravelData, departure: datetime) -> Recommendation:
    scores: list[ModeScore] = []
    if Mode.BIKE.value in route.modes:
        scores.append(score_bike(data, prefs))
    if Mode.TRANSIT.value in route.modes:
        scores.append(score_transit(data, prefs, departure))
    if Mode.CAR.value in route.modes:
        scores.append(score_car(data, prefs, departure))

    ranked = sorted((s for s in scores if s.available), key=lambda s: s.felt_min)
    if not ranked:
        return Recommendation(None, scores, "Keine Empfehlung möglich", ["Für keine Option liegen genug Daten vor."], "keine")

    best = ranked[0]
    reasons: list[str] = []
    margin = 0.0
    if len(ranked) > 1:
        second = ranked[1]
        margin = second.felt_min - best.felt_min
        if margin < 1:
            reasons.append(f"Praktisch gleichauf mit {second.mode.label}")
        else:
            reasons.append(f"Gefühlt {_fmt(margin)} min besser als {second.mode.label}")
    else:
        reasons.append("Die einzige Option, die heute in Frage kommt")

    reasons.extend(best.notes[:2])
    for other in scores:
        if other is best:
            continue
        if not other.available:
            reasons.append(f"{other.mode.label}: {other.excluded_reason}")
        else:
            worst = max((p for p in other.parts if p.minutes > 0 and not p.label.startswith("Fahrzeit")), key=lambda p: p.minutes, default=None)
            if worst and worst.minutes >= 3:
                reasons.append(f"{other.mode.label}: {worst.label} (+{_fmt(worst.minutes)} min)")

    confidence = "klar" if margin >= CLEAR_MARGIN_MIN or len(ranked) == 1 else "knapp"
    headline = f"{best.mode.label}"
    return Recommendation(best.mode, scores, headline, reasons, confidence, margin)


def _excluded(s: ModeScore, reason: str) -> ModeScore:
    s.available = False
    s.excluded_reason = reason
    s.parts = []
    return s


def _finish(s: ModeScore) -> ModeScore:
    s.felt_min = sum(p.minutes for p in s.parts)
    return s


def _fmt(x: float) -> str:
    return f"{x:.0f}"
