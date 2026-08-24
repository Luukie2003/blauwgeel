"""Haalt de team-agenda's op (iCal-feeds, bijv. van Sportlink) en zet de
komende wedstrijden in de database, zodat het dashboard kan laten zien welk
weekend het druk wordt -- handig om de verwachte omzet mee in te schatten.

Bedoeld om dagelijks te draaien via een PythonAnywhere Scheduled Task:

    python3 agenda.py

Gebruikt alleen de standaardbibliotheek (net als backup.py -- geen
virtualenv nodig). Werkt alleen als agenda_instellingen.py bestaat; ontbreekt
dat bestand, dan doet dit script niets en blijft de rest van de app gewoon
werken.
"""

import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from urllib.request import urlopen

try:
    import agenda_instellingen as instellingen

    AGENDA_BESCHIKBAAR = True
except ImportError:
    instellingen = None
    AGENDA_BESCHIKBAAR = False

BASE_DIR = Path(__file__).parent
DB_PAD = BASE_DIR / "voorraad.db"
TIMEOUT_SECONDEN = 15

# Deelstring waarmee we onze eigen club herkennen in de wedstrijdomschrijving
# (bijv. "Blauw Geel'15 2-Potetos 4"), om te bepalen of het een thuis- of
# uitwedstrijd is. Hoofdletterongevoelig vergeleken.
CLUBNAAM = "blauw geel"


def _team_naam(tekst):
    match = re.search(r"X-WR-CALNAME:(.+)", tekst)
    if not match:
        return None
    naam = match.group(1).strip()
    # "Voetbal.nl - Blauw Geel'15 O23-1" -> "Blauw Geel'15 O23-1". Splitst op
    # " - " (spatie-streepje-spatie) i.p.v. los streepje, want een teamnaam
    # als "O23-1" heeft zelf ook een streepje, zonder spaties eromheen.
    return naam.split(" - ", 1)[-1].strip()


def _parse_ics(tekst):
    """Minimalistische iCal-parser: leest per VEVENT-blok de SUMMARY en
    DTSTART. Geen externe library nodig voor deze paar velden -- ICS is een
    simpel regelformaat, en we hebben alleen datum + omschrijving nodig."""
    wedstrijden = []
    for blok in tekst.split("BEGIN:VEVENT")[1:]:
        blok = blok.split("END:VEVENT")[0]
        samenvatting_match = re.search(r"SUMMARY:(.+)", blok)
        datum_match = re.search(r"DTSTART[^:]*:(\d{8})", blok)
        if not samenvatting_match or not datum_match:
            continue
        try:
            datum = datetime.strptime(datum_match.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        samenvatting = samenvatting_match.group(1).strip().replace("\\,", ",").replace("\\;", ";")
        thuisploeg = samenvatting.split("-", 1)[0]
        wedstrijden.append({
            "datum": datum.isoformat(),
            "omschrijving": samenvatting,
            "thuis": CLUBNAAM in thuisploeg.lower(),
        })
    return wedstrijden


def ververs_wedstrijden(db_pad=None, vandaag=None):
    """Haalt alle feeds op en vervangt de inhoud van de wedstrijden-tabel
    door de wedstrijden vanaf vandaag. Geeft het aantal weggeschreven
    wedstrijden terug, of None als er geen agenda_instellingen.py is."""
    if not AGENDA_BESCHIKBAAR:
        print("[agenda] Overgeslagen (geen agenda_instellingen.py)")
        return None

    db_pad = db_pad or DB_PAD
    if not Path(db_pad).exists():
        print("[agenda] Database bestaat nog niet -- niets te doen.")
        return None
    vandaag = vandaag or date.today()

    conn = sqlite3.connect(db_pad)
    conn.execute("DELETE FROM wedstrijden")

    aantal = 0
    for feed in instellingen.AGENDA_FEEDS:
        try:
            with urlopen(feed["url"], timeout=TIMEOUT_SECONDEN) as response:
                tekst = response.read().decode("utf-8", errors="replace")
        except Exception as fout:
            print(f"[agenda] Ophalen mislukt voor feed: {fout}")
            continue
        team = _team_naam(tekst) or "Onbekend team"
        for wedstrijd in _parse_ics(tekst):
            if wedstrijd["datum"] < vandaag.isoformat():
                continue
            conn.execute(
                "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES (?, ?, ?, ?)",
                (team, wedstrijd["datum"], wedstrijd["omschrijving"], int(wedstrijd["thuis"])),
            )
            aantal += 1

    conn.commit()
    conn.close()
    print(f"[agenda] {aantal} komende wedstrijden bijgewerkt")
    return aantal


if __name__ == "__main__":
    ververs_wedstrijden()
