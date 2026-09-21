"""Tests voor de sleep-indeling van categorieën over de 3 vaste kolommen van
het prijzenscherm (zie kiosk_prijzen_instellingen.html en
_verdeel_over_kolommen/_verdeel_namen_over_kolommen in routes/kiosk.py)."""
import json

from conftest import stel_csrf_token_in as _csrf
from test_kiosk import _voeg_product_toe


def _sla_indeling_op(ingelogde_client, indeling):
    return ingelogde_client.post(
        "/kiosk/prijzen/categorie-kolommen",
        data={"csrf_token": _csrf(ingelogde_client), "indeling": json.dumps(indeling)},
    )


def test_zonder_indeling_staat_alles_in_1_kolom(client, db):
    _voeg_product_toe(db, "Bier A", categorie="Bier", toon_op_kiosk=1)
    _voeg_product_toe(db, "Fris A", categorie="Fris", toon_op_kiosk=1)
    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert tekst.count('class="prijzen-kolom"') == 1
    assert "Bier A" in tekst and "Fris A" in tekst


def test_indeling_opslaan_verdeelt_categorieen_over_kolommen(client, ingelogde_client, db):
    _voeg_product_toe(db, "Bier A", categorie="Bier", toon_op_kiosk=1)
    _voeg_product_toe(db, "Fris A", categorie="Fris", toon_op_kiosk=1)
    _voeg_product_toe(db, "Snack A", categorie="Keuken", toon_op_kiosk=1)

    resp = _sla_indeling_op(
        ingelogde_client, {"1": ["Fris"], "2": ["Bier"], "3": ["Keuken"]}
    )
    assert resp.status_code == 302

    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert tekst.count('class="prijzen-kolom"') == 3
    assert tekst.index("Fris A") < tekst.index("Bier A") < tekst.index("Snack A")


def test_volgorde_binnen_kolom_volgt_de_indeling(client, ingelogde_client, db):
    _voeg_product_toe(db, "Wijn A", categorie="Wijn", toon_op_kiosk=1)
    _voeg_product_toe(db, "Bier A", categorie="Bier", toon_op_kiosk=1)

    _sla_indeling_op(ingelogde_client, {"1": ["Wijn", "Bier"], "2": [], "3": []})
    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert tekst.index("Wijn A") < tekst.index("Bier A")

    _sla_indeling_op(ingelogde_client, {"1": ["Bier", "Wijn"], "2": [], "3": []})
    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert tekst.index("Bier A") < tekst.index("Wijn A")


def test_nieuwe_categorie_verschijnt_alsnog_in_kolom_1(client, ingelogde_client, db):
    _voeg_product_toe(db, "Bier A", categorie="Bier", toon_op_kiosk=1)
    _sla_indeling_op(ingelogde_client, {"1": ["Bier"], "2": [], "3": []})

    # Categorie 'Fris' bestond nog niet toen de indeling werd opgeslagen.
    _voeg_product_toe(db, "Fris A", categorie="Fris", toon_op_kiosk=1)
    tekst = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert "Fris A" in tekst


def test_instellingenpagina_toont_sleep_indeling(ingelogde_client, db):
    _voeg_product_toe(db, "Bier A", categorie="Bier", toon_op_kiosk=1)
    tekst = ingelogde_client.get("/kiosk/prijzen/instellingen").get_data(as_text=True)
    assert "Indeling prijzenscherm" in tekst
    assert 'data-naam="Bier"' in tekst


def test_indeling_wijzigt_de_versie_zodat_schermen_verversen(client, ingelogde_client, db):
    _voeg_product_toe(db, "Bier A", categorie="Bier", toon_op_kiosk=1)
    _voeg_product_toe(db, "Fris A", categorie="Fris", toon_op_kiosk=1)
    voor = client.get("/kiosk/prijzen/versie").get_json()["versie"]
    _sla_indeling_op(ingelogde_client, {"1": [], "2": ["Fris"], "3": ["Bier"]})
    na = client.get("/kiosk/prijzen/versie").get_json()["versie"]
    assert voor != na
