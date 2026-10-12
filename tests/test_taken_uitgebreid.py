"""Eigen taken: terugkomen, checklists met stappen en de taken op het startscherm van de handterminal."""

from datetime import date, timedelta

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_eigen_taken import ADMIN, _nieuwe_taak_via_formulier, _taak, _vrijwilliger

import eigen_taken
from eigen_taken import (
    CHECKLIST_VOORBEELDEN,
    MAX_STAPPEN,
    maak_taak,
    rond_af,
    schoon_stappen,
    taak_voor_persoon,
    taken_voor_gebruiker,
    vink_stap,
    volgende_datum,
)


def _vandaag():
    from helpers.tijd import vandaag_amsterdam

    return vandaag_amsterdam()


def _maak(db, herhaling=None, stappen=None, deadline=None, ids=(ADMIN,), titel="Opdracht", iedereen=True, soort="eigen"):
    taak_id, fout = maak_taak(db, titel, "", soort, deadline.isoformat() if deadline else None, list(ids), iedereen, "admin", herhaling, stappen)
    assert fout is None, fout
    return taak_id


def _volgende_taak(db, na):
    return db.execute("SELECT * FROM taken WHERE id > ? ORDER BY id LIMIT 1", (na,)).fetchone()


# ---------- Terugkomen ----------


def test_een_terugkerende_taak_vraagt_om_een_datum_en_een_geldige_maanddag(db):
    assert "uiterste datum" in maak_taak(db, "X", "", "eigen", None, [ADMIN], True, "admin", "week")[1]
    assert "tot en met de 28e" in maak_taak(db, "X", "", "eigen", "2026-12-31", [ADMIN], True, "admin", "maand")[1]
    assert maak_taak(db, "X", "", "eigen", "2026-12-28", [ADMIN], True, "admin", "maand")[1] is None
    assert maak_taak(db, "Een keer", "", "eigen", None, [ADMIN], True, "admin", "bestaat-niet")[1] is None  # onbekend: eenmalig


def test_zodra_een_wekelijkse_taak_klaar_is_staat_de_volgende_er(db):
    deadline = _vandaag() + timedelta(days=1)
    taak_id = _maak(db, "week", deadline=deadline)
    resultaat = rond_af(db, taak_id, ADMIN, "admin")
    assert resultaat["klaar"] and resultaat["volgende"] == deadline + timedelta(days=7)
    volgende = _volgende_taak(db, taak_id)
    assert (volgende["titel"], volgende["deadline"], volgende["herhaling"]) == ("Opdracht", (deadline + timedelta(days=7)).isoformat(), "week")
    assert [r[0] for r in db.execute("SELECT gebruiker_id FROM taak_toewijzingen WHERE taak_id = ?", (volgende["id"],))] == [ADMIN]


def test_de_volgende_keer_staat_pas_vlak_voor_de_datum_op_het_overzicht(db):
    deadline = _vandaag() + timedelta(days=1)
    taak_id = _maak(db, "week", deadline=deadline)
    rond_af(db, taak_id, ADMIN, "admin")
    volgende = _volgende_taak(db, taak_id)
    assert volgende["start_op"] == (deadline + timedelta(days=4)).isoformat()  # 3 dagen voor de uiterste datum
    assert taken_voor_gebruiker(db, ADMIN) == []  # nog niet aan de beurt
    gepland = [t for t in eigen_taken.open_taken(db) if t["id"] == volgende["id"]][0]
    assert gepland["gepland"] is True and gepland["herhaling_label"] == "Elke week"
    db.execute("UPDATE taken SET start_op = ? WHERE id = ?", (_vandaag().isoformat(), volgende["id"]))
    db.commit()
    assert [t["id"] for t in taken_voor_gebruiker(db, ADMIN)] == [volgende["id"]]


def test_een_te_late_taak_schuift_de_reeks_op_in_plaats_van_verlopen_taken_te_maken(db):
    deadline = _vandaag() - timedelta(days=20)
    taak_id = _maak(db, "week", deadline=deadline)
    volgende = rond_af(db, taak_id, ADMIN, "admin")["volgende"]
    assert volgende >= _vandaag() and (volgende - deadline).days % 7 == 0  # nog steeds op dezelfde weekdag
    assert volgende - _vandaag() < timedelta(days=7)


