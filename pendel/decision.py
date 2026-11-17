"""Entscheidungslogik: Welches Verkehrsmittel bringt dich am schnellsten ans Ziel?

Gezählt werden nur **echte Minuten von Tür zu Tür** – keine Umrechnung von Geld
in Zeit und keine künstlichen Aufschläge:

* **Rad:** Fahrzeit laut Routing (angepasst an dein Tempo).
* **Bahn:** Abfahrt-Modus: Warten bis zur Abfahrt + Fahrzeit inkl. Fußwegen,
  also die Zeit bis zur Ankunft. Ankunft-Modus: die Fahrzeit der spätesten
  Verbindung, die noch rechtzeitig ankommt. Verspätungen stecken schon in den
  Echtzeitdaten.
* **Auto:** Fahrzeit + Berufsverkehr + Staus/Sperrungen + Parkplatzsuche.

Die kürzeste Zeit gewinnt. Das Wetter verändert keine Minuten, sondern schließt
das Rad bei Gewitter, Glätte, starkem Regen, Sturm oder Kälte aus. Kosten werden
angezeigt, fließen aber nicht in die Entscheidung ein.

Jede Zahl wird als ``ScorePart`` gespeichert. So kann die Oberfläche genau
zeigen, wie die Zeit zustande kommt.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

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

CLEAR_MARGIN_MIN = 5.0  # ab 5 Minuten Vorsprung gilt die Empfehlung als „klar“


def is_rush_hour(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return time(6, 30) <= t <= time(9, 0) or time(16, 0) <= t <= time(18, 30)


def _fare(opt, prefs: Preferences) -> float:
    """Ticketpreis einer Verbindung: 0 € mit Deutschlandticket, sonst der geschätzte Preis."""
    if prefs.has_deutschlandticket:
        return 0.0
    return opt.fare_eur or 0.0


# ---------------------------------------------------------------------------
# Rad
# ---------------------------------------------------------------------------


def score_bike(data: TravelData, prefs: Preferences, arrive_by: datetime | None = None) -> ModeScore:
    s = ModeScore(Mode.BIKE, available=True)
    if data.bike is None:
        return _excluded(s, "Keine Radroute verfügbar")
    if data.bike.distance_km > prefs.bike_max_km:
        return _excluded(s, f"{de(data.bike.distance_km)} km sind mehr als dein Maximum von {prefs.bike_max_km:.0f} km")

    w: HourWeather | None = data.weather.at_departure if data.weather else None
    if w is not None:
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

    travel = data.bike.duration_min * prefs.bike_speed_factor
    s.parts.append(ScorePart("Fahrzeit", travel))
    s.travel_min = travel

    if w is None:
        s.notes.append("Ohne Wetterdaten bewertet")
    else:
        weather = f"{describe(w.code)}, {w.temp_c:.0f} °C"
        if w.precip_mm >= 0.1:
            weather += f", Regen {de(w.precip_mm)} mm/h"
        elif w.precip_prob >= 40:
            weather += f", Regenrisiko {w.precip_prob} %"
        s.notes.append(weather)
    s.notes.append(f"{de(data.bike.distance_km)} km")
    if data.bike.estimated:
        s.notes.append("Strecke nur geschätzt (Routing nicht erreichbar)")
    if arrive_by:
        s.notes.insert(0, f"Losfahren um {arrive_by - timedelta(minutes=travel):%H:%M}")
    return _finish(s)


# ---------------------------------------------------------------------------
# Bahn
# ---------------------------------------------------------------------------


def score_transit(
    data: TravelData, prefs: Preferences, departure: datetime, arrive_by: datetime | None = None
) -> ModeScore:
    """Wählt die beste Bahnverbindung und zählt ihre echten Minuten.

    Abfahrt-Modus: die Verbindung mit der frühesten Ankunft; gezählt wird die Zeit
    von der Wunsch-Abfahrt bis zur Ankunft (Warten + Fahrt).
    Ankunft-Modus: die spätestmögliche Verbindung, die noch rechtzeitig ankommt
    (wie in der DB-App); gezählt wird ihre Fahrzeit.
    """
    s = ModeScore(Mode.TRANSIT, available=True)
    if not data.transit:
        return _excluded(s, "Keine Verbindungsdaten" + (" (Dienst nicht erreichbar)" if "bahn" in data.errors else ""))

    usable = [o for o in data.transit if not o.cancelled]
    if arrive_by:
        candidates = [o for o in usable if (o.arrival - arrive_by).total_seconds() <= 60]
        if not candidates:
            return _excluded(s, f"Keine Verbindung kommt bis {arrive_by:%H:%M} an")
        opt = max(candidates, key=lambda o: (o.departure, -o.duration_min))  # so spät wie möglich los
        s.parts.append(ScorePart("Fahrzeit inkl. Fußwege", opt.duration_min))
    else:
        candidates = [o for o in usable if (o.departure - departure).total_seconds() > -120]
        if not candidates:
            return _excluded(s, "Alle passenden Verbindungen fallen aus")
        opt = min(candidates, key=lambda o: (o.arrival, o.duration_min))  # so früh wie möglich da
        wait = max(0.0, (opt.departure - departure).total_seconds() / 60)
        if wait >= 1:
            s.parts.append(ScorePart(f"Warten bis {opt.departure:%H:%M}", wait))
        s.parts.append(ScorePart("Fahrzeit inkl. Fußwege", opt.duration_min))

    s.option = opt
    s.travel_min = opt.duration_min
    s.cost_eur = _fare(opt, prefs)
    lines = " → ".join(opt.lines) or "Fußweg"
    s.notes.append(f"{opt.departure:%H:%M} ab, {opt.arrival:%H:%M} an · {lines}")
    if prefs.has_deutschlandticket:
        s.notes.append("Mit Deutschlandticket: 0 € pro Fahrt")
    elif opt.fare_eur:
        s.notes.append(f"Ticket {de(opt.fare_eur, 2)} € – {opt.fare_label}")
    if opt.transfers:
        s.notes.append(f"{opt.transfers}× umsteigen")
    if opt.delay_min >= 3:
        s.notes.append(f"aktuell +{opt.delay_min} min (schon eingerechnet)")
    cancelled = sum(1 for o in data.transit if o.cancelled)
    if cancelled:
        s.notes.append(f"{cancelled} Verbindung(en) fallen aus")
    return _finish(s)


# ---------------------------------------------------------------------------
# Auto
# ---------------------------------------------------------------------------


def score_car(
    data: TravelData, prefs: Preferences, departure: datetime, arrive_by: datetime | None = None
) -> ModeScore:
    s = ModeScore(Mode.CAR, available=True)
    if data.car is None:
        return _excluded(s, "Keine Autoroute verfügbar")

    base = data.car.duration_min
    s.parts.append(ScorePart("Fahrzeit ohne Verkehr", base))
    # Bei Ankunftswunsch zählt, ob die Fahrt selbst in den Berufsverkehr fällt
    start = arrive_by - timedelta(minutes=base * prefs.rush_hour_factor) if arrive_by else departure
    if is_rush_hour(start) or (arrive_by is not None and is_rush_hour(arrive_by)):
        s.parts.append(ScorePart("Berufsverkehr", base * (prefs.rush_hour_factor - 1)))

    inc_min = 0.0
    for inc in data.incidents:
        if inc.kind == "roadworks":
            inc_min += 1.5
        elif inc.blocked or inc.kind == "closure":
            inc_min += inc.delay_min or 15
        else:
            inc_min += inc.delay_min or prefs.incident_default_delay_min
    if inc_min:
        roads = ", ".join(sorted({i.road for i in data.incidents}))
        s.parts.append(ScorePart(f"{len(data.incidents)} Meldung(en) auf {roads}", inc_min))

    w = data.weather.at_departure if data.weather else None
    if w and (w.code in ICE_OR_SNOW or (w.temp_c <= 0.5 and w.precip_mm > 0)):
        s.parts.append(ScorePart("Langsamer wegen Glätte", base * 0.25))
    elif w and w.precip_mm >= 2:
        s.parts.append(ScorePart("Langsamer wegen Starkregen", base * 0.1))

    if prefs.parking_search_min:
        s.parts.append(ScorePart("Parkplatzsuche", prefs.parking_search_min))

    travel = sum(p.minutes for p in s.parts)
    fuel = data.car.distance_km * prefs.consumption_l_100km / 100 * prefs.fuel_price_eur_l
    s.cost_eur = fuel + prefs.parking_cost_eur
    s.travel_min = travel
    s.notes.append(f"{de(data.car.distance_km)} km, Sprit{' + Parken' if prefs.parking_cost_eur else ''} ca. {de(s.cost_eur, 2)} €")
    if data.car.estimated:
        s.notes.append("Strecke nur geschätzt (Routing nicht erreichbar)")
    if arrive_by:
        s.notes.insert(0, f"Losfahren um {arrive_by - timedelta(minutes=travel):%H:%M}")
    if data.incidents:
        s.notes.append(data.incidents[0].title + (f" – {data.incidents[0].subtitle}" if data.incidents[0].subtitle else ""))
    return _finish(s)


# ---------------------------------------------------------------------------
# Gesamtentscheidung
# ---------------------------------------------------------------------------


def evaluate(
    route: Route, prefs: Preferences, data: TravelData, departure: datetime, arrive_by: datetime | None = None
) -> Recommendation:
    """``departure`` = gewünschte Abfahrt. Ist ``arrive_by`` gesetzt, wird stattdessen
    nach der spätesten Ankunft gesucht (wie „Ankunft“ in der DB-App)."""
    scores: list[ModeScore] = []
    if Mode.BIKE.value in route.modes:
        scores.append(score_bike(data, prefs, arrive_by))
    if Mode.TRANSIT.value in route.modes:
        scores.append(score_transit(data, prefs, departure, arrive_by))
    if Mode.CAR.value in route.modes:
        scores.append(score_car(data, prefs, departure, arrive_by))

    available = [s for s in scores if s.available]
    if not available:
        return Recommendation(None, scores, "Keine Empfehlung möglich", ["Für keine Option liegen genug Daten vor."], "keine")

    # Abwägung Zeit gegen Geld – NUR für die Empfehlung. Die angezeigten Minuten
    # bleiben echte Reisezeit. Dein „Zeitwert“ (Einstellungen) sagt, wie viel Euro
    # dir eine Stunde wert ist: Bei 12 €/h lohnt es sich, für 1 € mehr bis zu
    # 5 Minuten schneller zu sein.
    vot = max(prefs.value_of_time_eur_h, 1.0)

    def balance(s: ModeScore) -> float:
        return s.total_min + s.cost_eur / vot * 60

    best = min(available, key=balance)
    fastest = min(available, key=lambda s: s.total_min)
    others = sorted((s for s in available if s is not best), key=balance)

    reasons: list[str] = []
    margin = 0.0
    if others:
        runner_up = others[0]
        margin = balance(runner_up) - balance(best)
        reasons.append(_compare(best, runner_up))
        if fastest is not best and fastest is not runner_up:
            reasons.append(_compare(best, fastest))
    else:
        reasons.append("Die einzige Option, die heute in Frage kommt")

    reasons.extend(best.notes[:2])
    for other in scores:
        if other is not best and not other.available:
            reasons.append(f"{other.mode.label}: {other.excluded_reason}")

    confidence = "klar" if margin >= CLEAR_MARGIN_MIN or not others else "knapp"
    return Recommendation(best.mode, scores, best.mode.label, reasons, confidence, margin)


def _compare(best: ModeScore, other: ModeScore) -> str:
    """Ein Satz, der Zeit und Geld gegenüberstellt, z. B.
    „3 min langsamer als Auto, aber 1,20 € günstiger“."""
    # mit den gerundeten Minuten rechnen, die auch in der App angezeigt werden
    dt = round(other.total_min) - round(best.total_min)  # > 0: best ist schneller
    dc = round(other.cost_eur, 2) - round(best.cost_eur, 2)  # > 0: best ist günstiger
    name = other.mode.label
    t = f"{abs(dt):.0f} min"
    c = f"{de(abs(dc), 2)} €"
    if abs(dt) < 1 and abs(dc) < 0.05:
        return f"Gleichauf mit {name}"
    if abs(dt) < 1:
        return f"Genauso schnell wie {name}, aber {c} günstiger" if dc > 0 else f"Genauso schnell wie {name}"
    if dt > 0 and dc >= 0.05:
        return f"{t} schneller als {name} und {c} günstiger"
    if dt > 0 and dc <= -0.05:
        return f"{t} schneller als {name} – kostet {c} mehr, das lohnt sich"
    if dt > 0:
        return f"{t} schneller als {name}"
    # best ist langsamer, gewinnt also über den Preis
    return f"{t} langsamer als {name}, spart aber {c}"


def _excluded(s: ModeScore, reason: str) -> ModeScore:
    s.available = False
    s.excluded_reason = reason
    s.parts = []
    return s


def _finish(s: ModeScore) -> ModeScore:
    s.total_min = sum(p.minutes for p in s.parts)
    return s


def _fmt(x: float) -> str:
    return f"{x:.0f}"
