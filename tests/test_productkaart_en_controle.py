"""De nettere productkaart (vaste eenheden, merk, 'Niet tellen', unieke artikelcode), de gegevenscontrole en het
overzicht Omzet en kassa met de kaartbetalingen."""

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from gegevenscontrole import controleer
from productkaart import EENHEDEN, normaliseer


def _product(db, naam, **velden):
    standaard = {
        "categorie": "Fris", "eenheid": "Fles", "voorraad": 10, "min_voorraad": 5, "verkoopprijs": 2.0,
        "inkoopprijs": 14.64, "actief": 1, "besteleenheid": "Krat", "besteleenheid_factor": 24, "artikelcode": None,
    }
    standaard.update(velden)
    kolommen = ", ".join(["naam", *standaard])
    cur = db.execute(
        f"INSERT INTO producten ({kolommen}) VALUES ({', '.join('?' * (len(standaard) + 1))})",
        (naam, *standaard.values()),
    )
    db.commit()
    return cur.lastrowid


def _formulier(client, **extra):
    data = {
        "csrf_token": _csrf(client), "naam": "Nieuw Flesje", "categorie": "Fris", "eenheid": "Fles", "voorraad": "0",
        "min_voorraad": "0", "bestel_hoeveelheid": "0", "verkoopprijs": "2", "inkoopprijs": "0", "actief": "on",
        "besteleenheid_factor": "1",
    }
    data.update(extra)
    return data


# ---------- Productkaart ----------


def test_een_eenheid_krijgt_de_schrijfwijze_uit_de_lijst():
    assert normaliseer("  fles ", EENHEDEN) == "Fles"
    assert normaliseer("STUKS", EENHEDEN) == "Stuks"
    assert normaliseer("Flesje", EENHEDEN) == "Flesje"  # staat niet in de lijst: blijft zoals het is
    assert normaliseer("", EENHEDEN) == ""


def test_kiezen_uit_de_lijst_of_anders(ingelogde_client, db):
    ingelogde_client.post("/producten/nieuw", data=_formulier(ingelogde_client, eenheid="blik", besteleenheid="__anders__",
                                                             besteleenheid_anders="Sixpack", merk="  Coca  Cola "))
    p = db.execute("SELECT * FROM producten WHERE naam = 'Nieuw Flesje'").fetchone()
    assert (p["eenheid"], p["besteleenheid"], p["merk"]) == ("Blik", "Sixpack", "Coca Cola")


def test_de_productkaart_toont_de_keuzelijsten(ingelogde_client, db):
    pid = _product(db, "Met Plastic", besteleenheid="Plastic")
    tekst = ingelogde_client.get(f"/producten/{pid}/bewerken").data.decode()
    assert '<select id="eenheid" name="eenheid"' in tekst and '<option value="Fles" selected>' in tekst
    # 'Plastic' staat niet in de lijst: 'Anders' is gekozen en het tekstvak toont de huidige waarde.
    assert '<option value="__anders__" selected>' in tekst and 'value="Plastic"' in tekst
    assert 'name="merk"' in tekst and 'name="niet_tellen"' in tekst


def test_een_dubbele_artikelcode_wordt_niet_opgeslagen(ingelogde_client, db):
    _product(db, "Bozu Blueberry", artikelcode="270012")
    resp = ingelogde_client.post(
        "/producten/nieuw", data=_formulier(ingelogde_client, artikelcode=" 270012 "), follow_redirects=True
    )
    assert "hoort al bij &#39;Bozu Blueberry&#39;" in resp.data.decode() or "hoort al bij 'Bozu Blueberry'" in resp.data.decode()
    assert db.execute("SELECT artikelcode FROM producten WHERE naam = 'Nieuw Flesje'").fetchone()[0] is None

    ander = _product(db, "Bozu Hard Icetea", artikelcode="270099", actief=0)
    p = db.execute("SELECT * FROM producten WHERE id = ?", (ander,)).fetchone()
    ingelogde_client.post(f"/producten/{ander}/bewerken", data=_formulier(
        ingelogde_client, naam=p["naam"], artikelcode="270012", actief=""), content_type="multipart/form-data")
    assert db.execute("SELECT artikelcode FROM producten WHERE id = ?", (ander,)).fetchone()[0] == "270099"


