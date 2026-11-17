"""Traffic2GoGo – Startdatei.

Starten:   python main.py
Dann im Browser öffnen:  http://localhost:8080

Umgebungsvariablen (optional):
  PORT              Port des Webservers (Standard 8080)
  PENDEL_PASSWORD   Passwortschutz, z. B. wenn die App auf einem Server läuft
  STORAGE_SECRET    Geheimnis für Browser-Sitzungen (auf dem Server setzen!)
  PENDEL_DATA_DIR   Ordner für settings.json und history.json
"""
import logging
import os

from nicegui import app, background_tasks, ui

from pendel import scheduler, state
from pendel.ui import dashboard, history_page, settings_page, theme

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

theme.setup()
dashboard.register()
settings_page.register()
history_page.register()


@ui.page("/login")
def login_page():
    if not state.PASSWORD:
        ui.navigate.to("/")
        return
    ui.add_css("body{display:grid;place-items:center;min-height:100vh}")
    with ui.column().classes("card w-[360px] max-w-[92vw] gap-4 items-stretch mt-[18vh] mx-auto"):
        with ui.row().classes("items-center gap-3"):
            ui.image(theme.LOGO_URL).classes("brand-mark")
            theme.html(f'<div class="brand-name">{theme.APP_NAME_HTML}</div>')
        pw = ui.input("Passwort", password=True, password_toggle_button=True).props("outlined dense autofocus")

        def go():
            if state.try_login(pw.value or ""):
                ui.navigate.to("/")
            else:
                ui.notify("Falsches Passwort", type="negative")

        pw.on("keydown.enter", go)
        ui.button("Anmelden", on_click=go).props("unelevated rounded no-caps")


app.on_startup(lambda: background_tasks.create(scheduler.run_forever(), name="morning-scheduler"))

# Render setzt die Variable RENDER automatisch. Lokal ist sie nicht gesetzt.
ON_SERVER = bool(os.environ.get("RENDER") or os.environ.get("PORT"))

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title=theme.APP_NAME,
        favicon=theme.LOGO_FILE,
        language="de",
        host=os.environ.get("HOST", "0.0.0.0" if ON_SERVER else "127.0.0.1"),
        port=int(os.environ.get("PORT", 8080)),
        storage_secret=os.environ.get("STORAGE_SECRET", "bitte-auf-dem-server-aendern"),
        reload=os.environ.get("RELOAD", "0") == "1",
        show=not ON_SERVER,  # lokal öffnet sich der Browser von selbst
    )
