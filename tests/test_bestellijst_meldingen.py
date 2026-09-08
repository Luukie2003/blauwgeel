from conftest import stel_csrf_token_in as _csrf


def _maak_product(db, naam="Gemeld product"):
    cursor = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad) "
        "VALUES (?, 'Fris', 'stuks', 10, 5)",
        (naam,),
    )
    db.commit()
    return cursor.lastrowid


def test_qr_meldingen_verschijnen_gegroepeerd_op_bestellijst(client, ingelogde_client, db):
    product_id = _maak_product(db)
    for _ in range(3):
        csrf = _csrf(client)
        client.post(f"/scan/{product_id}/melden", data={"csrf_token": csrf})

    resp = ingelogde_client.get("/bestellijst")
    assert resp.status_code == 200
    assert b"Gemeld product" in resp.data
    assert b"3x gemeld" in resp.data


def test_verbruiksvoorwerp_tekstmelding_verschijnt_op_bestellijst(ingelogde_client, db):
    item_id = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES ('Bakjes', NULL, '2026-01-01 10:00')"
    ).lastrowid
    db.commit()
    ingelogde_client.post(
        f"/verbruiksvoorwerpen/{item_id}/bestellijst-melden",
        data={"csrf_token": _csrf(ingelogde_client)},
    )

    resp = ingelogde_client.get("/bestellijst")
    assert resp.status_code == 200
    assert b"Bakjes" in resp.data
    assert b"verbruiksvoorwerp" in resp.data


def test_product_melding_afhandelen_verbergt_hem(client, ingelogde_client, db):
    product_id = _maak_product(db)
    csrf = _csrf(client)
    client.post(f"/scan/{product_id}/melden", data={"csrf_token": csrf})

    resp = ingelogde_client.post(
        f"/bestellijst/meldingen/product/{product_id}/afhandelen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    melding = db.execute(
        "SELECT * FROM bestellijst_meldingen WHERE product_id = ?", (product_id,)
    ).fetchone()
    assert melding["afgehandeld"] == 1
    assert melding["afgehandeld_door"] == "admin"

    # De productnaam kan nog los in de "ander product toevoegen"-lijst staan
    # (dat is onafhankelijk van meldingen) -- de melding-badge zelf moet weg zijn.
    resp = ingelogde_client.get("/bestellijst")
    assert b"x gemeld" not in resp.data


def test_product_afhandelen_dekt_alle_openstaande_meldingen_voor_dat_product(client, ingelogde_client, db):
    product_id = _maak_product(db)
    for _ in range(2):
        csrf = _csrf(client)
        client.post(f"/scan/{product_id}/melden", data={"csrf_token": csrf})

    ingelogde_client.post(
        f"/bestellijst/meldingen/product/{product_id}/afhandelen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    onafgehandeld = db.execute(
        "SELECT COUNT(*) AS n FROM bestellijst_meldingen WHERE product_id = ? AND afgehandeld = 0",
        (product_id,),
    ).fetchone()["n"]
    assert onafgehandeld == 0


def test_tekstmelding_afhandelen_verbergt_hem(ingelogde_client, db):
    item_id = db.execute(
        "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES ('Servetten', NULL, '2026-01-01 10:00')"
    ).lastrowid
    db.commit()
    ingelogde_client.post(
        f"/verbruiksvoorwerpen/{item_id}/bestellijst-melden",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    melding = db.execute("SELECT * FROM bestellijst_meldingen WHERE tekst = 'Servetten'").fetchone()

    resp = ingelogde_client.post(
        f"/bestellijst/meldingen/{melding['id']}/afhandelen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    resp = ingelogde_client.get("/bestellijst")
    assert b"(verbruiksvoorwerp)" not in resp.data


def test_afhandelroutes_vragen_om_inloggen(client, db):
    product_id = _maak_product(db)
    resp = client.post(f"/bestellijst/meldingen/product/{product_id}/afhandelen", data={})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
