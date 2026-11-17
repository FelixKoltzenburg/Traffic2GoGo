"""Gemeinsames Design: Farben, Schrift, Kopfzeile und Seitenrahmen.

Stil „Fahrschein“: klare Flächen mit scharfen Kanten, Schrift Manrope,
Farben je nach Jahreszeit (siehe ``seasons.py``) und dezente Animationen
am Seitenrand (Blätter, Schnee, Blüten, Sonne).
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from nicegui import app, ui

from .. import state
from . import seasons

APP_NAME = "Traffic2GoGo"
APP_NAME_HTML = 'Traffic<span>2GoGo</span>'
LOGO_FILE = Path(__file__).with_name("logo.svg")
LOGO_URL = "/static/logo.svg"

CSS = r"""
/* Alias-Namen, damit alle Seiten dieselben Jahreszeiten-Farben nutzen */
:root { --card: var(--paper); --soft: var(--stub); --muted: var(--mute);
  --rad: var(--a1); --auto: var(--a2); --bahn: var(--a3);
  --good: #2f8f4e; --warn: #c27a12; --bad: #c0392b; }
/* Dunkelmodus: neutrale dunkle Flächen, Akzente der Jahreszeit bleiben */
.body--dark { --bg: #121314; --paper: #1b1c1f; --ink: #ecebe8; --mute: #9b978f; --line: #2d2f33;
  --stub: #222428; --panel: #000000; --on-panel: #ecebe8; --good: #6fd08f; --bad: #ff7b6b; --warn: #f2b155; }

* { border-radius: 0; }
body { background: var(--bg) !important; color: var(--ink);
  font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; font-variant-numeric: tabular-nums; }
.nicegui-content { padding: 0 !important; }
.page { width: 100%; max-width: 1180px; margin: 0 auto; padding: 20px 20px 48px; gap: 22px; position: relative; z-index: 1; }
.card { background: var(--paper); border: 1px solid var(--line); padding: 20px; }
.muted { color: var(--mute); }
.h-title { font-size: 1.02rem; font-weight: 800; letter-spacing: -.01em; }
.kicker { font-size: .7rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--mute); }
.tiny { font-size: .78rem; }
.num { font-variant-numeric: tabular-nums; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; font-size: .75rem; font-weight: 700;
  background: var(--stub); color: var(--mute); border: 1px solid var(--line); }
.pill.good { background: transparent; color: var(--good); border-color: currentColor; }
.pill.warn { background: transparent; color: var(--warn); border-color: currentColor; }
.pill.bad  { background: transparent; color: var(--bad); border-color: currentColor; }
.pill.on-dark { background: transparent; color: var(--on-panel); border-color: rgba(255,255,255,.3); }
.q-btn, .q-field__control, .q-menu, .q-card, .q-dialog__inner > div, .q-toggle__track, .q-chip { border-radius: 0 !important; }
.q-field__label, .q-field__native, .q-field__suffix, .q-field__input { color: var(--ink) !important; }
.q-menu, .q-card { background: var(--paper); color: var(--ink); }
.footer a { color: var(--mute); }

/* Kopfzeile mit dem Ampel-Logo */
.topbar { background: var(--bg) !important; color: var(--ink); border-bottom: 1px solid var(--line); }
.brand-mark { width: 36px; height: 36px; display: block; flex-shrink: 0; }
.brand-name { font-weight: 800; font-size: 1.15rem; letter-spacing: -.02em; color: var(--ink); line-height: 1.1; }
.brand-name span { color: var(--a1); }
.navlink { padding: 7px 14px; color: var(--ink); font-weight: 600; font-size: .9rem; text-decoration: none; }
.navlink:hover { background: var(--stub); }
.navlink.active { background: var(--ink); color: var(--bg); }
.season-tag { font-size: .78rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--a1); }
.icon-btn { color: var(--mute) !important; }

/* --- Suche als Fahrschein ------------------------------------------------- */
.ticket { display: grid; grid-template-columns: minmax(0, 1fr) 260px; position: relative; width: 100%;
  background: var(--paper); filter: drop-shadow(0 10px 18px rgba(0,0,0,.08)); }
