"""Een onderbroken looplijst bewaren en later hervatten."""

import json
from datetime import datetime, timedelta

from flask import session

from helpers import now_str


LOOP_SESSIE_SLEUTELS = ("loop_fase", "loop_index", "loop_bar", "loop_hok")


LOOP_BEWAREN_DAGEN = 3  # een onderbroken looplijst blijft zo lang bewaard


# ---------- Looplijst bewaren, zodat je 'm kunt pauzeren en later oppakken ----------
# De stand staat tijdens het lopen in de sessie (zie hieronder) en wordt bij
# elke stap ook in de database bewaard: zo overleeft 'ie een vergrendelde
# telefoon, uitloggen of een ander toestel.

def bewaar_stand(db, gebruiker_id, fase, index, bar, hok, review=None):
    """De stand van iemands looplijst in de database: {product_id (tekst): ingevuld aantal (tekst)} voor de bar en het
    voorraadhok, en bij het controleren de opgetelde totalen (review). Ook voor de handterminal-app, die zelf telt en
    alleen de stand doorgeeft (zie routes/app_api.py); zo kun je op de app pauzeren en op de site verder, of andersom."""
    db.execute(
        """INSERT OR REPLACE INTO loop_voortgang
               (gebruiker_id, fase, indx, bar, hok, review, bijgewerkt_op)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (gebruiker_id, fase, index, json.dumps(bar), json.dumps(hok),
         json.dumps(review) if review is not None else None, now_str()),
    )
    db.commit()


def wis_stand(db, gebruiker_id):
    db.execute("DELETE FROM loop_voortgang WHERE gebruiker_id = ?", (gebruiker_id,))
    db.commit()


def loop_bewaren(db):
    gebruiker_id = session.get("gebruiker_id")
    review = session.get("loop_review")
    if gebruiker_id is None or (review is None and "loop_fase" not in session):
        return
    bewaar_stand(db, gebruiker_id, session.get("loop_fase", "bar"), session.get("loop_index", 0),
                 session.get("loop_bar", {}), session.get("loop_hok", {}), review)


def loop_wissen(db):
    """Alles van de looplijst weg: sessie en bewaarde stand."""
    for sleutel in list(LOOP_SESSIE_SLEUTELS) + ["loop_review"]:
        session.pop(sleutel, None)
    gebruiker_id = session.get("gebruiker_id")
    if gebruiker_id is not None:
        wis_stand(db, gebruiker_id)


def bewaarde_stand(db, gebruiker_id):
    """{"fase", "index", "bar", "hok", "review", "bijgewerkt_op"} van iemands bewaarde looplijst, of None."""
    rij = _bewaarde_loop(db, gebruiker_id)
    if rij is None:
        return None
    return {"fase": rij["fase"], "index": rij["indx"], "bar": json.loads(rij["bar"]), "hok": json.loads(rij["hok"]),
            "review": json.loads(rij["review"]) if rij["review"] is not None else None,
            "bijgewerkt_op": rij["bijgewerkt_op"]}


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
    if rij["review"] is not None:
        session["loop_review"] = json.loads(rij["review"])
        session.pop("loop_fase", None)
        session.pop("loop_index", None)
    else:
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
