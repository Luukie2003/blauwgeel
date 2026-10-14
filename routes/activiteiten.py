"""Start > Agenda: de komende weken in de kantine (zie activiteiten.py)."""

import json

from flask import render_template, request

from activiteiten import DAGEN_KEUZES, bouw_agenda, kies_dagen
from database import get_db
from helpers.tijd import vandaag_amsterdam
from voorspelling import maak_prognose


def register_routes(app):
    @app.route("/agenda")
    def agenda():
        dagen = kies_dagen(request.args.get("dagen"))
        return render_template(
            "agenda.html", weken=bouw_agenda(get_db(), vandaag_amsterdam(), dagen), dagen=dagen, dagen_keuzes=DAGEN_KEUZES
        )

    @app.route("/agenda/omzet")
    def agenda_omzet():
        """De verwachte omzet per dag voor de agenda, apart opgehaald (het voorspelmodel rekent soms enkele seconden).
        Geeft een verborgen element met {datum: omzet}; de pagina zet de bedragen bij de dagen."""
        dagen = kies_dagen(request.args.get("dagen"))
        omzet = {}
        try:
            prognose = maak_prognose(get_db(), dagen=min(dagen, 28))
            if prognose["beschikbaar"]:
                omzet = {d["datum"].isoformat(): round(d["omzet"]) for d in prognose["dagen_overzicht"] if d["open"]}
        except Exception as fout:  # de agenda mag hier nooit door stukgaan
            print(f"[agenda] prognose mislukt: {fout}")
        return f'<span hidden id="agenda-omzet" data-omzet="{json.dumps(omzet).replace(chr(34), "&quot;")}"></span>'
