"""Kaartjes printen: kies een ontwerp, typ de hardlopers en maak de pdf om uit te knippen."""

from flask import Response, flash, redirect, render_template, request, url_for

from database import get_db
from kaartjes import MAX_VELLEN, bewaar_instellingen, lees_instellingen, topverkopers
from pdf import KAARTJES_OPTIES, MAX_HARDLOPERS, kaartjes_overzicht_pdf, kaartjes_pdf


def register_routes(app):
    @app.route("/kaartjes", methods=["GET", "POST"])
    def kaartjes_pagina():
        db = get_db()
        if request.method == "POST":
            try:
                vellen = int(request.form.get("vellen") or 1)
            except ValueError:
                vellen = 1
            weggelaten = bewaar_instellingen(
                db,
                request.form.get("optie", ""),
                request.form.get("hardlopers", ""),
                vellen,
                bool(request.form.get("zwartwit")),
            )
            flash("Opgeslagen: het voorbeeld hiernaast is bijgewerkt.", "success")
            if weggelaten:
                flash(
                    f"Er passen maximaal {MAX_HARDLOPERS} hardlopers op een kaartje: "
                    f"de laatste {weggelaten} zijn weggelaten.",
                    "warning",
                )
            return redirect(url_for("kaartjes_pagina"))
        return render_template(
            "kaartjes.html",
            opties=KAARTJES_OPTIES,
            instellingen=lees_instellingen(db),
            topverkopers=topverkopers(db),
            max_hardlopers=MAX_HARDLOPERS,
            max_vellen=MAX_VELLEN,
        )

    @app.route("/kaartjes/pdf")
    def kaartjes_pdf_route():
        """De pdf met de opgeslagen instellingen. ?voorbeeld=1: 1 vel (voor in de pagina); ?alle=1: 1 pagina per
        ontwerp; ?download=1: als download in plaats van in de browser te openen."""
        instellingen = lees_instellingen(get_db())
        if request.args.get("alle"):
            inhoud = kaartjes_overzicht_pdf(instellingen["hardlopers"], instellingen["zwartwit"])
            naam = "kaartjes-alle-ontwerpen.pdf"
        else:
            vellen = 1 if request.args.get("voorbeeld") else instellingen["vellen"]
            inhoud = kaartjes_pdf(instellingen["optie"], instellingen["hardlopers"], vellen, instellingen["zwartwit"])
            naam = f"kaartjes-{instellingen['optie']}.pdf"
        weergave = "attachment" if request.args.get("download") else "inline"
        return Response(
            inhoud,
            mimetype="application/pdf",
            # Niet bewaren: na het opslaan van een andere hardloper moet het voorbeeld meteen kloppen.
            headers={"Content-Disposition": f"{weergave}; filename={naam}", "Cache-Control": "no-store"},
        )
