"""Statuskaarten voor het dashboard en de handterminal."""

from datetime import datetime

from helpers.kas import bereken_kassa_telling_status
from helpers.toegang import heeft_sectie_toegang
from helpers.wedstrijden import bereken_komende_thuiswedstrijden


def bereken_laatste_telling_status(db):
    """Status van de laatste voorraadtelling voor het statusblokje op het
    dashboard: groen binnen 7 dagen, rood daarboven (of als er nog nooit
    geteld is)."""
    laatste = db.execute("SELECT * FROM tellingen ORDER BY datum DESC, id DESC LIMIT 1").fetchone()
    if laatste is None:
        return {"laatste": None, "dagen_geleden": None, "ok": False}
    dagen_geleden = (datetime.now() - datetime.strptime(laatste["datum"], "%Y-%m-%d %H:%M")).days
    return {"laatste": laatste, "dagen_geleden": dagen_geleden, "ok": dagen_geleden <= 7}


def bereken_bestelling_status(db):
    """Status van het statusblokje 'Bestelling inboeken'. Oranje zolang er
    nog een openstaande bestelling is (besteld, nog niet ontvangen) --
    gaat voor de andere regels. Anders: groen als de laatst ontvangen
    bestelling binnen 7 dagen was, rood daarboven (of als er nog nooit een
    bestelling ontvangen is)."""
    open_bestelling = db.execute(
        "SELECT * FROM bestellingen WHERE status = 'besteld' ORDER BY aangemaakt_op DESC LIMIT 1"
    ).fetchone()
    if open_bestelling is not None:
        return {"status": "oranje", "tekst": "Nog niet ingeboekt", "laatste_bestelling": open_bestelling}

    laatste_ontvangen = db.execute(
        "SELECT * FROM bestellingen WHERE status = 'ontvangen' ORDER BY ontvangen_op DESC LIMIT 1"
    ).fetchone()
    if laatste_ontvangen is None:
        return {"status": "rood", "tekst": "Nog nooit ontvangen", "laatste_bestelling": None}

    dagen_geleden = (
        datetime.now() - datetime.strptime(laatste_ontvangen["ontvangen_op"], "%Y-%m-%d %H:%M")
    ).days
    if dagen_geleden <= 7:
        status = "groen"
        tekst = f"{dagen_geleden} dag{'' if dagen_geleden == 1 else 'en'} geleden"
    else:
        status = "rood"
        tekst = "Meer dan 7 dagen niet ontvangen"

    return {"status": status, "tekst": tekst, "laatste_bestelling": laatste_ontvangen}


def bereken_pda_start(db, rol, secties):
    """Wat het handterminal-startscherm bovenaan laat zien: een paar korte
    regels met wat er nu aandacht nodig heeft. Alleen wat bij de rechten
    van de gebruiker past (voorraad, kassa, keuken), zodat een vrijwilliger
    met alleen keuken-rechten niet ineens voorraadcijfers krijgt."""
    heeft = lambda sectie: heeft_sectie_toegang(rol, secties, sectie)
    uitkomst = {
        "laag": None,
        "open_bestellingen": None,
        "telling_status": None,
        "kassa_status": None,
        "bestelling_status": None,
        "frituurvet_status": None,
        "volgende_wedstrijd": None,
    }
    if heeft("voorraad"):
        uitkomst["laag"] = db.execute(
            "SELECT COUNT(*) AS n FROM producten WHERE actief = 1 AND voorraad < min_voorraad"
        ).fetchone()["n"]
        uitkomst["open_bestellingen"] = db.execute(
            "SELECT COUNT(*) AS n FROM bestellingen WHERE status = 'besteld'"
        ).fetchone()["n"]
        uitkomst["telling_status"] = bereken_laatste_telling_status(db)
        uitkomst["bestelling_status"] = bereken_bestelling_status(db)
        komend = bereken_komende_thuiswedstrijden(db, dagen=7)
        uitkomst["volgende_wedstrijd"] = komend[0] if komend else None
    if heeft("kassa"):
        uitkomst["kassa_status"] = bereken_kassa_telling_status(db)
    if heeft("keuken"):
        uitkomst["frituurvet_status"] = bereken_frituurvet_status(db)
    mededelingen = db.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(urgent), 0) AS urgent
           FROM mededelingen WHERE afgehandeld = 0"""
    ).fetchone()
    uitkomst["mededelingen_open"] = mededelingen["n"]
    uitkomst["mededelingen_urgent"] = mededelingen["urgent"]
    return uitkomst


def bereken_frituurvet_status(db):
    """Status van het statusblokje 'Frituurvet': groen zolang de laatste
    vervanging binnen het ingestelde aantal dagen (instellingen tabel,
    standaard 14) valt, rood daarboven of als er nog nooit een vervanging
    is gelogd."""
    interval = db.execute(
        "SELECT frituurvet_interval_dagen FROM instellingen WHERE id = 1"
    ).fetchone()["frituurvet_interval_dagen"]
    laatste = db.execute(
        "SELECT * FROM frituurvet_vervangingen ORDER BY datum DESC, id DESC LIMIT 1"
    ).fetchone()
    if laatste is None:
        return {"laatste": None, "dagen_geleden": None, "interval": interval, "ok": False}
    dagen_geleden = (datetime.now() - datetime.strptime(laatste["datum"], "%Y-%m-%d %H:%M")).days
    return {
        "laatste": laatste,
        "dagen_geleden": dagen_geleden,
        "interval": interval,
        "ok": dagen_geleden <= interval,
    }
