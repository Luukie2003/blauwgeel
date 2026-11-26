"""Afspraken met een merk (2.22.0): vastleggen bij de Merkanalyse, wat ze opleveren, en het seintje bij Factuur inboeken."""

from datetime import date

from conftest import stel_csrf_token_in as _csrf
from test_bestelling_concept import CHAUD_TRAY, _levering

import afspraken
import facturen


def _in(db, pid, aantal, datum, opmerking="Levering"):
    db.execute("INSERT INTO mutaties (product_id, type, aantal, datum, opmerking) VALUES (?, 'in', ?, ?, ?)",
               (pid, aantal, datum, opmerking))
    db.commit()


def test_vastleggen_en_controleren(db):
    assert afspraken.voeg_toe(db, "Chaudfontaine", "korting", "1,00", None, None, "2026-11-01", None) is None
    assert afspraken.voeg_toe(db, "Chaudfontaine", "gratis", None, "10", "via Robertus", "2026-11-01", "2026-12-31") is None
    assert afspraken.voeg_toe(db, "Chaudfontaine", "anders", None, None, "Koelkast in bruikleen", "2026-11-01", None) is None
    assert "korting" in afspraken.voeg_toe(db, "Chaudfontaine", "korting", "", None, None, "2026-11-01", None)
    assert "gratis" in afspraken.voeg_toe(db, "Chaudfontaine", "gratis", None, "0", None, "2026-11-01", None)
    assert "Beschrijf" in afspraken.voeg_toe(db, "Chaudfontaine", "anders", None, None, " ", "2026-11-01", None)
    assert "einde" in afspraken.voeg_toe(db, "Chaudfontaine", "korting", "1", None, None, "2026-11-10", "2026-11-01")
    assert "begindatum" in afspraken.voeg_toe(db, "Chaudfontaine", "korting", "1", None, None, "morgen", None)
    assert "merk" in afspraken.voeg_toe(db, "", "korting", "1", None, None, "2026-11-01", None)
    teksten = sorted(afspraken.tekst(r) for r in db.execute("SELECT * FROM afspraken").fetchall())
    assert teksten == ["1 doos gratis op 10 (via Robertus)", "Koelkast in bruikleen", "€ 1,00 korting per doos"]


def test_wat_de_afspraak_oplevert(db):
    _lev, chaud, cola, _b = _levering(db)  # Chaudfontaine per tray van 24
    afspraken.voeg_toe(db, "Chaudfontaine", "korting", "0,50", None, None, "2026-11-01", None)
    afspraken.voeg_toe(db, "Chaudfontaine", "gratis", None, "5", None, "2026-11-01", "2026-11-30")
    afspraken.voeg_toe(db, "Chaudfontaine", "korting", "2", None, None, "2025-01-01", "2025-12-31")  # is voorbij
    _in(db, chaud, 24 * 6, "2026-11-05 12:00")
    _in(db, chaud, 24 * 6, "2026-12-05 12:00")
    _in(db, chaud, 24 * 20, "2026-11-06 12:00", "Correctie na telling")  # telt niet
    _in(db, chaud, 24, "2026-10-20 12:00")  # voor het begin
    lijst = afspraken.van_merk(db, "chaudfontaine", date(2026, 12, 10))
    assert [a["loopt"] for a in lijst] == [True, False, False]
    korting = next(a for a in lijst if a["soort"] == "korting" and a["loopt"])
    gratis = next(a for a in lijst if a["soort"] == "gratis")
    assert korting["dozen"] == 12 and korting["korting"] == 6.0
    assert gratis["dozen"] == 6 and gratis["gratis"] == 1  # tot en met 30 november


def test_seintje_bij_factuur_inboeken(ingelogde_client, db):
    _lev, chaud, _cola, b = _levering(db)
    afspraken.voeg_toe(db, "Chaudfontaine", "gratis", None, "10", None, "2026-01-01", None)
    _in(db, chaud, 24 * 11, "2026-11-05 12:00")
    ronde = facturen.ronde_voor_bestelling(db, b)
    facturen.scan(db, ronde, CHAUD_TRAY)
    pagina = ingelogde_client.get(f"/facturen/{ronde}").data.decode()
    assert 'id="afspraken"' in pagina and "1 doos gratis op 10" in pagina and "1 gratis doos bij" in pagina
    assert afspraken.bij_factuur(db, []) == []


def test_bij_de_merkanalyse(ingelogde_client, db):
    _levering(db)
    csrf = _csrf(ingelogde_client)
    ingelogde_client.post("/rapporten/merk/afspraak", data={"csrf_token": csrf, "merk": "Chaudfontaine", "soort": "korting",
                                                            "bedrag": "1,00", "vanaf": "2026-11-01"})
    pagina = ingelogde_client.get("/rapporten/merk?merk=Chaudfontaine").data.decode()
    assert "€ 1,00 korting per doos" in pagina
    afspraak_id = db.execute("SELECT id FROM afspraken").fetchone()[0]
    assert db.execute("SELECT actie FROM logboek WHERE endpoint = 'merk_afspraak_toevoegen'").fetchone()
    ingelogde_client.post(f"/rapporten/merk/afspraak/{afspraak_id}/verwijderen", data={"csrf_token": csrf, "merk": "Chaudfontaine"})
    assert db.execute("SELECT COUNT(*) FROM afspraken").fetchone()[0] == 0


def test_de_app_krijgt_meer_dan_besteld_en_de_afspraken(ingelogde_client, db):
    _lev, chaud, _cola, b = _levering(db)
    afspraken.voeg_toe(db, "Chaudfontaine", "korting", "1", None, None, "2026-01-01", None)
    ronde = facturen.ronde_voor_bestelling(db, b)
    for _ in range(4):
        facturen.scan(db, ronde, CHAUD_TRAY)  # 4 trays, 2 besteld
    data = ingelogde_client.get(f"/api/facturen/{ronde}").get_json()
    assert [m["naam"] for m in data["meer_dan_besteld"]] == ["Chaudfontaine"]
    assert data["afspraken"][0]["tekst"] == "€ 1,00 korting per doos"
