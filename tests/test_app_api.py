"""De JSON-API voor de handterminal-app (routes/app_api.py)."""

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_barcodes import AH_DOOS, AH_ZAK, _artikel, _ean, _product
from test_secties_rechten import _login, _maak_vrijwilliger

import barcodes

FLES, KRAT = _ean("871200000001"), _ean("871200000002")


@pytest.fixture
def app_client(app):
    """Ingelogd zoals de app dat doet: met de code, en het csrf_token in een header."""
    client = app.test_client()
    login = client.post("/api/tablet-code/inloggen", json={"code": "999999"}).get_json()
    assert login["geldig"]
    client.kop = {"X-CSRF-Token": login["csrf_token"]}
    return client


def _post(client, pad, **json):
    return client.post(pad, json=json, headers=client.kop)


def _voorraad(db, pid):
    return db.execute("SELECT voorraad FROM producten WHERE id = ?", (pid,)).fetchone()[0]


# ---------- Inloggen en rechten ----------


def test_zonder_inloggen_json_in_plaats_van_een_doorverwijzing(client):
    resp = client.get("/api/app/start")
    assert resp.status_code == 401 and resp.get_json()["fout"] == "niet_ingelogd"


def test_zonder_voorraadrechten_alleen_het_startscherm(app, db):
    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    client = app.test_client()
    _login(client, "keukenhulp")
    start = client.get("/api/app/start").get_json()
    assert start["toegang"]["voorraad"] is False and start["toegang"]["keuken"] is True
    assert "Keuken" in [p["label"] for p in start["paginas"]] and "Bestellijst" not in [p["label"] for p in start["paginas"]]
    assert client.get("/api/app/producten").status_code == 403
    assert client.post("/api/app/tellen/stand", json={}, headers={"X-CSRF-Token": _csrf(client)}).status_code == 403


def test_overal_uitgelogd_geeft_json(app_client, db):
    db.execute("UPDATE gebruikers SET sessie_versie = sessie_versie + 1 WHERE naam = 'admin'")
    db.commit()
    assert app_client.get("/api/app/producten").status_code == 401


def test_schrijven_zonder_csrf_token_mag_niet(app_client, db):
    pid = _product(db, "Cola")
    resp = app_client.post(f"/api/app/producten/{pid}/boeken", json={"type": "in", "aantal": 1})
    assert resp.status_code == 400 and resp.get_json()["fout"] == "csrf"
    assert _voorraad(db, pid) == 10


# ---------- Startscherm en producten ----------


def test_startscherm(app_client, db):
    start = app_client.get("/api/app/start").get_json()
    assert start["naam"] == "admin" and start["beheerder"] and start["toegang"]["voorraad"]
    assert {"Bestellijst", "Prikbord", "Kluis"} <= {p["label"] for p in start["paginas"]}
    assert all(p["pad"].startswith("/") for p in start["paginas"])
    assert start["app_versie"]


def test_productlijst_met_barcodes_en_etag(app_client, db):
    pid = _product(db, "Hertog Jan", eenheid="fles", categorie="Bier")
    db.execute("UPDATE producten SET besteleenheid = 'krat', besteleenheid_factor = 24 WHERE id = ?", (pid,))
    db.commit()
    _artikel(db, pid, "Hertog Jan 30cl", FLES, doos=KRAT, per_doos=24)
    resp = app_client.get("/api/app/producten")
    hertog = next(p for p in resp.get_json()["producten"] if p["id"] == pid)
    assert hertog["besteleenheid"] == "krat" and hertog["per_besteleenheid"] == 24
    assert {(b["code"], b["niveau"], b["aantal"]) for b in hertog["barcodes"]} == {
        (FLES, "verpakking", 1), (KRAT, "omverpakking", 24)}

    etag = resp.headers["ETag"]
    assert app_client.get("/api/app/producten", headers={"If-None-Match": etag}).status_code == 304
    _post(app_client, f"/api/app/producten/{pid}/boeken", type="in", aantal=1)
    assert app_client.get("/api/app/producten", headers={"If-None-Match": etag}).status_code == 200


def test_een_product_met_de_laatste_boekingen(app_client, db):
    pid = _product(db, "Cola")
    _post(app_client, f"/api/app/producten/{pid}/boeken", type="uit", aantal=2, reden="breuk")
    product = app_client.get(f"/api/app/producten/{pid}").get_json()
    assert product["product"]["voorraad"] == 8 and product["pad"] == f"/producten/{pid}"
    assert product["mutaties"][0]["reden"] == "Breuk of gemorst" and product["mutaties"][0]["naam"] == "admin"
    assert app_client.get("/api/app/producten/999999").status_code == 404


# ---------- Boeken ----------


