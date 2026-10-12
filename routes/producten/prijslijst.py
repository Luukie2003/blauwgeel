"""De prijslijst om te bekijken (voor iedereen met de voorraadsectie) en als pdf voor aan de bar."""

from flask import Response, render_template, request, session

from database import get_db
from eigen_taken import taken_voor_gebruiker
from helpers.tijd import vandaag_amsterdam
from pdf import prijslijst_pdf
from prijzen import geplande_wijzigingen
from routes.kiosk.prijzen_gegevens import _prijzen_categorieen


def register_routes(app):
    @app.route("/prijslijst")
    def prijslijst_pagina():
        """Alle verkoopprijzen om na te lopen, zonder iets te kunnen wijzigen. Heb je een taak 'Prijzenlijst nalopen
        (alleen kijken)', dan rond je die hier af."""
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam COLLATE NOCASE"
        ).fetchall()
        opties = {}
        for optie in db.execute("SELECT * FROM product_prijsopties ORDER BY product_id, volgorde, id").fetchall():
            opties.setdefault(optie["product_id"], []).append(optie)
        per_categorie = {}
        for p in producten:
            if p["verkoopprijs"] > 0 or opties.get(p["id"]) or p["glazen_per_fust"]:
                per_categorie.setdefault(p["categorie"], []).append(p)
        mijn_taken = [
            t for t in taken_voor_gebruiker(db, session["gebruiker_id"])
            if t["doel"] and t["doel"]["endpoint"] == "prijslijst_pagina"
        ]
        return render_template(
            "prijslijst.html",
            per_categorie=sorted(per_categorie.items()),
            opties=opties,
            gepland=geplande_wijzigingen(db),
            mijn_taken=mijn_taken,
            vandaag=vandaag_amsterdam(),
        )

    @app.route("/prijslijst/pdf")
    def prijslijst_pdf_route():
        """De prijslijst zoals hij op de prijzen-tv staat, op A4 om op te hangen. ?download=1: als download."""
        inhoud = prijslijst_pdf(_prijzen_categorieen(get_db()), vandaag_amsterdam())
        kopteksten = {}
        if request.args.get("download"):
            kopteksten["Content-Disposition"] = "attachment; filename=prijslijst.pdf"
        return Response(inhoud, mimetype="application/pdf", headers=kopteksten)
