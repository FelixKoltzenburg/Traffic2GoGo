"""Gemeinsames Design: Farben, Schrift, Kopfzeile und Seitenrahmen."""
from __future__ import annotations

from contextlib import contextmanager

from nicegui import app, ui

CSS = r"""
:root {
  --bg: #f3f5fa; --card: #ffffff; --ink: #0f172a; --muted: #64748b; --line: #e5e8f0;
  --soft: #f7f8fc; --shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.06);
  --rad: #16a34a; --bahn: #2563eb; --auto: #ea580c; --warn: #d97706; --bad: #dc2626; --good: #16a34a;
}
.body--dark {
  --bg: #0b1020; --card: #131a2e; --ink: #e8ecf6; --muted: #94a3b8; --line: #243049;
  --soft: #182038; --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
}
body { background: var(--bg) !important; color: var(--ink);
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }
.nicegui-content { padding: 0 !important; }
.page { width: 100%; max-width: 1180px; margin: 0 auto; padding: 24px 20px 48px; gap: 20px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 20px;
  box-shadow: var(--shadow); padding: 20px; }
.muted { color: var(--muted); }
.h-title { font-size: 1.05rem; font-weight: 700; letter-spacing: -.01em; }
.tiny { font-size: .78rem; }
.num { font-variant-numeric: tabular-nums; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px;
  font-size: .78rem; font-weight: 600; background: var(--soft); color: var(--muted); border: 1px solid var(--line); }
.pill.good { background: rgba(22,163,74,.12); color: var(--good); border-color: transparent; }
.pill.warn { background: rgba(217,119,6,.14); color: var(--warn); border-color: transparent; }
.pill.bad  { background: rgba(220,38,38,.12); color: var(--bad); border-color: transparent; }
.pill.on-dark { background: rgba(255,255,255,.18); color: #fff; border-color: rgba(255,255,255,.25); }

/* Kopfzeile */
.topbar { background: rgba(255,255,255,.75); backdrop-filter: blur(12px); border-bottom: 1px solid var(--line); }
.body--dark .topbar { background: rgba(11,16,32,.75); }
.brand-mark { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; color: #fff;
  background: linear-gradient(135deg, var(--rad), var(--bahn) 55%, var(--auto)); }
.navlink { padding: 6px 12px; border-radius: 10px; color: var(--muted); font-weight: 600; font-size: .9rem;
  text-decoration: none; transition: background .15s, color .15s; }
.navlink:hover { background: var(--soft); color: var(--ink); }
.navlink.active { background: var(--soft); color: var(--ink); }

/* Hero-Karte mit der Empfehlung */
.hero { position: relative; overflow: hidden; border-radius: 26px; padding: 28px; color: #fff;
  box-shadow: 0 18px 40px -18px var(--accent); }
.hero::after { content: ''; position: absolute; right: -80px; top: -80px; width: 320px; height: 320px;
  border-radius: 50%; background: rgba(255,255,255,.10); }
.hero::before { content: ''; position: absolute; right: 90px; bottom: -120px; width: 260px; height: 260px;
  border-radius: 50%; background: rgba(255,255,255,.07); }
.hero-icon { width: 84px; height: 84px; border-radius: 24px; background: rgba(255,255,255,.18);
  display: grid; place-items: center; border: 1px solid rgba(255,255,255,.3); }
.hero-mode { font-size: 3.2rem; font-weight: 800; letter-spacing: -.03em; line-height: 1; }
.hero-reason { display: flex; gap: 8px; align-items: flex-start; font-size: .95rem; line-height: 1.35; }
.hero-panel { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22); border-radius: 18px;
  padding: 16px; position: relative; z-index: 1; }
.bar-track { height: 10px; border-radius: 999px; background: rgba(255,255,255,.18); overflow: hidden; }
.bar-fill { height: 100%; border-radius: 999px; background: #fff; transition: width .6s ease; }
.fade-in { animation: fadeUp .45s ease both; }
.fade-in.d1 { animation-delay: .06s; } .fade-in.d2 { animation-delay: .12s; } .fade-in.d3 { animation-delay: .18s; }
@keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* Verkehrsmittel-Karten */
.mode-card { border-top: 4px solid var(--accent); transition: transform .15s ease; }
.mode-card:hover { transform: translateY(-2px); }
.mode-card.winner { outline: 2px solid var(--accent); outline-offset: -1px; }
.mode-card.off { opacity: .62; border-top-color: var(--line); }
.mode-badge { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent); }
.big-num { font-size: 2.4rem; font-weight: 800; letter-spacing: -.03em; line-height: 1; }
.part-row { display: flex; justify-content: space-between; gap: 12px; font-size: .86rem; padding: 6px 0;
  border-bottom: 1px dashed var(--line); }
.part-row:last-child { border-bottom: 0; }
.plus { color: var(--bad); } .minus { color: var(--good); }

/* Listen */
.conn { display: grid; grid-template-columns: 64px 1fr auto; gap: 12px; align-items: center; padding: 10px 0;
  border-bottom: 1px solid var(--line); }
.conn:last-child { border-bottom: 0; }
.line-chip { font-size: .75rem; font-weight: 700; padding: 2px 7px; border-radius: 6px; color: #fff; background: var(--bahn); }
.line-chip.S { background: #16a34a; } .line-chip.U { background: #2563eb; } .line-chip.B { background: #c026d3; }
.line-chip.R { background: #64748b; }
.incident { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.incident:last-child { border-bottom: 0; }
.wx-stat { background: var(--soft); border-radius: 14px; padding: 10px 12px; }
.q-field__label, .q-field__native, .q-field__suffix { color: var(--ink) !important; }
.footer a { color: var(--muted); }
.q-dialog .q-card { background: var(--card); color: var(--ink); }
"""