def test_boeken_erin_en_eruit(app_client, db):
    pid = _product(db, "Cola")
    erin = _post(app_client, f"/api/app/producten/{pid}/boeken", type="in", aantal=24).get_json()
    assert erin["voorraad"] == 34 and "24 stuks erin" in erin["melding"]
    eruit = _post(app_client, f"/api/app/producten/{pid}/boeken", type="uit", aantal=40).get_json()
    assert eruit["voorraad"] == -6 and "Controleer de telling" in eruit["waarschuwing"]
    assert _voorraad(db, pid) == -6
    for fout in ({"type": "in", "aantal": 0}, {"type": "erin", "aantal": 1}, {"type": "in", "aantal": "veel"}):
        assert _post(app_client, f"/api/app/producten/{pid}/boeken", **fout).status_code == 400
    assert _voorraad(db, pid) == -6


def test_dezelfde_boeking_nog_een_keer_sturen_boekt_niet_dubbel(app_client, db):
    """De verbinding viel weg na het opslaan, en de app stuurt hetzelfde verzoek opnieuw."""
    pid = _product(db, "Cola")
    eerste = _post(app_client, f"/api/app/producten/{pid}/boeken", type="in", aantal=5, verzoek_id="abc-1")
    tweede = _post(app_client, f"/api/app/producten/{pid}/boeken", type="in", aantal=5, verzoek_id="abc-1")
    assert eerste.get_json() == tweede.get_json() and _voorraad(db, pid) == 15
    _post(app_client, f"/api/app/producten/{pid}/boeken", type="in", aantal=5, verzoek_id="abc-2")
    assert _voorraad(db, pid) == 20
    assert db.execute("SELECT COUNT(*) FROM mutaties WHERE product_id = ?", (pid,)).fetchone()[0] == 2


def test_boeken_op_de_site_werkt_nog_hetzelfde(ingelogde_client, db):
    pid = _product(db, "Cola")
    ingelogde_client.post("/boeken", data={"csrf_token": _csrf(ingelogde_client), "product_id": pid, "type": "uit",
                                           "aantal": 3, "reden": "breuk"})
    assert _voorraad(db, pid) == 7
    assert db.execute("SELECT reden FROM mutaties WHERE product_id = ?", (pid,)).fetchone()[0] == "breuk"


# ---------- Een barcode koppelen in één stap ----------


def test_een_flesje_koppelen_zonder_verder_iets_in_te_vullen(app_client, db):
    pid = _product(db, "Hertog Jan", eenheid="fles")
    resp = _post(app_client, "/api/app/barcodes/koppelen", code=FLES, product_id=pid)
    assert resp.status_code == 200
    assert resp.get_json()["product"]["barcodes"] == [{"code": FLES, "niveau": "verpakking", "aantal": 1,
                                                       "artikel": "Hertog Jan", "doos_aantal": None, "doos_code": None}]
    # Daarna de krat: die komt bij hetzelfde artikel.
    _post(app_client, "/api/app/barcodes/koppelen", code=KRAT, product_id=pid, per_doos=24)
    assert db.execute("SELECT COUNT(*) FROM artikelen WHERE product_id = ?", (pid,)).fetchone()[0] == 1
    assert barcodes.zoek_barcode(db, KRAT)["aantal"] == 24
    # Al gekoppeld: een duidelijke melding.
    fout = _post(app_client, "/api/app/barcodes/koppelen", code=FLES, product_id=pid).get_json()
    assert "hoort al bij" in fout["melding"]


def test_de_doos_bij_een_zak_van_twintig(db):
    pid = _product(db, "Frikandel")
    zak = _artikel(db, pid, "AH frikandellen", AH_ZAK, aantal=20)
    assert barcodes.snel_koppelen(db, AH_DOOS, pid, 80) == (zak, None)  # 80 frikandellen = 4 zakken
    assert barcodes.zoek_barcode(db, AH_DOOS)["aantal"] == 80
    andere_doos = _ean("871000000009")
    artikel_id, fout = barcodes.snel_koppelen(db, andere_doos, pid, 30)  # past niet in zakken van 20: eigen artikel
    assert fout is None and artikel_id != zak and barcodes.zoek_barcode(db, andere_doos)["aantal"] == 30


def test_koppelen_met_fouten(db):
    pid = _product(db, "Cola")
    assert barcodes.snel_koppelen(db, "123", pid)[1].startswith("'123' is geen barcode")
    assert "Kies bij welk product" in barcodes.snel_koppelen(db, FLES, 999999)[1]
    assert "hoeveel" in barcodes.snel_koppelen(db, FLES, pid, "nul")[1]


def test_snel_koppelen_op_de_site(ingelogde_client, db):
    pid = _product(db, "Hertog Jan", eenheid="fles")
    pagina = ingelogde_client.get(f"/barcodes/zoek?code={FLES}").data.decode()
    assert "Meer hoef je niet in te vullen" in pagina and 'name="per_doos"' in pagina
    ingelogde_client.post("/barcodes/snel-koppelen", data={"csrf_token": _csrf(ingelogde_client), "code": FLES,
                                                          "product_id": pid, "per_doos": ""})
    assert barcodes.zoek_barcode(db, FLES)["bekend"]


