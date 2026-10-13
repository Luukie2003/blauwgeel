"""Bestellen > Leveranciers: wie levert wat, wanneer bestel je en hoe (zie leveranciers.py)."""

from flask import flash, redirect, render_template, request, url_for

from database import get_db
from leveranciers import (
    DAGEN,
    alle_leveranciers,
    besteldagen,
    besteldagen_tekst,
    bewaar_leverancier,
    koppel_producten,
    verwijder_leverancier,
)


def _producten(db):
    return db.execute(
        """SELECT p.id, p.naam, p.categorie, p.artikelcode, p.leverancier_id, l.naam AS leverancier_naam
           FROM producten p LEFT JOIN leveranciers l ON l.id = p.leverancier_id
           WHERE p.actief = 1 ORDER BY p.categorie, p.naam COLLATE NOCASE"""
    ).fetchall()


def register_routes(app):
    @app.route("/leveranciers")
    def leveranciers_lijst():
        db = get_db()
        leveranciers = [dict(lev, dagen=besteldagen_tekst(lev)) for lev in alle_leveranciers(db)]
        zonder = db.execute("SELECT COUNT(*) FROM producten WHERE actief = 1 AND leverancier_id IS NULL").fetchone()[0]
        return render_template("leveranciers.html", leveranciers=leveranciers, zonder_leverancier=zonder)

    @app.route("/leveranciers/nieuw", methods=["GET", "POST"])
    def leverancier_nieuw():
        db = get_db()
        if request.method == "POST":
            leverancier_id, fout = bewaar_leverancier(db, request.form)
            if fout:
                flash(fout, "error")
            else:
                koppel_producten(db, leverancier_id, request.form.getlist("product_id"))
                flash("Leverancier toegevoegd.", "success")
                return redirect(url_for("leveranciers_lijst"))
        return render_template(
            "leverancier_form.html", leverancier=None, dagen=DAGEN, gekozen_dagen=[], producten=_producten(db),
            ingevuld=request.form,
        )

    @app.route("/leveranciers/<int:leverancier_id>", methods=["GET", "POST"])
    def leverancier_bewerken(leverancier_id):
        db = get_db()
        leverancier = db.execute("SELECT * FROM leveranciers WHERE id = ?", (leverancier_id,)).fetchone()
        if leverancier is None:
            flash("Leverancier niet gevonden.", "error")
            return redirect(url_for("leveranciers_lijst"))
        if request.method == "POST":
            _, fout = bewaar_leverancier(db, request.form, leverancier_id)
            if fout:
                flash(fout, "error")
            else:
                koppel_producten(db, leverancier_id, request.form.getlist("product_id"))
                flash("Leverancier opgeslagen.", "success")
                return redirect(url_for("leveranciers_lijst"))
        return render_template(
            "leverancier_form.html", leverancier=leverancier, dagen=DAGEN, gekozen_dagen=besteldagen(leverancier),
            producten=_producten(db), ingevuld=request.form,
        )

    @app.route("/leveranciers/<int:leverancier_id>/verwijderen", methods=["POST"])
    def leverancier_verwijderen(leverancier_id):
        verwijder_leverancier(get_db(), leverancier_id)
        flash("Leverancier verwijderd. De producten zijn er niet door veranderd, alleen losgekoppeld.", "success")
        return redirect(url_for("leveranciers_lijst"))
