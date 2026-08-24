from conftest import stel_csrf_token_in as _csrf


def test_telling_werkt_voorraad_bij_en_registreert_correctie(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    assert product["voorraad"] == 0

    resp = ingelogde_client.post(
        "/tellen",
        data={"csrf_token": _csrf(ingelogde_client), f"geteld_{product['id']}": "10"},
    )
    assert resp.status_code == 302

    bijgewerkt = db.execute(
        "SELECT * FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert bijgewerkt["voorraad"] == 10

    regel = db.execute(
        "SELECT * FROM telling_regels WHERE product_id = ? ORDER BY id DESC LIMIT 1",
        (product["id"],),
    ).fetchone()
    assert regel["correctie"] == 10
    assert regel["verkocht"] == 0


def test_telling_registreert_verkoop_bij_afname(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 20 WHERE id = ?", (product["id"],))
    db.commit()

    ingelogde_client.post(
        "/tellen",
        data={"csrf_token": _csrf(ingelogde_client), f"geteld_{product['id']}": "12"},
    )

    bijgewerkt = db.execute(
        "SELECT * FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert bijgewerkt["voorraad"] == 12

    regel = db.execute(
        "SELECT * FROM telling_regels WHERE product_id = ? ORDER BY id DESC LIMIT 1",
        (product["id"],),
    ).fetchone()
    assert regel["verkocht"] == 8
    assert regel["correctie"] == 0


def test_telling_zonder_ingevulde_aantallen_maakt_niets_aan(ingelogde_client, db):
    aantal_voor = db.execute("SELECT COUNT(*) AS n FROM tellingen").fetchone()["n"]
    resp = ingelogde_client.post(
        "/tellen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    aantal_na = db.execute("SELECT COUNT(*) AS n FROM tellingen").fetchone()["n"]
    assert aantal_na == aantal_voor


def test_bestelling_handmatig_klaarzetten_raakt_voorraad_niet_tot_inboeken(ingelogde_client, db):
    """Regressietest voor de 'factuur klaarzetten'-flow: een handmatig
    aangemaakte bestelling (los van de lage-voorraad-suggesties) mag de
    voorraad pas wijzigen op het moment van inboeken, niet bij het
    klaarzetten zelf."""
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    voorraad_voor = product["voorraad"]

    resp = ingelogde_client.post(
        "/bestellijst/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "referentie": "Testfactuur 123",
            f"aantal_{product['id']}": "3",
        },
    )
    assert resp.status_code == 302

    bestelling = db.execute(
        "SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert bestelling["status"] == "besteld"
    assert bestelling["referentie"] == "Testfactuur 123"

    regel = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchone()
    besteleenheid_factor = product["besteleenheid_factor"] or 1
    assert regel["aantal_besteld"] == 3 * besteleenheid_factor

    onveranderd = db.execute(
        "SELECT * FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert onveranderd["voorraad"] == voorraad_voor  # nog niet ingeboekt

    ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/inboeken",
        data={"csrf_token": _csrf(ingelogde_client), f"ontvangen_{regel['id']}": "3"},
    )
    bijgewerkt = db.execute(
        "SELECT * FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert bijgewerkt["voorraad"] == voorraad_voor + 3 * besteleenheid_factor


def test_negatief_geteld_aantal_wordt_genegeerd(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 5 WHERE id = ?", (product["id"],))
    db.commit()

    ingelogde_client.post(
        "/tellen",
        data={"csrf_token": _csrf(ingelogde_client), f"geteld_{product['id']}": "-3"},
    )

    ongewijzigd = db.execute(
        "SELECT * FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert ongewijzigd["voorraad"] == 5
