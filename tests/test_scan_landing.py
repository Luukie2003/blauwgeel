from conftest import stel_csrf_token_in as _csrf


def _maak_product(db, naam="Testproduct"):
    cursor = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad) "
        "VALUES (?, 'Fris', 'stuks', 10, 5)",
        (naam,),
    )
    db.commit()
    return cursor.lastrowid


def test_scan_landing_werkt_zonder_inloggen(client, db):
    product_id = _maak_product(db)
    resp = client.get(f"/scan/{product_id}")
    assert resp.status_code == 200
    assert b"Testproduct" in resp.data
    assert b"Naar productpagina" in resp.data
    # Melden voor de bestellijst gaat sinds 1.72.0 met de handterminal, niet meer met een telefoon.
    assert b"Melden voor bestellijst" not in resp.data
    assert b"handterminal" in resp.data


def test_scan_landing_ingelogd_gaat_meteen_naar_de_productpagina(ingelogde_client, db):
    product_id = _maak_product(db)
    resp = ingelogde_client.get(f"/scan/{product_id}")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/producten/{product_id}")


def test_scan_landing_onbekend_product_geeft_404(client):
    resp = client.get("/scan/99999")
    assert resp.status_code == 404
    assert b"niet gevonden" in resp.data


def test_melden_via_de_qr_code_kan_niet_meer(client, db):
    product_id = _maak_product(db)
    item_id = _maak_verbruiksvoorwerp(db)
    for pad in (f"/scan/{product_id}/melden", f"/scan/verbruiksvoorwerp/{item_id}/melden"):
        assert client.post(pad, data={"csrf_token": _csrf(client)}).status_code == 404
    assert db.execute("SELECT COUNT(*) AS n FROM bestellijst_meldingen").fetchone()["n"] == 0


def test_naar_productpagina_vraagt_alsnog_inloggen(client, db):
    product_id = _maak_product(db)
    resp = client.get(f"/producten/{product_id}")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_schaplabel_qr_wijst_naar_scan_landing(ingelogde_client, db):
    product_id = _maak_product(db)
    resp = ingelogde_client.get(f"/producten/{product_id}/label.pdf")
    assert resp.status_code == 200
    assert resp.data[:4] == b"%PDF"


# ---------- Zelfde flow, maar dan voor verbruiksvoorwerpen ----------


def _maak_verbruiksvoorwerp(db, naam="Frietbakjes"):
    cursor = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) "
        "VALUES (?, 'Verpakking', '2026-01-01 10:00')",
        (naam,),
    )
    db.commit()
    return cursor.lastrowid


def test_scan_landing_verbruiksvoorwerp_werkt_zonder_inloggen(client, db):
    item_id = _maak_verbruiksvoorwerp(db)
    resp = client.get(f"/scan/verbruiksvoorwerp/{item_id}")
    assert resp.status_code == 200
    assert b"Frietbakjes" in resp.data
    assert b"handterminal" in resp.data
    assert b"Melden voor bestellijst" not in resp.data
    # Geen productpagina om naartoe te gaan -- die knop hoort hier niet.
    assert b"Naar productpagina" not in resp.data


def test_scan_landing_verbruiksvoorwerp_onbekend_geeft_404(client):
    resp = client.get("/scan/verbruiksvoorwerp/99999")
    assert resp.status_code == 404
    assert b"niet gevonden" in resp.data.lower() or b"Niet gevonden" in resp.data


def test_verbruiksvoorwerp_schaplabel_qr_wijst_naar_scan_landing(ingelogde_client, db):
    item_id = _maak_verbruiksvoorwerp(db)
    resp = ingelogde_client.get(f"/verbruiksvoorwerpen/{item_id}/label.pdf")
    assert resp.status_code == 200
    assert resp.data[:4] == b"%PDF"
