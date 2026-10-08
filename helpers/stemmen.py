"""Hulpjes voor stemmingen."""

from helpers.tijd import now_str


def stemming_is_open(stemvraag):
    """Een stemming is open als hij niet handmatig gesloten is EN de
    (optionele) einddatum nog niet is verstreken. sluit_op wordt bewaard
    als einde van die dag ("YYYY-MM-DD 23:59"), dus een gewone
    stringvergelijking met now_str() volstaat."""
    if not stemvraag["actief"]:
        return False
    if stemvraag["sluit_op"] and stemvraag["sluit_op"] < now_str():
        return False
    return True


def tel_stemmers(db, stemvraag_id):
    """Aantal unieke stemmers (niet het aantal uitgebrachte keuzes) -- bij
    stemvragen met aantal_keuzes > 1 brengt 1 stemmer meerdere stemmen uit,
    dus is dit de juiste noemer voor percentages in de uitslag."""
    return db.execute(
        "SELECT COUNT(DISTINCT kiezer_sleutel) AS n FROM stemmen WHERE stemvraag_id = ? AND afgekeurd = 0",
        (stemvraag_id,),
    ).fetchone()["n"]
