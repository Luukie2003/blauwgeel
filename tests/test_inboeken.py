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


def test_niet_aangevinkte_regel_wordt_manco_en_boekt_niets_in(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    voorraad_voor = product["voorraad"]
    _maak_bestelling(ingelogde_client, product["id"], 3)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()
    regel = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchone()

    resp = ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/inboeken",
        data={"csrf_token": _csrf(ingelogde_client), f"ontvangen_{regel['id']}": "3"},
    )
    assert resp.status_code == 302

    product_na = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert product_na["voorraad"] == voorraad_voor  # manco: niets bijgeboekt

    regel_na = db.execute("SELECT * FROM bestelregels WHERE id = ?", (regel["id"],)).fetchone()
    assert regel_na["manco"] == 1
    assert regel_na["aantal_ontvangen"] == 0

    bestelling_na = db.execute(
        "SELECT * FROM bestellingen WHERE id = ?", (bestelling["id"],)
    ).fetchone()
    assert bestelling_na["status"] == "ontvangen"  # order is afgehandeld, ondanks manco


def test_manco_corrigeren_naar_binnen_boekt_alsnog_in(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    voorraad_voor = product["voorraad"]
    _maak_bestelling(ingelogde_client, product["id"], 3)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()
    regel = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchone()

    # Eerst per ongeluk als manco ingeboekt (vinkje niet aan)...
    ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/inboeken",
        data={"csrf_token": _csrf(ingelogde_client), f"ontvangen_{regel['id']}": "3"},
    )
    # ...later alsnog binnengekomen, dus corrigeren met het vinkje aan.
    ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/inboeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            f"binnen_{regel['id']}": "on",
            f"ontvangen_{regel['id']}": "3",
        },
    )

    product_na = db.execute("SELECT * FROM producten WHERE id = ?", (product["id"],)).fetchone()
    besteleenheid_factor = product["besteleenheid_factor"] or 1
    assert product_na["voorraad"] == voorraad_voor + 3 * besteleenheid_factor

    regel_na = db.execute("SELECT * FROM bestelregels WHERE id = ?", (regel["id"],)).fetchone()
    assert regel_na["manco"] == 0


def test_extra_product_toevoegen_bij_inboeken_boekt_het_in(ingelogde_client, db):
    besteld_product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    extra_product = db.execute(
        "SELECT * FROM producten WHERE actief = 1 AND id != ? LIMIT 1", (besteld_product["id"],)
    ).fetchone()
    extra_voorraad_voor = extra_product["voorraad"]

    _maak_bestelling(ingelogde_client, besteld_product["id"], 2)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()
    regel = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchone()

    resp = ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/inboeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            f"binnen_{regel['id']}": "on",
            f"ontvangen_{regel['id']}": "2",
            "nieuw_product_id": str(extra_product["id"]),
            "nieuw_aantal": "5",
        },
    )
    assert resp.status_code == 302

    extra_na = db.execute("SELECT * FROM producten WHERE id = ?", (extra_product["id"],)).fetchone()
    factor = extra_product["besteleenheid_factor"] or 1
    assert extra_na["voorraad"] == extra_voorraad_voor + 5 * factor

    nieuwe_regel = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ? AND product_id = ?",
        (bestelling["id"], extra_product["id"]),
    ).fetchone()
    assert nieuwe_regel is not None
    assert nieuwe_regel["aantal_besteld"] == 0  # niet oorspronkelijk besteld
    assert nieuwe_regel["manco"] == 0


def test_inboeken_pagina_toont_alleen_niet_bestelde_producten_als_toevoegoptie(ingelogde_client, db):
    besteld_product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _maak_bestelling(ingelogde_client, besteld_product["id"], 1)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.get(f"/bestellingen/{bestelling['id']}/inboeken")
    body = resp.data.decode()
    select_html = body.split('id="nieuw-product-select"')[1].split("</select>")[0]
    # Het reeds bestelde product hoort niet nogmaals in de "extra toevoegen"-select te staan.
    assert besteld_product["naam"] not in select_html


def test_bestellijst_mengt_geen_regels_tussen_verschillende_bestellingen(ingelogde_client, db):
    """Regressietest voor de query-batching in bestellijst(): bij meerdere
    open bestellingen tegelijk moet elke bestelling zijn eigen productregels
    tonen, niet die van een andere bestelling."""
    producten = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 2").fetchall()
    product_a, product_b = producten[0], producten[1]

    _maak_bestelling(ingelogde_client, product_a["id"], 2)
    bestelling_a = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()
    _maak_bestelling(ingelogde_client, product_b["id"], 4)
    bestelling_b = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()

    body = ingelogde_client.get("/bestellijst").data.decode()
    # <strong>-tag i.p.v. platte tekst zoeken, want "Bestelling #N" komt ook
    # voor in de (opgestapelde) flash-meldingen van de twee aanmaak-POSTs.
    kop_a = f"<strong>Bestelling #{bestelling_a['id']}</strong>"
    kop_b = f"<strong>Bestelling #{bestelling_b['id']}</strong>"
    start_a, start_b = body.index(kop_a), body.index(kop_b)
    kaart_a = body[start_a:start_b] if start_a < start_b else body[start_a:]
    kaart_b = body[start_b:start_a] if start_b < start_a else body[start_b:]

    assert product_a["naam"] in kaart_a
    assert product_b["naam"] not in kaart_a
    assert product_b["naam"] in kaart_b
    assert product_a["naam"] not in kaart_b


