"""Rapporten: het marge-overzicht en de derving."""

from datetime import timedelta

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_producten_prijzen import _product
from test_secties_rechten import _login, _maak_vrijwilliger

from derving import DERVING_REDENEN, bereken_derving, kies_reden
from marge import LAGE_MARGE_PCT, STANDAARD_WEKEN, WEKEN_KEUZES, bereken_marge, kies_weken


def _vandaag():
    from helpers.tijd import vandaag_amsterdam

    return vandaag_amsterdam()


def _regel(rapport, naam):
    """De productregel van een product in het rapport (de testdatabase heeft ook al producten)."""
    return next(p for p in rapport["producten"] if p["naam"] == naam)


def _telling(db, dagen_geleden, regels):
    """regels: {product_id: (verkocht, verkoopprijs)}."""
    datum = (_vandaag() - timedelta(days=dagen_geleden)).strftime("%Y-%m-%d 12:00")
    tid = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'T')", (datum,)).lastrowid
    for pid, (verkocht, prijs) in regels.items():
        db.execute(
            "INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs) VALUES (?, ?, 0, 0, ?, ?)",
            (tid, pid, verkocht, prijs),
        )
    db.commit()


def _uitboeking(db, pid, aantal, reden, dagen_geleden=1, naam="admin", opmerking=""):
    datum = (_vandaag() - timedelta(days=dagen_geleden)).strftime("%Y-%m-%d 12:00")
    db.execute(
        "INSERT INTO mutaties (product_id, type, aantal, datum, naam, opmerking, reden) VALUES (?, 'uit', ?, ?, ?, ?, ?)",
        (pid, aantal, datum, naam, opmerking, reden),
    )
    db.commit()


# ---------- Marge ----------


def test_weken_kiezen_valt_terug_op_de_standaard():
    assert kies_weken("8") == 8 and kies_weken(26) == 26
    for onzin in (None, "", "abc", "7", "-4", "1000"):
        assert kies_weken(onzin) == STANDAARD_WEKEN
    assert STANDAARD_WEKEN in WEKEN_KEUZES


def test_marge_per_product_en_categorie(db):
    pils = _product(db, "Pils", categorie="Bier", verkoop=2.0, inkoop=1.2)
    cola = _product(db, "Cola", categorie="Fris", verkoop=1.5, inkoop=1.2)
    _telling(db, 5, {pils: (100, 2.0), cola: (50, 1.5)})
    rapport = bereken_marge(db, 13, _vandaag())
    p = {x["naam"]: x for x in rapport["producten"]}
    assert p["Pils"]["omzet"] == pytest.approx(200) and p["Pils"]["aantal"] == 100
    assert p["Pils"]["marge_stuk"] == pytest.approx(0.8) and p["Pils"]["marge_pct"] == pytest.approx(40)
    assert p["Pils"]["winst"] == pytest.approx(200 - 100 * 1.2)
    assert p["Cola"]["marge_pct"] == pytest.approx(20)  # onder de grens
    assert p["Cola"]["marge_pct"] < LAGE_MARGE_PCT
    cats = {c["naam"]: c for c in rapport["categorieen"]}
    assert cats["Bier"]["omzet"] == pytest.approx(200) and cats["Bier"]["marge_pct"] == pytest.approx(40)
    assert rapport["totaal"]["omzet"] == pytest.approx(275)
    assert rapport["totaal"]["winst"] == pytest.approx(80 + 15)
    assert [x["naam"] for x in rapport["laagste"]][:2] == ["Cola", "Pils"]  # de laagste marge eerst
    assert rapport["beste"][0]["naam"] == "Pils"


def test_de_winst_gebruikt_de_prijs_van_het_moment_van_tellen(db):
    pid = _product(db, "Pils", verkoop=3.0, inkoop=1.0)  # prijs is later verhoogd
    _telling(db, 5, {pid: (10, 2.0)})  # destijds 2,00
    p = _regel(bereken_marge(db, 13, _vandaag()), "Pils")
    assert p["omzet"] == pytest.approx(20) and p["winst"] == pytest.approx(10)  # 20 - 10 x 1,00
    assert p["marge_pct"] == pytest.approx(66.666, rel=1e-3)  # de marge per stuk volgt de huidige prijzen


def test_een_telling_buiten_de_periode_telt_niet_mee(db):
    pid = _product(db, "Pils", verkoop=2.0, inkoop=1.0)
    _telling(db, 5, {pid: (10, 2.0)})
    _telling(db, 100, {pid: (500, 2.0)})  # 14 weken geleden
    assert _regel(bereken_marge(db, 4, _vandaag()), "Pils")["aantal"] == 10
    assert _regel(bereken_marge(db, 13, _vandaag()), "Pils")["aantal"] == 10  # 100 dagen = bijna 14,3 weken: net buiten
    assert _regel(bereken_marge(db, 26, _vandaag()), "Pils")["aantal"] == 510


