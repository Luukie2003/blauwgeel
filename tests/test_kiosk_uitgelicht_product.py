"""Tests voor het 'uitgelicht product' op het prijzenscherm (bijv. "Snack
van de week") -- zie _uitgelicht_product in routes/kiosk.py en de
sleep-onafhankelijke kaart op kiosk_prijzen_instellingen.html."""
from conftest import stel_csrf_token_in as _csrf
from test_kiosk import _voeg_product_toe


def _zet_uitgelicht(ingelogde_client, product_id, titel=None):
    data = {"csrf_token": _csrf(ingelogde_client), "product_id": str(product_id or "")}
    if titel is not None:
        data["titel"] = titel
    return ingelogde_client.post("/kiosk/prijzen/uitgelicht", data=data)


def test_zonder_keuze_geen_uitgelicht_kaart(client, db):
    _voeg_product_toe(db, "Chips A", categorie="Chips", toon_op_kiosk=1)
    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert '<div class="uitgelicht-kaart' not in tekst


def test_uitgelicht_product_verschijnt_groot_en_valt_uit_eigen_categorie(client, ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Bitterballen", categorie="Keuken", prijs=4.5, toon_op_kiosk=1)
    resp = _zet_uitgelicht(ingelogde_client, product_id, titel="Snack van de week")
    assert resp.status_code == 302

    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert '<div class="uitgelicht-kaart' in tekst
    assert '<span class="uitgelicht-label">Snack van de week</span>' in tekst
    assert '<span class="uitgelicht-naam">Bitterballen</span>' in tekst
    assert "&euro; 4.50" in tekst
    # Niet nogmaals als gewone regel onder 'Keuken'.
    assert "Keuken" not in tekst


def test_uitgelicht_product_toont_uitverkocht(client, ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Loempia", categorie="Keuken", prijs=2.0, toon_op_kiosk=1)
    db.execute("UPDATE producten SET kiosk_uitverkocht = 1 WHERE id = ?", (product_id,))
    db.commit()
    _zet_uitgelicht(ingelogde_client, product_id)

    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert "uitgelicht-kaart--uitverkocht" in tekst
    assert '<span class="uitgelicht-naam">Loempia</span>' in tekst
    assert "bedrag-uitverkocht" in tekst


def test_uitgelicht_product_uitzetten(client, ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Frikandel", categorie="Keuken", toon_op_kiosk=1)
    _zet_uitgelicht(ingelogde_client, product_id)
    assert '<div class="uitgelicht-kaart' in client.get("/kiosk/prijzen").get_data(as_text=True)

    _zet_uitgelicht(ingelogde_client, None)
    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert '<div class="uitgelicht-kaart' not in tekst
    # Valt terug in zijn eigen categorie zodra 'ie niet meer uitgelicht is.
    assert "Frikandel" in tekst
    assert "Keuken" in tekst


def test_verwijderd_product_blijft_geen_kapotte_kaart_tonen(client, ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Kroket", categorie="Keuken", toon_op_kiosk=1)
    _zet_uitgelicht(ingelogde_client, product_id)
    db.execute("UPDATE producten SET actief = 0 WHERE id = ?", (product_id,))
    db.commit()

    resp = client.get("/kiosk/prijzen")
    assert resp.status_code == 200
    assert '<div class="uitgelicht-kaart' not in resp.get_data(as_text=True)


def test_instellingenpagina_toont_uitgelicht_keuze(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Nootjes", categorie="Snoep", toon_op_kiosk=1)
    _zet_uitgelicht(ingelogde_client, product_id, titel="Borrelhapje")

    tekst = ingelogde_client.get("/kiosk/prijzen/instellingen").get_data(as_text=True)
    assert "Uitgelicht product" in tekst
    assert 'value="Borrelhapje"' in tekst
    assert f'<option value="{product_id}" selected>Nootjes</option>' in tekst


def test_uitgelicht_wijziging_verandert_versie(client, ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Zoutjes", categorie="Snoep", toon_op_kiosk=1)
    voor = client.get("/kiosk/prijzen/versie").get_json()["versie"]
    _zet_uitgelicht(ingelogde_client, product_id)
    na = client.get("/kiosk/prijzen/versie").get_json()["versie"]
    assert voor != na
