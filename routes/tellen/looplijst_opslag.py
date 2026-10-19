"""Een onderbroken looplijst bewaren en later hervatten.

Elke looplijst heeft een eigen loop_id. Zo merkt een toestel dat een looplijst ergens anders is afgebroken, opgeslagen
of opnieuw begonnen (een andere browser, of de handterminal-app), in plaats van hem bij de volgende stap stilletjes
weer terug te zetten. De bewaarde stand in de database is steeds de waarheid; de sessie (op de site) en de app volgen
die."""

import json
import uuid
from datetime import datetime, timedelta

from flask import session

from helpers import now_str


LOOP_SESSIE_SLEUTELS = ("loop_fase", "loop_index", "loop_bar", "loop_hok")
# Daarnaast in de sessie: loop_review (bij het controleren), loop_id en loop_op_site (de stand is al eens bewaard).
LOOP_ALLE_SESSIE_SLEUTELS = LOOP_SESSIE_SLEUTELS + ("loop_review", "loop_id", "loop_op_site")

AFGEBROKEN = "Deze telling is op een ander toestel (of in de app) afgebroken of al opgeslagen."
VERVANGEN = "Op een ander toestel (of in de app) is intussen een nieuwe telling begonnen."


LOOP_BEWAREN_DAGEN = 3  # een onderbroken looplijst blijft zo lang bewaard


# ---------- Looplijst bewaren, zodat je 'm kunt pauzeren en later oppakken ----------
# De stand staat tijdens het lopen in de sessie (zie hieronder) en wordt bij
# elke stap ook in de database bewaard: zo overleeft 'ie een vergrendelde
# telefoon, uitloggen of een ander toestel.

def nieuw_loop_id():
    return uuid.uuid4().hex


