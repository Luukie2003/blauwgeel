"""Het bestelvoorstel (bestelvoorstel.py): het uiterste bestelmoment per leverancier (1.68.0), bij het product zelf het
aantal colli kiezen (1.69.0, site en handterminal), en producten scannen op de bestellijst (1.69.0)."""

from datetime import datetime

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_barcodes import AH_DOOS, AH_ZAK, _artikel

import bestelvoorstel
from helpers.producten import bestel_advies


def _lev(besteldagen="1,3", voor="16:00", levertijd=1):
    return {"naam": "Sligro", "besteldagen": besteldagen, "bestellen_voor": voor, "levertijd_dagen": levertijd}


def _product(db, naam, voorraad=10, minimum=0, factor=1, besteleenheid=None):
    pid = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, inkoopprijs, actief,
                                  besteleenheid, besteleenheid_factor) VALUES (?, 'Fris', 'stuks', ?, ?, 2.0, 1.0, 1, ?, ?)""",
        (naam, voorraad, minimum, besteleenheid, factor),
    ).lastrowid
    db.commit()
    return pid


@pytest.fixture
def prognose(monkeypatch):
    """Een vaste prognose in plaats van het voorspelmodel: {product_id: (verwacht, hoog)}; wat er niet in staat, heeft
    (nog) geen verkoop."""
    vast = {}

    def nep(db, dagen_set, nu=None):
        return {d: {pid: {"verwacht": v, "hoog": h, "kans_tekort": 0.0, "status": "ok", "advies_stuks": 0}
                    for pid, (v, h) in vast.items()} for d in set(dagen_set)}

    monkeypatch.setattr(bestelvoorstel, "prognoses", nep)
    return vast


def test_uiterste_bestelmoment_en_de_periode_tot_de_levering_daarna():
    # Vrijdag 23-10: eerstvolgende besteldag is dinsdag vóór 16:00, levering woensdag; de bestelling erna (donderdag)
    # komt vrijdag 30-10. Tot dan moet de voorraad het houden.
    p = bestelvoorstel.bestelperiode(_lev(), datetime(2026, 10, 23, 10, 0))
    assert p["uiterst"] == datetime(2026, 10, 27, 16, 0)
    assert p["levering"].isoformat() == "2026-10-28" and p["volgende_levering"].isoformat() == "2026-10-30"
    assert p["dagen"] == 7
    assert bestelvoorstel.dag_tekst(p["uiterst"], met_tijd=True) == "di 27-10 16:00"
    # Op de besteldag zelf: vóór de tijd nog vandaag, erna de volgende besteldag.
    assert bestelvoorstel.bestelperiode(_lev(), datetime(2026, 10, 27, 15, 0))["uiterst"] == datetime(2026, 10, 27, 16, 0)
    assert bestelvoorstel.bestelperiode(_lev(), datetime(2026, 10, 27, 17, 0))["uiterst"] == datetime(2026, 10, 29, 16, 0)
    # Zonder besteldagen: geen periode (dan de standaard 7 dagen).
    assert bestelvoorstel.bestelperiode(_lev(besteldagen=""), datetime(2026, 10, 23)) is None


def test_bijstelling_telt_op_bij_de_prognose_in_hele_besteleenheden():
    product = {"voorraad": 0, "min_voorraad": 0, "besteleenheid": "tray", "besteleenheid_factor": 24, "eenheid": "stuks"}
    a = bestelvoorstel.advies(product, None, bijstelling=6)
    assert (a["met_bijstelling"], a["advies_eenheden"], a["advies_stuks"]) == (6, 1, 24)
    a = bestelvoorstel.advies(product, {"verwacht": 20, "hoog": 30}, bijstelling=-30)
    assert a["advies_eenheden"] == 0 and a["met_bijstelling"] == 0


def test_prognose_nul_bijgesteld_komt_bij_voorgesteld(db, prognose):
    pid = _product(db, "Ranja Toernooi", voorraad=4)
    assert all(e["id"] != pid for e in bestel_advies(db)["extra"])
    bestelvoorstel.zet_bijstelling(db, pid, 10, "Luuk")
    extra = {e["id"]: e for e in bestel_advies(db)["extra"]}
    assert extra[pid]["status"] == "bijgesteld" and extra[pid]["bijstelling"] == 10
    assert extra[pid]["advies_eenheden"] == 6 and extra[pid]["bijgesteld_door"] == "Luuk"


def test_omlaag_bijgesteld_mag_onder_het_gewone_voorstel(db, prognose):
    pid = _product(db, "Cola Omlaag", voorraad=2, minimum=10)
    prognose[pid] = (20, 30)
    assert bestel_advies(db)["producten"][pid]["advies_eenheden"] == 28
    bestelvoorstel.zet_bijstelling(db, pid, -25)
    regel = bestel_advies(db)["producten"][pid]
    assert regel["advies_eenheden"] == 8 and regel["bijstelling"] == -25


def test_app_stelt_bij_en_krijgt_het_nieuwe_blok(app_client, db, prognose):  # noqa: F811
    pid = _product(db, "Chips App", voorraad=0, factor=12, besteleenheid="doos")
    resp = _post(app_client, f"/api/app/producten/{pid}/bijstelling", stuks=12)
    blok = resp.get_json()["bestellen"]
    assert resp.status_code == 200 and blok["bijstelling"] == 12 and blok["advies_eenheden"] == 1
    assert "Prognose +12" in resp.get_json()["melding"]
    assert _post(app_client, f"/api/app/producten/{pid}/bijstelling", stuks="veel").status_code == 400
    assert _post(app_client, f"/api/app/producten/{pid}/bijstelling", stuks=0).get_json()["bestellen"]["bijstelling"] == 0
    assert bestelvoorstel.bijstellingen(db) == {}


def test_site_kiest_het_aantal_colli_en_bestellen_wist_het(ingelogde_client, db, prognose):
    pid = _product(db, "Sinas Site", voorraad=0, factor=24, besteleenheid="tray")
    prognose[pid] = (10, 15)
    pagina = ingelogde_client.get(f"/producten/{pid}/verkoop").data.decode()
    assert 'name="aantal" value="1"' in pagina and "Kies met min en plus" in pagina  # het advies: 1 tray
    resp = ingelogde_client.post(f"/producten/{pid}/bestellen", data={"csrf_token": _csrf(ingelogde_client), "eenheden": "3"})
    assert resp.status_code == 302 and resp.location.endswith(f"/producten/{pid}#verkoop")
    assert bestelvoorstel.bijstellingen(db)[pid]["eenheden"] == 3
    pagina = ingelogde_client.get(f"/producten/{pid}/verkoop").data.decode()
    assert 'name="aantal" value="3"' in pagina and "terug naar het advies" in pagina and "(72 stuks)" in pagina
    # Enter in het invulvak: een lege 'eenheden', dus het getal uit 'aantal'.
    ingelogde_client.post(f"/producten/{pid}/bestellen", data={"csrf_token": _csrf(ingelogde_client), "eenheden": "", "aantal": "5"})
    assert bestelvoorstel.bijstellingen(db)[pid]["eenheden"] == 5
    ingelogde_client.post("/bestellijst/aanmaken", data={"csrf_token": _csrf(ingelogde_client), "product_id": [pid], f"aantal_{pid}": "5"})
    assert pid not in bestelvoorstel.bijstellingen(db)


def test_terug_naar_het_advies(ingelogde_client, db, prognose):
    pid = _product(db, "Ranja Advies")
    bestelvoorstel.zet_bestelaantal(db, pid, 2)
    ingelogde_client.post(f"/producten/{pid}/bestellen", data={"csrf_token": _csrf(ingelogde_client), "eenheden": "advies"})
    assert bestelvoorstel.bijstellingen(db) == {}


def test_app_kiest_het_aantal_colli(app_client, db, prognose):  # noqa: F811
    pid = _product(db, "Chips Colli", voorraad=0, factor=12, besteleenheid="doos")
    prognose[pid] = (5, 8)
    resp = _post(app_client, f"/api/app/producten/{pid}/bestelaantal", eenheden=4)
    blok = resp.get_json()["bestellen"]
    assert resp.status_code == 200 and blok["gekozen"] == 4 and blok["bestellen_eenheden"] == 4 and blok["advies_eenheden"] == 1
    assert resp.get_json()["melding"] == "Chips Colli: 4 doos bestellen."
    assert _post(app_client, f"/api/app/producten/{pid}/bestelaantal", eenheden=-1).status_code == 400
    assert _post(app_client, f"/api/app/producten/{pid}/bestelaantal", eenheden="veel").status_code == 400
    blok = _post(app_client, f"/api/app/producten/{pid}/bestelaantal", eenheden=None).get_json()["bestellen"]
    assert blok["gekozen"] is None and blok["bestellen_eenheden"] == 1


def test_gekozen_aantal_staat_meteen_op_de_bestellijst(ingelogde_client, app_client, db, prognose):  # noqa: F811
    boven = _product(db, "Cola Boven", voorraad=50, minimum=10, factor=24, besteleenheid="tray")
    laag = _product(db, "Bier Laag", voorraad=0, minimum=10)
    bestelvoorstel.zet_bestelaantal(db, boven, 3, "Luuk")
    bestelvoorstel.zet_bestelaantal(db, laag, 0, "Luuk")

    pagina = ingelogde_client.get("/bestellijst").data.decode()
    assert f'name="aantal_{boven}"' in pagina and "zelf gekozen (Luuk)" in pagina and "niet bestellen (Luuk)" in pagina
    rij_laag = pagina[pagina.index(f'value="{laag}"') - 60:pagina.index(f'value="{laag}"') + 120]
    assert "checked" not in rij_laag

    advies = bestel_advies(db)
    assert advies["producten"][boven]["gekozen"] == 3 and all(e["id"] != boven for e in advies["extra"])

    lijst = app_client.get("/api/app/bestellijst").get_json()
    assert [p["id"] for p in lijst["gekozen"]] == [boven] and lijst["gekozen"][0]["gekozen"] == 3
    assert next(p for p in lijst["bestellen"] if p["id"] == laag)["gekozen"] == 0


def test_scannen_op_de_bestellijst(ingelogde_client, db):
    pid = _product(db, "Frikandel Scan", voorraad=3, factor=40, besteleenheid="doos")
    _artikel(db, pid, "AH frikandellen", ean=AH_ZAK, aantal=20, doos=AH_DOOS, per_doos=2)
    _product(db, "Cola Zoek")
    _product(db, "Cola Zero Zoek")
    bestelvoorstel.zet_bestelaantal(db, pid, 2)

    def zoek(q):
        return ingelogde_client.get("/bestellijst/zoek", query_string={"q": q}).get_json()

    for code in (AH_ZAK, AH_DOOS, f"https://www.kantineblauwgeel.nl/scan/{pid}"):
        p = zoek(code)["producten"]
        assert [x["id"] for x in p] == [pid] and p[0]["besteleenheid"] == "doos" and p[0]["factor"] == 40
        assert p[0]["gekozen"] == 2 and p[0]["open_bestelling"] is None
    assert [x["naam"] for x in zoek("cola zoek")["producten"]] == ["Cola Zoek"]  # precies de naam
    assert [x["naam"] for x in zoek("zoek cola")["producten"]] == ["Cola Zero Zoek", "Cola Zoek"]
    assert "hoort nog bij geen enkel product" in zoek("8712345678906")["melding"]
    assert zoek("snoep")["producten"] == [] and "Geen product" in zoek("snoep")["melding"]
    assert 'id="bestel-scan"' in ingelogde_client.get("/bestellijst").data.decode()
