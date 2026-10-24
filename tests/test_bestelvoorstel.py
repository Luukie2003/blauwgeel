"""Het bestelvoorstel (bestelvoorstel.py, 1.68.0): het uiterste bestelmoment per leverancier, en de prognose met plus en
min bijstellen vanaf het product (site en handterminal), wat meetelt bij "Voorgesteld om te bestellen"."""

from datetime import datetime

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, app_client  # noqa: F401 (fixture)

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


def test_site_stelt_bij_en_bestellen_wist_de_bijstelling(ingelogde_client, db, prognose):
    pid = _product(db, "Sinas Site", voorraad=0)
    resp = ingelogde_client.post(f"/producten/{pid}/bijstelling", data={"csrf_token": _csrf(ingelogde_client), "stuks": "5"})
    assert resp.status_code == 302 and resp.location.endswith(f"/producten/{pid}#verkoop")
    assert bestelvoorstel.bijstellingen(db)[pid]["stuks"] == 5
    ingelogde_client.post("/bestellijst/aanmaken", data={"csrf_token": _csrf(ingelogde_client), "product_id": [pid], f"aantal_{pid}": "5"})
    assert pid not in bestelvoorstel.bijstellingen(db)
