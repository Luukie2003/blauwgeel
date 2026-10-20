"""Timers op de tv-schermen (kiosk_timers.py): starten, verlengen en weghalen op de site en op de handterminal, en
linksonder op elk scherm."""

from datetime import datetime, timedelta

from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_secties_rechten import _login, _maak_vrijwilliger

import kiosk_timers


def _start(client, naam="Gehaktballen", minuten="15"):
    return client.post("/timer/starten", data={"csrf_token": _csrf(client), "naam": naam, "minuten": minuten})


def _op_de_tv(app):
    return app.test_client().get("/kiosk/welkom").get_json()["timers"]


def test_een_timer_staat_op_elk_scherm(app, ingelogde_client, db):
    assert _op_de_tv(app) == []
    _start(ingelogde_client)
    timers = _op_de_tv(app)
    assert len(timers) == 1 and timers[0]["naam"] == "Gehaktballen"
    assert 890 <= timers[0]["resterend"] <= 900 and timers[0]["totaal"] == 900
    tv = app.test_client()
    for url in ("/kiosk/prijzen", "/kiosk/scherm", "/kiosk/tv"):
        pagina = tv.get(url).data.decode()
        assert 'id="kiosk-timers"' in pagina and "kioskTimersBijwerken" in pagina and "kioskScherm" in pagina, url


def test_verlengen_en_weghalen(app, ingelogde_client, db):
    _start(ingelogde_client, minuten="10")
    timer_id = _op_de_tv(app)[0]["id"]
    ingelogde_client.post(f"/timer/{timer_id}/verlengen", data={"csrf_token": _csrf(ingelogde_client), "minuten": "5"})
    assert 890 <= _op_de_tv(app)[0]["resterend"] <= 900
    ingelogde_client.post(f"/timer/{timer_id}/stoppen", data={"csrf_token": _csrf(ingelogde_client)})
    assert _op_de_tv(app) == []


def test_klaar_blijft_een_kwartier_staan(db):
    nu = datetime(2026, 10, 20, 20, 0, 0)
    timer_id, _ = kiosk_timers.start(db, "gehaktballen", 15, "Piet", nu=nu)
    assert kiosk_timers.actieve(db, nu + timedelta(minutes=16))[0]["klaar"] is True
    assert kiosk_timers.actieve(db, nu + timedelta(minutes=16))[0]["naam"] == "Gehaktballen"
    assert kiosk_timers.actieve(db, nu + timedelta(minutes=29))
    assert kiosk_timers.actieve(db, nu + timedelta(minutes=31)) == []
    # Een timer die al klaar was en verlengd wordt, telt weer af vanaf nu.
    kiosk_timers.verleng(db, timer_id, 5, nu=nu + timedelta(minutes=20))
    timer = kiosk_timers.actieve(db, nu + timedelta(minutes=20))[0]
    assert timer["resterend"] == 300 and not timer["klaar"]


def test_de_vorige_tijd_wordt_de_standaard(app, ingelogde_client, db):
    assert kiosk_timers.voorstellen(db) == [{"naam": "Gehaktballen", "minuten": 15}]
    _start(ingelogde_client, minuten="12")
    _start(ingelogde_client, naam="Bitterballen", minuten="8")
    assert kiosk_timers.voorstellen(db) == [{"naam": "Bitterballen", "minuten": 8}, {"naam": "Gehaktballen", "minuten": 12}]
    pagina = ingelogde_client.get("/timer").data.decode()
    assert "Bitterballen" in pagina and '"minuten": 12' in pagina.replace('"minuten":12', '"minuten": 12')


def test_ongeldige_invoer(app, ingelogde_client, db):
    for naam, minuten in (("", "15"), ("Gehaktballen", "0"), ("Gehaktballen", "999"), ("Gehaktballen", "tien")):
        _start(ingelogde_client, naam, minuten)
    assert _op_de_tv(app) == []


def test_voor_iedereen_die_is_ingelogd(app, db):
    _maak_vrijwilliger(db, "barman", "")
    barman = app.test_client()
    _login(barman, "barman")
    assert "Timer op de tv" in barman.get("/").data.decode()
    assert barman.get("/timer").status_code == 200
    _start(barman)
    assert _op_de_tv(app)[0]["naam"] == "Gehaktballen"
    assert db.execute("SELECT gestart_door FROM kiosk_timers").fetchone()[0] == "barman"
    assert app.test_client().get("/timer").status_code == 302  # niet ingelogd


def test_vanaf_de_handterminal(app_client, app, db):  # noqa: F811
    leeg = app_client.get("/api/app/timers").get_json()
    assert leeg["timers"] == [] and leeg["voorstellen"][0]["naam"] == "Gehaktballen"
    resp = _post(app_client, "/api/app/timers", naam="Gehaktballen", minuten=15, verzoek_id="t1")
    assert resp.status_code == 200 and "klaar om" in resp.get_json()["melding"]
    _post(app_client, "/api/app/timers", naam="Gehaktballen", minuten=15, verzoek_id="t1")  # nog eens: niet dubbel
    timers = _op_de_tv(app)
    assert len(timers) == 1
    assert app_client.get("/api/app/start").get_json()["timers"][0]["naam"] == "Gehaktballen"
    resp = _post(app_client, f"/api/app/timers/{timers[0]['id']}/verlengen", minuten=5, verzoek_id="t2")
    assert resp.get_json()["timers"][0]["resterend"] > 1100
    assert _post(app_client, "/api/app/timers", naam="", minuten=15, verzoek_id="t3").status_code == 400
    resp = _post(app_client, f"/api/app/timers/{timers[0]['id']}/stoppen")
    assert resp.get_json()["timers"] == [] and _op_de_tv(app) == []
