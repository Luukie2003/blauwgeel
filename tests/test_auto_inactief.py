from conftest import stel_csrf_token_in as _csrf


def _maak_product(db, naam="Testproduct", voorraad=5, auto_inactief=1, actief=1):
    cursor = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, "
        "auto_inactief_bij_nul, actief) VALUES (?, 'Fris', 'stuks', ?, 0, ?, ?)",
        (naam, voorraad, auto_inactief, actief),
    )
    db.commit()
    return cursor.lastrowid


def _is_actief(db, product_id):
    return bool(db.execute("SELECT actief FROM producten WHERE id = ?", (product_id,)).fetchone()["actief"])


def test_boeken_uit_naar_nul_deactiveert_met_vinkje(ingelogde_client, db):
    product_id = _maak_product(db, voorraad=3, auto_inactief=1)
    resp = ingelogde_client.post(
        "/boeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": product_id,
            "type": "uit",
            "aantal": "3",
        },
    )
    assert resp.status_code == 302
    assert _is_actief(db, product_id) is False


def test_boeken_uit_naar_nul_laat_actief_zonder_vinkje(ingelogde_client, db):
    product_id = _maak_product(db, voorraad=3, auto_inactief=0)
    resp = ingelogde_client.post(
        "/boeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": product_id,
            "type": "uit",
            "aantal": "3",
        },
    )
    assert resp.status_code == 302
    assert _is_actief(db, product_id) is True


def test_boeken_uit_niet_naar_nul_blijft_actief(ingelogde_client, db):
    product_id = _maak_product(db, voorraad=5, auto_inactief=1)
    ingelogde_client.post(
        "/boeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": product_id,
            "type": "uit",
            "aantal": "2",
        },
    )
    assert _is_actief(db, product_id) is True


def test_tellen_naar_nul_deactiveert_met_vinkje(ingelogde_client, db):
    product_id = _maak_product(db, voorraad=4, auto_inactief=1)
    resp = ingelogde_client.post(
        "/tellen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            f"geteld_{product_id}": "0",
        },
    )
    assert resp.status_code == 302
    assert _is_actief(db, product_id) is False


def test_levering_inboeken_bij_negatieve_voorraad_naar_nul_deactiveert(ingelogde_client, db):
    product_id = _maak_product(db, voorraad=-2, auto_inactief=1)
    resp = ingelogde_client.post(
        "/leveringen/inboeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "referentie": "Test",
            f"aantal_{product_id}": "2",
        },
    )
    assert resp.status_code == 302
    assert _is_actief(db, product_id) is False


def test_bestelling_verwijderen_naar_nul_deactiveert(ingelogde_client, db):
    product_id = _maak_product(db, voorraad=0, auto_inactief=1)
    resp = ingelogde_client.post(
        "/bestellijst/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "referentie": "Test",
            f"aantal_{product_id}": "5",
        },
    )
    assert resp.status_code == 302
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()
    regel = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchone()
    ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/inboeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            f"binnen_{regel['id']}": "on",
            f"ontvangen_{regel['id']}": "5",
        },
    )
    # Even weer actief zetten (het product is nu op voorraad 5, dus niet
    # automatisch gedeactiveerd door het inboeken zelf) om de terugdraai-actie
    # te kunnen isoleren.
    db.execute("UPDATE producten SET actief = 1 WHERE id = ?", (product_id,))
    db.commit()
    assert db.execute("SELECT voorraad FROM producten WHERE id = ?", (product_id,)).fetchone()["voorraad"] == 5

    resp = ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT voorraad FROM producten WHERE id = ?", (product_id,)).fetchone()["voorraad"] == 0
    assert _is_actief(db, product_id) is False


def test_product_bewerken_forceert_inactief_bij_nul_met_vinkje(ingelogde_client, db):
    product_id = _maak_product(db, voorraad=5, auto_inactief=1, actief=1)
    resp = ingelogde_client.post(
        f"/producten/{product_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Testproduct",
            "categorie": "Fris",
            "eenheid": "stuks",
            "voorraad": "0",
            "min_voorraad": "0",
            "bestel_hoeveelheid": "0",
            "verkoopprijs": "1.00",
            "actief": "on",
            "auto_inactief_bij_nul": "on",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"automatisch op inactief gezet" in resp.data
    assert _is_actief(db, product_id) is False


def test_product_nieuw_forceert_inactief_bij_nul_met_vinkje(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/producten/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Nieuw testproduct",
            "categorie": "Fris",
            "eenheid": "stuks",
            "voorraad": "0",
            "min_voorraad": "0",
            "bestel_hoeveelheid": "0",
            "verkoopprijs": "1.00",
            "actief": "on",
            "auto_inactief_bij_nul": "on",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"automatisch op inactief gezet" in resp.data
    gebruiker = db.execute(
        "SELECT actief FROM producten WHERE naam = 'Nieuw testproduct'"
    ).fetchone()
    assert bool(gebruiker["actief"]) is False


def test_verwerk_auto_inactief_laat_al_inactief_product_met_rust(db):
    """Geen dubbele flash/no-op als het product al inactief was."""
    from helpers import verwerk_auto_inactief

    product_id = _maak_product(db, voorraad=0, auto_inactief=1, actief=0)
    resultaat = verwerk_auto_inactief(db, product_id, 0)
    assert resultaat is None
