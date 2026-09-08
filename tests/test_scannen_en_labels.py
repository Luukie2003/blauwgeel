def _maak_product(db, naam="Testproduct", min_voorraad=5):
    cursor = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad) "
        "VALUES (?, 'Fris', 'stuks', 10, ?)",
        (naam, min_voorraad),
    )
    db.commit()
    return cursor.lastrowid


def test_scannen_pagina_laadt(ingelogde_client):
    resp = ingelogde_client.get("/scannen")
    assert resp.status_code == 200
    assert b"BarcodeDetector" in resp.data


def test_product_label_pdf_wordt_gegenereerd(ingelogde_client, db):
    product_id = _maak_product(db)
    resp = ingelogde_client.get(f"/producten/{product_id}/label.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_product_label_pdf_onbekend_product_stuurt_terug(ingelogde_client):
    resp = ingelogde_client.get("/producten/99999/label.pdf", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Product niet gevonden" in resp.data


def test_bulk_labels_pdf_met_meerdere_producten(ingelogde_client, db):
    id1 = _maak_product(db, "Product Een")
    id2 = _maak_product(db, "Product Twee")
    resp = ingelogde_client.get(f"/producten/labels.pdf?ids={id1},{id2}")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_bulk_labels_pdf_zonder_ids_stuurt_terug(ingelogde_client):
    resp = ingelogde_client.get("/producten/labels.pdf", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Geen producten geselecteerd" in resp.data


def test_bulk_labels_pdf_negeert_geknoei_in_querystring(ingelogde_client, db):
    product_id = _maak_product(db)
    resp = ingelogde_client.get(f"/producten/labels.pdf?ids={product_id},abc,;drop table")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