def test_elke_twee_weken_en_elke_maand():
    class Db:  # volgende_datum heeft alleen bij 'verkoopdagen' een database nodig
        pass

    d = date(2026, 10, 14)
    assert volgende_datum(Db, "2weken", d, date(2026, 10, 1)) == date(2026, 10, 28)
    assert volgende_datum(Db, "maand", d, date(2026, 10, 1)) == date(2026, 11, 14)
    assert volgende_datum(Db, "maand", date(2026, 12, 14), date(2026, 12, 1)) == date(2027, 1, 14)  # over de jaargrens
    assert volgende_datum(Db, "maand", d, date(2027, 1, 20)) == date(2027, 2, 14)  # te laat: schuift mee


def test_op_elke_verkoopdag_komt_de_volgende_open_dag(db):
    from voorspelling import dag_is_open, lees_verkoopdagen

    weekdagen, uitzonderingen = lees_verkoopdagen(db)  # standaard woensdag en zaterdag
    zaterdag = next(_vandaag() + timedelta(days=i) for i in range(1, 15) if (_vandaag() + timedelta(days=i)).weekday() == 5)
    volgende = volgende_datum(db, "verkoopdagen", zaterdag, _vandaag())
    assert volgende.weekday() == 2 and volgende > zaterdag and dag_is_open(volgende, weekdagen, uitzonderingen)  # de woensdag erna
    # Een dichte dag (uitzondering) wordt overgeslagen.
    db.execute("INSERT INTO verkoop_uitzonderingen (datum, open) VALUES (?, 0)", (volgende.isoformat(),))
    db.commit()
    assert volgende_datum(db, "verkoopdagen", zaterdag, _vandaag()) == volgende + timedelta(days=3)  # de zaterdag erna


def test_een_eenmalige_taak_geeft_geen_volgende(db):
    taak_id = _maak(db, deadline=_vandaag() + timedelta(days=2))
    assert rond_af(db, taak_id, ADMIN, "admin")["volgende"] is None
    assert _volgende_taak(db, taak_id) is None


def test_een_taak_die_nog_niet_klaar_is_voor_iedereen_maakt_nog_geen_volgende(app, db):
    _, bakker = _vrijwilliger(app, db)
    taak_id = _maak(db, "week", deadline=_vandaag() + timedelta(days=1), ids=[ADMIN, bakker], soort="preset:voorraad_tellen")
    assert rond_af(db, taak_id, ADMIN, "admin")["volgende"] is None
    assert _volgende_taak(db, taak_id) is None
    assert rond_af(db, taak_id, bakker, "bakker")["volgende"] is not None
    assert len(db.execute("SELECT gebruiker_id FROM taak_toewijzingen WHERE taak_id = ?", (_volgende_taak(db, taak_id)["id"],)).fetchall()) == 2


def test_het_formulier_maakt_een_terugkerende_taak_en_zegt_wanneer_de_volgende_komt(ingelogde_client, db):
    deadline = (_vandaag() + timedelta(days=1)).isoformat()
    resp = _nieuwe_taak_via_formulier(ingelogde_client, herhaling="week", deadline=deadline)
    assert db.execute("SELECT herhaling FROM taken").fetchone()[0] == "week"
    taak_id = db.execute("SELECT id FROM taken").fetchone()[0]
    af = ingelogde_client.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "De volgende keer is" in af.data.decode()
    assert "Taak toegevoegd" in resp.data.decode()


def test_zonder_datum_geen_terugkerende_taak_via_het_formulier(ingelogde_client, db):
    resp = _nieuwe_taak_via_formulier(ingelogde_client, herhaling="week")
    assert "uiterste datum" in resp.data.decode() and db.execute("SELECT COUNT(*) FROM taken").fetchone()[0] == 0


