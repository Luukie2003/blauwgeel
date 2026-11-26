"""2.27.0: meer dan kon bij het tellen, telfouten niet als verkocht in de rapporten, en Alle rapporten."""

from datetime import timedelta

from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_navigatie import _inloggen, _menu
from test_producten_prijzen import _product

from helpers.tijd import vandaag_amsterdam
from marge import bereken_marge
from navigatie import NAV_ITEMS, RAPPORT_UITLEG
from routes.tellen.looplijst import controle_regels


def _telling(db, dagen_geleden, regels):
    """regels: {product_id: (voorraad_voor, geteld)}; verkocht en correctie zoals verwerk_telling ze uitrekent."""
    datum = (vandaag_amsterdam() - timedelta(days=dagen_geleden)).strftime("%Y-%m-%d 12:00")
    tid = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'T')", (datum,)).lastrowid
    for pid, (voor, geteld) in regels.items():
        db.execute(
            """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
               VALUES (?, ?, ?, ?, ?, ?, 2.0)""",
            (tid, pid, voor, geteld, max(0, voor - geteld), max(0, geteld - voor)),
        )
        db.execute("UPDATE producten SET voorraad = ? WHERE id = ?", (geteld, pid))
    db.commit()


# ---------- Meer dan kon ----------


def test_meer_dan_er_kan_liggen_krijgt_een_waarschuwing(db):
    pid = _product(db, "Bozu Peach", voorraad=0)
    _telling(db, 7, {pid: (0, 10)})  # de eerste telling: alles is nieuw
    regel = controle_regels(db, {str(pid): 14}, {str(pid): "14"}, {})[0]
    assert regel["meer_dan_kon"] == 4
    assert controle_regels(db, {str(pid): 10}, {}, {})[0]["meer_dan_kon"] is None
    assert controle_regels(db, {str(pid): 6}, {}, {})[0]["meer_dan_kon"] is None


def test_bij_de_eerste_telling_zegt_meer_niets(db):
    pid = _product(db, "Nieuw blikje", voorraad=0)
    assert controle_regels(db, {str(pid): 24}, {}, {})[0]["meer_dan_kon"] is None


def test_het_controlescherm_en_de_app_tonen_het(app_client, db, app):  # noqa: F811
    pid = _product(db, "Bozu Mango", voorraad=0)
    _telling(db, 7, {pid: (0, 5)})
    with app.test_request_context():
        from flask import render_template, session

        session["gebruiker_naam"] = "admin"
        html = render_template("tellen_lopen_controleren.html", regels=controle_regels(db, {str(pid): 8}, {}, {}),
                               basis_template="base.html")
    assert "Meer dan kon" in html and "hooguit 5" in html
    antwoord = _post(app_client, "/api/app/tellen/controleren", bar={str(pid): "8"}, hok={}, loop_id="L1", nieuw=True)
    regels = antwoord.get_json()["regels"]
    assert next(r for r in regels if r["product_id"] == pid)["meer_dan_kon"] == 3


def test_het_telformulier_waarschuwt_alleen_bij_eerder_getelde_producten(ingelogde_client, db):
    geteld = _product(db, "Al eens geteld", voorraad=0)
    _telling(db, 7, {geteld: (0, 6)})
    nieuw = _product(db, "Nog nooit geteld", voorraad=0)
    html = ingelogde_client.get("/tellen").data.decode()
    assert f'name="geteld_{geteld}"' in html and 'data-kon="6"' in html
    veld_nieuw = html.split(f'name="geteld_{nieuw}"')[1].split(">")[0]
    assert "data-kon" not in veld_nieuw
    assert "Meer dan kon" in html


# ---------- Telfouten niet als verkocht ----------


def test_de_marge_telt_een_telfout_niet_als_verkocht(db):
    pid = _product(db, "Telfout-pils", voorraad=0)
    _telling(db, 30, {pid: (0, 20)})  # eerste telling
    _telling(db, 20, {pid: (20, 10)})  # 10 verkocht, maar er stonden er nog 4 meer
    _telling(db, 10, {pid: (10, 14)})  # meer dan kon: 4 te veel
    regel = next(p for p in bereken_marge(db, 13, vandaag_amsterdam())["producten"] if p["naam"] == "Telfout-pils")
    assert regel["aantal"] == 6


def test_de_toppers_van_het_verkooprapport_zijn_netto(ingelogde_client, db):
    from helpers.omzet import bereken_omzet_trend_periode

    pid = _product(db, "Netto-cola", voorraad=0)
    _telling(db, 30, {pid: (0, 20)})
    _telling(db, 20, {pid: (20, 10)})
    _telling(db, 10, {pid: (10, 14)})
    van = (vandaag_amsterdam() - timedelta(days=25)).isoformat()
    trend = bereken_omzet_trend_periode(db, van, vandaag_amsterdam().isoformat())
    top = next(t for t in trend["top_verkopers"] if t["product_naam"] == "Netto-cola")
    assert top["verkocht"] == 6 and top["omzet"] == 12.0


# ---------- Alle rapporten ----------


def test_het_menu_houdt_vier_rapporten(ingelogde_client):
    rapporten = _menu(ingelogde_client.get("/").data.decode())["Rapporten"]
    assert rapporten == ["Alle rapporten", "Verkooprapport", "Marge", "Weekoverzicht"]


def test_alle_rapporten_staan_op_het_overzicht_met_uitleg(ingelogde_client):
    html = ingelogde_client.get("/rapporten").data.decode()
    for item in NAV_ITEMS:
        if item["groep"] == "Rapporten" and item["url_endpoint"] != "rapporten_overzicht":
            assert item["label"] in html, item["label"]
            assert item["url_endpoint"] in RAPPORT_UITLEG, item["url_endpoint"]
    for rubriek in ("Omzet", "Winst en inkoop", "Voorraad", "Overig"):
        assert f"<h2>{rubriek}</h2>" in html


def test_op_een_rapport_buiten_het_menu_licht_alle_rapporten_op(ingelogde_client):
    html = ingelogde_client.get("/rapporten/derving").data.decode()
    zijbalk = html.split('data-groep="Rapporten"')[1].split("</ul>")[0]
    assert 'class="actief">Alle rapporten' in zijbalk


def test_een_vrijwilliger_ziet_geen_rapporten_voor_beheerders(client, db):
    _inloggen(client, db, "voorraad")
    html = client.get("/rapporten").data.decode()
    assert "Verkooprapport" in html and "Seizoen in cijfers" in html
    for alleen_beheer in ("Marge", "Merkanalyse", "Derving", "Niet-lopers", "Omzet per bardienst"):
        assert f"<strong>{alleen_beheer}</strong>" not in html, alleen_beheer
    assert "<h2>Winst en inkoop</h2>" not in html
