from conftest import stel_csrf_token_in as _csrf


def test_toevoegen_en_lijst(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/verbruiksvoorwerpen",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Frietbakjes", "categorie": "Verpakking"},
    )
    assert resp.status_code == 302
    item = db.execute("SELECT * FROM verbruiksvoorwerpen WHERE naam = 'Frietbakjes'").fetchone()
    assert item is not None
    assert item["categorie"] == "Verpakking"

    resp = ingelogde_client.get("/verbruiksvoorwerpen")
    assert b"Frietbakjes" in resp.data


def test_naam_verplicht(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/verbruiksvoorwerpen",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "", "categorie": ""},
        follow_redirects=True,
    )
    assert b"Naam is verplicht" in resp.data
    assert db.execute("SELECT COUNT(*) AS n FROM verbruiksvoorwerpen").fetchone()["n"] == 0


def test_verwijderen(ingelogde_client, db):
    cursor = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES ('Servetten', NULL, '2026-01-01 10:00')"
    )
    db.commit()
    item_id = cursor.lastrowid

    resp = ingelogde_client.post(
        f"/verbruiksvoorwerpen/{item_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM verbruiksvoorwerpen WHERE id = ?", (item_id,)).fetchone() is None


def test_bestellijst_melden_maakt_tekstmelding(ingelogde_client, db):
    cursor = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES ('Bakjes', NULL, '2026-01-01 10:00')"
    )
    db.commit()
    item_id = cursor.lastrowid

    resp = ingelogde_client.post(
        f"/verbruiksvoorwerpen/{item_id}/bestellijst-melden",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    melding = db.execute(
        "SELECT * FROM bestellijst_meldingen WHERE bron = 'verbruiksvoorwerp'"
    ).fetchone()
    assert melding is not None
    assert melding["tekst"] == "Bakjes"
    assert melding["product_id"] is None
    assert melding["afgehandeld"] == 0


def test_label_pdf_zonder_qr(ingelogde_client, db):
    cursor = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES ('Bakjes', 'Verpakking', '2026-01-01 10:00')"
    )
    db.commit()
    item_id = cursor.lastrowid

    resp = ingelogde_client.get(f"/verbruiksvoorwerpen/{item_id}/label.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_bulk_labels_pdf(ingelogde_client, db):
    id1 = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES ('A', NULL, '2026-01-01 10:00')"
    ).lastrowid
    id2 = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES ('B', NULL, '2026-01-01 10:00')"
    ).lastrowid
    db.commit()

    resp = ingelogde_client.get(f"/verbruiksvoorwerpen/labels.pdf?ids={id1},{id2}")
    assert resp.status_code == 200
    assert resp.data[:4] == b"%PDF"
