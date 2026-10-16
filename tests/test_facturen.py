"""Facturen inboeken door dozen en verpakkingen te scannen (zie facturen.py en routes/facturen.py)."""

from conftest import stel_csrf_token_in as _csrf
from test_barcodes import AH_DOOS, AH_ZAK, PLUS_ZAK, _artikel, _ean, _product
from test_secties_rechten import _login, _maak_vrijwilliger

import facturen


def _voorraad(db, pid):
    return db.execute("SELECT voorraad FROM producten WHERE id = ?", (pid,)).fetchone()[0]


def _frikandel(db):
    pid = _product(db, "Frikandel")  # voorraad 10
    _artikel(db, pid, "AH frikandellen", AH_ZAK, aantal=20, prijs=20, doos=AH_DOOS, per_doos=4)
    return pid


# ---------- De inboekronde ----------


def test_scannen_optellen_en_afronden(db):
    pid = _frikandel(db)
    ronde_id = facturen.start_ronde(db, factuurnummer="F-1001", door="Luuk")
    assert facturen.scan(db, ronde_id, AH_DOOS)["status"] == "toegevoegd"
    assert facturen.scan(db, ronde_id, AH_DOOS)["status"] == "toegevoegd"  # tweede doos
    assert facturen.scan(db, ronde_id, AH_ZAK)["status"] == "toegevoegd"  # plus een losse zak
    gegevens = facturen.ronde(db, ronde_id)
    assert gegevens["scans"] == 3 and len(gegevens["regels"]) == 2
    assert gegevens["per_product"][0]["eenheden"] == 2 * 80 + 20 and gegevens["totaal"] == 180.0

    samenvatting, fout = facturen.afronden(db, ronde_id, door="Luuk")
    assert fout is None and samenvatting["eenheden"] == 180
    assert _voorraad(db, pid) == 190
    mutatie = db.execute("SELECT type, aantal, opmerking, naam FROM mutaties WHERE product_id = ?", (pid,)).fetchone()
    assert (mutatie["type"], mutatie["aantal"], mutatie["naam"]) == ("in", 180, "Luuk")
    assert mutatie["opmerking"] == "Factuur F-1001 ingeboekt"

    # Afgerond is afgerond: niet nog eens, en er kan niets meer bij.
    assert facturen.afronden(db, ronde_id)[1] and _voorraad(db, pid) == 190
    assert facturen.scan(db, ronde_id, AH_DOOS)["status"] == "gesloten"


def test_onbekend_ongeldig_en_niets_gescand(db):
    _frikandel(db)
    ronde_id = facturen.start_ronde(db)
    assert facturen.scan(db, ronde_id, PLUS_ZAK)["status"] == "onbekend"
    assert facturen.scan(db, ronde_id, "4006381333932")["status"] == "ongeldig"
    assert facturen.afronden(db, ronde_id)[1] == "Er is nog niets gescand."


def test_aantal_aanpassen_handmatig_en_annuleren(db):
    pid = _frikandel(db)
    ronde_id = facturen.start_ronde(db)
    regel_id = facturen.scan(db, ronde_id, AH_DOOS)["regel_id"]
    facturen.scan(db, ronde_id, AH_DOOS)
    assert facturen.zet_aantal(db, ronde_id, regel_id, 1) is None
    assert facturen.voeg_handmatig_toe(db, ronde_id, pid, 5, "4,50") is None
    gegevens = facturen.ronde(db, ronde_id)
    assert gegevens["per_product"][0]["eenheden"] == 85 and gegevens["totaal"] == 84.5
    assert facturen.zet_aantal(db, ronde_id, regel_id, 0) is None
    assert len(facturen.ronde(db, ronde_id)["regels"]) == 1
    facturen.annuleren(db, ronde_id)
    assert facturen.ronde(db, ronde_id)["ronde"]["status"] == "geannuleerd" and _voorraad(db, pid) == 10


def test_factuurbedrag_naast_het_gescande_totaal(db):
    _frikandel(db)
    ronde_id = facturen.start_ronde(db)
    facturen.scan(db, ronde_id, AH_DOOS)
    facturen.werk_gegevens_bij(db, ronde_id, {"factuurbedrag": "82,50", "factuurnummer": " F-7 "})
    gegevens = facturen.ronde(db, ronde_id)
    assert gegevens["ronde"]["factuurnummer"] == "F-7" and gegevens["verschil"] == -2.5


