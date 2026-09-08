def test_service_worker_wordt_geserveerd_op_domeinniveau(client):
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.content_type


def test_service_worker_is_toegankelijk_zonder_inloggen(client):
    resp = client.get("/sw.js")
    assert resp.status_code == 200


def test_offline_pagina_is_toegankelijk_zonder_inloggen(client):
    resp = client.get("/offline")
    assert resp.status_code == 200
    assert b"Geen verbinding" in resp.data


def test_boeken_formulier_heeft_offline_wachtrij_klasse(ingelogde_client):
    resp = ingelogde_client.get("/boeken")
    assert b'class="boeking-formulier"' in resp.data
    assert b'data-offline-wachtrij="Boeking"' in resp.data


def test_product_detail_formulier_heeft_offline_wachtrij_klasse(ingelogde_client, db):
    cursor = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad) "
        "VALUES ('Offline testproduct', 'Fris', 'stuks', 5, 2)"
    )
    db.commit()
    resp = ingelogde_client.get(f"/producten/{cursor.lastrowid}")
    assert b'class="boeking-formulier"' in resp.data
    assert b'data-offline-wachtrij="Boeking"' in resp.data


def test_boeken_werkt_nog_gewoon_als_normale_paginapost(ingelogde_client, db):
    """De offline-wachtrij is puur clientside JS -- een normale form-post
    (zoals bij uitgeschakelde JS) moet precies als voorheen blijven werken."""
    cursor = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad) "
        "VALUES ('Gewone boeking', 'Fris', 'stuks', 5, 2)"
    )
    db.commit()
    product_id = cursor.lastrowid
    from conftest import stel_csrf_token_in

    csrf = stel_csrf_token_in(ingelogde_client)
    resp = ingelogde_client.post(
        "/boeken",
        data={"product_id": product_id, "type": "in", "aantal": "3", "csrf_token": csrf},
    )
    assert resp.status_code == 302
    voorraad = db.execute(
        "SELECT voorraad FROM producten WHERE id = ?", (product_id,)
    ).fetchone()["voorraad"]
    assert voorraad == 8
