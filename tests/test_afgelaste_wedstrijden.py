"""Afgelaste thuiswedstrijden: een wedstrijd die niet doorgaat telt nergens meer mee
(prognose, dia's, welkomstmelding, kassa-herinnering). De agenda-feed kan het melden,
en je kunt het zelf op afgelast zetten of terugzetten op "gaat door"."""

import sqlite3
from datetime import date, timedelta


import agenda
from conftest import stel_csrf_token_in as _csrf
from helpers import (
    bereken_kassa_telling_status,
    bereken_komende_thuiswedstrijden,
    bereken_wedstrijd_geschiedenis,
    vandaag_amsterdam,
)
from test_kiosk_dagvarianten import _wedstrijden_json
from test_secties_rechten import _login, _maak_vrijwilliger
from test_voorspelling import _bouw_geschiedenis, _product

from voorspelling import lees_kalender, maak_prognose


def _ics(*events):
    """events: (datum 'YYYYMMDD', omschrijving of (omschrijving, status))."""
    regels = ["BEGIN:VCALENDAR", "X-WR-CALNAME:Voetbal.nl - Blauw Geel'15 3"]
    for datum, omschrijving in events:
        status = None
        if isinstance(omschrijving, tuple):
            omschrijving, status = omschrijving
        regels += ["BEGIN:VEVENT", f"DTSTART:{datum}T140000", f"SUMMARY:{omschrijving}"]
        if status:
            regels.append(f"STATUS:{status}")
        regels.append("END:VEVENT")
    regels.append("END:VCALENDAR")
    return "\n".join(regels)


