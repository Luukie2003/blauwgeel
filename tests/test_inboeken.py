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
