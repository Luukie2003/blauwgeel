"""Merkanalyse (2.19.0): alles over één merk voor een gesprek met de vertegenwoordiger."""

from datetime import date, timedelta

import pytest
from pdf_tekst import pdf_tekst
from test_bestelvoorstel import _product

import merkanalyse

VANDAAG = date(2026, 11, 25)


def _merk(db, naam, voorraad, categorie="Mix", merk=None, inkoop=12.0, gearchiveerd=0):
    pid = _product(db, naam, voorraad=voorraad, minimum=0, factor=12, besteleenheid="Doos")
    db.execute("UPDATE producten SET categorie = ?, merk = ?, inkoopprijs = ?, verkoopprijs = 3.5, gearchiveerd = ?, actief = ? WHERE id = ?",
               (categorie, merk, inkoop, gearchiveerd, 0 if gearchiveerd else 1, pid))
    db.commit()
    return pid


def _telling(db, weken_geleden, regels):
    """regels: {product_id: (geteld, verkocht, correctie)}"""
    datum = (VANDAAG - timedelta(weeks=weken_geleden)).strftime("%Y-%m-%d 10:00")
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (datum,)).lastrowid
    for pid, (geteld, verkocht, correctie) in regels.items():
        db.execute("""INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
                      VALUES (?, ?, ?, ?, ?, ?, 3.5)""", (t, pid, geteld + verkocht - correctie, geteld, verkocht, correctie))
    db.commit()


def _in(db, pid, aantal, weken_geleden, bestelling_id=None, opmerking=None):
    db.execute("INSERT INTO mutaties (product_id, type, aantal, datum, bestelling_id, opmerking) VALUES (?, 'in', ?, ?, ?, ?)",
               (pid, aantal, (VANDAAG - timedelta(weeks=weken_geleden)).strftime("%Y-%m-%d 12:00"), bestelling_id, opmerking))
    db.commit()


@pytest.fixture
def bozu(db):
    """Sparkling loopt (en steeds beter), Green niet, Icetea is uit het assortiment; Cola is een ander merk."""
    s, g = _merk(db, "Bozu Sparkling", 40), _merk(db, "Bozu Green", 100)
    i, c = _merk(db, "Bozu Icetea", 0, gearchiveerd=1), _merk(db, "Cola Mix", 20)
    _telling(db, 12, {s: (20, 0, 20), g: (30, 0, 30), i: (10, 0, 10), c: (30, 0, 30)})  # de eerste keer: alles is nieuw
    _in(db, s, 120, 9)
    _telling(db, 8, {s: (100, 40, 0), g: (28, 2, 0), i: (0, 10, 0), c: (25, 5, 0)})
    _in(db, s, 72, 5)
    _telling(db, 4, {s: (72, 100, 0), g: (36, 0, 8), c: (20, 5, 0)})  # Green: 8 meer dan kan, een telfout
    _telling(db, 1, {s: (12, 60, 0), g: (20, 16, 0), c: (20, 0, 0)})
    return s, g, i, c


def test_merken_uit_naam_en_merkveld(db, bozu):
    _merk(db, "Zoet", 1, merk="Haribo")
    namen = merkanalyse.merken(db)
    assert "Bozu" in namen and "Haribo" in namen
    assert "Cola" not in namen or sum(1 for n in namen if n == "Cola") == 1  # een los product is geen merk om te kiezen
    assert merkanalyse.merk_van({"naam": "Fust Hertog Jan", "merk": None}) == "Hertog"


def test_cijfers_netto_zonder_telfouten(db, bozu):
    s, g, i, _c = bozu
    a = merkanalyse.analyse(db, "bozu", 13, VANDAAG)
    assert a["merk"] == "Bozu"
    per = {p["id"]: p for p in a["producten"]}
    assert set(per) == {s, g, i}
    assert per[s]["verkocht"] == 200 and per[g]["verkocht"] == 10  # 18 min de telfout van 8
    assert per[g]["kort"] == "Green" and per[i]["gearchiveerd"]
    t = a["totaal"]
    assert t["verkocht"] == 220 and t["omzet"] == pytest.approx(770) and t["telverschil"] == 8
    assert t["marge_pct"] == pytest.approx((3.5 - 1) / 3.5 * 100)
    assert t["plek"] == 1 and 90 < t["aandeel_categorie"] < 100
    assert sum(m["totaal"] for m in a["per_maand"]) == 220
    assert [r["naam"] for r in a["andere"]] == ["Cola Mix"]
    assert per[s]["na"] > per[s]["voor"] > 0