# ---------- Tellen ----------


def _tel_producten(app_client):
    return app_client.get("/api/app/tellen").get_json()["producten"]


def test_tellen_van_begin_tot_eind(app_client, db):
    producten = _tel_producten(app_client)
    eerste, tweede = producten[0], producten[1]
    bar = {str(eerste["id"]): "3", str(tweede["id"]): "1"}
    hok = {str(eerste["id"]): "4"}
    assert _post(app_client, "/api/app/tellen/stand", fase="hok", index=0, bar=bar, hok=hok).status_code == 200
    stand = app_client.get("/api/app/tellen").get_json()["stand"]
    assert stand["fase"] == "hok" and stand["bar"] == bar

    regels = _post(app_client, "/api/app/tellen/controleren", bar=bar, hok=hok).get_json()["regels"]
    totalen = {r["product_id"]: r["totaal"] for r in regels}
    assert totalen == {eerste["id"]: 7, tweede["id"]: 1}

    resp = _post(app_client, "/api/app/tellen/bevestigen", waarden={str(k): v for k, v in totalen.items()},
                 verzoek_id="tel-1")
    telling_id = resp.get_json()["telling_id"]
    assert _voorraad(db, eerste["id"]) == 7 and _voorraad(db, tweede["id"]) == 1
    assert app_client.get("/api/app/tellen").get_json()["stand"] is None
    # Nog een keer hetzelfde verzoek: geen tweede telling.
    _post(app_client, "/api/app/tellen/bevestigen", waarden={str(k): v for k, v in totalen.items()}, verzoek_id="tel-1")
    assert db.execute("SELECT COUNT(*) FROM tellingen").fetchone()[0] == 1
    assert db.execute("SELECT opmerking FROM tellingen WHERE id = ?", (telling_id,)).fetchone()[0].startswith(
        "Via de handterminal-app")


def test_op_de_app_gepauzeerd_op_de_site_verder(app_client, db):
    producten = _tel_producten(app_client)
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=2, bar={str(producten[0]["id"]): "5"}, hok={})
    # Dezelfde gebruiker op de site (de bewaarde stand hoort bij het account, niet bij het toestel).
    resp = app_client.get("/tellen/lopen/hervatten")
    assert resp.headers["Location"].endswith("/tellen/lopen")
    assert producten[2]["naam"] in app_client.get("/tellen/lopen").data.decode()


def test_niets_ingevuld_en_stoppen(app_client, db):
    assert _post(app_client, "/api/app/tellen/controleren", bar={}, hok={}).status_code == 400
    assert _post(app_client, "/api/app/tellen/bevestigen", waarden={}).status_code == 400
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=1, bar={"1": "2"}, hok={})
    _post(app_client, "/api/app/tellen/stoppen")
    assert app_client.get("/api/app/tellen").get_json()["stand"] is None


def test_rommel_in_de_stand_wordt_genegeerd(app_client, db):
    _post(app_client, "/api/app/tellen/stand", fase="iets", index="x", bar={"1": "-3", "a": "2", "2": "4"}, hok=[1])
    stand = app_client.get("/api/app/tellen").get_json()["stand"]
    assert stand["fase"] == "bar" and stand["index"] == 0 and stand["bar"] == {"2": "4"} and stand["hok"] == {}


def test_dezelfde_factuurscan_telt_maar_een_keer(app_client, db):
    pid = _product(db, "Hertog Jan", eenheid="fles")
    _artikel(db, pid, "Hertog Jan 30cl", FLES, doos=KRAT, per_doos=24)
    ronde_id = _post(app_client, "/api/facturen").get_json()["id"]
    for _ in range(2):  # de verbinding viel weg, de app stuurt dezelfde scan nog een keer
        antwoord = _post(app_client, f"/api/facturen/{ronde_id}/scan", code=KRAT, verzoek_id="scan-1").get_json()
    assert antwoord["status"] == "toegevoegd" and antwoord["ronde"]["scans"] == 1
    _post(app_client, f"/api/facturen/{ronde_id}/scan", code=KRAT, verzoek_id="scan-2")
    assert app_client.get(f"/api/facturen/{ronde_id}").get_json()["scans"] == 2
    assert _post(app_client, "/api/facturen/999999/scan", code=KRAT).status_code == 404


# ---------- Versie 2.1: foto's, de doos bij een losse verpakking, en eigen schermen ----------


