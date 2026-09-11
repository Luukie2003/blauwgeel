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
    assert b"Melden voor bestellijst" in resp.data


def test_scan_landing_onbekend_product_geeft_404(client):
    resp = client.get("/scan/99999")
    assert resp.status_code == 404
    assert b"niet gevonden" in resp.data


def test_scan_melden_werkt_zonder_inloggen(client, db):
    product_id = _maak_product(db)
    csrf = _csrf(client)
    # De landingspagina zelf zorgt normaal voor het csrf-token in de sessie
    # (via csrf_token() in het formulier); hier zetten we 'm rechtstreeks,
    # net als de rest van de tests, zie conftest.stel_csrf_token_in.
    resp = client.post(
        f"/scan/{product_id}/melden",
        data={"csrf_token": csrf},
    )
    assert resp.status_code == 302
    melding = db.execute(
        "SELECT * FROM bestellijst_meldingen WHERE product_id = ?", (product_id,)
    ).fetchone()
    assert melding is not None
    assert melding["bron"] == "qr_scan"
    assert melding["afgehandeld"] == 0


def test_scan_melden_zonder_csrf_token_mislukt(client, db):
    product_id = _maak_product(db)
    resp = client.post(f"/scan/{product_id}/melden", data={})
    assert resp.status_code == 302
    assert db.execute("SELECT COUNT(*) AS n FROM bestellijst_meldingen").fetchone()["n"] == 0


def test_scan_melden_meerdere_keren_telt_op(client, db):
    product_id = _maak_product(db)
    for _ in range(3):
        csrf = _csrf(client)
        client.post(f"/scan/{product_id}/melden", data={"csrf_token": csrf})
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM bestellijst_meldingen WHERE product_id = ?", (product_id,)
    ).fetchone()["n"]
    assert aantal == 3


def test_scan_melden_onbekend_product(client):
    csrf = _csrf(client)
    resp = client.post("/scan/99999/melden", data={"csrf_token": csrf}, follow_redirects=True)
    assert b"niet gevonden" in resp.data


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
    assert b"Melden voor bestellijst" in resp.data
    # Geen productpagina om naartoe te gaan -- die knop hoort hier niet.
    assert b"Naar productpagina" not in resp.data


def test_scan_landing_verbruiksvoorwerp_onbekend_geeft_404(client):
    resp = client.get("/scan/verbruiksvoorwerp/99999")
    assert resp.status_code == 404
    assert b"niet gevonden" in resp.data.lower() or b"Niet gevonden" in resp.data


def test_scan_melden_verbruiksvoorwerp_werkt_zonder_inloggen(client, db):
    item_id = _maak_verbruiksvoorwerp(db)
    csrf = _csrf(client)
    resp = client.post(
        f"/scan/verbruiksvoorwerp/{item_id}/melden",
        data={"csrf_token": csrf},
    )
    assert resp.status_code == 302
    melding = db.execute(
        "SELECT * FROM bestellijst_meldingen WHERE bron = 'verbruiksvoorwerp' AND tekst = 'Frietbakjes'"
    ).fetchone()
    assert melding is not None
    assert melding["product_id"] is None
    assert melding["afgehandeld"] == 0


def test_scan_melden_verbruiksvoorwerp_zonder_csrf_token_mislukt(client, db):
    item_id = _maak_verbruiksvoorwerp(db)
    resp = client.post(f"/scan/verbruiksvoorwerp/{item_id}/melden", data={})
    assert resp.status_code == 302
    assert db.execute("SELECT COUNT(*) AS n FROM bestellijst_meldingen").fetchone()["n"] == 0


def test_scan_melden_verbruiksvoorwerp_onbekend(client):
    csrf = _csrf(client)
    resp = client.post(
        "/scan/verbruiksvoorwerp/99999/melden", data={"csrf_token": csrf}, follow_redirects=True
    )
    assert b"niet gevonden" in resp.data.lower()


def test_verbruiksvoorwerp_schaplabel_qr_wijst_naar_scan_landing(ingelogde_client, db):
    item_id = _maak_verbruiksvoorwerp(db)
    resp = ingelogde_client.get(f"/verbruiksvoorwerpen/{item_id}/label.pdf")
    assert resp.status_code == 200
    assert resp.data[:4] == b"%PDF"