def setup() -> None:
    """Einmalig beim Start: Schrift, Farben und CSS für alle Seiten."""
    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">',
        shared=True,
    )
    ui.add_css(CSS, shared=True)


@contextmanager
def frame(active: str, demo: bool = False):
    """Rahmen jeder Seite: Kopfzeile + zentrierter Inhaltsbereich."""
    ui.colors(primary="#2563eb", secondary="#16a34a", accent="#ea580c", positive="#16a34a", negative="#dc2626")
    dark = ui.dark_mode(value=app.storage.user.get("dark", False))

    with ui.header().classes("topbar text-[color:var(--ink)] px-5 py-3").style("box-shadow:none"):
        with ui.row().classes("w-full max-w-[1180px] mx-auto items-center no-wrap gap-3"):
            with ui.link(target="/").classes("no-underline flex flex-nowrap items-center gap-3 shrink-0"):
                with ui.element("div").classes("brand-mark"):
                    ui.icon("alt_route").classes("text-xl")
                with ui.column().classes("gap-0"):
                    ui.label("Pendel-Berater").classes("font-extrabold text-[1.05rem] text-[color:var(--ink)] leading-tight whitespace-nowrap")
                    ui.label("Auto · Bahn · Rad").classes("tiny muted leading-tight max-sm:hidden")
            ui.space()
            with ui.row().classes("gap-1 items-center max-sm:hidden"):
                for path, label in (("/", "Heute"), ("/verlauf", "Verlauf"), ("/einstellungen", "Einstellungen")):
                    ui.link(label, path).classes("navlink" + (" active" if path == active else ""))
            if demo:
                ui.html('<span class="pill warn"><span class="material-icons" style="font-size:15px">science</span>Demo</span>')

            def toggle_dark():
                dark.value = not dark.value
                app.storage.user["dark"] = dark.value
                btn.props(f"icon={'light_mode' if dark.value else 'dark_mode'}")

            btn = ui.button(icon="light_mode" if dark.value else "dark_mode", on_click=toggle_dark).props(
                "flat round dense"
            ).classes("text-[color:var(--muted)]").tooltip("Hell/Dunkel")
            with ui.button(icon="menu").props("flat round dense").classes("sm:hidden text-[color:var(--muted)]"):
                with ui.menu():
                    ui.menu_item("Heute", lambda: ui.navigate.to("/"))
                    ui.menu_item("Verlauf", lambda: ui.navigate.to("/verlauf"))
                    ui.menu_item("Einstellungen", lambda: ui.navigate.to("/einstellungen"))

    with ui.column().classes("page"):
        yield
        ui.html(
            '<div class="footer tiny muted" style="margin-top:8px">'
            'Wetter: <a href="https://open-meteo.com" target="_blank">Open-Meteo</a> (CC BY 4.0) · '
            'Routing: <a href="https://routing.openstreetmap.de" target="_blank">FOSSGIS-OSRM</a>, '
            '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>-Mitwirkende · '
            'Bahn: <a href="https://v6.db.transport.rest" target="_blank">db.transport.rest</a> · '
            'Verkehr: <a href="https://autobahn.api.bund.dev" target="_blank">Autobahn GmbH</a>'
            "</div>"
        )
