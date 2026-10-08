"""Datum- en tijdhulpjes (Nederlandse notatie, Amsterdamse tijd)."""

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo


def format_datum(value):
    if not value:
        return ""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return dt.strftime("%d-%m-%Y %H:%M")


def format_datum_kort(value):
    """Zet een kale ISO-datum (YYYY-MM-DD, geen tijdstip) om naar
    dd-mm-jjjj -- voor de looptijd van een Club van 20-lidmaatschap."""
    if not value:
        return ""
    jaar, maand, dag = value.split("-")
    return f"{dag}-{maand}-{jaar}"


def voeg_maanden_toe(datum_iso, aantal_maanden):
    """Telt kalendermaanden op bij een ISO-datum (YYYY-MM-DD), met
    dagklem aan het einde van de doelmaand (31 jan + 1 maand = 28/29 feb,
    niet 3 maart) -- gebruikt voor de automatische einddatum van een Club
    van 20-lidmaatschap (startdatum + de ingestelde standaard looptijd)."""
    jaar, maand, dag = (int(deel) for deel in datum_iso.split("-"))
    totaal_maanden = maand - 1 + aantal_maanden
    nieuw_jaar = jaar + totaal_maanden // 12
    nieuwe_maand = totaal_maanden % 12 + 1
    laatste_dag = calendar.monthrange(nieuw_jaar, nieuwe_maand)[1]
    return date(nieuw_jaar, nieuwe_maand, min(dag, laatste_dag)).isoformat()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def vandaag_amsterdam():
    """De datum van vandaag in Europe/Amsterdam, i.p.v. date.today() (de
    servertijdzone, UTC op de hosting van deze site) -- gebruikt overal waar
    een datumveld standaard "vandaag" moet zijn voor een gebruiker die zelf
    in Amsterdamse tijd zit. Zonder dit staat zo'n veld tussen middernacht en
    ~02:00 zomertijd (of ~01:00 wintertijd) een dag te vroeg (zie de
    bardienst-datumbug van 16 september 2026, routes/kiosk.py)."""
    return datetime.now(ZoneInfo("Europe/Amsterdam")).date()


def now_datetime_local():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def dagdeel_groet():
    """'Goedemorgen'/'Goedemiddag'/'Goedenavond' op basis van het huidige
    tijdstip, voor de begroeting op het handterminal-startscherm."""
    uur = datetime.now().hour
    if uur < 12:
        return "Goedemorgen"
    if uur < 18:
        return "Goedemiddag"
    return "Goedenavond"
