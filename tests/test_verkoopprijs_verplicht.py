from conftest import stel_csrf_token_in as _csrf


def _maak_categorie(db, naam, verkoopprijs_verplicht=1):
    db.execute(
        "INSERT INTO categorieen (naam, verkoopprijs_verplicht) VALUES (?, ?)",
        (naam, verkoopprijs_verplicht),
    )
    db.commit()
    return db.execute("SELECT * FROM categorieen WHERE naam = ?", (naam,)).fetchone()


def _maak_product(db, naam, categorie, verkoopprijs=0, inkoopprijs=1.0):
    db.execute(
        """INSERT INTO producten
           (naam, categorie, eenheid, voorraad, min_voorraad, bestel_hoeveelheid,
            verkoopprijs, inkoopprijs, actief)
           VALUES (?, ?, 'stuks', 0, 0, 0, ?, ?, 1)""",
        (naam, categorie, verkoopprijs, inkoopprijs),
    )
    db.commit()


def test_toggle_wisselt_verkoopprijs_verplicht(ingelogde_client, db):
    categorie = _maak_categorie(db, "Fusten")
    assert categorie["verkoopprijs_verplicht"] == 1

    ingelogde_client.post(
        f"/categorieen/{categorie['id']}/verkoopprijs-verplicht",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    bijgewerkt = db.execute("SELECT * FROM categorieen WHERE id = ?", (categorie["id"],)).fetchone()
    assert bijgewerkt["verkoopprijs_verplicht"] == 0

    ingelogde_client.post(
        f"/categorieen/{categorie['id']}/verkoopprijs-verplicht",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    terug = db.execute("SELECT * FROM categorieen WHERE id = ?", (categorie["id"],)).fetchone()
    assert terug["verkoopprijs_verplicht"] == 1


def test_producten_lijst_verbergt_ontbreekt_badge_voor_uitgezette_categorie(ingelogde_client, db):
    _maak_categorie(db, "Fusten", verkoopprijs_verplicht=0)
    _maak_categorie(db, "Bier extra")
    _maak_product(db, "Testfust", "Fusten", verkoopprijs=0)
    _maak_product(db, "Testflesje", "Bier extra", verkoopprijs=0)

    resp = ingelogde_client.get("/producten")
    body = resp.data.decode()
    rijen = [rij for rij in body.split("<tr") if "Testfust" in rij or "Testflesje" in rij]
    rij_fust = next(r for r in rijen if "Testfust" in r)
    rij_flesje = next(r for r in rijen if "Testflesje" in r)
    # Het flesje (verplichte categorie) moet wel een ontbreekt-badge krijgen.
    assert "ontbreekt" in rij_flesje
    # De fust (categorie zonder verplichting) mag geen ontbreekt-badge krijgen.
    assert "ontbreekt" not in rij_fust


def test_voorraadoverzicht_zonder_prijs_sluit_uitgezette_categorie_uit(ingelogde_client, db):
    _maak_categorie(db, "Fusten", verkoopprijs_verplicht=0)
    _maak_product(db, "Testfust2", "Fusten", verkoopprijs=0)

    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    start = body.index("zonder verkoopprijs")
    kaart = body[start:body.index("</div>", start)]
    assert "Testfust2" not in kaart


def test_voorraadoverzicht_zonder_prijs_toont_wel_verplichte_categorie(ingelogde_client, db):
    _maak_categorie(db, "Bier extra 2")
    _maak_product(db, "Testflesje2", "Bier extra 2", verkoopprijs=0)

    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    start = body.index("zonder verkoopprijs")
    kaart = body[start:body.index("</div>", start)]
    assert "Testflesje2" in kaart


def test_week_overzicht_meldt_fust_alleen_bij_missende_inkoopprijs(ingelogde_client, db):
    _maak_categorie(db, "Fusten", verkoopprijs_verplicht=0)
    _maak_product(db, "Fust compleet", "Fusten", verkoopprijs=0, inkoopprijs=63.28)
    _maak_product(db, "Fust incompleet", "Fusten", verkoopprijs=0, inkoopprijs=0)

    resp = ingelogde_client.get("/week-overzicht")
    body = resp.data.decode()
    assert "Fust compleet" not in body
    assert "Fust incompleet" in body
    assert "geen verkoopprijs" not in body[body.index("Fust incompleet"):body.index("Fust incompleet") + 300]
