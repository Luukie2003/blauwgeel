"""Het voorspelmodel bewaart zijn uitkomst ook op schijf, zodat meer serverprocessen (en een nieuwe start) het niet
allemaal zelf opnieuw hoeven uit te rekenen."""

import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from test_seizoensrapport import _product, _weekelijkse_tellingen

import voorspelling

NU = datetime(2026, 10, 8, 12, 0)


@pytest.fixture
def schijf(monkeypatch, db, app):
    """Bewaren aan (geheugen en schijf), met een teller van hoe vaak het model echt wordt uitgerekend."""
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    monkeypatch.setattr(voorspelling, "SCHIJF_AAN", True)
    voorspelling.wis_bewaarde_resultaten()
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 6, 27), tot=date(2026, 10, 3))
    aantal = {"model": 0}
    echt = voorspelling._prognose_fit

    def geteld(*a, **k):
        aantal["model"] += 1
        return echt(*a, **k)

    monkeypatch.setattr(voorspelling, "_prognose_fit", geteld)
    map_ = Path(app.config["DATABASE"]).parent / "voorspelling_cache"
    yield {"aantal": aantal, "map": map_, "product": pils}
    voorspelling.wis_bewaarde_resultaten()


def _nieuw_proces():
    """Zoals een ander serverproces: geheugen leeg, schijf niet."""
    voorspelling.wis_bewaarde_resultaten()


def test_de_uitkomst_komt_ook_op_schijf(db, schijf):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    bestanden = list(schijf["map"].glob("*.pkl"))
    assert bestanden and all(b.stat().st_size > 0 for b in bestanden)
    assert not list(schijf["map"].glob("*.tmp"))  # geen halve bestanden achtergelaten


def test_een_ander_proces_gebruikt_het_bestand_in_plaats_van_opnieuw_te_rekenen(db, schijf):
    eerste = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert schijf["aantal"]["model"] == 1
    _nieuw_proces()
    tweede = voorspelling.maak_prognose(db, dagen=7, nu=NU + timedelta(minutes=5))
    assert schijf["aantal"]["model"] == 1  # niet opnieuw gerekend
    assert tweede["totaal"] == eerste["totaal"]
    assert [p["verwacht"] for p in tweede["producten"]] == [p["verwacht"] for p in eerste["producten"]]


def test_de_omzet_per_week_en_de_verdeling_worden_ook_gedeeld(db, schijf):
    eerste = voorspelling.omzet_per_week(db, NU)
    _nieuw_proces()
    assert voorspelling.omzet_per_week(db, NU) == eerste


def test_veranderde_gegevens_geven_een_nieuwe_berekening(db, schijf):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    db.execute("UPDATE telling_regels SET verkocht = verkocht + 5 WHERE id = (SELECT MAX(id) FROM telling_regels)")
    db.commit()
    _nieuw_proces()
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert schijf["aantal"]["model"] == 2  # de vingerafdruk klopte niet meer: het oude bestand telt niet


def test_het_model_geldt_de_hele_kantinedag_ook_voor_een_ander_proces(db, schijf):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    _nieuw_proces()
    voorspelling.maak_prognose(db, dagen=14, nu=NU + timedelta(hours=3))  # ander uur, andere periode
    assert schijf["aantal"]["model"] == 1
    _nieuw_proces()
    voorspelling.maak_prognose(db, dagen=7, nu=NU + timedelta(hours=25))  # de volgende kantinedag
    assert schijf["aantal"]["model"] == 2


def test_een_nieuwe_versie_van_de_site_gebruikt_oude_bestanden_niet(db, schijf, monkeypatch):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    _nieuw_proces()
    monkeypatch.setattr(voorspelling, "SCHIJF_VERSIE", voorspelling.SCHIJF_VERSIE + 1)
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert schijf["aantal"]["model"] == 2
    import wijzigingen

    _nieuw_proces()
    monkeypatch.setattr(wijzigingen, "HUIDIGE_VERSIE", "99.0.0")  # ook een nieuwe uitgave van de site
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert schijf["aantal"]["model"] == 3


def test_een_kapot_bestand_wordt_gewoon_opnieuw_gerekend_en_vervangen(db, schijf):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    for bestand in schijf["map"].glob("*.pkl"):
        bestand.write_bytes(b"dit is geen pickle")
    _nieuw_proces()
    uitkomst = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert uitkomst["beschikbaar"] and schijf["aantal"]["model"] == 2
    _nieuw_proces()
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert schijf["aantal"]["model"] == 2  # het vervangen bestand is weer goed


def test_niet_kunnen_schrijven_laat_het_rekenen_niet_mislukken(db, schijf, monkeypatch):
    def stuk(*a, **k):
        raise OSError("schijf vol")

    monkeypatch.setattr(os, "replace", stuk)
    assert voorspelling.maak_prognose(db, dagen=7, nu=NU)["beschikbaar"]


def test_zonder_schijf_aan_wordt_er_niets_geschreven(db, schijf, monkeypatch):
    monkeypatch.setattr(voorspelling, "SCHIJF_AAN", False)
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert not schijf["map"].exists() or not list(schijf["map"].glob("*.pkl"))


def test_een_database_in_het_geheugen_krijgt_geen_bestanden(schijf):
    assert voorspelling._schijf_pad(("", "x", (), 1, 1, "v")) is None


def test_oude_bestanden_worden_opgeruimd(db, schijf):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    oud = schijf["map"] / "heel-oud.pkl"
    oud.write_bytes(b"x")
    drie_dagen_en_meer = time.time() - 4 * 24 * 3600
    os.utime(oud, (drie_dagen_en_meer, drie_dagen_en_meer))
    restje = schijf["map"] / "half.tmp"
    restje.write_bytes(b"x")
    os.utime(restje, (time.time() - 7200, time.time() - 7200))
    voorspelling.maak_prognose(db, dagen=14, nu=NU)  # nog een uitkomst schrijven doet het opruimen
    assert not oud.exists() and not restje.exists()


def test_de_map_blijft_klein(db, schijf, monkeypatch):
    monkeypatch.setattr(voorspelling, "SCHIJF_MAX_BESTANDEN", 3)
    for uur in range(8):
        voorspelling.verdeling(db, NU + timedelta(hours=uur))
    assert len(list(schijf["map"].glob("*.pkl"))) <= 3


def test_sqlite_rijen_worden_gewone_dicts_en_blijven_bruikbaar(db, schijf):
    uitkomst = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    product = uitkomst["producten"][0]["product"]
    assert isinstance(product, dict) and product["naam"] == "Pils"
    assert isinstance(voorspelling._gewone_typen(db.execute("SELECT 1 AS een").fetchone()), dict)
    assert voorspelling._gewone_typen({"a": [(1, {2})]}) == {"a": [(1, {2})]}


def test_de_pagina_s_geven_hetzelfde_antwoord_na_het_laden_van_schijf(ingelogde_client, db, schijf):
    voor = ingelogde_client.get("/prognose/resultaat").data
    _nieuw_proces()
    na = ingelogde_client.get("/prognose/resultaat").data
    assert voor == na


def test_de_cachemap_staat_in_gitignore():
    assert "voorspelling_cache/" in (Path(__file__).parent.parent / ".gitignore").read_text()