def test_bestelling_komt_op_ontvangen_met_manco(db):
    frikandel = _frikandel(db)
    kroket = _product(db, "Kroket")
    b = db.execute("INSERT INTO bestellingen (status, aangemaakt_op) VALUES ('besteld', '2026-10-15 10:00')").lastrowid
    db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, 80)", (b, frikandel))
    db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, 24)", (b, kroket))
    db.commit()
    ronde_id = facturen.start_ronde(db, bestelling_id=b)
    facturen.scan(db, ronde_id, AH_DOOS)
    samenvatting, _ = facturen.afronden(db, ronde_id)
    assert samenvatting["bestelling_id"] == b and samenvatting["manco"] == 1
    assert db.execute("SELECT status FROM bestellingen WHERE id = ?", (b,)).fetchone()[0] == "ontvangen"
    regels = {r["product_id"]: (r["aantal_ontvangen"], r["manco"]) for r in db.execute(
        "SELECT * FROM bestelregels WHERE bestelling_id = ?", (b,))}
    assert regels == {frikandel: (80, 0), kroket: (0, 1)}
    assert _voorraad(db, frikandel) == 90 and _voorraad(db, kroket) == 10
    assert db.execute("SELECT bestelling_id FROM mutaties WHERE product_id = ?", (frikandel,)).fetchone()[0] == b


# ---------- In de browser ----------


def test_inboeken_in_de_browser(ingelogde_client, db):
    pid = _frikandel(db)
    assert "Nieuwe factuur" in ingelogde_client.get("/facturen").data.decode()
    resp = ingelogde_client.post("/facturen/nieuw", data={"csrf_token": _csrf(ingelogde_client), "factuurnummer": "F-9"})
    ronde_url = resp.headers["Location"]
    ronde_id = int(ronde_url.rstrip("/").split("/")[-1])
    ingelogde_client.post(f"/facturen/{ronde_id}/scan", data={"csrf_token": _csrf(ingelogde_client), "code": AH_DOOS})
    tekst = ingelogde_client.get(ronde_url).data.decode()
    assert "Factuur F-9" in tekst and "+80" in tekst and "Afronden en inboeken" in tekst

    regel_id = facturen.ronde(db, ronde_id)["regels"][0]["id"]
    ingelogde_client.post(f"/facturen/{ronde_id}/regels/{regel_id}", data={
        "csrf_token": _csrf(ingelogde_client), "aantal": "1", "weg": "1"})
    assert facturen.ronde(db, ronde_id)["regels"] == []

    ingelogde_client.post(f"/facturen/{ronde_id}/scan", data={"csrf_token": _csrf(ingelogde_client), "code": AH_DOOS})
    ingelogde_client.post(f"/facturen/{ronde_id}/afronden", data={"csrf_token": _csrf(ingelogde_client)})
    assert _voorraad(db, pid) == 90
    assert "ingeboekt" in ingelogde_client.get(ronde_url).data.decode()


def test_onbekende_barcode_koppelen_en_meteen_meetellen(ingelogde_client, db):
    pid = _frikandel(db)
    ronde_id = facturen.start_ronde(db)
    resp = ingelogde_client.post(f"/facturen/{ronde_id}/scan", data={"csrf_token": _csrf(ingelogde_client), "code": PLUS_ZAK})
    assert f"onbekend={PLUS_ZAK}" in resp.headers["Location"]
    tekst = ingelogde_client.get(resp.headers["Location"]).data.decode()
    assert "Onbekende barcode" in tekst and f"ronde_id={ronde_id}" in tekst

    # Als nieuw artikel: na het opslaan telt de scan meteen mee en ben je terug in de ronde.
    resp = ingelogde_client.post("/barcodes/nieuw", data={
        "csrf_token": _csrf(ingelogde_client), "product_id": pid, "naam": "Plus frikandellen", "ean": PLUS_ZAK,
        "aantal_per_verpakking": "15", "inkoopprijs": "18", "terug": "ronde", "ronde_id": str(ronde_id), "zoekcode": PLUS_ZAK,
    })
    assert resp.headers["Location"].endswith(f"/facturen/{ronde_id}")
    assert facturen.ronde(db, ronde_id)["per_product"][0]["eenheden"] == 15

    # Als doos van een bekend artikel.
    plus_doos = _ean("1" + PLUS_ZAK[:12])
    ingelogde_client.post("/barcodes/doos", data={
        "csrf_token": _csrf(ingelogde_client), "code": plus_doos, "per_omverpakking": "6", "ronde_id": str(ronde_id),
        "artikel_id": str(db.execute("SELECT id FROM artikelen WHERE ean = ?", (PLUS_ZAK,)).fetchone()[0]),
    })
    assert facturen.ronde(db, ronde_id)["per_product"][0]["eenheden"] == 15 + 6 * 15


