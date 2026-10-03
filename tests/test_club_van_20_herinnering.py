"""De tijdelijke herinnering: t/m een ingestelde dag staan ook leden die dit
seizoen nog niet betaald hebben lichtrood op het scherm (zie onbetaald_actie
en scherm_bereik in club_van_20.py)."""

from datetime import timedelta

from conftest import stel_csrf_token_in as _csrf
from test_club_van_20 import HUIDIG, TWEE_TERUG, VORIG, _alleen_club_van_20, _bijdrage, _lid, _zet

from club_van_20 import bouw_slides, onbetaald_actie, scherm_bereik, verschuif_seizoen
from helpers import vandaag_amsterdam


def _leden(db):
    """Betaalt Nu (dit seizoen), Vorig Seizoen en Twee Terug (nog niet betaald),
    Lang Weg (4 seizoenen terug), Gestopt (archief) en Zegt Af (stopt)."""
    _bijdrage(db, _lid(db, "Betaalt Nu"), HUIDIG)
    _bijdrage(db, _lid(db, "Vorig Seizoen"), VORIG)
    _bijdrage(db, _lid(db, "Twee Terug"), TWEE_TERUG)
    _bijdrage(db, _lid(db, "Lang Weg"), verschuif_seizoen(HUIDIG, -4))
    _bijdrage(db, _lid(db, "Gestopt", status="inactief"), VORIG)
    zegt_af = _lid(db, "Zegt Af")
    _bijdrage(db, zegt_af, VORIG)
    _bijdrage(db, zegt_af, HUIDIG, status="afgezegd")


def _tot(dagen):
    return (vandaag_amsterdam() + timedelta(days=dagen)).isoformat()


def _scherm(client):
    return client.get("/kiosk/scherm").data.decode()


def _rood(tekst, naam):
    positie = tekst.index(naam)
    return "c20-bordje--niet-betaald" in tekst[max(0, positie - 400) : positie]


def test_zonder_herinnering_blijft_het_scherm_zoals_ingesteld(client, db):
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=1, club_van_20_markeer_onbetaald=0)
    tekst = _scherm(client)
    assert "Betaalt Nu" in tekst
    assert "Vorig Seizoen" not in tekst and "Twee Terug" not in tekst


def test_herinnering_toont_onbetaalden_lichtrood_en_betaalden_gewoon(client, db):
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=1, club_van_20_markeer_onbetaald=0,
         club_van_20_onbetaald_tot=_tot(7), club_van_20_onbetaald_seizoenen=3)
    tekst = _scherm(client)
    assert _rood(tekst, "Vorig Seizoen") and _rood(tekst, "Twee Terug")
    assert not _rood(tekst, "Betaalt Nu")
    # Te lang geleden, gearchiveerd of gestopt: nooit erbij.
    assert "Lang Weg" not in tekst and "Gestopt" not in tekst and "Zegt Af" not in tekst


def test_herinnering_met_alle_actieve_leden_en_ruimer_dan_de_gewone_instelling(client, db):
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=1, club_van_20_onbetaald_tot=_tot(7),
         club_van_20_onbetaald_seizoenen=0)
    assert _rood(_scherm(client), "Lang Weg")
    # De gewone instelling mag ruimer zijn dan de herinnering: het ruimste telt.
    _zet(db, club_van_20_zichtbaar_seizoenen=0, club_van_20_onbetaald_seizoenen=2)
    assert "Lang Weg" in _scherm(client)


def test_herinnering_loopt_t_m_de_ingestelde_dag(client, db):
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=1, club_van_20_onbetaald_tot=_tot(0))
    assert "Vorig Seizoen" in _scherm(client)  # vandaag is de laatste dag
    _zet(db, club_van_20_onbetaald_tot=_tot(-1))
    tekst = _scherm(client)
    assert "Vorig Seizoen" not in tekst and "Betaalt Nu" in tekst  # gisteren: voorbij


def test_onbetaald_actie_en_scherm_bereik(db):
    instellingen = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert onbetaald_actie(instellingen) is None
    _zet(db, club_van_20_onbetaald_tot="onzin")
    assert onbetaald_actie(db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()) is None
    _zet(db, club_van_20_zichtbaar_seizoenen=1, club_van_20_markeer_onbetaald=0,
         club_van_20_onbetaald_tot=_tot(3), club_van_20_onbetaald_seizoenen=3)
    instellingen = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert onbetaald_actie(instellingen)["tot"] == vandaag_amsterdam() + timedelta(days=3)
    assert scherm_bereik(instellingen) == (3, True)
    assert scherm_bereik(instellingen, vandaag=vandaag_amsterdam() + timedelta(days=4)) == (1, False)


def test_tellers_en_teamstand_en_publieke_pagina_tellen_alleen_betaalden(client, db):
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=1, club_van_20_onbetaald_tot=_tot(7),
         club_van_20_onbetaald_seizoenen=3, club_van_20_toon_teller=1, club_van_20_toon_werving=1)
    instellingen = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    slides = bouw_slides(db, instellingen)
    muur = [s for s in slides if s["type"] == "club_van_20"]
    assert sum(len(s["namen"]) for s in muur) == 3  # Betaalt Nu + 2 onbetaalden
    assert [s["aantal_leden"] for s in slides if s["type"] in ("club_van_20_teller", "club_van_20_werving")] == [1, 1]
    publiek = client.get("/club-van-20/doe-mee").data.decode()
    assert "Betaalt Nu" in publiek
    assert "Vorig Seizoen" not in publiek and "Twee Terug" not in publiek


def test_herinnering_opslaan_en_tonen_in_de_instellingen(ingelogde_client, db):
    _alleen_club_van_20(db)
    _leden(db)
    morgen = _tot(1)
    resp = ingelogde_client.post(
        "/club-van-20/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "club_van_20_titel": "Club van 20",
            "club_van_20_zichtbaar_seizoenen": "1",
            "club_van_20_onbetaald_tot": morgen,
            "club_van_20_onbetaald_seizoenen": "0",
        },
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert rij["club_van_20_onbetaald_tot"] == morgen and rij["club_van_20_onbetaald_seizoenen"] == 0
    tekst = ingelogde_client.get("/club-van-20/instellingen").data.decode()
    assert "Loopt nu" in tekst and "lichtrode bordjes" in tekst
    # Leeg of onleesbaar = geen herinnering.
    ingelogde_client.post(
        "/club-van-20/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "club_van_20_onbetaald_tot": "morgen"},
    )
    rij = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert rij["club_van_20_onbetaald_tot"] is None


def test_ledenlijst_markeert_wie_tijdelijk_op_het_scherm_staat(ingelogde_client, db):
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=1)
    lid_id = db.execute("SELECT id FROM club_van_20_leden WHERE naam = 'Vorig Seizoen'").fetchone()["id"]
    tekst = ingelogde_client.get(f"/club-van-20/leden/{lid_id}").data.decode()
    assert "telt nog mee door een eerdere betaling" not in tekst
    _zet(db, club_van_20_onbetaald_tot=_tot(7), club_van_20_onbetaald_seizoenen=3)
    tekst = ingelogde_client.get(f"/club-van-20/leden/{lid_id}").data.decode()
    assert "telt nog mee door een eerdere betaling" in tekst
