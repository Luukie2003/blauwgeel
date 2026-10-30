"""Kantine-tv: een dia alleen tussen twee data tonen. En de turfknoppen op de telpagina."""

from datetime import timedelta

from conftest import stel_csrf_token_in as _csrf
from test_kiosk import _voeg_sponsor_toe
from test_producten_prijzen import _product

from routes.kiosk.dia_gegevens import _bouw_slides


def _vandaag():
    from helpers.tijd import vandaag_amsterdam

    return vandaag_amsterdam()


def _dag(delta):
    return (_vandaag() + timedelta(days=delta)).isoformat()


def _zet_data(db, titel, vanaf=None, tot=None):
    db.execute("UPDATE kiosk_sponsoren SET zichtbaar_vanaf = ?, zichtbaar_tot = ? WHERE titel = ?", (vanaf, tot, titel))
    db.commit()


def _titels(db):
    from flask import current_app

    with current_app.test_request_context("/"):  # de dia's bouwen urls: daar is een verzoek voor nodig
        return [s.get("titel") for s in _bouw_slides(db) if s.get("titel")]


# ---------- Dia's plannen ----------


def test_een_dia_zonder_data_staat_er_altijd_in(db):
    _voeg_sponsor_toe(db, "Altijd")
    assert "Altijd" in _titels(db)


def test_een_dia_met_een_begindatum_in_de_toekomst_staat_er_nog_niet_in(db):
    _voeg_sponsor_toe(db, "Straks")
    _zet_data(db, "Straks", vanaf=_dag(3))
    assert "Straks" not in _titels(db)
    _zet_data(db, "Straks", vanaf=_dag(0))  # vanaf vandaag telt vandaag zelf al mee
    assert "Straks" in _titels(db)


def test_een_dia_met_een_einddatum_verdwijnt_na_die_dag(db):
    _voeg_sponsor_toe(db, "Tijdelijk")
    _zet_data(db, "Tijdelijk", tot=_dag(0))  # t/m vandaag: vandaag nog wel
    assert "Tijdelijk" in _titels(db)
    _zet_data(db, "Tijdelijk", tot=_dag(-1))
    assert "Tijdelijk" not in _titels(db)


def test_tussen_begin_en_einddatum(db):
    _voeg_sponsor_toe(db, "Actie")
    _zet_data(db, "Actie", vanaf=_dag(-2), tot=_dag(2))
    assert "Actie" in _titels(db)
    _zet_data(db, "Actie", vanaf=_dag(1), tot=_dag(5))
    assert "Actie" not in _titels(db)


def test_een_uitgezette_dia_blijft_uit_ook_binnen_de_periode(db):
    _voeg_sponsor_toe(db, "Uit", actief=0)
    _zet_data(db, "Uit", vanaf=_dag(-1), tot=_dag(1))
    assert "Uit" not in _titels(db)


def _formulier(client, **velden):
    data = {"csrf_token": _csrf(client), "sjabloon": "titel_tekst_groot", "titel": "Geplande dia", "actief": "on", "weergave_duur_seconden": "6"}
    data.update(velden)
    return client.post("/kiosk/sponsoren-leden/sponsoren/nieuw", data=data, follow_redirects=True)


def test_het_formulier_bewaart_de_data(ingelogde_client, db):
    _formulier(ingelogde_client, zichtbaar_vanaf=_dag(2), zichtbaar_tot=_dag(9))
    rij = db.execute("SELECT zichtbaar_vanaf, zichtbaar_tot FROM kiosk_sponsoren WHERE titel = 'Geplande dia'").fetchone()
    assert tuple(rij) == (_dag(2), _dag(9))
    assert "Geplande dia" not in _titels(db)  # nog niet aan de beurt


def test_een_ongeldige_of_lege_datum_betekent_geen_grens(ingelogde_client, db):
    _formulier(ingelogde_client, zichtbaar_vanaf="morgen", zichtbaar_tot="")
    rij = db.execute("SELECT zichtbaar_vanaf, zichtbaar_tot FROM kiosk_sponsoren WHERE titel = 'Geplande dia'").fetchone()
    assert tuple(rij) == (None, None)


