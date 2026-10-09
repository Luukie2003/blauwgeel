from datetime import date, datetime, timedelta

import pytest

import voorspelling
from test_seizoensrapport import _product, _weekelijkse_tellingen

NU = datetime(2026, 10, 8, 12, 0)


@pytest.fixture
def bewaren(monkeypatch, db):
    """Zet het bewaren aan, met teller van hoe vaak er echt gerekend wordt, en geschiedenis om mee te rekenen."""
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    voorspelling.wis_bewaarde_resultaten()
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 6, 27), tot=date(2026, 10, 3))
    aantal = {"prognose": 0, "verdeling": 0}
    echte_prognose, echte_verdeling = voorspelling._maak_prognose, voorspelling._verdeling

    def geteld_prognose(*a, **k):
        aantal["prognose"] += 1
        return echte_prognose(*a, **k)

    def geteld_verdeling(*a, **k):
        aantal["verdeling"] += 1
        return echte_verdeling(*a, **k)

    monkeypatch.setattr(voorspelling, "_maak_prognose", geteld_prognose)
    monkeypatch.setattr(voorspelling, "_verdeling", geteld_verdeling)
    yield {"aantal": aantal, "product": pils}
    voorspelling.wis_bewaarde_resultaten()


def test_dezelfde_vraag_rekent_maar_een_keer(db, bewaren):
    eerste = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    tweede = voorspelling.maak_prognose(db, dagen=7, nu=NU + timedelta(minutes=3))  # zelfde tijdvenster
    assert bewaren["aantal"]["prognose"] == 1
    assert eerste["totaal"] == tweede["totaal"]

    voorspelling.verdeling(db, NU)
    voorspelling.verdeling(db, NU)
    assert bewaren["aantal"]["verdeling"] == 1


def test_bewaard_resultaat_is_gelijk_aan_nieuw_rekenen(db, bewaren, monkeypatch):
    bewaard = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    monkeypatch.setattr(voorspelling, "CACHE_AAN", False)
    vers = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert bewaard["totaal"] == vers["totaal"]
    assert [p["verwacht"] for p in bewaard["producten"]] == [p["verwacht"] for p in vers["producten"]]
    assert voorspelling.verdeling(db, NU)["omzet"] == voorspelling._verdeling(db, NU)["omzet"]


def test_andere_parameters_of_een_ander_tijdvenster_geven_een_nieuwe_berekening(db, bewaren):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    voorspelling.maak_prognose(db, dagen=14, nu=NU)
    voorspelling.maak_prognose(db, dagen=7, nu=NU + timedelta(hours=2))
    assert bewaren["aantal"]["prognose"] == 3


@pytest.mark.parametrize(
    "wijziging",
    [
        "UPDATE producten SET voorraad = voorraad + 5",
        "UPDATE producten SET min_voorraad = min_voorraad + 1",
        "UPDATE telling_regels SET verkocht = verkocht + 1 WHERE id = (SELECT MAX(id) FROM telling_regels)",
        "UPDATE instellingen SET verkoopdagen = '1,2,3'",
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('ZA 1', '2026-10-10', 'x', 1)",
        "INSERT INTO verkoop_uitzonderingen (datum, open) VALUES ('2026-10-09', 0)",
        "INSERT INTO weer_voorspelling (datum, max_temp, neerslag_kans, weercode) VALUES ('2026-10-09', 12, 40, 3)",
        # Een openstaande bestelling met een regel telt als "al onderweg" in de prognose.
        "INSERT INTO bestellingen (id, status, aangemaakt_op) VALUES (900, 'besteld', '2026-10-08 10:00')",
    ],
)
def test_een_wijziging_in_de_gegevens_geeft_een_nieuwe_berekening(db, bewaren, wijziging):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    voorspelling.verdeling(db, NU)

    db.execute(wijziging)
    if "bestellingen" in wijziging:
        db.execute(
            "INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (900, ?, 24)", (bewaren["product"],)
        )
    db.commit()
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    voorspelling.verdeling(db, NU)

    assert bewaren["aantal"] == {"prognose": 2, "verdeling": 2}, wijziging


def test_een_nieuwe_telling_geeft_een_nieuwe_berekening(db, bewaren):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-10-07 23:00', 'x')")
    db.commit()
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert bewaren["aantal"]["prognose"] == 2


def test_een_wijziging_die_niets_met_de_voorspelling_te_maken_heeft_houdt_het_bewaarde(db, bewaren):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    db.execute("INSERT INTO mededelingen (tekst, naam, datum) VALUES ('hoi', 'x', '2026-10-08 10:00')")
    db.execute("UPDATE producten SET naam = naam || '!'")  # een naamswijziging verandert de uitkomst niet
    db.commit()
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert bewaren["aantal"]["prognose"] == 1


def test_elke_database_heeft_zijn_eigen_bewaarde_uitkomst(app, db, bewaren, tmp_path):
    import sqlite3
    import shutil

    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    kopie = tmp_path / "kopie.db"
    shutil.copyfile(app.config["DATABASE"], kopie)
    andere = sqlite3.connect(kopie)
    andere.row_factory = sqlite3.Row
    voorspelling.maak_prognose(andere, dagen=7, nu=NU)  # zelfde gegevens, ander bestand
    andere.close()
    assert bewaren["aantal"]["prognose"] == 2


def test_de_bewaarplaats_blijft_klein(db, bewaren):
    for uur in range(voorspelling.CACHE_MAX_ITEMS + 10):
        voorspelling.verdeling(db, NU + timedelta(hours=uur))
    assert len(voorspelling._CACHE) <= voorspelling.CACHE_MAX_ITEMS


def test_een_pagina_die_sleutels_toevoegt_verandert_het_bewaarde_niet(db, bewaren):
    eerste = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    eerste["extra"] = "alleen voor deze pagina"
    assert "extra" not in voorspelling.maak_prognose(db, dagen=7, nu=NU)


def test_zonder_geschiedenis_geeft_het_ook_gewoon_een_antwoord(app, monkeypatch, tmp_path):
    """De vingerafdruk moet ook werken op een lege database."""
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    import sqlite3
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    assert voorspelling.verdeling(conn, NU) is None
    assert not voorspelling.maak_prognose(conn, nu=NU)["beschikbaar"]
    conn.close()


def test_pagina_s_geven_hetzelfde_antwoord_met_en_zonder_bewaren(ingelogde_client, db, bewaren, monkeypatch):
    def pagina(pad):
        return ingelogde_client.get(pad).data.decode()

    pagina("/")  # de welkomstmelding verschijnt maar op de allereerste pagina na het inloggen
    monkeypatch.setattr(voorspelling, "CACHE_AAN", False)
    zonder = {pad: pagina(pad) for pad in ("/bestellijst", "/prognose", "/tellingen")}
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    for pad, verwacht in zonder.items():
        assert pagina(pad) == verwacht  # eerste keer rekenen
        assert pagina(pad) == verwacht  # tweede keer uit het geheugen
