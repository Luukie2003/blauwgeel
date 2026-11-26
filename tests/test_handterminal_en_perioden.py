"""Het startscherm en de tabbalk van de handterminal, en een uitzondering voor een hele periode (bijv. de winterstop)."""

from datetime import date

from conftest import stel_csrf_token_in as _csrf

from voorspelling import lees_kalender


# ---------- Uitzondering voor een periode ----------


def _periode(client, van, tot, status="dicht", opmerking="Winterstop"):
    return client.post("/prognose/uitzondering", data={
        "csrf_token": _csrf(client), "datum": van, "tot": tot, "status": status, "opmerking": opmerking,
    })


def test_winterstop_als_periode(ingelogde_client, db):
    _periode(ingelogde_client, "2026-12-23", "2027-01-10")
    rijen = db.execute("SELECT datum, open, opmerking FROM verkoop_uitzonderingen ORDER BY datum").fetchall()
    assert len(rijen) == 19 and rijen[0]["datum"] == "2026-12-23" and rijen[-1]["datum"] == "2027-01-10"
    assert all(r["open"] == 0 and r["opmerking"] == "Winterstop" for r in rijen)

    # Een woensdag in de winterstop is dicht, ook voor de prognose.
    woensdag = date(2026, 12, 30)
    assert lees_kalender(db, woensdag, woensdag)[woensdag]["open"] is False

    tekst = ingelogde_client.get("/prognose").data.decode()
    assert "t/m zondag 10-1-2027" in tekst and "(19 dagen)" in tekst and tekst.count("Winterstop") >= 1


def test_periode_in_een_keer_verwijderen(ingelogde_client, db):
    _periode(ingelogde_client, "2026-12-23", "2027-01-10")
    _periode(ingelogde_client, "2027-01-20", "2027-01-20", status="open", opmerking="Toernooi")  # los, blijft staan
    ingelogde_client.post("/prognose/uitzondering/periode/verwijderen", data={
        "csrf_token": _csrf(ingelogde_client), "van": "2026-12-23", "tot": "2027-01-10"})
    assert [r[0] for r in db.execute("SELECT datum FROM verkoop_uitzonderingen")] == ["2027-01-20"]


def test_losse_dagen_blijven_losse_regels(ingelogde_client, db):
    for datum, opmerking in (("2026-11-04", "Bekerwedstrijd"), ("2026-11-05", "Vergadering")):
        _periode(ingelogde_client, datum, "", status="open", opmerking=opmerking)
    tekst = ingelogde_client.get("/prognose").data.decode()
    assert "Bekerwedstrijd" in tekst and "Vergadering" in tekst and "(2 dagen)" not in tekst


def test_foute_periodes_worden_geweigerd(ingelogde_client, db):
    _periode(ingelogde_client, "2027-01-10", "2026-12-23")  # eind voor begin
    _periode(ingelogde_client, "2026-01-01", "2027-06-01")  # langer dan een jaar
    assert db.execute("SELECT COUNT(*) FROM verkoop_uitzonderingen").fetchone()[0] == 0


# ---------- De handterminal ----------