def test_niet_tellen_en_de_keuken_staan_niet_in_de_gewone_telling(ingelogde_client, db):
    gewoon = _product(db, "Gewoon Product")
    knop = _product(db, "Kassaknop Wijn", niet_tellen=1)
    keuken = _product(db, "Frikandel Proef", categorie="Keuken")
    tekst = ingelogde_client.get("/tellen").data.decode()
    assert f'name="geteld_{gewoon}"' in tekst
    assert f'name="geteld_{knop}"' not in tekst and f'name="geteld_{keuken}"' not in tekst
    # Ook via een handgemaakt formulier telt het niet mee.
    ingelogde_client.post("/tellen", data={"csrf_token": _csrf(ingelogde_client), f"geteld_{knop}": "1", f"geteld_{gewoon}": "9"})
    assert db.execute("SELECT COUNT(*) FROM telling_regels WHERE product_id = ?", (knop,)).fetchone()[0] == 0


# ---------- Gegevenscontrole ----------


def _controle(db, sleutel):
    for c in controleer(db)["controles"]:
        if c["sleutel"] == sleutel:
            return {r["naam"] for r in c["regels"]}
    return set()


def test_de_gegevenscontrole_vindt_de_bekende_fouten(db):
    _product(db, "Onder Inkoop", inkoopprijs=60.0, verkoopprijs=2.0)  # € 2,50 per fles inkoop, € 2 verkoop
    _product(db, "Per Stuk Ingevuld", inkoopprijs=0.30, verkoopprijs=2.0)  # 99% marge: per stuk i.p.v. per krat
    _product(db, "Krat Zonder Aantal", besteleenheid_factor=1)
    _product(db, "Fust Zonder Glazen", categorie="Telling", eenheid="Fust", verkoopprijs=0, besteleenheid=None,
             besteleenheid_factor=1, inkoopprijs=63.0)
    _product(db, "Gratis Product", verkoopprijs=0)
    _product(db, "Zonder Inkoop", inkoopprijs=0)
    _product(db, "Zonder Minimum", min_voorraad=0)
    _product(db, "Code A", artikelcode="X1")
    _product(db, "Code B", artikelcode="x1 ", actief=0)
    _product(db, "Flesje Product", eenheid="Flesje")
    _product(db, "Kleine Letters", eenheid="stuks")
    _product(db, "Inactief Met Voorraad", actief=0, voorraad=4)

    assert "Onder Inkoop" in _controle(db, "onder_inkoop")
    assert "Per Stuk Ingevuld" in _controle(db, "hoge_marge")
    assert "Krat Zonder Aantal" in _controle(db, "besteleenheid_zonder_aantal")
    assert "Fust Zonder Glazen" in _controle(db, "fust_zonder_glazen")
    assert "Gratis Product" in _controle(db, "geen_verkoopprijs")
    assert "Fust Zonder Glazen" not in _controle(db, "geen_verkoopprijs")  # staat al bij het fust zelf
    assert "Zonder Inkoop" in _controle(db, "geen_inkoopprijs")
    assert "Zonder Minimum" in _controle(db, "geen_minimum")
    assert {"Code A", "Code B"} <= _controle(db, "dubbele_artikelcode")
    assert {"Flesje Product", "Kleine Letters"} <= _controle(db, "afwijkende_eenheid")
    assert "Inactief Met Voorraad" in _controle(db, "inactief_met_voorraad")
    assert "Gewoon Goed" not in _controle(db, "onder_inkoop")


def test_een_kassaknop_hoeft_geen_minimum(db):
    _product(db, "Assorti Wijn Proef", niet_tellen=1, min_voorraad=0)
    assert "Assorti Wijn Proef" not in _controle(db, "geen_minimum")


def test_de_belangrijkste_controles_staan_bovenaan(db):
    _product(db, "Onder Inkoop", inkoopprijs=60.0)
    _product(db, "Zonder Minimum", min_voorraad=0)
    ernst = [c["ernst"] for c in controleer(db)["controles"]]
    assert ernst == sorted(ernst, key={"hoog": 0, "middel": 1, "laag": 2}.get)


