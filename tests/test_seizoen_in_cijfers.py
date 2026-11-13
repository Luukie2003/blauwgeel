"""Seizoen in cijfers (seizoen_in_cijfers.py): het seizoen tot nu toe in getallen, op een pagina bij Rapporten en als
twee dia's op de Kantine-tv. De verkoop aan de bar komt uit voorspelling.verdeling(); die wordt hier vervangen door
vaste getallen, zodat de tests over het optellen gaan en niet over het verdelen."""

import re
from datetime import date, datetime, timedelta

import pytest

from conftest import stel_csrf_token_in
from test_secties_rechten import _login, _maak_vrijwilliger

import seizoen_in_cijfers
from club_van_20 import seizoen_van_datum
from seizoensrapport import seizoen_start

NU = datetime(2026, 11, 10, 12, 0)


def _product(db, naam, eenheid="stuks", glazen_per_fust=0):
    return db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, glazen_per_fust) VALUES (?, 'Test', ?, ?)",
        (naam, eenheid, glazen_per_fust),
    ).lastrowid


@pytest.fixture
def seizoen(db, monkeypatch):
    """Een seizoen met bar, keuken, wedstrijden, tellingen en frituurvet; per item ook iets dat níet mag meetellen."""
    pils = _product(db, "Fust Pils", "fust", glazen_per_fust=80)
    cola = _product(db, "Cola", "flesjes")
    kroket = _product(db, "Kroket")
    frikandel = _product(db, "Frikandel")
    verdeling = {
        "omzet": {date(2026, 10, 3): 900.0, date(2026, 10, 8): 300.0, date(2026, 6, 20): 5000.0},
        "producten": {
            date(2026, 10, 3): {pils: [2.0, 800.0], cola: [120.0, 300.0]},
            date(2026, 10, 8): {pils: [0.5, 200.0], cola: [30.0, 75.0]},
            date(2026, 6, 20): {cola: [999.0, 2000.0]},  # vorig seizoen
        },
        "eerste": datetime(2026, 6, 1), "laatste": datetime(2026, 11, 9),
    }
    monkeypatch.setattr(seizoen_in_cijfers, "verdeling", lambda db, nu=None: verdeling)

    for omschrijving, datum, thuis, afgelast in [
        ("Blauw-Geel 1 - VV Test", "2026-10-03", 1, 0),
        ("Blauw-Geel 2 - SC Proef", "2026-09-12", 1, 0),
        ("Blauw-Geel 3 - Afgelast", "2026-10-17", 1, 1),
        ("Uit - Blauw-Geel 1", "2026-10-24", 0, 0),
        ("Blauw-Geel 1 - Straks", "2026-12-01", 1, 0),  # nog niet gespeeld
    ]:
        db.execute(
            """INSERT INTO wedstrijden (team, datum, tijd, omschrijving, thuis, afgelast)
               VALUES ('Team', ?, '14:30', ?, ?, ?)""",  # de datum zonder tijd, zoals agenda.py hem opslaat
            (datum, omschrijving, thuis, afgelast),
        )
    for datum, naam in [("2026-09-02 20:00", "Piet"), ("2026-10-07 21:00", "Anna"), ("2026-06-28 20:00", "Oud")]:
        db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, ?)", (datum, naam))
    telling = db.execute("INSERT INTO keuken_tellingen (datum, naam) VALUES ('2026-10-05 20:00', 'Piet')").lastrowid
    begin = db.execute(
        "INSERT INTO keuken_tellingen (datum, naam, begintelling) VALUES ('2026-07-02 18:00', NULL, 1)"
    ).lastrowid
    for t, pid, verkocht in [(telling, kroket, 40), (telling, frikandel, 25), (begin, kroket, 999)]:
        db.execute(
            """INSERT INTO keuken_telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht)
               VALUES (?, ?, 0, 0, ?)""",
            (t, pid, verkocht),
        )
    for datum in ("2026-08-30 10:00", "2026-10-20 10:00", "2026-05-01 10:00"):
        db.execute("INSERT INTO frituurvet_vervangingen (datum, naam) VALUES (?, 'Piet')", (datum,))
    db.commit()


