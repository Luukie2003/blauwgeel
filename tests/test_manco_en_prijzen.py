"""Manco opvolgen (manco.py), de pagina Bestellingen en de inkoopprijs uit de factuur (1.67.0)."""

from conftest import stel_csrf_token_in as _csrf
from test_barcodes import AH_DOOS, AH_ZAK, _artikel

import facturen
import manco


def _product(db, naam, voorraad=0, inkoop=10.0, factor=1, besteleenheid=None):
    pid = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, inkoopprijs, actief,
                                  besteleenheid, besteleenheid_factor) VALUES (?, 'Fris', 'stuks', ?, 0, 2.0, ?, 1, ?, ?)""",
        (naam, voorraad, inkoop, besteleenheid, factor),
    ).lastrowid
    db.commit()
    return pid


def _ontvangen_bestelling(db, regels):
    """regels: [(product_id, besteld, ontvangen)] -> een ontvangen bestelling."""
    b = db.execute("INSERT INTO bestellingen (status, aangemaakt_op, ontvangen_op) VALUES ('ontvangen', '2026-10-15 10:00', '2026-10-16 10:00')").lastrowid
    for pid, besteld, ontvangen in regels:
        db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld, aantal_ontvangen, manco) VALUES (?, ?, ?, ?, ?)",
                   (b, pid, besteld, ontvangen, 0 if ontvangen else 1))
    db.commit()
    return b


def test_manco_komt_terug_op_de_bestellijst_tot_het_weer_besteld_is(ingelogde_client, db):
    cola = _product(db, "Cola Manco", voorraad=50, factor=24, besteleenheid="tray")
    sinas = _product(db, "Sinas Manco", voorraad=50)
    b = _ontvangen_bestelling(db, [(cola, 48, 24), (sinas, 10, 0)])
    assert {m["naam"]: m["tekort"] for m in manco.open_manco(db)} == {"Cola Manco": 24, "Sinas Manco": 10}

    pagina = ingelogde_client.get("/bestellijst").data.decode()
    assert f"niet geleverd bij #{b}" in pagina and "24 stuks niet geleverd" in pagina
    assert f'name="aantal_{cola}" min="0" style="width:6rem" aria-label="Aantal te bestellen Cola Manco"\n                                   value="1"' in pagina

    # Weer besteld: dan is het opgevolgd.
    ingelogde_client.post("/bestellijst/aanmaken", data={"csrf_token": _csrf(ingelogde_client), "product_id": [cola], f"aantal_{cola}": "1"})
    assert [m["naam"] for m in manco.open_manco(db)] == ["Sinas Manco"]
    # Niet meer nodig
    ingelogde_client.post(f"/bestellijst/manco/{sinas}/afhandelen", data={"csrf_token": _csrf(ingelogde_client)})
    assert manco.open_manco(db) == []


def test_bestellingen_pagina_bewaart_alles_en_toont_manco_per_leverancier(ingelogde_client, db):
    lev = db.execute("INSERT INTO leveranciers (naam, aangemaakt_op) VALUES ('Sligro', '2026-10-01')").lastrowid
    cola = _product(db, "Cola Overzicht")
    db.execute("UPDATE producten SET leverancier_id = ? WHERE id = ?", (lev, cola))
    db.commit()
    b = _ontvangen_bestelling(db, [(cola, 10, 4)])
    pagina = ingelogde_client.get("/bestellingen").data.decode()
    assert "Nog niet geleverd" in pagina and "Sligro" in pagina and "6 stuks niet geleverd (4 van 10)" in pagina
    assert f"<strong>#{b}</strong>" in pagina and "1 manco" not in pagina  # te weinig is geen 'manco'-vlag, wel 'te weinig'
    assert "te weinig" in pagina
    assert f"<strong>#{b}</strong>" not in ingelogde_client.get("/bestellingen?status=besteld").data.decode()


def test_oud_manco_komt_niet_ineens_terug(db):
    from database.migraties import _m5_oud_manco_afgehandeld

    pid = _product(db, "Oud Manco")
    _ontvangen_bestelling(db, [(pid, 10, 0)])
    _m5_oud_manco_afgehandeld(db)
    assert manco.open_manco(db) == []


def test_prijs_uit_de_factuur_wordt_de_inkoopprijs(ingelogde_client, db):
    pid = _product(db, "Frikandel Prijs", inkoop=0, factor=40, besteleenheid="doos")
    artikel = _artikel(db, pid, "AH frikandellen", ean=AH_ZAK, aantal=20, prijs=10, doos=AH_DOOS, per_doos=2)
    ronde_id = facturen.start_ronde(db)
    facturen.scan(db, ronde_id, AH_DOOS)
    regel_id = facturen.ronde(db, ronde_id)["regels"][0]["id"]
    resp = ingelogde_client.post(f"/facturen/{ronde_id}/regels/{regel_id}/prijs", data={"csrf_token": _csrf(ingelogde_client), "prijs": "24,00"})
    assert resp.status_code == 302
    assert facturen.ronde(db, ronde_id)["totaal"] == 24.0
    samenvatting, _ = facturen.afronden(db, ronde_id)
    assert samenvatting["prijzen"] == 1
    assert db.execute("SELECT inkoopprijs FROM artikelen WHERE id = ?", (artikel,)).fetchone()[0] == 12.0  # per zak van 20
    assert db.execute("SELECT inkoopprijs FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 24.0  # doos van 40


def test_prijs_van_een_fust_zonder_barcode(db):
    fust = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, verkoopprijs, inkoopprijs, actief, glazen_per_fust)
           VALUES ('Fust Prijs', 'Bier', 'fust', 0, 3.0, 90.0, 1, 200)"""
    ).lastrowid
    db.commit()
    ronde_id = facturen.start_ronde(db)
    facturen.voeg_plu_toe(db, ronde_id, fust, 2)
    regel_id = facturen.ronde(db, ronde_id)["regels"][0]["id"]
    assert facturen.zet_prijs(db, ronde_id, regel_id, "97,50") is None
    facturen.afronden(db, ronde_id)
    assert db.execute("SELECT inkoopprijs FROM producten WHERE id = ?", (fust,)).fetchone()[0] == 97.5
    assert db.execute("SELECT COUNT(*) FROM prijs_geschiedenis WHERE product_id = ?", (fust,)).fetchone()[0] == 1
