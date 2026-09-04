"""Tests voor het corrigeren van een productregel binnen een eerder
afgeronde telling (/tellingen/regels/<id>/corrigeren) -- bijv. omdat er bij
het tellen iets over het hoofd is gezien (een krat die nog ergens stond).
Corrigeert het verkocht/correctie-cijfer (en dus de omzet) van die ene
telling, en de bijbehorende mutatie -- maar raakt nooit de actuele
voorraad, want die wordt altijd apart via boeken in/uit rechtgezet."""

from conftest import stel_csrf_token_in as _csrf


def _maak_telling(db, product_id, voorraad_voor, geteld_aantal, verkoopprijs=2.0):
    cur = db.execute(
        "INSERT INTO tellingen (datum, naam) VALUES ('2026-01-01 10:00', 'Test')"
    )
    telling_id = cur.lastrowid
    verschil = geteld_aantal - voorraad_voor
    verkocht = max(0, -verschil)
    correctie = max(0, verschil)
    cur2 = db.execute(
        """INSERT INTO telling_regels
           (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs),
    )
    regel_id = cur2.lastrowid
    if verkocht > 0:
        db.execute(
            """INSERT INTO mutaties (product_id, type, aantal, datum, naam, opmerking, telling_id)
               VALUES (?, 'uit', ?, '2026-01-01 10:00', 'Test', ?, ?)""",
            (product_id, verkocht, f"Verkocht (telling #{telling_id})", telling_id),
        )
    db.commit()
    return telling_id, regel_id


def test_correctie_verlaagt_verkocht_en_laat_voorraad_met_rust(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = 20 WHERE id = ?", (product["id"],))
    db.commit()
    # Telling: voorraad was 50, geteld 20 -- dus 30 "verkocht". In werkelijkheid
    # stond er nog een krat (10 stuks) die niet meegeteld is.
    telling_id, regel_id = _maak_telling(db, product["id"], voorraad_voor=50, geteld_aantal=20)

    resp = ingelogde_client.post(
        f"/tellingen/regels/{regel_id}/corrigeren",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "geteld_aantal": "30",
            "correctie_opmerking": "Krat over het hoofd gezien",
        },
    )
    assert resp.status_code == 302

    regel = db.execute("SELECT * FROM telling_regels WHERE id = ?", (regel_id,)).fetchone()
    assert regel["geteld_aantal"] == 30
    assert regel["verkocht"] == 20  # was 30, nu 20 (50 - 30)
    assert regel["correctie"] == 0
    assert regel["geteld_aantal_voor_correctie"] == 20
    assert regel["correctie_opmerking"] == "Krat over het hoofd gezien"
    assert regel["gecorrigeerd_door"] == "admin"

    # De actuele voorraad blijft ongewijzigd -- die is al apart rechtgezet.
    product_na = db.execute("SELECT voorraad FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert product_na["voorraad"] == 20

    # De mutatie voor deze telling+product is bijgewerkt naar het nieuwe cijfer.
    mutatie = db.execute(
        "SELECT * FROM mutaties WHERE telling_id = ? AND product_id = ?",
        (telling_id, product["id"]),
    ).fetchone()
    assert mutatie["aantal"] == 20
    assert mutatie["type"] == "uit"


def test_correctie_kan_verkocht_naar_nul_en_correctie_positief_omzetten(ingelogde_client, db):
    """Als de werkelijke telling zelfs hoger blijkt dan de geregistreerde
    voorraad, moet 'verkocht' naar 0 en 'correctie' positief worden --
    precies zoals bij een gewone telling zou gebeuren."""
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    telling_id, regel_id = _maak_telling(db, product["id"], voorraad_voor=50, geteld_aantal=20)

    resp = ingelogde_client.post(
        f"/tellingen/regels/{regel_id}/corrigeren",
        data={"csrf_token": _csrf(ingelogde_client), "geteld_aantal": "60"},
    )
    assert resp.status_code == 302

    regel = db.execute("SELECT * FROM telling_regels WHERE id = ?", (regel_id,)).fetchone()
    assert regel["verkocht"] == 0
    assert regel["correctie"] == 10

    mutatie = db.execute(
        "SELECT * FROM mutaties WHERE telling_id = ? AND product_id = ?",
        (telling_id, product["id"]),
    ).fetchone()
    assert mutatie["type"] == "in"
    assert mutatie["aantal"] == 10


def test_correctie_verschijnt_op_telling_detail_pagina(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    telling_id, regel_id = _maak_telling(db, product["id"], voorraad_voor=50, geteld_aantal=20)
    ingelogde_client.post(
        f"/tellingen/regels/{regel_id}/corrigeren",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "geteld_aantal": "30",
            "correctie_opmerking": "Krat over het hoofd gezien",
        },
    )

    resp = ingelogde_client.get(f"/tellingen/{telling_id}")
    body = resp.data.decode()
    assert "Laatst gecorrigeerd door admin" in body
    assert "was 20" in body
    assert "Krat over het hoofd gezien" in body


def test_omzet_op_telling_detail_klopt_na_correctie(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    telling_id, regel_id = _maak_telling(
        db, product["id"], voorraad_voor=50, geteld_aantal=20, verkoopprijs=2.0
    )
    # Voor correctie: 30 verkocht * 2.00 = 60.00 euro omzet.
    resp_voor = ingelogde_client.get(f"/tellingen/{telling_id}")
    assert "60.00".encode() in resp_voor.data

    ingelogde_client.post(
        f"/tellingen/regels/{regel_id}/corrigeren",
        data={"csrf_token": _csrf(ingelogde_client), "geteld_aantal": "30"},
    )
    # Na correctie: 20 verkocht * 2.00 = 40.00 euro omzet.
    resp_na = ingelogde_client.get(f"/tellingen/{telling_id}")
    assert "40.00".encode() in resp_na.data
