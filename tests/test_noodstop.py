"""De noodstop (noodstop.py): de hele site en de tv-schermen afsluiten, en alleen de eigenaar kan weer openen."""

import pytest
from werkzeug.security import generate_password_hash

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

import noodstop
from database import WACHTWOORD_HASH_METHODE

WACHTWOORD = "kantine123"  # van de beheerder in de tests (zie conftest.py)


def _dicht(client, wachtwoord=WACHTWOORD, reden="Vreemde inlogpogingen"):
    return client.post("/beheer/noodstop/dicht", data={"csrf_token": _csrf(client), "wachtwoord": wachtwoord, "reden": reden})


def _open(client, wachtwoord=WACHTWOORD, code=""):
    return client.post("/beheer/noodstop/open", data={"csrf_token": _csrf(client), "wachtwoord": wachtwoord, "code": code})


def _code(client, code, oude_code="", wachtwoord=WACHTWOORD):
    return client.post("/beheer/noodstop/code", data={
        "csrf_token": _csrf(client), "wachtwoord": wachtwoord, "oude_code": oude_code, "code": code, "code_herhalen": code})


def _tweede_beheerder(db, naam="beheerder2"):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op) VALUES (?, ?, 'beheerder', '2026-01-01 10:00')",
        (naam, generate_password_hash("test1234", method=WACHTWOORD_HASH_METHODE)),
    )
    db.commit()


# ---------- Wie mag het ----------


def test_de_beheerder_is_de_eigenaar(db):
    e = noodstop.eigenaar(db)
    assert e is not None and e[1] == "admin"


def test_een_andere_beheerder_kan_niet_bij_de_noodstop(client, db):
    _tweede_beheerder(db)
    _login(client, "beheerder2")
    assert client.get("/beheer/noodstop").headers["Location"].endswith("/")
    _dicht(client, wachtwoord="test1234")
    assert not noodstop.is_actief(db)
    assert "/beheer/noodstop" not in client.get("/").data.decode()  # ook niet in het menu


def test_eigenaar_ziet_de_noodstop_in_het_menu(ingelogde_client, db):
    assert "/beheer/noodstop" in ingelogde_client.get("/").data.decode()
    assert "Noodstop: alles afsluiten" in ingelogde_client.get("/beheer/noodstop").data.decode()


def test_afsluiten_vraagt_het_wachtwoord(ingelogde_client, db):
    _dicht(ingelogde_client, wachtwoord="fout")
    assert not noodstop.is_actief(db)


# ---------- Afgesloten ----------


@pytest.fixture
def afgesloten(app, ingelogde_client, db):
    """Een vrijwilliger die al ingelogd was, en daarna de noodstop van de eigenaar."""
    _maak_vrijwilliger(db, "vrijwilliger1", "voorraad")
    vrijwilliger = app.test_client()
    _login(vrijwilliger, "vrijwilliger1")
    assert vrijwilliger.get("/").status_code == 200
    _dicht(ingelogde_client)
    assert noodstop.is_actief(db)
    return vrijwilliger


def test_iedereen_eruit_behalve_de_eigenaar(afgesloten, ingelogde_client):
    resp = afgesloten.get("/")
    assert resp.status_code == 503 and "Tijdelijk afgesloten" in resp.data.decode()
    tekst = ingelogde_client.get("/").data.decode()  # de eigenaar werkt gewoon door
    assert "Noodstop actief sinds" in tekst


def test_alleen_de_eigenaar_kan_inloggen(app, afgesloten, db):
    anders = app.test_client()
    csrf = _csrf(anders)
    resp = anders.post("/login", data={"naam": "vrijwilliger1", "wachtwoord": "test1234", "csrf_token": csrf})
    assert resp.status_code == 200 and "tijdelijk afgesloten" in resp.data.decode()
    eigenaar = app.test_client()
    resp = eigenaar.post("/login", data={"naam": "admin", "wachtwoord": WACHTWOORD, "csrf_token": _csrf(eigenaar)})
    assert resp.status_code == 302 and eigenaar.get("/beheer/noodstop").status_code == 200


def test_tv_schermen_tonen_het_vergrendel_scherm(app, afgesloten):
    tv = app.test_client()
    for url in ("/kiosk/scherm", "/kiosk/prijzen", "/kiosk/tv"):
        resp = tv.get(url)
        assert resp.status_code == 200 and "Systeem <span>vergrendeld</span>" in resp.data.decode(), url
    assert tv.get("/kiosk/scherm/versie").get_json()["versie"] == "noodstop"
    assert tv.get("/noodstop/status").get_json() == {"actief": True}


def test_publieke_paginas_en_apps_zijn_dicht(app, afgesloten):
    bezoeker = app.test_client()
    for url in ("/club-van-20/doe-mee", "/wachtwoord-vergeten", "/weergave/pda"):
        assert bezoeker.get(url).status_code == 503, url
    resp = bezoeker.post("/api/tablet-code/inloggen", json={"code": "999999"})
    assert resp.status_code == 503 and resp.get_json()["fout"] == "noodstop"
    assert bezoeker.get("/status").status_code == 200  # het live-zet-script moet nog kunnen kijken


# ---------- Weer openen ----------