def test_de_pagina_alleen_voor_beheerders(ingelogde_client, client, db):
    _product(db, "Onder Inkoop", inkoopprijs=60.0)
    tekst = ingelogde_client.get("/producten/gegevenscontrole").data.decode()
    assert "Verkoopprijs onder de inkoopprijs" in tekst and "Onder Inkoop" in tekst
    menu = ingelogde_client.get("/").data.decode()
    assert 'href="/producten/gegevenscontrole"' in menu

    _maak_vrijwilliger(db, "vrijwilliger", "voorraad")
    ander = client.application.test_client()
    _login(ander, "vrijwilliger")
    assert "alleen voor beheerders" in ander.get("/producten/gegevenscontrole", follow_redirects=True).data.decode()
    assert 'href="/producten/gegevenscontrole"' not in ander.get("/").data.decode()


# ---------- Kaartbetalingen en Omzet en kassa ----------


def _kassatelling(db, datum, contant, kaart=0):
    db.execute(
        """INSERT INTO kassa_tellingen (datum, naam, contante_omzet, kaart_omzet, afgesloten)
           VALUES (?, 'Test', ?, ?, 1)""",
        (datum, contant, kaart),
    )


def _voorraadtelling(db, datum, omzet):
    product = _product(db, f"Verkocht {datum}", verkoopprijs=omzet)
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'Test')", (datum,)).lastrowid
    db.execute(
        """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
           VALUES (?, ?, 1, 0, 1, ?)""",
        (t, product, omzet),
    )


def test_kaartbetalingen_invullen_bij_kassa_tellen(ingelogde_client, db):
    ingelogde_client.post(
        "/kassa/tellen", data={"csrf_token": _csrf(ingelogde_client), "contante_omzet": "100,00", "kaart_omzet": "250,50"}
    )
    t = db.execute("SELECT * FROM kassa_tellingen ORDER BY id DESC LIMIT 1").fetchone()
    assert t["contante_omzet"] == 100 and t["kaart_omzet"] == 250.5
    assert t["verwacht_bedrag"] == round(t["verwacht_bedrag"], 2)  # de kaart telt niet mee voor de la
    tekst = ingelogde_client.get(f"/kassa/tellingen/{t['id']}").data.decode()
    assert "Kaartbetalingen sinds vorige telling" in tekst and "250.50" in tekst


def test_kaartbetalingen_achteraf_verbeteren_raakt_de_la_niet(ingelogde_client, db):
    _kassatelling(db, "2026-10-01 12:00", 80)
    db.commit()
    t = db.execute("SELECT * FROM kassa_tellingen ORDER BY id DESC LIMIT 1").fetchone()
    ingelogde_client.post(f"/kassa/tellingen/{t['id']}/kaartomzet", data={"csrf_token": _csrf(ingelogde_client), "kaart_omzet": "42.10"})
    na = db.execute("SELECT * FROM kassa_tellingen WHERE id = ?", (t["id"],)).fetchone()
    assert na["kaart_omzet"] == 42.1 and na["verwacht_bedrag"] == t["verwacht_bedrag"] and na["verschil"] == t["verschil"]


def test_omzet_en_kassa_zet_paypal_naast_de_voorraad(ingelogde_client, db):
    from helpers import bereken_omzet_en_kassa

    _kassatelling(db, "2026-10-01 12:00", 0)
    _voorraadtelling(db, "2026-10-03 12:00", 300)
    _kassatelling(db, "2026-10-05 12:00", 100, 180)  # PayPal 280, voorraad 300: € 20 meer weg dan afgerekend
    _voorraadtelling(db, "2026-10-08 12:00", 200)
    _kassatelling(db, "2026-10-09 12:00", 150)  # kaart vergeten
    db.commit()

    uitkomst = bereken_omzet_en_kassa(db)

    nieuwste, oudste = uitkomst["periodes"]
    assert (oudste["paypal"], oudste["voorraad"], oudste["verschil"]) == (280, 300, 20)
    assert nieuwste["kaart_leeg"] and nieuwste["verschil"] == 50
    assert uitkomst["totaal"]["verschil"] == 70 and uitkomst["totaal"]["zonder_kaart"] == 1

    tekst = ingelogde_client.get("/kassa/omzet-en-kassa").data.decode()
    assert "Volgens PayPal (contant + kaart)" in tekst and "niet ingevuld" in tekst


def test_omzet_en_kassa_alleen_voor_beheerders(client, db):
    _maak_vrijwilliger(db, "kassier", "kassa")
    _login(client, "kassier")
    assert "alleen voor beheerders" in client.get("/kassa/omzet-en-kassa", follow_redirects=True).data.decode()
    assert client.get("/kassa/tellen").status_code == 200  # de kassa zelf mag wel
