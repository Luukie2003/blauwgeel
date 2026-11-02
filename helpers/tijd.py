"""Datum- en tijdhulpjes (Nederlandse notatie, Amsterdamse tijd)."""

import tijdzone  # noqa: F401  (het proces rekent in Nederlandse tijd, ook op een server in UTC)

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo


def format_datum(value):
    if not value:
        return ""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return dt.strftime("%d-%m-%Y %H:%M")


def format_laatst_actief(value, nu=None):
    """'vandaag 14:05', 'gisteren 20:13', '3 dagen geleden' of anders de datum, voor een tijdstip in het formaat van
    now_str() (dezelfde klok, zodat 'vandaag' klopt met wat er is opgeslagen)."""
    if not value:
        return ""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
    nu = nu or datetime.strptime(now_str(), "%Y-%m-%d %H:%M")
    dagen = (nu.date() - dt.date()).days
    if dagen <= 0:
        return f"vandaag {dt:%H:%M}"
    if dagen == 1:
        return f"gisteren {dt:%H:%M}"
    if dagen < 7:
        return f"{dagen} dagen geleden"
    return dt.strftime("%d-%m-%Y")


_WEEKDAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
_MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
            "november", "december"]
_MAANDEN_KORT = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def format_dag_maand(value):
    """'2026-09-18 22:00' of '2026-09-18' -> '18 sep': kort, voor lijsten en tabellen (2.0)."""
    if not value:
        return ""
    dt = datetime.strptime(str(value)[:10], "%Y-%m-%d")
    return f"{dt.day} {_MAANDEN_KORT[dt.month - 1]}"


def datum_lang(dag):
    """date -> 'zaterdag 31 oktober', voor de kop van een pagina (2.0)."""
    return f"{_WEEKDAGEN[dag.weekday()]} {dag.day} {_MAANDEN[dag.month - 1]}"


def format_dag_lang(value, vandaag=None):
    """'2026-10-27 18:37' -> 'dinsdag 27 oktober', met het jaar erachter als het niet dit jaar is: voor een kopregel per
    dag in een lijst, zoals het mutatieoverzicht (2.0)."""
    if not value:
        return ""
    dag = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    vandaag = vandaag or datetime.now().date()
    return datum_lang(dag) if dag.year == vandaag.year else f"{datum_lang(dag)} {dag.year}"


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