def test_noodcode_instellen(ingelogde_client, db):
    assert "nog geen noodcode" in ingelogde_client.get("/beheer/noodstop").data.decode()
    _code(ingelogde_client, "kort")
    assert not noodstop.toestand(db)["code_ingesteld"]
    _code(ingelogde_client, "geheim-123", wachtwoord="fout")
    assert not noodstop.toestand(db)["code_ingesteld"]
    _code(ingelogde_client, "geheim-123")
    assert noodstop.code_klopt(db, "geheim-123")
    _code(ingelogde_client, "nieuw-456", oude_code="verkeerd")  # veranderen vraagt de huidige code
    assert noodstop.code_klopt(db, "geheim-123")
    _code(ingelogde_client, "nieuw-456", oude_code="geheim-123")
    assert noodstop.code_klopt(db, "nieuw-456")


def test_openen_met_wachtwoord_en_noodcode(afgesloten, ingelogde_client, db):
    noodstop.zet_code(db, "geheim-123")
    _open(ingelogde_client, code="fout")
    assert noodstop.is_actief(db)
    _open(ingelogde_client, wachtwoord="fout", code="geheim-123")
    assert noodstop.is_actief(db)
    _open(ingelogde_client, code="geheim-123")
    assert not noodstop.is_actief(db)
    # De vrijwilliger moet opnieuw inloggen: die sessie was bij het afsluiten al ongeldig.
    assert afgesloten.get("/").headers.get("Location", "").startswith("/login")


def test_te_veel_foute_pogingen(afgesloten, ingelogde_client, db):
    noodstop.zet_code(db, "geheim-123")
    for _ in range(noodstop.MAX_POGINGEN):
        _open(ingelogde_client, code="fout")
    assert noodstop.wachten(db) > 0
    _open(ingelogde_client, code="geheim-123")  # ook met de goede code eerst wachten
    assert noodstop.is_actief(db)
    assert "Te veel foute pogingen" in ingelogde_client.get("/beheer/noodstop").data.decode()


def test_logboek_houdt_bij_wie_het_deed(afgesloten, ingelogde_client, db):
    _open(ingelogde_client)
    acties = [r[0] for r in db.execute("SELECT actie FROM logboek WHERE endpoint LIKE 'noodstop%' ORDER BY id")]
    assert acties == ["Noodstop: site en schermen afgesloten", "Noodstop: site en schermen weer geopend"]


# ---------- Op de server ----------


def test_vanaf_de_server_openen_en_sluiten(app, db, monkeypatch, capsys):
    monkeypatch.setattr(noodstop, "DB_PAD", app.config["DATABASE"])
    noodstop._console(["dicht"])
    assert noodstop.is_actief(db)
    noodstop.zet_code(db, "geheim-123")
    noodstop._console(["code-wissen"])
    noodstop._console(["open"])
    assert not noodstop.is_actief(db) and not noodstop.toestand(db)["code_ingesteld"]
    noodstop._console(["status"])
    assert "Eigenaar: admin" in capsys.readouterr().out


def test_eigenaar_veranderen_kan_alleen_op_de_server(db):
    _tweede_beheerder(db)
    assert noodstop.maak_eigenaar(db, "beheerder2") is None
    assert noodstop.eigenaar(db)[1] == "beheerder2"
    assert noodstop.maak_eigenaar(db, "bestaat-niet")


def test_live_zetten_blijft_mogelijk_tijdens_een_noodstop(app, afgesloten, db, monkeypatch):
    import mail
    import rooktest

    monkeypatch.setattr(mail, "MAIL_BESCHIKBAAR", False)
    uitkomst = rooktest.draai(app.config["DATABASE"])
    assert uitkomst["afgerond"] and uitkomst["fouten"] == []
    assert noodstop.is_actief(db)  # de echte site blijft dicht


# ---------- De schermen gaan altijd op slot ----------


def test_schermen_ook_op_slot_als_de_eigenaar_daar_is_ingelogd(afgesloten, ingelogde_client):
    """Een tv-scherm dat via een ingelogde browser (of de tablet-app met de code van de eigenaar) draait."""
    for url in ("/kiosk/scherm", "/kiosk/prijzen", "/kiosk/tv"):
        assert "Systeem <span>vergrendeld</span>" in ingelogde_client.get(url).data.decode(), url
    assert ingelogde_client.get("/kiosk/prijzen/versie").get_json()["versie"] == "noodstop"
    assert ingelogde_client.get("/beheer/noodstop").status_code == 200  # de eigenaar kan zelf wel verder


def test_een_oude_sessie_van_de_eigenaar_komt_er_niet_meer_in(app, db):
    """Op een tweede toestel ingelogd als eigenaar, daarna de noodstop vanaf het eerste: het tweede is uitgelogd, ook
    op publieke pagina's."""
    eerste, tweede = app.test_client(), app.test_client()
    for client in (eerste, tweede):
        assert client.post("/login", data={"naam": "admin", "wachtwoord": WACHTWOORD, "csrf_token": _csrf(client)}).status_code == 302
    _dicht(eerste)
    assert tweede.get("/club-van-20/doe-mee").status_code == 503
    assert "Tijdelijk afgesloten" in tweede.get("/").data.decode()
    assert eerste.get("/").status_code == 200
