from datetime import date, datetime, timedelta

from app import bereken_kassa_telling_status, bereken_laatste_telling_status


def test_laatste_telling_status_zonder_tellingen(db):
    resultaat = bereken_laatste_telling_status(db)
    assert resultaat["laatste"] is None
    assert resultaat["ok"] is False


def test_laatste_telling_status_binnen_zeven_dagen_is_groen(db):
    datum = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
    db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'Luuk')", (datum,))
    db.commit()

    resultaat = bereken_laatste_telling_status(db)
    assert resultaat["ok"] is True
    assert resultaat["dagen_geleden"] == 2


def test_laatste_telling_status_boven_zeven_dagen_is_rood(db):
    datum = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
    db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'Luuk')", (datum,))
    db.commit()

    resultaat = bereken_laatste_telling_status(db)
    assert resultaat["ok"] is False


def test_kassa_status_zonder_wedstrijden_is_neutraal(db):
    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "neutraal"


def _voeg_thuiswedstrijd_toe(db, dagen_geleden):
    datum = (date.today() - timedelta(days=dagen_geleden)).isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, '1e - Test', 1)",
        (datum,),
    )
    db.commit()


def _sluit_kassatelling_af(db, dagen_geleden):
    datum = (datetime.now() - timedelta(days=dagen_geleden)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO kassa_tellingen (datum, naam, afgesloten) VALUES (?, 'Luuk', 1)", (datum,)
    )
    db.commit()


def test_kassa_status_groen_als_geteld_sinds_wedstrijd(db):
    _voeg_thuiswedstrijd_toe(db, dagen_geleden=3)
    _sluit_kassatelling_af(db, dagen_geleden=1)  # na de wedstrijd

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "groen"


def test_kassa_status_rood_als_deadline_verstreken_zonder_telling(db):
    _voeg_thuiswedstrijd_toe(db, dagen_geleden=5)  # deadline was 3 dagen geleden

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "rood"


def test_kassa_status_neutraal_binnen_de_deadline(db):
    _voeg_thuiswedstrijd_toe(db, dagen_geleden=1)  # deadline pas over 1 dag

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "neutraal"


def test_kassa_status_negeert_telling_van_voor_de_wedstrijd(db):
    _sluit_kassatelling_af(db, dagen_geleden=10)  # oude telling, telt niet mee
    _voeg_thuiswedstrijd_toe(db, dagen_geleden=5)

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "rood"
