"""Mappen, momenten en de schijnwerper op de kantine-tv (1.76.0, zie kiosk_momenten.py): een map met één klik aan of uit
(en met een begin en einde vanzelf), een dia met een tijdslot, de eerste minuten groot op alle tv's (ook het
prijzenscherm), daarna een balk, en bijsturen met Nu tonen, Stop en Later; ook in de app."""

import json
from datetime import datetime, timedelta

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, app_client  # noqa: F401 (fixture)

import kiosk_momenten

NU = datetime(2026, 10, 31, 16, 30)


def _t(minuten):
    return (NU + timedelta(minutes=minuten)).strftime("%Y-%m-%d %H:%M")


def _straks(uren=2, minuten=0):
    """Een moment over een paar uur (de schermen krijgen de momenten van de komende 24 uur), op de minuut."""
    return (datetime.now() + timedelta(hours=uren, minutes=minuten)).strftime("%Y-%m-%d %H:%M")


def _map(db, naam="Halloween feest", vanaf=None, tot=None, actief=1):
    map_id = db.execute(
        "INSERT INTO kiosk_dia_mappen (naam, actief, vanaf, tot, volgorde, aangemaakt_op) VALUES (?, ?, ?, ?, 1, '2026-10-29 12:00')",
        (naam, actief, vanaf, tot),
    ).lastrowid
    db.commit()
    return map_id


def _dia(db, titel, map_id=None, moment=None, sjabloon="titel_tekst_groot", effect=None, minuten=5, balk=None,
         moment_tot=None, tekst=None, label=None, afbeelding=None):
    dia_id = db.execute(
        """INSERT INTO kiosk_sponsoren (sjabloon, titel, tekst, afbeelding, weergave_duur_seconden, volgorde, actief,
               aangemaakt_op, map_id, moment, moment_tot, schijnwerper_minuten, effect, balk_tekst, label)
           VALUES (?, ?, ?, ?, 10, 0, 1, '2026-10-29 12:00', ?, ?, ?, ?, ?, ?, ?)""",
        (sjabloon, titel, tekst, afbeelding, map_id, moment, moment_tot, minuten, effect, balk, label),
    ).lastrowid
    db.commit()
    return dia_id


def _dias(db):
    return db.execute("SELECT * FROM kiosk_sponsoren WHERE actief = 1").fetchall()


# ---------- Wanneer een dia in de diashow staat ----------


def test_een_moment_loopt_tot_het_volgende_moment_in_de_map(db):
    m = _map(db, vanaf=_t(-60), tot=_t(9 * 60))
    heks = _dia(db, "Heksenbrouwsel", m, _t(-30))
    snack = _dia(db, "Snack", m, _t(30))
    laatste = _dia(db, "Shout-out", m, _t(8 * 60))
    los = _dia(db, "Een moment zonder map", None, _t(60))
    altijd = _dia(db, "Programma", m)
    v = kiosk_momenten.vensters(db, _dias(db), NU)
    assert v[heks] == (NU - timedelta(minutes=30), NU + timedelta(minutes=30))  # tot de snack
    assert v[snack] == (NU + timedelta(minutes=30), NU + timedelta(hours=8))
    assert v[laatste] == (NU + timedelta(hours=8), NU + timedelta(hours=9))  # tot het einde van de map
    assert v[los] == (NU + timedelta(hours=1), NU + timedelta(hours=2))  # zonder map: een uur
    assert v[altijd] == (NU - timedelta(hours=1), NU + timedelta(hours=9))  # de map zelf

    # Een eigen einde, een voorbij moment, en een map die uit staat.
    eigen = _dia(db, "Eigen einde", m, _t(-90), moment_tot=_t(-70))
    assert eigen not in kiosk_momenten.vensters(db, _dias(db), NU)
    kiosk_momenten.zet_map_aan(db, m, False)
    assert set(kiosk_momenten.vensters(db, _dias(db), NU)) == {los}