def test_categorieen_zonder_verkoop_staan_er_niet_bij(db):
    pils = _product(db, "Pils", categorie="Bier", verkoop=2.0, inkoop=1.0)
    _product(db, "Leeg", categorie="Stilstaand", verkoop=2.0, inkoop=1.0)
    _telling(db, 3, {pils: (10, 2.0)})
    namen = [c["naam"] for c in bereken_marge(db, 13, _vandaag())["categorieen"]]
    assert "Bier" in namen and "Stilstaand" not in namen


def test_een_product_zonder_inkoopprijs_telt_niet_mee_in_de_marge_maar_staat_apart(db):
    goed = _product(db, "Pils", verkoop=2.0, inkoop=1.0)
    onbekend = _product(db, "Bozu", verkoop=3.5, inkoop=0)
    _telling(db, 3, {goed: (10, 2.0), onbekend: (30, 3.5)})
    rapport = bereken_marge(db, 13, _vandaag())
    assert rapport["zonder_inkoop"][0]["naam"] == "Bozu" and rapport["zonder_inkoop"][0]["omzet"] == pytest.approx(105)  # de meeste omzet eerst
    assert "Pils" not in [p["naam"] for p in rapport["zonder_inkoop"]]
    assert rapport["totaal"]["omzet"] == pytest.approx(125) and rapport["totaal"]["winst"] == pytest.approx(10)
    assert rapport["totaal"]["marge_pct"] == pytest.approx(50)  # alleen over de omzet met een inkoopprijs
    assert rapport["totaal"]["dekking_pct"] == pytest.approx(20 / 125 * 100)
    assert "Bozu" not in [p["naam"] for p in rapport["laagste"]]


def test_producten_die_niet_los_verkocht_worden_staan_er_niet_in(db):
    _product(db, "Fust", categorie="Fust", verkoop=0, inkoop=90)
    assert [p["naam"] for p in bereken_marge(db, 13, _vandaag())["producten"] if p["naam"] == "Fust"] == []


def test_zonder_tellingen_geeft_het_rapport_gewoon_nullen(db):
    rapport = bereken_marge(db, 13, _vandaag())
    assert rapport["totaal"]["omzet"] == 0 and rapport["totaal"]["marge_pct"] is None and rapport["totaal"]["dekking_pct"] is None


def test_de_margepagina(ingelogde_client, db):
    pid = _product(db, "Pils", verkoop=2.0, inkoop=1.7)
    _product(db, "Bozu", verkoop=3.5, inkoop=0)
    _telling(db, 3, {pid: (10, 2.0)})
    tekst = ingelogde_client.get("/rapporten/marge?weken=8").data.decode()
    assert "Verdienen het minst" in tekst and "Pils" in tekst and "Zonder inkoopprijs" in tekst and "Bozu" in tekst
    assert "Laatste 8 weken" in tekst and "selected" in tekst
    assert "15%" in tekst  # (2,00 - 1,70) / 2,00


def test_de_margepagina_met_een_onbekende_periode_gebruikt_de_standaard(ingelogde_client):
    assert "Laatste 13 weken" in ingelogde_client.get("/rapporten/marge?weken=abc").data.decode()


def test_de_marge_is_alleen_voor_beheerders_en_staat_in_het_menu(ingelogde_client, app, db):
    assert 'href="/rapporten/marge"' in ingelogde_client.get("/").data.decode()
    _maak_vrijwilliger(db, "bakker", "voorraad")
    klant = app.test_client()
    _login(klant, "bakker")
    assert "alleen voor beheerders" in klant.get("/rapporten/marge", follow_redirects=True).data.decode()
    assert 'href="/rapporten/marge"' not in klant.get("/").data.decode()


# ---------- Derving ----------


def test_een_geldige_reden_kiezen():
    assert kies_reden("breuk") == "breuk"
    assert kies_reden("") is None and kies_reden(None) is None and kies_reden("onzin") is None


def _boek(client, pid, mtype="uit", **extra):
    return client.post(
        "/boeken", data={"csrf_token": _csrf(client), "product_id": str(pid), "type": mtype, "aantal": "3", **extra}, follow_redirects=True
    )


def test_uitboeken_met_een_reden_bewaart_de_reden(ingelogde_client, db):
    pid = _product(db, "Pils", inkoop=1.0, voorraad=50)
    resp = _boek(ingelogde_client, pid, reden="breuk", opmerking="Krat gevallen")
    assert "afgeboekt" in resp.data.decode() and "Breuk of gemorst" in resp.data.decode()  # staat bij de laatste boekingen
    rij = db.execute("SELECT type, aantal, reden, opmerking FROM mutaties WHERE product_id = ?", (pid,)).fetchone()
    assert tuple(rij) == ("uit", 3, "breuk", "Krat gevallen")


