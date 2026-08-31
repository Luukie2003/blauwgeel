def _maak_product(db, naam, categorie, subcategorie=None, voorraad=10, min_voorraad=0, verkoopprijs=1.0):
    db.execute(
        """INSERT INTO producten
           (naam, categorie, subcategorie, eenheid, voorraad, min_voorraad, bestel_hoeveelheid,
            verkoopprijs, inkoopprijs, actief)
           VALUES (?, ?, ?, 'stuks', ?, ?, 0, ?, 1.0, 1)""",
        (naam, categorie, subcategorie, voorraad, min_voorraad, verkoopprijs),
    )
    db.commit()


def test_voorraadoverzicht_toont_subcategorie_uitsplitsing(ingelogde_client, db):
    _maak_product(db, "IPA testbier", "Bier", subcategorie="Speciaalbier", voorraad=10, verkoopprijs=3.0)
    _maak_product(db, "Pils testbier", "Bier", subcategorie=None, voorraad=10, verkoopprijs=2.0)

    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    start = body.index("Voorraadwaarde per categorie")
    kaart = body[start:body.index("Top 10 producten", start)]
    assert "Speciaalbier" in kaart
    assert "Overig" in kaart


def test_voorraadoverzicht_geen_uitsplitsing_zonder_subcategorieen(ingelogde_client, db):
    _maak_product(db, "Chipszakje testproduct", "Chips", subcategorie=None, voorraad=5, verkoopprijs=1.5)

    resp = ingelogde_client.get("/voorraadoverzicht")
    body = resp.data.decode()
    start = body.index("Voorraadwaarde per categorie")
    kaart = body[start:body.index("Top 10 producten", start)]
    positie_chips = kaart.index("Chips")
    # Direct na de Chips-regel volgt geen "Overig"-subregel, want binnen
    # Chips wordt (in deze test) geen enkele subcategorie gebruikt.
    stuk_na_chips = kaart[positie_chips:positie_chips + 200]
    assert "Overig" not in stuk_na_chips


def test_week_overzicht_onder_minimum_toont_subcategorie(ingelogde_client, db):
    _maak_product(
        db, "Laagvoorraad testbier", "Bier", subcategorie="Speciaalbier", voorraad=1, min_voorraad=5
    )

    resp = ingelogde_client.get("/week-overzicht")
    body = resp.data.decode()
    positie = body.index("Laagvoorraad testbier")
    assert "Speciaalbier" in body[positie:positie + 300]


def test_dashboard_lage_voorraad_toont_subcategorie(ingelogde_client, db):
    _maak_product(
        db, "Dashboard testbier", "Bier", subcategorie="Speciaalbier", voorraad=1, min_voorraad=5
    )

    resp = ingelogde_client.get("/")
    body = resp.data.decode()
    positie = body.index("Dashboard testbier")
    assert "Speciaalbier" in body[positie:positie + 300]
