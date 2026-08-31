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


def test_inactief_staat_ook_onderaan_bij_minimumvoorraad_en_besteleenheid(ingelogde_client, db):
    actief = db.execute("SELECT id, naam FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    ander = db.execute(
        "SELECT id, naam FROM producten WHERE actief = 1 AND id != ? LIMIT 1", (actief["id"],)
    ).fetchone()
    _zet_actief(ingelogde_client, db, ander["id"], actief=False)

    for url in ("/producten/minimumvoorraad", "/producten/besteleenheid"):
        resp = ingelogde_client.get(url)
        body = resp.data.decode()
        assert body.index(actief["naam"]) < body.index(ander["naam"])

    _zet_actief(ingelogde_client, db, ander["id"], actief=True)
