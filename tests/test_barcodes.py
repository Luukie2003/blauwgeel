"""Barcodes (EAN): artikelen die je inkoopt, met de barcode van de verpakking en van de doos, per product."""

import pytest

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

import barcodes


def _ean(begin):
    """Een geldige EAN-13 (of GTIN-14) bij de eerste 12 (of 13) cijfers."""
    som = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(begin)))
    return begin + str((10 - som % 10) % 10)


AH_ZAK, AH_DOOS = _ean("871000000001"), _ean("871000000002")
PLUS_ZAK = _ean("871000000003")
WIJN_A, WIJN_B = _ean("540000000001"), _ean("540000000002")


def _product(db, naam, eenheid="stuks", categorie="Snacks"):
    cur = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, verkoopprijs, actief) VALUES (?, ?, ?, 10, 2.0, 1)",
        (naam, categorie, eenheid),
    )
    db.commit()
    return cur.lastrowid


def _artikel(db, product_id, naam, ean=None, aantal=1, prijs=0, doos=None, per_doos=0):
    artikel_id, fout = barcodes.bewaar_artikel(db, {
        "product_id": str(product_id), "naam": naam, "ean": ean or "", "aantal_per_verpakking": str(aantal),
        "inkoopprijs": str(prijs), "ean_omverpakking": doos or "", "per_omverpakking": str(per_doos),
    })
    assert fout is None, fout
    return artikel_id


# ---------- Barcodes lezen ----------


@pytest.mark.parametrize("invoer, verwacht", [
    ("4006381333931", "4006381333931"),  # EAN-13
    (" 4006 3813 33931 ", "4006381333931"),  # spaties van overtikken
    ("96385074", "96385074"),  # EAN-8
    ("012345678905", "0012345678905"),  # UPC-A wordt EAN-13
    ("00012345678905", "0012345678905"),  # doos-code die met 0 begint = dezelfde EAN-13
    ("10012345678902", "10012345678902"),  # echte doos-code (GTIN-14)
])
def test_geldige_barcodes_in_een_vaste_vorm(invoer, verwacht):
    assert barcodes.controleer(invoer) == (verwacht, None)


@pytest.mark.parametrize("invoer", ["4006381333932", "12345", "abc", "40063813339310000"])
def test_tikfout_of_geen_barcode_wordt_geweigerd(invoer):
    code, fout = barcodes.controleer(invoer)
    assert code is None and fout


# ---------- Artikelen en opzoeken ----------


def test_zak_en_doos_frikandellen(db):
    """AH frikandellen: een zak van 20 voor € 20, een doos met 4 zakken."""
    frikandel = _product(db, "Frikandel")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20, doos=AH_DOOS, per_doos=4)

    zak = barcodes.zoek_barcode(db, AH_ZAK)
    assert (zak["bekend"], zak["niveau"], zak["aantal"], zak["inkoopprijs"]) == (True, "verpakking", 20, 20.0)
    assert zak["omschrijving"] == "AH frikandellen, 20 stuks, € 20,00"
    assert zak["artikel"]["product_naam"] == "Frikandel"

    doos = barcodes.zoek_barcode(db, AH_DOOS)
    assert (doos["niveau"], doos["aantal"], doos["inkoopprijs"]) == ("omverpakking", 80, 80.0)
    assert doos["omschrijving"] == "AH frikandellen, doos van 4 (80 stuks), € 80,00"


def test_andere_winkel_ander_artikel_zelfde_product(db):
    frikandel = _product(db, "Frikandel")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20)
    _artikel(db, frikandel, "Plus frikandellen", PLUS_ZAK, aantal=15, prijs=18)
    plus = barcodes.zoek_barcode(db, PLUS_ZAK)
    assert (plus["artikel"]["naam"], plus["aantal"], plus["inkoopprijs"]) == ("Plus frikandellen", 15, 18.0)
    assert plus["artikel"]["product_id"] == frikandel
    assert barcodes.per_eenheid(plus["artikel"]) == pytest.approx(1.2)
    assert len(barcodes.artikelen_van(db, frikandel)) == 2


def test_wijnen_horen_bij_een_product(db):
    witte_wijn = _product(db, "Witte wijn", "fles", "Wijn")
    aantal_producten = db.execute("SELECT COUNT(*) FROM producten").fetchone()[0]
    _artikel(db, witte_wijn, "Chardonnay", WIJN_A, prijs=4.5)
    _artikel(db, witte_wijn, "Sauvignon blanc", WIJN_B, prijs=5.25)
    assert {barcodes.zoek_barcode(db, c)["artikel"]["product_naam"] for c in (WIJN_A, WIJN_B)} == {"Witte wijn"}
    # Op de overzichten blijft het één product: artikelen maken geen nieuwe producten.
    assert db.execute("SELECT COUNT(*) FROM producten").fetchone()[0] == aantal_producten


