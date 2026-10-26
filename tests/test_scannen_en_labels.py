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


# ---------- Uitgebreide schaplabels (1.72.0): bestelinformatie, prijs en een klein formaat ----------


def _pdf_tekst(data):
    import re
    import zlib

    inhoud = b""
    for stroom in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            inhoud += zlib.decompress(stroom)
        except zlib.error:
            inhoud += stroom
    return inhoud


def test_schaplabel_met_bestelinformatie_en_prijs(ingelogde_client, db):
    lid = db.execute("INSERT INTO leveranciers (naam, aangemaakt_op) VALUES ('Sligro', '2026-10-01')").lastrowid
    pid = _maak_product(db, "Cola Label", min_voorraad=48)
    db.execute(
        """UPDATE producten SET besteleenheid = 'tray', besteleenheid_factor = 24, leverancier_id = ?, artikelcode = 'A1',
           verkoopprijs = 2.25 WHERE id = ?""",
        (lid, pid),
    )
    db.commit()
    tekst = _pdf_tekst(ingelogde_client.get(f"/producten/{pid}/label.pdf").data)
    assert b"Min. voorraad: 48 stuks \\(2 tray\\)" in tekst and b"Bestellen per tray van 24" in tekst
    assert b"Sligro \xb7 art.nr. A1" in tekst and b"Scan met de handterminal" in tekst
    assert b"2,25" not in tekst  # de prijs alleen als je erom vraagt
    klein = _pdf_tekst(ingelogde_client.get(f"/producten/{pid}/label.pdf?formaat=klein&prijs=1").data)
    assert b"\x80 2,25" in klein and b"Cola Label" in klein


def test_kleine_schaplabels_zestien_per_vel(ingelogde_client, db):
    ids = [_maak_product(db, f"Klein {i}") for i in range(17)]
    lijst = ",".join(map(str, ids))
    klein = ingelogde_client.get(f"/producten/labels.pdf?ids={lijst}&formaat=klein").data
    groot = ingelogde_client.get(f"/producten/labels.pdf?ids={lijst}&formaat=onzin").data
    assert b"/Count 2" in klein and b"/Count 3" in groot  # onbekend formaat: gewoon groot, 6 per vel


def test_label_regels_en_opties():
    from pdf import label_opties, label_regels

    assert label_regels({"min_voorraad": 30, "eenheid": "flesjes", "besteleenheid": "krat", "besteleenheid_factor": 24}) == [
        ("minimum", "Min. voorraad: 30 flesjes"),
        ("bestellen", "Bestellen per krat van 24"),
    ]
    assert label_regels({"min_voorraad": 0, "artikelcode": "FR-20"}) == [("herkomst", "Art.nr. FR-20")]
    assert label_regels({"naam": "Toiletpapier"}) == []
    assert label_opties({"formaat": "klein", "prijs": "1"}) == {"formaat": "klein", "met_prijs": True}
    assert label_opties({}) == {"formaat": "groot", "met_prijs": False}


def test_verbruiksvoorwerp_label_in_het_klein(ingelogde_client, db):
    item = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES ('Handzeep', NULL, '2026-01-01 10:00')"
    ).lastrowid
    db.commit()
    tekst = _pdf_tekst(ingelogde_client.get(f"/verbruiksvoorwerpen/{item}/label.pdf?formaat=klein").data)
    assert b"Handzeep" in tekst and b"Op? Scan met de handterminal" in tekst


def test_printvenster_voor_schaplabels(ingelogde_client, db):
    pid = _maak_product(db)
    for pagina in ("/producten", f"/producten/{pid}", "/verbruiksvoorwerpen"):
        tekst = ingelogde_client.get(pagina).get_data(as_text=True)
        assert 'id="labels-dialoog"' in tekst and "16 per A4" in tekst, pagina
    assert "Met de verkoopprijs erop" in ingelogde_client.get("/producten").get_data(as_text=True)
    assert "Met de verkoopprijs erop" not in ingelogde_client.get("/verbruiksvoorwerpen").get_data(as_text=True)
