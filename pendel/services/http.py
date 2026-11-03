"""Gemeinsamer HTTP-Client mit kleinem Zwischenspeicher (Cache).

Warum ein Cache? Öffentliche APIs sind kostenlos, aber begrenzt. Wer die
Seite fünfmal neu lädt, soll die Server nicht fünfmal fragen.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

USER_AGENT = "PendelBerater/1.0 (privates Lernprojekt; Python/httpx)"
_client: httpx.AsyncClient | None = None
_cache: dict[str, tuple[float, Any]] = {}


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=6.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
    return _client


async def get_json(url: str, params: dict | None = None, ttl: int = 300) -> Any:
    """GET-Anfrage, Antwort als JSON. ``ttl`` = Sekunden, die das Ergebnis gültig bleibt."""
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    resp = await client().get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    _cache[key] = (time.time(), data)
    if len(_cache) > 500:  # Speicher begrenzen: älteste Einträge entfernen
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
            _cache.pop(k, None)
    return data


async def post_text(url: str, text: str, headers: dict | None = None) -> None:
    resp = await client().post(url, content=text.encode("utf-8"), headers=headers or {})
    resp.raise_for_status()
