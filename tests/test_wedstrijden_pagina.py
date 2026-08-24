from datetime import date, timedelta

from conftest import stel_csrf_token_in as _csrf


def _voeg_wedstrijd_toe(db, datum, omschrijving="1e - Test", thuis=1):
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, ?, ?)",
        (datum, omschrijving, thuis),
    )
    db.commit()


def test_pagina_toont_komende_en_gespeelde_wedstrijden(ingelogde_client, db):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    gisteren = (date.today() - timedelta(days=1)).isoformat()
    _voeg_wedstrijd_toe(db, morgen, "1e - Toekomstige tegenstander")
    _voeg_wedstrijd_toe(db, gisteren, "1e - Oude tegenstander")

    resp = ingelogde_client.get("/wedstrijden")
    assert resp.status_code == 200
    assert b"Toekomstige tegenstander" in resp.data
    assert b"Oude tegenstander" in resp.data


def test_vrijwilliger_mag_wedstrijden_pagina_wel_bekijken(client, db, csrf):
    """In tegenstelling tot Club instellingen (beheerder-only) is deze
    pagina voor iedereen -- staat in het Beeld-menu, niet Accounts."""
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op) "
        "VALUES ('vrijwilliger1', 'x', 'vrijwilliger', '2026-01-01 10:00')"
    )
    db.commit()
    gebruiker = db.execute("SELECT * FROM gebruikers WHERE naam = 'vrijwilliger1'").fetchone()
    with client.session_transaction() as sess:
        sess["gebruiker_id"] = gebruiker["id"]
        sess["gebruiker_naam"] = "vrijwilliger1"
        sess["gebruiker_rol"] = "vrijwilliger"
        sess["csrf_token"] = csrf

    resp = client.get("/wedstrijden")
    assert resp.status_code == 200


def test_club_instellingen_verwijst_naar_wedstrijden_pagina(ingelogde_client, db):
    """De geschiedenistabel zelf staat niet meer dubbel op Club
    instellingen, alleen een link naar de Wedstrijden-pagina."""
    resp = ingelogde_client.get("/club-instellingen")
    assert resp.status_code == 200
    assert b"Wedstrijden-pagina" in resp.data