def _tegels(cijfers):
    return {c["label"]: (c["getal"], c["sub"]) for c in cijfers["cijfers"]}


# ---------- Rekenen ----------


def test_de_getallen_van_het_seizoen(db, seizoen):
    cijfers = seizoen_in_cijfers.bereken(db, NU)
    assert (cijfers["seizoen"], cijfers["kort"], cijfers["van"]) == ("2026-2027", "26/27", "2026-07-01")
    assert _tegels(cijfers) == {
        "keer iets aan de bar": (350, "glazen, flesjes en snacks samen"),
        "glazen getapt": (200, "uit 2 fusten"),
        "kroketten": (40, "uit de keuken"),
        "thuiswedstrijden": (2, None),
        "tellingen": (4, "door 2 vrijwilligers"),
        "keer vers frituurvet": (2, None),
    }


def test_de_toppers_tellen_een_fust_in_glazen(db, seizoen):
    cijfers = seizoen_in_cijfers.bereken(db, NU)
    assert [(p["naam"], p["aantal"], p["eenheid"]) for p in cijfers["top_bar"]] == [
        ("Pils", 200, "glazen"), ("Cola", 150, "flesjes")]
    assert [(p["naam"], p["tekst"]) for p in cijfers["top_keuken"]] == [("Kroket", "40"), ("Frikandel", "25")]


def test_de_drukste_dag_met_de_thuiswedstrijd(db, seizoen):
    drukste = seizoen_in_cijfers.bereken(db, NU)["drukste_dag"]
    assert drukste == {"datum": "2026-10-03", "tekst": "zaterdag 3 oktober", "wedstrijden": ["Blauw-Geel 1 - VV Test"]}


def test_zonder_kroketten_telt_de_hele_keuken(db, seizoen):
    db.execute("UPDATE producten SET naam = 'Bitterbal' WHERE naam = 'Kroket'")
    db.commit()
    assert _tegels(seizoen_in_cijfers.bereken(db, NU))["keer iets uit de keuken"] == (65, "het meest: Bitterbal")


def test_grote_getallen_met_een_punt(db, seizoen, monkeypatch):
    groot = {"omzet": {date(2026, 10, 3): 1.0}, "producten": {date(2026, 10, 3): {}}, "eerste": NU, "laatste": NU}
    cola = db.execute("SELECT id FROM producten WHERE naam = 'Cola'").fetchone()[0]
    groot["producten"][date(2026, 10, 3)][cola] = [12345.0, 1.0]
    monkeypatch.setattr(seizoen_in_cijfers, "verdeling", lambda db, nu=None: groot)
    assert seizoen_in_cijfers.bereken(db, NU)["top_bar"][0]["tekst"] == "12.345"


def test_zonder_gegevens_niets(db):
    assert seizoen_in_cijfers.bereken(db, NU) is None


# ---------- Bewaren: alleen opnieuw rekenen als er iets veranderd is ----------


def test_ververs_rekent_alleen_na_een_telling_of_op_een_nieuwe_dag(db, seizoen, monkeypatch):
    echt, keer = seizoen_in_cijfers.bereken, []
    monkeypatch.setattr(seizoen_in_cijfers, "bereken", lambda db, nu=None: keer.append(nu) or echt(db, nu))

    assert seizoen_in_cijfers.ververs(db, NU)["kort"] == "26/27"
    seizoen_in_cijfers.ververs(db, NU + timedelta(hours=2))
    assert len(keer) == 1  # niets veranderd: wat er bewaard is

    db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-11-10 13:00', 'Piet')")
    db.commit()
    seizoen_in_cijfers.ververs(db, NU + timedelta(hours=2))
    assert len(keer) == 2  # een nieuwe telling

    seizoen_in_cijfers.ververs(db, NU + timedelta(days=1))
    assert len(keer) == 3  # een nieuwe dag


