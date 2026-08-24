from datetime import date, datetime, timedelta

from app import bereken_komende_thuiswedstrijden, bereken_voorspelde_tekorten
from weer import weer_label


def test_weer_label_bekende_en_onbekende_code():
    assert weer_label(0) == "helder"
    assert weer_label(61) == "lichte regen"
    assert weer_label(12345) == "onbekend"


def test_geen_tellingen_geeft_lege_voorspelling(db):
    assert bereken_voorspelde_tekorten(db) == []


def _maak_historische_telling(db, product_id, verkocht, dagen_geleden):
    datum = (datetime.now() - timedelta(days=dagen_geleden)).strftime("%Y-%m-%d %H:%M")
    cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (datum,))
    telling_id = cur.lastrowid
    product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()
    db.execute(
        """INSERT INTO telling_regels
           (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (telling_id, product_id, verkocht + 5, 5, verkocht, product["verkoopprijs"]),
    )
    db.commit()


def test_signaleert_product_boven_minimum_met_hoge_historische_verkoop(db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute(
        "UPDATE producten SET voorraad = 10, min_voorraad = 0 WHERE id = ?", (product["id"],)
    )
    db.commit()
    # 100 verkocht in de afgelopen week -- ruim meer dan de 10 die nu nog op voorraad staan.
    _maak_historische_telling(db, product["id"], verkocht=100, dagen_geleden=7)

    resultaat = bereken_voorspelde_tekorten(db, dagen_vooruit=7)
    namen = {r["product"]["naam"] for r in resultaat}
    assert product["naam"] in namen


def test_sluit_producten_die_al_onder_minimum_zitten_uit(db):
    """bestel_suggesties() vangt dit al -- voorspelde_tekorten moet geen
    dubbele melding geven voor iets dat al reactief gesignaleerd wordt."""
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute(
        "UPDATE producten SET voorraad = 0, min_voorraad = 10 WHERE id = ?", (product["id"],)
    )
    db.commit()
    _maak_historische_telling(db, product["id"], verkocht=100, dagen_geleden=7)

    resultaat = bereken_voorspelde_tekorten(db, dagen_vooruit=7)
    namen = {r["product"]["naam"] for r in resultaat}
    assert product["naam"] not in namen


def test_thuiswedstrijden_verhogen_het_verwachte_verbruik(db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute(
        "UPDATE producten SET voorraad = 50, min_voorraad = 0 WHERE id = ?", (product["id"],)
    )
    db.commit()
    _maak_historische_telling(db, product["id"], verkocht=100, dagen_geleden=7)

    zonder = bereken_voorspelde_tekorten(db, dagen_vooruit=7)
    verbruik_zonder = next(
        r["verwacht_verbruik"] for r in zonder if r["product"]["naam"] == product["naam"]
    )

    morgen = (date.today() + timedelta(days=1)).isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, '1e - Test', 1)",
        (morgen,),
    )
    db.commit()

    met = bereken_voorspelde_tekorten(db, dagen_vooruit=7)
    verbruik_met = next(
        r["verwacht_verbruik"] for r in met if r["product"]["naam"] == product["naam"]
    )
    assert verbruik_met > verbruik_zonder


def test_komende_thuiswedstrijden_koppelt_weer_op_datum(db):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, '1e - Test', 1)",
        (morgen,),
    )
    db.execute(
        "INSERT INTO weer_voorspelling (datum, max_temp, neerslag_kans, weercode) VALUES (?, 20.0, 10, 0)",
        (morgen,),
    )
    db.commit()

    resultaat = bereken_komende_thuiswedstrijden(db)
    dag = next(d for d in resultaat if d["datum"] == morgen)
    assert dag["weer"]["label"] == "helder"
    assert dag["weer"]["max_temp"] == 20.0


def test_komende_thuiswedstrijden_zonder_weer_data(db):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, '1e - Test', 1)",
        (morgen,),
    )
    db.commit()

    resultaat = bereken_komende_thuiswedstrijden(db)
    dag = next(d for d in resultaat if d["datum"] == morgen)
    assert dag["weer"] is None
