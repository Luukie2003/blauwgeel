"""Een voorraad die via Bewerken verandert, laat een boeking na; de zoekbalk van de handterminal vindt barcodes."""

from conftest import stel_csrf_token_in as _csrf
from test_barcodes import AH_DOOS, AH_ZAK, PLUS_ZAK, _artikel, _product

from productinfo import HANDMATIG_AANGEPAST


def _bewerk_voorraad(client, product, voorraad):
    return client.post(f"/producten/{product['id']}/bewerken", data={
        "csrf_token": _csrf(client), "naam": product["naam"], "categorie": product["categorie"],
        "eenheid": product["eenheid"], "voorraad": str(voorraad), "min_voorraad": "0", "bestel_hoeveelheid": "0",
        "verkoopprijs": "2.0", "inkoopprijs": "0", "besteleenheid_factor": "1", "actief": "on",
    })


def test_voorraad_via_bewerken_laat_een_boeking_na(ingelogde_client, db):
    pid = _product(db, "Fanta test")
    product = db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()
    _bewerk_voorraad(ingelogde_client, product, 13)  # was 10
    rij = db.execute("SELECT type, aantal, opmerking FROM mutaties WHERE product_id = ?", (pid,)).fetchone()
    assert (rij["type"], rij["aantal"]) == ("in", 3) and rij["opmerking"].startswith(HANDMATIG_AANGEPAST)
    assert "10 → 13" in rij["opmerking"]

    product = db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()
    _bewerk_voorraad(ingelogde_client, product, 13)  # niets veranderd: geen boeking
    _bewerk_voorraad(ingelogde_client, product, 9)
    assert [(r["type"], r["aantal"]) for r in db.execute("SELECT type, aantal FROM mutaties WHERE product_id = ? ORDER BY id", (pid,))] == [("in", 3), ("uit", 4)]
    # Telt niet als 'laatst binnen' op de productpagina.
    assert "nog niets ingeboekt" in ingelogde_client.get(f"/producten/{pid}").data.decode()


def test_handterminal_zoekt_op_barcode(ingelogde_client, db):
    pid = _product(db, "Frikandel")
    _artikel(db, pid, "AH frikandellen", AH_ZAK, aantal=20, prijs=20, doos=AH_DOOS, per_doos=4)
    data = ingelogde_client.get(f"/producten/zoeken?q={AH_DOOS}").get_json()
    assert [p["id"] for p in data["resultaten"]] == [pid] and "doos van 4" in data["barcode"]["omschrijving"]

    data = ingelogde_client.get(f"/producten/zoeken?q={PLUS_ZAK}").get_json()
    assert data["resultaten"] == [] and data["onbekende_barcode"] == PLUS_ZAK

    data = ingelogde_client.get("/producten/zoeken?q=Frikan").get_json()  # gewoon zoeken blijft werken
    assert pid in [p["id"] for p in data["resultaten"]] and "onbekende_barcode" not in data


def test_een_lange_artikelcode_is_geen_onbekende_barcode(ingelogde_client, db):
    pid = _product(db, "Speciaal")
    db.execute("UPDATE producten SET artikelcode = ? WHERE id = ?", (PLUS_ZAK, pid))
    db.commit()
    data = ingelogde_client.get(f"/producten/zoeken?q={PLUS_ZAK}").get_json()
    assert [p["id"] for p in data["resultaten"]] == [pid] and "onbekende_barcode" not in data
