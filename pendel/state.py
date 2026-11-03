"""Globaler Zustand der App (eine Person = ein Einstellungs-Objekt)."""
from __future__ import annotations

import hmac
import os

from nicegui import app, ui

from . import storage
from .models import Settings
from .services import http

_settings: Settings | None = None
_last: dict[str, object] = {}  # route_id -> letztes Ergebnis

PASSWORD = os.environ.get("PENDEL_PASSWORD", "")


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = storage.load_settings()
    return _settings


def save() -> None:
    storage.save_settings(settings())


def clear_cache() -> None:
    http._cache.clear()


def remember(result) -> None:
    _last[result.route.id] = result


def check_login() -> bool:
    """Optionaler Passwortschutz für den Betrieb auf einem öffentlichen Server.
    Aktiv, sobald die Umgebungsvariable PENDEL_PASSWORD gesetzt ist."""
    if not PASSWORD or app.storage.user.get("auth"):
        return True
    ui.navigate.to("/login")
    return False


def try_login(pw: str) -> bool:
    ok = bool(PASSWORD) and hmac.compare_digest(pw.encode(), PASSWORD.encode())
    if ok:
        app.storage.user["auth"] = True
    return ok
