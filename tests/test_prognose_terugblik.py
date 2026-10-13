"""Bestellen > Prognose en verkoop: per telling wat het model toen voorspelde en wat er werkelijk verkocht is."""

from datetime import timedelta

from test_voorspelling import MAANDAG, _bouw_geschiedenis, _product, _twee_keer_per_week

from voorspelling import terugblik, vat_terugblik_samen


def test_een_regelmatige_kantine_wordt_goed_voorspeld(db):
    bier, cola = _product(db, "Bier", prijs=2.2), _product(db, "Cola", prijs=2.0)
    tijden = _twee_keer_per_week(5)
    laatste = _bouw_geschiedenis(db, {bier: 20, cola: 8}, tijdstippen=tijden)

    perioden = terugblik(db, laatste + timedelta(hours=1))

    assert perioden and perioden[0]["tot"] == laatste  # nieuwste eerst
    assert len(perioden) == len(tijden) - 1 - 2  # de nulmeting en de eerste twee periodes hebben te weinig geschiedenis
    nieuwste = perioden[0]
    assert abs(nieuwste["pct"]) < 10  # zo regelmatig: het model zit er nauwelijks naast
    assert nieuwste["werkelijk"] == sum(p["verkocht"] * p["prijs"] for p in nieuwste["producten"])
    assert {p["naam"] for p in nieuwste["producten"]} == {"Bier", "Cola"}
    samen = vat_terugblik_samen(perioden)
    assert samen["aantal"] == len(perioden) and samen["binnen"] == len(perioden)


def test_een_onverwacht_drukke_periode_valt_op(db):
    bier = _product(db, "Bier", prijs=2.0)
    tijden = [MAANDAG + timedelta(days=7 * i) for i in range(8)]
    _bouw_geschiedenis(db, {bier: 20}, tijdstippen=tijden)
    # Nog een week, maar nu drie keer zo druk als gewoonlijk.
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", ((tijden[-1] + timedelta(days=7)).strftime("%Y-%m-%d %H:%M"),)).lastrowid
    db.execute("INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs) VALUES (?, ?, 470, 50, 420, 2.0)", (t, bier))
    db.commit()

    nieuwste = terugblik(db, tijden[-1] + timedelta(days=7, hours=1))[0]

    assert nieuwste["pct"] > 100 and nieuwste["werkelijk"] == 840
    assert vat_terugblik_samen([nieuwste])["meer_verkocht"] == 1


def test_te_weinig_tellingen_geeft_niets(db):
    bier = _product(db, "Bier")
    laatste = _bouw_geschiedenis(db, {bier: 20}, tijdstippen=[MAANDAG, MAANDAG + timedelta(days=7)])
    assert terugblik(db, laatste) == [] and vat_terugblik_samen([]) is None


def test_de_pagina_laadt_de_vergelijking_apart(ingelogde_client, db):
    tekst = ingelogde_client.get("/prognose/terugblik").data.decode()
    assert 'data-lazy-bron="/prognose/terugblik/resultaat"' in tekst
    assert "te weinig tellingen" in ingelogde_client.get("/prognose/terugblik/resultaat").data.decode()
    assert 'href="/prognose/terugblik"' in ingelogde_client.get("/").data.decode()  # in het menu

    bier = _product(db, "Bier")
    _bouw_geschiedenis(db, {bier: 20}, tijdstippen=_twee_keer_per_week(4))
    fragment = ingelogde_client.get("/prognose/terugblik/resultaat").data.decode()
    assert "Per telling" in fragment and "voorspeld" in fragment and "Bier" in fragment
    assert db.execute("SELECT COUNT(*) FROM paginabezoeken WHERE endpoint = 'prognose_terugblik_resultaat'").fetchone()[0] == 0
