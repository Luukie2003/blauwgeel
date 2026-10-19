"""Een klaargezette bestelling is het concept van de factuur (facturen.ronde_voor_bestelling): inscannen met wat er
besteld is ernaast, 'zoals besteld' voor wat zonder barcode binnenkomt, en wat extra meekomt. Plus de prognose bij de
bestellijst (helpers.producten.bestel_advies) en een nieuw product aanmaken vanaf de handterminal."""

from datetime import datetime, timedelta

from conftest import stel_csrf_token_in as _csrf
from test_app_api_meer import _vrijwilliger
from test_barcodes import _artikel, _ean, _product
from test_voorspelling import _bouw_geschiedenis

import facturen

CHAUD_FLES, CHAUD_TRAY = _ean("540000000011"), _ean("540000000012")
COLA_TRAY = _ean("540000000013")
NIEUW = _ean("871000000095")


def _voorraad(db, pid):
    return db.execute("SELECT voorraad FROM producten WHERE id = ?", (pid,)).fetchone()[0]


def _tray(db, naam, per=24, inkoop=12.0, leverancier_id=None):
    """Een product dat per tray van 24 besteld wordt (de inkoopprijs staat per tray)."""
    pid = _product(db, naam, eenheid="Fles", categorie="Fris")
    db.execute("UPDATE producten SET besteleenheid = 'Tray', besteleenheid_factor = ?, inkoopprijs = ?, leverancier_id = ?"
               " WHERE id = ?", (per, inkoop, leverancier_id, pid))
    db.commit()
    return pid


def _bestelling(db, regels, referentie=None):
    b = db.execute("INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, referentie) VALUES ('besteld', ?, 'Luuk', ?)",
                   ("2026-10-19 10:00", referentie)).lastrowid
    for pid, aantal in regels:
        db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, ?)", (b, pid, aantal))
    db.commit()
    return b


def _levering(db):
    """Chaudfontaine (2 trays besteld, met barcodes) en Coca Cola (1 tray besteld, met de barcode van de tray)."""
    lev = db.execute("INSERT INTO leveranciers (naam, actief, aangemaakt_op) VALUES ('Sligro', 1, '2026-10-01 10:00')").lastrowid
    chaud, cola = _tray(db, "Chaudfontaine", leverancier_id=lev), _tray(db, "Coca Cola", leverancier_id=lev)
    _artikel(db, chaud, "Chaudfontaine 50cl", CHAUD_FLES, prijs=0.5, doos=CHAUD_TRAY, per_doos=24)
    _artikel(db, cola, "Coca Cola 50cl", None, prijs=0.8, doos=COLA_TRAY, per_doos=24)
    return lev, chaud, cola, _bestelling(db, [(chaud, 48), (cola, 24)], referentie="Sligro week 43")


# ---------- De bestelling als concept van de factuur ----------


def test_inboeken_begint_een_ronde_of_gaat_verder_met_de_open(db):
    lev, chaud, cola, b = _levering(db)
    ronde_id = facturen.ronde_voor_bestelling(db, b, door="Luuk")
    assert facturen.ronde_voor_bestelling(db, b, door="Piet") == ronde_id  # nooit twee open rondes per bestelling
    ronde = facturen.ronde(db, ronde_id)
    assert ronde["ronde"]["leverancier_id"] == lev  # alle producten komen van Sligro
    assert [(x["naam"], x["besteld_eenheden"], x["besteleenheid"], x["status"]) for x in ronde["besteld"]] == [
        ("Chaudfontaine", 2, "Tray", "nog_niet"), ("Coca Cola", 1, "Tray", "nog_niet")]
    [concept] = facturen.open_bestellingen(db)
    assert concept["ronde_id"] == ronde_id and concept["producten"] == 2
    assert concept["samenvatting"] == "2 Tray Chaudfontaine, 1 Tray Coca Cola"

    facturen.annuleren(db, ronde_id)
    assert facturen.ronde_voor_bestelling(db, b) != ronde_id  # een geannuleerde ronde: opnieuw beginnen
    assert facturen.ronde_voor_bestelling(db, 999) is None


