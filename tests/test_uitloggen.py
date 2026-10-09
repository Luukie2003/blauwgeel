from werkzeug.security import generate_password_hash

from conftest import stel_csrf_token_in as _csrf
from database import WACHTWOORD_HASH_METHODE
from helpers import genereer_wachtwoord_token


def _maak_account(db, naam, rol="vrijwilliger", wachtwoord="geheim123"):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) VALUES (?, ?, ?, 'voorraad', '2026-01-01 10:00')",
        (naam, generate_password_hash(wachtwoord, method=WACHTWOORD_HASH_METHODE), rol),
    )
    db.commit()
    return db.execute("SELECT id FROM gebruikers WHERE naam = ?", (naam,)).fetchone()["id"]


def _toestel(app, naam, wachtwoord="geheim123"):
    """Een apart 'toestel': een eigen client met een eigen sessie."""
    client = app.test_client()
    resp = client.post("/login", data={"naam": naam, "wachtwoord": wachtwoord, "csrf_token": _csrf(client)})
    assert resp.status_code == 302
    return client


def _ingelogd(client):
    resp = client.get("/", follow_redirects=False)
    return resp.status_code == 200


def _post(client, pad, **data):
    return client.post(pad, data={"csrf_token": _csrf(client), **data})


def test_inloggen_onthoudt_de_sessieversie(app, db):
    _maak_account(db, "piet")
    client = _toestel(app, "piet")
    with client.session_transaction() as sess:
        assert sess["sessie_versie"] == 0


def test_andere_toestellen_uitloggen_laat_dit_toestel_ingelogd(app, db):
    _maak_account(db, "piet")
    telefoon, laptop = _toestel(app, "piet"), _toestel(app, "piet")
    assert _ingelogd(telefoon) and _ingelogd(laptop)

    resp = _post(laptop, "/account/uitloggen-elders")

    assert resp.status_code == 302
    assert _ingelogd(laptop)
    oud = telefoon.get("/", follow_redirects=False)
    assert oud.status_code == 302 and "/login" in oud.headers["Location"]
    assert "uitgelogd" in telefoon.get("/login").data.decode().lower()  # uitleg waarom


def test_na_opnieuw_inloggen_werkt_een_toestel_weer(app, db):
    _maak_account(db, "piet")
    telefoon, laptop = _toestel(app, "piet"), _toestel(app, "piet")
    _post(laptop, "/account/uitloggen-elders")
    assert not _ingelogd(telefoon)

    telefoon = _toestel(app, "piet")
    assert _ingelogd(telefoon) and _ingelogd(laptop)


def test_een_nieuw_wachtwoord_logt_de_andere_toestellen_uit(app, db):
    _maak_account(db, "piet")
    telefoon, laptop = _toestel(app, "piet"), _toestel(app, "piet")

    _post(
        laptop, "/account/wachtwoord",
        huidig_wachtwoord="geheim123", nieuw_wachtwoord="nieuw-geheim", nieuw_wachtwoord_herhaald="nieuw-geheim",
    )

    assert _ingelogd(laptop)
    assert not _ingelogd(telefoon)


def test_een_wachtwoord_instellen_via_een_link_logt_oude_sessies_uit(app, db):
    gebruiker_id = _maak_account(db, "piet")
    oude_sessie = _toestel(app, "piet")
    token = genereer_wachtwoord_token(db, gebruiker_id, geldig_uren=24)

    nieuw = app.test_client()
    resp = nieuw.post(
        f"/wachtwoord-instellen/{token}",
        data={"csrf_token": _csrf(nieuw), "nieuw_wachtwoord": "nieuw-geheim", "nieuw_wachtwoord_herhaald": "nieuw-geheim"},
    )

    assert resp.status_code == 302
    assert _ingelogd(nieuw)  # wie het wachtwoord instelt is meteen ingelogd
    assert not _ingelogd(oude_sessie)


def test_beheerder_kan_een_account_overal_uitloggen(app, ingelogde_client, db):
    gebruiker_id = _maak_account(db, "piet")
    telefoon = _toestel(app, "piet")
    assert _ingelogd(telefoon)

    resp = _post(ingelogde_client, f"/accounts/{gebruiker_id}/overal-uitloggen")

    assert resp.status_code == 302
    assert not _ingelogd(telefoon)
    assert _ingelogd(ingelogde_client)
    # ... en piet kan gewoon opnieuw inloggen
    assert _ingelogd(_toestel(app, "piet"))


def test_een_beheerder_sluit_zichzelf_niet_buiten(ingelogde_client, db):
    admin_id = db.execute("SELECT id FROM gebruikers WHERE naam = 'admin'").fetchone()["id"]
    _post(ingelogde_client, f"/accounts/{admin_id}/overal-uitloggen")
    assert _ingelogd(ingelogde_client)


def test_overal_uitloggen_van_een_onbekend_account(ingelogde_client):
    resp = _post(ingelogde_client, "/accounts/99999/overal-uitloggen")
    assert resp.status_code == 302
    assert _ingelogd(ingelogde_client)


def test_overal_uitloggen_van_een_ander_account_is_alleen_voor_beheerders(app, db):
    doel = _maak_account(db, "slachtoffer")
    _maak_account(db, "vrijwilliger")
    vrijwilliger = _toestel(app, "vrijwilliger")
    slachtoffer = _toestel(app, "slachtoffer")

    resp = _post(vrijwilliger, f"/accounts/{doel}/overal-uitloggen")

    assert resp.status_code == 302 and _ingelogd(slachtoffer)


def test_sessies_van_voor_deze_functie_blijven_geldig(app, db):
    """Wie al ingelogd was toen dit live ging heeft nog geen sessieversie: dat telt als 0 en dus als geldig."""
    _maak_account(db, "piet")
    client = _toestel(app, "piet")
    with client.session_transaction() as sess:
        del sess["sessie_versie"]
    assert _ingelogd(client)


def test_een_geblokkeerd_account_wordt_nog_steeds_buitengesloten(app, db):
    gebruiker_id = _maak_account(db, "piet")
    client = _toestel(app, "piet")
    db.execute("UPDATE gebruikers SET actief = 0 WHERE id = ?", (gebruiker_id,))
    db.commit()
    assert not _ingelogd(client)


def test_het_staat_in_het_logboek(app, ingelogde_client, db):
    gebruiker_id = _maak_account(db, "piet")
    _post(ingelogde_client, f"/accounts/{gebruiker_id}/overal-uitloggen")
    _post(ingelogde_client, "/account/uitloggen-elders")
    acties = {r["endpoint"] for r in db.execute("SELECT endpoint FROM logboek")}
    assert {"account_overal_uitloggen", "account_andere_toestellen_uitloggen"} <= acties


def test_de_knoppen_staan_op_de_pagina_s(ingelogde_client, db):
    _maak_account(db, "piet")
    assert "Uitloggen op alle andere toestellen" in ingelogde_client.get("/account/voorkeuren").data.decode()
    assert "Overal uitloggen" in ingelogde_client.get("/accounts").data.decode()