def test_een_map_met_begin_en_einde_gaat_vanzelf_aan_en_uit(db):
    m = _map(db, vanaf=_t(60), tot=_t(120))
    rij = db.execute("SELECT * FROM kiosk_dia_mappen WHERE id = ?", (m,)).fetchone()
    assert kiosk_momenten.map_status(rij, NU) == "straks"
    assert kiosk_momenten.map_status(rij, NU + timedelta(minutes=90)) == "aan"
    assert kiosk_momenten.map_status(rij, NU + timedelta(minutes=150)) == "voorbij"
    _, fout = kiosk_momenten.bewaar_map(db, m, "Halloween feest", _t(60), _t(30))
    assert fout == "Het einde van de map ligt voor het begin."


def test_de_diashow_krijgt_het_tijdslot_en_het_effect_mee(client, db):
    m = _map(db)
    moment = _straks()
    _dia(db, "Feest start!", m, moment, sjabloon="griezel", effect="vuur", tekst="Super Saturday\n€ 8,-")
    _dia(db, "Programma", m, effect="programma", sjabloon="afbeelding_volledig", afbeelding="programma.jpg")
    _dia(db, "Uit", _map(db, "Oud feest", actief=0))
    html = client.get("/kiosk/scherm").get_data(as_text=True)
    assert 'data-van="' in html and 'data-effect="vuur"' in html and 'data-effect="programma"' in html
    assert "gz-titel" in html and "Feest start!" in html and "gz-regel gz-prijs" in html  # de griezeldia
    assert f"{moment[11:16]} uur" in html  # het label is de tijd van het moment
    assert ">Uit<" not in html  # een map die uit staat, doet niet mee
    assert "kiosk_effecten.css" in html and "kiosk_effecten.js" in html and "window.kioskNu" in html
    assert '<div class="onderschrift">Programma</div>' not in html  # een ontwerp met effect heeft zijn eigen tekst
    # Het programma weet welke tijdsloten er in zijn map zijn, en waar zijn regels staan.
    opties = json.loads(html.split('data-effect="programma" data-opties="')[1].split('"')[0].replace("&#34;", '"'))
    assert opties["rijen"][0] == "16:00" and [x["tijd"] for x in opties["momenten"]] == [moment[11:16]]


# ---------- De schijnwerper ----------


def test_de_schermen_krijgen_de_momenten_en_de_klok(client, db):
    m = _map(db)
    moment = _straks()
    dia = _dia(db, "Heksenbrouwsel", m, moment, effect="heksenketel", balk="4 shotjes voor € 6")
    antwoord = client.get("/kiosk/welkom").get_json()
    assert isinstance(antwoord["nu"], int)
    momenten = antwoord["momenten"]
    item = next(x for x in momenten["momenten"] if x["id"] == dia)
    assert item["tijd"] == moment[11:16] and item["balk"] == "4 shotjes voor € 6" and item["effect"] == "heksenketel"
    assert item["spot"] - item["van"] == 5 * 60 * 1000  # vijf minuten in de schijnwerper
    assert item["opties"]["prijs"] == [76, 52]  # de prijs in het ontwerp
    # Niets veranderd: dan stuurt de server ze niet nog eens (de schermen vragen het elke 5 seconden).
    assert client.get(f"/kiosk/welkom?mv={momenten['versie']}").get_json()["momenten"] is None
    # Beide schermen hebben de schijnwerper en de klok.
    for pad in ("/kiosk/scherm", "/kiosk/prijzen"):
        html = client.get(pad).get_data(as_text=True)
        assert 'id="kiosk-moment"' in html and "kioskMomentenBijwerken" in html and "window.kioskNu" in html
    assert "kiosk_scherm_stijl.css" in client.get("/kiosk/prijzen").get_data(as_text=True)


def test_nu_tonen_stop_en_later_op_de_site(ingelogde_client, client, db):
    m = _map(db)
    dia = _dia(db, "Duivelsbloed", m, "2099-10-31 20:00", effect="duivel")
    kop = {"csrf_token": _csrf(ingelogde_client), "terug": "/kiosk#momenten"}
    resp = ingelogde_client.post(f"/kiosk/momenten/{dia}/nu", data=kop)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/kiosk#momenten")
    handmatig = client.get("/kiosk/welkom").get_json()["momenten"]["handmatig"]
    assert handmatig["id"] == dia
    assert "Stop de schijnwerper" in ingelogde_client.get("/kiosk").get_data(as_text=True)

    ingelogde_client.post("/kiosk/momenten/stop", data=kop)
    assert client.get("/kiosk/welkom").get_json()["momenten"]["handmatig"] is None

    ingelogde_client.post(f"/kiosk/momenten/{dia}/later", data=kop)
    assert db.execute("SELECT moment FROM kiosk_sponsoren WHERE id = ?", (dia,)).fetchone()[0] == "2099-10-31 20:15"
    # Een open adres van buiten als 'terug' wordt genegeerd.
    resp = ingelogde_client.post(f"/kiosk/momenten/{dia}/later", data={**kop, "terug": "//elders.nl/x", "minuten": "-15"})
    assert "elders.nl" not in resp.headers["Location"]
    assert db.execute("SELECT moment FROM kiosk_sponsoren WHERE id = ?", (dia,)).fetchone()[0] == "2099-10-31 20:00"
    assert "Voorbeeld schijnwerper" in ingelogde_client.get(f"/kiosk/momenten/{dia}/voorbeeld").get_data(as_text=True)