def test_onbekende_barcode(db):
    uitkomst = barcodes.zoek_barcode(db, AH_ZAK)
    assert uitkomst["geldig"] and not uitkomst["bekend"] and uitkomst["suggestie"] is None
    fout = barcodes.zoek_barcode(db, "123")
    assert not fout["geldig"] and fout["melding"]


def test_doos_code_wijst_naar_wat_erin_zit(db):
    """Een doos-code van 14 cijfers bevat de EAN van wat erin zit: dan stelt de site dat artikel voor."""
    frikandel = _product(db, "Frikandel")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20)
    doos = _ean("1" + AH_ZAK[:12])
    assert barcodes.zoek_barcode(db, doos)["suggestie"]["naam"] == "AH frikandellen"


def test_een_barcode_hoort_bij_een_artikel(db):
    frikandel = _product(db, "Frikandel")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, doos=AH_DOOS, per_doos=4)
    basis = {"product_id": str(frikandel), "naam": "Ander", "aantal_per_verpakking": "1"}
    for velden in ({"ean": AH_ZAK}, {"ean": AH_DOOS}, {"ean_omverpakking": AH_ZAK, "per_omverpakking": "2"}):
        _, fout = barcodes.bewaar_artikel(db, {**basis, **velden})
        assert fout and "hoort al bij 'AH frikandellen'" in fout
    _, fout = barcodes.bewaar_artikel(db, {**basis, "ean": PLUS_ZAK, "ean_omverpakking": PLUS_ZAK, "per_omverpakking": "2"})
    assert "hetzelfde" in fout
    _, fout = barcodes.bewaar_artikel(db, {**basis, "ean_omverpakking": PLUS_ZAK})
    assert "hoeveel er in de doos" in fout
    _, fout = barcodes.bewaar_artikel(db, {**basis, "ean": "4006381333932"})
    assert "klopt niet" in fout
    _, fout = barcodes.bewaar_artikel(db, {**basis, "product_id": ""})
    assert "product" in fout


def test_een_artikel_bewerken_mag_zijn_eigen_barcode_houden(db):
    frikandel = _product(db, "Frikandel")
    artikel_id = _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20)
    _, fout = barcodes.bewaar_artikel(db, {"product_id": str(frikandel), "naam": "AH frikandellen", "ean": AH_ZAK,
                                           "aantal_per_verpakking": "20", "inkoopprijs": "21,50"}, artikel_id)
    assert fout is None
    assert barcodes.artikel(db, artikel_id)["inkoopprijs"] == 21.5


# ---------- De pagina's ----------


def test_onbekende_barcode_scannen_en_toevoegen(ingelogde_client, db):
    frikandel = _product(db, "Frikandel")
    tekst = ingelogde_client.get(f"/barcodes/zoek?code={AH_ZAK}").data.decode()
    assert "Onbekende barcode" in tekst and f"/barcodes/nieuw?ean={AH_ZAK}" in tekst

    resp = ingelogde_client.post("/barcodes/nieuw", data={
        "csrf_token": _csrf(ingelogde_client), "product_id": frikandel, "naam": "AH frikandellen", "ean": AH_ZAK,
        "aantal_per_verpakking": "20", "inkoopprijs": "20", "terug": "zoeken", "zoekcode": AH_ZAK,
    })
    assert resp.status_code == 302 and f"/barcodes/zoek?code={AH_ZAK}" in resp.headers["Location"]
    tekst = ingelogde_client.get(f"/barcodes/zoek?code={AH_ZAK}").data.decode()
    assert "AH frikandellen" in tekst and "20 stuks" in tekst and "20,00" in tekst


def test_fout_in_het_formulier_houdt_de_invoer_vast(ingelogde_client, db):
    frikandel = _product(db, "Frikandel")
    resp = ingelogde_client.post("/barcodes/nieuw", data={
        "csrf_token": _csrf(ingelogde_client), "product_id": frikandel, "naam": "AH frikandellen",
        "ean": "4006381333932", "aantal_per_verpakking": "20",
    })
    tekst = resp.data.decode()
    assert resp.status_code == 200 and "klopt niet" in tekst and 'value="AH frikandellen"' in tekst
    assert db.execute("SELECT COUNT(*) FROM artikelen").fetchone()[0] == 0


