def _maak_product(db, naam, categorie="Fris", voorraad=10, min_voorraad=5, actief=1):
    cursor = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, actief) "
        "VALUES (?, ?, 'stuks', ?, ?, ?)",
        (naam, categorie, voorraad, min_voorraad, actief),
    )
    db.commit()
    return cursor.lastrowid


def test_actieve_producten_verschijnen_op_voorraadoverzicht(ingelogde_client, db):
    _maak_product(db, "Actief Testproduct", categorie="Fris")
    resp = ingelogde_client.get("/voorraadoverzicht")
    assert resp.status_code == 200
    assert b"Actief Testproduct" in resp.data
    assert b"Alle actieve producten" in resp.data


def test_inactieve_producten_staan_niet_in_de_lijst(ingelogde_client, db):
    # voorraad=0 zodat dit product ook niet via de aparte "inactief met nog
    # voorraad"-waarschuwing elders op de pagina verschijnt -- deze test gaat
    # puur over de "Alle actieve producten"-sectie zelf.
    _maak_product(db, "Inactief Testproduct", categorie="Fris", voorraad=0, actief=0)
    resp = ingelogde_client.get("/voorraadoverzicht")
    assert resp.status_code == 200
    assert b"Inactief Testproduct" not in resp.data


def test_producten_gegroepeerd_per_categorie(ingelogde_client, db):
    _maak_product(db, "Colaatje", categorie="Frisdrank")
    resp = ingelogde_client.get("/voorraadoverzicht")
    assert resp.status_code == 200
    assert b"Frisdrank" in resp.data


def test_lage_voorraad_krijgt_waarschuwingsbadge(ingelogde_client, db):
    _maak_product(db, "Bijna op", categorie="Fris", voorraad=1, min_voorraad=5)
    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    idx = body.index("Bijna op")
    omgeving = body[idx:idx + 400]
    assert "badge-laag" in omgeving
