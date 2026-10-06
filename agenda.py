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
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).parent
DB_PAD = BASE_DIR / "voorraad.db"
TIMEOUT_SECONDEN = 15

# Deelstring waarmee we onze eigen club herkennen in de wedstrijdomschrijving
# (bijv. "Blauw Geel'15 2-Potetos 4"), om te bepalen of het een thuis- of
# uitwedstrijd is. Hoofdletterongevoelig vergeleken.
CLUBNAAM = "blauw geel"

# Een afgelaste wedstrijd herkennen we aan STATUS:CANCELLED in de feed, of aan een
# woord als "afgelast" in de omschrijving. Dat woord halen we uit de omschrijving
# weg, zodat een wedstrijd die later alsnog als afgelast in de feed komt dezelfde
# rij blijft en niet dubbel in de database komt.
AFGELAST_WOORDEN = r"afgelast|afgelasting|geannuleerd|cancelled|canceled"
_AFGELAST_PATROON = re.compile(rf"\b(?:{AFGELAST_WOORDEN})\b", re.IGNORECASE)
_AFGELAST_MARKERING = re.compile(
    rf"[\(\[]?\b(?:{AFGELAST_WOORDEN})\b[\)\]]?\s*[:\-\u2013]?\s*", re.IGNORECASE
)


