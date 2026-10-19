"""Voorraad tellen in 1 formulier."""

from flask import flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import now_datetime_local, now_str
from productkaart import TELLEN_VOORWAARDE
from routes.tellen.looplijst_opslag import loop_bijwerken, loop_onderbroken
from routes.tellen.verwerken import verwerk_telling


def register_routes(app):
    @app.route("/tellen", methods=["GET", "POST"])
    def tellen():
        db = get_db()
        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            opmerking = request.form.get("opmerking", "").strip()
            datum_input = request.form.get("datum", "").strip()
            datum = datum_input.replace("T", " ") if datum_input else now_str()

            producten = db.execute(
                f"SELECT * FROM producten WHERE {TELLEN_VOORWAARDE} ORDER BY categorie, naam"
            ).fetchall()

            waarden = {}
            for p in producten:
                waarde = request.form.get(f"geteld_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    geteld = int(waarde)
                except ValueError:
                    continue
                if geteld < 0:
                    continue
                waarden[p["id"]] = geteld

            telling_id = verwerk_telling(db, waarden, naam, opmerking, datum, gebruiker_id)
            if telling_id is None:
                flash("Geen aantallen ingevuld: er is niets geteld.", "error")
                return redirect(url_for("tellen"))

            flash(
                f"Telling #{telling_id} verwerkt: {len(waarden)} product(en) geteld.",
                "success",
            )
            return redirect(url_for("telling_detail", telling_id=telling_id))

        producten = db.execute(
            f"SELECT * FROM producten WHERE {TELLEN_VOORWAARDE} ORDER BY categorie, naam"
        ).fetchall()
        loop_bijwerken(db)  # wat er in de app of op een ander toestel is afgebroken, staat hier ook niet meer
        return render_template(
            "tellen.html",
            producten=producten,
            nu_datetime_local=now_datetime_local(),
            loop_onderbroken=loop_onderbroken(db, len(producten)),
        )