def _wedstrijd(db, dag, omschrijving="Blauw Geel'15 3-Roden 4", team="Blauw Geel'15 3", afgelast=0, bron=None):
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, afgelast, afgelast_bron) VALUES (?, ?, ?, 1, ?, ?)",
        (team, dag.isoformat(), omschrijving, afgelast, bron),
    )
    db.commit()
    return db.execute("SELECT id FROM wedstrijden ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _afgelast(db, wedstrijd_id):
    r = db.execute("SELECT afgelast, afgelast_bron FROM wedstrijden WHERE id = ?", (wedstrijd_id,)).fetchone()
    return r["afgelast"], r["afgelast_bron"]


# ---------- Herkennen in de agenda ----------


def test_agenda_herkent_een_afgelasting_op_status_en_op_woorden():
    ics = _ics(
        ("20261010", "Blauw Geel'15 3-Roden 4"),
        ("20261017", ("Blauw Geel'15 3-Haren 5", "CANCELLED")),
        ("20261024", "AFGELAST - Blauw Geel'15 3-Zuidhorn 6"),
        ("20261031", "Blauw Geel'15 3-Leek 2 (afgelast)"),
    )
    w = agenda._parse_ics(ics)
    assert [(x["datum"], x["afgelast"]) for x in w] == [
        ("2026-10-10", False), ("2026-10-17", True), ("2026-10-24", True), ("2026-10-31", True),
    ]
    # De markering zit niet in de omschrijving: dezelfde wedstrijd blijft dezelfde rij.
    assert [x["omschrijving"] for x in w][2:] == ["Blauw Geel'15 3-Zuidhorn 6", "Blauw Geel'15 3-Leek 2"]
    assert all(x["thuis"] for x in w)


def _ververs(app, db, monkeypatch, tekst):
    db.execute("INSERT OR IGNORE INTO agenda_feeds (id, url) VALUES (1, 'https://voorbeeld.nl/feed.ics')")
    db.commit()

    class Nep:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return tekst.encode("utf-8")

    monkeypatch.setattr(agenda, "urlopen", lambda url, timeout=None: Nep())
    return agenda.ververs_wedstrijden(db_pad=app.config["DATABASE"])


def _rij(app, omschrijving):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM wedstrijden WHERE omschrijving = ?", (omschrijving,)).fetchone()
    conn.close()
    return r


def test_synchronisatie_zet_een_afgelasting_en_haalt_die_weer_weg(app, db, monkeypatch):
    morgen = (date.today() + timedelta(days=3)).strftime("%Y%m%d")
    naam = "Blauw Geel'15 3-Roden 4"
    _ververs(app, db, monkeypatch, _ics((morgen, naam)))
    assert (_rij(app, naam)["afgelast"], _rij(app, naam)["afgelast_bron"]) == (0, None)

    _ververs(app, db, monkeypatch, _ics((morgen, ("AFGELAST " + naam))))  # de agenda meldt het
    assert (_rij(app, naam)["afgelast"], _rij(app, naam)["afgelast_bron"]) == (1, "agenda")

    _ververs(app, db, monkeypatch, _ics((morgen, naam)))  # en weer gewoon
    assert (_rij(app, naam)["afgelast"], _rij(app, naam)["afgelast_bron"]) == (0, None)


def test_synchronisatie_overschrijft_een_handmatige_keuze_niet(app, db, monkeypatch):
    morgen = date.today() + timedelta(days=3)
    naam = "Blauw Geel'15 3-Roden 4"
    _ververs(app, db, monkeypatch, _ics((morgen.strftime("%Y%m%d"), naam)))
    db.execute("UPDATE wedstrijden SET afgelast = 1, afgelast_bron = 'handmatig'")
    db.commit()
    _ververs(app, db, monkeypatch, _ics((morgen.strftime("%Y%m%d"), naam)))  # feed zegt: gewoon
    assert _rij(app, naam)["afgelast"] == 1

    db.execute("UPDATE wedstrijden SET afgelast = 0, afgelast_bron = 'handmatig'")  # "toch spelen"
    db.commit()
    _ververs(app, db, monkeypatch, _ics((morgen.strftime("%Y%m%d"), "AFGELAST " + naam)))
    assert _rij(app, naam)["afgelast"] == 0


def test_wedstrijd_die_uit_de_feed_verdwijnt_gaat_als_afgelast_door(app, db, monkeypatch):
    over_3 = date.today() + timedelta(days=3)
    over_9 = date.today() + timedelta(days=9)
    over_30 = date.today() + timedelta(days=30)
    a, b, c = "Blauw Geel'15 3-A 1", "Blauw Geel'15 3-B 2", "Blauw Geel'15 3-C 3"
    feed = _ics(*[(d.strftime("%Y%m%d"), n) for d, n in ((over_3, a), (over_9, b), (over_30, c))])
    _ververs(app, db, monkeypatch, feed)

    # Wedstrijd b (over 9 dagen) staat niet meer in de feed, maar een latere wel: afgelast.
    # a is er nog en c ligt buiten de 14 dagen waarin we dit afleiden.
    _ververs(app, db, monkeypatch, _ics((over_3.strftime("%Y%m%d"), a), (over_30.strftime("%Y%m%d"), c)))
    assert _rij(app, a)["afgelast"] == 0 and _rij(app, c)["afgelast"] == 0
    assert (_rij(app, b)["afgelast"], _rij(app, b)["afgelast_bron"]) == (1, "agenda")

    # Komt 'ie terug in de feed, dan gaat 'ie weer door.
    _ververs(app, db, monkeypatch, feed)
    assert _rij(app, b)["afgelast"] == 0


def test_een_afgekapte_feed_zonder_latere_wedstrijden_zet_niets_op_afgelast(app, db, monkeypatch):
    over_3 = date.today() + timedelta(days=3)
    over_9 = date.today() + timedelta(days=9)
    a, b = "Blauw Geel'15 3-A 1", "Blauw Geel'15 3-B 2"
    _ververs(app, db, monkeypatch, _ics((over_3.strftime("%Y%m%d"), a), (over_9.strftime("%Y%m%d"), b)))
    # De feed noemt alleen nog een eerdere wedstrijd: 'b' ligt daarna, dus geen bewijs van afgelasting.
    _ververs(app, db, monkeypatch, _ics((date.today().strftime("%Y%m%d"), "Blauw Geel'15 3-Z 9")))
    assert _rij(app, a)["afgelast"] == 0 and _rij(app, b)["afgelast"] == 0


# ---------- Een afgelaste wedstrijd telt nergens mee ----------


def test_prognose_kalender_telt_afgelaste_wedstrijd_niet_mee(db):
    dag = date(2026, 10, 10)
    _wedstrijd(db, dag, "Blauw Geel'15 1-A 1", team="T1")
    afgelast = _wedstrijd(db, dag, "Blauw Geel'15 3-B 2", team="T3")
    assert lees_kalender(db, dag, dag)[dag]["wedstrijden"] == 2
    db.execute("UPDATE wedstrijden SET afgelast = 1, afgelast_bron = 'handmatig' WHERE id = ?", (afgelast,))
    db.commit()
    assert lees_kalender(db, dag, dag)[dag]["wedstrijden"] == 1


def test_prognose_wordt_rustiger_als_de_wedstrijd_is_afgelast(db):
    pid = _product(db, "Pils", voorraad=500)
    laatste = _bouw_geschiedenis(db, {pid: 10}, open_dagen="2,5")
    zaterdag = (laatste + timedelta(days=(5 - laatste.weekday()) % 7 or 7)).date()
    wedstrijd = _wedstrijd(db, zaterdag)
    nu = laatste + timedelta(hours=1)
    met = maak_prognose(db, dagen=14, nu=nu)["totaal"]["omzet"]

    db.execute("UPDATE wedstrijden SET afgelast = 1, afgelast_bron = 'handmatig' WHERE id = ?", (wedstrijd,))
    db.commit()
    zonder = maak_prognose(db, dagen=14, nu=nu)["totaal"]["omzet"]
    assert zonder < met


def test_komende_wedstrijden_en_geschiedenis_laten_afgelaste_weg(db):
    morgen = date.today() + timedelta(days=1)
    gisteren = date.today() - timedelta(days=1)
    _wedstrijd(db, morgen, "Blauw Geel'15 1-A 1", team="T1")
    _wedstrijd(db, morgen, "Blauw Geel'15 3-B 2", team="T3", afgelast=1, bron="handmatig")
    _wedstrijd(db, gisteren, "Blauw Geel'15 3-C 3", team="T3", afgelast=1, bron="agenda")

    gewoon = bereken_komende_thuiswedstrijden(db)
    assert [w["omschrijving"] for w in gewoon[0]["wedstrijden"]] == ["Blauw Geel'15 1-A 1"]
    alles = bereken_komende_thuiswedstrijden(db, inclusief_afgelast=True)
    assert [(w["omschrijving"], w["afgelast"]) for w in alles[0]["wedstrijden"]] == [
        ("Blauw Geel'15 1-A 1", 0), ("Blauw Geel'15 3-B 2", 1),
    ]
    assert bereken_wedstrijd_geschiedenis(db) == []


def test_welkomstmelding_en_kassaherinnering_negeren_een_afgelaste_wedstrijd(client, db):
    vandaag = vandaag_amsterdam()
    _wedstrijd(db, vandaag, "Blauw Geel'15 3-Roden 4", afgelast=1, bron="handmatig")
    assert _wedstrijden_json(client.get("/kiosk/prijzen").data.decode()) == []

    # De kassa-herinnering ("na een thuiswedstrijd binnen 3 dagen tellen") ook niet.
    vier_dagen_terug = date.today() - timedelta(days=4)
    wid = _wedstrijd(db, vier_dagen_terug, "Blauw Geel'15 3-Haren 5")
    assert bereken_kassa_telling_status(db)["tekst"].startswith("Nog niet geteld sinds wedstrijd van")
    db.execute("UPDATE wedstrijden SET afgelast = 1, afgelast_bron = 'handmatig' WHERE id = ?", (wid,))
    db.commit()
    assert not bereken_kassa_telling_status(db)["tekst"].startswith("Nog niet geteld sinds wedstrijd van")


# ---------- Zelf op afgelast zetten ----------


def test_wedstrijd_afgelasten_en_terugzetten(ingelogde_client, db):
    morgen = date.today() + timedelta(days=2)
    wid = _wedstrijd(db, morgen)

    resp = ingelogde_client.post(
        f"/wedstrijden/{wid}/afgelast",
        data={"csrf_token": _csrf(ingelogde_client), "afgelast": "1", "terug": "prognose"},
    )
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/prognose#thuiswedstrijden")
    assert _afgelast(db, wid) == (1, "handmatig")

    pagina = ingelogde_client.get("/prognose").data.decode()
    assert "Thuiswedstrijden die meetellen" in pagina and "Toch spelen" in pagina and "afgelast" in pagina

    resp = ingelogde_client.post(
        f"/wedstrijden/{wid}/afgelast", data={"csrf_token": _csrf(ingelogde_client), "afgelast": "0"}
    )
    assert resp.headers["Location"].endswith("/wedstrijden")
    assert _afgelast(db, wid) == (0, "handmatig")  # handmatig: de agenda overschrijft dit niet meer


def test_wedstrijdenpagina_toont_afgelaste_wedstrijd_met_knop(ingelogde_client, db):
    morgen = date.today() + timedelta(days=2)
    wid = _wedstrijd(db, morgen, afgelast=1, bron="handmatig")
    tekst = ingelogde_client.get("/wedstrijden").data.decode()
    assert "Roden 4" in tekst and "afgelast" in tekst and "Toch spelen" in tekst
    assert f"/wedstrijden/{wid}/afgelast" in tekst


def test_onbekende_wedstrijd_geeft_een_melding(ingelogde_client):
    resp = ingelogde_client.post(
        "/wedstrijden/99999/afgelast", data={"csrf_token": _csrf(ingelogde_client), "afgelast": "1"}
    )
    assert resp.status_code == 302


def test_afgelasten_hoort_bij_de_voorraad_sectie(client, db):
    wid = _wedstrijd(db, date.today() + timedelta(days=2))
    _maak_vrijwilliger(db, "kassahulp", "kassa")
    _login(client, "kassahulp")
    resp = client.post(f"/wedstrijden/{wid}/afgelast", data={"csrf_token": _csrf(client), "afgelast": "1"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
    assert _afgelast(db, wid) == (0, None)


def test_gespeelde_wedstrijden_kun_je_achteraf_afgelasten(ingelogde_client, db):
    gisteren = date.today() - timedelta(days=1)
    wid = _wedstrijd(db, gisteren, "Blauw Geel'15 3-Helpman 4")
    tekst = ingelogde_client.get("/wedstrijden").data.decode()
    assert "Helpman 4" in tekst and "Afgelast?" in tekst and f"/wedstrijden/{wid}/afgelast" in tekst

    ingelogde_client.post(
        f"/wedstrijden/{wid}/afgelast", data={"csrf_token": _csrf(ingelogde_client), "afgelast": "1"}
    )
    tekst = ingelogde_client.get("/wedstrijden").data.decode()
    assert "afgelast" in tekst and "Toch gespeeld" in tekst
    # Voor de rest van de app is 'ie niet gespeeld: niet in de kalender van de prognose.
    assert lees_kalender(db, gisteren, gisteren)[gisteren]["wedstrijden"] == 0
    assert bereken_wedstrijd_geschiedenis(db) == []
    assert [w["afgelast"] for w in bereken_wedstrijd_geschiedenis(db, inclusief_afgelast=True)] == [1]