def test_stop_breekt_een_lopend_moment_af(db):
    m = _map(db)
    dia = _dia(db, "Eindshow", m, _t(-2), effect="zombie")
    assert next(x for x in kiosk_momenten.programma(db, NU) if x["dia"]["id"] == dia)["status"] == "schijnwerper"
    kiosk_momenten.stop_schijnwerper(db, NU)
    gestopt = kiosk_momenten.gestopte_schijnwerper(db, NU)
    assert gestopt["dia_id"] == dia and gestopt["tot"] == NU + timedelta(minutes=3)
    assert next(x for x in kiosk_momenten.programma(db, NU) if x["dia"]["id"] == dia)["status"] == "bezig"


@pytest.mark.parametrize("pad", ["/kiosk/momenten/1/nu", "/kiosk/momenten/stop", "/kiosk/dia-mappen/opslaan"])
def test_bijsturen_alleen_met_rechten(client, pad):
    resp = client.post(pad, data={"csrf_token": _csrf(client)})
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


# ---------- Mappen en dia's beheren ----------


def test_mappen_beheren_op_de_site(ingelogde_client, db):
    kop = {"csrf_token": _csrf(ingelogde_client), "terug": "/kiosk/sponsoren-leden#dias-tabel"}
    ingelogde_client.post("/kiosk/dia-mappen/opslaan", data={**kop, "naam": " Halloween  feest ", "vanaf": "2026-10-31T15:45",
                                                             "tot": "2026-11-01T02:00"})
    m = db.execute("SELECT * FROM kiosk_dia_mappen").fetchone()
    assert (m["naam"], m["vanaf"], m["tot"], m["actief"]) == ("Halloween feest", "2026-10-31 15:45", "2026-11-01 02:00", 1)
    dia = _dia(db, "In de map", m["id"])
    pagina = ingelogde_client.get("/kiosk/sponsoren-leden").get_data(as_text=True)
    assert "Halloween feest" in pagina and "+ Dia in deze map" in pagina
    ingelogde_client.post(f"/kiosk/dia-mappen/{m['id']}/aan", data={**kop, "aan": "0"})
    assert db.execute("SELECT actief FROM kiosk_dia_mappen").fetchone()[0] == 0
    ingelogde_client.post(f"/kiosk/dia-mappen/{m['id']}/verwijderen", data=kop)
    assert db.execute("SELECT COUNT(*) FROM kiosk_dia_mappen").fetchone()[0] == 0
    assert db.execute("SELECT map_id FROM kiosk_sponsoren WHERE id = ?", (dia,)).fetchone()[0] is None  # nu Algemeen


