"""Bestellijst en Prognose staan meteen klaar; het rekenwerk uit het voorspelmodel komt er na het laden bij."""

from datetime import datetime, timedelta

import pytest
from test_secties_rechten import _login, _maak_vrijwilliger
from test_voorspelling import _bouw_geschiedenis, _product

import routes.prognose as prognose_routes
import voorspelling
import routes.bestellijst as bestellijst_routes

LAZY_PAGINA = {
    "/bestellijst": "/bestellijst/voorspeld",
    "/prognose": "/prognose/resultaat",
}
# Op de computer haalt de bestellijst de prognose op als gegevens, voor in de tabel 'Voorgesteld om te bestellen'.
LAZY_COMPUTER = {**LAZY_PAGINA, "/bestellijst": "/bestellijst/prognose"}


@pytest.fixture
def zonder_model(monkeypatch):
    """Maakt zichtbaar of een pagina het voorspelmodel aanroept: dat mogen deze pagina's zelf niet meer."""
    def mag_niet(*args, **kwargs):
        raise AssertionError("de pagina mag het voorspelmodel niet zelf aanroepen")

    monkeypatch.setattr(prognose_routes, "maak_prognose", mag_niet)
    monkeypatch.setattr(voorspelling, "maak_prognose", mag_niet)
    monkeypatch.setattr(bestellijst_routes, "bereken_voorspelde_tekorten", mag_niet)


@pytest.mark.parametrize("pagina, deel", LAZY_COMPUTER.items())
def test_de_pagina_rekent_het_voorspelmodel_niet_zelf_uit(ingelogde_client, zonder_model, pagina, deel):
    resp = ingelogde_client.get(pagina)
    tekst = resp.data.decode()
    assert resp.status_code == 200
    if pagina == "/bestellijst":
        assert f"fetch('{deel}'" in tekst and "De prognose wordt berekend" in tekst
    else:
        assert f'data-lazy-bron="{deel}' in tekst and "data-lazy-status" in tekst  # de plek voor het rekenwerk, tot het er is


@pytest.mark.parametrize("pagina, deel", LAZY_PAGINA.items())
def test_de_pagina_ook_op_de_handterminal(ingelogde_client, zonder_model, pagina, deel):
    ingelogde_client.get("/weergave/pda")
    tekst = ingelogde_client.get(pagina).data.decode()
    assert "pda-kop-menuknop" in tekst and f'data-lazy-bron="{deel}' in tekst


def test_het_deel_van_de_bestellijst_is_leeg_zonder_tekorten_en_toont_ze_anders(ingelogde_client, db):
    assert "Voorspelde tekorten" not in ingelogde_client.get("/bestellijst/voorspeld").data.decode()  # niets verwacht: leeg
    pid = _product(db, "Pils krat", voorraad=30, factor=24, besteleenheid="krat")
    _bouw_geschiedenis(
        db, {pid: 40},
        tijdstippen=[datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=7 * (6 - i)) for i in range(7)],
    )
    tekst = ingelogde_client.get("/bestellijst/voorspeld").data.decode()
    assert "Voorspelde tekorten" in tekst and "Pils krat" in tekst and "<html" not in tekst
    ingelogde_client.get("/weergave/pda")
    pda = ingelogde_client.get("/bestellijst/voorspeld").data.decode()
    assert "Pils krat" in pda and "pda-kaartje" in pda and "<html" not in pda


def test_de_prognose_krijgt_horizon_en_categorie_mee_naar_het_deel(ingelogde_client):
    tekst = ingelogde_client.get("/prognose?dagen=14&categorie=Bier").data.decode()
    assert 'data-lazy-bron="/prognose/resultaat?dagen=14&amp;categorie=Bier"' in tekst
    assert 'data-lazy-bron="/prognose/resultaat?dagen=7"' in ingelogde_client.get("/prognose?dagen=99").data.decode()
    assert "Komende 14 dagen" in tekst  # de knoppen staan wel meteen op de pagina


def test_de_instellingen_van_de_prognose_staan_meteen_op_de_pagina(ingelogde_client, zonder_model):
    tekst = ingelogde_client.get("/prognose").data.decode()
    assert "Verkoopdagen" in tekst and "Uitzonderingen" in tekst