def _schoon_afgelasting(samenvatting, status_geannuleerd=False):
    """(omschrijving zonder afgelast-markering, afgelast?)."""
    afgelast = status_geannuleerd or bool(_AFGELAST_PATROON.search(samenvatting))
    schoon = _AFGELAST_MARKERING.sub("", samenvatting).strip(" -:") or samenvatting
    return schoon, afgelast


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
    simpel regelformaat, en we hebben alleen datum + omschrijving (+ eventueel
    aanvangstijd) nodig."""
    wedstrijden = []
    for blok in tekst.split("BEGIN:VEVENT")[1:]:
        blok = blok.split("END:VEVENT")[0]
        samenvatting_match = re.search(r"SUMMARY:(.+)", blok)
        # Groep 1: datumcijfers (altijd aanwezig). Groepen 2-4: uur/minuut/
        # seconde, alleen aanwezig bij een echte DTSTART:...T-tijdstip (een
        # "heel-de-dag"-event zoals DTSTART;VALUE=DATE:20260920 heeft dat
        # niet). Groep 5: een kale "Z" betekent UTC i.p.v. lokale tijd.
        datum_match = re.search(r"DTSTART[^:]*:(\d{8})(?:T(\d{2})(\d{2})\d{2}(Z)?)?", blok)
        if not samenvatting_match or not datum_match:
            continue
        try:
            datum = datetime.strptime(datum_match.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        tijd = None
        if datum_match.group(2):
            uur, minuut = int(datum_match.group(2)), int(datum_match.group(3))
            if datum_match.group(4):
                # UTC-tijdstip -- omzetten naar Europe/Amsterdam kan de datum
                # zelf ook verschuiven (net na middernacht lokaal).
                lokaal = datetime(
                    datum.year, datum.month, datum.day, uur, minuut, tzinfo=ZoneInfo("UTC")
                ).astimezone(ZoneInfo("Europe/Amsterdam"))
                datum = lokaal.date()
                tijd = lokaal.strftime("%H:%M")
            else:
                tijd = f"{uur:02d}:{minuut:02d}"
        samenvatting = samenvatting_match.group(1).strip().replace("\\,", ",").replace("\\;", ";")
        samenvatting, afgelast = _schoon_afgelasting(
            samenvatting, status_geannuleerd=bool(re.search(r"STATUS:\s*CANCELLED", blok, re.IGNORECASE))
        )
        thuisploeg = samenvatting.split("-", 1)[0]
        wedstrijden.append({
            "datum": datum.isoformat(),
            "omschrijving": samenvatting,
            "thuis": CLUBNAAM in thuisploeg.lower(),
            "tijd": tijd,
            "afgelast": afgelast,
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


def _werk_afgelasting_bij(conn, team, wedstrijden):
    """Wedstrijden die al in de database stonden: zet ze op afgelast als de agenda dat
    nu meldt, en haal een afgelasting weg die alleen de agenda had gezet als de agenda
    weer zegt dat de wedstrijd gewoon doorgaat. Wat iemand handmatig heeft gekozen
    (afgelast of juist "toch spelen") blijft staan."""
    for wedstrijd in wedstrijden:
        if wedstrijd["afgelast"]:
            conn.execute(
                """UPDATE wedstrijden SET afgelast = 1, afgelast_bron = 'agenda'
                   WHERE team = ? AND datum = ? AND omschrijving = ?
                         AND afgelast = 0 AND afgelast_bron IS NOT 'handmatig'""",
                (team, wedstrijd["datum"], wedstrijd["omschrijving"]),
            )
        else:
            conn.execute(
                """UPDATE wedstrijden SET afgelast = 0, afgelast_bron = NULL
                   WHERE team = ? AND datum = ? AND omschrijving = ?
                         AND afgelast = 1 AND afgelast_bron = 'agenda'""",
                (team, wedstrijd["datum"], wedstrijd["omschrijving"]),
            )


def _markeer_verdwenen_wedstrijden(conn, team, wedstrijden, dagen_vooruit=14, vandaag=None):
    """Een wedstrijd van de komende dagen die nog in de database staat maar niet
    meer in de feed van dit team (afgelast en uit de agenda gehaald, of verzet
    naar een andere datum), gaat als afgelast door. Alleen als de feed zelf
    nog wedstrijden op of na die datum bevat: een feed die opeens leeg of
    afgekapt is mag niet voor een stapel valse afgelastingen zorgen."""
    if not wedstrijden:
        return
    vandaag = vandaag or datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    grens = vandaag.fromordinal(vandaag.toordinal() + dagen_vooruit).isoformat()
    in_feed = {(w["datum"], w["omschrijving"]) for w in wedstrijden}
    laatste_in_feed = max(w["datum"] for w in wedstrijden)
    for rij in conn.execute(
        """SELECT id, datum, omschrijving FROM wedstrijden
           WHERE team = ? AND afgelast = 0 AND afgelast_bron IS NOT 'handmatig'
                 AND datum >= ? AND datum <= ?""",
        (team, vandaag.isoformat(), grens),
    ).fetchall():
        if (rij["datum"], rij["omschrijving"]) not in in_feed and laatste_in_feed >= rij["datum"]:
            conn.execute(
                "UPDATE wedstrijden SET afgelast = 1, afgelast_bron = 'agenda' WHERE id = ?", (rij["id"],)
            )


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
                """INSERT OR IGNORE INTO wedstrijden (team, datum, omschrijving, thuis, tijd, afgelast, afgelast_bron)
                   VALUES (?, ?, ?, ?, ?, ?, CASE WHEN ? = 1 THEN 'agenda' END)""",
                (
                    team,
                    wedstrijd["datum"],
                    wedstrijd["omschrijving"],
                    int(wedstrijd["thuis"]),
                    wedstrijd["tijd"],
                    1 if wedstrijd["afgelast"] else 0,
                    1 if wedstrijd["afgelast"] else 0,
                ),
            )
            if cursor.rowcount:
                aantal += 1
            elif wedstrijd["tijd"]:
                # Was al bekend (bijv. van vóór de tijd werd meegenomen uit de
                # feed) -- tijd alsnog bijwerken, want INSERT OR IGNORE raakt
                # een bestaande rij verder niet aan.
                conn.execute(
                    """UPDATE wedstrijden SET tijd = ?
                       WHERE team = ? AND datum = ? AND omschrijving = ?
                             AND (tijd IS NULL OR tijd != ?)""",
                    (
                        wedstrijd["tijd"],
                        team,
                        wedstrijd["datum"],
                        wedstrijd["omschrijving"],
                        wedstrijd["tijd"],
                    ),
                )

        _werk_afgelasting_bij(conn, team, wedstrijden)
        _markeer_verdwenen_wedstrijden(conn, team, wedstrijden)

    conn.commit()
    conn.close()
    print(f"[agenda] {aantal} nieuwe wedstrijden toegevoegd")
    return aantal


if __name__ == "__main__":
    ververs_wedstrijden()