def test_een_dia_met_moment_en_effect_opslaan(ingelogde_client, db):
    m = _map(db)
    resp = ingelogde_client.post("/kiosk/sponsoren-leden/sponsoren/nieuw", data={
        "csrf_token": _csrf(ingelogde_client), "sjabloon": "griezel", "titel": "Griezelshot", "tekst": "De hele avond\n€ 8",
        "weergave_duur_seconden": "10", "actief": "1", "map_id": str(m), "moment": "2026-10-31T16:00",
        "moment_tot": "2026-10-31T15:00", "schijnwerper_minuten": "7", "effect": "toverglans", "prijs_links": "50",
        "prijs_boven": "50", "balk_tekst": "Griezelshot:  4 voor € 8", "label": "De hele avond",
    })
    assert resp.status_code == 302 and resp.headers["Location"].endswith("#dias-tabel")
    d = db.execute("SELECT * FROM kiosk_sponsoren ORDER BY id DESC").fetchone()
    assert (d["map_id"], d["moment"], d["moment_tot"], d["schijnwerper_minuten"], d["effect"]) == \
        (m, "2026-10-31 16:00", None, 7, "toverglans")  # een einde voor het begin is weggelaten
    assert (d["balk_tekst"], d["label"], d["effect_opties"]) == ("Griezelshot: 4 voor € 8", "De hele avond", None)

    # Een afbeelding met een effect: de aangetikte plek van de prijs blijft bewaard.
    ingelogde_client.post(f"/kiosk/sponsoren-leden/sponsoren/{d['id']}/bewerken", data={
        "csrf_token": _csrf(ingelogde_client), "sjabloon": "afbeelding_volledig", "titel": "Duivelsbloed",
        "weergave_duur_seconden": "10", "actief": "1", "effect": "duivel", "prijs_links": "70.5", "prijs_boven": "60",
        "schijnwerper_minuten": "99"})
    d = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (d["id"],)).fetchone()
    assert json.loads(d["effect_opties"]) == {"prijs": [70.5, 60.0]} and d["schijnwerper_minuten"] == 30
    assert d["map_id"] is None  # geen map gekozen: Algemeen


