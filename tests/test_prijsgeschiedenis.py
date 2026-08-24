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
    return client.post(f"/producten/{product['id']}/bewerken", data=data)


def test_prijswijziging_wordt_gelogd(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    resp = _bewerk_product(ingelogde_client, product, verkoopprijs="3.50")
    assert resp.status_code == 302

    regel = db.execute(
        "SELECT * FROM prijs_geschiedenis WHERE product_id = ?", (product["id"],)
    ).fetchone()
    assert regel is not None
    assert regel["veld"] == "verkoopprijs"
    assert regel["oude_prijs"] == product["verkoopprijs"]
    assert regel["nieuwe_prijs"] == 3.50
    assert regel["naam"] == "admin"


def test_ongewijzigde_prijs_logt_niets(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product)  # alles gelijk gelaten

    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM prijs_geschiedenis WHERE product_id = ?", (product["id"],)
    ).fetchone()["n"]
    assert aantal == 0


def test_beide_prijzen_apart_gelogd_bij_gelijktijdige_wijziging(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product, verkoopprijs="9.99", inkoopprijs="5.00")

    velden = {
        r["veld"]
        for r in db.execute(
            "SELECT * FROM prijs_geschiedenis WHERE product_id = ?", (product["id"],)
        ).fetchall()
    }
    assert velden == {"verkoopprijs", "inkoopprijs"}


def test_geschiedenis_zichtbaar_op_bewerkpagina(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product, verkoopprijs="7.77")

    resp = ingelogde_client.get(f"/producten/{product['id']}/bewerken")
    assert resp.status_code == 200
    assert b"7.77" in resp.data
    assert "Prijsgeschiedenis".encode() in resp.data