def test_het_deel_met_het_rekenwerk_toont_de_categoriekeuze(ingelogde_client, db):
    pils = _product(db, "Heineken krat", voorraad=40)
    _bouw_geschiedenis(
        db, {pils: 30},
        tijdstippen=[datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=7 * (8 - i)) for i in range(9)],
    )
    tekst = ingelogde_client.get("/prognose/resultaat?dagen=7").data.decode()
    assert 'name="categorie"' in tekst and "Dag voor dag" in tekst and "<html" not in tekst


@pytest.mark.parametrize("pad", ["/bestellijst/voorspeld", "/prognose/resultaat", "/voorspelling/opwarmen"])
def test_de_delen_vragen_inloggen_en_de_voorraadsectie(client, db, pad):
    assert client.get(pad).status_code == 302
    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    _login(client, "keukenhulp")
    resp = client.get(pad, follow_redirects=True)
    assert "niet beschikbaar voor jouw account" in resp.data.decode()


# ---------- Voorverwarmen vanaf het overzicht ----------


def test_voorverwarmen_laat_het_model_rekenen_en_geeft_niets_terug(ingelogde_client, monkeypatch):
    aangeroepen = []
    monkeypatch.setattr(prognose_routes, "maak_prognose", lambda db, dagen=7, **kw: aangeroepen.append(dagen))
    resp = ingelogde_client.get("/voorspelling/opwarmen")
    assert resp.status_code == 204 and resp.data == b"" and aangeroepen == [7]


def test_voorverwarmen_mislukt_stilletjes(ingelogde_client, monkeypatch):
    def stuk(db, dagen=7, **kw):
        raise RuntimeError("kapot")

    monkeypatch.setattr(prognose_routes, "maak_prognose", stuk)
    assert ingelogde_client.get("/voorspelling/opwarmen").status_code == 204


def test_voorverwarmen_maakt_de_pagina_daarna_snel(ingelogde_client, db, monkeypatch):
    """Na het voorverwarmen staat het resultaat in het geheugen: de bestellijst hoeft het model niet nog eens te rekenen."""
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    voorspelling.wis_bewaarde_resultaten()
    pid = _product(db, "Pils krat", voorraad=30, factor=24, besteleenheid="krat")
    _bouw_geschiedenis(
        db, {pid: 40},
        tijdstippen=[datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=7 * (6 - i)) for i in range(7)],
    )
    aantal = {"model": 0}
    echt = voorspelling._prognose_model

    def geteld(*a, **k):
        aantal["model"] += 1
        return echt(*a, **k)

    monkeypatch.setattr(voorspelling, "_prognose_model", geteld)
    try:
        ingelogde_client.get("/voorspelling/opwarmen")
        assert aantal["model"] == 1
        assert "Pils krat" in ingelogde_client.get("/bestellijst/voorspeld").data.decode()
        assert ingelogde_client.get("/prognose/resultaat").status_code == 200
        assert aantal["model"] == 1  # niet opnieuw gerekend
    finally:
        voorspelling.wis_bewaarde_resultaten()


def test_het_overzicht_warmt_het_model_voor_wie_de_voorraad_mag_zien(ingelogde_client, app, db):
    tekst = ingelogde_client.get("/").data.decode()
    assert "lazy-klaar" in tekst and 'fetch(\'/voorspelling/opwarmen\'' in tekst

    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    keuken = app.test_client()
    _login(keuken, "keukenhulp")
    assert "voorspelling/opwarmen" not in keuken.get("/").data.decode()  # geen voorraadrechten: niets te warmen


def test_de_gedeelde_loader_geeft_een_seintje_als_alles_geladen_is(app):
    from pathlib import Path

    js = (Path(app.root_path) / "static" / "gedeeld.js").read_text()
    assert 'new Event("lazy-klaar")' in js and "Promise.all(laden)" in js


@pytest.mark.parametrize(
    "pad", ["/bestellijst/voorspeld", "/prognose/resultaat", "/voorspelling/opwarmen", "/tellingen/cijfers", "/dashboard/omzettrend"]
)
def test_delen_van_een_pagina_tellen_niet_mee_als_paginabezoek(ingelogde_client, db, pad):
    voor = db.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0]
    ingelogde_client.get(pad)
    assert db.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0] == voor
    ingelogde_client.get("/prognose")  # een echte pagina wel
    assert db.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0] == voor + 1
