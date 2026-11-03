"""Zeit-Hilfen. Alles wird in deutscher Ortszeit gerechnet – auch wenn der
Server (z. B. in der Cloud) auf UTC läuft."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")


def now() -> datetime:
    """Aktuelle Ortszeit ohne Zeitzonen-Anhang (einfacher zu vergleichen)."""
    return datetime.now(TZ).replace(tzinfo=None)


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(TZ).replace(tzinfo=None)


def aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt


def next_departure(hhmm: str, weekdays: list[int], ref: datetime | None = None) -> datetime:
    """Nächster passender Abfahrtszeitpunkt. Ist die Zeit heute schon vorbei
    (oder heute kein Pendeltag), wird der nächste Pendeltag genommen."""
    ref = ref or now()
    h, m = map(int, hhmm.split(":"))
    for add in range(0, 8):
        d: date = ref.date() + timedelta(days=add)
        cand = datetime.combine(d, time(h, m))
        if (not weekdays or d.weekday() in weekdays) and cand >= ref - timedelta(minutes=10):
            return cand
    return datetime.combine(ref.date() + timedelta(days=1), time(h, m))


WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def day_label(dt: datetime, ref: datetime | None = None) -> str:
    ref = ref or now()
    diff = (dt.date() - ref.date()).days
    if diff == 0:
        return "heute"
    if diff == 1:
        return "morgen"
    return f"{WEEKDAYS[dt.weekday()]}, {dt:%d.%m.}"
