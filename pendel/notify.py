"""Push-Nachrichten über ntfy.sh (kostenlos, ohne Konto).

Doku: https://docs.ntfy.sh/publish/
"""
from __future__ import annotations

from .services.http import client


async def send_push(topic: str, title: str, message: str, tags: str = "") -> None:
    # Titel und Tags als URL-Parameter – HTTP-Header dürften keine Umlaute enthalten.
    params = {"title": title}
    if tags:
        params["tags"] = tags
    resp = await client().post(f"https://ntfy.sh/{topic}", params=params, content=message.encode("utf-8"))
    resp.raise_for_status()