def test_programma_op_de_kiosk_hub(ingelogde_client, db):
    _dia(db, "Heksenbrouwsel", _map(db), (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
    pagina = ingelogde_client.get("/kiosk").get_data(as_text=True)
    assert "Momenten" in pagina and "Heksenbrouwsel" in pagina and "Straks" in pagina and "+15 min" in pagina


# ---------- In de app ----------


def test_momenten_en_mappen_in_de_app(app_client, db):  # noqa: F811
    m = _map(db)
    dia = _dia(db, "Toverstaf", m, (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"), balk="3 voor € 6")
    overzicht = app_client.get("/api/app/kantine-tv").get_json()
    item = next(x for x in overzicht["momenten"] if x["id"] == dia)
    assert (item["titel"], item["map"], item["status"], item["balk"]) == ("Toverstaf", "Halloween feest", "straks", "3 voor € 6")
    assert overzicht["schijnwerper"] is False

    aan = _post(app_client, f"/api/app/kantine-tv/momenten/{dia}/nu", verzoek_id="mo1").get_json()
    assert aan["schijnwerper"] is True and "groot op alle tv's" in aan["melding"]
    uit = _post(app_client, "/api/app/kantine-tv/schijnwerper/stop").get_json()
    assert uit["schijnwerper"] is False
    later = _post(app_client, f"/api/app/kantine-tv/momenten/{dia}/later", minuten=15, verzoek_id="mo2").get_json()
    assert "komt nu om" in later["melding"]
    assert _post(app_client, "/api/app/kantine-tv/momenten/999999/nu").status_code == 404

    dias = app_client.get("/api/app/kantine-tv/dias").get_json()
    assert dias["mappen"][0]["naam"] == "Halloween feest" and dias["mappen"][0]["dias"] == 1
    uitgezet = _post(app_client, f"/api/app/kantine-tv/mappen/{m}", aan=False).get_json()
    assert uitgezet["mappen"][0]["aan"] is False and "staat nu uit" in uitgezet["melding"]


# ---------- De griezeldia als poster en als programma (1.77.0) ----------


def test_de_regels_van_een_poster_en_een_programma():
    assert kiosk_momenten.griezel_delen(["Halloween shot!", "3 shotjes voor", "€ 6,-"]) == {
        "onder_titel": ["Halloween shot!"], "aanbod": "3 shotjes voor", "prijs": "€ 6,-", "na_prijs": []}
    assert kiosk_momenten.griezel_delen(["€ 8,-", "Bekendmaking beste outfit!"]) == {
        "onder_titel": [], "aanbod": None, "prijs": "€ 8,-", "na_prijs": ["Bekendmaking beste outfit!"]}
    assert kiosk_momenten.griezel_delen(["Super Saturday"])["onder_titel"] == ["Super Saturday"]  # geen prijs: geen bord
    rijen, overig = kiosk_momenten.programma_regels(
        ["16:00 Feest start!", "17.00 uur - Heksenbrouwsel", "De hele avond:", "€ 8,-", "25:00 Geen tijd"],
        [{"tijd": "17:00", "kleur": "#7dff3a"}])
    assert [(r["tijd"], r["naam"]) for r in rijen] == [("16:00", "Feest start!"), ("17:00", "Heksenbrouwsel")]
    assert rijen[1]["kleur"] == "#7dff3a"  # de kleur van het moment op die tijd
    assert rijen[0]["kleur"] == kiosk_momenten.PROGRAMMA_KLEUREN[0]  # geen moment: een vaste kleur
    assert overig == ["De hele avond:", "€ 8,-", "25:00 Geen tijd"]
    # De tekening hoort bij een griezeldia; een onbekende tekening wordt niet bewaard.
    assert json.loads(kiosk_momenten.schoon_opties(None, None, None, None, "griezel", "ketel")) == {"tekening": "ketel"}
    assert kiosk_momenten.schoon_opties("vuur", None, None, None, "afbeelding_volledig", "ketel") is None
    assert kiosk_momenten.schoon_opties("vuur", None, None, None, "griezel", "onbekend") is None


def test_een_poster_en_een_programma_op_de_tv(client, db):
    m = _map(db)
    moment = _straks()
    poster = _dia(db, "Heksenbrouwsel", m, moment, sjabloon="griezel", effect="heksenketel",
                  tekst="4 shotjes voor\n€ 6,-\nDe hele avond")
    db.execute("UPDATE kiosk_sponsoren SET effect_opties = ? WHERE id = ?", (json.dumps({"tekening": "ketel"}), poster))
    db.commit()
    _dia(db, "Halloween feest", m, sjabloon="griezel", effect="programma",
         tekst=f"{moment[11:16]} Heksenbrouwsel\n21:00 Eindshow!\nDe hele avond:\nGriezelshot\n€ 8,-")
    html = client.get("/kiosk/scherm").get_data(as_text=True)
    assert "gz gz--poster" in html and "gz-tekening--ketel" in html and "<svg" in html
    assert '<p class="gz-bord-aanbod">4 shotjes voor</p>' in html and '<p class="gz-bord-prijs">€ 6,-</p>' in html
    assert '<div class="gz-voet"><p>De hele avond</p></div>' in html  # een regel na de prijs
    assert "gz gz--programma" in html and '<p class="gz-programma-kop">Programma</p>' in html
    assert f'data-tijd="{moment[11:16]}" style="--rij-kleur: #7dff3a;"' in html  # de kleur van het Heksenbrouwsel
    assert '<p class="gz-bord-kop">De hele avond:</p>' in html and '<p class="gz-bord-prijs">€ 8,-</p>' in html


def test_een_griezeldia_met_tekening_opslaan_en_het_voorbeeld(ingelogde_client, db):
    ingelogde_client.post("/kiosk/sponsoren-leden/sponsoren/nieuw", data={
        "csrf_token": _csrf(ingelogde_client), "sjabloon": "griezel", "titel": "Duivelsbloed", "tekst": "2 voor\n€ 4,-",
        "weergave_duur_seconden": "10", "actief": "1", "effect": "duivel", "tekening": "duivel"})
    d = db.execute("SELECT * FROM kiosk_sponsoren ORDER BY id DESC").fetchone()
    assert json.loads(d["effect_opties"]) == {"tekening": "duivel"} and kiosk_momenten.tekening_van(d) == "duivel"
    pagina = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{d['id']}/bewerken").get_data(as_text=True)
    assert '<option value="duivel" selected>' in pagina and 'id="griezel-voorbeeld"' in pagina
    # Het live voorbeeld: de dia zoals op de tv, in een iframe op de eigen site.
    resp = ingelogde_client.get("/kiosk/griezel-voorbeeld?titel=Duivelsbloed&tekst=2+voor%0A%E2%82%AC+4%2C-"
                                "&effect=duivel&tekening=duivel")
    assert resp.status_code == 200 and resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    html = resp.get_data(as_text=True)
    assert "gz-tekening--duivel" in html and '<p class="gz-bord-prijs">€ 4,-</p>' in html and "kiosk_effecten.js" in html


def test_het_griezelvoorbeeld_alleen_met_rechten(client):
    resp = client.get("/kiosk/griezel-voorbeeld")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
