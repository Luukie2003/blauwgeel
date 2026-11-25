"""Slimmer bestellen (2.17.0): wat er nu waarschijnlijk nog ligt bij Bestellijst nalopen, een seintje als je meer bestelt
dan er voorlopig op gaat, en bij Factuur inboeken wat er veel meer binnenkomt dan besteld."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_bestelling_concept import CHAUD_TRAY, COLA_TRAY, _bestelling, _levering
from test_bestelvoorstel import _product
from test_voorspelling import _bouw_geschiedenis

import bestellen
import facturen
import voorraadduur
import voorspelling


def _tellingen(db, pid, verkocht_per_keer, keren=6, dagen=7):
    """Een begintelling en dan elke 'dagen' dagen een telling waarin zoveel verkocht is; de laatste is van gisteren."""
    laatste = datetime.now() - timedelta(days=1)
    for i in range(keren + 1):
        tijd = laatste - timedelta(days=dagen * (keren - i))
        t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (tijd.strftime("%Y-%m-%d %H:%M"),)).lastrowid
        verkocht = verkocht_per_keer if i else 999  # de eerste regel is het begin en telt niet mee
        db.execute(
            """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
               VALUES (?, ?, 50, 50, ?, 2.0)""", (t, pid, verkocht))
    db.commit()


# ---------- Hoe lang het meegaat ----------


def test_verkoop_per_week_uit_de_tellingen(db):
    gewoon, kort = _product(db, "Fanta Tempo"), _product(db, "Nieuw Tempo")
    _tellingen(db, gewoon, 4)
    _tellingen(db, kort, 4, keren=3, dagen=2)
    tempo = voorraadduur.verkoop_per_week(db)
    assert tempo[gewoon] == pytest.approx(4, abs=0.01)
    assert kort not in tempo  # nog geen drie weken bekend: geen uitspraak


def test_te_veel_alleen_als_een_colli_minder_ook_ruim_genoeg_is():
    # 4 per week, niets op voorraad: 1 krat van 24 is 6 weken, maar zonder die krat heb je niets.
    assert voorraadduur.te_veel(4, 0, 0, 1, 24) is None
    # 2 krat: met 1 krat heb je al 6 weken.
    assert voorraadduur.te_veel(4, 0, 0, 2, 24) == pytest.approx(12)
    # Er ligt al genoeg: dan is ook 1 krat te veel. Wat onderweg is, telt mee.
    assert voorraadduur.te_veel(4, 20, 4, 1, 24) == pytest.approx(12)
    assert voorraadduur.te_veel(40, 0, 0, 5, 24) is None
    assert voorraadduur.te_veel(None, 100, 0, 5, 24) is None  # te weinig bekend
    assert voorraadduur.te_veel(0, 10, 0, 1, 24) == float("inf")  # niets verkocht, en er ligt nog
    assert voorraadduur.te_veel(0, 0, 0, 1, 24) is None
    assert voorraadduur.te_veel(4, 100, 0, 0, 24) is None  # niets bestellen


def test_tempo_op_de_nalooplijst_en_seintje_in_het_besteloverzicht(ingelogde_client, db):
    pid = _product(db, "Fanta Veel", voorraad=10, minimum=0, factor=24, besteleenheid="tray")
    _tellingen(db, pid, 4)
    r = next(r for r in bestellen.nalooplijst(db)["overig"] if r["id"] == pid)
    assert r["per_week"] == pytest.approx(4, abs=0.01) and r["onderweg_stuks"] == 0

    b = _bestelling(db, [(pid, 72)])
    r = bestellen.besteloverzicht(db, [b])[0]["regels"][0]
    assert r["weken"] == pytest.approx((10 + 72) / 4, abs=0.1)  # wat onderweg is, is deze bestelling zelf
    assert "genoeg voor ongeveer 20 weken" in ingelogde_client.get(f"/bestellingen/overzicht?id={b}").data.decode()
    # Ingeboekt: dan geen seintje meer.
    db.execute("UPDATE bestellingen SET status = 'ontvangen' WHERE id = ?", (b,))
    db.commit()
    assert "genoeg voor" not in ingelogde_client.get(f"/bestellingen/overzicht?id={b}").data.decode()


# ---------- Wat er nu waarschijnlijk ligt ----------


def test_verwachte_stand_bij_nalopen(ingelogde_client, db):
    laatste = (datetime.now() - timedelta(days=4)).replace(minute=0, second=0, microsecond=0)
    pid = _product(db, "Pils Stand", voorraad=50, minimum=30)
    op = _product(db, "Op Stand", voorraad=0, minimum=5)
    _bouw_geschiedenis(db, {pid: 10, op: 3}, tijdstippen=[laatste - timedelta(days=7 * (9 - i)) for i in range(10)])

    stand = bestellen.verwachte_stand(db)
    # Zo'n 4 dagen van 10 sinds de telling: in de app staat nog 50, maar er ligt waarschijnlijk minder dan het minimum.
    assert 0 <= stand[pid]["verwacht"] < 30 and stand[pid]["onder_minimum"]
    assert stand[pid]["laag"] <= stand[pid]["verwacht"] <= stand[pid]["hoog"]
    assert stand[pid]["geteld"].endswith(laatste.strftime("%d-%m"))
    assert op not in stand  # er lag al niets

    data = ingelogde_client.get("/bestellijst/nalopen/stand").get_json()
    assert data["stand"][str(pid)]["verwacht"] == stand[pid]["verwacht"]


def test_geen_model_dan_geen_stand(ingelogde_client, db, monkeypatch):
    _product(db, "Zonder Telling")
    assert ingelogde_client.get("/bestellijst/nalopen/stand").get_json() == {"stand": {}}

    def stuk(*_, **__):
        raise RuntimeError("model stuk")

    monkeypatch.setattr(bestellen, "verwachte_verkoop_sinds_telling", stuk)
    assert bestellen.verwachte_stand(db) == {}


# ---------- Meer binnen dan besteld ----------


def _scan(db, ronde_id, code, keer):
    for _ in range(keer):
        facturen.scan(db, ronde_id, code)


def test_meer_dan_besteld_en_niet_besteld(db):
    _lev, chaud, cola, b = _levering(db)  # 48 Chaudfontaine, 24 Coca Cola
    extra = _product(db, "Extra Mee")
    ronde = facturen.ronde_voor_bestelling(db, b)
    _scan(db, ronde, CHAUD_TRAY, 2)
    _scan(db, ronde, COLA_TRAY, 1)
    assert facturen.meer_dan_besteld(db, facturen.ronde(db, ronde)) == []
    facturen.voeg_handmatig_toe(db, ronde, cola, 5)  # minder dan een tray te veel: niets aan de hand
    assert facturen.meer_dan_besteld(db, facturen.ronde(db, ronde)) == []
    _scan(db, ronde, CHAUD_TRAY, 2)
    facturen.voeg_handmatig_toe(db, ronde, extra, 3)
    veel = {m["product_id"]: m for m in facturen.meer_dan_besteld(db, facturen.ronde(db, ronde))}
    assert set(veel) == {chaud, extra}
    assert (veel[chaud]["besteld"], veel[chaud]["gescand"], veel[chaud]["extra"]) == (48, 96, 48)
    assert veel[extra]["besteld"] == 0


def test_verklaring_eerder_niet_geleverd_of_al_ingeboekt(db):
    _lev, chaud, _cola, b = _levering(db)
    oud = db.execute("INSERT INTO bestellingen (status, aangemaakt_op, ontvangen_op) VALUES ('ontvangen', '2026-10-01', '2026-10-03')").lastrowid
    db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld, aantal_ontvangen) VALUES (?, ?, 48, 0)", (oud, chaud))

    def boeking(dagen, aantal, opmerking=None):
        db.execute("INSERT INTO mutaties (product_id, type, aantal, datum, opmerking) VALUES (?, 'in', ?, ?, ?)",
                   (chaud, aantal, (datetime.now() - timedelta(days=dagen)).strftime("%Y-%m-%d %H:%M"), opmerking))

    boeking(5, 48)
    boeking(5, 7, "Correctie na telling")
    boeking(40, 24)
    db.commit()
    ronde = facturen.ronde_voor_bestelling(db, b)
    _scan(db, ronde, CHAUD_TRAY, 4)
    m = facturen.meer_dan_besteld(db, facturen.ronde(db, ronde))[0]
    assert m["nog_open"] == 48
    # Alleen de losse levering van vijf dagen terug, niet de correctie en niet die van weken geleden.
    assert [(e["aantal"], e["datum"]) for e in m["al_ingeboekt"]] == [(48, (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"))]


def test_zonder_bestelling_geen_vergelijking(db):
    _levering(db)
    ronde = facturen.start_ronde(db)
    _scan(db, ronde, CHAUD_TRAY, 9)
    assert facturen.meer_dan_besteld(db, facturen.ronde(db, ronde)) == []


def test_waarschuwing_op_de_pagina_houdt_het_inboeken_niet_tegen(ingelogde_client, db):
    _lev, chaud, _cola, b = _levering(db)
    db.execute("UPDATE producten SET naam = 'Lay''s Water' WHERE id = ?", (chaud,))
    db.commit()
    ronde = facturen.ronde_voor_bestelling(db, b)
    _scan(db, ronde, CHAUD_TRAY, 4)
    pagina = ingelogde_client.get(f"/facturen/{ronde}").data.decode()
    assert 'id="meer-dan-besteld"' in pagina
    assert "Meer dan besteld: Lay\\u0027s Water 96 Fles (48 besteld)." in pagina  # in de vraag bij het afronden
    ingelogde_client.post(f"/facturen/{ronde}/afronden", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT status FROM inboekrondes WHERE id = ?", (ronde,)).fetchone()[0] == "afgerond"
    assert 'id="meer-dan-besteld"' not in ingelogde_client.get(f"/facturen/{ronde}").data.decode()


# ---------- Nooit het model twee keer tegelijk (2.17.1) ----------


def test_stand_rekent_het_model_niet_zelf(db, monkeypatch):
    laatste = (datetime.now() - timedelta(days=4)).replace(minute=0, second=0, microsecond=0)
    pid = _product(db, "Pils Koud", voorraad=50, minimum=30)
    _bouw_geschiedenis(db, {pid: 10}, tijdstippen=[laatste - timedelta(days=7 * (9 - i)) for i in range(10)])
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    monkeypatch.setattr(voorspelling, "SCHIJF_AAN", False)
    voorspelling.wis_bewaarde_resultaten()
    voorspelling._VERWACHT_CACHE.clear()

    def niet_rekenen(*_):
        raise AssertionError("het model hoort hier niet gerekend te worden")

    with monkeypatch.context() as m:
        m.setattr(voorspelling, "_prognose_fit", niet_rekenen)
        m.setattr(voorspelling, "_licht_model", niet_rekenen)
        assert bestellen.verwachte_stand(db) == {}  # nog niet klaar: geen stand, en niets onthouden
    with monkeypatch.context() as m:
        m.setattr(voorspelling, "_prognose_fit", niet_rekenen)
        licht = voorspelling.verwachte_verkoop_sinds_telling(db)[pid]["verwacht"]  # de looplijst: alleen het lichte deel
    voorspelling._VERWACHT_CACHE.clear()
    voorspelling.maak_prognose(db, dagen=7)  # de prognose rekent en bewaart het model
    monkeypatch.setattr(voorspelling, "_licht_model", niet_rekenen)
    assert bestellen.verwachte_stand(db)[pid]["onder_minimum"]
    assert voorspelling.verwachte_verkoop_sinds_telling(db)[pid]["verwacht"] == pytest.approx(licht, rel=0.01)
    voorspelling.wis_bewaarde_resultaten()
    voorspelling._VERWACHT_CACHE.clear()


def test_stand_pas_na_de_prognose_en_lege_melding_verborgen(ingelogde_client):
    pagina = ingelogde_client.get("/bestellijst/nalopen").data.decode()
    assert pagina.count("fetch(standUrl") == 1 and pagina.rstrip().count(".then(haalStand)") == 1
    assert 'id="stand-melding" hidden' in pagina
    css = (Path(__file__).parent.parent / "static" / "clubstijl.css").read_text(encoding="utf-8")
    assert ".cs-melding[hidden] { display: none; }" in css  # .cs-melding is flex: zonder deze regel blijft hij zichtbaar
