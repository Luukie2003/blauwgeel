import io

from conftest import stel_csrf_token_in as _csrf

from app import PRODUCT_AFBEELDINGEN_MAP

_KLEINE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def test_afbeelding_uploaden_bij_nieuw_product(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/producten/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Testbier met foto",
            "categorie": "Bier",
            "eenheid": "fles",
            "voorraad": 0,
            "min_voorraad": 0,
            "bestel_hoeveelheid": 0,
            "verkoopprijs": "2.00",
            "actief": "on",
            "afbeelding": (io.BytesIO(_KLEINE_PNG), "bier.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    product = db.execute(
        "SELECT * FROM producten WHERE naam = 'Testbier met foto'"
    ).fetchone()
    assert product["afbeelding"] is not None
    afbeelding_pad = PRODUCT_AFBEELDINGEN_MAP / product["afbeelding"]
    assert afbeelding_pad.exists()
    afbeelding_pad.unlink()


def test_afbeelding_uploaden_bij_bestaand_product(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    resp = _bewerk_product(
        ingelogde_client, product, afbeelding=(io.BytesIO(_KLEINE_PNG), "product.png")
    )
    assert resp.status_code == 302

    bijgewerkt = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert bijgewerkt["afbeelding"] is not None
    afbeelding_pad = PRODUCT_AFBEELDINGEN_MAP / bijgewerkt["afbeelding"]
    assert afbeelding_pad.exists()
    afbeelding_pad.unlink()


def test_afbeelding_blijft_behouden_zonder_nieuwe_upload(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product, afbeelding=(io.BytesIO(_KLEINE_PNG), "product.png"))
    tussenstand = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()

    _bewerk_product(ingelogde_client, tussenstand, verkoopprijs="4.44")  # geen nieuwe afbeelding
    bijgewerkt = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert bijgewerkt["afbeelding"] == tussenstand["afbeelding"]
    (PRODUCT_AFBEELDINGEN_MAP / bijgewerkt["afbeelding"]).unlink()


def test_afbeelding_kan_verwijderd_worden(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product, afbeelding=(io.BytesIO(_KLEINE_PNG), "product.png"))
    tussenstand = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()
    afbeelding_pad = PRODUCT_AFBEELDINGEN_MAP / tussenstand["afbeelding"]

    _bewerk_product(ingelogde_client, tussenstand, afbeelding_verwijderen="on")
    bijgewerkt = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert bijgewerkt["afbeelding"] is None
    afbeelding_pad.unlink()


def test_producten_lijst_toont_thumbnail(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _bewerk_product(ingelogde_client, product, afbeelding=(io.BytesIO(_KLEINE_PNG), "product.png"))
    bijgewerkt = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()

    resp = ingelogde_client.get("/producten")
    assert b"product-thumb" in resp.data
    (PRODUCT_AFBEELDINGEN_MAP / bijgewerkt["afbeelding"]).unlink()
