"""Technische meldingen (een serverfout, een te oude of mislukte back-up, een volle opslag, een storing) krijgt alleen
de systeembeheerder: het account dat eigenaar is (zie noodstop.py). Andere beheerders zien ze niet op het overzicht en
krijgen er geen mail over."""

import pytest

from test_foutmelding import fout_routes, mails  # noqa: F401  (fixtures)
from test_noodstop import _tweede_beheerder
from test_secties_rechten import _login

import backup
import mail
import uptime_check
from foutenlog import registreer_fout
from helpers.status import bouw_taken


def _mailadres(db, naam, adres):
    db.execute("UPDATE gebruikers SET email = ? WHERE naam = ?", (adres, naam))
    db.commit()


@pytest.fixture
def overal_iets_mis(db, monkeypatch):
    """Een serverfout van deze week en een back-up die te oud is."""
    registreer_fout(db, RuntimeError("test-fout"), endpoint="dashboard", pad="/", versie="test")
    monkeypatch.setattr(
        backup, "bereken_backup_status", lambda: {"ok": False, "tekst": "De laatste back-up is 9 dagen oud."}
    )


# ---------- Wie is de systeembeheerder ----------


def test_het_adres_is_dat_van_het_eigenaarsaccount(db):
    _tweede_beheerder(db)
    _mailadres(db, "beheerder2", "ander@club.nl")
    assert mail.systeembeheerder_adres(db) is None  # de eigenaar (admin) heeft nog geen e-mailadres
    _mailadres(db, "admin", "luuk@club.nl")
    assert mail.systeembeheerder_adres(db) == "luuk@club.nl"


def test_ook_te_vinden_vanuit_een_los_script(app, db):
    _mailadres(db, "admin", "luuk@club.nl")
    assert mail.systeembeheerder_adres(db_pad=app.config["DATABASE"]) == "luuk@club.nl"


def test_een_onleesbare_database_geeft_geen_adres(tmp_path):
    assert mail.systeembeheerder_adres(db_pad=tmp_path / "bestaat-niet.db") is None


# ---------- Op het overzicht ----------


def test_een_andere_beheerder_ziet_geen_technische_meldingen(client, db, overal_iets_mis):
    _tweede_beheerder(db)
    _login(client, "beheerder2")
    tekst = client.get("/").data.decode()
    assert "foutmelding deze week" not in tekst
    assert "De laatste back-up is 9 dagen oud." not in tekst


def test_de_systeembeheerder_ziet_ze_wel(ingelogde_client, overal_iets_mis):
    tekst = ingelogde_client.get("/").data.decode()
    assert "1 foutmelding deze week" in tekst
    assert "De laatste back-up is 9 dagen oud." in tekst


def test_de_taken_zonder_systeembeheerder_bevatten_geen_foutmeldingen(db, overal_iets_mis):
    titels = lambda **kw: [t["titel"] for t in bouw_taken(db, "beheerder", None, **kw)]
    assert not any("foutmelding" in t for t in titels())
    assert any("foutmelding" in t for t in titels(systeembeheerder=True))


# ---------- Per mail ----------


def test_een_serverfout_gaat_naar_de_systeembeheerder(fout_routes, ingelogde_client, mails, db):  # noqa: F811
    db.execute("UPDATE instellingen SET notificatie_email = 'kantine@club.nl' WHERE id = 1")
    _mailadres(db, "admin", "luuk@club.nl")

    assert ingelogde_client.get("/_boem").status_code == 500
    assert [naar for _, _, naar in mails] == ["luuk@club.nl"]


@pytest.fixture
def backupmails(app, db, monkeypatch):
    verstuurd = []
    monkeypatch.setattr(mail, "stuur_mail", lambda onderwerp, tekst, naar=None, **kw: verstuurd.append(naar) or True)
    monkeypatch.setattr(backup, "BRON", app.config["DATABASE"])
    return verstuurd


def test_een_mislukte_backup_gaat_naar_de_systeembeheerder(db, backupmails):
    _mailadres(db, "admin", "luuk@club.nl")
    backup.meld_mislukte_backup("schijf vol")
    backup.meld_mislukte_herstelcontrole({"backup": "voorraad-2026-11-10.db", "melding": "kapot"})
    assert backupmails == ["luuk@club.nl", "luuk@club.nl"]


def test_zonder_adres_van_de_systeembeheerder_blijft_de_backupwaarschuwing_komen(db, backupmails):
    backup.meld_mislukte_backup("schijf vol")
    assert backupmails == [backup.BACKUP_MAIL_NAAR]


def test_de_dagelijkse_kopie_blijft_naar_het_backupadres_gaan(db, backupmails, tmp_path):
    _mailadres(db, "admin", "luuk@club.nl")
    kopie = tmp_path / "voorraad-2026-11-10.db"
    kopie.write_bytes(b"")
    backup.mail_backup(kopie)
    assert backupmails == [backup.BACKUP_MAIL_NAAR]


def test_een_storing_gaat_naar_de_systeembeheerder(app, db, monkeypatch):
    monkeypatch.setattr(uptime_check, "DB_PAD", app.config["DATABASE"])
    _mailadres(db, "admin", "luuk@club.nl")
    assert uptime_check.ontvanger() == "luuk@club.nl"
