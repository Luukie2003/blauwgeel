"""De systeemstatus (taakstatus.py, Beheer > Systeemstatus): de geplande taken leggen vast wanneer ze draaiden en of het
lukte. Een taak die twee keer mislukt of niet meer draait, valt op bij de systeembeheerder, met één mail per probleem."""

from datetime import datetime, timedelta

import pytest

from test_noodstop import _tweede_beheerder
from test_secties_rechten import _login

import agenda
import backup
import mail
import taakstatus
import uptime_check
import weer
import week_overzicht_mail

NU = datetime(2026, 11, 10, 4, 0)
DAG = timedelta(days=1)


@pytest.fixture
def pad(app):
    return app.config["DATABASE"]


@pytest.fixture
def mails(monkeypatch):
    verstuurd = []
    monkeypatch.setattr(
        mail, "stuur_mail",
        lambda onderwerp, tekst, naar=None, **kw: verstuurd.append({"onderwerp": onderwerp, "tekst": tekst, "naar": naar})
        or True,
    )
    return verstuurd


@pytest.fixture
def alleen(monkeypatch):
    """Kijk alleen naar deze taken: de andere draaien in de test niet en zouden anders ook als probleem meetellen."""

    def beperk(*sleutels):
        monkeypatch.setattr(taakstatus, "TAKEN", [t for t in taakstatus.TAKEN if t["sleutel"] in sleutels])

    return beperk


def _volg_vanaf(db, moment):
    """Alsof de systeemstatus de taken al volgt sinds 'moment'."""
    db.execute("UPDATE taak_status SET bekend_sinds = ?", (moment.strftime(taakstatus.TIJD),))
    db.commit()


def _stand(db, sleutel, nu=NU):
    return next(t for t in taakstatus.overzicht(db, nu) if t["sleutel"] == sleutel)


# ---------- De stand per taak ----------


def test_elke_geplande_taak_heeft_een_rij(db):
    rijen = {r["sleutel"] for r in db.execute("SELECT sleutel FROM taak_status")}
    assert rijen == {t["sleutel"] for t in taakstatus.TAKEN}


def test_een_gelukte_taak_staat_op_groen(db, pad, mails):
    _volg_vanaf(db, NU)
    taakstatus.registreer("agenda", True, "3 nieuwe wedstrijden", db_pad=pad, nu=NU)
    stand = _stand(db, "agenda")
    assert (stand["stand"], stand["tekst"], stand["melding"]) == ("ok", "In orde", "3 nieuwe wedstrijden")
    assert mails == []


def test_een_keer_mislukt_is_nog_geen_probleem(db, pad, mails, alleen):
    alleen("agenda")
    _volg_vanaf(db, NU)
    taakstatus.registreer("agenda", True, db_pad=pad, nu=NU)
    taakstatus.registreer("agenda", False, "Niet gelukt voor JO13-1: HTTP Error 404", db_pad=pad, nu=NU + DAG)
    assert _stand(db, "agenda", NU + DAG)["stand"] == "mislukt"
    assert taakstatus.problemen(db, NU + DAG) == [] and mails == []


def test_twee_dagen_niet_gelukt_geeft_een_mail_aan_de_systeembeheerder(db, pad, mails, alleen):
    alleen("agenda")
    db.execute("UPDATE gebruikers SET email = 'luuk@club.nl' WHERE naam = 'admin'")
    _volg_vanaf(db, NU)
    taakstatus.registreer("agenda", True, db_pad=pad, nu=NU)
    taakstatus.registreer("agenda", False, "Niet gelukt voor JO13-1: HTTP Error 404", db_pad=pad, nu=NU + DAG)
    taakstatus.registreer("agenda", False, "Niet gelukt voor JO13-1: HTTP Error 404", db_pad=pad, nu=NU + 2 * DAG + timedelta(hours=3))

    stand = _stand(db, "agenda", NU + 2 * DAG + timedelta(hours=3))
    assert (stand["stand"], stand["tekst"]) == ("probleem", "Niet gelukt sinds 10-11 04:00")
    assert len(mails) == 1 and mails[0]["naar"] == "luuk@club.nl"
    assert mails[0]["onderwerp"] == "Kantine Beheer: Teamagenda's niet gelukt sinds 10-11 04:00"
    assert "JO13-1: HTTP Error 404" in mails[0]["tekst"] and "/beheer/systeemstatus" in mails[0]["tekst"]

    taakstatus.registreer("agenda", False, "nog steeds", db_pad=pad, nu=NU + 3 * DAG)
    assert len(mails) == 1  # één mail per probleem


