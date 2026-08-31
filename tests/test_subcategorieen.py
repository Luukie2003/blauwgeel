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


def test_nieuwe_subcategorie_bij_bewerken_wordt_geregistreerd(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    resp = _bewerk_product(ingelogde_client, product, subcategorie="Speciaalbier")
    assert resp.status_code == 302

    geregistreerd = db.execute(
        "SELECT * FROM subcategorieen WHERE categorie = ? AND naam = 'Speciaalbier'",
        (product["categorie"],),
    ).fetchone()
    assert geregistreerd is not None

    bijgewerkt = db.execute("SELECT subcategorie FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert bijgewerkt["subcategorie"] == "Speciaalbier"


def test_nieuwe_subcategorie_bij_nieuw_product_wordt_geregistreerd(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/producten/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Testbier met subcategorie",
            "categorie": "Bier",
            "subcategorie": "Ambachtelijk",
            "eenheid": "fles",
            "voorraad": 0,
            "min_voorraad": 0,
            "bestel_hoeveelheid": 0,
            "verkoopprijs": "2.00",
            "actief": "on",
        },
    )
    assert resp.status_code == 302
    geregistreerd = db.execute(
        "SELECT * FROM subcategorieen WHERE categorie = 'Bier' AND naam = 'Ambachtelijk'"
    ).fetchone()
    assert geregistreerd is not None


def test_bestaande_subcategorie_wordt_niet_gedupliceerd(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product, subcategorie="Speciaalbier")
    _bewerk_product(ingelogde_client, product, subcategorie="Speciaalbier")

    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM subcategorieen WHERE categorie = ? AND naam = 'Speciaalbier'",
        (product["categorie"],),
    ).fetchone()["n"]
    assert aantal == 1


def test_subcategorie_leeg_registreert_niets(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    aantal_voor = db.execute("SELECT COUNT(*) AS n FROM subcategorieen").fetchone()["n"]
    _bewerk_product(ingelogde_client, product, subcategorie="")
    aantal_na = db.execute("SELECT COUNT(*) AS n FROM subcategorieen").fetchone()["n"]
    assert aantal_na == aantal_voor


def test_productformulieren_laden_zonder_fout_met_subcategorieen(ingelogde_client, db):
    ingelogde_client.post(
        "/subcategorieen/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "categorie": "Bier", "naam": "Speciaalbier"},
    )
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()

    resp_nieuw = ingelogde_client.get("/producten/nieuw")
    assert resp_nieuw.status_code == 200
    assert b"subcategorie-opties" in resp_nieuw.data

    resp_bewerken = ingelogde_client.get(f"/producten/{product['id']}/bewerken")
    assert resp_bewerken.status_code == 200
    assert b"subcategorie-opties" in resp_bewerken.data
