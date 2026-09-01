"""Tests voor de fusten-pagina (/fusten, bereken_fust_verkopen in app.py):
waarschijnlijke verkoop per fust, afgeleid uit de gewone voorraadtellingen op
basis van de nieuwe velden glazen_per_fust en prijs_per_glas."""

from conftest import stel_csrf_token_in as _csrf


def _bewerk_product(client, product, **overrides):
    data = {
        "csrf_token": _csrf(client),
        "artikelcode": product["artikelcode"] or "",
        "naam": product["naam"],
        "categorie": product["categorie"],
        "eenheid": product["eenheid"],
        "voorraad": product["voorraad"],
        "min_voorraad": product["min_voorraad"],
        "bestel_hoeveelheid": product["bestel_hoeveelheid"],
        "verkoopprijs": product["verkoopprijs"],
        "inkoopprijs": product["inkoopprijs"],
        "besteleenheid_factor": product["besteleenheid_factor"] or 1,
        "actief": "on" if product["actief"] else "",
    }
    data.update(overrides)
    return client.post(
        f"/producten/{product['id']}/bewerken", data=data, content_type="multipart/form-data"
    )


def test_fusten_pagina_leeg_zonder_ingestelde_fusten(ingelogde_client, db):
    resp = ingelogde_client.get("/fusten")
    assert resp.status_code == 200
    assert "Nog geen enkel product ingesteld als fust".encode() in resp.data


def test_bewerken_slaat_glazen_per_fust_en_prijs_per_glas_op(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    resp = _bewerk_product(
        ingelogde_client, product, glazen_per_fust="80", prijs_per_glas="2.50"
    )
    assert resp.status_code == 302

    bijgewerkt = db.execute(
        "SELECT glazen_per_fust, prijs_per_glas FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert bijgewerkt["glazen_per_fust"] == 80
    assert bijgewerkt["prijs_per_glas"] == 2.5


def test_ingesteld_fust_product_verschijnt_op_fusten_pagina(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product, glazen_per_fust="80", prijs_per_glas="2.50")

    resp = ingelogde_client.get("/fusten")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert product["naam"] in body
    assert "Nog geen fust leeg geteld" in body


def test_lege_fust_via_telling_geeft_waarschijnlijke_verkoop(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product, glazen_per_fust="80", prijs_per_glas="2.50")
    db.execute("UPDATE producten SET voorraad = 2 WHERE id = ?", (product["id"],))
    db.commit()

    # 1 fust leeg: van 2 naar 1 geteld.
    ingelogde_client.post(
        "/tellen",
        data={"csrf_token": _csrf(ingelogde_client), f"geteld_{product['id']}": "1"},
    )

    resp = ingelogde_client.get("/fusten")
    body = resp.data.decode()
    assert resp.status_code == 200
    assert "1</td>" in body  # 1 fust leeg
    assert "80</td>" in body  # 80 glazen geschat
    assert "€ 200.00" in body  # 80 x 2.50


def test_normaal_product_zonder_fust_instelling_telt_niet_mee(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 20 WHERE id = ?", (product["id"],))
    db.commit()
    ingelogde_client.post(
        "/tellen",
        data={"csrf_token": _csrf(ingelogde_client), f"geteld_{product['id']}": "5"},
    )

    resp = ingelogde_client.get("/fusten")
    assert resp.status_code == 200
    assert "Nog geen enkel product ingesteld als fust".encode() in resp.data
