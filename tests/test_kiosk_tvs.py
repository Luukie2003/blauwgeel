"""Gekoppelde tv's (kiosk_tvs.py, routes/kiosk/tvs.py): koppelen met een code, per tv kiezen wat hij toont en hoe
groot, op afstand opnieuw laden, zien of hij aan staat, en een melding als hij uit staat tijdens de bardienst."""

import re
from datetime import datetime, timedelta

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

import kiosk_tvs
import noodstop

TOKEN = "TestTvToken1234567890"


def _code(tv_client, token=TOKEN):
    pagina = tv_client.get(f"/kiosk/t/{token}").data.decode()
    return re.search(r'class="code">(\d{3}) (\d{3})<', pagina).group(1, 2)


def _koppel(beheer, code, naam="Bar", scherm="prijzen"):
    return beheer.post("/kiosk/tvs/koppelen", data={
        "csrf_token": _csrf(beheer), "code": " ".join(code), "naam": naam, "scherm": scherm})


def _gekoppeld(app, ingelogde_client, scherm="prijzen", token=TOKEN):
    tv = app.test_client()
    _koppel(ingelogde_client, _code(tv, token), scherm=scherm)
    return tv


def _rij(db, token=TOKEN):
    return db.execute("SELECT * FROM kiosk_tvs WHERE token = ?", (token,)).fetchone()


def _versie(tv, token=TOKEN, **args):
    query = "&".join(f"{k}={v}" for k, v in args.items())
    return tv.get(f"/kiosk/t/{token}/versie" + (f"?{query}" if query else "")).get_json()["versie"]


def test_een_nieuwe_tv_krijgt_een_eigen_adres_en_een_koppelcode(app, db):
    tv = app.test_client()
    start = tv.get("/kiosk/koppelen")
    assert start.status_code == 200 and "kantine_tv_token" in start.data.decode()
    assert "/kiosk/t/TOKEN" in start.data.decode()
    code = "".join(_code(tv))
    assert _code(tv) == (code[:3], code[3:])  # dezelfde code zolang hij geldig is
    assert _versie(tv) == f"koppel-{code}"
    assert tv.get("/kiosk/t/kort").status_code == 404
    assert tv.get("/kiosk/t/met%20spatie%20erin%20lang").status_code == 404


def test_koppelen_met_de_code(app, ingelogde_client, db):
    tv = app.test_client()
    code = _code(tv)
    oude_versie = _versie(tv)
    resp = _koppel(ingelogde_client, code, naam="  Bar  ", scherm="dias")
    assert resp.headers["Location"].endswith("/kiosk#tvs")
    rij = _rij(db)
    assert rij["naam"] == "Bar" and rij["scherm"] == "dias" and rij["gekoppeld_door"] == "admin"
    # De tv merkt het bij de volgende vraag en toont dan de dia's.
    assert _versie(tv) != oude_versie
    pagina = tv.get(f"/kiosk/t/{TOKEN}").data.decode()
    assert "kiosk_dia_positie" in pagina and "Deze tv koppelen" not in pagina
    assert "Tv gekoppeld" in ingelogde_client.get("/logboek").data.decode()
    # De code is daarna niet nog eens te gebruiken.
    assert db.execute("SELECT COUNT(*) FROM kiosk_tv_koppelcodes").fetchone()[0] == 0


def test_een_verkeerde_of_verlopen_code(app, ingelogde_client, db):
    tv = app.test_client()
    code = _code(tv)
    _koppel(ingelogde_client, ("000", "000") if code != ("000", "000") else ("111", "111"))
    assert _rij(db) is None
    assert "staat niet (meer) op een tv" in ingelogde_client.get("/kiosk").data.decode()
    oud = (datetime.now() - timedelta(minutes=31)).strftime(kiosk_tvs.FORMAAT)
    db.execute("UPDATE kiosk_tv_koppelcodes SET aangemaakt_op = ?", (oud,))
    db.commit()
    _koppel(ingelogde_client, code)
    assert _rij(db) is None
    assert _code(tv) != code  # de tv krijgt vanzelf een nieuwe


def test_per_tv_kiezen_wat_hij_toont_en_hoe_groot(app, ingelogde_client, db):
    tv = _gekoppeld(app, ingelogde_client)
    rij = _rij(db)
    pagina = tv.get(f"/kiosk/t/{TOKEN}").data.decode()
    assert "prijzen-grid" in pagina and '"zoom": 100' in pagina
    versie = _versie(tv)

    ingelogde_client.post(f"/kiosk/tvs/{rij['id']}/opslaan", data={
        "csrf_token": _csrf(ingelogde_client), "naam": "Bar links", "scherm": "prijzen", "zoom": "120"})
    assert _rij(db)["zoom"] == 120 and _rij(db)["naam"] == "Bar links"
    assert _versie(tv) != versie
    assert '"zoom": 120' in tv.get(f"/kiosk/t/{TOKEN}").data.decode()

    # Opnieuw laden op afstand: alleen de versie verandert.
    versie = _versie(tv)
    ingelogde_client.post(f"/kiosk/tvs/{rij['id']}/herladen", data={"csrf_token": _csrf(ingelogde_client)})
    assert _versie(tv) != versie

    # Een zoom die er niet tussen staat wordt de dichtstbijzijnde; een onbekend scherm wordt geweigerd.
    ingelogde_client.post(f"/kiosk/tvs/{rij['id']}/opslaan", data={
        "csrf_token": _csrf(ingelogde_client), "naam": "Bar", "scherm": "prijzen", "zoom": "117"})
    assert _rij(db)["zoom"] == 120
    ingelogde_client.post(f"/kiosk/tvs/{rij['id']}/opslaan", data={
        "csrf_token": _csrf(ingelogde_client), "naam": "Bar", "scherm": "iets", "zoom": "100"})
    assert _rij(db)["scherm"] == "prijzen"