def test_lees_rekent_nooit(db, seizoen, monkeypatch):
    assert seizoen_in_cijfers.lees(db, NU) is None
    seizoen_in_cijfers.ververs(db, NU)

    def mag_niet(*args, **kwargs):
        raise AssertionError("lees() mag niet rekenen: de tv vraagt elke minuut om de dia's")

    monkeypatch.setattr(seizoen_in_cijfers, "bereken", mag_niet)
    bewaard = seizoen_in_cijfers.lees(db, NU)
    assert bewaard["berekend_op"] == "2026-11-10 12:00" and bewaard["top_bar"][0]["naam"] == "Pils"


# ---------- De pagina en de tv (met getallen uit het seizoen van vandaag) ----------


@pytest.fixture
def vandaag_iets_verkocht(db, monkeypatch):
    vandaag = datetime.now().date()
    dag = max(seizoen_start(seizoen_van_datum(vandaag)), vandaag - timedelta(days=1))
    pils = _product(db, "Fust Pils", "fust", glazen_per_fust=80)
    db.commit()
    verdeling = {"omzet": {dag: 500.0}, "producten": {dag: {pils: [3.0, 500.0]}}, "eerste": NU, "laatste": NU}
    monkeypatch.setattr(seizoen_in_cijfers, "verdeling", lambda db, nu=None: verdeling)


def test_de_pagina(ingelogde_client, vandaag_iets_verkocht):
    tekst = ingelogde_client.get("/rapporten/seizoen-in-cijfers").data.decode()
    assert "240" in tekst and "glazen getapt" in tekst and "De toppers van de bar" in tekst and "Pils" in tekst
    assert "€" not in tekst.split("<main>")[-1]  # geen bedragen


def test_ook_een_vrijwilliger_ziet_de_pagina(client, db, vandaag_iets_verkocht):
    _maak_vrijwilliger(db, "vrijwilliger1", "voorraad")
    _login(client, "vrijwilliger1")
    assert client.get("/rapporten/seizoen-in-cijfers").status_code == 200


def test_zonder_tellingen_zegt_de_pagina_dat(ingelogde_client):
    assert "nog niets geteld" in ingelogde_client.get("/rapporten/seizoen-in-cijfers").data.decode()


def _zet(db, **velden):
    db.execute(
        f"UPDATE kiosk_scherm_instellingen SET {', '.join(f'{k} = ?' for k in velden)} WHERE id = 1",
        tuple(velden.values()),
    )
    db.commit()


def test_de_tv_toont_twee_dias_als_het_onderdeel_aan_staat(client, db, vandaag_iets_verkocht):
    seizoen_in_cijfers.ververs(db)
    assert "in cijfers" not in client.get("/kiosk/scherm").data.decode()  # staat standaard uit

    _zet(db, toon_seizoen=1, seizoen_duur_seconden=12)
    tekst = client.get("/kiosk/scherm").data.decode()
    assert "slide-seizoen_cijfers" in tekst and "slide-seizoen_top" in tekst
    assert "240" in tekst and "glazen getapt" in tekst and "Pils" in tekst
    assert re.search(r'slide-seizoen_cijfers[^>]*data-duur="12"', tekst, re.S)


def test_de_tv_rekent_zelf_niet(client, db, monkeypatch):
    _zet(db, toon_seizoen=1)

    def mag_niet(*args, **kwargs):
        raise AssertionError("de tv mag niet rekenen")

    monkeypatch.setattr(seizoen_in_cijfers, "bereken", mag_niet)
    resp = client.get("/kiosk/scherm")
    assert resp.status_code == 200 and "slide-seizoen_cijfers" not in resp.data.decode()  # nog niets bewaard


