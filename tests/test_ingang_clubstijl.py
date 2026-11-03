"""2.2: de pagina's om binnen te komen in de clubstijl (base_inlog.html), Mijn voorkeuren met één knop, en de
offline-pagina die zonder verbinding alles uit de cache van de service worker haalt."""

import re
from pathlib import Path

from conftest import stel_csrf_token_in as _csrf

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_inlogpaginas_in_de_clubstijl(client):
    for pad in ("/login", "/wachtwoord-vergeten"):
        tekst = client.get(pad).data.decode()
        assert 'class="cs-ingang"' in tekst and "clubstijl.css" in tekst
    assert ">Inloggen</button>" in client.get("/login").data.decode()
    assert 'class="cs-terug"' in client.get("/wachtwoord-vergeten").data.decode()  # terug naar inloggen


def test_tablet_code_met_een_weg_terug_als_je_al_een_code_hebt(ingelogde_client):
    tekst = ingelogde_client.get("/tablet-code/instellen").data.decode()
    assert 'class="cs-ingang"' in tekst and "Terug naar het overzicht" in tekst  # de testaccounts hebben een code


def test_voorkeuren_mail_en_weergave_met_een_knop(ingelogde_client, db):
    ingelogde_client.post("/account/voorkeuren", data={
        "csrf_token": _csrf(ingelogde_client), "met_weergave": "1", "mail_factuur": "on", "eenvoudig": "on",
        "favoriet": ["boeken", "tellen"],
    })
    rij = db.execute("SELECT mail_factuur, eenvoudig, favorieten FROM gebruikers WHERE naam = 'admin'").fetchone()
    assert (rij["mail_factuur"], rij["eenvoudig"], rij["favorieten"]) == (1, 1, "boeken,tellen")

    # Zonder met_weergave (zoals vroeger) blijft de weergave staan.
    ingelogde_client.post("/account/voorkeuren", data={"csrf_token": _csrf(ingelogde_client)})
    rij = db.execute("SELECT mail_factuur, eenvoudig, favorieten FROM gebruikers WHERE naam = 'admin'").fetchone()
    assert (rij["mail_factuur"], rij["eenvoudig"], rij["favorieten"]) == (0, 1, "boeken,tellen")


def test_niet_gevonden_in_de_clubstijl_en_op_de_handterminal(ingelogde_client):
    resp = ingelogde_client.get("/bestaat-niet")
    assert resp.status_code == 404 and 'class="cs-titel"' in resp.data.decode()
    ingelogde_client.get("/weergave/pda")
    assert "Terug naar het overzicht" in ingelogde_client.get("/bestaat-niet").data.decode()


def test_offline_pagina_heeft_alles_in_de_cache(client):
    """Zonder verbinding kan /offline alleen gebruiken wat de service worker bewaart."""
    tekst = client.get("/offline").data.decode()
    assert 'rel="stylesheet"' not in tekst  # de stijl staat in de pagina zelf
    sw = (STATIC / "sw.js").read_text()
    for pad in re.findall(r'url\("(/static/[^"]+)"\)', tekst) + re.findall(r'src="(/static/[^"]+)"', tekst):
        assert f'"{pad}"' in sw, f"{pad} staat niet in de cache van de service worker"