def test_besteld_naast_gescand_en_zoals_besteld(db):
    _, chaud, cola, b = _levering(db)
    ronde_id = facturen.ronde_voor_bestelling(db, b)
    facturen.scan(db, ronde_id, CHAUD_TRAY)
    besteld = {x["naam"]: x for x in facturen.ronde(db, ronde_id)["besteld"]}
    assert (besteld["Chaudfontaine"]["gescand"], besteld["Chaudfontaine"]["rest"], besteld["Chaudfontaine"]["status"]) == (24, 24, "deels")

    # De cola komt zonder dat je de tray scant: erbij zoals besteld, met de inkoopprijs (die van het artikel: 0,80 per
    # fles, dus 19,20 per tray).
    assert facturen.voeg_rest_toe(db, ronde_id, cola) == (1, None)
    besteld = {x["naam"]: x for x in facturen.ronde(db, ronde_id)["besteld"]}
    assert besteld["Coca Cola"]["status"] == "binnen" and besteld["Chaudfontaine"]["status"] == "deels"
    regel = db.execute("SELECT * FROM inboekronde_regels WHERE ronde_id = ? AND product_id = ?", (ronde_id, cola)).fetchone()
    assert (regel["niveau"], regel["eenheden_per_stuk"], regel["prijs_per_stuk"]) == ("handmatig", 24, 19.2)
    assert facturen.voeg_rest_toe(db, ronde_id, cola)[1] == "Daar mist niets meer van: alles is al gescand."

    # De rest van alles in één keer.
    assert facturen.voeg_rest_toe(db, ronde_id) == (1, None)
    assert all(x["status"] == "binnen" for x in facturen.ronde(db, ronde_id)["besteld"])

    zonder = facturen.start_ronde(db)
    assert facturen.voeg_rest_toe(db, zonder)[1] == "Deze factuur hoort niet bij een klaargezette bestelling."


def test_afronden_met_iets_extra_en_iets_dat_niet_kwam(db):
    _, chaud, cola, b = _levering(db)
    extra = _tray(db, "Fanta")
    _artikel(db, extra, "Fanta 50cl", None, doos=NIEUW, per_doos=24)
    ronde_id = facturen.ronde_voor_bestelling(db, b)
    for code in (CHAUD_TRAY, CHAUD_TRAY, NIEUW):  # de cola kwam niet, de Fanta was niet besteld
        facturen.scan(db, ronde_id, code)
    per_product = {p["naam"]: p for p in facturen.ronde(db, ronde_id)["per_product"]}
    assert per_product["Chaudfontaine"]["besteld"] and not per_product["Fanta"]["besteld"]

    samenvatting, fout = facturen.afronden(db, ronde_id, door="Luuk")
    assert fout is None and samenvatting["manco"] == 1 and samenvatting["bestelling_id"] == b
    regels = {r["product_id"]: r for r in db.execute("SELECT * FROM bestelregels WHERE bestelling_id = ?", (b,))}
    assert (regels[chaud]["aantal_ontvangen"], regels[cola]["manco"]) == (48, 1)
    assert (regels[extra]["aantal_besteld"], regels[extra]["aantal_ontvangen"]) == (0, 24)  # extra meegekomen
    assert db.execute("SELECT bestelling_id FROM mutaties WHERE product_id = ?", (extra,)).fetchone()[0] == b
    assert _voorraad(db, extra) == 10 + 24 and _voorraad(db, chaud) == 10 + 48


# ---------- Op de site ----------


def test_inboeken_vanaf_de_bestellijst_gaat_naar_de_factuur(ingelogde_client, db):
    _, chaud, cola, b = _levering(db)
    lijst = ingelogde_client.get("/bestellijst").data.decode()
    assert f"/facturen/bestelling/{b}" in lijst
    resp = ingelogde_client.get(f"/facturen/bestelling/{b}")
    ronde_id = db.execute("SELECT id FROM inboekrondes WHERE bestelling_id = ?", (b,)).fetchone()[0]
    assert resp.headers["Location"].endswith(f"/facturen/{ronde_id}")
    # Het oude inboekformulier stuurt een openstaande bestelling ook door naar de factuur.
    assert ingelogde_client.get(f"/bestellingen/{b}/inboeken").headers["Location"].endswith(f"/facturen/bestelling/{b}")

    pagina = ingelogde_client.get(f"/facturen/{ronde_id}").data.decode()
    assert "Besteld" in pagina and "+48 zoals besteld" in pagina and "Alles wat nog mist zoals besteld" in pagina
    ingelogde_client.post(f"/facturen/{ronde_id}/zoals-besteld", data={"csrf_token": _csrf(ingelogde_client), "product_id": chaud})
    pagina = ingelogde_client.get(f"/facturen/{ronde_id}").data.decode()
    assert "binnen</span>" in pagina and "+24 zoals besteld" in pagina

    ingelogde_client.post(f"/facturen/{ronde_id}/afronden", data={"csrf_token": _csrf(ingelogde_client)})
    # Een ontvangen bestelling kun je nog corrigeren met het gewone formulier.
    assert ingelogde_client.get(f"/bestellingen/{b}/inboeken").status_code == 200


