"""Tests voor de verschil-trendgrafiek op /kassa/geschiedenis
(bereken_kassa_verschil_trend in app.py), inclusief de signalering als het
handmatig ingetypte PayPal-bedrag sterk afwijkt van de omzet die uit de
voorraadtellingen in dezelfde periode volgt."""

from app import bereken_kassa_verschil_trend


def _kassa_telling(db, datum, contante_omzet=0, verschil=0, afgesloten=1):
    cur = db.execute(
        """INSERT INTO kassa_tellingen (datum, contante_omzet, verschil, geteld_bedrag, afgesloten)
           VALUES (?, ?, ?, 0, ?)""",
        (datum, contante_omzet, verschil, afgesloten),
    )
    db.commit()
    return cur.lastrowid


def _voorraad_omzet(db, datum, verkocht=10, verkoopprijs=2.0):
    product = db.execute("SELECT id FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'Test')", (datum,))
    db.execute(
        """INSERT INTO telling_regels
           (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
           VALUES (?, ?, 0, 0, ?, 0, ?)""",
        (cur.lastrowid, product["id"], verkocht, verkoopprijs),
    )
    db.commit()


def test_open_concept_telling_telt_niet_mee(db):
    _kassa_telling(db, "2026-01-01 10:00", afgesloten=0)
    trend = bereken_kassa_verschil_trend(db)
    assert trend["balken"] == []


def test_signaleert_afwijkend_paypal_bedrag(db):
    _kassa_telling(db, "2026-01-01 10:00")
    _voorraad_omzet(db, "2026-01-01 15:00", verkocht=10, verkoopprijs=2.0)  # € 20 omzet
    telling_b = _kassa_telling(db, "2026-01-02 10:00", contante_omzet=100, verschil=5)

    trend = bereken_kassa_verschil_trend(db)
    balk_b = next(b for b in trend["balken"] if b["id"] == telling_b)
    assert balk_b["afwijkend"] is True
    assert balk_b["verkoop_omzet"] == 20.0


def test_geen_signaal_als_paypal_bedrag_ongeveer_klopt(db):
    _kassa_telling(db, "2026-01-01 10:00")
    _voorraad_omzet(db, "2026-01-01 15:00", verkocht=10, verkoopprijs=2.0)  # € 20 omzet
    telling_b = _kassa_telling(db, "2026-01-02 10:00", contante_omzet=22, verschil=0)

    trend = bereken_kassa_verschil_trend(db)
    balk_b = next(b for b in trend["balken"] if b["id"] == telling_b)
    assert balk_b["afwijkend"] is False


def test_eerste_telling_zonder_context_krijgt_geen_signaal(db):
    """De allereerste afgesloten kassatelling ooit heeft geen vorige telling
    om een periode mee af te bakenen, dus kan niet zinnig vergeleken worden."""
    telling_a = _kassa_telling(db, "2026-01-01 10:00", contante_omzet=500, verschil=0)
    trend = bereken_kassa_verschil_trend(db)
    balk_a = next(b for b in trend["balken"] if b["id"] == telling_a)
    assert balk_a["afwijkend"] is False
    assert balk_a["verkoop_omzet"] is None


def test_kassa_geschiedenis_toont_afwijking_op_de_pagina(ingelogde_client, db):
    _kassa_telling(db, "2026-01-01 10:00")
    _voorraad_omzet(db, "2026-01-01 15:00", verkocht=10, verkoopprijs=2.0)
    _kassa_telling(db, "2026-01-02 10:00", contante_omzet=100, verschil=5)

    resp = ingelogde_client.get("/kassa/geschiedenis")
    assert resp.status_code == 200
    assert "wijkt af".encode() in resp.data
    assert "omzet-bar-tekort".encode() not in resp.data
    assert "omzet-bar-overschot".encode() in resp.data
