import json
import re
import sqlite3
from datetime import date

import database
from conftest import stel_csrf_token_in as _csrf
from helpers import bepaal_tegenstander, is_trainingsavond, vandaag_amsterdam
from test_kiosk import _voeg_product_toe


def test_is_trainingsavond_klopt_op_de_vaste_trainingsdag():
    # TRAININGSDAG = 2 (woensdag) -- zie helpers.py.
    woensdag = date(2026, 9, 23)
    assert woensdag.weekday() == 2
    assert is_trainingsavond(woensdag) is True


def test_is_trainingsavond_is_false_op_andere_dagen():
    donderdag = date(2026, 9, 24)
    assert is_trainingsavond(donderdag) is False


def test_bepaal_tegenstander_bij_thuiswedstrijd():
    assert bepaal_tegenstander("Blauw Geel'15 2-Potetos 4") == "Potetos 4"


def test_bepaal_tegenstander_bij_uitwedstrijd_omschrijving():
    assert bepaal_tegenstander("Potetos 4-Blauw Geel'15 2") == "Potetos 4"


def test_bepaal_tegenstander_zonder_clubnaam_geeft_none():
    assert bepaal_tegenstander("Potetos 4-VEV'67 6") is None


def test_migratie_trainingsavond_kopieert_bestaande_toon_op_kiosk_waarde(tmp_path):
    """Geen gewone kolom-migratie (die zou toon_op_kiosk_trainingsavond op 0
    laten staan) -- bij het aanmaken van de kolom moet de dan geldende
    toon_op_kiosk-waarde gekopieerd worden, zodat de trainingsavond-selectie
    er in eerste instantie hetzelfde uitziet als normaal."""
    conn = sqlite3.connect(tmp_path / "migratie_test.db")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE producten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            naam TEXT NOT NULL,
            toon_op_kiosk INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute("INSERT INTO producten (naam, toon_op_kiosk) VALUES ('Bier', 1)")
    conn.execute("INSERT INTO producten (naam, toon_op_kiosk) VALUES ('Wijn', 0)")
    conn.commit()

    database._migreer_kiosk_trainingsavond(conn)

    waarden = dict(
        conn.execute("SELECT naam, toon_op_kiosk_trainingsavond FROM producten").fetchall()
    )
    assert waarden == {"Bier": 1, "Wijn": 0}


def test_trainingsavond_tab_toont_eigen_selectie(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Speciaalbier", toon_op_kiosk=1)
    db.execute(
        "UPDATE producten SET toon_op_kiosk_trainingsavond = 0 WHERE id = ?", (product_id,)
    )
    db.commit()

    normaal = ingelogde_client.get("/kiosk/prijzen/instellingen?dag=normaal")
    training = ingelogde_client.get("/kiosk/prijzen/instellingen?dag=trainingsavond")

    assert f'name="toon_{product_id}" checked' in normaal.data.decode()
    assert f'name="toon_{product_id}" checked' not in training.data.decode()


def test_opslaan_op_trainingsavond_tab_raakt_normale_kolom_niet(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Speciaalbier", toon_op_kiosk=1)
    db.execute(
        "UPDATE producten SET toon_op_kiosk_trainingsavond = 0 WHERE id = ?", (product_id,)
    )
    db.commit()

    resp = ingelogde_client.post(
        "/kiosk/prijzen/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "dag": "trainingsavond"},
    )
    assert resp.status_code == 302

    rij = db.execute(
        "SELECT toon_op_kiosk, toon_op_kiosk_trainingsavond FROM producten WHERE id = ?",
        (product_id,),
    ).fetchone()
    assert rij["toon_op_kiosk"] == 1
    assert rij["toon_op_kiosk_trainingsavond"] == 0


def test_prijzenscherm_toont_trainingsavond_selectie_op_trainingsavond(client, db, monkeypatch):
    monkeypatch.setattr("routes.kiosk.is_trainingsavond", lambda datum: True)
    alleen_normaal = _voeg_product_toe(db, "Alleen normaal", toon_op_kiosk=1)
    db.execute(
        "UPDATE producten SET toon_op_kiosk_trainingsavond = 0 WHERE id = ?", (alleen_normaal,)
    )
    alleen_training = _voeg_product_toe(db, "Alleen trainingsavond", toon_op_kiosk=0)
    db.execute(
        "UPDATE producten SET toon_op_kiosk_trainingsavond = 1 WHERE id = ?", (alleen_training,)
    )
    db.commit()

    resp = client.get("/kiosk/prijzen")
    tekst = resp.data.decode()

    assert "Alleen trainingsavond" in tekst
    assert "Alleen normaal" not in tekst


def _wedstrijden_json(tekst):
    """Haalt de JS-array 'wedstrijdenVandaag' uit de paginabron (zie
    kiosk_prijzen_scherm.html) -- de banner/popup zelf wordt client-side
    gevuld, dus in de kale server-HTML valt alleen deze data te checken."""
    match = re.search(r"var wedstrijdenVandaag = (\[.*?\]);", tekst)
    assert match is not None
    return json.loads(match.group(1))


def test_wedstrijddag_welkom_toont_tegenstander_uit_agenda(client, db):
    vandaag = vandaag_amsterdam().isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, tijd) VALUES (?, ?, ?, 1, ?)",
        ("Blauw Geel'15 2", vandaag, "Blauw Geel'15 2-Haren 1", "14:00"),
    )
    db.commit()

    resp = client.get("/kiosk/prijzen")
    assert _wedstrijden_json(resp.data.decode()) == [{"tijd": "14:00", "tegenstander": "Haren 1"}]


