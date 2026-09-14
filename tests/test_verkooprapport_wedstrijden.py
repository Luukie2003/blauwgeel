"""Tests voor de thuiswedstrijden- en trainingsavond-indicator op het
verkooprapport (bereken_omzet_trend_periode in app.py): elke omzetbalk laat
zien hoeveel thuiswedstrijden en trainingsavonden er in die telling-periode
vielen."""

from datetime import datetime

from conftest import stel_csrf_token_in as _csrf


def _registreer_verkoop(client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 20 WHERE id = ?", (product["id"],))
    db.commit()
    resp = client.post(
        "/tellen",
        data={"csrf_token": _csrf(client), f"geteld_{product['id']}": "5"},
    )
    assert resp.status_code == 302
    return product


def _voeg_thuiswedstrijd_toe(db, datum):
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, 'Test - Wedstrijd', 1)",
        (datum,),
    )
    db.commit()


def _vandaag_periode():
    vandaag = datetime.now().strftime("%Y-%m-%d")
    return vandaag, vandaag


def test_verkooprapport_toont_thuiswedstrijd_bij_omzetbalk(ingelogde_client, db):
    _registreer_verkoop(ingelogde_client, db)
    van, tot = _vandaag_periode()
    _voeg_thuiswedstrijd_toe(db, van)

    resp = ingelogde_client.get(f"/verkooprapport?van={van}&tot={tot}")
    assert resp.status_code == 200
    assert "omzet-bar-wedstrijden".encode() in resp.data
    assert "🏠".encode() in resp.data


def test_verkooprapport_geen_indicator_zonder_thuiswedstrijd(ingelogde_client, db):
    _registreer_verkoop(ingelogde_client, db)
    van, tot = _vandaag_periode()

    resp = ingelogde_client.get(f"/verkooprapport?van={van}&tot={tot}")
    assert resp.status_code == 200
    assert "omzet-bar-wedstrijden".encode() not in resp.data


def test_verkooprapport_negeert_uitwedstrijd(ingelogde_client, db):
    _registreer_verkoop(ingelogde_client, db)
    van, tot = _vandaag_periode()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, 'Test - Uit', 0)",
        (van,),
    )
    db.commit()

    resp = ingelogde_client.get(f"/verkooprapport?van={van}&tot={tot}")
    assert resp.status_code == 200
    assert "omzet-bar-wedstrijden".encode() not in resp.data


def _maak_telling_op_datum(db, datum):
    """Zet een telling op een vaste, zelf gekozen datum (i.p.v. 'nu' zoals
    POST /tellen dat doet) -- nodig om de periode betrouwbaar rond een
    bekende woensdag te leggen, ongeacht welke dag de test echt draait."""
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 20 WHERE id = ?", (product["id"],))
    db.commit()
    cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (datum,))
    telling_id = cur.lastrowid
    db.execute(
        """INSERT INTO telling_regels
           (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
           VALUES (?, ?, 20, 15, 5, ?)""",
        (telling_id, product["id"], product["verkoopprijs"] or 1),
    )
    db.commit()


def test_verkooprapport_toont_trainingsavond_bij_omzetbalk(ingelogde_client, db):
    """Alle teams trainen op dezelfde vaste woensdagavond -- dat hoeft
    niemand handmatig aan te geven, in tegenstelling tot wedstrijden.
    2024-01-01 is een maandag, dus 2024-01-04 (donderdag) t/m 2024-01-01
    bevat precies één woensdag (2024-01-03)."""
    _maak_telling_op_datum(db, "2024-01-04 12:00")

    resp = ingelogde_client.get("/verkooprapport?van=2024-01-01&tot=2024-01-04")
    assert resp.status_code == 200
    assert "omzet-bar-trainingen".encode() in resp.data
    assert "🏋️".encode() in resp.data


def test_verkooprapport_geen_indicator_zonder_trainingsavond(ingelogde_client, db):
    """2024-01-01 (maandag) t/m 2024-01-02 (dinsdag) bevat geen woensdag."""
    _maak_telling_op_datum(db, "2024-01-02 12:00")

    resp = ingelogde_client.get("/verkooprapport?van=2024-01-01&tot=2024-01-02")
    assert resp.status_code == 200
    assert "omzet-bar-trainingen".encode() not in resp.data
