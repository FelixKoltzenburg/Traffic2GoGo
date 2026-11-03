"""WMO-Wettercodes (von Open-Meteo genutzt) auf Deutsch."""

WMO = {
    0: ("Klar", "wb_sunny"),
    1: ("Überwiegend klar", "wb_sunny"),
    2: ("Teils bewölkt", "wb_cloudy"),
    3: ("Bedeckt", "cloud"),
    45: ("Nebel", "blur_on"),
    48: ("Reifnebel", "blur_on"),
    51: ("Leichter Niesel", "grain"),
    53: ("Niesel", "grain"),
    55: ("Starker Niesel", "grain"),
    56: ("Gefrierender Niesel", "ac_unit"),
    57: ("Gefrierender Niesel", "ac_unit"),
    61: ("Leichter Regen", "umbrella"),
    63: ("Regen", "umbrella"),
    65: ("Starker Regen", "umbrella"),
    66: ("Gefrierender Regen", "ac_unit"),
    67: ("Gefrierender Regen", "ac_unit"),
    71: ("Leichter Schneefall", "ac_unit"),
    73: ("Schneefall", "ac_unit"),
    75: ("Starker Schneefall", "ac_unit"),
    77: ("Schneegriesel", "ac_unit"),
    80: ("Leichte Schauer", "umbrella"),
    81: ("Schauer", "umbrella"),
    82: ("Heftige Schauer", "flash_on"),
    85: ("Schneeschauer", "ac_unit"),
    86: ("Starke Schneeschauer", "ac_unit"),
    95: ("Gewitter", "flash_on"),
    96: ("Gewitter mit Hagel", "flash_on"),
    99: ("Schweres Gewitter mit Hagel", "flash_on"),
}

THUNDER = {95, 96, 99}
ICE_OR_SNOW = {56, 57, 66, 67, 71, 73, 75, 77, 85, 86}


def describe(code: int) -> str:
    return WMO.get(code, ("Unbekannt", "help"))[0]


def icon(code: int) -> str:
    return WMO.get(code, ("Unbekannt", "help"))[1]
