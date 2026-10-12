"""Rapporten: het marge-overzicht en de derving (wat er zonder te verkopen uit de voorraad verdwijnt)."""

from flask import render_template, request

from database import get_db
from derving import DERVING_REDENEN, bereken_derving
from helpers.tijd import vandaag_amsterdam
from marge import LAGE_MARGE_PCT, WEKEN_KEUZES, bereken_marge, kies_weken


def register_routes(app):
    @app.route("/rapporten/marge")
    def marge_rapport():
        weken = kies_weken(request.args.get("weken"))
        return render_template(
            "marge_rapport.html",
            weken=weken,
            weken_keuzes=WEKEN_KEUZES,
            lage_marge=LAGE_MARGE_PCT,
            rapport=bereken_marge(get_db(), weken, vandaag_amsterdam()),
        )

    @app.route("/rapporten/derving")
    def derving_rapport():
        weken = kies_weken(request.args.get("weken"))
        return render_template(
            "derving_rapport.html",
            weken=weken,
            weken_keuzes=WEKEN_KEUZES,
            redenen=DERVING_REDENEN,
            rapport=bereken_derving(get_db(), weken, vandaag_amsterdam()),
        )
