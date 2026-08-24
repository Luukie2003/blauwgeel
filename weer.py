"""Haalt een weersverwachting op (Open-Meteo -- gratis, geen account of
API-sleutel nodig) en zet 'm in de database. Wordt samen met de
teamagenda's (agenda.py) gebruikt om in te schatten hoe druk een dag wordt:
mooi weer plus een thuiswedstrijd trekt meer mensen dan een wedstrijd bij
regen.

Bedoeld om dagelijks te draaien via een PythonAnywhere Scheduled Task, net
als agenda.py en backup.py:

    python3 weer.py

Gebruikt alleen de standaardbibliotheek -- geen virtualenv nodig."""

import json
import sqlite3
from pathlib import Path
from urllib.request import urlopen

BASE_DIR = Path(__file__).parent
DB_PAD = BASE_DIR / "voorraad.db"
TIMEOUT_SECONDEN = 15

# Coördinaten van Groningen (Kooiweg, 9722 BZ) -- pas aan bij verhuizing
# van de club. Voor een weersverwachting is stadsniveau precies genoeg,
# het weer verschilt niet merkbaar binnen een stad.
LATITUDE = 53.21917
LONGITUDE = 6.56667

VOORSPELLING_DAGEN = 10

# Vereenvoudigde vertaling van de WMO-weercodes die Open-Meteo gebruikt.
WEERCODE_LABELS = {
    0: "helder",
    1: "overwegend helder",
    2: "half bewolkt",
    3: "bewolkt",
    45: "mist",
    48: "mist",
    51: "lichte motregen",
    53: "motregen",
    55: "motregen",
    61: "lichte regen",
    63: "regen",
    65: "zware regen",
    71: "lichte sneeuw",
    73: "sneeuw",
    75: "zware sneeuw",
    80: "regenbuien",
    81: "regenbuien",
    82: "zware regenbuien",
    95: "onweer",
    96: "onweer met hagel",
    99: "onweer met hagel",
}


def weer_label(weercode):
    return WEERCODE_LABELS.get(weercode, "onbekend")


def haal_voorspelling_op():
    """Haalt de dagelijkse verwachting op. Gooit een uitzondering door bij
    een netwerkfout; de aanroeper bepaalt hoe dat afgehandeld wordt."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&daily=weathercode,temperature_2m_max,precipitation_probability_max"
        f"&timezone=Europe%2FAmsterdam&forecast_days={VOORSPELLING_DAGEN}"
    )
    with urlopen(url, timeout=TIMEOUT_SECONDEN) as response:
        data = json.loads(response.read().decode("utf-8"))
    dagen = data["daily"]
    return [
        {
            "datum": datum,
            "max_temp": dagen["temperature_2m_max"][i],
            "neerslag_kans": dagen["precipitation_probability_max"][i],
            "weercode": dagen["weathercode"][i],
        }
        for i, datum in enumerate(dagen["time"])
    ]


def ververs_weer(db_pad=None):
    """Haalt de verwachting op en vervangt de inhoud van de
    weer_voorspelling-tabel. Geeft het aantal weggeschreven dagen terug, of
    None als het ophalen mislukte."""
    db_pad = db_pad or DB_PAD
    if not Path(db_pad).exists():
        print("[weer] Database bestaat nog niet -- niets te doen.")
        return None
    try:
        voorspelling = haal_voorspelling_op()
    except Exception as fout:
        print(f"[weer] Ophalen mislukt: {fout}")
        return None

    conn = sqlite3.connect(db_pad)
    conn.execute("DELETE FROM weer_voorspelling")
    for dag in voorspelling:
        conn.execute(
            """INSERT INTO weer_voorspelling (datum, max_temp, neerslag_kans, weercode)
               VALUES (?, ?, ?, ?)""",
            (dag["datum"], dag["max_temp"], dag["neerslag_kans"], dag["weercode"]),
        )
    conn.commit()
    conn.close()
    print(f"[weer] {len(voorspelling)} dagen weersvoorspelling bijgewerkt")
    return len(voorspelling)


if __name__ == "__main__":
    ververs_weer()
