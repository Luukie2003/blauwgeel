"""Tests voor het controlescherm van de looplijst (/tellen/lopen/controleren):
het waarschuwingssignaal bij een sterk afwijkende telling (signaleer_afwijkende_telling
in app.py), en de annuleren/bevestigen-acties op dat scherm."""

from conftest import stel_csrf_token_in as _csrf


def _zet_loop_sessie(client, product_id, totaal, bar="0", hok=None):
    hok = totaal if hok is None else hok
    with client.session_transaction() as s:
        s["loop_review"] = {str(product_id): totaal}
        s["loop_bar"] = {str(product_id): bar}
        s["loop_hok"] = {str(product_id): str(hok)}


def _maak_telling_geschiedenis(db, product_id, verkocht_reeks):
    for verkocht in verkocht_reeks:
        cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-01-01 10:00', 'Test')")
        db.execute(
            """INSERT INTO telling_regels
               (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
               VALUES (?, ?, 0, 0, ?, 0, 1.0)""",
            (cur.lastrowid, product_id, verkocht),
        )
    db.commit()


def test_telling_controleren_signaleert_afwijkende_telling(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 50 WHERE id = ?", (product["id"],))
    db.commit()
    _maak_telling_geschiedenis(db, product["id"], [2, 3, 2, 1])

    _zet_loop_sessie(ingelogde_client, product["id"], totaal=0)
    resp = ingelogde_client.get("/tellen/lopen/controleren")

    assert resp.status_code == 200
    assert "Controleer".encode() in resp.data
    assert "rij-waarschuwing".encode() in resp.data


def test_telling_controleren_geen_signaal_bij_normale_telling(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 50 WHERE id = ?", (product["id"],))
    db.commit()
    _maak_telling_geschiedenis(db, product["id"], [2, 3, 2, 1])

    _zet_loop_sessie(ingelogde_client, product["id"], totaal=48)
    resp = ingelogde_client.get("/tellen/lopen/controleren")

    assert resp.status_code == 200
    assert "rij-waarschuwing".encode() not in resp.data


def test_telling_controleren_geen_signaal_bij_te_weinig_geschiedenis(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 50 WHERE id = ?", (product["id"],))
    db.commit()
    _maak_telling_geschiedenis(db, product["id"], [2, 3])

    _zet_loop_sessie(ingelogde_client, product["id"], totaal=0)
    resp = ingelogde_client.get("/tellen/lopen/controleren")

    assert resp.status_code == 200
    assert "rij-waarschuwing".encode() not in resp.data


def test_telling_controleren_annuleren_slaat_niets_op(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    aantal_voor = db.execute("SELECT COUNT(*) AS n FROM tellingen").fetchone()["n"]

    _zet_loop_sessie(ingelogde_client, product["id"], totaal=99)
    resp = ingelogde_client.post(
        "/tellen/lopen/controleren",
        data={"csrf_token": _csrf(ingelogde_client), "actie": "annuleren"},
    )

    assert resp.status_code == 302
    aantal_na = db.execute("SELECT COUNT(*) AS n FROM tellingen").fetchone()["n"]
    assert aantal_na == aantal_voor
    bijgewerkt = db.execute("SELECT voorraad FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert bijgewerkt["voorraad"] != 99


def test_telling_controleren_bevestigen_slaat_op(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()

    _zet_loop_sessie(ingelogde_client, product["id"], totaal=7)
    resp = ingelogde_client.post(
        "/tellen/lopen/controleren",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "actie": "bevestigen",
            f"totaal_{product['id']}": "7",
        },
    )

    assert resp.status_code == 302
    bijgewerkt = db.execute("SELECT voorraad FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert bijgewerkt["voorraad"] == 7
