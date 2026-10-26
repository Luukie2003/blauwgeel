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
    aantal = {"prognose": 0, "verdeling": 0, "model": 0}
    echte_prognose, echte_verdeling = voorspelling._maak_prognose, voorspelling._verdeling
    echt_model = voorspelling._prognose_fit

    def geteld_model(*a, **k):
        aantal["model"] += 1
        return echt_model(*a, **k)

    def geteld_prognose(*a, **k):
        aantal["prognose"] += 1
        return echte_prognose(*a, **k)

    def geteld_verdeling(*a, **k):
        aantal["verdeling"] += 1
        return echte_verdeling(*a, **k)

    monkeypatch.setattr(voorspelling, "_maak_prognose", geteld_prognose)
    monkeypatch.setattr(voorspelling, "_verdeling", geteld_verdeling)
    monkeypatch.setattr(voorspelling, "_prognose_fit", geteld_model)
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

    assert bewaren["aantal"]["prognose"] == 2, wijziging
    # De verdeling (de omzet per dag tot de laatste telling) hangt alleen af van de tellingen en de kalender tot dan: een
    # boeking, een bestelling of iets in de komende dagen (hier na de laatste telling van 3 oktober) rekent hem niet
    # opnieuw.
    geschiedenis = wijziging.startswith(("UPDATE telling_regels", "UPDATE instellingen"))
    assert bewaren["aantal"]["verdeling"] == (2 if geschiedenis else 1), wijziging


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
    zonder = {pad: pagina(pad) for pad in ("/bestellijst", "/prognose", "/tellingen/cijfers")}
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    for pad, verwacht in zonder.items():
        assert pagina(pad) == verwacht  # eerste keer rekenen
        assert pagina(pad) == verwacht  # tweede keer uit het geheugen


# ---------- Het zware model apart bewaren ----------


def test_een_voorraadwijziging_rekent_het_model_niet_opnieuw_maar_wel_het_advies(db, bewaren):
    """Elke boeking verandert de voorraad; het model aanpassen (het zware deel) hoeft daarvoor niet opnieuw."""
    eerste = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    voor = next(p for p in eerste["producten"] if p["product"]["id"] == bewaren["product"])["voorraad"]

    db.execute("UPDATE producten SET voorraad = voorraad + 500 WHERE id = ?", (bewaren["product"],))
    db.commit()
    tweede = voorspelling.maak_prognose(db, dagen=7, nu=NU)

    assert bewaren["aantal"]["prognose"] == 2  # de uitkomst per product is opnieuw bepaald...
    assert bewaren["aantal"]["model"] == 1  # ...maar het model niet
    na = next(p for p in tweede["producten"] if p["product"]["id"] == bewaren["product"])
    assert na["voorraad"] == voor + 500
    assert tweede["model"] == eerste["model"]


def test_het_model_rekent_pas_opnieuw_na_een_nieuwe_telling(db, bewaren, monkeypatch):
    """7 dagen, 14 dagen en de bestelperiode van een leverancier (bijv. 6 dagen), uren later en ook de dagen erna: één
    keer het zware deel. Pas na een nieuwe telling opnieuw (zie model_vingerafdruk)."""
    zeven = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    veertien = voorspelling.maak_prognose(db, dagen=14, nu=NU + timedelta(hours=3))
    voorspelling.maak_prognose(db, dagen=6, nu=NU + timedelta(hours=20))
    voorspelling.maak_prognose(db, dagen=7, nu=NU + timedelta(days=2))  # twee kantinedagen later
    assert bewaren["aantal"]["model"] == 1
    assert veertien["totaal"]["omzet"] > zeven["totaal"]["omzet"]

    # Uren later met het model van die middag: (bijna) hetzelfde als vers gerekend.
    monkeypatch.setattr(voorspelling, "CACHE_AAN", False)
    vers = voorspelling.maak_prognose(db, dagen=14, nu=NU + timedelta(hours=3))
    assert veertien["totaal"]["omzet"] == pytest.approx(vers["totaal"]["omzet"], rel=0.01)
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    gerekend = bewaren["aantal"]["model"]  # het vers rekenen hierboven telt ook mee

    tid = db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-10-10 23:00', 'x')").lastrowid
    db.execute(
        """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
           VALUES (?, ?, 120, 50, 70, 2.0)""", (tid, bewaren["product"]),
    )
    db.commit()
    voorspelling.maak_prognose(db, dagen=7, nu=NU + timedelta(days=2, hours=1))
    assert bewaren["aantal"]["model"] == gerekend + 1


def test_iets_in_de_komende_dagen_rekent_alleen_het_voorspelvenster_opnieuw(db, bewaren):
    """Een thuiswedstrijd volgende week (of het weer, of een gesloten dag) verandert de prognose, maar niet het model:
    dat kijkt alleen naar de tellingen en wat er tot de laatste telling gebeurde."""
    voor = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    db.execute("INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('ZA 1', '2026-10-10', 'x', 1)")
    db.commit()
    na = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert bewaren["aantal"]["model"] == 1 and bewaren["aantal"]["prognose"] == 2
    assert na["totaal"]["omzet"] > voor["totaal"]["omzet"]  # met een thuiswedstrijd erbij wordt het drukker


