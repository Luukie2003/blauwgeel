"""De keuken per verpakking (1.75.0): inboeken nooit per stuk, de verpakkingen per merk (ook zonder barcode), het
aantal erin één keer vragen, muteren en derven, en wat op raakt op de boodschappenlijst in plaats van de bestellijst."""

from conftest import stel_csrf_token_in as _csrf
from test_app_api import app_client  # noqa: F401 (fixture)
from test_app_api_meer import _vrijwilliger
from test_barcodes import AH_DOOS, AH_ZAK, PLUS_ZAK, _artikel, _ean
from test_keuken_module import _keuken, _voorraad
from test_secties_rechten import _login, _maak_vrijwilliger

import bestelvoorstel
from helpers.producten import bestel_suggesties
from keukenbeheer import (
    boek_keuken_in,
    keuken_barcodes,
    keuken_verpakkingen,
    muteer_keuken,
    verwerk_keuken_telling,
    zet_keuken_verpakking,
    zet_product_verpakking,
)


def _frikandel(db, **kwargs):
    """Frikandellen van twee merken: AH (zak van 20, € 10, en een doos met 2 zakken) en Plus (zak van 15, € 9). Bij het
    product zelf staat nog een oude 'doos van 40'."""
    pid = _keuken(db, **kwargs)
    ah = _artikel(db, pid, "AH frikandellen", ean=AH_ZAK, aantal=20, prijs=10, doos=AH_DOOS, per_doos=2)
    plus = _artikel(db, pid, "Plus frikandellen", ean=PLUS_ZAK, aantal=15, prijs=9)
    return pid, ah, plus


def _boodschappen(db, afgevinkt=0):
    return [r[0] for r in db.execute("SELECT tekst FROM boodschappen WHERE afgevinkt = ? ORDER BY id", (afgevinkt,))]


# ---------- Verpakkingen ----------


def test_verpakkingen_per_merk_en_zonder_barcode(db):
    pid, ah, plus = _frikandel(db)
    gehakt = _keuken(db, naam="Gehaktbal Proef", factor=24, inkoop=18.0)
    los = _keuken(db, naam="Kroket Proef", factor=1)
    v = keuken_verpakkingen(db)
    # De kleinste eerst; de oude 'doos van 40' van het product zelf staat er niet naast de echte zakken.
    assert [(x["sleutel"], x["naam"], x["aantal"]) for x in v[pid]] == [
        (f"artikel:{plus}", "Plus frikandellen", 15), (f"artikel:{ah}", "AH frikandellen", 20),
        (f"doos:{ah}", "AH frikandellen, doos van 2", 40)]
    assert [x["per_stuk"] for x in v[pid]] == [0.6, 0.5, 0.5]
    assert v[gehakt] == [{"sleutel": "product", "naam": "doos", "aantal": 24, "per_stuk": 0.75}]
    assert los not in v  # per stuk inboeken kan niet: eerst een verpakking instellen


