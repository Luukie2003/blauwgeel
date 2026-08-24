from conftest import stel_csrf_token_in as _csrf

import agenda


def test_agenda_link_toevoegen_en_verwijderen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/club-instellingen/toevoegen",
        data={"csrf_token": _csrf(ingelogde_client), "url": "https://data.sportlink.com/ical-team?token=abc"},
    )
    assert resp.status_code == 302
    feed = db.execute("SELECT * FROM agenda_feeds ORDER BY id DESC LIMIT 1").fetchone()
    assert feed["url"] == "https://data.sportlink.com/ical-team?token=abc"
    assert feed["team"] is None  # nog niet opgehaald

    resp = ingelogde_client.get("/club-instellingen")
    assert resp.status_code == 200
    assert b"data.sportlink.com" in resp.data

    resp = ingelogde_client.post(
        f"/club-instellingen/{feed['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM agenda_feeds WHERE id = ?", (feed["id"],)).fetchone() is None


def test_lege_link_wordt_niet_toegevoegd(ingelogde_client, db):
    aantal_voor = db.execute("SELECT COUNT(*) AS n FROM agenda_feeds").fetchone()["n"]
    ingelogde_client.post(
        "/club-instellingen/toevoegen",
        data={"csrf_token": _csrf(ingelogde_client), "url": ""},
    )
    aantal_na = db.execute("SELECT COUNT(*) AS n FROM agenda_feeds").fetchone()["n"]
    assert aantal_na == aantal_voor


def test_verversen_gebruikt_agenda_module(ingelogde_client, db, monkeypatch):
    """De route moet de gedeelde agenda.ververs_wedstrijden aanroepen (zelfde
    functie als de geplande dagelijkse taak), niet zijn eigen logica."""
    aangeroepen_met = {}

    def nep_ververs(db_pad=None, vandaag=None):
        aangeroepen_met["db_pad"] = db_pad
        return 7

    monkeypatch.setattr(agenda, "ververs_wedstrijden", nep_ververs)
    resp = ingelogde_client.post(
        "/club-instellingen/verversen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert aangeroepen_met["db_pad"]


def test_controleren_toont_resultaat_zonder_database_te_wijzigen(ingelogde_client, db, monkeypatch):
    db.execute("INSERT INTO agenda_feeds (url) VALUES (?)", ("https://voorbeeld.nl/feed.ics",))
    db.commit()

    def nep_controleer(urls):
        assert urls == ["https://voorbeeld.nl/feed.ics"]
        return [{"url": urls[0], "ok": True, "team": "Testteam", "aantal": 3}]

    monkeypatch.setattr(agenda, "controleer_feeds", nep_controleer)
    resp = ingelogde_client.post(
        "/club-instellingen/controleren", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    aantal_wedstrijden = db.execute("SELECT COUNT(*) AS n FROM wedstrijden").fetchone()["n"]
    assert aantal_wedstrijden == 0  # controleren raakt de wedstrijden-tabel niet aan


def test_vrijwilliger_mag_geen_club_instellingen_beheren(client, db, csrf):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op) "
        "VALUES ('vrijwilliger1', 'x', 'vrijwilliger', '2026-01-01 10:00')"
    )
    db.commit()
    gebruiker = db.execute(
        "SELECT * FROM gebruikers WHERE naam = 'vrijwilliger1'"
    ).fetchone()
    with client.session_transaction() as sess:
        sess["gebruiker_id"] = gebruiker["id"]
        sess["gebruiker_naam"] = "vrijwilliger1"
        sess["gebruiker_rol"] = "vrijwilliger"
        sess["csrf_token"] = csrf

    resp = client.get("/club-instellingen")
    assert resp.status_code == 302  # geweerd, terug naar dashboard