def test_de_beheerpagina_toont_terugkerende_en_geplande_taken(ingelogde_client, db):
    deadline = _vandaag() + timedelta(days=1)
    taak_id = _maak(db, "maand", deadline=deadline)
    rond_af(db, taak_id, ADMIN, "admin")
    tekst = ingelogde_client.get("/taken").data.decode()
    assert "Elke maand" in tekst and "gepland vanaf" in tekst
    assert "Dit stopt ook het terugkomen" in tekst
    assert 'name="herhaling"' in tekst and "Op elke verkoopdag" in tekst


# ---------- Checklists ----------


def test_stappen_schoonmaken():
    assert schoon_stappen("  Eerste \n\n  Tweede  stap\r\n") == "Eerste\nTweede stap"
    assert schoon_stappen("") is None and schoon_stappen(None) is None
    assert len(schoon_stappen("\n".join(f"Stap {i}" for i in range(40))).splitlines()) == MAX_STAPPEN
    assert len(schoon_stappen("x" * 500)) == eigen_taken.MAX_TEKENS_STAP


def test_vinkt_per_persoon_stappen_af(app, db):
    _, bakker = _vrijwilliger(app, db)
    taak_id = _maak(db, stappen="Een\nTwee\nDrie", ids=[ADMIN, bakker], soort="preset:voorraad_tellen")
    assert vink_stap(db, taak_id, ADMIN, 0, True) == {"afgevinkt": [0], "totaal": 3}
    assert vink_stap(db, taak_id, ADMIN, 2, True)["afgevinkt"] == [0, 2]
    assert vink_stap(db, taak_id, ADMIN, 0, False)["afgevinkt"] == [2]
    assert taak_voor_persoon(db, taak_id, bakker)["mijn_afgevinkt"] == []  # ieder zijn eigen vinkjes
    assert vink_stap(db, taak_id, ADMIN, 7, True) is None and vink_stap(db, 999, ADMIN, 0, True) is None
    assert vink_stap(db, taak_id, 999, 0, True) is None  # niet aan hem toegewezen


def test_afronden_kan_pas_als_alles_is_afgevinkt(db):
    taak_id = _maak(db, stappen="Een\nTwee")
    vink_stap(db, taak_id, ADMIN, 0, True)
    assert rond_af(db, taak_id, ADMIN, "admin")["onvolledig"] == (1, 2)
    assert db.execute("SELECT afgerond_op FROM taken WHERE id = ?", (taak_id,)).fetchone()[0] is None
    vink_stap(db, taak_id, ADMIN, 1, True)
    assert rond_af(db, taak_id, ADMIN, "admin")["klaar"] is True


def test_een_beheerder_kan_een_checklist_wel_voor_iedereen_afronden(ingelogde_client, db):
    taak_id = _maak(db, stappen="Een\nTwee")
    ingelogde_client.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(ingelogde_client), "voor_iedereen": "1"})
    assert db.execute("SELECT afgerond_op FROM taken WHERE id = ?", (taak_id,)).fetchone()[0] is not None


def test_de_checklistpagina_en_het_afvinken_via_de_site(ingelogde_client, db):
    taak_id = _maak(db, titel="Kantine openen", stappen="Licht aan\nKassa klaarzetten")
    tekst = ingelogde_client.get(f"/taken/{taak_id}").data.decode()
    assert "Kantine openen" in tekst and "Licht aan" in tekst and 'data-stap="1"' in tekst and "checklist-klaar" in tekst

    resp = ingelogde_client.post(f"/taken/{taak_id}/stap", data={"csrf_token": _csrf(ingelogde_client), "stap": "0", "aan": "1"})
    assert resp.get_json() == {"ok": True, "afgevinkt": [0], "totaal": 2}
    assert "checked" in ingelogde_client.get(f"/taken/{taak_id}").data.decode()  # blijft staan na verversen

    onvolledig = ingelogde_client.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "Vink eerst alle stappen af (1 van 2)" in onvolledig.data.decode()
    ingelogde_client.post(f"/taken/{taak_id}/stap", data={"csrf_token": _csrf(ingelogde_client), "stap": "1", "aan": "1"})
    klaar = ingelogde_client.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "is klaar" in klaar.data.decode()


