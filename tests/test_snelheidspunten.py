"""Snelheidspunten van 1.44.3: kleine productfoto's, de welkom-poll buiten de statistiek en bewaarde kiosk-versies."""

import os
import re
from types import SimpleNamespace

import pytest
from PIL import Image
from test_kiosk import _voeg_product_toe, _voeg_sponsor_toe

import helpers.afbeeldingen as afbeeldingen
from database.migraties import migreer_alles
from helpers import kleine_afbeelding
from routes.kiosk import gedeeld


@pytest.fixture
def fotomap(tmp_path, monkeypatch):
    map_ = tmp_path / "product_afbeeldingen"
    map_.mkdir()
    monkeypatch.setattr(afbeeldingen, "PRODUCT_AFBEELDINGEN_MAP", map_)
    return map_


def _foto(map_, naam, afmeting=(800, 800), modus="RGB"):
    """Een grote foto met ruis erin (zodat hij echt groot is, zoals een foto van een flesje)."""
    kleuren = {"RGB": 3, "RGBA": 4}[modus]
    Image.frombytes(modus, afmeting, os.urandom(afmeting[0] * afmeting[1] * kleuren)).save(map_ / naam)
    return map_ / naam


def _geef_product_foto(db, naam):
    product = db.execute("SELECT id FROM producten WHERE actief = 1 ORDER BY id LIMIT 1").fetchone()
    db.execute("UPDATE producten SET afbeelding = ? WHERE id = ?", (naam, product["id"]))
    db.commit()
    return product["id"]


# ---------- Kleine productfoto's ----------


def test_een_grote_foto_krijgt_een_veel_kleinere_kopie(fotomap):
    origineel = _foto(fotomap, "bier.png")

    pad = kleine_afbeelding("bier.png")

    assert pad == "klein/bier.webp"
    kopie = fotomap / pad
    with Image.open(kopie) as plaatje:
        assert plaatje.format == "WEBP" and max(plaatje.size) == 128
    assert kopie.stat().st_size < origineel.stat().st_size / 20


def test_het_middelgrote_formaat_is_groter(fotomap):
    _foto(fotomap, "bier.png")
    pad = kleine_afbeelding("bier.png", "middel")
    assert pad == "middel/bier.webp"
    with Image.open(fotomap / pad) as plaatje:
        assert max(plaatje.size) == 256


def test_staande_en_doorzichtige_foto_s_blijven_kloppen(fotomap):
    _foto(fotomap, "fles.png", afmeting=(400, 800), modus="RGBA")
    with Image.open(fotomap / kleine_afbeelding("fles.png")) as plaatje:
        assert plaatje.size == (64, 128)  # de verhouding blijft
        assert plaatje.mode == "RGBA"  # doorzichtig blijft doorzichtig


def test_zonder_foto_een_gif_of_een_kapot_bestand_blijft_de_naam_zoals_hij_was(fotomap):
    assert kleine_afbeelding(None) == "" and kleine_afbeelding("") == ""
    assert kleine_afbeelding("weg.png") == "weg.png"  # het bestand bestaat niet
    (fotomap / "bewegend.gif").write_bytes(b"GIF89a")
    assert kleine_afbeelding("bewegend.gif") == "bewegend.gif"  # een gif kan bewegen: laten staan
    (fotomap / "kapot.png").write_bytes(b"dit is geen plaatje")
    assert kleine_afbeelding("kapot.png") == "kapot.png"
    assert not list((fotomap / "klein").glob("*")) if (fotomap / "klein").exists() else True  # geen rommel achtergelaten


def test_een_bestaande_kopie_wordt_niet_opnieuw_gemaakt(fotomap, monkeypatch):
    _foto(fotomap, "bier.png")
    kleine_afbeelding("bier.png")

    def nooit(*args, **kwargs):
        raise AssertionError("de kopie bestaat al")

    monkeypatch.setattr(Image, "open", nooit)
    assert kleine_afbeelding("bier.png") == "klein/bier.webp"