def test_product_met_een_inboekronde_kun_je_niet_verwijderen(ingelogde_client, db):
    pid = _frikandel(db)
    facturen.scan(db, facturen.start_ronde(db), AH_DOOS)
    assert f"/producten/{pid}/archiveren" in ingelogde_client.get("/producten").data.decode()


# ---------- Voor de app (JSON) ----------


def test_de_app_boekt_een_factuur_in(ingelogde_client, db):
    pid = _frikandel(db)
    kop = {"X-CSRF-Token": _csrf(ingelogde_client)}
    start = ingelogde_client.get("/api/facturen").get_json()
    assert start["open"] == [] and any(p["id"] == pid for p in start["producten"])

    resp = ingelogde_client.post("/api/facturen", json={"factuurnummer": "APP-1"}, headers=kop)
    assert resp.status_code == 201
    ronde_id = resp.get_json()["id"]

    scan = ingelogde_client.post(f"/api/facturen/{ronde_id}/scan", json={"code": AH_DOOS}, headers=kop).get_json()
    assert scan["status"] == "toegevoegd" and scan["barcode"]["aantal"] == 80 and scan["ronde"]["scans"] == 1

    onbekend = ingelogde_client.post(f"/api/facturen/{ronde_id}/scan", json={"code": PLUS_ZAK}, headers=kop).get_json()
    assert onbekend["status"] == "onbekend"
    gekoppeld = ingelogde_client.post(f"/api/facturen/{ronde_id}/koppelen", json={
        "code": PLUS_ZAK, "soort": "artikel", "product_id": pid, "naam": "Plus frikandellen",
        "aantal_per_verpakking": 15, "inkoopprijs": 18,
    }, headers=kop).get_json()
    assert gekoppeld["status"] == "toegevoegd" and gekoppeld["ronde"]["scans"] == 2

    regel_id = scan["regel_id"]
    ronde = ingelogde_client.post(f"/api/facturen/{ronde_id}/regels/{regel_id}", json={"aantal": 2}, headers=kop).get_json()
    assert ronde["per_product"][0]["eenheden"] == 2 * 80 + 15

    klaar = ingelogde_client.post(f"/api/facturen/{ronde_id}/afronden", json={}, headers=kop).get_json()
    assert klaar["status"] == "afgerond" and _voorraad(db, pid) == 10 + 175
    assert db.execute("SELECT bron FROM inboekrondes WHERE id = ?", (ronde_id,)).fetchone()[0] == "app"


def test_de_app_zonder_csrf_token(ingelogde_client, db):
    resp = ingelogde_client.post("/api/facturen", json={})
    assert resp.status_code == 400 and resp.get_json()["fout"] == "csrf"
    assert db.execute("SELECT COUNT(*) FROM inboekrondes").fetchone()[0] == 0


def test_de_app_niet_ingelogd_en_zonder_voorraad_sectie(app, db):
    anoniem = app.test_client()
    resp = anoniem.get("/api/facturen")
    assert resp.status_code == 401 and resp.get_json()["fout"] == "niet_ingelogd"

    kassa = app.test_client()
    _maak_vrijwilliger(db, "kassahulp", "kassa")
    _login(kassa, "kassahulp")
    resp = kassa.get("/api/facturen")
    assert resp.status_code == 403 and resp.get_json()["fout"] == "geen_toegang"


def test_de_app_logt_in_met_de_code_en_boekt_in(app, db):
    """Zoals de app het straks doet: inloggen met de 6-cijferige code van een account, en daarna met het csrf_token
    uit dat antwoord in de header scannen en afronden."""
    pid = _frikandel(db)
    db.execute("DELETE FROM gebruikers WHERE naam != 'admin'")  # alleen de beheerder heeft code 999999
    db.commit()
    app_client = app.test_client()
    login = app_client.post("/api/tablet-code/inloggen", json={"code": "999999"}).get_json()
    assert login["geldig"] and login["csrf_token"]
    kop = {"X-CSRF-Token": login["csrf_token"]}
    ronde_id = app_client.post("/api/facturen", json={}, headers=kop).get_json()["id"]
    app_client.post(f"/api/facturen/{ronde_id}/scan", json={"code": AH_DOOS}, headers=kop)
    assert app_client.post(f"/api/facturen/{ronde_id}/afronden", json={}, headers=kop).get_json()["status"] == "afgerond"
    assert _voorraad(db, pid) == 90
