"""De Prognose-pagina (Bestellen > Prognose): wat wordt er de komende dagen
verkocht, welke producten raken op en wat moet er besteld worden. De
rekenregels staan in voorspelling.py."""

from flask import render_template, request

from database import get_db
from voorspelling import maak_prognose

HORIZONNEN = (3, 7, 14)


def register_routes(app):
    @app.route("/prognose")
    def prognose_pagina():
        db = get_db()
        dagen = request.args.get("dagen", 7, type=int)
        if dagen not in HORIZONNEN:
            dagen = 7
        prognose = maak_prognose(db, dagen=dagen)
        categorie = request.args.get("categorie") or ""
        if prognose["beschikbaar"]:
            categorieen = sorted({p["product"]["categorie"] for p in prognose["producten"]})
            if categorie in categorieen:
                prognose = dict(
                    prognose,
                    producten=[p for p in prognose["producten"] if p["product"]["categorie"] == categorie],
                )
            else:
                categorie = ""
        else:
            categorieen = []
        return render_template(
            "prognose.html",
            prognose=prognose,
            dagen=dagen,
            horizonnen=HORIZONNEN,
            categorie=categorie,
            categorieen=categorieen,
        )