def test_productlijst_met_foto_en_de_doos_van_een_losse_verpakking(app_client, db):
    pid = _product(db, "Chips paprika", eenheid="zak", categorie="Chips")
    db.execute("UPDATE producten SET afbeelding = 'chips.png' WHERE id = ?", (pid,))
    db.commit()
    zak, doos = _ean("871300000001"), _ean("871300000002")
    _artikel(db, pid, "Lay's paprika", zak, doos=doos, per_doos=20)
    chips = next(p for p in app_client.get("/api/app/producten").get_json()["producten"] if p["id"] == pid)
    los = next(b for b in chips["barcodes"] if b["niveau"] == "verpakking")
    assert los["doos_aantal"] == 20 and los["doos_code"] == doos
    assert chips["foto"].startswith("/static/product_afbeeldingen/") and chips["foto_groot"]


def test_keukenspullen_koppelen_met_inhoud_en_inkoopprijs(app_client, db):
    pid = _product(db, "Frikandel", categorie="Keuken")
    ah, plus = _ean("871300000011"), _ean("871300000012")
    _post(app_client, "/api/app/barcodes/koppelen", code=ah, product_id=pid, per_verpakking=20, inkoopprijs="20",
          naam="AH frikandellen")
    _post(app_client, "/api/app/barcodes/koppelen", code=plus, product_id=pid, per_verpakking=15, inkoopprijs="16,50",
          naam="Plus frikandellen")
    assert barcodes.zoek_barcode(db, ah)["omschrijving"] == "AH frikandellen, 20 stuks, € 20,00"
    assert barcodes.zoek_barcode(db, plus)["aantal"] == 15
    assert db.execute("SELECT COUNT(*) FROM artikelen WHERE product_id = ?", (pid,)).fetchone()[0] == 2


def test_prikbord(app_client, db):
    leeg = app_client.get("/api/app/prikbord").get_json()["mededelingen"]
    antwoord = _post(app_client, "/api/app/prikbord", tekst="Tapkraan lekt", urgent=True, verzoek_id="p-1").get_json()
    _post(app_client, "/api/app/prikbord", tekst="Tapkraan lekt", urgent=True, verzoek_id="p-1")  # niet dubbel
    nieuw = antwoord["mededelingen"][0]
    assert len(antwoord["mededelingen"]) == len(leeg) + 1 and nieuw["urgent"] and nieuw["naam"] == "admin"
    met_reactie = _post(app_client, f"/api/app/prikbord/{nieuw['id']}/reactie", tekst="Ik kijk ernaar").get_json()
    assert met_reactie["mededelingen"][0]["reacties"][0]["tekst"] == "Ik kijk ernaar"
    na = _post(app_client, f"/api/app/prikbord/{nieuw['id']}/afhandelen").get_json()["mededelingen"]
    assert next(m for m in na if m["id"] == nieuw["id"])["afgehandeld"]
    assert _post(app_client, "/api/app/prikbord", tekst="  ").status_code == 400


def test_geschiedenis_tellingen_en_bestellijst(app_client, db):
    pid = _product(db, "Cola")
    db.execute("UPDATE producten SET min_voorraad = 20 WHERE id = ?", (pid,))
    db.commit()
    _post(app_client, f"/api/app/producten/{pid}/boeken", type="uit", aantal=2)
    mutaties = app_client.get(f"/api/app/geschiedenis?product_id={pid}").get_json()["mutaties"]
    assert [(m["type"], m["aantal"], m["product"]) for m in mutaties] == [("uit", 2, "Cola")]

    _post(app_client, "/api/app/tellen/bevestigen", waarden={str(pid): 5})
    telling = app_client.get("/api/app/tellingen").get_json()["tellingen"][0]
    detail = app_client.get(f"/api/app/tellingen/{telling['id']}").get_json()
    assert detail["regels"][0]["product"] == "Cola" and detail["regels"][0]["verkocht"] == 3
    assert app_client.get("/api/app/tellingen/999999").status_code == 404

    db.execute("INSERT INTO bestellijst_meldingen (product_id, aangemaakt_op) VALUES (?, '2026-10-19 10:00')", (pid,))
    fris = _product(db, "Fanta")
    db.execute("UPDATE producten SET besteleenheid = 'tray', besteleenheid_factor = 24 WHERE id = ?", (fris,))
    bestelling = db.execute("INSERT INTO bestellingen (status, aangemaakt_op, referentie) VALUES ('besteld', '2026-10-19 09:00', 'Sligro')").lastrowid
    db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, 48)", (bestelling, fris))
    db.commit()
    lijst = app_client.get("/api/app/bestellijst").get_json()
    assert lijst["onderweg"][0]["regels"] == [{"product": "Fanta", "aantal": 2, "eenheid": "tray"}]
    assert pid in [p["id"] for p in lijst["bestellen"]] and lijst["gemeld"][0]["keer"] == 1
    assert _post(app_client, f"/api/app/bestellijst/gemeld/{pid}/afhandelen").get_json()["gemeld"] == []
