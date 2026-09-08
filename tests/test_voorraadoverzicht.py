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


def test_inactieve_producten_staan_niet_in_de_actieve_lijst(ingelogde_client, db):
    # voorraad=0 zodat dit product ook niet via de aparte "inactief met nog
    # voorraad"-waarschuwing elders op de pagina verschijnt -- deze test gaat
    # puur over de "Alle actieve producten"-sectie zelf. Het product mag wel
    # (bewust) in de volledige, filterbare lijst onderaan de pagina staan.
    _maak_product(db, "Inactief Testproduct", categorie="Fris", voorraad=0, actief=0)
    resp = ingelogde_client.get("/voorraadoverzicht")
    assert resp.status_code == 200
    body = resp.data.decode()
    actieve_sectie = body[body.index('id="voorraadoverzicht-groepen"'):body.index('id="vpl-tabel"')]
    assert "Inactief Testproduct" not in actieve_sectie


def test_inactieve_producten_staan_wel_in_de_volledige_lijst(ingelogde_client, db):
    _maak_product(db, "Inactief Volledig", categorie="Fris", voorraad=0, actief=0)
    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    volledige_sectie = body[body.index('id="vpl-tabel"'):]
    assert "Inactief Volledig" in volledige_sectie
    assert 'data-status="inactief"' in volledige_sectie


def test_producten_gegroepeerd_per_categorie(ingelogde_client, db):
    _maak_product(db, "Colaatje", categorie="Frisdrank")
    resp = ingelogde_client.get("/voorraadoverzicht")
    assert resp.status_code == 200
    assert b"Frisdrank" in resp.data


def test_volledige_lijst_heeft_filtervinkjes_per_categorie(ingelogde_client, db):
    _maak_product(db, "Product A", categorie="Bier")
    _maak_product(db, "Product B", categorie="Fris")
    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    assert '<input type="checkbox" class="vpl-categorie" value="Bier"' in body
    assert '<input type="checkbox" class="vpl-categorie" value="Fris"' in body
    assert '<input type="checkbox" class="vpl-status" value="actief"' in body
    assert '<input type="checkbox" class="vpl-status" value="inactief"' in body


def test_volledige_lijst_heeft_subcategorie_vinkjes(ingelogde_client, db):
    product_id = _maak_product(db, "Met subcat", categorie="Bier")
    db.execute("UPDATE producten SET subcategorie = 'Speciaalbier' WHERE id = ?", (product_id,))
    db.commit()
    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    assert '<input type="checkbox" class="vpl-subcategorie" value="Speciaalbier"' in body


def test_volledige_lijst_heeft_sorteeropties(ingelogde_client, db):
    _maak_product(db, "Sorteerbaar")
    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    assert 'id="vpl-sorteren"' in body
    for optie in ("naam-az", "naam-za", "voorraad-hoog", "voorraad-laag"):
        assert f'value="{optie}"' in body


def test_volledige_lijst_rij_heeft_juiste_data_attributen(ingelogde_client, db):
    _maak_product(db, "Data attributen check", categorie="Bier", voorraad=7, min_voorraad=3)
    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    volledige_sectie = body[body.index('id="vpl-tabel"'):]
    idx = volledige_sectie.index("Data attributen check")
    rij_start = volledige_sectie.rindex("<tr", 0, idx)
    rij = volledige_sectie[rij_start:idx]
    assert 'data-status="actief"' in rij
    assert 'data-categorie="Bier"' in rij
    assert 'data-voorraad="7"' in rij
    assert 'data-naam="data attributen check"' in rij


def test_lage_voorraad_krijgt_waarschuwingsbadge(ingelogde_client, db):
    _maak_product(db, "Bijna op", categorie="Fris", voorraad=1, min_voorraad=5)
    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    idx = body.index("Bijna op")
    omgeving = body[idx:idx + 400]
    assert "badge-laag" in omgeving
