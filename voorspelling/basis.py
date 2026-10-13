"""Het voorspelmodel, deel 1: de aannames, de verkoopdagen en de kalender (thuiswedstrijden, training, weer en
evenementen), en hoeveel 'gewone dagen' een periode waard is (blootstelling en drukte). Zie voorspelling/__init__.py
voor hoe het model als geheel werkt."""

import sqlite3
from datetime import datetime, time, timedelta

from helpers import TRAININGSDAG

# ---- Aannames waar het model mee begint en wat het erbij leert ----
PRIOR = {"wedstrijd": 0.30, "training": 0.20, "weer": 0.12, "evenement": 1.0}
# Hoe zeker we van de aanname zijn (standaardafwijking van het effect). Hoe
# kleiner, hoe meer data er nodig is om ervan af te wijken.
ONZEKERHEID = {"wedstrijd": 0.5, "training": 0.35, "weer": 0.15, "evenement": 1.0}
GRENZEN = {"wedstrijd": (0.0, 1.5), "training": (0.0, 1.0), "weer": (-0.25, 0.5), "evenement": (0.0, 4.0)}
EFFECT_NAMEN = {
    "wedstrijd": "Thuiswedstrijd",
    "training": "Trainingsavond",
    "weer": "Weer (mooi plus, regen min)",
    "evenement": "Evenement (toernooi, feest, verhuur)",
}

DAG_BEGIN_UUR = 12  # een kantinedag loopt van 12.00 tot 12.00 uur
HALVERING_WEKEN = 6.0  # recente verkoop telt zwaarder
MAX_WEKEN_GESCHIEDENIS = 30  # oudere verkoop weegt toch bijna niets meer mee
MODEL_MAX_PRODUCTEN = 30  # alleen de best verkopende producten leren de effecten
MIN_RIJEN_PER_PRODUCT = 2
TERUGTOETS_START = 4  # pas terugtoetsen vanaf de 4e telling

MODEL_ONZEKERHEID_DAG = 0.12  # ruimte voor drukte die we niet kunnen voorspellen
DEKKING_SERVICENIVEAU = 0.9  # bestelling dekt de vraag in 9 van de 10 gevallen

_WEEKDAG = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
_WEEKDAG_KORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]

VERKOOPDAGEN_STANDAARD = (2, 5)  # woensdag en zaterdag (maandag = 0)
_LEGE_DAG = {"wedstrijden": 0, "training": False, "weer": None, "open": True, "evenementen": 0}


def lees_verkoopdagen(db):
    """(weekdagen, uitzonderingen): de weekdagen waarop standaard verkocht wordt
    (maandag = 0) en {datum-tekst: True/False} voor losse datums die daarvan
    afwijken (True = wel open, False = dicht). Zonder instelling: woensdag
    en zaterdag."""
    tekst = None
    try:
        rij = db.execute("SELECT verkoopdagen FROM instellingen WHERE id = 1").fetchone()
        tekst = rij["verkoopdagen"] if rij else None
    except Exception:  # kolom bestaat nog niet (oude database)
        pass
    dagen = {int(x) for x in (tekst or "").split(",") if x.strip().isdigit() and 0 <= int(x) <= 6}
    try:
        uitzonderingen = {
            r["datum"]: bool(r["open"]) for r in db.execute("SELECT datum, open FROM verkoop_uitzonderingen")
        }
    except Exception:  # tabel bestaat nog niet
        uitzonderingen = {}
    return (dagen or set(VERKOOPDAGEN_STANDAARD)), uitzonderingen


def dag_is_open(dag, weekdagen, uitzonderingen):
    """Wordt er op deze datum (date) verkocht?"""
    return uitzonderingen.get(dag.isoformat(), dag.weekday() in weekdagen)


# ---------------------------------------------------------------------------
# Kalender: wat gebeurt er op welke dag?
# ---------------------------------------------------------------------------


def wedstrijd_gewicht(aantal):
    """Drukte-gewicht van een dag met 'aantal' thuiswedstrijden: de eerste telt
    voor 1, elke extra voor 0,25 erbij (met een maximum van 4 wedstrijden)."""
    if aantal <= 0:
        return 0.0
    return 1.0 + 0.25 * (min(aantal, 4) - 1)


def weer_score(max_temp, neerslag_kans):
    """+1 bij mooi weer (warm en droog), -1 bij regen, anders 0. None als er
    geen weergegevens zijn."""
    if max_temp is None or neerslag_kans is None:
        return None
    if neerslag_kans >= 60:
        return -1.0
    if max_temp >= 18 and neerslag_kans < 30:
        return 1.0
    return 0.0


