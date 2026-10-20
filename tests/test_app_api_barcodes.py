"""Barcodes aanpassen en de koppelronde in de handterminal-app (routes/app_api_barcodes.py)."""

from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_app_api_meer import _vrijwilliger
from test_barcodes import AH_DOOS, AH_ZAK, PLUS_ZAK, _artikel, _ean, _product

COLA = _ean("871200000101")


def _artikel_rij(db, artikel_id):
    return db.execute("SELECT * FROM artikelen WHERE id = ?", (artikel_id,)).fetchone()


# ---------- Een artikel aanpassen ----------


def test_barcode_van_een_artikel_aanpassen(app_client, db):  # noqa: F811
    pid = _product(db, "Frikandel")
    aid = _artikel(db, pid, "AH frikandellen", AH_ZAK, aantal=20, prijs=20, doos=AH_DOOS, per_doos=4)
    info = app_client.get(f"/api/app/producten/{pid}").get_json()["info"]
    assert info["artikelen"][0]["id"] == aid

    data = app_client.get(f"/api/app/artikelen/{aid}").get_json()
    assert data["artikel"]["ean"] == AH_ZAK and data["artikel"]["per_doos"] == 4 and "leveranciers" in data

    # Alleen de barcode: de rest blijft zoals het was.
    resp = _post(app_client, f"/api/app/artikelen/{aid}", ean=PLUS_ZAK)
    assert resp.status_code == 200, resp.get_json()
    rij = _artikel_rij(db, aid)
    assert rij["ean"] == PLUS_ZAK and rij["aantal_per_verpakking"] == 20 and rij["ean_omverpakking"] == AH_DOOS
    assert any(b["code"] == PLUS_ZAK for b in resp.get_json()["product"]["barcodes"])

    # Een leeg veld haalt de doos weg (en het aantal in de doos ook).
    _post(app_client, f"/api/app/artikelen/{aid}", ean_omverpakking="")
    rij = _artikel_rij(db, aid)
    assert rij["ean_omverpakking"] is None and rij["per_omverpakking"] == 0


def test_aanpassen_met_dezelfde_controles_als_de_site(app_client, db):  # noqa: F811
    pid = _product(db, "Frikandel")
    a1 = _artikel(db, pid, "AH frikandellen", AH_ZAK)
    a2 = _artikel(db, pid, "Plus frikandellen", PLUS_ZAK)
    resp = _post(app_client, f"/api/app/artikelen/{a2}", ean=AH_ZAK)
    assert resp.status_code == 400 and "hoort al bij" in resp.get_json()["melding"]
    assert _post(app_client, f"/api/app/artikelen/{a2}", ean="1234").status_code == 400
    assert _post(app_client, "/api/app/artikelen/9999", ean=COLA).status_code == 404

    resp = _post(app_client, f"/api/app/artikelen/{a1}/verwijderen")
    assert resp.status_code == 200 and _artikel_rij(db, a1) is None


# ---------- De koppelronde ----------


def test_koppelronde(app_client, db):  # noqa: F811
    db.execute("UPDATE producten SET actief = 0")  # alleen de producten van deze test
    cola = _product(db, "Cola", categorie="Fris")
    bier = _product(db, "Tapbier", eenheid="glazen", categorie="Bier")
    friet = _product(db, "Frikandel")
    _artikel(db, friet, "AH frikandellen", AH_ZAK)
    # Alleen een doos-barcode telt niet: de losse verpakking moet nog.
    _artikel(db, bier, "Fust", None, doos=AH_DOOS, per_doos=50)

    ronde = app_client.get("/api/app/koppelronde").get_json()
    assert [p["naam"] for p in ronde["te_doen"]] == ["Tapbier", "Cola"]  # op categorie
    assert ronde["gekoppeld"] == 1 and ronde["totaal"] == 3

    # Koppelen gaat via het bestaande endpoint.
    resp = _post(app_client, "/api/app/barcodes/koppelen", code=COLA, product_id=cola, verzoek_id="k1")
    assert resp.status_code == 200
    ronde = app_client.get("/api/app/koppelronde").get_json()
    assert [p["naam"] for p in ronde["te_doen"]] == ["Tapbier"] and ronde["gekoppeld"] == 2

    # Tapbier heeft geen barcode.
    ronde = _post(app_client, "/api/app/koppelronde/geen-barcode", product_id=bier, geen=True).get_json()
    assert ronde["te_doen"] == [] and ronde["geen_barcode"][0]["naam"] == "Tapbier"
    ronde = _post(app_client, "/api/app/koppelronde/geen-barcode", product_id=bier, geen=False).get_json()
    assert [p["naam"] for p in ronde["te_doen"]] == ["Tapbier"]

    # Ongedaan maken: het artikel was alleen voor die barcode, dus het gaat helemaal weg.
    resp = _post(app_client, "/api/app/koppelronde/ongedaan", code=COLA, verzoek_id="o1")
    assert resp.status_code == 200 and "weer los" in resp.get_json()["melding"]
    assert db.execute("SELECT COUNT(*) FROM artikelen WHERE product_id = ?", (cola,)).fetchone()[0] == 0
    assert _post(app_client, "/api/app/koppelronde/ongedaan", code=COLA).status_code == 404


def test_ongedaan_laat_een_ingevuld_artikel_staan(app_client, db):  # noqa: F811
    pid = _product(db, "Frikandel")
    aid = _artikel(db, pid, "AH frikandellen", AH_ZAK, aantal=20, prijs=20)
    _post(app_client, "/api/app/koppelronde/ongedaan", code=AH_ZAK)
    rij = _artikel_rij(db, aid)
    assert rij is not None and rij["ean"] is None and rij["inkoopprijs"] == 20


def test_alleen_met_voorraadrechten(app, db):
    client = _vrijwilliger(app, db, "keukenhulp", "keuken")
    assert client.get("/api/app/koppelronde").status_code == 403
    assert client.post("/api/app/artikelen/1", json={"ean": ""}, headers=client.kop).status_code == 403
