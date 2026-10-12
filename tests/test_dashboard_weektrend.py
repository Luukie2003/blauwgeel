"""De omzettrend op het dashboard per week: vergelijkt de laatste volledige week met de week ervoor en met het
gemiddelde, met het aantal thuiswedstrijden erbij."""

from datetime import date, timedelta

import pytest

import voorspelling
from helpers import bouw_weektrend

VANDAAG = date(2026, 10, 14)  # woensdag in week 42
KAART = "/dashboard/omzettrend"  # de kaart die het dashboard na het laden ophaalt


def _week(maandag, omzet, status="compleet"):
    jaar, week, _ = maandag.isocalendar()
    return {
        "jaar": jaar, "week": week, "van": maandag.isoformat(), "tot": (maandag + timedelta(days=6)).isoformat(),
        "omzet": omzet, "status": status,
    }


def _weken(omzetten, lopend=True, eerste_status="compleet"):
    """Weken t/m de week van VANAF (nieuwste eerst, zoals omzet_per_week): de laatste is de lopende week."""
    maandag_nu = VANDAAG - timedelta(days=VANDAAG.weekday())
    aantal = len(omzetten)
    weken = []
    for i, omzet in enumerate(omzetten):
        maandag = maandag_nu - timedelta(days=7 * (aantal - 1 - i))
        status = "loopt_nog" if (lopend and i == aantal - 1) else ("begin" if i == 0 and eerste_status == "begin" else "compleet")
        weken.append(_week(maandag, omzet, status))
    return list(reversed(weken))


def test_balken_staan_op_volgorde_met_de_lopende_week_apart():
    weken = _weken([100, 200, 300, 400])  # wk 39, 40, 41 compleet, wk 42 loopt
    uitkomst = bouw_weektrend(weken, [], VANDAAG)

    assert [b["week"] for b in uitkomst["balken"]] == [39, 40, 41, 42]
    assert [b["volledig"] for b in uitkomst["balken"]] == [True, True, True, False]
    assert uitkomst["balken"][-1]["lopend"] is True and not any(b["lopend"] for b in uitkomst["balken"][:-1])
    assert [round(b["hoogte_pct"]) for b in uitkomst["balken"]] == [25, 50, 75, 100]
    assert uitkomst["balken"][0]["datum_kort"] == "21-09"


def test_vergelijking_met_de_week_ervoor_en_het_gemiddelde():
    # wk 36..41 compleet (vier weken voor het gemiddelde + de week ervoor), wk 42 loopt (en telt niet mee).
    weken = _weken([300, 100, 100, 100, 100, 150, 9999])
    sv = bouw_weektrend(weken, [], VANDAAG)["samenvatting"]

    assert sv["week"] == 41 and sv["omzet"] == 150 and sv["week_ervoor"] == 40
    assert sv["verschil_percentage"] == pytest.approx(50)  # 150 tegen 100
    assert sv["aantal_voor_gemiddelde"] == 4 and sv["gemiddelde"] == 100  # de 4 weken voor wk 41: wk 37..40
    assert sv["verschil_gemiddelde_percentage"] == pytest.approx(50)


def test_de_lopende_en_onvolledige_weken_tellen_niet_mee():
    weken = _weken([111, 200, 300, 5], eerste_status="begin")  # wk 39 begin (onvolledig), 40 en 41 compleet, 42 loopt
    uitkomst = bouw_weektrend(weken, [], VANDAAG)
    assert [b["volledig"] for b in uitkomst["balken"]] == [False, True, True, False]
    assert uitkomst["samenvatting"]["week"] == 41 and uitkomst["samenvatting"]["week_ervoor"] == 40


def test_zonder_twee_volledige_weken_geen_vergelijking():
    assert bouw_weektrend(_weken([100, 50]), [], VANDAAG)["samenvatting"] is None  # 1 volledige week + de lopende
    assert bouw_weektrend(_weken([50], lopend=True), [], VANDAAG)["samenvatting"] is None
    leeg = bouw_weektrend([], [], VANDAAG)
    assert leeg == {"balken": [], "samenvatting": None}


def test_week_ervoor_zonder_omzet_geeft_geen_percentage():
    sv = bouw_weektrend(_weken([0, 100, 5]), [], VANDAAG)["samenvatting"]
    assert sv["week"] == 41 and sv["verschil_percentage"] is None and sv["verschil_gemiddelde_percentage"] is None


def test_hooguit_acht_weken():
    uitkomst = bouw_weektrend(_weken(list(range(100, 112))), [], VANDAAG)
    assert len(uitkomst["balken"]) == 8 and uitkomst["balken"][-1]["lopend"]