def test_onbekende_doos_koppelen_aan_een_bekend_artikel(ingelogde_client, db):
    frikandel = _product(db, "Frikandel")
    artikel_id = _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20)
    tekst = ingelogde_client.get(f"/barcodes/zoek?code={AH_DOOS}").data.decode()
    assert "de doos van een artikel dat al bekend is" in tekst

    ingelogde_client.post("/barcodes/doos", data={
        "csrf_token": _csrf(ingelogde_client), "code": AH_DOOS, "artikel_id": artikel_id, "per_omverpakking": "4",
    })
    doos = barcodes.zoek_barcode(db, AH_DOOS)
    assert (doos["niveau"], doos["aantal"], doos["inkoopprijs"]) == ("omverpakking", 80, 80.0)


def test_overzicht_productpagina_en_verwijderen(ingelogde_client, db):
    frikandel = _product(db, "Frikandel")
    artikel_id = _artikel(db, frikandel, "Plus snackfrikandel", PLUS_ZAK, aantal=15, prijs=18)
    tekst = ingelogde_client.get("/barcodes").data.decode()
    assert "Plus snackfrikandel" in tekst and PLUS_ZAK in tekst and "1,20 per stuks" in tekst
    assert "Plus snackfrikandel" in ingelogde_client.get(f"/producten/{frikandel}/bewerken").data.decode()
    assert "Plus snackfrikandel" in ingelogde_client.get("/barcodes?q=plus").data.decode()
    assert "Plus snackfrikandel" not in ingelogde_client.get("/barcodes?q=wijn").data.decode()

    ingelogde_client.post(f"/barcodes/{artikel_id}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT COUNT(*) FROM artikelen").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM producten WHERE id = ?", (frikandel,)).fetchone()[0] == 1


def test_json_voor_de_app(ingelogde_client, db):
    frikandel = _product(db, "Frikandel")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20, doos=AH_DOOS, per_doos=4)
    data = ingelogde_client.get(f"/api/barcode/{AH_DOOS}").get_json()
    assert data["bekend"] and data["niveau"] == "omverpakking" and data["aantal"] == 80 and data["inkoopprijs"] == 80.0
    assert data["product"]["naam"] == "Frikandel" and data["artikel"]["ean"] == AH_ZAK
    onbekend = ingelogde_client.get(f"/api/barcode/{PLUS_ZAK}").get_json()
    assert onbekend["geldig"] and not onbekend["bekend"] and onbekend["product"] is None


def test_zoekbalk_vindt_een_gescande_barcode(ingelogde_client, db):
    frikandel = _product(db, "Frikandel")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, doos=AH_DOOS, per_doos=4)
    tekst = ingelogde_client.get(f"/zoeken?q={AH_DOOS}").data.decode()
    assert "AH frikandellen" in tekst and f"/barcodes/zoek?code={AH_DOOS}" in tekst


def test_barcodes_horen_bij_de_voorraad_sectie(client, db):
    _maak_vrijwilliger(db, "kassahulp", "kassa")
    _login(client, "kassahulp")
    assert client.get("/barcodes").status_code == 302
    resp = client.get(f"/api/barcode/{AH_ZAK}")  # de app krijgt JSON in plaats van een doorverwijzing
    assert resp.status_code == 403 and resp.get_json()["fout"] == "geen_toegang"


def test_vrijwilliger_met_voorraad_kan_barcodes_toevoegen(client, db):
    frikandel = _product(db, "Frikandel")
    _maak_vrijwilliger(db, "inboeker", "voorraad")
    _login(client, "inboeker")
    assert client.get("/barcodes").status_code == 200
    client.post("/barcodes/nieuw", data={"csrf_token": _csrf(client), "product_id": frikandel, "naam": "AH frikandellen",
                                         "ean": AH_ZAK, "aantal_per_verpakking": "20"})
    assert barcodes.zoek_barcode(db, AH_ZAK)["bekend"]