def test_na_herstel_krijgt_een_nieuw_probleem_weer_een_mail(db, pad, mails, alleen):
    alleen("weer")
    _volg_vanaf(db, NU)
    taakstatus.registreer("weer", True, db_pad=pad, nu=NU)
    taakstatus.registreer("weer", False, "HTTP Error 503", db_pad=pad, nu=NU + 3 * DAG)
    assert len(mails) == 1
    taakstatus.registreer("weer", True, db_pad=pad, nu=NU + 4 * DAG)
    assert _stand(db, "weer", NU + 4 * DAG)["stand"] == "ok"
    taakstatus.registreer("weer", False, "HTTP Error 503", db_pad=pad, nu=NU + 7 * DAG)
    assert len(mails) == 2


def test_een_taak_die_nooit_draait_valt_op_bij_een_andere_taak(db, pad, mails):
    _volg_vanaf(db, NU)
    assert _stand(db, "weer", NU + DAG)["stand"] == "wacht"  # nog niet gedraaid, maar dat kan nog

    # De bereikbaarheidscontrole draait elk uur en kijkt daarbij ook naar de rest.
    taakstatus.registreer("bereikbaarheid", True, "Site bereikbaar", db_pad=pad, nu=NU + 2 * DAG + timedelta(hours=3))

    assert _stand(db, "weer", NU + 2 * DAG + timedelta(hours=3))["tekst"] == "Draait niet"
    assert len(mails) == 1
    assert mails[0]["onderwerp"] == "Kantine Beheer: 3 geplande taken met een probleem"
    for naam in ("Teamagenda's", "Weerbericht", "Weekoverzicht per mail"):
        assert naam in mails[0]["tekst"]
    assert "Back-up" not in mails[0]["tekst"]  # die heeft zijn eigen waarschuwing (zie backup.py)


def test_de_backup_heeft_zijn_eigen_waarschuwing(db):
    _volg_vanaf(db, NU)
    assert _stand(db, "backup", NU + 3 * DAG)["stand"] == "probleem"
    assert "backup" not in {t["sleutel"] for t in taakstatus.problemen(db, NU + 3 * DAG)}


def test_lukt_mailen_niet_dan_de_volgende_keer_opnieuw(db, pad, monkeypatch):
    pogingen = []
    monkeypatch.setattr(mail, "stuur_mail", lambda *a, **kw: pogingen.append(a) and False)
    _volg_vanaf(db, NU)
    taakstatus.registreer("bereikbaarheid", True, db_pad=pad, nu=NU + 3 * DAG)
    taakstatus.registreer("bereikbaarheid", True, db_pad=pad, nu=NU + 3 * DAG + timedelta(hours=1))
    assert len(pogingen) == 2


def test_zonder_database_wordt_er_niets_aangemaakt(tmp_path):
    taakstatus.registreer("weer", True, db_pad=tmp_path / "bestaat-niet.db")
    assert not (tmp_path / "bestaat-niet.db").exists()


# ---------- De taken zelf ----------


def test_de_agenda_legt_vast_welk_team_niet_lukte(db, pad, monkeypatch, mails):
    db.execute("INSERT INTO agenda_feeds (url, team) VALUES ('https://goed.example/a.ics', 'JO11-1')")
    db.execute("INSERT INTO agenda_feeds (url, team) VALUES ('https://kapot.example/b.ics', 'JO13-1')")
    db.commit()

    def haal_op(url):
        if "kapot" in url:
            raise OSError("HTTP Error 404: Not Found")
        return "JO11-1", []

    monkeypatch.setattr(agenda, "haal_feed_op", haal_op)
    agenda.dagelijkse_taak(db_pad=pad)
    stand = _stand(db, "agenda", datetime.now())
    assert stand["stand"] == "mislukt" and stand["melding"] == "Niet gelukt voor JO13-1: HTTP Error 404: Not Found"


def test_de_agenda_zonder_problemen(db, pad, monkeypatch, mails):
    db.execute("INSERT INTO agenda_feeds (url, team) VALUES ('https://goed.example/a.ics', 'JO11-1')")
    db.commit()
    monkeypatch.setattr(agenda, "haal_feed_op", lambda url: ("JO11-1", []))
    agenda.dagelijkse_taak(db_pad=pad)
    stand = _stand(db, "agenda", datetime.now())
    assert (stand["stand"], stand["melding"]) == ("ok", "0 nieuwe wedstrijden")


