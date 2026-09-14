"""Regressietest voor de ImportError die dit script bij elke maandagochtend-run
had (bereken_week_overzicht stond niet in app.py, maar in helpers.py)."""

from datetime import date

import week_overzicht_mail


def test_import_slaagt():
    """Los importeren mag geen ImportError geven -- dit is precies hoe de
    PythonAnywhere Scheduled Task het script binnenhaalt."""
    assert week_overzicht_mail.bereken_week_overzicht is not None


def test_bouw_mailtekst_met_minimaal_overzicht():
    overzicht = {
        "week_van": date(2026, 1, 5),
        "week_tot": date(2026, 1, 11),
        "totale_omzet": 123.45,
        "verschil_percentage": None,
        "top_verkopers": [],
        "onder_minimum": [],
        "open_bestellingen": [],
        "nieuwe_mededelingen": [],
        "zonder_prijs": [],
    }

    tekst = week_overzicht_mail.bouw_mailtekst(overzicht)

    assert "Weekoverzicht 05-01-2026 t/m 11-01-2026" in tekst
    assert "Omzet: € 123.45" in tekst
    assert "(geen verkoop deze week)" in tekst