.ticket::before, .ticket::after { content: ''; position: absolute; left: calc(100% - 274px); width: 28px; height: 28px;
  background: var(--bg); border-radius: 50%; z-index: 2; }
.ticket::before { top: -14px; } .ticket::after { bottom: -14px; }
.t-main { padding: 20px 30px; border-right: 2px dashed var(--line); display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.t-stub { padding: 20px 22px; background: var(--stub); display: flex; flex-direction: column; justify-content: space-between; gap: 14px; }
.t-top { display: flex; justify-content: space-between; }
.route { display: grid; grid-template-columns: minmax(0, 1fr) 54px minmax(0, 1fr); align-items: end; gap: 6px; }
.place-label { font-size: .7rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--mute); }
.big-input .q-field__control { height: auto !important; min-height: 0 !important; padding: 0 !important;
  background: transparent !important; border-bottom: 2px solid var(--ink); }
.big-input .q-field__control::before, .big-input .q-field__control::after { display: none !important; }
.big-input .q-field__native { font-size: 1.85rem; font-weight: 800; letter-spacing: -.02em; padding: 2px 0 6px !important;
  min-height: 0 !important; line-height: 1.2; }
.big-input .q-field__append { height: auto; align-self: center; }
.place-sub { font-size: .8rem; color: var(--mute); min-height: 1.1em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.swap-btn { color: var(--a1) !important; margin-bottom: 18px; }
.meta { display: flex; align-items: flex-end; gap: 22px; flex-wrap: wrap; border-top: 1px solid var(--line); padding-top: 12px; }
.meta-field .q-field__control { height: auto !important; min-height: 0 !important; padding: 0 !important; background: transparent !important; }
.meta-field .q-field__control::before, .meta-field .q-field__control::after { display: none !important; }
.meta-field .q-field__native { font-size: 1.2rem; font-weight: 800; padding: 0 !important; min-height: 0 !important; }
.meta-field .q-field__append { height: auto; color: var(--mute); }
.seg { border: 1.5px solid var(--ink); }
.seg .q-btn { font-weight: 600; padding: 2px 12px; min-height: 30px; color: var(--ink); }
.seg .q-btn.bg-primary { background: var(--ink) !important; color: var(--bg) !important; }
.link-btn { color: var(--a1) !important; text-decoration: underline; text-underline-offset: 3px; font-weight: 600; padding: 0 4px !important; min-height: 0 !important; }
.mine { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; border-top: 1px solid var(--line); padding-top: 12px; }
.mine .route-chip, .mine .route-chip .q-chip__content { background: var(--bg) !important; color: var(--ink) !important; }
.mine .route-chip { border: 1px solid var(--line) !important;
  font-weight: 600; margin: 0 !important; }
.dt-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-weight: 700; font-size: .9rem; }
.dt-switch { flex-shrink: 0; }
.dt-switch .q-toggle__inner--truthy { color: var(--a1) !important; }
.fare { border-top: 1px dashed var(--line); border-bottom: 1px dashed var(--line); padding: 12px 0; }
.fare-price { font-size: 1.7rem; font-weight: 800; letter-spacing: -.02em; }
.go { background: var(--a1) !important; color: var(--on-a1) !important; font-weight: 800; font-size: 1rem;
  padding: 12px 10px; width: 100%; letter-spacing: .01em; }
.search-menu { position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 3000; background: var(--paper);
  color: var(--ink); border: 1.5px solid var(--ink); box-shadow: 0 14px 30px rgba(0,0,0,.14);
  max-height: 340px; overflow-y: auto; padding: 4px 0; }
.search-item { min-height: 44px; }
.search-item:hover { background: var(--stub); }

/* --- Empfehlung groß links, Alternativen klein rechts ----------------------- */
.result { display: grid; grid-template-columns: minmax(0, 1fr) 330px; gap: 22px; width: 100%; align-items: start; }
.verdict { display: grid; grid-template-columns: minmax(0, 1fr) 250px; background: var(--panel); color: var(--on-panel);
  position: relative; overflow: hidden; }
