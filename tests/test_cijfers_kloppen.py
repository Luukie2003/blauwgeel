"""Cijfers die kloppen (2.18.0): shots per fles in de omzet (en oude tellingen omrekenen), smaken die bij het tellen door
elkaar zijn gehaald, en het winterstop-plan."""

from datetime import date, datetime, timedelta

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_bestelvoorstel import _product
from test_slimmer_bestellen import _tellingen
from test_voorspelling import _bouw_geschiedenis

import facturen
import gegevenscontrole
import glazen
import marge
import seizoen_in_cijfers
import sluitperiode
import verwisseld
import voorspelling
from helpers import bereken_fust_verkopen
from helpers.producten import is_fles_per_glas, omzet_per_eenheid
from routes.tellen.looplijst import controle_regels

# ---------- Shots ----------


def _shot(db, naam="Dropshot", glazen_=28, prijs=3.5, categorie="Shot", eenheid="Fles"):
    pid = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, inkoopprijs, actief,
               glazen_per_fust, prijs_per_glas) VALUES (?, ?, ?, 10, 0, 3.5, 14, 1, ?, ?)""",
        (naam, categorie, eenheid, glazen_, prijs),
    ).lastrowid
    db.commit()
    return pid


def _rij(db, pid):
    return db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()


def _telregel(db, pid, verkocht, prijs, datum="2026-11-03 12:00"):
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (datum,)).lastrowid
    r = db.execute(
        """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
           VALUES (?, ?, 10, 3, ?, ?)""", (t, pid, verkocht, prijs)).lastrowid
    db.commit()
    return r


def test_een_fles_per_glas_is_geen_fust(db):
    fles, fust = _shot(db), _shot(db, "Hertog Jan Fust", 60, 2.0, "Telling", "Fust")
    assert is_fles_per_glas(_rij(db, fles)) and not is_fles_per_glas(_rij(db, fust))
    assert not is_fles_per_glas(_rij(db, _shot(db, "Wijn heel", 0)))
    assert omzet_per_eenheid(_rij(db, fles)) == 98.0
    _telregel(db, fles, 2, 98.0)
    _telregel(db, fust, 1, 120.0, "2026-11-04 12:00")
    assert [g["product_naam"] for g in bereken_fust_verkopen(db)["gebeurtenissen"]] == ["Hertog Jan Fust"]
    assert [f["naam"] for f in marge.bereken_tap(db)] == ["Hertog Jan Fust"]
    assert [p["naam"] for p in facturen.plu_lijst(db)] == ["Hertog Jan Fust"]


def test_shots_zijn_geen_getapte_glazen_in_seizoen_in_cijfers(db, monkeypatch):
    fles, fust = _shot(db), _shot(db, "Fust Pils", 80, 2.0, "Telling", "Fust")
    verdeling = {"omzet": {date(2026, 10, 3): 900.0}, "producten": {date(2026, 10, 3): {fles: [2.0, 196.0], fust: [1.0, 160.0]}},
                 "eerste": datetime(2026, 6, 1), "laatste": datetime(2026, 11, 9)}
    monkeypatch.setattr(seizoen_in_cijfers, "verdeling", lambda db, nu=None: verdeling)
    cijfers = seizoen_in_cijfers.bereken(db, datetime(2026, 11, 10, 12))
    assert next(c for c in cijfers["cijfers"] if c["sleutel"] == "getapt")["getal"] == 80  # alleen het fust
    assert [(p["naam"], p["aantal"]) for p in cijfers["top_bar"]] == [("Pils", 80), ("Dropshot", 56)]  # twee flessen van 28


def test_oude_tellingen_omrekenen(db):
    pid = _shot(db)
    oud = _telregel(db, pid, 7, 3.5)
    ouder = _telregel(db, pid, 2, 3.0, "2026-10-01 12:00")  # toen kostte een shot nog € 3,00
    goed = _telregel(db, pid, 1, 98.0, "2026-11-10 12:00")
    niets = _telregel(db, pid, 0, 3.5, "2026-11-11 12:00")
    regels = glazen.te_corrigeren(db, _rij(db, pid))
    assert [(r["id"], r["nieuw"], r["erbij"]) for r in regels] == [(oud, 98.0, 661.5), (ouder, 84.0, 162.0)]
    assert glazen.corrigeer(db, _rij(db, pid)) == (2, 823.5)
    prijzen = dict(db.execute("SELECT id, verkoopprijs FROM telling_regels").fetchall())
    assert (prijzen[oud], prijzen[ouder], prijzen[goed], prijzen[niets]) == (98.0, 84.0, 98.0, 3.5)
    assert glazen.corrigeer(db, _rij(db, pid)) == (0, 0)  # nog een keer doet niets
    # Een fust of een fles die heel verkocht wordt, blijft ervan af.
    fust = _shot(db, "Fust", 60, 2.0, "Telling", "Fust")
    _telregel(db, fust, 1, 2.0)
    assert glazen.te_corrigeren(db, _rij(db, fust)) == []
    heel = _shot(db, "Heel", 0, 0)
    _telregel(db, heel, 1, 3.5)
    assert glazen.te_corrigeren(db, _rij(db, heel)) == []


def test_na_bewerken_naar_het_omrekenen(ingelogde_client, db):
    pid = _shot(db, glazen_=0, prijs=0)
    _telregel(db, pid, 7, 3.5)
    p = _rij(db, pid)
    velden = {"csrf_token": _csrf(ingelogde_client), "naam": p["naam"], "categorie": "Shot", "eenheid": "Fles", "voorraad": "10",
              "min_voorraad": "0", "bestel_hoeveelheid": "0", "verkoopprijs": "3.50", "inkoopprijs": "14", "actief": "1",
              "besteleenheid_factor": "1", "glazen_per_fust": "28", "prijs_per_glas": "3.50"}
    antwoord = ingelogde_client.post(f"/producten/{pid}/bewerken", data=velden)
    assert antwoord.headers["Location"].endswith(f"/producten/{pid}/oude-tellingen")
    pagina = ingelogde_client.get(f"/producten/{pid}/oude-tellingen").data.decode()
    assert "661,50" in pagina and db.execute("SELECT verkoopprijs FROM telling_regels").fetchone()[0] == 3.5  # alleen gekeken
    assert "oude-tellingen" in ingelogde_client.get(f"/producten/{pid}/bewerken").data.decode()
    ingelogde_client.post(f"/producten/{pid}/oude-tellingen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT verkoopprijs FROM telling_regels").fetchone()[0] == 98.0
    assert db.execute("SELECT omschrijving FROM logboek WHERE endpoint = 'product_oude_tellingen'").fetchone()[0].startswith("Dropshot")
    assert "per fles" in ingelogde_client.get(f"/producten/{pid}").data.decode()


def test_omrekenen_alleen_voor_beheerders():
    import rechten

    assert "product_oude_tellingen" in rechten.BEHEERDER_ENDPOINTS


def test_gegevenscontrole_noemt_een_shotfles_zonder_aantal(db):
    _shot(db, "Stroh", 0, 0)
    _shot(db, "Klaar", 28)
    c = next(c for c in gegevenscontrole.controleer(db)["controles"] if c["sleutel"] == "shotfles_zonder_glazen")
    assert [r["naam"] for r in c["regels"]] == ["Stroh"]


def test_prognose_omzet_telt_glazen(db):
    laatste = (datetime.now() - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    pid = _shot(db)
    _bouw_geschiedenis(db, {pid: 1}, tijdstippen=[laatste - timedelta(days=7 * (9 - i)) for i in range(10)])
    p = voorspelling.maak_prognose(db, dagen=7)
    regel = p["producten"][0]
    assert p["totaal"]["omzet"] == pytest.approx(regel["verwacht"] * 98.0)


# ---------- Door elkaar geteld ----------


def _smaak(db, naam, voorraad, categorie="Mix"):
    pid = _product(db, naam, voorraad=voorraad)
    db.execute("UPDATE producten SET categorie = ? WHERE id = ?", (categorie, pid))
    db.commit()
    return pid


def _regel(db, pid, totaal, verwacht):
    v = {"verwacht": verwacht, "laag": verwacht - 2, "hoog": verwacht + 2}
    return {"product": _rij(db, pid), "totaal": totaal, "verwacht": v, "afwijking": None, "model_afwijking": None}


def test_smaken_verwisseld_op_het_controlescherm(db):
    peach, green = _smaak(db, "Bozu Peach", 60), _smaak(db, "Bozu Green", 60)
    cola = _smaak(db, "Coca Cola", 60)
    regels = verwisseld.op_controlescherm([
        _regel(db, peach, 30, 54), _regel(db, green, 80, 58), _regel(db, cola, 30, 54),  # cola ook te weinig, ander merk
    ])
    per = {r["product"]["id"]: r["verwisseld"] for r in regels}
    assert per[peach] == {"met": "Bozu Green", "meer": False, "aantal": 22}
    assert per[green] == {"met": "Bozu Peach", "meer": True, "aantal": 22}
    assert per[cola] is None


@pytest.mark.parametrize("pda", [False, True])
def test_de_vraag_staat_op_het_controlescherm(app, db, pda):
    from flask import render_template

    peach, green = _smaak(db, "Bozu Peach", 60), _smaak(db, "Bozu Green", 60)
    regels = verwisseld.op_controlescherm([_regel(db, peach, 30, 54), _regel(db, green, 80, 58)])
    for r in regels:
        r.update(bar="1", hok="2")
    with app.test_request_context("/tellen/lopen/controleren"):
        pagina = render_template("tellen_lopen_controleren.html", regels=regels, pda_modus=pda,
                                 basis_template="base_pda.html" if pda else "base.html")
    tekst = " ".join(pagina.split())
    assert "Door elkaar geteld met Bozu Green? Hier staan er 22 minder dan verwacht, daar ongeveer evenveel meer." in tekst


def test_geen_vraag_bij_klein_of_ongelijk_verschil(db):
    peach, green = _smaak(db, "Bozu Peach", 60), _smaak(db, "Bozu Green", 60)
    regels = verwisseld.op_controlescherm([_regel(db, peach, 51, 54), _regel(db, green, 62, 60)])
    assert not any(r["verwisseld"] for r in regels)
    regels = verwisseld.op_controlescherm([_regel(db, peach, 4, 54), _regel(db, green, 64, 60)])  # 50 weg, 4 erbij
    assert not any(r["verwisseld"] for r in regels)


def test_merk_telt_als_familie_en_controlescherm_in_de_app(db):
    a, b = _smaak(db, "Zoet", 20), _smaak(db, "Zuur", 20)
    db.execute("UPDATE producten SET merk = 'Haribo' WHERE id IN (?, ?)", (a, b))
    db.commit()
    regels = verwisseld.op_controlescherm([_regel(db, a, 30, 19), _regel(db, b, 8, 19)])
    assert regels[0]["verwisseld"]["met"] == "Zuur"
    assert "verwisseld" in controle_regels(db, {str(a): 20}, {}, {})[0]


def test_bij_een_telling_achteraf_ook_van_de_handterminal(ingelogde_client, db):
    peach, green = _smaak(db, "Bozu Peach", 60), _smaak(db, "Bozu Green", 60)
    for pid in (peach, green):
        _tellingen(db, pid, 10)
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'zebra')", (datetime.now().strftime("%Y-%m-%d %H:%M"),)).lastrowid
    for pid, geteld, verkocht, correctie in ((peach, 20, 40, 0), (green, 85, 0, 25)):
        db.execute("""INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
                      VALUES (?, ?, 60, ?, ?, ?, 2)""", (t, pid, geteld, verkocht, correctie))
    db.commit()
    paren = verwisseld.bij_telling(db, db.execute("SELECT * FROM tellingen WHERE id = ?", (t,)).fetchone())
    assert [(v["meer"]["naam"], v["minder"]["naam"]) for v in paren] == [("Bozu Green", "Bozu Peach")]
    assert 'id="verwisseld"' in ingelogde_client.get(f"/tellingen/{t}").data.decode()
    eerste = db.execute("SELECT * FROM tellingen ORDER BY id LIMIT 1").fetchone()
    assert verwisseld.bij_telling(db, eerste) == []
    assert 'id="verwisseld"' not in ingelogde_client.get(f"/tellingen/{eerste['id']}").data.decode()


# ---------- Winterstop ----------


def _dicht(db, van, dagen):
    for i in range(dagen):
        db.execute("INSERT OR REPLACE INTO verkoop_uitzonderingen (datum, open, opmerking) VALUES (?, 0, 'Winterstop')",
                   ((van + timedelta(days=i)).isoformat(),))
    db.commit()


def test_sluitperioden(db):
    vandaag = date(2026, 11, 25)  # woensdag; standaard open op woensdag en zaterdag
    db.execute("UPDATE instellingen SET verkoopdagen = '2,5' WHERE id = 1")
    db.commit()
    assert sluitperiode.perioden(db, vandaag) == []
    _dicht(db, date(2026, 12, 14), 28)
    p, = sluitperiode.perioden(db, vandaag)
    assert (p["laatste_open"], p["van"], p["tot"], p["eerste_open"]) == (
        date(2026, 12, 12), date(2026, 12, 13), date(2027, 1, 12), date(2027, 1, 13))
    p, = sluitperiode.perioden(db, date(2026, 12, 20))  # er middenin
    assert p["laatste_open"] is None and p["eerste_open"] == date(2027, 1, 13)


def test_laatste_bestelmoment():
    lev = {"naam": "Robertus", "besteldagen": "1", "bestellen_voor": "23:00", "levertijd_dagen": 2}
    nu = datetime(2026, 11, 25, 10)
    assert sluitperiode.laatste_bestelmoment(lev, date(2026, 12, 12), nu) == datetime(2026, 12, 8, 23)
    assert sluitperiode.laatste_bestelmoment(lev, date(2026, 11, 26), nu) is None
    assert sluitperiode.laatste_bestelmoment({**lev, "besteldagen": ""}, date(2026, 12, 12), nu) is None


def test_winterstop_plan(ingelogde_client, db):
    laatste = (datetime.now() - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    tekort = _product(db, "Pils Stop", voorraad=5, minimum=200, factor=24, besteleenheid="krat")
    veel = _product(db, "Green Stop", voorraad=900, minimum=10)
    wacht = _product(db, "Cola Stop", voorraad=60, minimum=80)
    _product(db, "Onbekend Stop", voorraad=50)  # nooit geteld: geen voorspelling, dus ook geen oordeel
    _bouw_geschiedenis(db, {tekort: 10, veel: 1, wacht: 2}, tijdstippen=[laatste - timedelta(days=7 * (9 - i)) for i in range(10)])
    db.execute("UPDATE producten SET voorraad = 5 WHERE id = ?", (tekort,))
    db.commit()
    vandaag = datetime.now().date()
    _dicht(db, vandaag + timedelta(days=8), 21)
    periode, = sluitperiode.perioden(db, vandaag)
    plan = sluitperiode.plan(db, periode)
    assert plan["beschikbaar"]
    per = {p["id"]: p for p in plan["producten"]}
    t = per[tekort]
    # Een week van zo'n 10 per dag: genoeg voor de verwachting, niet voor het minimum van 200.
    assert t["bestellen"] >= 3 and t["bestellen"] * 24 < 200
    assert [p["id"] for p in plan["bestellen"]] == [tekort]
    assert [p["id"] for p in plan["opmaken"]] == [veel]
    assert [p["id"] for p in plan["wachten"]] == [wacht]  # onder het minimum, maar genoeg tot de stop
    assert t["herstart"] > 0 and per[veel]["herstart"] == 0

    pagina = ingelogde_client.get("/prognose/winterstop").data.decode()
    assert "Winterstop" in pagina and "data-lazy-bron" in pagina
    deel = ingelogde_client.get("/prognose/winterstop/resultaat").data.decode()
    assert "Pils Stop" in deel and "Hoeft niet" in deel


def test_winterstop_zonder_stop_of_voorspelling(ingelogde_client, db):
    db.execute("DELETE FROM verkoop_uitzonderingen")
    db.execute("UPDATE instellingen SET verkoopdagen = '2,5' WHERE id = 1")
    db.commit()
    assert "als uitzondering" in ingelogde_client.get("/prognose/winterstop").data.decode()
    assert ingelogde_client.get("/prognose/winterstop/resultaat").data == b""
    _dicht(db, datetime.now().date() + timedelta(days=8), 30)
    assert "te weinig tellingen" in ingelogde_client.get("/prognose/winterstop/resultaat").data.decode()