def test_het_wisselscherm_volgt_de_wisselknop(app, ingelogde_client, db):
    tv = _gekoppeld(app, ingelogde_client, scherm="wissel")
    assert "prijzen-grid" in tv.get(f"/kiosk/t/{TOKEN}").data.decode()
    versie = _versie(tv)
    ingelogde_client.post("/kiosk/tv/wisselen", data={"csrf_token": _csrf(ingelogde_client)})
    assert _versie(tv) != versie
    assert "kiosk_dia_positie" in tv.get(f"/kiosk/t/{TOKEN}").data.decode()


def test_de_tv_laat_weten_dat_hij_aan_staat(app, ingelogde_client, db):
    tv = _gekoppeld(app, ingelogde_client)
    assert _rij(db)["laatst_gezien"] is None
    # Een voorbeeld op de site telt niet.
    tv.get(f"/kiosk/t/{TOKEN}?voorbeeld=1")
    _versie(tv)
    assert _rij(db)["laatst_gezien"] is None
    tv.get(f"/kiosk/t/{TOKEN}")
    rij = _rij(db)
    assert rij["laatst_gezien"] is not None and rij["geladen_op"] is not None
    _versie(tv, beeld="961x541", app="1.1")
    rij = _rij(db)
    assert rij["toont"] == "prijzen" and rij["beeld"] == "961x541" and rij["app_versie"] == "1.1"
    status = kiosk_tvs.status(rij)
    assert status["aan"] and status["tekst"] == "Aan" and status["app"] == "tv-app 1.1"
    # Het opvragen vlak voor een herlaadbeurt (zie _kiosk_herstel.html) telt niet als opnieuw geladen.
    db.execute("UPDATE kiosk_tvs SET geladen_op = '2026-01-01 10:00:00'")
    db.commit()
    tv.get(f"/kiosk/t/{TOKEN}", headers={"X-Kiosk-Controle": "1"})
    assert _rij(db)["geladen_op"] == "2026-01-01 10:00:00"
    status = ingelogde_client.get("/kiosk/tvs/status").get_json()["tvs"][0]
    assert status["naam"] == "Bar" and status["status"]["aan"]


def test_hooguit_eens_per_minuut_weggeschreven(app, ingelogde_client, db):
    _gekoppeld(app, ingelogde_client)
    nu = datetime(2026, 10, 20, 20, 0, 0)
    kiosk_tvs.hartslag(db, _rij(db), toont="prijzen", beeld="1920x1080", app_versie="browser", nu=nu)
    kiosk_tvs.hartslag(db, _rij(db), toont="prijzen", beeld="1920x1080", app_versie="browser", nu=nu + timedelta(seconds=30))
    assert _rij(db)["laatst_gezien"] == "2026-10-20 20:00:00"
    # Iets anders op het scherm: meteen.
    kiosk_tvs.hartslag(db, _rij(db), toont="dias", nu=nu + timedelta(seconds=40))
    assert _rij(db)["laatst_gezien"] == "2026-10-20 20:00:40"
    kiosk_tvs.hartslag(db, _rij(db), toont="dias", nu=nu + timedelta(seconds=101))
    assert _rij(db)["laatst_gezien"] == "2026-10-20 20:01:41"
    rij = _rij(db)
    assert kiosk_tvs.staat_aan(rij, nu + timedelta(minutes=4))
    assert not kiosk_tvs.staat_aan(rij, nu + timedelta(minutes=5))
    assert kiosk_tvs.status(rij, nu + timedelta(minutes=5))["tekst"] == "Uit, laatst gezien om 20:01"
    assert kiosk_tvs.status(rij, nu + timedelta(days=1))["tekst"] == "Uit, laatst gezien gisteren om 20:01"


def test_een_tv_die_uit_staat_tijdens_de_bardienst(app, ingelogde_client, db):
    _gekoppeld(app, ingelogde_client)
    assert "staat uit" not in ingelogde_client.get("/").data.decode()  # geen bardienst: geen melding
    nu = datetime.now()
    db.execute(
        "INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op) VALUES (?, ?, ?, 'Piet', ?)",
        (nu.date().isoformat(), (nu - timedelta(hours=1)).strftime("%H:%M"), (nu + timedelta(hours=1)).strftime("%H:%M"),
         nu.strftime("%Y-%m-%d %H:%M")),
    )
    db.commit()
    if nu.hour in (0, 23):  # de dienst loopt dan over middernacht: daar is een eigen test voor
        return
    overzicht = ingelogde_client.get("/").data.decode()
    assert "Tv &#39;Bar&#39; staat uit" in overzicht and "/kiosk#tvs" in overzicht
    kiosk_tvs.hartslag(db, _rij(db), toont="prijzen")
    assert "staat uit" not in ingelogde_client.get("/").data.decode()


