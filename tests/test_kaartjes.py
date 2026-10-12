"""Kaartjes printen: de instellingen (ontwerp, hardlopers, vellen, kleur), de pagina en de pdf."""

import re

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from kaartjes import bewaar_instellingen, groepeer_op_merk, lees_instellingen, topverkopers
from pdf.kaartjes import (
    MAX_HARDLOPERS,
    MAX_TEKENS_HARDLOPER,
    OPTIE_PER_SLEUTEL,
    OPTIES,
    kaartjes_overzicht_pdf,
    kaartjes_pdf,
    schoon_hardlopers,
)

STANDAARD = ["Pils tap", "Hertog Jan Fles", "Bozu", "Powerrade", "Bacardi Cola", "Sonnema Cola"]


def _paginas(pdf_bytes):
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_bytes))


def _opslaan(client, **velden):
    data = {"csrf_token": _csrf(client), "optie": "D", "hardlopers": "Pils tap", "vellen": "1", **velden}
    return client.post("/kaartjes", data=data, follow_redirects=True)


# ---------- De hardlopers ----------


def test_hardlopers_schoonmaken():
    assert schoon_hardlopers("  Pils tap \n\n Bozu\r\nHertog   Jan  Fles") == (["Pils tap", "Bozu", "Hertog Jan Fles"], 0)
    assert schoon_hardlopers("") == ([], 0) and schoon_hardlopers(None) == ([], 0)
    assert schoon_hardlopers("Bozu\nbozu\nBOZU") == (["Bozu"], 0)  # dezelfde naam maar 1 keer


def test_maximaal_zes_hardlopers_en_korte_namen():
    namen, weggelaten = schoon_hardlopers("\n".join(f"Drank {i}" for i in range(9)))
    assert len(namen) == MAX_HARDLOPERS == 6 and weggelaten == 3
    assert schoon_hardlopers("x" * 80)[0] == ["x" * MAX_TEKENS_HARDLOPER]


# ---------- Opgeslagen instellingen ----------


def test_standaardinstellingen(db):
    i = lees_instellingen(db)
    assert i["optie"] == "D" and i["hardlopers"] == STANDAARD and i["vellen"] == 1 and i["zwartwit"] is False


def test_instellingen_bewaren_en_begrenzen(db):
    assert bewaar_instellingen(db, "A", "Pils tap\n\nBier", 3, True) == 0
    i = lees_instellingen(db)
    assert (i["optie"], i["hardlopers"], i["vellen"], i["zwartwit"]) == ("A", ["Pils tap", "Bier"], 3, True)

    bewaar_instellingen(db, "bestaat-niet", "x", 9999, False)
    i = lees_instellingen(db)
    assert i["optie"] == "D" and i["vellen"] == 50  # onbekend ontwerp -> standaard, vellen begrensd
    bewaar_instellingen(db, "D", "x", 0, False)
    assert lees_instellingen(db)["vellen"] == 1


# ---------- De pdf ----------


def test_elk_ontwerp_geeft_een_pdf_met_de_juiste_aantallen():
    assert [o.sleutel for o in OPTIES] == ["D", "D2", "A", "B", "C"]
    for optie in OPTIES:
        pdf = kaartjes_pdf(optie.sleutel, STANDAARD)
        assert pdf.startswith(b"%PDF") and _paginas(pdf) == 1
        # Past op A4 met een rand voor de printer: minstens 4 mm links/rechts en boven/onder.
        assert optie.breedte * optie.kolommen <= 202 and optie.hoogte * optie.rijen <= 289
    assert _paginas(kaartjes_pdf("D", STANDAARD, vellen=3)) == 3
    assert _paginas(kaartjes_overzicht_pdf(STANDAARD)) == len(OPTIES)


def test_onbekend_ontwerp_valt_terug_op_het_standaardontwerp():
    assert kaartjes_pdf("bestaat-niet", STANDAARD).startswith(b"%PDF")
    assert OPTIE_PER_SLEUTEL["D"].breedte == 97


