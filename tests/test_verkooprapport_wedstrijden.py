"""Tests voor de thuiswedstrijden-indicator op het verkooprapport
(bereken_omzet_trend_periode in app.py): elke omzetbalk laat zien hoeveel
thuiswedstrijden er in die telling-periode vielen."""

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