def test_thuiswedstrijden_per_week():
    weken = _weken([100, 200, 300])  # wk 40, 41, 42
    za_40, za_41 = date(2026, 10, 3), date(2026, 10, 10)
    wedstrijden = [za_40.isoformat(), za_41.isoformat(), (za_41 + timedelta(days=1)).isoformat(), "2020-01-01"]

    uitkomst = bouw_weektrend(weken, wedstrijden, VANDAAG)

    assert [b["thuiswedstrijden"] for b in uitkomst["balken"]] == [1, 2, 0]  # wk 40: 1, wk 41: 2, wk 42: 0
    assert uitkomst["samenvatting"]["thuiswedstrijden"] == 2 and uitkomst["samenvatting"]["thuiswedstrijden_ervoor"] == 1


# ---------- Op het dashboard zelf ----------


def _ga_uit_van(monkeypatch, omzetten, **kwargs):
    """Zet weken in de plaats van de echte berekening, relatief aan vandaag."""
    vandaag = date.today()
    maandag_nu = vandaag - timedelta(days=vandaag.weekday())
    weken = []
    for i, omzet in enumerate(omzetten):
        maandag = maandag_nu - timedelta(days=7 * (len(omzetten) - 1 - i))
        weken.append(_week(maandag, omzet, "loopt_nog" if i == len(omzetten) - 1 else "compleet"))
    monkeypatch.setattr(voorspelling, "omzet_per_week", lambda db, nu=None: list(reversed(weken)))
    return weken


def test_dashboard_toont_de_weekvergelijking(ingelogde_client, db, monkeypatch):
    weken = _ga_uit_van(monkeypatch, [800, 900, 1000, 1200, 50])
    vorige, ervoor = weken[-2], weken[-3]
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, afgelast) VALUES ('Za1', ?, 'Za1 - Tegenstander', 1, 0)",
        (vorige["van"],),
    )
    db.commit()

    tekst = ingelogde_client.get(KAART).data.decode()

    assert f"Vorige week (wk {vorige['week']})" in tekst and "&euro; 1200" in tekst.replace("€", "&euro;")
    assert "+20%" in tekst  # 1200 tegen 1000
    assert f"t.o.v. wk {ervoor['week']}" in tekst
    assert "1 thuiswedstrijd in wk" in tekst
    assert "omzet-bar-afwijkend" in tekst and "loopt" in tekst  # de lopende week is gestippeld
    assert "Laatste dag:" not in tekst and "t.o.v. gemiddelde" not in tekst  # de misleidende oude vergelijking is weg


def test_dashboard_met_te_weinig_weken_zegt_dat(ingelogde_client, db, monkeypatch):
    _ga_uit_van(monkeypatch, [800, 50])
    assert "Nog te weinig volledige weken voor een vergelijking" in ingelogde_client.get(KAART).data.decode()


def test_dashboard_valt_terug_op_tellingen_als_de_weekberekening_stuk_gaat(ingelogde_client, db, monkeypatch):
    def stuk(db, nu=None):
        raise RuntimeError("kapot")

    monkeypatch.setattr(voorspelling, "omzet_per_week", stuk)
    resp = ingelogde_client.get(KAART)
    assert resp.status_code == 200  # de kaart blijft werken
    assert "Omzettrend" in resp.data.decode()


def test_top_verkopers_blijven_zichtbaar_bij_de_weektrend(ingelogde_client, db, monkeypatch):
    _ga_uit_van(monkeypatch, [800, 900, 1000, 50])
    pid = db.execute("INSERT INTO producten (naam, categorie, eenheid, verkoopprijs, actief) VALUES ('Toppie', 'Bier', 'Fles', 2, 1)").lastrowid
    cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES (strftime('%Y-%m-%d %H:%M', 'now'), 'T')")
    db.execute(
        "INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs) VALUES (?, ?, 0, 0, 9, 2)",
        (cur.lastrowid, pid),
    )
    db.commit()
    tekst = ingelogde_client.get(KAART).data.decode()
    assert "Top verkopers in de laatste 8 tellingen" in tekst and "Toppie" in tekst


# ---------- Het dashboard zelf wacht niet op de weekcijfers ----------


def test_het_dashboard_rekent_de_weekcijfers_niet_zelf_uit(ingelogde_client, monkeypatch):
    def mag_niet(db, nu=None):
        raise AssertionError("het dashboard mag het voorspelmodel niet aanroepen")

    monkeypatch.setattr(voorspelling, "omzet_per_week", mag_niet)
    resp = ingelogde_client.get("/")
    tekst = resp.data.decode()
    assert resp.status_code == 200
    assert 'id="omzettrend-kaart"' in tekst and f'data-lazy-bron="{KAART}"' in tekst  # de plek waar de kaart in komt
    assert "wordt berekend" in tekst  # tot de cijfers er zijn


def test_de_kaart_is_er_voor_iedereen_die_is_ingelogd(client, db):
    from test_secties_rechten import _login, _maak_vrijwilliger

    _maak_vrijwilliger(db, "vrijwilliger", "voorraad")
    _login(client, "vrijwilliger")
    assert client.get(KAART).status_code == 200


def test_de_kaart_vraagt_inloggen(client):
    resp = client.get(KAART)
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