@pytest.mark.parametrize("optie", [o.sleutel for o in OPTIES])
def test_ook_met_weinig_of_geen_hardlopers_en_gekke_tekens(optie):
    for hardlopers in ([], ["Pils tap"], ["Fusé ♥ emoji \U0001f37a", "x" * 24], STANDAARD):
        for zwartwit in (False, True):
            assert kaartjes_pdf(optie, hardlopers, 1, zwartwit).startswith(b"%PDF")


def test_zwartwit_gebruikt_geen_blauw():
    kleur = kaartjes_pdf("D", STANDAARD, zwartwit=False)
    zw = kaartjes_pdf("D", STANDAARD, zwartwit=True)
    assert kleur != zw
    blauw = b"0.1176 0.2275 0.5412 RG"  # het clubblauw (30, 58, 138) als lijnkleur
    assert blauw in _ontvouw(kleur)
    assert blauw not in _ontvouw(zw)  # de dubbele lijn is dan donkergrijs


def _ontvouw(pdf):
    """De tekenopdrachten van de pagina (pdf's zijn gecomprimeerd)."""
    import re as _re
    import zlib

    uit = b""
    for stroom in _re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, _re.S):
        try:
            uit += zlib.decompress(stroom)
        except zlib.error:
            uit += stroom
    return uit


def test_de_hardlopers_staan_op_de_kaartjes():
    inhoud = _ontvouw(kaartjes_pdf("D", ["Pils tap", "Bozu"]))
    assert b"Pils tap" in inhoud and b"Bozu" in inhoud and b"Sonnema" not in inhoud


# ---------- Meest verkocht, merken samengenomen ----------


def test_merken_worden_een_regel_en_de_rest_blijft_los():
    rijen = [
        ("Bozu Sparkling", 302), ("Bozu Peach", 266), ("Bozu Hard Icetea", 127),
        ("Hertog Jan Fles", 826),
        ("AA Drink", 27), ("AA Drink Iso Lemon", 23), ("AA Drink Orange", 135),
        ("Coca Cola", 85), ("Coca Cola Zero", 66),
        ("Snicker", 56), ("Nooit Verkocht", 0), ("", 5),
    ]
    groepen = groepeer_op_merk(rijen)
    assert [(g["naam"], g["aantal"], g["producten"]) for g in groepen] == [
        ("Hertog Jan Fles", 826, 1),
        ("Bozu", 695, 3),
        ("AA Drink", 185, 3),
        ("Coca Cola", 151, 2),
        ("Snicker", 56, 1),
    ]


def test_de_naam_van_een_groep_is_het_begin_dat_alle_producten_delen():
    assert groepeer_op_merk([("Fust Hertog Jan", 12), ("Fust Hertog Jan Weizener", 3)])[0]["naam"] == "Fust Hertog Jan"
    assert groepeer_op_merk([("Lays Paprika", 13), ("Lays Bolognese", 20)])[0]["naam"] == "Lays"
    assert len(groepeer_op_merk([(f"Merk{i} x", i + 1) for i in range(30)], aantal=5)) == 5


def _telling_met_verkoop(db, regels):
    from datetime import datetime

    cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'Test')", (datetime.now().strftime("%Y-%m-%d %H:%M"),))
    for product, verkocht in regels:
        pid = db.execute("SELECT id FROM producten WHERE naam = ?", (product,)).fetchone()
        if pid is None:
            pid = db.execute(
                "INSERT INTO producten (naam, categorie, eenheid, verkoopprijs, actief) VALUES (?, 'Bier', 'Fles', 2, 1)", (product,)
            ).lastrowid
        else:
            pid = pid["id"]
        db.execute(
            """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
               VALUES (?, ?, 0, 0, ?, 2)""",
            (cur.lastrowid, pid, verkocht),
        )
    db.commit()


def test_topverkopers_uit_de_tellingen_van_dit_seizoen(db):
    _telling_met_verkoop(db, [("Bozu Peach", 10), ("Bozu Green", 5), ("Pils", 7)])
    top = {t["naam"]: (t["aantal"], t["producten"]) for t in topverkopers(db)}
    assert top["Bozu"] == (15, 2) and top["Pils"] == (7, 1)

    # Een telling van voor dit seizoen telt niet mee.
    db.execute("UPDATE tellingen SET datum = '2020-01-01 10:00'")
    db.commit()
    assert "Bozu" not in {t["naam"] for t in topverkopers(db)}


