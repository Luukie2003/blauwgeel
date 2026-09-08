from werkzeug.security import generate_password_hash

from database import WACHTWOORD_HASH_METHODE

from conftest import stel_csrf_token_in


def _maak_vrijwilliger(db, naam, secties):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) "
        "VALUES (?, ?, 'vrijwilliger', ?, '2026-01-01 10:00')",
        (naam, generate_password_hash("test1234", method=WACHTWOORD_HASH_METHODE), secties),
    )
    db.commit()


def _login(client, naam):
    csrf = stel_csrf_token_in(client)
    resp = client.post(
        "/login", data={"naam": naam, "wachtwoord": "test1234", "csrf_token": csrf}
    )
    assert resp.status_code == 302
    return csrf


def test_vrijwilliger_zonder_kassa_sectie_wordt_geweerd(client, db):
    _maak_vrijwilliger(db, "kassaloze_vrijwilliger", "voorraad")
    _login(client, "kassaloze_vrijwilliger")

    resp = client.get("/kassa/tellen", follow_redirects=True)
    assert resp.status_code == 200
    assert b"niet beschikbaar voor jouw account" in resp.data
    # Redirect eindigt op het dashboard, niet op de kassapagina zelf.
    assert resp.request.path == "/"


def test_vrijwilliger_met_kassa_sectie_mag_er_wel_in(client, db):
    _maak_vrijwilliger(db, "kassa_vrijwilliger", "kassa")
    _login(client, "kassa_vrijwilliger")

    resp = client.get("/kassa/tellen")
    assert resp.status_code == 200


def test_vrijwilliger_zonder_voorraad_sectie_ziet_geen_boeken_in_zijbalk(client, db):
    _maak_vrijwilliger(db, "kassa_only", "kassa")
    _login(client, "kassa_only")

    resp = client.get("/")
    assert resp.status_code == 200
    assert b'href="/boeken"' not in resp.data
    assert b'href="/kassa/tellen"' in resp.data


def test_beheerder_omzeilt_secties_altijd(client, csrf):
    resp = client.post(
        "/login", data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": csrf}
    )
    assert resp.status_code == 302

    resp = client.get("/kassa/tellen")
    assert resp.status_code == 200
    resp = client.get("/keuken")
    assert resp.status_code == 200


def test_beheerder_kan_secties_van_vrijwilliger_wijzigen(client, db):
    _maak_vrijwilliger(db, "wisselend", "kassa")
    csrf = stel_csrf_token_in(client)
    resp = client.post(
        "/login", data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": csrf}
    )
    assert resp.status_code == 302

    gebruiker = db.execute("SELECT id FROM gebruikers WHERE naam = 'wisselend'").fetchone()
    csrf = stel_csrf_token_in(client)
    resp = client.post(
        f"/accounts/{gebruiker['id']}/secties",
        data={"secties": ["voorraad", "keuken"], "csrf_token": csrf},
    )
    assert resp.status_code == 302

    bijgewerkt = db.execute(
        "SELECT secties FROM gebruikers WHERE id = ?", (gebruiker["id"],)
    ).fetchone()
    assert set(bijgewerkt["secties"].split(",")) == {"voorraad", "keuken"}


def test_vrijwilliger_kan_secties_niet_zelf_wijzigen(client, db):
    _maak_vrijwilliger(db, "zelfbediening", "kassa")
    _login(client, "zelfbediening")

    gebruiker = db.execute("SELECT id FROM gebruikers WHERE naam = 'zelfbediening'").fetchone()
    csrf = stel_csrf_token_in(client)
    resp = client.post(
        f"/accounts/{gebruiker['id']}/secties",
        data={"secties": ["voorraad", "kassa", "keuken", "stemmen"], "csrf_token": csrf},
        follow_redirects=True,
    )
    assert b"alleen voor beheerders" in resp.data
    ongewijzigd = db.execute(
        "SELECT secties FROM gebruikers WHERE id = ?", (gebruiker["id"],)
    ).fetchone()
    assert ongewijzigd["secties"] == "kassa"
