"""Jahreszeiten: Farben und Rand-Animationen wechseln automatisch mit dem Datum.

Frühling 20.3.–20.6. · Sommer 21.6.–22.9. · Herbst 23.9.–20.12. · Winter 21.12.–19.3.
In den Einstellungen kann man eine Jahreszeit auch fest wählen (praktisch zum Vorführen).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from .. import timeutil


@dataclass(frozen=True)
class Season:
    key: str
    label: str
    icon: str  # Symbol für Kopfzeile und Aufzählungen
    colors: dict[str, str]
    particle: str  # "petal" | "sun" | "leaf" | "snow"


# Farb-Rollen:
#   bg/paper/ink/mute/line/stub  – Flächen, Text, Linien, Ticket-Abschnitt
#   panel/on-panel               – dunkle Empfehlungsfläche und Text darauf
#   a1/on-a1                     – Hauptakzent (Buttons, Zeit-Block) und Text darauf
#   a2, a3                       – zweiter und dritter Akzent (großes Wort, Balken)
SEASONS: dict[str, Season] = {
    "fruehling": Season("fruehling", "Frühling", "✿", {
        "bg": "#f1f7ef", "paper": "#fbfefb", "ink": "#1d2b20", "mute": "#6d8576", "line": "#d5e6d6",
        "stub": "#e3f0e5", "panel": "#1d2b20", "on-panel": "#fbfefb",
        "a1": "#3a9d5d", "on-a1": "#ffffff", "a2": "#f4a7bb", "a3": "#6aaed6",
    }, "petal"),
    "sommer": Season("sommer", "Sommer", "☀", {
        "bg": "#fff8e7", "paper": "#fffdf6", "ink": "#1a1408", "mute": "#7a6a4a", "line": "#f1e2bd",
        "stub": "#fbedc9", "panel": "#1a1408", "on-panel": "#fffdf6",
        "a1": "#ff7a2f", "on-a1": "#ffffff", "a2": "#ffd34d", "a3": "#16c2a3",
    }, "sun"),
    "herbst": Season("herbst", "Herbst", "🍂", {
        "bg": "#f6efe4", "paper": "#fffaf2", "ink": "#2a1d14", "mute": "#8a7262", "line": "#e5d6bf",
        "stub": "#efe2cc", "panel": "#2a1d14", "on-panel": "#fffaf2",
        "a1": "#b4471f", "on-a1": "#ffffff", "a2": "#d99a2b", "a3": "#5d6b3a",
    }, "leaf"),
    "winter": Season("winter", "Winter", "❄", {
        "bg": "#0b1626", "paper": "#12213a", "ink": "#e8f1fb", "mute": "#8aa2c0", "line": "#22344f",
        "stub": "#0f1d31", "panel": "#050c17", "on-panel": "#e8f1fb",
        "a1": "#9fd8ff", "on-a1": "#0b1626", "a2": "#9fd8ff", "a3": "#ffb86b",
    }, "snow"),
}

CHOICES = {"auto": "Automatisch (nach Datum)", **{k: s.label for k, s in SEASONS.items()}}


def season_for(day: date) -> str:
    md = (day.month, day.day)
    if (3, 20) <= md <= (6, 20):
        return "fruehling"
    if (6, 21) <= md <= (9, 22):
        return "sommer"
    if (9, 23) <= md <= (12, 20):
        return "herbst"
    return "winter"


def current(choice: str = "auto") -> Season:
    key = choice if choice in SEASONS else season_for(timeutil.now().date())
    return SEASONS[key]


def css_vars(season: Season) -> str:
    """CSS-Variablen der Jahreszeit für :root."""
    return ":root{" + "".join(f"--{k}:{v};" for k, v in season.colors.items()) + "}"


# ---------------------------------------------------------------------------
# Rand-Animationen
# ---------------------------------------------------------------------------

LEAF = (
    '<svg viewBox="0 0 24 24" width="{s}" height="{s}"><path d="M12 2C7 6 4 10 4 14a8 8 0 0 0 16 0c0-4-3-8-8-12Z" '
    'fill="{c}"/><path d="M12 6v16" stroke="rgba(0,0,0,.25)" stroke-width="1"/></svg>'
)


def particles_html(season: Season, count: int = 14) -> str:
    """Partikel nur links und rechts am Rand. Zufällig, aber pro Tag gleich (ruhiges Bild)."""
    rnd = random.Random(f"{season.key}-{date.today()}")
    c = season.colors
    items: list[str] = []
    if season.particle == "sun":
        items.append('<div class="sun-glow"></div>')
    for i in range(count):
        side = "left" if i % 2 == 0 else "right"
        pos = rnd.uniform(0.5, 4.5)  # vw vom Rand
        delay = rnd.uniform(0, 18)
        dur = rnd.uniform(14, 26)
        size = rnd.randint(14, 26)
        style = f"{side}:{pos:.1f}vw;animation-delay:-{delay:.1f}s;animation-duration:{dur:.1f}s"
        if season.particle == "leaf":
            color = rnd.choice([c["a1"], c["a2"], c["a3"], "#8e3b1d"])
            inner = LEAF.format(s=size, c=color)
            items.append(f'<span class="pt leaf" style="{style}">{inner}</span>')
        elif season.particle == "snow":
            ch = rnd.choice(["❄", "❅", "✻", "•"])
            items.append(f'<span class="pt snow" style="{style};font-size:{size - 4}px">{ch}</span>')
        elif season.particle == "petal":
            items.append(f'<span class="pt petal" style="{style};width:{size // 2}px;height:{int(size * 0.7)}px"></span>')
        else:  # Sommer: funkelnde Lichtpunkte
            top = rnd.uniform(5, 95)
            items.append(
                f'<span class="pt spark" style="{side}:{pos:.1f}vw;top:{top:.0f}vh;'
                f'animation-delay:-{delay:.1f}s;width:{size // 3}px;height:{size // 3}px"></span>'
            )
    return '<div class="season-layer" aria-hidden="true">' + "".join(items) + "</div>"