.v-main { padding: 28px 32px; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.v-main .kicker { color: var(--on-panel); opacity: .65; }
.v-word { font-size: 6.2rem; font-weight: 800; letter-spacing: -.05em; line-height: .95; color: var(--a2); margin: 8px 0 14px; }
.v-reason { display: flex; gap: 10px; font-size: .97rem; line-height: 1.4; }
.v-reason .ic { color: var(--a2); flex-shrink: 0; width: 18px; text-align: center; }
.stamp { position: absolute; right: 282px; top: 74px; border: 3px solid var(--a2); color: var(--a2); padding: 5px 12px;
  font-weight: 800; transform: rotate(-7deg); font-size: .85rem; letter-spacing: .12em; }
.v-side { background: var(--a1); color: var(--on-a1); padding: 26px 24px; display: flex; flex-direction: column;
  justify-content: space-between; gap: 18px; }
.v-side .kicker { color: var(--on-a1); opacity: .8; }
.v-time { font-size: 4.2rem; font-weight: 800; line-height: 1; letter-spacing: -.03em; margin-top: 4px; }
.v-cost { font-size: 1.7rem; font-weight: 800; }
.v-small { font-size: .82rem; opacity: .9; line-height: 1.45; }
.verdict .v-link, .verdict .v-link .q-btn__content { color: inherit !important; }
.v-link { text-decoration: underline; text-underline-offset: 3px; font-weight: 700;
  padding: 0 !important; min-height: 0 !important; justify-content: flex-start; }
.alts { display: flex; flex-direction: column; gap: 10px; }
.alt { background: var(--paper); border-left: 4px solid var(--c); padding: 11px 15px; cursor: pointer;
  display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1px 10px; transition: background .15s; }
.alt:hover { background: var(--stub); }
.alt .n { font-size: .8rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.alt .v { font-weight: 800; text-align: right; }
.alt .why { font-size: .76rem; color: var(--mute); min-width: 0; }
.alt .c { font-size: .76rem; color: var(--mute); text-align: right; }
.alt .bar { grid-column: 1 / 3; height: 4px; background: var(--line); margin-top: 6px; }
.alt .bar i { display: block; height: 4px; background: var(--c); }
.alt.off { opacity: .6; }

/* --- Details darunter ----------------------------------------------------- */
.info { display: grid; grid-template-columns: 1.2fr 1fr 1fr; width: 100%; background: var(--paper); border: 1px solid var(--line); }
.info > div { padding: 16px 22px; min-width: 0; }
.info > div + div { border-left: 1px solid var(--line); }
.conn { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; padding: 6px 0; font-size: .86rem; }
.conn-click { cursor: pointer; }
.conn-click:hover { background: var(--stub); }
.line-chip { font-size: .7rem; font-weight: 800; padding: 1px 6px; color: #fff; background: var(--a3); margin-right: 6px; }
.temp { font-size: 2.6rem; font-weight: 800; line-height: 1; }
.notice { background: var(--paper); border: 1.5px solid var(--warn); padding: 12px 16px; width: 100%; }

/* --- Weitere Seiten (Einstellungen, Verlauf) -------------------------------- */
.mode-card { border-left: 4px solid var(--accent, var(--a1)); }
.mode-badge { width: 40px; height: 40px; display: grid; place-items: center; color: var(--accent, var(--a1)); background: var(--stub); }
.big-num { font-size: 2.4rem; font-weight: 800; letter-spacing: -.03em; line-height: 1; }
.part-row { display: flex; justify-content: space-between; gap: 12px; font-size: .88rem; padding: 7px 0; border-bottom: 1px dashed var(--line); }
.part-row:last-child { border-bottom: 0; }

/* Verbindungsdetails (Dialog) */
.journey-card { overflow: hidden; }
.journey-body { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); border-top: 1px solid var(--line); }
.journey-steps { padding: 16px 20px 20px; max-height: 62vh; overflow-y: auto; }
.journey-map { height: 100%; min-height: 420px; border-left: 1px solid var(--line); }
.jleg { display: grid; grid-template-columns: 46px 16px minmax(0, 1fr); column-gap: 10px; align-items: start; }
.jtime { font-weight: 800; font-size: .9rem; text-align: right; padding-top: 1px; }
.jdot { width: 14px; height: 14px; border-radius: 50% !important; border: 3px solid var(--line-c, var(--mute));
  background: var(--paper); justify-self: center; margin-top: 3px; }
.jbar { width: 4px; background: var(--line-c, var(--mute)); justify-self: center; min-height: 54px; }
.jbar.dotted { background: none; width: 0; border-left: 3px dotted var(--mute); min-height: 36px; }
.jtext { font-size: .9rem; padding-bottom: 2px; min-width: 0; }
.jmid { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 8px 0; align-self: center; }
.jmid .tiny { flex-basis: 100%; }
.track { font-size: .72rem; font-weight: 700; padding: 1px 6px; background: var(--stub); border: 1px solid var(--line);
  color: var(--mute); white-space: nowrap; }
.walk-exp .q-item { padding: 2px 0; min-height: 32px; font-size: .82rem; color: var(--mute); }
.walk-exp .q-expansion-item__content { padding-left: 8px; }

/* --- Jahreszeiten-Animationen am Rand -------------------------------------- */
.season-layer { position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden; }
.pt { position: absolute; top: -40px; animation-name: fall; animation-timing-function: linear; animation-iteration-count: infinite; }
.pt.leaf { animation-name: leaf; }
.pt.snow { color: #cfe9ff; opacity: .85; animation-name: snow; }
.body--light .pt.snow { color: #9cc4e4; }
.pt.petal { background: var(--a2); border-radius: 60% 0 60% 0 !important; opacity: .85; animation-name: petal; }
.pt.spark { top: auto; background: var(--a2); border-radius: 50% !important; animation: twinkle 3.5s ease-in-out infinite; }
.sun-glow { position: absolute; right: -90px; top: -90px; width: 260px; height: 260px; border-radius: 50% !important;
  background: radial-gradient(circle, var(--a2) 0 28%, color-mix(in srgb, var(--a2) 35%, transparent) 30% 55%, transparent 58%);
  animation: pulse 6s ease-in-out infinite; }
@keyframes leaf { 0% { transform: translate(0, 0) rotate(0deg); } 25% { transform: translate(18px, 25vh) rotate(90deg); }
  50% { transform: translate(-14px, 50vh) rotate(180deg); } 75% { transform: translate(16px, 75vh) rotate(270deg); }
  100% { transform: translate(0, 108vh) rotate(360deg); } }
@keyframes snow { 0% { transform: translate(0, 0); } 50% { transform: translate(10px, 54vh); } 100% { transform: translate(-6px, 108vh); } }
@keyframes petal { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-40px, 108vh) rotate(300deg); } }
@keyframes twinkle { 0%, 100% { opacity: .15; transform: scale(.7); } 50% { opacity: .9; transform: scale(1.15); } }
@keyframes pulse { 0%, 100% { transform: scale(1); opacity: .85; } 50% { transform: scale(1.07); opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .season-layer { display: none; } }

.fade-in { animation: fadeUp .4s ease both; }
@keyframes fadeUp { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

/* --- Handy ---------------------------------------------------------------- */
@media (max-width: 900px) {
  .ticket, .result, .verdict, .info { grid-template-columns: 1fr; }
  .ticket::before, .ticket::after { display: none; }
  .t-main { border-right: 0; border-bottom: 2px dashed var(--line); padding: 18px; }
  .route { grid-template-columns: 1fr; }
  .swap-btn { margin: 0; justify-self: start; }
  .stamp { left: auto; right: 18px; top: 104px; }
  .v-word { font-size: 4.2rem; }
  .info > div + div { border-left: 0; border-top: 1px solid var(--line); }
  .journey-body { grid-template-columns: 1fr; }
  .journey-map { min-height: 260px; border-left: 0; border-top: 1px solid var(--line); }
  .season-layer { opacity: .5; }
}

/* Quasar setzt Farb-Klassen (bg-primary, text-primary) mit !important in einer späten Ebene.
   Damit unsere Farben gewinnen, stehen diese Regeln in derselben Ebene – mit höherer Spezifität. */
@layer quasar_importants {
  .meta .seg .q-btn.bg-primary, .meta .seg .q-btn.bg-primary .q-btn__content { background: var(--ink) !important; color: var(--bg) !important; }
  .t-stub .go { background: var(--a1) !important; color: var(--on-a1) !important; }
  .mine .route-chip, .mine .route-chip .q-chip__content { background: var(--bg) !important; color: var(--ink) !important; }
  .verdict .v-link, .verdict .v-link .q-btn__content { color: inherit !important; }
  .t-main .link-btn, .alts .link-btn, .notice .link-btn { color: var(--a1) !important; }
}
"""


def html(content: str):
    """Eigenes HTML einfügen. ``sanitize=False`` ist bei älteren NiceGUI-Versionen
    (z. B. unter Python 3.9) Pflicht. Wichtig: Texte aus fremden Quellen vorher
    mit ``html.escape`` entschärfen (siehe ``_esc`` in dashboard.py)."""
    return ui.html(content, sanitize=False)


def setup() -> None:
    """Einmalig beim Start: Schrift, Grund-CSS und Logo für alle Seiten."""
    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">',
        shared=True,
    )
    ui.add_css(CSS, shared=True)
    if LOGO_FILE.is_file():  # fehlt die Datei, startet die App trotzdem (nur ohne Logo)
        app.add_static_file(local_file=LOGO_FILE, url_path=LOGO_URL)


def season() -> seasons.Season:
    return seasons.current(state.settings().season)


@contextmanager
def frame(active: str):
    """Rahmen jeder Seite: Jahreszeiten-Farben, Kopfzeile, Inhalt, Animationen."""
    s = state.settings()
    sea = season()
    c = sea.colors
    ui.add_css(seasons.css_vars(sea))  # Farben der aktuellen Jahreszeit (nur für diese Seite)
    ui.colors(primary=c["ink"], secondary=c["a1"], accent=c["a2"], positive="#2f8f4e", negative="#c0392b")
    dark = ui.dark_mode(value=app.storage.user.get("dark", False))
    if s.animations:
        html(seasons.particles_html(sea))

    with ui.header().classes("topbar px-5 py-3").style("box-shadow:none"):
        with ui.row().classes("w-full max-w-[1180px] mx-auto items-center no-wrap gap-3"):
            with ui.link(target="/").classes("no-underline flex flex-nowrap items-center gap-3 shrink-0"):
                ui.image(LOGO_URL).classes("brand-mark")
                with ui.column().classes("gap-0"):
                    html(f'<div class="brand-name">{APP_NAME_HTML}</div>')
                    ui.label("Auto · Bahn · Rad").classes("tiny muted leading-tight max-sm:hidden")
            ui.space()
            with ui.row().classes("gap-1 items-center max-sm:hidden"):
                for path, label in (("/", "Heute"), ("/verlauf", "Verlauf"), ("/einstellungen", "Einstellungen")):
                    ui.link(label, path).classes("navlink" + (" active" if path == active else ""))
            ui.space()
            ui.label(f"{sea.icon} {sea.label}").classes("season-tag max-sm:hidden")

            def toggle_dark():
                dark.value = not dark.value
                app.storage.user["dark"] = dark.value
                btn.props(f"icon={'light_mode' if dark.value else 'dark_mode'}")

            btn = ui.button(icon="light_mode" if dark.value else "dark_mode", on_click=toggle_dark).props(
                "flat round dense"
            ).classes("icon-btn").tooltip("Hell/Dunkel")
            with ui.button(icon="menu").props("flat round dense").classes("sm:hidden icon-btn"):
                with ui.menu():
                    ui.menu_item("Heute", lambda: ui.navigate.to("/"))
                    ui.menu_item("Verlauf", lambda: ui.navigate.to("/verlauf"))
                    ui.menu_item("Einstellungen", lambda: ui.navigate.to("/einstellungen"))

    with ui.column().classes("page"):
        yield
        html(
            '<div class="footer tiny muted" style="margin-top:8px">'
            'Wetter: <a href="https://open-meteo.com" target="_blank">Open-Meteo</a> (CC BY 4.0) · '
            'Routing: <a href="https://routing.openstreetmap.de" target="_blank">FOSSGIS-OSRM</a>, '
            '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>-Mitwirkende · '
            'Bahn &amp; Bus: <a href="https://transitous.org/sources/" target="_blank">Transitous</a> · '
            'Verkehr: <a href="https://autobahn.api.bund.dev" target="_blank">Autobahn GmbH</a>'
            "</div>"
        )