def test_wedstrijddag_welkom_zonder_bekende_tijd(client, db):
    """Geen tijd bekend (bijv. een 'hele dag'-agenda-item) -- de banner moet
    dan alsnog gegevens krijgen (client-side valt 'ie dan terug op de hele
    dag, zie actieveWedstrijddagTegenstander())."""
    vandaag = vandaag_amsterdam().isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES (?, ?, ?, 1)",
        ("Blauw Geel'15 2", vandaag, "Blauw Geel'15 2-Haren 1"),
    )
    db.commit()

    resp = client.get("/kiosk/prijzen")
    assert _wedstrijden_json(resp.data.decode()) == [{"tijd": None, "tegenstander": "Haren 1"}]


def test_wedstrijddag_welkom_meerdere_thuiswedstrijden_op_tijd_gesorteerd(client, db):
    vandaag = vandaag_amsterdam().isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, tijd) VALUES (?, ?, ?, 1, ?)",
        ("Blauw Geel'15 1", vandaag, "Blauw Geel'15 1-VEV'67 1", "16:00"),
    )
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, tijd) VALUES (?, ?, ?, 1, ?)",
        ("Blauw Geel'15 2", vandaag, "Blauw Geel'15 2-Haren 1", "12:00"),
    )
    db.commit()

    resp = client.get("/kiosk/prijzen")
    assert _wedstrijden_json(resp.data.decode()) == [
        {"tijd": "12:00", "tegenstander": "Haren 1"},
        {"tijd": "16:00", "tegenstander": "VEV'67 1"},
    ]


def test_wedstrijddag_welkom_verschijnt_niet_zonder_thuiswedstrijd(client, db):
    resp = client.get("/kiosk/prijzen")
    assert _wedstrijden_json(resp.data.decode()) == []


def test_wedstrijddag_welkom_uitgezet_toont_niets(client, db):
    vandaag = vandaag_amsterdam().isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES (?, ?, ?, 1)",
        ("Blauw Geel'15 2", vandaag, "Blauw Geel'15 2-Haren 1"),
    )
    db.execute("UPDATE kiosk_prijzen_instellingen SET wedstrijddag_welkom_actief = 0 WHERE id = 1")
    db.commit()

    resp = client.get("/kiosk/prijzen")
    assert _wedstrijden_json(resp.data.decode()) == []


def test_wedstrijddag_welkom_instellingen_opslaan(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/prijzen/wedstrijddag-welkom",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "wedstrijddag_welkom_tekst": "Hup {tegenstander}, welkom!",
        },
    )
    assert resp.status_code == 302

    rij = db.execute(
        "SELECT wedstrijddag_welkom_actief, wedstrijddag_welkom_tekst FROM kiosk_prijzen_instellingen WHERE id = 1"
    ).fetchone()
    assert rij["wedstrijddag_welkom_actief"] == 0
    assert rij["wedstrijddag_welkom_tekst"] == "Hup {tegenstander}, welkom!"


def test_wedstrijddag_welkom_testen_hoogt_teller_op_en_komt_in_versie_terug(ingelogde_client, db):
    """De tablet-app dwingt hiermee een testmelding af zonder een echte
    thuiswedstrijd nodig te hebben -- het scherm herkent 'm via zijn gewone
    versiepoll (zie kiosk_prijzen_versie en de JS in
    kiosk_prijzen_scherm.html)."""
    voor = db.execute("SELECT wedstrijddag_test_teller FROM kiosk_prijzen_instellingen WHERE id = 1").fetchone()[
        "wedstrijddag_test_teller"
    ]

    resp = ingelogde_client.post(
        "/kiosk/prijzen/wedstrijddag-welkom/test",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.get_json() == {"ok": True}

    na = db.execute("SELECT wedstrijddag_test_teller FROM kiosk_prijzen_instellingen WHERE id = 1").fetchone()[
        "wedstrijddag_test_teller"
    ]
    assert na == voor + 1

    versie = ingelogde_client.get("/kiosk/prijzen/versie").get_json()
    assert versie["wedstrijddag_test"] == na


def test_subnav_markeert_actieve_pagina(ingelogde_client):
    resp = ingelogde_client.get("/kiosk/prijzen/acties")
    tekst = resp.data.decode()
    assert 'class="tab-knop actief">Acties</a>' in tekst
    assert 'class="tab-knop actief">Producten</a>' not in tekst


def test_diaspagina_bevat_tabbladen(ingelogde_client):
    resp = ingelogde_client.get("/kiosk/sponsoren-leden")
    tekst = resp.data.decode()
    assert 'data-tab-doel="diashow"' in tekst
    assert 'data-tab-doel="dias-tabel"' in tekst
    assert 'data-tab-doel="sjablonen"' in tekst
    assert 'data-tab-doel="club-van-20"' in tekst
