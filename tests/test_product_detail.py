"""Tests voor de productpagina (foto, voorraad, snel boeken, geschiedenis)
en de zoekbalk erboven in de handterminal-weergave."""

from conftest import stel_csrf_token_in as _csrf


def _maak_bestelling(client, product_id, aantal):
    resp = client.post(
        "/bestellijst/nieuw",
        data={
            "csrf_token": _csrf(client),
            "referentie": "Test",
            f"aantal_{product_id}": str(aantal),
        },
    )
    assert resp.status_code == 302
    return resp


def test_zoeken_vindt_product_op_naam(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE naam = 'Tap Bier'").fetchone()
    resp = ingelogde_client.get("/producten/zoeken?q=tap")
    data = resp.get_json()
    ids = [r["id"] for r in data["resultaten"]]
    assert product["id"] in ids


def test_zoeken_met_te_korte_term_geeft_niets_terug(ingelogde_client):
    resp = ingelogde_client.get("/producten/zoeken?q=t")
    data = resp.get_json()
    assert data["resultaten"] == []


def test_zoeken_negeert_inactieve_producten(ingelogde_client, db):
    db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, actief) "
        "VALUES ('Zoektest Inactief', 'Overig', 'stuks', 0, 0, 0)"
    )
    db.commit()
    resp = ingelogde_client.get("/producten/zoeken?q=Zoektest")
    data = resp.get_json()
    assert data["resultaten"] == []


def test_productpagina_toont_naam_en_voorraad(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE naam = 'Tap Bier'").fetchone()
    resp = ingelogde_client.get(f"/producten/{product['id']}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Tap Bier" in body
    assert "Boeken" in body


def test_onbekend_product_redirect_naar_productenlijst(ingelogde_client):
    resp = ingelogde_client.get("/producten/999999", follow_redirects=True)
    assert resp.status_code == 200
    assert "Product niet gevonden" in resp.data.decode()


def test_boeken_vanaf_productpagina_gaat_terug_naar_productpagina(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE naam = 'Tap Bier'").fetchone()
    resp = ingelogde_client.post(
        "/boeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": str(product["id"]),
            "type": "in",
            "aantal": "5",
            "terug_naar_product": str(product["id"]),
        },
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == f"/producten/{product['id']}"

    product_na = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert product_na["voorraad"] == product["voorraad"] + 5


def test_boeken_zonder_terug_naar_product_gaat_naar_boeken(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE naam = 'Tap Bier'").fetchone()
    resp = ingelogde_client.post(
        "/boeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": str(product["id"]),
            "type": "in",
            "aantal": "1",
        },
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/boeken"


def test_productpagina_toont_recente_boeking_met_link(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE naam = 'Tap Bier'").fetchone()
    ingelogde_client.post(
        "/boeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": str(product["id"]),
            "type": "in",
            "aantal": "7",
        },
    )
    resp = ingelogde_client.get(f"/producten/{product['id']}")
    body = resp.data.decode()
    assert "7 " in body
    assert f"/geschiedenis?product_id={product['id']}" in body


def test_pda_inboeken_toont_kaarten_met_manco_toggle(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE naam = 'Tap Bier'").fetchone()
    _maak_bestelling(ingelogde_client, product["id"], 4)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()

    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get(f"/bestellingen/{bestelling['id']}/inboeken")
    body = resp.data.decode()
    assert 'id="inboeken-kaarten"' in body
    assert 'id="inboeken-tabel"' not in body
    assert "Binnengekomen" in body


def test_desktop_inboeken_toont_gewoon_de_tabel(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE naam = 'Tap Bier'").fetchone()
    _maak_bestelling(ingelogde_client, product["id"], 4)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()

    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get(f"/bestellingen/{bestelling['id']}/inboeken")
    body = resp.data.decode()
    assert 'id="inboeken-tabel"' in body
    assert 'id="inboeken-kaarten"' not in body