def test_zonder_reden_of_met_een_onzinreden_is_het_gewoon_uitboeken(ingelogde_client, db):
    pid = _product(db, "Pils")
    _boek(ingelogde_client, pid)
    _boek(ingelogde_client, pid, reden="onzin")
    assert [r[0] for r in db.execute("SELECT reden FROM mutaties WHERE product_id = ?", (pid,))] == [None, None]


def test_een_reden_bij_inboeken_wordt_genegeerd(ingelogde_client, db):
    pid = _product(db, "Pils")
    _boek(ingelogde_client, pid, "in", reden="breuk")
    assert db.execute("SELECT reden FROM mutaties WHERE product_id = ?", (pid,)).fetchone()[0] is None


def test_het_boekformulier_heeft_een_reden_die_pas_bij_uit_zichtbaar_wordt(ingelogde_client, db):
    pid = _product(db, "Pils")
    for pad in ("/boeken", f"/producten/{pid}"):
        tekst = ingelogde_client.get(pad).data.decode()
        assert 'name="reden"' in tekst and "derving-reden" in tekst and 'hidden' in tekst, pad
        for naam in DERVING_REDENEN.values():
            assert naam in tekst


def test_een_reden_staat_in_de_geschiedenis_en_op_de_productpagina(ingelogde_client, db):
    pid = _product(db, "Pils")
    _boek(ingelogde_client, pid, reden="over_datum")
    assert "Over de datum of bedorven" in ingelogde_client.get("/geschiedenis").data.decode()
    assert "Over de datum of bedorven" in ingelogde_client.get(f"/producten/{pid}").data.decode()


def test_derving_per_reden_product_en_waarde(db):
    pils = _product(db, "Pils", inkoop=1.2)
    cola = _product(db, "Cola", inkoop=0.5)
    _uitboeking(db, pils, 10, "breuk")
    _uitboeking(db, pils, 5, "over_datum")
    _uitboeking(db, cola, 20, "breuk")
    _uitboeking(db, cola, 4, None)  # gewoon uitgeboekt: geen derving
    rapport = bereken_derving(db, 13, _vandaag())
    assert rapport["totaal"]["boekingen"] == 3 and rapport["totaal"]["waarde"] == pytest.approx(15 * 1.2 + 20 * 0.5)
    reden = {r["naam"]: r for r in rapport["per_reden"]}
    assert reden["Breuk of gemorst"]["stuks"] == 30 and reden["Breuk of gemorst"]["boekingen"] == 2
    assert reden["Breuk of gemorst"]["waarde"] == pytest.approx(10 * 1.2 + 20 * 0.5)
    assert [p["naam"] for p in rapport["per_product"]] == ["Pils", "Cola"]  # op waarde: 18 tegen 10
    assert len(rapport["recent"]) == 3 and rapport["recent"][0]["reden_naam"]


def test_derving_buiten_de_periode_en_onbekende_redenen_tellen_niet(db):
    pid = _product(db, "Pils", inkoop=1.0)
    _uitboeking(db, pid, 99, "breuk", dagen_geleden=400)
    _uitboeking(db, pid, 7, "uit-een-oude-versie")
    _uitboeking(db, pid, 1, "breuk")
    rapport = bereken_derving(db, 13, _vandaag())
    assert rapport["totaal"]["boekingen"] == 1 and rapport["per_reden"][0]["stuks"] == 1


def test_de_dervingspagina(ingelogde_client, db):
    pid = _product(db, "Pils", inkoop=2.0)
    _uitboeking(db, pid, 6, "weggegeven", naam="Bakker", opmerking="Proeverij sponsor")
    tekst = ingelogde_client.get("/rapporten/derving").data.decode()
    assert "Gratis weggegeven" in tekst and "Pils" in tekst and "Proeverij sponsor" in tekst and "Bakker" in tekst
    assert "12,00" in tekst  # 6 x 2,00
    assert "Laatste 13 weken" in tekst


def test_de_dervingspagina_zonder_boekingen_zegt_dat(ingelogde_client):
    assert "niets met een reden uitgeboekt" in ingelogde_client.get("/rapporten/derving").data.decode()


def test_derving_is_alleen_voor_beheerders(client, db):
    _maak_vrijwilliger(db, "bakker", "voorraad")
    _login(client, "bakker")
    assert "alleen voor beheerders" in client.get("/rapporten/derving", follow_redirects=True).data.decode()
    # Maar uitboeken met een reden mag iedereen met voorraadrechten.
    pid = _product(db, "Pils", voorraad=20)
    client.post("/boeken", data={"csrf_token": _csrf(client), "product_id": str(pid), "type": "uit", "aantal": "2", "reden": "breuk"})
    assert db.execute("SELECT reden FROM mutaties WHERE product_id = ?", (pid,)).fetchone()[0] == "breuk"
