"""Tests voor het corrigeren van een productregel binnen een eerder
afgeronde telling (/tellingen/regels/<id>/corrigeren) -- bijv. omdat er bij
het tellen iets over het hoofd is gezien (een krat die nog ergens stond).
Corrigeert het verkocht/correctie-cijfer (en dus de omzet) van die ene
telling, en de bijbehorende mutatie. Is het de laatste telling van het
product, dan gaat met het vinkje 'voorraad_aanpassen' (standaard aan) de
huidige voorraad mee met het verschil; zonder vinkje, of bij een oudere
telling, blijft de voorraad zoals hij is."""

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


def test_correctie_zonder_vinkje_laat_voorraad_met_rust(ingelogde_client, db):
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

    # Zonder het vinkje blijft de actuele voorraad ongewijzigd (bijv. omdat die al apart is rechtgezet).
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


# ---------- De huidige voorraad meenemen ----------


def _product_met_voorraad(db, voorraad):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute("UPDATE producten SET voorraad = ?, auto_inactief_bij_nul = 0 WHERE id = ?", (voorraad, product["id"]))
    db.commit()
    return product["id"]


def _voorraad(db, product_id):
    return db.execute("SELECT voorraad FROM producten WHERE id = ?", (product_id,)).fetchone()[0]


def _corrigeer(client, regel_id, geteld, vinkje=True):
    data = {"csrf_token": _csrf(client), "geteld_aantal": str(geteld)}
    if vinkje:
        data["voorraad_aanpassen"] = "1"
    return client.post(f"/tellingen/regels/{regel_id}/corrigeren", data=data)


def test_correctie_op_de_laatste_telling_past_de_voorraad_aan(ingelogde_client, db):
    """Geteld 20, daarna 2 verkocht en geboekt (voorraad 18); de telling blijkt 30 te moeten zijn: voorraad 28."""
    pid = _product_met_voorraad(db, 18)
    telling_id, regel_id = _maak_telling(db, pid, voorraad_voor=50, geteld_aantal=20)
    _corrigeer(ingelogde_client, regel_id, 30)
    assert _voorraad(db, pid) == 28
    assert db.execute("SELECT verkocht FROM telling_regels WHERE id = ?", (regel_id,)).fetchone()[0] == 20
    # Nog eens corrigeren (30 -> 25) gaat vanaf de nieuwe stand.
    _corrigeer(ingelogde_client, regel_id, 25)
    assert _voorraad(db, pid) == 23


def test_correctie_op_een_oudere_telling_raakt_de_voorraad_niet(ingelogde_client, db):
    pid = _product_met_voorraad(db, 15)
    _, regel_id = _maak_telling(db, pid, voorraad_voor=50, geteld_aantal=20)
    later = db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-01-08 10:00', 'Test')").lastrowid
    db.execute(
        """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
           VALUES (?, ?, 20, 15, 5, 2.0)""",
        (later, pid),
    )
    db.commit()
    resp = _corrigeer(ingelogde_client, regel_id, 30)
    assert _voorraad(db, pid) == 15
    tekst = ingelogde_client.get(resp.headers["Location"]).data.decode()
    assert "daarna opnieuw geteld" in tekst


def test_vinkje_staat_alleen_bij_de_laatste_telling(ingelogde_client, db):
    pid = _product_met_voorraad(db, 20)
    telling_id, _ = _maak_telling(db, pid, voorraad_voor=50, geteld_aantal=20)
    assert 'name="voorraad_aanpassen"' in ingelogde_client.get(f"/tellingen/{telling_id}").data.decode()
    later = db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-01-08 10:00', 'Test')").lastrowid
    db.execute(
        "INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkoopprijs) VALUES (?, ?, 20, 20, 2.0)",
        (later, pid),
    )
    db.commit()
    assert 'name="voorraad_aanpassen"' not in ingelogde_client.get(f"/tellingen/{telling_id}").data.decode()


def _knop(client, telling_id):
    return client.get(f"/tellingen/{telling_id}").data.decode()


def test_voorraad_die_niet_meeging_op_de_telling_zetten(ingelogde_client, db):
    """Gecorrigeerd zonder dat de voorraad meeging (zoals vóór deze versie): een knop zet de voorraad op de telling."""
    pid = _product_met_voorraad(db, 20)
    telling_id, regel_id = _maak_telling(db, pid, voorraad_voor=50, geteld_aantal=20)
    _corrigeer(ingelogde_client, regel_id, 30, vinkje=False)
    tekst = _knop(ingelogde_client, telling_id)
    assert "De huidige voorraad is 20" in tekst and "Voorraad op 30 zetten" in tekst

    ingelogde_client.post(f"/tellingen/regels/{regel_id}/voorraad-bijwerken", data={"csrf_token": _csrf(ingelogde_client)})
    assert _voorraad(db, pid) == 30
    ingelogde_client.post(f"/tellingen/regels/{regel_id}/voorraad-bijwerken", data={"csrf_token": _csrf(ingelogde_client)})
    assert _voorraad(db, pid) == 30
    assert "Voorraad op 30 zetten" not in _knop(ingelogde_client, telling_id)


def test_boekingen_na_de_telling_tellen_mee(ingelogde_client, db):
    pid = _product_met_voorraad(db, 17)  # 20 geteld, daarna 3 verkocht geboekt
    telling_id, regel_id = _maak_telling(db, pid, voorraad_voor=50, geteld_aantal=20)
    db.execute("INSERT INTO mutaties (product_id, type, aantal, datum, naam) VALUES (?, 'uit', 3, '2026-01-02 20:00', 'Test')", (pid,))
    db.commit()
    _corrigeer(ingelogde_client, regel_id, 30, vinkje=False)
    assert "Voorraad op 27 zetten" in _knop(ingelogde_client, telling_id)


def test_geen_knop_als_de_voorraad_al_met_de_hand_klopt(ingelogde_client, db):
    """Zoals bij Rivella: gecorrigeerd van 18 naar 40 en de voorraad zelf al op 40 gezet."""
    pid = _product_met_voorraad(db, 18)
    telling_id, regel_id = _maak_telling(db, pid, voorraad_voor=42, geteld_aantal=18)
    _corrigeer(ingelogde_client, regel_id, 40, vinkje=False)
    db.execute("UPDATE producten SET voorraad = 40 WHERE id = ?", (pid,))
    db.commit()
    assert "zetten</button>" not in _knop(ingelogde_client, telling_id)
    ingelogde_client.post(f"/tellingen/regels/{regel_id}/voorraad-bijwerken", data={"csrf_token": _csrf(ingelogde_client)})
    assert _voorraad(db, pid) == 40


def test_handterminal_toont_vinkje_en_knop(ingelogde_client, db):
    pid = _product_met_voorraad(db, 20)
    telling_id, regel_id = _maak_telling(db, pid, voorraad_voor=50, geteld_aantal=20)
    _corrigeer(ingelogde_client, regel_id, 30, vinkje=False)
    ingelogde_client.get("/weergave/pda")
    tekst = ingelogde_client.get(f"/tellingen/{telling_id}").data.decode()
    assert 'name="voorraad_aanpassen"' in tekst and "Voorraad op 30 zetten" in tekst
