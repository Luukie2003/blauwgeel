"""'s Avonds (1.80.0): vanaf een vaste tijd draaien alleen nog de dia's en de onderdelen die ook 's avonds mogen, tot
de volgende ochtend -- zie _overdag in routes/kiosk/dia_gegevens.py en kiosk_scherm_avond in routes/kiosk/scherm.py."""
from datetime import datetime

from conftest import stel_csrf_token_in as _csrf

import kiosk_momenten
from routes.kiosk.dia_gegevens import _bouw_slides, _overdag


def _ms(tekst):
    return kiosk_momenten.ms(datetime.strptime(tekst, "%Y-%m-%d %H:%M"))


def test_zonder_avond_draait_alles_de_hele_dag():
    assert _overdag({"avond_vanaf": None}, datetime(2026, 10, 31, 18, 0)) is None
    assert _overdag({"avond_vanaf": "05:00"}, datetime(2026, 10, 31, 18, 0)) is None  # vóór de ochtend: geen avond


def test_overdag_loopt_van_de_ochtend_tot_de_avond():
    instellingen = {"avond_vanaf": "16:00"}
    assert _overdag(instellingen, datetime(2026, 10, 31, 10, 0)) == (_ms("2026-10-31 06:00"), _ms("2026-10-31 16:00"))
    # Vanaf de avond, ook na middernacht, is het pas de volgende ochtend weer overdag.
    for nu in (datetime(2026, 10, 31, 16, 0), datetime(2026, 10, 31, 23, 30), datetime(2026, 11, 1, 1, 30)):
        assert _overdag(instellingen, nu) == (_ms("2026-11-01 06:00"), _ms("2026-11-01 16:00"))


def test_s_avonds_alleen_de_onderdelen_die_aan_staan(ingelogde_client, app, db):
    db.execute("INSERT INTO kiosk_motm (team, speler, volgorde) VALUES ('Zaterdag 1', 'Jan Jansen', 0)")
    db.commit()
    kop = {"csrf_token": _csrf(ingelogde_client)}
    resp = ingelogde_client.post("/kiosk/scherm/avond", data={**kop, "avond_vanaf": "16:00", "avond_club_van_20": "on"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/kiosk/diashow#avond")
    rij = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert (rij["avond_vanaf"], rij["avond_club_van_20"], rij["avond_motm"], rij["avond_sponsorlogos"]) == ("16:00", 1, 0, 0)
    with app.test_request_context():
        slides = _bouw_slides(db, datetime(2026, 10, 31, 12, 0))
    motm = next(s for s in slides if s["type"] == "motm")
    assert (motm["van"], motm["tot"]) == (_ms("2026-10-31 06:00"), _ms("2026-10-31 16:00"))
    assert all("tot" not in s for s in slides if s["type"].startswith("club_van_20"))
    pagina = ingelogde_client.get("/kiosk/diashow").get_data(as_text=True)
    assert 'id="avond"' in pagina and 'name="avond_vanaf" value="16:00"' in pagina


def test_een_avond_voor_de_ochtend_kan_niet(ingelogde_client, db):
    kop = {"csrf_token": _csrf(ingelogde_client)}
    resp = ingelogde_client.post("/kiosk/scherm/avond", data={**kop, "avond_vanaf": "05:00"}, follow_redirects=True)
    assert "Kies een tijd na 6 uur" in resp.get_data(as_text=True)
    assert db.execute("SELECT avond_vanaf FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()[0] is None
    # Leeg maken zet de avond weer uit: dan draait alles de hele dag.
    ingelogde_client.post("/kiosk/scherm/avond", data={**kop, "avond_vanaf": ""})
    assert db.execute("SELECT avond_vanaf FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()[0] is None