def test_data_in_de_verkeerde_volgorde_worden_omgewisseld_met_een_melding(ingelogde_client, db):
    resp = _formulier(ingelogde_client, zichtbaar_vanaf=_dag(9), zichtbaar_tot=_dag(2))
    assert "omgewisseld" in resp.data.decode()
    rij = db.execute("SELECT zichtbaar_vanaf, zichtbaar_tot FROM kiosk_sponsoren WHERE titel = 'Geplande dia'").fetchone()
    assert tuple(rij) == (_dag(2), _dag(9))


def test_bewerken_toont_en_wijzigt_de_data(ingelogde_client, db):
    _formulier(ingelogde_client, zichtbaar_vanaf=_dag(2), zichtbaar_tot=_dag(9))
    dia = db.execute("SELECT id FROM kiosk_sponsoren WHERE titel = 'Geplande dia'").fetchone()["id"]
    pagina = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{dia}/bewerken").data.decode()
    assert f'value="{_dag(2)}"' in pagina and f'value="{_dag(9)}"' in pagina and "Tonen vanaf" in pagina
    ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{dia}/bewerken",
        data={"csrf_token": _csrf(ingelogde_client), "sjabloon": "titel_tekst_groot", "titel": "Geplande dia", "actief": "on",
              "weergave_duur_seconden": "6", "zichtbaar_vanaf": "", "zichtbaar_tot": _dag(20)},
    )
    assert tuple(db.execute("SELECT zichtbaar_vanaf, zichtbaar_tot FROM kiosk_sponsoren WHERE id = ?", (dia,)).fetchone()) == (None, _dag(20))


def test_het_dialijstje_toont_gepland_actief_en_verlopen(ingelogde_client, db):
    _voeg_sponsor_toe(db, "Straks")
    _voeg_sponsor_toe(db, "Nu")
    _voeg_sponsor_toe(db, "Voorbij")
    _zet_data(db, "Straks", vanaf=_dag(5))
    _zet_data(db, "Nu", tot=_dag(3))
    _zet_data(db, "Voorbij", tot=_dag(-2))
    tekst = ingelogde_client.get("/kiosk/sponsoren-leden").data.decode()
    assert "gepland vanaf" in tekst and "verlopen op" in tekst and f"t/m {_dag(3)[8:10]}-{_dag(3)[5:7]}" in tekst


def test_de_tv_pakt_het_filter_ook_op_het_scherm(ingelogde_client, db):
    _voeg_sponsor_toe(db, "Straks")
    _zet_data(db, "Straks", vanaf=_dag(4))
    assert "Straks" not in ingelogde_client.get("/kiosk/scherm").data.decode()
    _zet_data(db, "Straks", vanaf=_dag(-1))
    assert "Straks" in ingelogde_client.get("/kiosk/scherm").data.decode()


# ---------- Turven ----------


def test_de_telpagina_heeft_turfknoppen_met_een_krat_als_er_een_besteleenheid_is(ingelogde_client, db):
    krat = _product(db, "Pils krat", besteleenheid="krat", besteleenheid_factor=24, voorraad=10)
    los = _product(db, "Losse fles", voorraad=10)
    tekst = ingelogde_client.get("/tellen").data.decode()
    assert f'name="geteld_{krat}"' in tekst and 'data-turf="1,5,24:krat"' in tekst
    assert f'name="geteld_{los}"' in tekst and 'data-turf="1,5,10"' in tekst


def test_de_turfknoppen_staan_in_de_gedeelde_javascript(app):
    from pathlib import Path

    js = (Path(app.root_path) / "static" / "gedeeld.js").read_text()
    assert "input[data-turf]" in js and "turf-knoppen" in js
    css = (Path(app.root_path) / "static" / "style.css").read_text()
    assert ".turf-knop" in css