def test_product_verwijderen_neemt_zijn_artikelen_mee(ingelogde_client, db):
    frikandel = _product(db, "Frikandel")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK)
    ingelogde_client.post(f"/producten/{frikandel}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT COUNT(*) FROM producten WHERE id = ?", (frikandel,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM artikelen").fetchone()[0] == 0


# ---------- De inkoopprijs van het product ----------


def _inkoop(db, product_id):
    return db.execute("SELECT inkoopprijs FROM producten WHERE id = ?", (product_id,)).fetchone()[0]


def test_inkoopprijs_van_het_product_is_het_gemiddelde_van_de_artikelen(db):
    """AH: 20 voor € 20 (€ 1,00 per stuk), Plus: 15 voor € 18 (€ 1,20 per stuk) -> gemiddeld € 1,10."""
    frikandel = _product(db, "Frikandel")
    assert _inkoop(db, frikandel) == 0
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20)
    assert _inkoop(db, frikandel) == pytest.approx(1.00)
    plus = _artikel(db, frikandel, "Plus frikandellen", PLUS_ZAK, aantal=15, prijs=18)
    assert _inkoop(db, frikandel) == pytest.approx(1.10)
    _artikel(db, frikandel, "Zonder prijs", _ean("871000000009"))  # telt niet mee
    assert _inkoop(db, frikandel) == pytest.approx(1.10)

    geschiedenis = db.execute(
        "SELECT oude_prijs, nieuwe_prijs FROM prijs_geschiedenis WHERE product_id = ? AND veld = 'inkoopprijs' ORDER BY id",
        (frikandel,),
    ).fetchall()
    assert [(r[0], round(r[1], 2)) for r in geschiedenis] == [(0, 1.0), (1.0, 1.1)]

    barcodes.verwijder_artikel(db, plus)
    assert _inkoop(db, frikandel) == pytest.approx(1.00)


def test_inkoopprijs_per_besteleenheid(db):
    """De inkoopprijs van een product staat per besteleenheid (bijv. een doos van 40)."""
    frikandel = _product(db, "Frikandel")
    db.execute("UPDATE producten SET besteleenheid = 'doos', besteleenheid_factor = 40 WHERE id = ?", (frikandel,))
    db.commit()
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20)
    assert _inkoop(db, frikandel) == pytest.approx(40.0)


def test_zonder_artikelen_met_prijs_blijft_de_eigen_prijs(db):
    frikandel = _product(db, "Frikandel")
    db.execute("UPDATE producten SET inkoopprijs = 0.9 WHERE id = ?", (frikandel,))
    db.commit()
    artikel_id = _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20)
    assert _inkoop(db, frikandel) == pytest.approx(0.9)
    barcodes.verwijder_artikel(db, artikel_id)
    assert _inkoop(db, frikandel) == pytest.approx(0.9)


def test_artikel_naar_een_ander_product_werkt_beide_bij(db):
    frikandel, kroket = _product(db, "Frikandel"), _product(db, "Kroket")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20)
    plus = _artikel(db, frikandel, "Plus kroketten", PLUS_ZAK, aantal=10, prijs=15)
    assert _inkoop(db, frikandel) == pytest.approx(1.25)
    barcodes.bewaar_artikel(db, {"product_id": str(kroket), "naam": "Plus kroketten", "ean": PLUS_ZAK,
                                 "aantal_per_verpakking": "10", "inkoopprijs": "15"}, plus)
    assert _inkoop(db, frikandel) == pytest.approx(1.00)
    assert _inkoop(db, kroket) == pytest.approx(1.50)


def test_productpagina_rekent_de_inkoopprijs_uit_de_artikelen(ingelogde_client, db):
    frikandel = _product(db, "Frikandel")
    _artikel(db, frikandel, "AH frikandellen", AH_ZAK, aantal=20, prijs=20)
    _artikel(db, frikandel, "Plus frikandellen", PLUS_ZAK, aantal=15, prijs=18)
    tekst = ingelogde_client.get(f"/producten/{frikandel}/bewerken").data.decode()
    assert "Komt uit de" in tekst and "gemiddeld &euro; 1,10 per stuks" in tekst

    # Wat er in het (vergrendelde) veld staat telt niet; een andere besteleenheid wel.
    product = db.execute("SELECT * FROM producten WHERE id = ?", (frikandel,)).fetchone()
    ingelogde_client.post(f"/producten/{frikandel}/bewerken", data={
        "csrf_token": _csrf(ingelogde_client), "naam": "Frikandel", "categorie": "Snacks", "eenheid": "stuks",
        "voorraad": product["voorraad"], "min_voorraad": "0", "bestel_hoeveelheid": "0", "verkoopprijs": "2.5",
        "inkoopprijs": "99", "besteleenheid": "doos", "besteleenheid_factor": "40", "actief": "on",
    })
    assert _inkoop(db, frikandel) == pytest.approx(44.0)