def test_de_productenlijst_laadt_de_kleine_kopie(ingelogde_client, db, fotomap):
    _foto(fotomap, "abc123.png")
    _geef_product_foto(db, "abc123.png")

    tekst = ingelogde_client.get("/producten").data.decode()

    assert "product_afbeeldingen/klein/abc123.webp" in tekst
    assert "product_afbeeldingen/abc123.png" not in tekst  # het zware origineel niet meer


def test_een_enkele_grotere_foto_gebruikt_het_middelformaat(ingelogde_client, db, fotomap):
    _foto(fotomap, "abc123.png")
    product_id = _geef_product_foto(db, "abc123.png")
    tekst = ingelogde_client.get(f"/producten/{product_id}").data.decode()
    assert "product_afbeeldingen/middel/abc123.webp" in tekst and "product_afbeeldingen/abc123.png" not in tekst


def test_de_keuzelijst_van_boeken_geeft_de_kleine_kopie_aan_de_voorbeeldfoto(ingelogde_client, db, fotomap):
    _foto(fotomap, "abc123.png")
    _geef_product_foto(db, "abc123.png")
    tekst = ingelogde_client.get("/boeken").data.decode()
    assert 'data-afbeelding="klein/abc123.webp"' in tekst


def test_zoeken_op_de_handterminal_geeft_de_kleine_kopie(ingelogde_client, db, fotomap):
    _foto(fotomap, "abc123.png")
    product_id = _geef_product_foto(db, "abc123.png")
    naam = db.execute("SELECT naam FROM producten WHERE id = ?", (product_id,)).fetchone()["naam"]

    resultaten = ingelogde_client.get("/producten/zoeken", query_string={"q": naam}).get_json()["resultaten"]

    assert [r["afbeelding"] for r in resultaten if r["id"] == product_id] == ["klein/abc123.webp"]


# ---------- De welkom-poll van de kiosk ----------


def test_de_welkom_poll_telt_niet_als_paginabezoek(client, db):
    for _ in range(3):
        assert client.get("/kiosk/welkom").status_code == 200
    assert db.execute("SELECT COUNT(*) FROM paginabezoeken WHERE endpoint = 'kiosk_welkom'").fetchone()[0] == 0


def test_oude_welkom_polls_gaan_uit_de_statistiek_en_echte_bezoeken_blijven(app, db):
    for endpoint in ("kiosk_welkom", "kiosk_welkom", "dashboard"):
        db.execute(
            "INSERT INTO paginabezoeken (endpoint, weergave_modus, datum) VALUES (?, 'desktop', '2026-10-10 15:00')",
            (endpoint,),
        )
    db.commit()

    migreer_alles(db)
    db.commit()

    assert [r[0] for r in db.execute("SELECT endpoint FROM paginabezoeken")] == ["dashboard"]


# ---------- Bewaarde versies van de kiosk-schermen ----------


@pytest.fixture
def vaste_minuut(monkeypatch):
    """De klok staat stil, zodat een test niet toevallig over een minuutgrens heen rekent."""
    monkeypatch.setattr(gedeeld, "time", SimpleNamespace(time=lambda: 1_800_000_000))


def _rekenmachine(uitkomsten):
    aantal = {"keer": 0}

    def bereken():
        aantal["keer"] += 1
        return next(uitkomsten)

    return bereken, aantal


def test_een_uitkomst_wordt_bewaard_tot_de_database_verandert(app, db, vaste_minuut):
    bereken, aantal = _rekenmachine(iter(["een", "twee", "drie"]))

    assert gedeeld.bewaarde_uitkomst("proef", bereken) == "een"
    assert gedeeld.bewaarde_uitkomst("proef", bereken) == "een" and aantal["keer"] == 1

    db.execute("UPDATE kiosk_scherm_instellingen SET toon_sponsoren = 1 - toon_sponsoren WHERE id = 1")
    db.commit()

    assert gedeeld.bewaarde_uitkomst("proef", bereken) == "twee" and aantal["keer"] == 2