def bewaar_stand(db, gebruiker_id, fase, index, bar, hok, review=None, loop_id=None):
    """De stand van iemands looplijst in de database: {product_id (tekst): ingevuld aantal (tekst)} voor de bar en het
    voorraadhok, en bij het controleren de opgetelde totalen (review). Ook voor de handterminal-app, die zelf telt en
    alleen de stand doorgeeft (zie routes/app_api.py); zo kun je op de app pauzeren en op de site verder, of andersom."""
    db.execute(
        """INSERT OR REPLACE INTO loop_voortgang
               (gebruiker_id, fase, indx, bar, hok, review, bijgewerkt_op, loop_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (gebruiker_id, fase, index, json.dumps(bar), json.dumps(hok),
         json.dumps(review) if review is not None else None, now_str(), loop_id),
    )
    db.commit()


def wis_stand(db, gebruiker_id, loop_id=None):
    """De bewaarde looplijst weg (afbreken of opgeslagen). Met loop_id alleen als het nog die looplijst is: een late
    'afbreken' van een toestel dat even geen verbinding had, gooit zo geen nieuwere looplijst weg."""
    if loop_id:
        db.execute("DELETE FROM loop_voortgang WHERE gebruiker_id = ? AND (loop_id = ? OR loop_id IS NULL)",
                   (gebruiker_id, loop_id))
    else:
        db.execute("DELETE FROM loop_voortgang WHERE gebruiker_id = ?", (gebruiker_id,))
    db.commit()


def stand_verlopen(db, gebruiker_id, loop_id, nieuw=False):
    """Mag de stand van looplijst loop_id (nog) bewaard of opgeslagen worden? None als het mag: een nieuwe looplijst
    (die vervangt wat er stond), of de bewaarde stand is van deze looplijst. Anders de reden: hij is intussen ergens
    anders afgebroken of opgeslagen, of er is daar een nieuwe begonnen. Zonder loop_id (een oudere app) mag het altijd."""
    if nieuw or not loop_id:
        return None
    rij = _bewaarde_loop(db, gebruiker_id)
    if rij is None:
        return AFGEBROKEN
    if rij["loop_id"] and rij["loop_id"] != loop_id:
        return VERVANGEN
    return None


def loop_bewaren(db):
    gebruiker_id = session.get("gebruiker_id")
    review = session.get("loop_review")
    if gebruiker_id is None or (review is None and "loop_fase" not in session):
        return
    if not session.get("loop_id"):
        session["loop_id"] = nieuw_loop_id()
    bewaar_stand(db, gebruiker_id, session.get("loop_fase", "bar"), session.get("loop_index", 0),
                 session.get("loop_bar", {}), session.get("loop_hok", {}), review, session["loop_id"])
    session["loop_op_site"] = True


def _sessie_leeg():
    for sleutel in LOOP_ALLE_SESSIE_SLEUTELS:
        session.pop(sleutel, None)


def loop_wissen(db):
    """Alles van de looplijst weg: sessie en bewaarde stand."""
    _sessie_leeg()
    gebruiker_id = session.get("gebruiker_id")
    if gebruiker_id is not None:
        wis_stand(db, gebruiker_id)


def loop_bijwerken(db):
    """Zet de looplijst in de sessie gelijk aan de bewaarde stand: die kan op een ander toestel of in de app verder
    zijn, of daar opnieuw begonnen. Geeft True als de looplijst van deze sessie intussen ergens anders is afgebroken of
    opgeslagen; de sessie is dan leeg. Een net begonnen looplijst die nog niet bewaard is, blijft gewoon staan."""
    actief = "loop_fase" in session or session.get("loop_review") is not None
    if _bewaarde_loop(db) is None:
        if actief and session.get("loop_op_site"):
            _sessie_leeg()
            return True
        return False
    loop_herstellen(db)
    return False


def bewaarde_stand(db, gebruiker_id):
    """{"fase", "index", "bar", "hok", "review", "bijgewerkt_op"} van iemands bewaarde looplijst, of None."""
    rij = _bewaarde_loop(db, gebruiker_id)
    if rij is None:
        return None
    return {"fase": rij["fase"], "index": rij["indx"], "bar": json.loads(rij["bar"]), "hok": json.loads(rij["hok"]),
            "review": json.loads(rij["review"]) if rij["review"] is not None else None,
            "bijgewerkt_op": rij["bijgewerkt_op"], "loop_id": rij["loop_id"]}


def _bewaarde_loop(db, gebruiker_id=None):
    """De bewaarde stand van deze gebruiker, of None (ook als 'ie verlopen is)."""
    gebruiker_id = gebruiker_id if gebruiker_id is not None else session.get("gebruiker_id")
    if gebruiker_id is None:
        return None
    rij = db.execute("SELECT * FROM loop_voortgang WHERE gebruiker_id = ?", (gebruiker_id,)).fetchone()
    if rij is None:
        return None
    try:
        bijgewerkt = datetime.strptime(rij["bijgewerkt_op"], "%Y-%m-%d %H:%M")
    except ValueError:
        bijgewerkt = datetime.now()
    if datetime.now() - bijgewerkt > timedelta(days=LOOP_BEWAREN_DAGEN):
        db.execute("DELETE FROM loop_voortgang WHERE gebruiker_id = ?", (gebruiker_id,))
        db.commit()
        return None
    return rij


def loop_herstellen(db):
    """Zet de bewaarde stand terug in de sessie. True als er iets was."""
    rij = _bewaarde_loop(db)
    if rij is None:
        return False
    session["loop_bar"] = json.loads(rij["bar"])
    session["loop_hok"] = json.loads(rij["hok"])
    session["loop_id"] = rij["loop_id"]
    session["loop_op_site"] = True
    if rij["review"] is not None:
        session["loop_review"] = json.loads(rij["review"])
        session.pop("loop_fase", None)
        session.pop("loop_index", None)
    else:
        session.pop("loop_review", None)
        session["loop_fase"] = rij["fase"]
        session["loop_index"] = rij["indx"]
    session.modified = True
    return True


def loop_onderbroken(db, totaal):
    """Beschrijving van een lopende of onderbroken looplijst voor de
    tellen-pagina, of None."""
    rij = _bewaarde_loop(db)
    bijgewerkt = rij["bijgewerkt_op"] if rij else None
    if session.get("loop_review") is not None:
        return {"in_controle": True, "fase": None, "nummer": None, "totaal": totaal, "bijgewerkt_op": bijgewerkt}
    if "loop_fase" in session:
        return {"in_controle": False, "fase": session.get("loop_fase", "bar"),
                "nummer": session.get("loop_index", 0) + 1, "totaal": totaal, "bijgewerkt_op": bijgewerkt}
    if rij is None:
        return None
    return {"in_controle": rij["review"] is not None, "fase": rij["fase"], "nummer": rij["indx"] + 1,
            "totaal": totaal, "bijgewerkt_op": bijgewerkt}