def test_een_bardienst_over_middernacht(app, db):
    db.execute(
        "INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op) "
        "VALUES ('2026-10-24', '22:00', '01:00', 'Piet', '2026-10-01 10:00')"
    )
    db.commit()
    assert kiosk_tvs.bardienst_bezig(db, datetime(2026, 10, 24, 21, 59)) is None
    assert kiosk_tvs.bardienst_bezig(db, datetime(2026, 10, 24, 23, 30)) is not None
    assert kiosk_tvs.bardienst_bezig(db, datetime(2026, 10, 25, 0, 30)) is not None
    assert kiosk_tvs.bardienst_bezig(db, datetime(2026, 10, 25, 1, 0)) is None


def test_ontkoppelen(app, ingelogde_client, db):
    tv = _gekoppeld(app, ingelogde_client)
    rij = _rij(db)
    ingelogde_client.post(f"/kiosk/tvs/{rij['id']}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    assert _rij(db) is None
    assert "Deze tv koppelen" in tv.get(f"/kiosk/t/{TOKEN}").data.decode()
    assert "Tv ontkoppeld" in ingelogde_client.get("/logboek").data.decode()


def test_kantine_tv_toont_de_tvs(app, ingelogde_client, db):
    tv = _gekoppeld(app, ingelogde_client)
    hub = ingelogde_client.get("/kiosk").data.decode()
    assert "Tv koppelen" in hub and "Bar" in hub and "Nog niet gezien" in hub
    assert f"/kiosk/t/{TOKEN}?voorbeeld=1" in hub
    tv.get(f"/kiosk/t/{TOKEN}")
    _versie(tv, beeld="1920x1080", app="browser")
    hub = ingelogde_client.get("/kiosk").data.decode()
    assert "tv-status--aan" in hub and "Toont de prijzenlijst · beeld 1920x1080 · in een browser" in hub


def test_alleen_met_de_sectie_kantine_tv(app, db):
    tv = app.test_client()
    code = _code(tv)
    _maak_vrijwilliger(db, "hulp", "voorraad")
    hulp = app.test_client()
    _login(hulp, "hulp")
    _koppel(hulp, code)
    assert _rij(db) is None
    assert hulp.get("/kiosk/tvs/status").status_code == 302


def test_niet_te_veel_open_koppelcodes(app, db):
    tv = app.test_client()
    for i in range(kiosk_tvs.MAX_OPEN_CODES):
        assert "class=\"code\"" in tv.get(f"/kiosk/t/{TOKEN}{i:03d}").data.decode()
    assert "te veel tv's tegelijk" in tv.get(f"/kiosk/t/{TOKEN}999").data.decode()


def test_tijdens_de_noodstop_ook_op_slot(app, ingelogde_client, db):
    tv = _gekoppeld(app, ingelogde_client)
    noodstop.vergrendel(db, "test")
    assert "Systeem <span>vergrendeld</span>" in tv.get(f"/kiosk/t/{TOKEN}").data.decode()
    assert "Systeem <span>vergrendeld</span>" in tv.get("/kiosk/koppelen").data.decode()
    assert _versie(tv) == "noodstop"


def test_de_tv_wisselt_zelf_met_de_afstandsbediening(app, ingelogde_client, db):
    """Knop omlaag in de tv-app: de prijzenlijst; omhoog: de dia's. Zonder inlog of csrf_token, met het token van de tv."""
    tv = _gekoppeld(app, ingelogde_client, scherm="dias")
    oud = _versie(tv)
    resp = tv.post(f"/kiosk/t/{TOKEN}/scherm", json={"toont": "prijzen"})
    assert resp.status_code == 200 and resp.get_json()["toont"] == "prijzen"
    assert _rij(db)["scherm"] == "prijzen" and _rij(db)["naam"] == "Bar"
    assert _versie(tv) != oud  # de tv herlaadt naar de prijzenlijst
    tv.post(f"/kiosk/t/{TOKEN}/scherm", json={"toont": "dias"})
    assert _rij(db)["scherm"] == "dias"
    # Een tv die niet gekoppeld is, of een ongeldig token: niets.
    assert app.test_client().post("/kiosk/t/OnbekendToken123456789/scherm", json={"toont": "prijzen"}).status_code == 404
    assert app.test_client().post("/kiosk/t/kort/scherm", json={}).status_code == 404


def test_standaard_toont_een_nieuwe_tv_de_dias(app, ingelogde_client, db):
    tv = app.test_client()
    ingelogde_client.post("/kiosk/tvs/koppelen", data={"csrf_token": _csrf(ingelogde_client), "code": "".join(_code(tv)),
                                                       "naam": "Bar"})
    assert _rij(db)["scherm"] == "dias"