def test_na_een_minuut_wordt_er_opnieuw_gerekend_ook_zonder_wijziging(app, db, monkeypatch):
    bereken, aantal = _rekenmachine(iter(["een", "twee"]))
    monkeypatch.setattr(gedeeld, "time", SimpleNamespace(time=lambda: 1_800_000_000))
    gedeeld.bewaarde_uitkomst("proef2", bereken)
    monkeypatch.setattr(gedeeld, "time", SimpleNamespace(time=lambda: 1_800_000_061))
    assert gedeeld.bewaarde_uitkomst("proef2", bereken) == "twee" and aantal["keer"] == 2


def test_zonder_databasebestand_wordt_er_niets_bewaard(app, db, vaste_minuut):
    app.config["DATABASE"] = ":memory:"
    bereken, aantal = _rekenmachine(iter(["een", "twee"]))
    gedeeld.bewaarde_uitkomst("proef3", bereken)
    assert gedeeld.bewaarde_uitkomst("proef3", bereken) == "twee" and aantal["keer"] == 2


def test_de_dia_poll_bouwt_de_dia_s_niet_steeds_opnieuw(client, vaste_minuut, monkeypatch):
    import routes.kiosk.scherm as scherm

    echt = scherm._bouw_slides
    aantal = {"keer": 0}

    def geteld(db):
        aantal["keer"] += 1
        return echt(db)

    monkeypatch.setattr(scherm, "_bouw_slides", geteld)
    antwoorden = {client.get("/kiosk/scherm/versie").get_json()["versie"] for _ in range(4)}
    assert len(antwoorden) == 1 and aantal["keer"] == 1


def test_de_dia_poll_geeft_dezelfde_versie_als_het_scherm_en_ziet_een_wijziging(client, db, vaste_minuut):
    def op_scherm():
        return re.search(r"huidigeVersie = \"(\w+)\"", client.get("/kiosk/scherm").data.decode()).group(1)

    def poll():
        return client.get("/kiosk/scherm/versie").get_json()["versie"]

    assert op_scherm() == poll()
    voor = poll()
    _voeg_sponsor_toe(db, "Nieuwe sponsor")  # een nieuwe dia: het scherm moet herladen
    assert poll() != voor and op_scherm() == poll()


def test_de_prijzen_poll_rekent_niet_steeds_opnieuw_en_klopt_met_het_scherm(client, db, vaste_minuut, monkeypatch):
    import routes.kiosk.prijzen_gegevens as gegevens

    echt = gegevens._prijzen_categorieen
    aantal = {"keer": 0}

    def geteld(*args, **kwargs):
        aantal["keer"] += 1
        return echt(*args, **kwargs)

    monkeypatch.setattr(gegevens, "_prijzen_categorieen", geteld)
    antwoorden = [client.get("/kiosk/prijzen/versie").get_json() for _ in range(4)]
    assert aantal["keer"] == 1 and all(a == antwoorden[0] for a in antwoorden)
    assert {"versie", "uitverkocht", "wedstrijddag_test", "wedstrijddag_test_tegenstander"} <= set(antwoorden[0])

    # Het scherm zelf en zijn poll geven dezelfde versie; wijzig je een prijs, dan verandert die.
    pagina = client.get("/kiosk/prijzen").data.decode()
    assert antwoorden[0]["versie"] in pagina
    _voeg_product_toe(db, "Nieuw op de kaart", toon_op_kiosk=1)
    nieuw = client.get("/kiosk/prijzen/versie").get_json()
    assert nieuw["versie"] != antwoorden[0]["versie"]


def test_de_tv_heeft_een_eigen_versie_naast_het_prijzenscherm(client, vaste_minuut):
    prijzen = client.get("/kiosk/prijzen/versie").get_json()["versie"]
    tv = client.get("/kiosk/tv/versie").get_json()["versie"]
    assert prijzen != tv  # wisselen tussen prijzen en dia's moet ook als verandering gelden
    assert tv in client.get("/kiosk/tv").data.decode()
