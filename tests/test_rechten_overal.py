"""De rechten van de site en de handterminal-app in één keer nagelopen (zie rechten.py): elk JSON-adres van de app
zegt 'niet ingelogd' of 'geen toegang' in plaats van door te verwijzen, wat bij een sectie hoort is dicht zonder die
sectie, wat voor beheerders is ook, en een gewijzigde rol of sectie geldt meteen."""

import re

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from rechten import BEHEERDER_ENDPOINTS, ENDPOINT_SECTIE


def _app_adressen(app):
    """(endpoint, methode, url) voor elk JSON-adres van de app, met 1 voor een id."""
    for regel in app.url_map.iter_rules():
        if not regel.endpoint.startswith(("api_app_", "api_factu")):
            continue
        url = re.sub(r"<[^>]+>", "1", regel.rule)
        for methode in sorted(regel.methods - {"HEAD", "OPTIONS"}):
            yield regel.endpoint, methode, url


def _vraag(client, methode, url):
    if methode == "GET":
        return client.get(url)
    return client.post(url, json={}, headers={"X-CSRF-Token": _csrf(client)})


def test_niet_ingelogd_geeft_overal_json(app):
    adressen = list(_app_adressen(app))
    assert len(adressen) > 50
    for endpoint, methode, url in adressen:
        resp = _vraag(app.test_client(), methode, url)
        assert resp.status_code == 401 and resp.get_json()["fout"] == "niet_ingelogd", (endpoint, methode)


@pytest.mark.parametrize("secties", ["", "voorraad", "kassa,keuken"])
def test_zonder_sectie_of_beheerder_is_het_dicht(app, db, secties):
    _maak_vrijwilliger(db, "hulp", secties)
    client = app.test_client()
    _login(client, "hulp")
    eigen = set(filter(None, secties.split(",")))
    for endpoint, methode, url in _app_adressen(app):
        if endpoint in BEHEERDER_ENDPOINTS:
            verwacht_dicht = True
        elif endpoint in ENDPOINT_SECTIE:
            verwacht_dicht = ENDPOINT_SECTIE[endpoint] not in eigen
        else:
            verwacht_dicht = False  # alleen inloggen: startscherm, prikbord, agenda, eigen taken
        resp = _vraag(client, methode, url)
        if verwacht_dicht:
            assert resp.status_code == 403 and resp.get_json()["fout"] == "geen_toegang", (endpoint, methode)
        else:
            assert resp.status_code != 403, (endpoint, methode)


def test_een_gewijzigde_sectie_geldt_meteen(app, ingelogde_client, db):
    """Ook in een sessie die nog weken loopt (Ingelogd blijven) en in de app."""
    _maak_vrijwilliger(db, "hulp", "voorraad,kassa")
    hulp = app.test_client()
    _login(hulp, "hulp")
    assert hulp.get("/api/app/kassa").status_code == 200 and hulp.get("/kassa/tellen").status_code == 200
    gid = db.execute("SELECT id FROM gebruikers WHERE naam = 'hulp'").fetchone()[0]
    ingelogde_client.post(f"/accounts/{gid}/secties", data={"csrf_token": _csrf(ingelogde_client), "secties": ["voorraad"]})
    assert db.execute("SELECT secties FROM gebruikers WHERE id = ?", (gid,)).fetchone()[0] == "voorraad"
    assert hulp.get("/api/app/kassa").status_code == 403
    assert hulp.get("/kassa/tellen").status_code == 302
    assert hulp.get("/api/app/start").get_json()["toegang"]["kassa"] is False


def test_een_beheerder_die_vrijwilliger_wordt_verliest_het_meteen(app, ingelogde_client, db):
    _maak_vrijwilliger(db, "tweede", "voorraad")
    db.execute("UPDATE gebruikers SET rol = 'beheerder' WHERE naam = 'tweede'")
    db.commit()
    tweede = app.test_client()
    _login(tweede, "tweede")
    assert tweede.get("/api/app/kluis").status_code == 200
    db.execute("UPDATE gebruikers SET rol = 'vrijwilliger' WHERE naam = 'tweede'")
    db.commit()
    assert tweede.get("/api/app/kluis").status_code == 403
    assert tweede.get("/api/app/start").get_json()["beheerder"] is False


def test_een_mededeling_verwijderen_mag_alleen_de_schrijver_of_een_beheerder(app, ingelogde_client, db):
    for naam in ("schrijver", "ander"):
        _maak_vrijwilliger(db, naam, "")
    mid = db.execute("INSERT INTO mededelingen (tekst, naam, datum) VALUES ('Koelkast lekt', 'schrijver', '2026-10-19 12:00')").lastrowid
    db.commit()
    ander = app.test_client()
    _login(ander, "ander")
    assert "/verwijderen" not in ander.get("/bijzonderheden").data.decode()
    ander.post(f"/bijzonderheden/{mid}/verwijderen", data={"csrf_token": _csrf(ander)})
    assert db.execute("SELECT 1 FROM mededelingen WHERE id = ?", (mid,)).fetchone()

    schrijver = app.test_client()
    _login(schrijver, "schrijver")
    assert f"/bijzonderheden/{mid}/verwijderen" in schrijver.get("/bijzonderheden").data.decode()
    schrijver.post(f"/bijzonderheden/{mid}/verwijderen", data={"csrf_token": _csrf(schrijver)})
    assert db.execute("SELECT 1 FROM mededelingen WHERE id = ?", (mid,)).fetchone() is None
