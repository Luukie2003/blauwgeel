"""Haalt de team-agenda's op (iCal-feeds, bijv. van Sportlink) en zet de
komende wedstrijden in de database, zodat het dashboard kan laten zien welk
weekend het druk wordt -- handig om de verwachte omzet mee in te schatten.

De feed-links worden beheerd via Club instellingen in de app (tabel
agenda_feeds) -- dit script leest ze rechtstreeks uit de database, er is
geen los configbestand meer nodig.

Bedoeld om dagelijks te draaien via een PythonAnywhere Scheduled Task:

    python3 agenda.py

Gebruikt alleen de standaardbibliotheek (net als backup.py -- geen
virtualenv nodig)."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

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


def haal_feed_op(url):
    """Haalt en parseert 1 iCal-feed. Gooit een uitzondering door bij een
    netwerk- of parseerfout; de aanroeper bepaalt hoe dat getoond wordt."""
    with urlopen(url, timeout=TIMEOUT_SECONDEN) as response:
        tekst = response.read().decode("utf-8", errors="replace")
    team = _team_naam(tekst) or "Onbekend team"
    return team, _parse_ics(tekst)


def controleer_feeds(urls):
    """Test elke feed-link zonder de database te wijzigen -- voor de
    'Controleren'-knop in Club instellingen."""
    resultaten = []
    for url in urls:
        try:
            team, wedstrijden = haal_feed_op(url)
            resultaten.append({"url": url, "ok": True, "team": team, "aantal": len(wedstrijden)})
        except Exception as fout:
            resultaten.append({"url": url, "ok": False, "team": None, "fout": str(fout)})
    return resultaten


def ververs_wedstrijden(db_pad=None):
    """Haalt alle ingestelde feeds op en voegt nieuwe wedstrijden toe aan de
    database -- zowel komende als al gespeelde, want gespeelde wedstrijden
    blijven bewust bewaard als geschiedenis in plaats van verwijderd te
    worden. INSERT OR IGNORE (samen met de unieke index op
    team+datum+omschrijving) zorgt dat een wedstrijd die al bekend was niet
    dubbel wordt weggeschreven bij een volgende ververs-ronde. Werkt de
    teamnaam per feed bij zodra die bekend is. Geeft het aantal nieuw
    toegevoegde wedstrijden terug, of None als er geen feeds zijn
    ingesteld."""
    db_pad = db_pad or DB_PAD
    if not Path(db_pad).exists():
        print("[agenda] Database bestaat nog niet -- niets te doen.")
        return None

    conn = sqlite3.connect(db_pad)
    conn.row_factory = sqlite3.Row
    feeds = conn.execute("SELECT id, url FROM agenda_feeds ORDER BY id").fetchall()
    if not feeds:
        conn.close()
        print("[agenda] Geen agenda-links ingesteld -- niets te doen.")
        return None

    aantal = 0
    for feed in feeds:
        try:
            team, wedstrijden = haal_feed_op(feed["url"])
        except Exception as fout:
            print(f"[agenda] Ophalen mislukt voor feed #{feed['id']}: {fout}")
            continue
        conn.execute("UPDATE agenda_feeds SET team = ? WHERE id = ?", (team, feed["id"]))
        for wedstrijd in wedstrijden:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO wedstrijden (team, datum, omschrijving, thuis)
                   VALUES (?, ?, ?, ?)""",
                (team, wedstrijd["datum"], wedstrijd["omschrijving"], int(wedstrijd["thuis"])),
            )
            if cursor.rowcount:
                aantal += 1

    conn.commit()
    conn.close()
    print(f"[agenda] {aantal} nieuwe wedstrijden toegevoegd")
    return aantal


if __name__ == "__main__":
    ververs_wedstrijden()