def test_wat_net_gebruikt_is_blijft_bewaard(db, monkeypatch):
    """Het geheugen houdt CACHE_MAX_ITEMS uitkomsten; is het vol, dan gaat de langst niet gebruikte eruit. Het model,
    dat bij elke prognose weer gebruikt wordt, blijft zo staan terwijl er elk uur nieuwe prognoses bijkomen."""
    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    monkeypatch.setattr(voorspelling, "SCHIJF_AAN", False)
    monkeypatch.setattr(voorspelling, "CACHE_MAX_ITEMS", 3)
    voorspelling.wis_bewaarde_resultaten()
    gerekend = []

    def bewaar(naam):
        return voorspelling._bewaard(db, naam, NU, (), lambda: gerekend.append(naam) or naam, lambda _: "x", tijdvak="altijd")

    bewaar("model")
    for i in range(5):
        bewaar(f"prognose-{i}")
        bewaar("model")  # bij elke prognose weer gebruikt
    assert gerekend.count("model") == 1 and len(gerekend) == 6
    voorspelling.wis_bewaarde_resultaten()


@pytest.mark.parametrize(
    "wijziging",
    [
        "INSERT INTO tellingen (datum, naam) VALUES ('2026-10-07 23:00', 'x')",
        "UPDATE telling_regels SET verkocht = verkocht + 1 WHERE id = (SELECT MAX(id) FROM telling_regels)",
        "UPDATE instellingen SET verkoopdagen = '1,2,3'",
        # Een wedstrijd die terug is gezet in de agenda, op een dag die al geteld is.
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('ZA 1', '2026-09-12', 'x', 1)",
    ],
)
def test_een_wijziging_in_de_geschiedenis_rekent_het_model_wel_opnieuw(db, bewaren, wijziging):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    db.execute(wijziging)
    db.commit()
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert bewaren["aantal"]["model"] == 2


def test_dagoverzicht_van_een_aanroep_wijzigt_het_bewaarde_model_niet(db, bewaren):
    eerste = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    eerste["dagen_overzicht"][0]["omzet"] = -1
    db.execute("UPDATE producten SET voorraad = voorraad + 1")
    db.commit()
    tweede = voorspelling.maak_prognose(db, dagen=7, nu=NU)
    assert tweede["dagen_overzicht"][0]["omzet"] != -1


# ---------- Een uur bewaren, en niet dubbel rekenen ----------


def test_binnen_een_uur_blijft_het_bewaarde_staan(db, bewaren):
    voorspelling.maak_prognose(db, dagen=7, nu=NU)
    voorspelling.maak_prognose(db, dagen=7, nu=NU + timedelta(minutes=50))
    assert bewaren["aantal"]["prognose"] == 1  # eerder was dit na 10 minuten alweer een koude start
    voorspelling.maak_prognose(db, dagen=7, nu=NU + timedelta(hours=1, minutes=1))
    assert bewaren["aantal"]["prognose"] == 2


def test_een_nieuwe_kantinedag_rekent_de_prognose_opnieuw_ook_bij_een_grotere_bewaartijd(db, bewaren, monkeypatch):
    """De kantinedag wisselt om 12.00 uur: 'vandaag' schuift op, dus een prognose van daarvoor klopt niet meer. Het
    model en de verdeling (wat al geteld is) blijven wel staan."""
    monkeypatch.setattr(voorspelling, "CACHE_BUCKET_SECONDEN", 24 * 3600)
    dinsdag = datetime(2026, 10, 6, 11, 59)
    for nu in (dinsdag, dinsdag + timedelta(minutes=1)):  # 12.00 uur: een nieuwe kantinedag
        voorspelling.maak_prognose(db, dagen=7, nu=nu)
        voorspelling.verdeling(db, nu)
    assert bewaren["aantal"]["prognose"] == 2
    voorspelling.maak_prognose(db, dagen=7, nu=dinsdag + timedelta(hours=3))  # nog dezelfde kantinedag
    assert bewaren["aantal"]["prognose"] == 2
    assert bewaren["aantal"]["model"] == 1 and bewaren["aantal"]["verdeling"] == 1


def test_twee_verzoeken_tegelijk_rekenen_maar_een_keer(app, monkeypatch):
    import sqlite3
    import threading
    import time

    aantal = {"n": 0}

    def traag():
        aantal["n"] += 1
        time.sleep(0.3)
        return {"antwoord": 42}

    uitkomsten = []

    def vraag():
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        try:
            uitkomsten.append(voorspelling._bewaard(conn, "test-tegelijk", NU, (), traag, lambda d: "vast"))
        finally:
            conn.close()

    monkeypatch.setattr(voorspelling, "CACHE_AAN", True)
    try:
        draden = [threading.Thread(target=vraag) for _ in range(3)]
        for d in draden:
            d.start()
        for d in draden:
            d.join()
    finally:
        voorspelling.wis_bewaarde_resultaten()
    assert aantal["n"] == 1 and uitkomsten == [{"antwoord": 42}] * 3
    assert voorspelling._BEZIG == {}  # niets blijft hangen


def test_een_mislukte_berekening_blokkeert_de_volgende_niet(db, bewaren):
    def stuk():
        raise RuntimeError("kapot")

    with pytest.raises(RuntimeError):
        voorspelling._bewaard(db, "test-stuk", NU, (), stuk, lambda d: "vast")
    assert voorspelling._BEZIG == {}
    assert voorspelling._bewaard(db, "test-stuk", NU, (), lambda: "gelukt", lambda d: "vast") == "gelukt"
