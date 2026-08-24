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


def test_kassa_status_zonder_wedstrijd_en_nog_nooit_geteld_is_rood(db):
    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "rood"


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


def _open_kassatelling(db, dagen_geleden=0):
    datum = (datetime.now() - timedelta(days=dagen_geleden)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO kassa_tellingen (datum, naam, afgesloten) VALUES (?, 'Luuk', 0)", (datum,)
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


def test_kassa_status_groen_bij_algemene_zeven_dagen_regel_zonder_wedstrijd(db):
    _sluit_kassatelling_af(db, dagen_geleden=3)  # geen wedstrijd, maar wel recent geteld

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "groen"


def test_kassa_status_rood_boven_zeven_dagen_zonder_wedstrijd(db):
    _sluit_kassatelling_af(db, dagen_geleden=10)  # geen wedstrijd, te lang geleden geteld

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "rood"


def test_kassa_status_wedstrijdregel_gaat_voor_algemene_regel(db):
    """Ook al is er ooit binnen 7 dagen geteld, een wedstrijd van >3 dagen
    geleden zonder telling sindsdien moet toch rood geven."""
    _sluit_kassatelling_af(db, dagen_geleden=6)
    _voeg_thuiswedstrijd_toe(db, dagen_geleden=4)  # na de laatste telling, deadline verstreken

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "rood"


def test_kassa_status_oranje_bij_openstaand_concept(db):
    _open_kassatelling(db)

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "oranje"


def test_kassa_status_concept_gaat_voor_alle_andere_regels(db):
    """Zelfs met een gemiste wedstrijd-deadline moet een openstaand concept
    (de allerlaatste telling) oranje laten zien -- iemand is er al mee
    bezig."""
    _voeg_thuiswedstrijd_toe(db, dagen_geleden=5)
    _open_kassatelling(db, dagen_geleden=0)

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "oranje"


def test_kassa_status_negeert_afgesloten_telling_als_er_daarna_een_concept_is(db):
    _sluit_kassatelling_af(db, dagen_geleden=1)
    _open_kassatelling(db, dagen_geleden=0)  # nieuwere, nog open telling

    resultaat = bereken_kassa_telling_status(db)
    assert resultaat["status"] == "oranje"