def test_het_weer_legt_de_reden_vast(db, pad, monkeypatch, mails):
    def kapot():
        raise OSError("HTTP Error 503: Service Unavailable")

    monkeypatch.setattr(weer, "haal_voorspelling_op", kapot)
    assert weer.dagelijkse_taak(db_pad=pad) is None
    assert _stand(db, "weer", datetime.now())["melding"] == "Ophalen mislukt: HTTP Error 503: Service Unavailable"

    dagen = [{"datum": "2026-11-10", "max_temp": 9.5, "neerslag_kans": 40, "weercode": 3}]
    monkeypatch.setattr(weer, "haal_voorspelling_op", lambda: dagen)
    assert weer.dagelijkse_taak(db_pad=pad) == 1
    stand = _stand(db, "weer", datetime.now())
    assert (stand["stand"], stand["melding"]) == ("ok", "Verwachting voor 1 dagen")


def test_de_backup_legt_vast_wat_er_gebeurde(db, pad, monkeypatch, mails):
    monkeypatch.setattr(backup, "BRON", pad)
    monkeypatch.setattr(backup, "_dagelijkse_backup", lambda: (1, "Back-up afgekeurd: database disk image is malformed"))
    assert backup.dagelijkse_taak([]) == 1
    assert _stand(db, "backup", datetime.now())["melding"] == "Back-up afgekeurd: database disk image is malformed"

    def crash():
        raise RuntimeError("schijf vol")

    monkeypatch.setattr(backup, "_dagelijkse_backup", crash)
    with pytest.raises(RuntimeError):
        backup.dagelijkse_taak([])
    assert _stand(db, "backup", datetime.now())["melding"] == "Gecrasht: schijf vol"


def test_de_bereikbaarheidscontrole_legt_vast(db, pad, monkeypatch, tmp_path, mails):
    monkeypatch.setattr(uptime_check, "site_bereikbaar", lambda: (True, None))
    monkeypatch.setattr(uptime_check, "STATUS_PAD", tmp_path / "uptime_status.txt")
    monkeypatch.setattr(uptime_check, "DB_PAD", pad)
    uptime_check.controleer()
    stand = _stand(db, "bereikbaarheid", datetime.now())
    assert (stand["stand"], stand["melding"]) == ("ok", "Site bereikbaar")


def test_het_weekoverzicht_op_een_andere_dag_dan_maandag(db, pad, monkeypatch, mails):
    monkeypatch.setattr(taakstatus, "DB_PAD", pad)
    week_overzicht_mail.main(nu=datetime(2026, 11, 10))  # een dinsdag
    stand = _stand(db, "weekoverzicht", datetime.now())
    assert (stand["stand"], stand["melding"]) == ("ok", "Geen maandag, niets te doen")


# ---------- Op de site: alleen voor de systeembeheerder ----------


def _stilgevallen_agenda(db):
    oud = (datetime.now() - 5 * DAG).strftime(taakstatus.TIJD)
    db.execute(
        """UPDATE taak_status SET bekend_sinds = ?, laatst_gedraaid = ?, laatst_gelukt = ?, laatste_ok = 0,
               melding = 'Niet gelukt voor JO13-1: HTTP Error 404' WHERE sleutel = 'agenda'""",
        (oud, oud, oud),
    )
    db.commit()


def test_de_systeembeheerder_ziet_een_stilgevallen_taak_op_het_overzicht(ingelogde_client, db):
    _stilgevallen_agenda(db)
    tekst = ingelogde_client.get("/").data.decode()
    assert "Teamagenda&#39;s: niet gelukt sinds" in tekst and "/beheer/systeemstatus" in tekst


def test_een_andere_beheerder_ziet_hem_niet(client, db):
    _stilgevallen_agenda(db)
    _tweede_beheerder(db)
    _login(client, "beheerder2")
    tekst = client.get("/").data.decode()
    assert "niet gelukt sinds" not in tekst and "/beheer/systeemstatus" not in tekst  # ook niet in het menu


def test_de_pagina_voor_de_systeembeheerder(ingelogde_client, db):
    _stilgevallen_agenda(db)
    db.execute("UPDATE gebruikers SET email = 'luuk@club.nl' WHERE naam = 'admin'")
    db.commit()
    resp = ingelogde_client.get("/beheer/systeemstatus")
    tekst = resp.data.decode()
    assert resp.status_code == 200
    for stuk in ("Geplande taken", "Teamagenda", "Weerbericht", "Bereikbaarheid", "HTTP Error 404", "luuk@club.nl"):
        assert stuk in tekst
    assert 'href="/beheer/systeemstatus"' in ingelogde_client.get("/").data.decode()  # in het menu


def test_zonder_e_mailadres_zegt_de_pagina_waar_de_mails_heen_gaan(ingelogde_client):
    assert "nog geen e-mailadres" in ingelogde_client.get("/beheer/systeemstatus").data.decode()


def test_een_andere_beheerder_komt_niet_op_de_pagina(client, db):
    _tweede_beheerder(db)
    _login(client, "beheerder2")
    resp = client.get("/beheer/systeemstatus")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
