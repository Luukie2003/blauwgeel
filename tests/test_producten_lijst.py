from conftest import stel_csrf_token_in as _csrf


def _zet_actief(client, db, product_id, actief):
    rij = db.execute("SELECT actief FROM producten WHERE id = ?", (product_id,)).fetchone()
    if bool(rij["actief"]) != actief:
        client.post(f"/producten/{product_id}/actief", data={"csrf_token": _csrf(client)})


def test_inactieve_producten_staan_onderaan_op_productenlijst(ingelogde_client, db):
    actief = db.execute("SELECT id, naam FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    ander = db.execute(
        "SELECT id, naam FROM producten WHERE actief = 1 AND id != ? LIMIT 1", (actief["id"],)
    ).fetchone()
    _zet_actief(ingelogde_client, db, ander["id"], actief=False)

    resp = ingelogde_client.get("/producten")
    body = resp.data.decode()
    assert body.index(actief["naam"]) < body.index(ander["naam"])

    _zet_actief(ingelogde_client, db, ander["id"], actief=True)


def test_heractiveren_zet_product_terug_bovenaan(ingelogde_client, db):
    a, b = db.execute("SELECT id, naam FROM producten WHERE actief = 1 LIMIT 2").fetchall()
    _zet_actief(ingelogde_client, db, a["id"], actief=False)
    _zet_actief(ingelogde_client, db, b["id"], actief=False)

    # A weer actief maken -> hoort weer boven het nog-inactieve product B te staan.
    _zet_actief(ingelogde_client, db, a["id"], actief=True)
    resp = ingelogde_client.get("/producten")
    body = resp.data.decode()
    assert body.index(a["naam"]) < body.index(b["naam"])

    _zet_actief(ingelogde_client, db, b["id"], actief=True)


def test_inactief_staat_ook_onderaan_bij_bulk_bewerken(ingelogde_client, db):
    actief = db.execute("SELECT id, naam FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    ander = db.execute(
        "SELECT id, naam FROM producten WHERE actief = 1 AND id != ? LIMIT 1", (actief["id"],)
    ).fetchone()
    _zet_actief(ingelogde_client, db, ander["id"], actief=False)

    resp = ingelogde_client.get("/producten/bulk-bewerken")
    body = resp.data.decode()
    assert body.index(actief["naam"]) < body.index(ander["naam"])

    _zet_actief(ingelogde_client, db, ander["id"], actief=True)


def test_minimumvoorraad_en_besteleenheid_urls_verwijzen_door_naar_bulk_bewerken(ingelogde_client):
    for url in ("/producten/minimumvoorraad", "/producten/besteleenheid"):
        resp = ingelogde_client.get(url)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/producten/bulk-bewerken")


def test_bulk_bewerken_slaat_minimumvoorraad_en_besteleenheid_tegelijk_op(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    resp = ingelogde_client.post(
        "/producten/bulk-bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            f"min_{product['id']}": "7",
            f"eenheid_{product['id']}": "Krat",
            f"factor_{product['id']}": "24",
        },
    )
    assert resp.status_code == 302

    bijgewerkt = db.execute(
        "SELECT min_voorraad, besteleenheid, besteleenheid_factor FROM producten WHERE id = ?",
        (product["id"],),
    ).fetchone()
    assert bijgewerkt["min_voorraad"] == 7
    assert bijgewerkt["besteleenheid"] == "Krat"
    assert bijgewerkt["besteleenheid_factor"] == 24


def test_bulk_bewerken_laat_leeg_veld_ongemoeid(ingelogde_client, db):
    product = db.execute(
        "SELECT * FROM producten WHERE actief = 1 AND besteleenheid_factor = 1 LIMIT 1"
    ).fetchone()
    oude_min = product["min_voorraad"]
    ingelogde_client.post(
        "/producten/bulk-bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            f"eenheid_{product['id']}": "Krat",
            f"factor_{product['id']}": "12",
        },
    )
    bijgewerkt = db.execute(
        "SELECT min_voorraad, besteleenheid_factor FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert bijgewerkt["min_voorraad"] == oude_min
    assert bijgewerkt["besteleenheid_factor"] == 12
