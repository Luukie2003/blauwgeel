"""Rapport Inkoop en verkoop: wat er is ingekocht tegen wat er verkocht is, wat blijft liggen en of leveringen klopten."""

from datetime import date

import pytest
from test_producten_prijzen import _product
from test_secties_rechten import _login, _maak_vrijwilliger

from inkoop_verkoop import STANDAARD_WEKEN, WEKEN_KEUZES, bereken_inkoop_verkoop, is_correctie, is_retour, kies_weken

VANDAAG = date(2026, 3, 31)  # 13 weken terug is 30 december 2025


def _telling(db, datum, regels):
    """regels: {product_id: (voorraad_voor, geteld, verkoopprijs)}; verkocht en correctie volgen daaruit."""
    tid = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'T')", (datum,)).lastrowid
    for pid, (voor, geteld, prijs) in regels.items():
        db.execute(
            """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, pid, voor, geteld, max(0, voor - geteld), max(0, geteld - voor), prijs),
        )
    db.commit()
    return tid


def _mutatie(db, pid, soort, aantal, datum, opmerking="", bestelling_id=None):
    db.execute(
        "INSERT INTO mutaties (product_id, type, aantal, datum, naam, opmerking, bestelling_id) VALUES (?, ?, ?, ?, 'admin', ?, ?)",
        (pid, soort, aantal, datum, opmerking, bestelling_id),
    )
    db.commit()


def _bestelling(db, regels, status="ontvangen", datum="2026-02-23 20:00", ontvangen="2026-02-25 15:00"):
    """regels: {product_id: (besteld, ontvangen)}."""
    bid = db.execute(
        "INSERT INTO bestellingen (status, aangemaakt_op, ontvangen_op) VALUES (?, ?, ?)",
        (status, datum, ontvangen if status == "ontvangen" else None),
    ).lastrowid
    for pid, (besteld, ontv) in regels.items():
        db.execute(
            "INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld, aantal_ontvangen) VALUES (?, ?, ?, ?)",
            (bid, pid, besteld, ontv if status == "ontvangen" else None),
        )
    db.commit()
    return bid


def _regel(rapport, naam):
    return next(p for p in rapport["producten"] if p["naam"] == naam)


@pytest.fixture
def pils(db):
    """Een krat van 24 voor € 24,00: € 1,00 per fles, verkocht voor € 2,00.

    20 feb nulmeting 10, 25 feb 48 binnen uit een bestelling, 26 feb een correctie van +5 (geen inkoop), 10 mrt een
    telling (verkocht 20), 15 mrt 12 retour, 28 mrt een telling met 2 meer dan verwacht. Er staan er nu 33."""
    pid = _product(db, "Pils", verkoop=2.0, inkoop=24.0, besteleenheid="Krat", besteleenheid_factor=24)
    _telling(db, "2026-02-20 12:00", {pid: (0, 10, 2.0)})
    bid = _bestelling(db, {pid: (48, 48)})
    _mutatie(db, pid, "in", 48, "2026-02-25 15:00", "Ontvangen uit bestelling", bestelling_id=bid)
    _mutatie(db, pid, "in", 5, "2026-02-26 10:00", "Correctie koelkast")
    _telling(db, "2026-03-10 12:00", {pid: (63, 43, 2.0)})
    _mutatie(db, pid, "uit", 12, "2026-03-15 10:00", "RETOUR")
    _telling(db, "2026-03-28 12:00", {pid: (31, 33, 2.0)})
    db.execute("UPDATE producten SET voorraad = 33 WHERE id = ?", (pid,))
    db.commit()
    return pid


def test_weken_kiezen_valt_terug_op_de_standaard():
    assert kies_weken("4") == 4 and kies_weken(52) == 52
    for onzin in (None, "", "abc", "7", "-4"):
        assert kies_weken(onzin) == STANDAARD_WEKEN
    assert STANDAARD_WEKEN in WEKEN_KEUZES


def test_correctie_en_retour_herkennen_aan_de_opmerking():
    assert is_correctie("Correctie koelkast") and is_correctie("Telling gecorrigeerd") and not is_correctie("Gekocht Poiesz")
    assert not is_correctie(None)
    assert is_retour("RETOUR") and is_retour("retour naar Robertus") and not is_retour("Levering aan buren")


def test_inkoop_is_zonder_correcties_en_min_de_retour(db, pils):
    p = _regel(bereken_inkoop_verkoop(db, 13, VANDAAG), "Pils")
    assert p["inkoop"] == 48 - 12  # de correctie van +5 is geen inkoop
    assert p["correctie"] == 5
    assert p["inkoop_waarde"] == pytest.approx(36.0)  # per fles € 1,00, niet € 24,00


def test_verkoop_omzet_en_marge_komen_uit_de_tellingen(db, pils):
    rapport = bereken_inkoop_verkoop(db, 13, VANDAAG)
    p = _regel(rapport, "Pils")
    assert p["verkocht"] == 20 and p["omzet"] == pytest.approx(40)
    assert p["kostprijs"] == pytest.approx(20) and p["winst"] == pytest.approx(20) and p["marge_pct"] == pytest.approx(50)
    assert rapport["totaal"]["omzet"] >= 40


def test_meer_geteld_dan_verwacht_telt_niet_bij_de_eerste_telling(db, pils):
    p = _regel(bereken_inkoop_verkoop(db, 13, VANDAAG), "Pils")
    assert p["telverschil"] == 2  # de nulmeting (0 -> 10) telt niet mee
    assert p["telverschil_waarde"] == pytest.approx(4.0)


def test_per_maand_inkoop_verkocht_en_omzet(db, pils):
    maanden = {m["maand"]: m for m in bereken_inkoop_verkoop(db, 13, VANDAAG)["per_maand"]}
    assert maanden["2026-02"]["inkoop"] == pytest.approx(48) and maanden["2026-02"]["verkocht"] == pytest.approx(0)
    assert maanden["2026-03"]["inkoop"] == pytest.approx(-12)  # de retour
    assert maanden["2026-03"]["verkocht"] == pytest.approx(20) and maanden["2026-03"]["omzet"] == pytest.approx(40)
    assert maanden["2026-03"]["label"] == "mrt 2026"


def test_weken_voorraad_en_wat_blijft_liggen(db, pils):
    rapport = bereken_inkoop_verkoop(db, 13, VANDAAG)
    weken = 36 / 7  # van de eerste telling (20 feb) tot de laatste (28 mrt)
    assert rapport["verkoopweken"] == pytest.approx(weken)
    p = _regel(rapport, "Pils")
    assert p["per_week"] == pytest.approx(20 / weken)
    assert p["weken_voorraad"] == pytest.approx(33 / (20 / weken))  # ruim 8 weken
    assert "Pils" in [r["naam"] for r in rapport["lang_liggen"]]


def test_de_verkoop_per_week_rekent_vanaf_de_telling_voor_de_periode(db, pils):
    # 4 weken terug is 3 maart: de telling van 10 maart telt de verkoop sinds 20 februari
    rapport = bereken_inkoop_verkoop(db, 4, VANDAAG)
    assert rapport["verkoopweken"] == pytest.approx(36 / 7)
    assert _regel(rapport, "Pils")["inkoop"] == -12  # alleen de retour valt in deze 4 weken


def test_een_openstaande_bestelling_telt_als_onderweg(db, pils):
    _bestelling(db, {pils: (24, None)}, status="besteld", datum="2026-03-30 20:00")
    rapport = bereken_inkoop_verkoop(db, 13, VANDAAG)
    p = _regel(rapport, "Pils")
    assert p["onderweg"] == 24 and p["inkoop"] == 36  # nog niet binnen, dus geen inkoop
    assert p["weken_na_levering"] == pytest.approx((33 + 24) / p["per_week"])
    assert "Pils" in [r["naam"] for r in rapport["na_levering"]]


def test_besteld_tegen_geleverd(db, pils):
    cola = _product(db, "Cola", categorie="Fris", verkoop=2.0, inkoop=12.0, besteleenheid_factor=24)
    bid = _bestelling(db, {pils: (24, 36), cola: (24, 0)}, datum="2026-03-01 20:00", ontvangen="2026-03-03 15:00")
    lev = bereken_inkoop_verkoop(db, 13, VANDAAG)["leveringen"]
    b = next(x for x in lev["bestellingen"] if x["id"] == bid)
    assert b["regels"] == 2 and b["regels_goed"] == 0
    assert {a["naam"]: a["verschil"] for a in b["afwijkend"]} == {"Pils": 12, "Cola": -24}
    assert b["besteld"] == pytest.approx(24 * 1.0 + 24 * 0.5) and b["geleverd"] == pytest.approx(36 * 1.0)
    assert lev["regels"] == 3 and lev["regels_goed"] == 1  # met de bestelling uit de fixture, die klopte


def test_keuken_en_niet_tellen_doen_niet_mee(db):
    kroket = _product(db, "Kroket", categorie="Keuken", verkoop=1.75, inkoop=0.35)
    knop = _product(db, "Kassaknop", categorie="Kassa knop", verkoop=1.5, inkoop=1.0, niet_tellen=1)
    _mutatie(db, kroket, "in", 24, "2026-03-20 10:00", "Factuur ingeboekt")
    _mutatie(db, knop, "in", 10, "2026-03-20 10:00")
    namen = [p["naam"] for p in bereken_inkoop_verkoop(db, 13, VANDAAG)["producten"]]
    assert "Kroket" not in namen and "Kassaknop" not in namen


def test_zonder_tellingen_geeft_het_rapport_nullen(db):
    rapport = bereken_inkoop_verkoop(db, 13, VANDAAG)
    assert rapport["verkoopweken"] is None and rapport["totaal"]["omzet"] == 0
    assert rapport["totaal"]["omzet_per_euro"] is None and rapport["totaal"]["marge_pct"] is None
    assert rapport["leveringen"]["bestellingen"] == []


def test_de_pagina_alleen_voor_beheerders(ingelogde_client, client, db, pils):
    html = ingelogde_client.get("/rapporten/inkoop-verkoop?weken=52").data.decode()
    assert "Inkoop en verkoop" in html and "Besteld tegen geleverd" in html and "Voorraad die blijft liggen" in html
    _maak_vrijwilliger(db, "vrijwilliger", "voorraad")
    ander = client.application.test_client()
    _login(ander, "vrijwilliger")
    assert "alleen voor beheerders" in ander.get("/rapporten/inkoop-verkoop", follow_redirects=True).data.decode()


def test_de_pagina_werkt_zonder_gegevens(ingelogde_client):
    resp = ingelogde_client.get("/rapporten/inkoop-verkoop")
    assert resp.status_code == 200 and "Inkoop en verkoop" in resp.data.decode()