def test_s_avonds_alleen_als_dat_aan_staat(client, db, vandaag_iets_verkocht):
    seizoen_in_cijfers.ververs(db)
    _zet(db, toon_seizoen=1, avond_vanaf="16:00", avond_seizoen=0)
    tekst = client.get("/kiosk/scherm").data.decode()
    assert re.search(r'slide-seizoen_cijfers[^>]*data-tot=', tekst, re.S)  # alleen overdag
    _zet(db, avond_seizoen=1)
    assert not re.search(r'slide-seizoen_cijfers[^>]*data-tot=', client.get("/kiosk/scherm").data.decode(), re.S)


def test_aanzetten_bij_de_diashow(ingelogde_client, db):
    assert "Seizoen in cijfers" in ingelogde_client.get("/kiosk/diashow").data.decode()
    ingelogde_client.post("/kiosk/scherm/instellingen", data={
        "csrf_token": stel_csrf_token_in(ingelogde_client), "toon_seizoen": "on",
        "seizoen_volgorde": "2", "seizoen_duur_seconden": "20"})
    rij = db.execute("SELECT toon_seizoen, seizoen_volgorde, seizoen_duur_seconden FROM kiosk_scherm_instellingen").fetchone()
    assert tuple(rij) == (1, 2, 20)


def test_het_voorverwarmen_werkt_de_cijfers_bij(ingelogde_client, db, vandaag_iets_verkocht):
    assert ingelogde_client.get("/voorspelling/opwarmen").status_code == 204
    assert seizoen_in_cijfers.lees(db)["top_bar"][0]["naam"] == "Pils"


def test_zelf_kiezen_wat_er_op_de_tv_staat(ingelogde_client, client, db, vandaag_iets_verkocht):
    seizoen_in_cijfers.ververs(db)
    _zet(db, toon_seizoen=1)
    assert "glazen getapt" in client.get("/kiosk/scherm").data.decode()
    pagina = ingelogde_client.get("/kiosk/diashow").data.decode()
    assert 'name="seizoen_tonen" value="getapt" checked' in pagina

    # Alles behalve de getapte glazen en de toppers aan: die twee staan niet meer op de tv.
    getoond = [s for s, _ in seizoen_in_cijfers.ONDERDELEN if s not in ("getapt", "toppers")]
    ingelogde_client.post("/kiosk/scherm/instellingen", data={
        "csrf_token": stel_csrf_token_in(ingelogde_client), "toon_seizoen": "on", "seizoen_tonen": getoond})
    assert db.execute("SELECT seizoen_verborgen FROM kiosk_scherm_instellingen").fetchone()[0] == "getapt,toppers"
    tekst = client.get("/kiosk/scherm").data.decode()
    assert "slide-seizoen_cijfers" in tekst and "glazen getapt" not in tekst and "slide-seizoen_top" not in tekst
    assert 'name="seizoen_tonen" value="getapt" >' in ingelogde_client.get("/kiosk/diashow").data.decode()


def test_een_oude_bewaarde_uitkomst_zonder_sleutels():
    oud = {"kort": "26/27", "drukste_dag": {"tekst": "zaterdag"}, "top_bar": [], "top_keuken": [],
           "cijfers": [{"getal": 5, "tekst": "5", "label": "kroketten", "sub": None},
                       {"getal": 3, "tekst": "3", "label": "thuiswedstrijden", "sub": None}]}
    dia = seizoen_in_cijfers.tv_slides(oud, 10, {"keuken", "drukste"})[0]
    assert [c["label"] for c in dia["cijfers"]] == ["thuiswedstrijden"] and dia["drukste_dag"] is None
    assert seizoen_in_cijfers.verborgen_uit("drukste, onzin ,stemmen") == {"drukste", "stemmen"}
    assert seizoen_in_cijfers.verborgen_tekst([s for s, _ in seizoen_in_cijfers.ONDERDELEN]) is None
