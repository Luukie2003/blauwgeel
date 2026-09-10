from datetime import datetime, timedelta

from conftest import stel_csrf_token_in as _csrf

from app import bereken_frituurvet_status


def test_status_zonder_vervangingen_is_rood(db):
    resultaat = bereken_frituurvet_status(db)
    assert resultaat["laatste"] is None
    assert resultaat["ok"] is False
    assert resultaat["interval"] == 14


def test_status_binnen_interval_is_groen(db):
    datum = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO frituurvet_vervangingen (datum, naam) VALUES (?, 'Luuk')", (datum,)
    )
    db.commit()

    resultaat = bereken_frituurvet_status(db)
    assert resultaat["ok"] is True
    assert resultaat["dagen_geleden"] == 3


def test_status_boven_interval_is_rood(db):
    datum = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO frituurvet_vervangingen (datum, naam) VALUES (?, 'Luuk')", (datum,)
    )
    db.commit()

    resultaat = bereken_frituurvet_status(db)
    assert resultaat["ok"] is False


def test_aangepast_interval_uit_instellingen_wordt_gebruikt(db):
    db.execute("UPDATE instellingen SET frituurvet_interval_dagen = 30 WHERE id = 1")
    datum = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO frituurvet_vervangingen (datum, naam) VALUES (?, 'Luuk')", (datum,)
    )
    db.commit()

    resultaat = bereken_frituurvet_status(db)
    assert resultaat["interval"] == 30
    assert resultaat["ok"] is True


def test_vervangen_route_logt_met_datum_en_gebruiker(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/frituurvet/vervangen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302

    regel = db.execute(
        "SELECT * FROM frituurvet_vervangingen ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert regel is not None
    assert regel["naam"] == "admin"
    assert regel["datum"] is not None


def test_dashboard_toont_frituurvet_statuskaart(ingelogde_client):
    body = ingelogde_client.get("/").data.decode()
    assert "Frituurvet" in body


def test_keuken_instellingen_interval_bijwerken(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/keuken/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "frituurvet_interval_dagen": "21"},
    )
    assert resp.status_code == 302

    waarde = db.execute(
        "SELECT frituurvet_interval_dagen FROM instellingen WHERE id = 1"
    ).fetchone()["frituurvet_interval_dagen"]
    assert waarde == 21


def test_keuken_instellingen_toont_historie(ingelogde_client, db):
    db.execute(
        "INSERT INTO frituurvet_vervangingen (datum, naam) VALUES ('2026-09-01 10:00', 'Luuk')"
    )
    db.commit()

    body = ingelogde_client.get("/keuken/instellingen").data.decode()
    assert "Luuk" in body


def test_keuken_voorraad_toont_alleen_keuken_producten(ingelogde_client, db):
    ander_product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, actief)
           VALUES ('Test Frikandel', 'Keuken', 'Stuks', 10, 5, 1)"""
    )
    db.commit()

    body = ingelogde_client.get("/keuken").data.decode()
    assert "Test Frikandel" in body
    assert ander_product["naam"] not in body


def test_keuken_nieuw_product_knop_selecteert_keuken_categorie(ingelogde_client):
    body = ingelogde_client.get("/producten/nieuw?categorie=Keuken").data.decode()
    optie_start = body.index('value="Keuken"')
    assert "selected" in body[optie_start : optie_start + 40]


def test_keuken_toont_geen_inkoopprijs_en_geen_namen_van_andere_categorieen(ingelogde_client, db):
    """/keuken hergebruikt het Producten-sjabloon vergrendeld op 1 categorie
    (zie render_producten_pagina) -- inkoopprijs blijft daar verborgen
    (zoals op de oude, eigen Keuken-pagina) en de categorieënlijst mag geen
    andere categorienamen lekken (relevant sinds /keuken achter een andere
    sectie zit dan /producten, zie test_secties_rechten.py)."""
    db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, actief, inkoopprijs)
           VALUES ('Test Frikandel', 'Keuken', 'Stuks', 10, 5, 1, 0.75)"""
    )
    db.commit()

    body = ingelogde_client.get("/keuken").data.decode()
    assert "0.75" not in body
    assert 'data-categorie="Bier"' not in body
    assert "Tap Bier" not in body
