"""Rapporten > Merkanalyse: alles over één merk, bijvoorbeeld voor een gesprek met de vertegenwoordiger (merkanalyse.py). Alleen
voor beheerders: de inkoopprijzen staan erin. De pdf kan ook zonder inkoop en marge, om te laten zien of mee te geven."""

from flask import Response, flash, redirect, render_template, request, url_for

import inkoop_verkoop
import merkanalyse
from database import get_db
from helpers.tijd import vandaag_amsterdam
from pdf import merkanalyse_pdf


def _keuze():
    """(merk, weken, seizoensweken) uit het adres."""
    seizoen = request.args.get("seizoen", merkanalyse.SEIZOEN_WEKEN, type=int)
    return (" ".join((request.args.get("merk") or "").split()), inkoop_verkoop.kies_weken(request.args.get("weken")),
            max(1, min(52, seizoen)))


def register_routes(app):
    @app.route("/rapporten/merk")
    def merk_rapport():
        db = get_db()
        merk, weken, seizoen = _keuze()
        keuzes = merkanalyse.merken(db)
        a = merkanalyse.analyse(db, merk, weken, vandaag_amsterdam(), seizoen) if merk else None
        if merk and a is None:
            flash(f"Er zijn geen producten van het merk '{merk}'.", "warning")
        return render_template(
            "merk_rapport.html", a=a, merken=keuzes, merk=a["merk"] if a else "", weken=weken,
            weken_keuzes=inkoop_verkoop.WEKEN_KEUZES, seizoen=seizoen, vragen=merkanalyse.VRAGEN,
        )

    @app.route("/rapporten/merk/pdf")
    def merk_rapport_pdf():
        merk, weken, seizoen = _keuze()
        a = merkanalyse.analyse(get_db(), merk, weken, vandaag_amsterdam(), seizoen) if merk else None
        if a is None:
            return redirect(url_for("merk_rapport"))
        deelbaar = request.args.get("deelbaar") == "1"
        naam = "".join(c for c in a["merk"].lower().replace(" ", "-") if c.isascii() and (c.isalnum() or c == "-")) or "merk"
        return Response(
            merkanalyse_pdf(a, deelbaar, merkanalyse.VRAGEN),
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=merkanalyse-{naam}{'-deelbaar' if deelbaar else '-intern'}.pdf"},
        )