def test_ongeldig_afvinken_geeft_een_fout(ingelogde_client, db):
    taak_id = _maak(db, stappen="Een")
    assert ingelogde_client.post(f"/taken/{taak_id}/stap", data={"csrf_token": _csrf(ingelogde_client), "stap": "abc"}).status_code == 400
    assert ingelogde_client.post(f"/taken/{taak_id}/stap", data={"csrf_token": _csrf(ingelogde_client), "stap": "5", "aan": "1"}).status_code == 404


def test_een_taak_van_een_ander_zie_je_niet_op_de_checklistpagina(app, db):
    klant, _ = _vrijwilliger(app, db)
    taak_id = _maak(db, stappen="Een", ids=[ADMIN])
    assert "staat niet (meer) open voor jou" in klant.get(f"/taken/{taak_id}", follow_redirects=True).data.decode()


def test_een_taak_met_stappen_opent_de_checklist(ingelogde_client, db):
    taak_id = _maak(db, stappen="Een", soort="preset:voorraad_tellen")  # heeft ook een pagina, maar de checklist gaat voor
    resp = ingelogde_client.get(f"/taken/{taak_id}/openen")
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/taken/{taak_id}")
    assert "/tellen" in ingelogde_client.get(f"/taken/{taak_id}").data.decode()  # en de pagina staat als knop op de checklist


def test_het_overzicht_toont_hoeveel_stappen_je_al_hebt(ingelogde_client, db):
    taak_id = _maak(db, stappen="Een\nTwee\nDrie")
    vink_stap(db, taak_id, ADMIN, 1, True)
    assert "1 van 3 stappen" in ingelogde_client.get("/").data.decode()


def test_de_voorbeeldchecklists_staan_op_het_formulier(ingelogde_client):
    tekst = ingelogde_client.get("/taken").data.decode()
    assert 'name="stappen"' in tekst
    for naam, stappen in CHECKLIST_VOORBEELDEN.items():
        assert naam in tekst and stappen[0] in tekst
    assert set(CHECKLIST_VOORBEELDEN) == {"Kantine openen", "Kantine sluiten"}


def test_het_formulier_bewaart_de_stappen(ingelogde_client, db):
    _nieuwe_taak_via_formulier(ingelogde_client, titel="Sluiten", stappen="Kassa tellen\n\nLicht uit")
    assert db.execute("SELECT stappen FROM taken").fetchone()[0] == "Kassa tellen\nLicht uit"


# ---------- Op de handterminal ----------


def test_de_taken_staan_op_het_startscherm_van_de_handterminal(ingelogde_client, db):
    _taak(db, "Prijzenlijst nalopen", soort="preset:prijzen", deadline=(_vandaag() - timedelta(days=1)).isoformat())
    _maak(db, titel="Kerstboom ophalen")
    ingelogde_client.get("/weergave/pda")
    tekst = ingelogde_client.get("/").data.decode()
    assert "pda-kop-menuknop" in tekst
    assert "Prijzenlijst nalopen" in tekst and "Kerstboom ophalen" in tekst and "(te laat)" in tekst
    assert "pda-status--slecht" in tekst  # de te late taak valt op


def test_zonder_taken_geen_extra_regels_op_de_handterminal(ingelogde_client):
    ingelogde_client.get("/weergave/pda")
    assert "eigen_taak" not in ingelogde_client.get("/").data.decode()


def test_een_vrijwilliger_ziet_alleen_zijn_eigen_taken_op_de_handterminal(app, db):
    klant, bakker = _vrijwilliger(app, db)
    _maak(db, titel="Alleen voor admin")
    _maak(db, titel="Voor de bakker", ids=[bakker], soort="preset:voorraad_tellen")
    klant.get("/weergave/pda")
    tekst = klant.get("/").data.decode()
    assert "Voor de bakker" in tekst and "Alleen voor admin" not in tekst


@pytest.mark.parametrize("pad", ["/taken/1/stap"])
def test_afvinken_vraagt_inloggen(client, pad):
    assert client.post(pad, data={"stap": "0"}).status_code in (302, 400)