def lees_kalender(db, van, tot):
    """{datum: {wedstrijden, training, weer, open}} voor van t/m tot (date-objecten).
    Wedstrijden komen uit de gekoppelde teamagenda's, het weer uit de
    opgeslagen weergeschiedenis (laatst bekende verwachting per dag) en voor
    de komende dagen uit de actuele verwachting."""
    wedstrijden = {
        r["datum"]: r["n"]
        for r in db.execute(
            """SELECT datum, COUNT(*) AS n FROM wedstrijden
               WHERE thuis = 1 AND afgelast = 0 AND datum >= ? AND datum <= ? GROUP BY datum""",
            (van.isoformat(), tot.isoformat()),
        ).fetchall()
    }
    weer = {}
    for tabel in ("weer_historie", "weer_voorspelling"):  # voorspelling wint (vers)
        try:
            rijen = db.execute(
                f"SELECT datum, max_temp, neerslag_kans FROM {tabel} WHERE datum >= ? AND datum <= ?",
                (van.isoformat(), tot.isoformat()),
            ).fetchall()
        except Exception:  # tabel bestaat nog niet (oude database)
            rijen = []
        for r in rijen:
            weer[r["datum"]] = weer_score(r["max_temp"], r["neerslag_kans"])
    evenementen = lees_evenementen(db, van, tot)
    weekdagen, uitzonderingen = lees_verkoopdagen(db)
    kalender = {}
    dag = van
    while dag <= tot:
        iso = dag.isoformat()
        # Een evenement (toernooi, feest, verhuur) is altijd een verkoopdag, ook op een dag dat de kantine anders dicht is.
        open_ = dag_is_open(dag, weekdagen, uitzonderingen) or iso in evenementen
        kalender[dag] = {
            "wedstrijden": wedstrijden.get(iso, 0),
            "training": dag.weekday() == TRAININGSDAG,
            "weer": weer.get(iso),
            "open": open_,
            "evenementen": len(evenementen.get(iso, [])),
        }
        dag += timedelta(days=1)
    return kalender


def lees_evenementen(db, van, tot):
    """{datum (tekst): [naam, ...]} van de evenementen van van t/m tot (date-objecten), zie Prognose > Evenementen."""
    uitkomst = {}
    try:
        rijen = db.execute(
            "SELECT datum, naam FROM evenementen WHERE datum >= ? AND datum <= ? ORDER BY datum, id",
            (van.isoformat(), tot.isoformat()),
        ).fetchall()
    except sqlite3.OperationalError:  # oudere database zonder deze tabel
        rijen = []
    for r in rijen:
        uitkomst.setdefault(r["datum"], []).append(r["naam"])
    return uitkomst


def _dag_venster(dag):
    begin = datetime.combine(dag, time(DAG_BEGIN_UUR, 0))
    return begin, begin + timedelta(days=1)


def blootstelling(start, einde, kalender):
    """Hoeveel 'dag-equivalent' een periode bevat, opgesplitst:
    D = dagen, M = wedstrijddagen (gewogen), T = trainingsavonden, S = weerscore
    (mooi +, regen -), W = dagen waarvan het weer bekend is. Een dag telt
    mee naar rato van hoeveel van zijn 12-12-venster in de periode valt. Een dag
    waarop niet verkocht wordt (zie lees_verkoopdagen) telt helemaal niet mee."""
    D = M = T = S = W = E = 0.0
    dag = (start - timedelta(hours=DAG_BEGIN_UUR)).date()
    while True:
        d_begin, d_eind = _dag_venster(dag)
        if d_begin >= einde:
            break
        deel = (min(einde, d_eind) - max(start, d_begin)).total_seconds() / 86400
        k = kalender.get(dag) or _LEGE_DAG
        if deel > 0 and k.get("open", True):
            D += deel
            M += deel * wedstrijd_gewicht(k["wedstrijden"])
            T += deel * (1.0 if k["training"] else 0.0)
            E += deel * (1.0 if k.get("evenementen") else 0.0)
            if k["weer"] is not None:
                S += deel * k["weer"]
                W += deel
        dag += timedelta(days=1)
    return {"D": D, "M": M, "T": T, "S": S, "W": W, "E": E}


def drukte(b, effecten):
    """Aantal 'normale dagen' dat deze blootstelling waard is."""
    return (
        b["D"] + effecten["wedstrijd"] * b["M"] + effecten["training"] * b["T"] + effecten["weer"] * b["S"]
        + effecten.get("evenement", 0.0) * b.get("E", 0.0)
    )
