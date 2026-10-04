import json
import re
from datetime import date, timedelta

from conftest import stel_csrf_token_in as _csrf
from helpers import bepaal_tegenstander, vandaag_amsterdam
from test_kiosk import _voeg_product_toe


def test_bepaal_tegenstander_bij_thuiswedstrijd():
    assert bepaal_tegenstander("Blauw Geel'15 2-Potetos 4") == "Potetos 4"


def test_bepaal_tegenstander_bij_uitwedstrijd_omschrijving():
    assert bepaal_tegenstander("Potetos 4-Blauw Geel'15 2") == "Potetos 4"


def test_bepaal_tegenstander_zonder_clubnaam_geeft_none():
    assert bepaal_tegenstander("Potetos 4-VEV'67 6") is None


def test_prijzenscherm_toont_de_algemene_selectie_op_elke_dag(client, db):
    """Eén algemene prijslijst: geen aparte selectie voor een trainingsavond
    of een wedstrijddag, dus altijd precies de producten met toon_op_kiosk aan."""
    _voeg_product_toe(db, "Staat op de lijst", toon_op_kiosk=1)
    _voeg_product_toe(db, "Staat er niet op", toon_op_kiosk=0)

    tekst = client.get("/kiosk/prijzen").data.decode()

    assert "Staat op de lijst" in tekst
    assert "Staat er niet op" not in tekst


def test_instellingen_hebben_geen_dagschakelaar_meer(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Speciaalbier", toon_op_kiosk=1)

    tekst = ingelogde_client.get("/kiosk/prijzen/instellingen").data.decode()

    assert f'name="toon_{product_id}" checked' in tekst
    assert "Trainingsavond" not in tekst and "trainingsavond" not in tekst
    # Een oude link of bladwijzer met ?dag=... werkt gewoon, maar toont dezelfde lijst.
    oud = ingelogde_client.get("/kiosk/prijzen/instellingen?dag=trainingsavond")
    assert oud.status_code == 200 and f'name="toon_{product_id}" checked' in oud.data.decode()
    # De wisselknop bestaat niet meer.
    weg = ingelogde_client.post(
        "/kiosk/prijzen/trainingsavond-modus", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert weg.status_code in (404, 405)


def test_selectie_opslaan_wijzigt_de_algemene_lijst(ingelogde_client, db):
    blijft = _voeg_product_toe(db, "Blijft", toon_op_kiosk=1)
    erbij = _voeg_product_toe(db, "Komt erbij", toon_op_kiosk=0)

    resp = ingelogde_client.post(
        "/kiosk/prijzen/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), f"toon_{blijft}": "on", f"toon_{erbij}": "on"},
    )

    assert resp.status_code == 302
    rijen = {r["naam"]: r["toon_op_kiosk"] for r in db.execute("SELECT naam, toon_op_kiosk FROM producten")}
    assert rijen["Blijft"] == 1 and rijen["Komt erbij"] == 1


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
