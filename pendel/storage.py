"""Speichern und Laden von Einstellungen und Verlauf als JSON-Dateien.

Bewusst ohne Datenbank: JSON reicht für eine Person völlig aus und man kann
die Dateien im Editor ansehen. (Ausbaustufe: SQLite mit SQLModel.)
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .models import Place, Preferences, Recommendation, Route, Settings

DATA_DIR = Path(os.environ.get("PENDEL_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.json"


def default_settings() -> Settings:
    """Beispielstrecke, damit die App sofort etwas anzeigt."""
    home = Place("Zuhause (Bad Cannstatt)", 48.8047, 9.2149)
    dhbw = Place("DHBW Stuttgart, Rotebühlplatz", 48.7757, 9.1718)
    work = Place("Praxispartner (Leinfelden-Echterdingen)", 48.6925, 9.1640)
    return Settings(
        routes=[
            Route(id="r1", name="Zur DHBW", origin=home, destination=dhbw, departure="07:45"),
            Route(id="r2", name="Zum Praxispartner", origin=home, destination=work, departure="07:15"),
        ],
        user_name="Felix",
    )


def _route_from_dict(d: dict) -> Route:
    d = dict(d)
    d["origin"] = Place(**d["origin"])
    d["destination"] = Place(**d["destination"])
    return Route(**d)


def load_settings() -> Settings:
    if not SETTINGS_FILE.exists():
        s = default_settings()
        save_settings(s)
        return s
    raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    known_prefs = Preferences.__dataclass_fields__.keys()
    prefs = Preferences(**{k: v for k, v in raw.get("prefs", {}).items() if k in known_prefs})
    other = {k: v for k, v in raw.items() if k not in ("routes", "prefs") and k in Settings.__dataclass_fields__}
    return Settings(routes=[_route_from_dict(r) for r in raw.get("routes", [])], prefs=prefs, **other)


def save_settings(s: Settings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_FILE)  # atomar ersetzen, damit nie eine halbe Datei entsteht


def new_route_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Verlauf
# ---------------------------------------------------------------------------


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))


def add_history(route: Route, rec: Recommendation, weather_text: str, day: date | None = None) -> None:
    """Speichert die Empfehlung eines Tages (pro Strecke höchstens ein Eintrag pro Tag)."""
    day = day or date.today()
    entries = [e for e in load_history() if not (e["date"] == day.isoformat() and e["route_id"] == route.id)]
    entries.append(
        {
            "date": day.isoformat(),
            "route_id": route.id,
            "route_name": route.name,
            "best": rec.best.value if rec.best else None,
            "confidence": rec.confidence,
            "weather": weather_text,
            "scores": {s.mode.value: round(s.felt_min, 1) for s in rec.scores if s.available},
        }
    )
    entries.sort(key=lambda e: e["date"])
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(entries[-400:], ensure_ascii=False, indent=2), encoding="utf-8")
