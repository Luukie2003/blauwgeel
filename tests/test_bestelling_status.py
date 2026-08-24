from datetime import datetime, timedelta

from app import bereken_bestelling_status


def _plaats_bestelling(db, dagen_geleden=0):
    datum = (datetime.now() - timedelta(days=dagen_geleden)).strftime("%Y-%m-%d %H:%M")
    cur = db.execute(
        "INSERT INTO bestellingen (status, aangemaakt_op, besteld_door) VALUES ('besteld', ?, 'Luuk')",
        (datum,),
    )
    db.commit()
    return cur.lastrowid


def _ontvang_bestelling(db, dagen_geleden=0):
    aangemaakt = (datetime.now() - timedelta(days=dagen_geleden + 1)).strftime("%Y-%m-%d %H:%M")
    ontvangen = (datetime.now() - timedelta(days=dagen_geleden)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        """INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, ontvangen_op)
           VALUES ('ontvangen', ?, 'Luuk', ?)""",
        (aangemaakt, ontvangen),
    )
    db.commit()


def test_status_rood_zonder_bestellingen(db):
    resultaat = bereken_bestelling_status(db)
    assert resultaat["status"] == "rood"
    assert resultaat["laatste_bestelling"] is None


def test_status_oranje_bij_openstaande_bestelling(db):
    _plaats_bestelling(db)

    resultaat = bereken_bestelling_status(db)
    assert resultaat["status"] == "oranje"


def test_status_groen_binnen_zeven_dagen_ontvangen(db):
    _ontvang_bestelling(db, dagen_geleden=3)

    resultaat = bereken_bestelling_status(db)
    assert resultaat["status"] == "groen"


def test_status_rood_boven_zeven_dagen_ontvangen(db):
    _ontvang_bestelling(db, dagen_geleden=10)

    resultaat = bereken_bestelling_status(db)
    assert resultaat["status"] == "rood"


def test_openstaande_bestelling_gaat_voor_recent_ontvangen(db):
    _ontvang_bestelling(db, dagen_geleden=1)
    _plaats_bestelling(db)  # nieuwe, nog niet ingeboekt

    resultaat = bereken_bestelling_status(db)
    assert resultaat["status"] == "oranje"
