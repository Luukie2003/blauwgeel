"""Uitverkocht zetten op het prijzenscherm vanaf de handterminal (routes/app_api_meer.py)."""

from test_app_api import _post, app_client  # noqa: F401 (fixture)


def _op_prijzenscherm(db):
    product_id = db.execute("SELECT id FROM producten WHERE actief = 1 ORDER BY id LIMIT 1").fetchone()[0]
    db.execute("UPDATE producten SET toon_op_kiosk = 1, kiosk_uitverkocht = 0 WHERE id = ?", (product_id,))
    db.commit()
    naam = db.execute("SELECT naam FROM producten WHERE id = ?", (product_id,)).fetchone()[0]
    return product_id, naam


def test_uitverkocht_en_weer_te_koop(app_client, app, db):  # noqa: F811
    product_id, naam = _op_prijzenscherm(db)
    lijst = app_client.get("/api/app/prijzenscherm").get_json()
    assert lijst["uitverkocht"] == 0
    assert any(p["id"] == product_id for g in lijst["groepen"] for p in g["producten"])

    resp = _post(app_client, f"/api/app/producten/{product_id}/uitverkocht", uitverkocht=True)
    data = resp.get_json()
    assert resp.status_code == 200 and data["uitverkocht"] == 1 and data["uitverkocht_op_scherm"] is True
    assert "uitverkocht op de tv" in data["melding"]
    # Op de tv (de versie-poll van het prijzenscherm geeft de uitverkochte namen mee, voor de melding).
    assert naam in app.test_client().get("/kiosk/prijzen/versie").get_json()["uitverkocht"]
    assert app_client.get("/api/app/start").get_json()["uitverkocht_op_tv"] == [naam]
    assert app_client.get(f"/api/app/producten/{product_id}").get_json()["info"]["uitverkocht_op_scherm"] is True

    _post(app_client, f"/api/app/producten/{product_id}/uitverkocht", uitverkocht=False)
    assert naam not in app.test_client().get("/kiosk/prijzen/versie").get_json()["uitverkocht"]
    assert app_client.get("/api/app/start").get_json()["uitverkocht_op_tv"] == []


def test_een_product_dat_niet_op_het_prijzenscherm_staat(app_client, db):  # noqa: F811
    product_id = db.execute("SELECT id FROM producten ORDER BY id LIMIT 1").fetchone()[0]
    db.execute("UPDATE producten SET toon_op_kiosk = 0 WHERE id = ?", (product_id,))
    db.commit()
    resp = _post(app_client, f"/api/app/producten/{product_id}/uitverkocht", uitverkocht=True)
    assert "staat niet op het prijzenscherm" in resp.get_json()["melding"]
    assert _post(app_client, "/api/app/producten/999999/uitverkocht", uitverkocht=True).status_code == 404