def test_volume_en_scenario(db, bozu):
    a = merkanalyse.analyse(db, "Bozu", 13, VANDAAG, seizoen_weken=20)
    v = a["volume"]
    assert v["doos"] == 12 and v["doosprijs"] == pytest.approx(12.0)
    assert v["dozen"] == pytest.approx(220 / 12 / a["verkoopweken"] * 20)
    per = {x["wat"]: x["scheelt"] for x in v["scenario"]}
    assert per["€ 1,00 per doos korting"] == pytest.approx(v["dozen"])
    assert per["1 doos gratis op 10 gekochte dozen"] == pytest.approx(v["dozen"] / 11 * 12)


def test_leveringen_en_wat_later_nakwam(db, bozu):
    s, g, _i, _c = bozu
    for pid, weken in ((s, 5), (g, 4)):
        b = db.execute("INSERT INTO bestellingen (status, aangemaakt_op, ontvangen_op) VALUES ('ontvangen', ?, ?)",
                       ((VANDAAG - timedelta(weeks=weken + 1)).isoformat(), (VANDAAG - timedelta(weeks=weken)).strftime("%Y-%m-%d 09:00"))).lastrowid
        db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld, aantal_ontvangen) VALUES (?, ?, 72, 0)", (b, pid))
    db.commit()
    a = merkanalyse.analyse(db, "Bozu", 13, VANDAAG)
    per = {f["naam"]: f for f in a["afwijkend"]}
    assert per["Sparkling"]["nagekomen"]["aantal"] == 72  # de losse boeking van dezelfde dag
    assert per["Green"]["nagekomen"] is None
    tekst = next(p["tekst"] for p in a["punten"] if p["titel"] == "Leveringen weken af")
    assert "Te weinig: Green 0 van 72" in tekst and "Later alsnog los binnengekomen: Sparkling 72" in tekst


def test_gesprekspunten(db, bozu):
    titels = [p["titel"] for p in merkanalyse.analyse(db, "Bozu", 13, VANDAAG)["punten"]]
    assert "Green loopt traag: ruilen of een actie" in titels
    assert "Sparkling groeit" in titels and "Green groeit" not in titels  # wat traag loopt, 'groeit' niet
    assert "Niet meer in het assortiment" in titels and "De marge naast de rest" in titels


def test_pagina_en_pdf(ingelogde_client, db, bozu):
    assert "Kies een merk" in ingelogde_client.get("/rapporten/merk").data.decode()
    pagina = ingelogde_client.get("/rapporten/merk?merk=Bozu&weken=13").data.decode()
    assert "Gesprekspunten" in pagina and "Bozu Sparkling" in pagina
    assert "geen producten" in ingelogde_client.get("/rapporten/merk?merk=Bestaatniet").data.decode()
    intern = ingelogde_client.get("/rapporten/merk/pdf?merk=Bozu")
    assert intern.mimetype == "application/pdf" and "merkanalyse-bozu-intern.pdf" in intern.headers["Content-Disposition"]
    tekst = pdf_tekst(intern.data)
    assert "Brutowinst" in tekst and "Gesprekspunten" in tekst
    # Om te laten zien: geen inkoop, marge, omzet of gesprekspunten.
    deelbaar = pdf_tekst(ingelogde_client.get("/rapporten/merk/pdf?merk=Bozu&deelbaar=1").data)
    assert "Sparkling" in deelbaar
    for woord in ("Brutowinst", "Marge", "marge", "Omzet", "Ingekocht", "Gesprekspunten", "€", "Intern", "Voorraad nu", "Cola Mix", "Aandeel in"):
        assert woord not in deelbaar
    assert ingelogde_client.get("/rapporten/merk/pdf").status_code == 302


def test_zonder_tellingen_en_alleen_voor_beheerders(ingelogde_client, db):
    import rechten

    _merk(db, "Leeg Een", 1)
    _merk(db, "Leeg Twee", 1)
    assert ingelogde_client.get("/rapporten/merk?merk=Leeg").status_code == 200
    assert ingelogde_client.get("/rapporten/merk/pdf?merk=Leeg").status_code == 200
    assert {"merk_rapport", "merk_rapport_pdf"} <= rechten.BEHEERDER_ENDPOINTS