def test_klaarzetten_zet_hem_als_concept_bij_factuur_inboeken(ingelogde_client, db):
    chaud = _tray(db, "Chaudfontaine")
    db.execute("UPDATE producten SET voorraad = 5, min_voorraad = 24 WHERE id = ?", (chaud,))
    db.commit()
    resp = ingelogde_client.post("/bestellijst/aanmaken", data={
        "csrf_token": _csrf(ingelogde_client), "product_id": str(chaud), f"aantal_{chaud}": "2"}, follow_redirects=True)
    assert "als concept bij Factuur inboeken" in resp.data.decode()
    overzicht = ingelogde_client.get("/facturen").data.decode()
    assert "Klaargezette bestellingen" in overzicht and "2 Tray Chaudfontaine" in overzicht


# ---------- In de app ----------


def test_de_app_boekt_een_klaargezette_bestelling_in(ingelogde_client, db):
    _, chaud, cola, b = _levering(db)
    kop = {"X-CSRF-Token": _csrf(ingelogde_client)}
    concept = ingelogde_client.get("/api/facturen").get_json()["bestellingen"][0]
    assert concept["id"] == b and concept["ronde_id"] is None and concept["referentie"] == "Sligro week 43"

    ronde = ingelogde_client.post(f"/api/facturen/bestelling/{b}", json={}, headers=kop).get_json()
    assert ingelogde_client.post(f"/api/facturen/bestelling/{b}", json={}, headers=kop).get_json()["id"] == ronde["id"]
    assert ronde["bestelling_id"] == b and ronde["bestelling_referentie"] == "Sligro week 43"
    assert [x["status"] for x in ronde["besteld"]] == ["nog_niet", "nog_niet"] and "inkoop_per_stuk" not in ronde["besteld"][0]

    ingelogde_client.post(f"/api/facturen/{ronde['id']}/scan", json={"code": CHAUD_TRAY, "verzoek_id": "s1"}, headers=kop)
    for _ in range(2):  # zelfde verzoek_id: maar één keer
        na = ingelogde_client.post(f"/api/facturen/{ronde['id']}/zoals-besteld", json={"verzoek_id": "z1"}, headers=kop).get_json()
    assert [x["status"] for x in na["besteld"]] == ["binnen", "binnen"] and na["scans"] == 3
    fout = ingelogde_client.post(f"/api/facturen/{ronde['id']}/zoals-besteld", json={"product_id": cola}, headers=kop)
    assert fout.status_code == 400
    assert ingelogde_client.post("/api/facturen/bestelling/999", json={}, headers=kop).status_code == 404


