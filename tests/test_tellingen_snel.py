"""Het tellingenoverzicht staat meteen klaar; de cijfers uit het voorspelmodel komen er na het laden bij."""

import pytest
from test_secties_rechten import _login, _maak_vrijwilliger

import routes.tellen.tellingen as tellingen_routes

CIJFERS = "/tellingen/cijfers"


@pytest.fixture
def zonder_model(monkeypatch):
    """Maakt zichtbaar of een pagina het voorspelmodel aanroept: dat mag het tellingenoverzicht zelf niet meer."""
    def mag_niet(*args, **kwargs):
        raise AssertionError("het tellingenoverzicht mag het voorspelmodel niet zelf aanroepen")

    monkeypatch.setattr(tellingen_routes, "omzet_per_week_berekend", mag_niet)
    monkeypatch.setattr(tellingen_routes, "maak_prognose", mag_niet)


def test_de_pagina_rekent_het_voorspelmodel_niet_zelf_uit(ingelogde_client, zonder_model):
    resp = ingelogde_client.get("/tellingen")
    tekst = resp.data.decode()
    assert resp.status_code == 200 and "Alle tellingen" in tekst
    assert f'data-lazy-bron="{CIJFERS}"' in tekst and "worden berekend" in tekst  # de plek voor de cijfers, tot ze er zijn
    assert "Verwachting &amp; trend" in tekst


def test_de_handterminalpagina_ook_niet(ingelogde_client, zonder_model):
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/tellingen")
    tekst = resp.data.decode()
    assert resp.status_code == 200 and f'data-lazy-bron="{CIJFERS}"' in tekst
    assert "pda-kop-menuknop" in tekst and 'class="app-zijbalk"' not in tekst  # echt de handterminal-weergave


def test_het_deel_met_de_cijfers_toont_beide_kaarten(ingelogde_client):
    tekst = ingelogde_client.get(CIJFERS).data.decode()
    assert "Verwachting &amp; trend" in tekst and "Omzet per week" in tekst
    assert "<html" not in tekst  # alleen de kaarten, geen hele pagina


def test_het_deel_met_de_cijfers_voor_de_handterminal(ingelogde_client):
    ingelogde_client.get("/weergave/pda")
    tekst = ingelogde_client.get(CIJFERS).data.decode()
    assert "Omzet per week" in tekst and "<html" not in tekst and "pda-kopje" in tekst


def test_gaat_het_voorspelmodel_stuk_dan_blijven_de_cijfers_werken(ingelogde_client, monkeypatch):
    def stuk(db, dagen=7):
        raise RuntimeError("kapot")

    monkeypatch.setattr(tellingen_routes, "maak_prognose", stuk)
    resp = ingelogde_client.get(CIJFERS)
    assert resp.status_code == 200 and "Omzet per week" in resp.data.decode()


def test_de_cijfers_vragen_inloggen(client):
    resp = client.get(CIJFERS)
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_wie_de_tellingen_niet_mag_zien_krijgt_ook_de_cijfers_niet(client, db):
    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    _login(client, "keukenhulp")
    resp = client.get(CIJFERS, follow_redirects=True)
    assert "niet beschikbaar voor jouw account" in resp.data.decode()
    assert "Omzet per week" not in resp.data.decode()


def test_het_dashboard_en_de_tellingen_gebruiken_dezelfde_loader(ingelogde_client, app):
    from pathlib import Path

    js = (Path(app.root_path) / "static" / "gedeeld.js").read_text()
    assert "data-lazy-bron" in js and "data-lazy-status" in js
    assert 'data-lazy-bron="/dashboard/omzettrend"' in ingelogde_client.get("/").data.decode()
    assert "fetch(kaart.dataset.bron" not in ingelogde_client.get("/").data.decode()  # geen eigen loader meer in het overzicht
