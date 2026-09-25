import json
import re
import sqlite3
from datetime import date, timedelta

import database
from conftest import stel_csrf_token_in as _csrf
from helpers import bepaal_tegenstander, vandaag_amsterdam
from test_kiosk import _voeg_product_toe


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


def test_prijzenscherm_toont_trainingsavond_selectie_als_modus_handmatig_aan_staat(client, db):
    db.execute("UPDATE kiosk_prijzen_instellingen SET trainingsavond_modus_actief = 1 WHERE id = 1")
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


def test_prijzenscherm_toont_normale_selectie_als_modus_uit_staat_ongeacht_kalenderdag(client, db):
    """Kern van de wijziging: geen automatische koppeling meer aan de
    kalenderdag -- ook al zou vandaag toevallig de vaste trainingsavond
    (woensdag) zijn, zonder de handmatige schakelaar blijft de normale
    selectie gelden."""
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

    assert "Alleen normaal" in tekst
    assert "Alleen trainingsavond" not in tekst


def test_trainingsavond_modus_wisselen_zet_aan_en_weer_uit(ingelogde_client, db):
    voor = db.execute(
        "SELECT trainingsavond_modus_actief FROM kiosk_prijzen_instellingen WHERE id = 1"
    ).fetchone()["trainingsavond_modus_actief"]
    assert voor == 0

    resp = ingelogde_client.post(
        "/kiosk/prijzen/trainingsavond-modus",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.get_json() == {"ok": True, "trainingsavond_modus_actief": 1}
    aan = db.execute(
        "SELECT trainingsavond_modus_actief FROM kiosk_prijzen_instellingen WHERE id = 1"
    ).fetchone()["trainingsavond_modus_actief"]
    assert aan == 1

    resp = ingelogde_client.post(
        "/kiosk/prijzen/trainingsavond-modus",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.get_json() == {"ok": True, "trainingsavond_modus_actief": 0}
    uit = db.execute(
        "SELECT trainingsavond_modus_actief FROM kiosk_prijzen_instellingen WHERE id = 1"
    ).fetchone()["trainingsavond_modus_actief"]
    assert uit == 0


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


def test_versie_geeft_eerstvolgende_bekende_tegenstander_voor_de_testknop(client, db):
    """Los van 'wedstrijddag_welkom_actief' en los van of het vandaag is --
    de testknop moet ook werken zonder geplande thuiswedstrijd vandaag (zie
    _eerstvolgende_bekende_tegenstander in routes/kiosk.py)."""
    over_een_week = date.fromisoformat(vandaag_amsterdam().isoformat())
    later = (over_een_week + timedelta(days=7)).isoformat()
    db.execute("UPDATE kiosk_prijzen_instellingen SET wedstrijddag_welkom_actief = 0 WHERE id = 1")
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, tijd) VALUES (?, ?, ?, 1, ?)",
        ("Blauw Geel'15 1", later, "Blauw Geel'15 1-VEV'67 1", "14:00"),
    )
    db.commit()

    versie = client.get("/kiosk/prijzen/versie").get_json()
    assert versie["wedstrijddag_test_tegenstander"] == "VEV'67 1"


def test_versie_negeert_verleden_wedstrijden_voor_eerstvolgende_tegenstander(client, db):
    gisteren = (date.fromisoformat(vandaag_amsterdam().isoformat()) - timedelta(days=1)).isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES (?, ?, ?, 1)",
        ("Blauw Geel'15 1", gisteren, "Blauw Geel'15 1-Verleden 1"),
    )
    db.commit()

    versie = client.get("/kiosk/prijzen/versie").get_json()
    assert versie["wedstrijddag_test_tegenstander"] is None


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
