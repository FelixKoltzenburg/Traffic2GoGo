# Pendel-Berater 🚲🚆🚗

Ein Web-Dashboard komplett in Python: Jeden Morgen bekommst du eine Empfehlung, ob für deine Strecke
heute **Rad, Bahn oder Auto** am besten ist, mit Begründung.

## Schnellstart (lokal)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Dann im Browser **http://localhost:8080** öffnen.
Die App startet im **Demo-Modus** mit Beispieldaten. Unter *Einstellungen* kannst du ihn ausschalten,
dann werden die echten APIs abgefragt.

## Tests

```bash
pytest -q
```

## Projektaufbau

```
main.py                  Startdatei (Webserver, Login, Scheduler)
pendel/
  models.py              Datenmodelle (dataclasses)
  decision.py            Entscheidungslogik („gefühlte Minuten“)
  engine.py              holt alle Daten parallel und ruft die Logik auf
  demo.py                Demo-Daten und Szenarien
  scheduler.py           Morgen-Job: Verlauf speichern + Push
  storage.py             Einstellungen & Verlauf als JSON
  notify.py              Push-Nachrichten über ntfy.sh
  timeutil.py            Zeitzonen-Hilfen (Europe/Berlin)
  services/              eine Datei pro API
    weather.py           Open-Meteo
    transit.py           db.transport.rest
    routing.py           OSRM (routing.openstreetmap.de)
    traffic.py           Autobahn GmbH
    geocode.py           Photon (Adresssuche)
  ui/                    Seiten der Weboberfläche (NiceGUI)
tests/                   pytest-Tests
```

## Auf einen Server bringen

**Variante A: Docker (z. B. Hetzner, Render, Railway, Fly.io)**

```bash
docker build -t pendel-berater .
docker run -d -p 8080:8080 -v pendel-data:/data \
  -e PENDEL_PASSWORD=dein-passwort -e STORAGE_SECRET=langer-zufallswert \
  pendel-berater
```

**Variante B: direkt auf einem Linux-Server** mit `python main.py` als systemd-Dienst.

Wichtig für den Server:

- `PENDEL_PASSWORD` setzen, sonst kann jeder mit dem Link deine Einstellungen sehen.
- `STORAGE_SECRET` auf einen langen Zufallswert setzen.
- Der Scheduler läuft nur, solange die App läuft. Bei Diensten mit „Sleep“ (kostenlose Render-Stufe)
  wacht die App morgens nicht von selbst auf. Ein kleiner VPS ist dafür besser geeignet.

## Datenquellen

| Quelle | Wofür | Schlüssel nötig? |
|---|---|---|
| [Open-Meteo](https://open-meteo.com) | Wetter (CC BY 4.0) | nein |
| [db.transport.rest](https://v6.db.transport.rest) | Bahn-Verbindungen, Verspätungen (max. 100 Anfragen/min) | nein |
| [routing.openstreetmap.de](https://routing.openstreetmap.de) | Auto- und Radrouten (© OpenStreetMap) | nein |
| [Autobahn-API](https://autobahn.api.bund.dev) | Staus, Sperrungen, Baustellen | nein |
| [Photon](https://photon.komoot.io) | Adresssuche | nein |
| [ntfy.sh](https://ntfy.sh) | Push-Nachrichten (optional) | nein |

Alle Dienste sind kostenlos, aber freiwillig betrieben. Die App fragt sparsam ab (Cache) und funktioniert
weiter, wenn eine Quelle ausfällt.