def test_bestelling_bewerken_vervangt_aantal(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    factor = product["besteleenheid_factor"] or 1
    _maak_bestelling(ingelogde_client, product["id"], 2)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "referentie": "Aangepaste referentie",
            f"aantal_{product['id']}": "5",
        },
    )
    assert resp.status_code == 302

    regels = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchall()
    assert len(regels) == 1
    assert regels[0]["aantal_besteld"] == 5 * factor

    bestelling_na = db.execute(
        "SELECT * FROM bestellingen WHERE id = ?", (bestelling["id"],)
    ).fetchone()
    assert bestelling_na["referentie"] == "Aangepaste referentie"


def test_bestelling_bewerken_kan_product_wisselen(ingelogde_client, db):
    producten = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 2").fetchall()
    product_a, product_b = producten[0], producten[1]
    _maak_bestelling(ingelogde_client, product_a["id"], 2)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "referentie": "",
            f"aantal_{product_a['id']}": "",  # weggehaald
            f"aantal_{product_b['id']}": "3",  # toegevoegd
        },
    )
    assert resp.status_code == 302

    regels = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchall()
    product_ids = {r["product_id"] for r in regels}
    assert product_ids == {product_b["id"]}


def test_bestelling_bewerken_op_ontvangen_bestelling_wordt_geweigerd(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _maak_bestelling(ingelogde_client, product["id"], 2)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()
    regel = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchone()
    ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/inboeken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            f"binnen_{regel['id']}": "on",
            f"ontvangen_{regel['id']}": "2",
        },
    )

    resp = ingelogde_client.post(
        f"/bestellingen/{bestelling['id']}/bewerken",
        data={"csrf_token": _csrf(ingelogde_client), f"aantal_{product['id']}": "9"},
    )
    assert resp.status_code == 302

    regel_na = db.execute(
        "SELECT * FROM bestelregels WHERE id = ?", (regel["id"],)
    ).fetchone()
    assert regel_na["aantal_besteld"] == regel["aantal_besteld"]  # ongewijzigd


def test_bestelling_bewerken_pagina_toont_huidig_aantal(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    _maak_bestelling(ingelogde_client, product["id"], 4)
    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.get(f"/bestellingen/{bestelling['id']}/bewerken")
    assert resp.status_code == 200
    body = resp.data.decode()
    veld_start = body.index(f'name="aantal_{product["id"]}"')
    veld_html = body[veld_start : veld_start + 200]
    assert 'value="4"' in veld_html


def _maak_testproduct(db, naam, voorraad, min_voorraad):
    db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, besteleenheid_factor, actief)
           VALUES (?, 'Test', 'Stuks', ?, ?, 1, 1)""",
        (naam, voorraad, min_voorraad),
    )
    db.commit()
    return db.execute("SELECT * FROM producten WHERE naam = ?", (naam,)).fetchone()


def test_bestellijst_toont_voorgesteld_label_alleen_bij_krappe_producten(ingelogde_client, db):
    _maak_testproduct(db, "Laag Testproduct", voorraad=1, min_voorraad=10)
    _maak_testproduct(db, "Normaal Testproduct", voorraad=50, min_voorraad=10)

    body = ingelogde_client.get("/bestellijst").data.decode()

    laag_start = body.index("Laag Testproduct")
    assert "Voorgesteld" in body[laag_start : laag_start + 150]

    # Niet-krap product hoort wel in de "zelf toevoegen"-keuzelijst te staan...
    assert 'data-naam="Normaal Testproduct"' in body
    # ...maar nergens met het "Voorgesteld"-label.
    normaal_start = body.index("Normaal Testproduct")
    assert "Voorgesteld" not in body[normaal_start : normaal_start + 150]


def test_overige_producten_sluit_al_openstaand_besteld_product_uit(ingelogde_client, db):
    product = _maak_testproduct(db, "Al Besteld Testproduct", voorraad=50, min_voorraad=10)
    _maak_bestelling(ingelogde_client, product["id"], 1)

    body = ingelogde_client.get("/bestellijst").data.decode()
    assert 'data-naam="Al Besteld Testproduct"' not in body


def test_bestelling_aanmaken_mixt_voorgesteld_en_zelf_toegevoegd_product(ingelogde_client, db):
    laag = _maak_testproduct(db, "Laag Testproduct 2", voorraad=1, min_voorraad=10)
    zelf = _maak_testproduct(db, "Zelf Toegevoegd Testproduct", voorraad=50, min_voorraad=10)

    resp = ingelogde_client.post(
        "/bestellijst/aanmaken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": [str(laag["id"]), str(zelf["id"])],
            f"aantal_{laag['id']}": "3",
            f"aantal_{zelf['id']}": "2",
        },
    )
    assert resp.status_code == 302

    bestelling = db.execute("SELECT * FROM bestellingen ORDER BY id DESC LIMIT 1").fetchone()
    regels = db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling["id"],)
    ).fetchall()
    product_ids = {r["product_id"] for r in regels}
    assert product_ids == {laag["id"], zelf["id"]}
