from conftest import stel_csrf_token_in as _csrf


def _zet_actief(client, db, product_id, actief):
    rij = db.execute("SELECT actief FROM producten WHERE id = ?", (product_id,)).fetchone()
    if bool(rij["actief"]) != actief:
        client.post(f"/producten/{product_id}/actief", data={"csrf_token": _csrf(client)})


def test_verwijderen_van_product_met_bestelgeschiedenis_geeft_nette_foutmelding(ingelogde_client, db):
    """bestelregels.product_id heeft bewust geen ON DELETE CASCADE (die
    geschiedenis mag nooit stilzwijgend verdwijnen) -- verwijderen moet dus
    netjes geweigerd worden i.p.v. een 500 (sqlite3.IntegrityError)."""
    product = db.execute("SELECT id, naam FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute(
        "INSERT INTO bestellingen (status, aangemaakt_op) VALUES ('besteld', '2026-01-01 10:00')"
    )
    bestelling_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    db.execute(
        "INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, 1)",
        (bestelling_id, product["id"]),
    )
    db.commit()

    resp = ingelogde_client.post(
        f"/producten/{product['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    nog_aanwezig = db.execute(
        "SELECT id FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert nog_aanwezig is not None

    vervolg = ingelogde_client.get(resp.headers["Location"])
    assert "kan niet verwijderd worden" in vervolg.data.decode()


def test_verwijderen_van_product_met_tellinggeschiedenis_geeft_nette_foutmelding(ingelogde_client, db):
    product = db.execute("SELECT id, naam FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-01-01', 'Test')")
    telling_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    db.execute(
        """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal)
           VALUES (?, ?, 10, 8)""",
        (telling_id, product["id"]),
    )
    db.commit()

    resp = ingelogde_client.post(
        f"/producten/{product['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    nog_aanwezig = db.execute(
        "SELECT id FROM producten WHERE id = ?", (product["id"],)
    ).fetchone()
    assert nog_aanwezig is not None


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


# ---------- Kerncijfers, snelfilters en marge (1.50.0) ----------


def test_productenlijst_kerncijfers_en_marge(ingelogde_client, db):
    db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, inkoopprijs, actief,
                                  besteleenheid, besteleenheid_factor)
           VALUES ('Lijsttest Pils', 'Bier', 'Fles', 5, 24, 2.5, 19.2, 1, 'Krat', 24)"""
    )
    db.commit()
    pid = db.execute("SELECT id FROM producten WHERE naam = 'Lijsttest Pils'").fetchone()[0]
    tekst = ingelogde_client.get("/producten").data.decode()
    assert "Actieve producten" in tekst and "Onder het minimum" in tekst and "Zonder barcode" in tekst
    assert f'href="/producten/{pid}" class="product-lijst-naam"' in tekst
    assert 'data-snel="laag"' in tekst and 'data-laag="1"' in tekst
    assert ">68%<" in tekst  # (2,50 - 0,80) / 2,50


def test_vrijwilliger_ziet_geen_marge_in_de_lijst(client, db):
    from test_secties_rechten import _login, _maak_vrijwilliger

    _maak_vrijwilliger(db, "lijsthulp", "voorraad")
    _login(client, "lijsthulp")
    tekst = client.get("/producten").data.decode()
    assert "Actieve producten" in tekst and "<th class=\"kolom-breed\">Marge</th>" not in tekst