# ---------- De pagina ----------


def test_pagina_toont_de_ontwerpen_en_de_hardlopers(ingelogde_client):
    tekst = ingelogde_client.get("/kaartjes").data.decode()
    for optie in OPTIES:
        assert f'value="{optie.sleutel}"' in tekst and f"{optie.breedte} &times; {optie.hoogte} mm" in tekst
    assert "Pils tap" in tekst and 'name="hardlopers"' in tekst and 'name="vellen"' in tekst and 'name="zwartwit"' in tekst
    assert "/kaartjes/pdf?voorbeeld=1" in tekst  # het voorbeeld in de pagina
    assert "Kaartjes printen" in tekst


def test_opslaan_via_de_pagina(ingelogde_client, db):
    resp = _opslaan(ingelogde_client, optie="D2", hardlopers="Bier\nWijn\n\nCola", vellen="4", zwartwit="on")
    assert "Opgeslagen" in resp.data.decode()
    i = lees_instellingen(db)
    assert (i["optie"], i["hardlopers"], i["vellen"], i["zwartwit"]) == ("D2", ["Bier", "Wijn", "Cola"], 4, True)
    pagina = ingelogde_client.get("/kaartjes").data.decode()
    assert re.search(r'value="D2"\s+checked', pagina) and "4 vellen" in pagina


def test_te_veel_hardlopers_geeft_een_waarschuwing(ingelogde_client, db):
    resp = _opslaan(ingelogde_client, hardlopers="\n".join(f"Drank {i}" for i in range(8)))
    assert "maximaal 6 hardlopers" in resp.data.decode() and "laatste 2" in resp.data.decode()
    assert len(lees_instellingen(db)["hardlopers"]) == 6


def test_vellen_zonder_getal_wordt_een(ingelogde_client, db):
    _opslaan(ingelogde_client, vellen="abc")
    assert lees_instellingen(db)["vellen"] == 1


def test_de_pdf_komt_uit_de_opgeslagen_instellingen(ingelogde_client, db):
    _opslaan(ingelogde_client, optie="A", hardlopers="Eigen Drank", vellen="2")

    pdf = ingelogde_client.get("/kaartjes/pdf")
    voorbeeld = ingelogde_client.get("/kaartjes/pdf?voorbeeld=1")
    alle = ingelogde_client.get("/kaartjes/pdf?alle=1")
    download = ingelogde_client.get("/kaartjes/pdf?download=1")

    assert pdf.mimetype == "application/pdf" and _paginas(pdf.data) == 2  # 2 vellen
    assert b"Eigen Drank" in _ontvouw(pdf.data)
    assert _paginas(voorbeeld.data) == 1  # het voorbeeld is 1 vel
    assert _paginas(alle.data) == len(OPTIES)
    assert pdf.headers["Content-Disposition"].startswith("inline") and download.headers["Content-Disposition"].startswith("attachment")
    assert pdf.headers["Cache-Control"] == "no-store"  # na opslaan meteen het nieuwe voorbeeld


def test_de_pdf_mag_in_de_pagina_getoond_worden_maar_andere_pagina_s_niet(ingelogde_client):
    assert ingelogde_client.get("/kaartjes/pdf?voorbeeld=1").headers["X-Frame-Options"] == "SAMEORIGIN"
    assert ingelogde_client.get("/kaartjes").headers["X-Frame-Options"] == "DENY"


def test_zonder_account_geen_toegang(client):
    assert client.get("/kaartjes").status_code == 302
    assert client.get("/kaartjes/pdf").status_code == 302
    assert client.post("/kaartjes", data={"optie": "A"}).status_code in (302, 400)


def test_toegang_volgt_de_sectie_voorraad(client, db):
    _maak_vrijwilliger(db, "alleen_stemmen", "stemmen")
    _login(client, "alleen_stemmen")
    assert "niet beschikbaar" in client.get("/kaartjes", follow_redirects=True).data.decode()

    _maak_vrijwilliger(db, "telt_voorraad", "voorraad")
    client.get("/logout")
    _login(client, "telt_voorraad")
    assert client.get("/kaartjes").status_code == 200
    assert client.get("/kaartjes/pdf").status_code == 200