def test_een_verpakking_zonder_aantal_vraagt_het_eerst(db):
    pid = _keuken(db)
    code = _ean("871000000044")
    _artikel(db, pid, "Jumbo frikandellen", ean=code, aantal=1, prijs=12)
    assert keuken_barcodes(db)[code]["aantal"] is None  # niet 1: per stuk inboeken doet de keuken niet
    assert boek_keuken_in(db, {}, "Kok", "2026-10-10 10:00", scans=[code]) == {
        "producten": 0, "overgeslagen": ["Jumbo frikandellen, 1 Stuks, € 12,00: er staat niet bij hoeveel erin zit"]}

    assert zet_keuken_verpakking(db, code, 1)[1].startswith("Vul in hoeveel")
    d, fout = zet_keuken_verpakking(db, code, 24, "Kok")
    assert fout is None and d["aantal"] == 24
    # De inkoopprijs van het product volgt het merk: € 12 voor 24 is € 0,50 per stuk, de doos van 40 dus € 20.
    assert db.execute("SELECT inkoopprijs FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 20.0
    assert boek_keuken_in(db, {}, "Kok", "2026-10-10 10:00", scans=[code, code])["producten"] == 1
    assert _voorraad(db, pid) == 40 + 48


def test_aantal_in_een_doos_is_een_veelvoud_van_de_zak(db):
    pid = _keuken(db)
    zak, doos = _ean("871000000055"), _ean("871000000066")
    artikel = _artikel(db, pid, "Mora zak", ean=zak, aantal=20, doos=doos, per_doos=1)
    assert "veelvoud van 20" in zet_keuken_verpakking(db, doos, 50)[1]
    d, fout = zet_keuken_verpakking(db, doos, 60)
    assert fout is None and d["aantal"] == 60
    assert db.execute("SELECT per_omverpakking FROM artikelen WHERE id = ?", (artikel,)).fetchone()[0] == 3
    assert zet_keuken_verpakking(db, _ean("871000000077"), 10)[1] == "Deze barcode hoort bij geen keukenproduct."


def test_verpakking_instellen_voor_een_product_zonder_barcode(db):
    pid = _keuken(db, naam="Gehaktbal Los", factor=1, inkoop=0.5)
    assert zet_product_verpakking(db, pid, "doos", 1) == "Vul in hoeveel er in een verpakking zit (2 of meer)."
    assert zet_product_verpakking(db, pid, "  bak ", 12) is None
    p = db.execute("SELECT besteleenheid, besteleenheid_factor, inkoopprijs FROM producten WHERE id = ?", (pid,)).fetchone()
    assert tuple(p) == ("Bak", 12, 6.0)  # een gehaktbal blijft € 0,50
    assert keuken_verpakkingen(db)[pid] == [{"sleutel": "product", "naam": "bak", "aantal": 12, "per_stuk": 0.5}]
    gewoon = db.execute("INSERT INTO producten (naam, categorie, voorraad) VALUES ('Cola', 'Fris', 1)").lastrowid
    assert zet_product_verpakking(db, gewoon, "krat", 24) == "Dit is geen keukenproduct."


# ---------- Inboeken: altijd per verpakking ----------


def test_inboeken_met_scans_en_verpakkingen(db):
    pid, ah, plus = _frikandel(db, voorraad=0)
    uitkomst = boek_keuken_in(db, {pid: {f"artikel:{plus}": 2, f"doos:{ah}": 1}}, "Kok", "2026-10-10 10:00",
                              scans=[AH_ZAK, AH_ZAK, "0" + AH_ZAK, _ean("871000000088")])
    assert uitkomst["producten"] == 1
    assert uitkomst["overgeslagen"] == [f"barcode {_ean('871000000088')}: hoort bij geen actief keukenproduct"]
    assert _voorraad(db, pid) == 3 * 20 + 2 * 15 + 40
    opmerkingen = [m[0] for m in db.execute("SELECT opmerking FROM mutaties WHERE product_id = ? ORDER BY id", (pid,))]
    assert opmerkingen == ["Ingeboekt (keuken): 3× AH frikandellen, 20 Stuks, € 10,00 (gescand)",
                           "Ingeboekt (keuken): 2× Plus frikandellen (30 stuks)",
                           "Ingeboekt (keuken): 1× AH frikandellen, doos van 2 (40 stuks)"]


def test_nooit_per_stuk_inboeken(db):
    los = _keuken(db, naam="Kroket Los", factor=1, voorraad=0)
    uitkomst = boek_keuken_in(db, {los: 5}, "Kok", "2026-10-10 10:00")
    assert uitkomst == {"producten": 0, "overgeslagen": ["Kroket Los: er staat niet bij hoeveel er in een verpakking zit"]}
    assert _voorraad(db, los) == 0


def test_inboeken_op_de_site(ingelogde_client, db):
    pid, ah, plus = _frikandel(db, voorraad=0)
    gehakt = _keuken(db, naam="Gehaktbal Proef", factor=24, inkoop=18.0, voorraad=0)
    pagina = ingelogde_client.get("/keuken/inboeken").data.decode()
    assert f'name="inkoop_{gehakt}"' in pagina and f'name="inkoop_{pid}"' not in pagina  # per merk: bij de barcode
    assert "per merk, gem." in pagina
    resp = ingelogde_client.post("/keuken/inboeken", data={
        "csrf_token": _csrf(ingelogde_client), "scan": [AH_ZAK, PLUS_ZAK], f"pakket_{pid}__artikel:{plus}": "1",
        f"pakket_{gehakt}__product": "2", f"inkoop_{gehakt}": "19,20"}, follow_redirects=True)
    assert "2 producten ingeboekt." in resp.data.decode()
    assert (_voorraad(db, pid), _voorraad(db, gehakt)) == (20 + 15 + 15, 48)
    assert db.execute("SELECT inkoopprijs FROM producten WHERE id = ?", (gehakt,)).fetchone()[0] == 19.2

    los = _keuken(db, naam="Kroket Los", factor=1)
    resp = ingelogde_client.post("/keuken/inboeken", data={"csrf_token": _csrf(ingelogde_client), f"pakket_{los}__product": "3"},
                                 follow_redirects=True)
    assert "Niet ingeboekt: Kroket Los: er staat niet bij hoeveel er in een verpakking zit." in resp.data.decode()


def test_verpakking_en_aantal_instellen_op_de_site(ingelogde_client, db):
    los = _keuken(db, naam="Gehaktbal Los", factor=1, inkoop=0.5)
    kop = {"X-CSRF-Token": _csrf(ingelogde_client)}
    resp = ingelogde_client.post("/keuken/product-verpakking", json={"product_id": los, "naam": "doos", "aantal": 20}, headers=kop)
    assert resp.status_code == 200 and resp.get_json()["verpakkingen"][0]["aantal"] == 20
    assert ingelogde_client.post("/keuken/product-verpakking", json={"product_id": los, "aantal": 1}, headers=kop).status_code == 400

    code = _ean("871000000099")
    _artikel(db, los, "Slager", ean=code, aantal=1)
    resp = ingelogde_client.post("/keuken/verpakking", json={"code": code, "aantal": 30}, headers=kop)
    assert resp.status_code == 200 and resp.get_json()["aantal"] == 30 and resp.get_json()["code"] == code
    # Koppelen met 1 erin kan niet meer: per stuk inboeken doet de keuken niet.
    resp = ingelogde_client.post("/keuken/barcode-koppelen", json={"code": _ean("871000000100"), "product_id": los, "aantal": 1},
                                 headers=kop)
    assert resp.status_code == 400 and "2 of meer" in resp.get_json()["fout"]


# ---------- Muteren en derven ----------


def test_derving_en_correctie(db):
    from datetime import date

    from derving import bereken_derving

    pid = _keuken(db, voorraad=30)
    assert muteer_keuken(db, pid, "derving", 3, "Kok")[1] == "Kies waarom het weg is."
    assert muteer_keuken(db, pid, "derving", 0, "Kok", reden="breuk")[1] == "Vul een aantal van 1 of meer in."
    melding, fout = muteer_keuken(db, pid, "derving", 3, "Kok", reden="over_datum", opmerking="aangebrand")
    assert fout is None and melding == "3 stuks Frikandel Proef weggegooid. Voorraad nu 27 stuks."
    rij = db.execute("SELECT type, aantal, reden, opmerking FROM mutaties WHERE product_id = ?", (pid,)).fetchone()
    assert tuple(rij) == ("uit", 3, "over_datum", "Keuken: weggegooid (derving), aangebrand")
    per_reden = bereken_derving(db, 1, date.today())["per_reden"]
    assert [(r["naam"], r["stuks"]) for r in per_reden] == [("Over de datum of bedorven", 3)]

    assert muteer_keuken(db, pid, "erbij", 2, "Kok")[0].endswith("Voorraad nu 29 stuks.")
    assert muteer_keuken(db, pid, "eraf", 4, "Kok")[0].endswith("Voorraad nu 25 stuks.")
    # Wat weggegooid is, telt bij de volgende telling niet als verkocht.
    telling = verwerk_keuken_telling(db, {pid: 25}, "Kok", "2026-10-11 20:00")
    assert db.execute("SELECT verkocht FROM keuken_telling_regels WHERE telling_id = ?", (telling,)).fetchone()[0] == 0
    gewoon = db.execute("INSERT INTO producten (naam, categorie, voorraad) VALUES ('Cola', 'Fris', 1)").lastrowid
    assert muteer_keuken(db, gewoon, "eraf", 1, "Kok")[1] == "Dit is geen keukenproduct."


def test_muteren_op_de_site_en_alleen_met_keukenrechten(client, db):
    pid = _keuken(db, voorraad=30)
    _maak_vrijwilliger(db, "kokmut", "keuken")
    _login(client, "kokmut")
    assert "Waarom is het weg?" in client.get("/keuken/muteren").data.decode()
    resp = client.post("/keuken/muteren", data={"csrf_token": _csrf(client), "product_id": pid, "soort": "derving",
                                                "aantal": "2", "reden": "breuk"}, follow_redirects=True)
    tekst = resp.data.decode()
    assert "2 stuks Frikandel Proef weggegooid." in tekst and "Breuk of gemorst" in tekst  # en in Laatst gemuteerd
    assert _voorraad(db, pid) == 28

    andere = client.application.test_client()
    _maak_vrijwilliger(db, "tapmut", "voorraad")
    _login(andere, "tapmut")
    assert andere.get("/keuken/muteren").status_code == 302


# ---------- Op raken: de boodschappenlijst, niet de bestellijst ----------


def test_onder_het_minimum_op_de_boodschappenlijst_en_eraf_na_inboeken(db):
    pid, ah, _ = _frikandel(db, voorraad=40)  # minimum 20
    verwerk_keuken_telling(db, {pid: 25}, "Kok", "2026-10-11 20:00")
    assert _boodschappen(db) == []
    verwerk_keuken_telling(db, {pid: 12}, "Kok", "2026-10-12 20:00")
    muteer_keuken(db, pid, "derving", 2, "Kok", reden="breuk")
    assert _boodschappen(db) == ["Frikandel Proef (keuken)"]  # maar één keer

    boek_keuken_in(db, {}, "Kok", "2026-10-13 10:00", scans=[AH_ZAK])  # 10 + 20 = 30: weer genoeg
    assert _boodschappen(db) == [] and _boodschappen(db, afgevinkt=1) == ["Frikandel Proef (keuken)"]


def test_de_keuken_staat_niet_op_de_bestellijst(app_client, ingelogde_client, db):  # noqa: F811
    import productinfo

    pid = _keuken(db, voorraad=0)
    assert pid not in {p["id"] for p in bestel_suggesties(db)}
    assert pid not in bestelvoorstel.adviezen(db)["producten"]
    lijst = app_client.get("/api/app/bestellijst").get_json()
    assert pid not in {p["id"] for p in lijst["bestellen"]}
    assert f'<option value="{pid}"' not in ingelogde_client.get("/bestellijst").data.decode()  # ook niet bij Ander product

    # Ook geen colli kiezen, in de app of op de site, en geen bestelblok op het productscherm.
    resp = app_client.post("/api/app/bestellijst/controleren", json={"product_id": pid, "eenheden": 1}, headers=app_client.kop)
    assert resp.status_code == 400 and resp.get_json()["fout"] == "keuken"
    resp = app_client.post(f"/api/app/producten/{pid}/bestelaantal", json={"eenheden": 1}, headers=app_client.kop)
    assert resp.status_code == 400 and "boodschappenlijst" in resp.get_json()["melding"]
    resp = ingelogde_client.post(f"/producten/{pid}/bestellen", data={"csrf_token": _csrf(ingelogde_client), "eenheden": "2"},
                                 follow_redirects=True)
    assert "Keukenspullen staan niet op de bestellijst" in resp.data.decode()
    assert pid not in bestelvoorstel.bijstellingen(db)
    product = db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()
    assert productinfo.bestelblok(db, product) is None


# ---------- De app ----------


def test_keuken_in_de_app(app, db):
    pid, ah, plus = _frikandel(db, voorraad=0)
    jumbo = _ean("871000000111")
    _artikel(db, pid, "Jumbo", ean=jumbo, aantal=1)
    kok = _vrijwilliger(app, db, "kokapp", "keuken")

    keuken = kok.get("/api/app/keuken").get_json()
    p = next(x for x in keuken["producten"] if x["id"] == pid)
    assert [(v["sleutel"], v["aantal"]) for v in p["verpakkingen"]] == [(f"artikel:{plus}", 15), (f"artikel:{ah}", 20),
                                                                         (f"doos:{ah}", 40)]
    assert next(d for d in p["dozen"] if d["code"] == jumbo)["aantal"] is None
    assert {"sleutel": "over_datum", "naam": "Over de datum of bedorven"} in keuken["derving_redenen"]

    # Het aantal in de Jumbo-zak vragen en bewaren, dan inboeken met scans en een verpakking zonder barcode.
    resp = kok.post("/api/app/keuken/verpakking", json={"code": jumbo, "aantal": 12}, headers=kok.kop).get_json()
    assert (resp["aantal"], resp["product_id"]) == (12, pid)
    resp = kok.post("/api/app/keuken/inboeken", json={"scans": [jumbo, AH_DOOS], "verpakkingen": {str(pid): {f"artikel:{plus}": 1}},
                                                       "verzoek_id": "kin1"}, headers=kok.kop)
    assert resp.status_code == 200 and resp.get_json()["melding"] == "1 product ingeboekt."
    assert _voorraad(db, pid) == 12 + 40 + 15
    resp = kok.post("/api/app/keuken/inboeken", json={"scans": [_ean("871000000122")], "verzoek_id": "kin2"}, headers=kok.kop)
    assert resp.status_code == 400 and "Niet ingeboekt" in resp.get_json()["melding"]

    resp = kok.post("/api/app/keuken/muteren", json={"product_id": pid, "soort": "derving", "aantal": 7, "reden": "breuk",
                                                     "verzoek_id": "kmu1"}, headers=kok.kop)
    assert resp.status_code == 200 and resp.get_json()["melding"].endswith("Voorraad nu 60 stuks.")
    assert kok.post("/api/app/keuken/muteren", json={"product_id": pid, "soort": "derving", "aantal": 1},
                    headers=kok.kop).status_code == 400

    los = _keuken(db, naam="Gehaktbal Los", factor=1)
    resp = kok.post("/api/app/keuken/product-verpakking", json={"product_id": los, "naam": "doos", "aantal": 24}, headers=kok.kop)
    assert resp.get_json()["verpakkingen"] == [{"sleutel": "product", "naam": "doos", "aantal": 24}]

    # Koppelen kan ook met alleen keukenrechten (de algemene koppeling is voor de voorraad), en nooit per stuk.
    nieuw = _ean("871000000133")
    resp = kok.post("/api/app/keuken/koppelen", json={"code": nieuw, "product_id": los, "aantal": 1, "verzoek_id": "kk1"},
                    headers=kok.kop)
    assert resp.status_code == 400 and "2 of meer" in resp.get_json()["melding"]
    resp = kok.post("/api/app/keuken/koppelen", json={"code": nieuw, "product_id": los, "aantal": 10, "naam": "Slager",
                                                      "inkoopprijs": "7,50", "verzoek_id": "kk2"}, headers=kok.kop).get_json()
    assert (resp["code"], resp["product_id"], resp["aantal"]) == (nieuw, los, 10) and resp["omschrijving"].startswith("Slager")
    assert kok.post("/api/app/barcodes/koppelen", json={"code": _ean("871000000144"), "product_id": los},
                    headers=kok.kop).status_code == 403