def test_een_nieuw_product_vanaf_de_handterminal(app, db):
    client = _vrijwilliger(app, db, "voorraadhulp", "voorraad")
    keuzes = client.get("/api/app/producten/nieuw").get_json()
    assert "Fles" in keuzes["eenheden"] and "Krat" in keuzes["besteleenheden"] and keuzes["categorieen"]
    categorie = keuzes["categorieen"][0]
    nieuw = {"naam": " Brand  Weizen ", "categorie": categorie, "eenheid": "Fles", "besteleenheid": "Krat",
             "per_besteleenheid": "24", "verkoopprijs": "2,50", "verzoek_id": "n1"}
    eerste = client.post("/api/app/producten/nieuw", json=nieuw, headers=client.kop).get_json()
    assert client.post("/api/app/producten/nieuw", json=nieuw, headers=client.kop).get_json() == eerste  # niet dubbel
    product = eerste["product"]
    assert (product["naam"], product["besteleenheid"], product["per_besteleenheid"], product["voorraad"]) == ("Brand Weizen", "Krat", 24, 0)
    rij = db.execute("SELECT categorie, verkoopprijs, actief FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert tuple(rij) == (categorie, 2.5, 1)
    assert "aangemaakt op de handterminal door voorraadhulp" in db.execute(
        "SELECT omschrijving FROM logboek WHERE endpoint = 'product_nieuw'").fetchone()[0]

    def fout(**anders):
        resp = client.post("/api/app/producten/nieuw", json={**nieuw, "verzoek_id": None, **anders}, headers=client.kop)
        return resp.status_code, resp.get_json()["melding"]

    assert fout(naam="brand weizen")[1].startswith("Er is al een product")
    assert fout(naam="Iets", eenheid="Emmer")[0] == 400
    assert fout(naam="Iets", per_besteleenheid="1")[0] == 400
    assert fout(naam="Iets", verkoopprijs="gratis")[0] == 400
    assert fout(naam="")[0] == 400

    kassa = _vrijwilliger(app, db, "kassahulp", "kassa")
    assert kassa.post("/api/app/producten/nieuw", json=nieuw, headers=kassa.kop).status_code == 403


# ---------- De prognose bij de bestellijst ----------


def _met_geschiedenis(db):
    """Chaudfontaine onder het minimum (6 per dag verkocht), Cola erboven maar hard op weg naar leeg (12 per dag)."""
    chaud, cola = _tray(db, "Chaudfontaine"), _tray(db, "Coca Cola")
    nu = datetime.now().replace(minute=0, second=0, microsecond=0)
    _bouw_geschiedenis(db, {chaud: 6, cola: 12}, tijdstippen=[nu - timedelta(days=7 * (6 - i), hours=2) for i in range(7)],
                       open_dagen="0,1,2,3,4,5,6")
    db.execute("UPDATE producten SET voorraad = 20, min_voorraad = 24 WHERE id = ?", (chaud,))
    db.execute("UPDATE producten SET voorraad = 40, min_voorraad = 24 WHERE id = ?", (cola,))
    db.commit()
    return chaud, cola


def test_prognose_bij_de_bestellijst(ingelogde_client, db):
    assert ingelogde_client.get("/bestellijst/prognose").get_json()["beschikbaar"] is False
    chaud, cola = _met_geschiedenis(db)
    advies = ingelogde_client.get("/bestellijst/prognose").get_json()
    x = advies["producten"][str(chaud)]
    assert advies["beschikbaar"] and x["verwacht"] > 30 and x["basis_eenheden"] == 1
    # Genoeg trays voor een drukke week (het 90%-punt), afgerond op hele trays: 20 op voorraad.
    assert x["advies_eenheden"] * 24 >= x["hoog"] - 20 > (x["advies_eenheden"] - 1) * 24
    [extra] = advies["extra"]
    assert extra["id"] == cola and extra["advies_eenheden"] >= 1 and extra["status"] == "urgent"
    assert extra["besteleenheid"] == "Tray" and extra["factor"] == 24

    pagina = ingelogde_client.get("/bestellijst").data.decode()
    assert "/bestellijst/prognose" in pagina and 'data-standaard="1"' in pagina and "Bestelling klaarzetten" in pagina


def test_prognose_in_de_app(app, db):
    chaud, cola = _met_geschiedenis(db)
    client = _vrijwilliger(app, db, "voorraadhulp", "voorraad")
    advies = client.get("/api/app/bestellijst/prognose").get_json()
    assert advies["producten"][str(chaud)]["advies_eenheden"] > advies["producten"][str(chaud)]["basis_eenheden"]
    assert advies["extra"][0]["id"] == cola and "afbeelding" not in advies["extra"][0] and "foto" in advies["extra"][0]


def test_een_artikel_toevoegen_vanaf_de_handterminal(app, db):
    pid = _tray(db, "Frikandel")
    lev = db.execute("INSERT INTO leveranciers (naam, actief, aangemaakt_op) VALUES ('AH', 1, '2026-10-01 10:00')").lastrowid
    db.commit()
    client = _vrijwilliger(app, db, "voorraadhulp", "voorraad")
    assert client.get(f"/api/app/producten/{pid}/artikelen").get_json()["leveranciers"] == [{"id": lev, "naam": "AH"}]
    zak, doos = _ean("871000000201"), _ean("871000000202")
    artikel = {"naam": "AH frikandellen", "merk": "AH", "ean": zak, "aantal_per_verpakking": "20", "inkoopprijs": "4,50",
               "ean_omverpakking": doos, "per_omverpakking": "6", "leverancier_id": lev, "verzoek_id": "a1"}
    antwoord = client.post(f"/api/app/producten/{pid}/artikelen", json=artikel, headers=client.kop).get_json()
    assert client.post(f"/api/app/producten/{pid}/artikelen", json=artikel, headers=client.kop).get_json() == antwoord
    codes = {b["code"]: b["aantal"] for b in antwoord["product"]["barcodes"]}
    assert codes == {zak: 20, doos: 120}
    rij = db.execute("SELECT inkoopprijs, leverancier_id, merk FROM artikelen WHERE ean = ?", (zak,)).fetchone()
    assert tuple(rij) == (4.5, lev, "AH")

    # Dezelfde controles als op de site: een bezette barcode, geen naam, een doos zonder aantal.
    for anders in ({"naam": "Ander", "ean": zak}, {"naam": ""}, {"naam": "X", "ean": "", "ean_omverpakking": _ean("871000000203"),
                                                                 "per_omverpakking": ""}):
        resp = client.post(f"/api/app/producten/{pid}/artikelen", json={**artikel, "verzoek_id": None, "ean_omverpakking": "",
                                                                        **anders}, headers=client.kop)
        assert resp.status_code == 400 and resp.get_json()["melding"], anders
    assert client.post("/api/app/producten/999/artikelen", json=artikel, headers=client.kop).status_code == 404
