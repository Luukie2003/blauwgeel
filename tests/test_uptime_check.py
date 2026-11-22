"""De bereikbaarheidscontrole (uptime_check.py): één mislukte poging is nog geen storing. Pas als de site na een paar
pogingen, met een minuut ertussen, nog niet reageert, gaat er een mail uit; een hapering staat wel in de systeemstatus."""

from datetime import datetime

import pytest

import mail
import taakstatus
import uptime_check


@pytest.fixture
def mails(monkeypatch):
    verstuurd = []
    monkeypatch.setattr(
        mail, "stuur_mail",
        lambda onderwerp, tekst, naar=None, **kw: verstuurd.append({"onderwerp": onderwerp, "tekst": tekst}) or True,
    )
    return verstuurd


@pytest.fixture
def gewacht(monkeypatch, app, tmp_path):
    """De controle tegen de testdatabase, met een eigen statusbestand en zonder echt te wachten. Geeft de lijst met
    gewachte seconden terug."""
    monkeypatch.setattr(uptime_check, "STATUS_PAD", tmp_path / "uptime_status.txt")
    monkeypatch.setattr(uptime_check, "DB_PAD", app.config["DATABASE"])
    seconden = []
    monkeypatch.setattr(uptime_check, "_wacht", seconden.append)
    return seconden


def _antwoorden(monkeypatch, *uitkomsten):
    """Laat de pogingen achter elkaar deze uitkomsten geven: True = gelukt, een tekst = die foutmelding."""
    rij = iter(uitkomsten)

    def poging():
        uitkomst = next(rij)
        return (True, None) if uitkomst is True else (False, uitkomst)

    monkeypatch.setattr(uptime_check, "site_bereikbaar", poging)


def _melding(db):
    stand = next(t for t in taakstatus.overzicht(db, datetime.now()) if t["sleutel"] == "bereikbaarheid")
    return stand["stand"], stand["melding"]


def test_een_hapering_die_bij_de_tweede_poging_over_is_geeft_geen_mail(db, monkeypatch, gewacht, mails):
    _antwoorden(monkeypatch, "The handshake operation timed out", True)
    uptime_check.controleer()
    assert mails == []
    assert gewacht == [uptime_check.PAUZE_SECONDEN]
    assert uptime_check.vorige_status() == "ok"
    assert _melding(db) == ("ok", "Site bereikbaar, pas bij poging 2 (eerst: The handshake operation timed out)")


def test_pas_als_geen_enkele_poging_lukt_komt_er_een_mail(db, monkeypatch, gewacht, mails):
    _antwoorden(monkeypatch, "timed out", "timed out", "HTTP Error 502: Bad Gateway")
    uptime_check.controleer()
    assert [m["onderwerp"] for m in mails] == ["Kantine Beheer is niet bereikbaar"]
    assert "Foutmelding (laatste poging): HTTP Error 502: Bad Gateway" in mails[0]["tekst"]
    assert gewacht == [uptime_check.PAUZE_SECONDEN] * (uptime_check.POGINGEN - 1)
    assert uptime_check.vorige_status() == "down"
    assert _melding(db) == ("ok", "Site reageerde niet, ook niet na 3 pogingen: HTTP Error 502: Bad Gateway")


def test_een_storing_wordt_maar_een_keer_gemeld_en_het_herstel_ook(db, monkeypatch, gewacht, mails):
    _antwoorden(monkeypatch, *["timed out"] * (2 * uptime_check.POGINGEN), True)
    uptime_check.controleer()
    uptime_check.controleer()  # een uur later nog steeds plat: geen tweede mail
    uptime_check.controleer()
    assert [m["onderwerp"] for m in mails] == ["Kantine Beheer is niet bereikbaar", "Kantine Beheer is weer bereikbaar"]


def test_als_alles_meteen_lukt_wordt_er_niet_gewacht(db, monkeypatch, gewacht, mails):
    _antwoorden(monkeypatch, True)
    uptime_check.controleer()
    assert (gewacht, mails) == ([], [])
    assert _melding(db) == ("ok", "Site bereikbaar")
