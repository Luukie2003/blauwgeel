from flask import flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import bereken_frituurvet_status, now_str


def register_routes(app):
    @app.route("/frituurvet/vervangen", methods=["POST"])
    def frituurvet_vervangen():
        db = get_db()
        db.execute(
            "INSERT INTO frituurvet_vervangingen (datum, naam, gebruiker_id) VALUES (?, ?, ?)",
            (now_str(), session.get("gebruiker_naam"), session.get("gebruiker_id")),
        )
        db.commit()
        flash("Frituurvet-vervanging geregistreerd.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/keuken")
    def keuken_voorraad():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten WHERE categorie = 'Keuken' ORDER BY actief DESC, subcategorie, naam"
        ).fetchall()
        return render_template("keuken_voorraad.html", producten=producten)

    @app.route("/keuken/instellingen", methods=["GET", "POST"])
    def keuken_instellingen():
        db = get_db()
        if request.method == "POST":
            try:
                interval = max(1, int(request.form.get("frituurvet_interval_dagen", "14")))
            except ValueError:
                interval = 14
            db.execute(
                "UPDATE instellingen SET frituurvet_interval_dagen = ? WHERE id = 1",
                (interval,),
            )
            db.commit()
            flash("Keuken-instellingen opgeslagen.", "success")
            return redirect(url_for("keuken_instellingen"))

        interval = db.execute(
            "SELECT frituurvet_interval_dagen FROM instellingen WHERE id = 1"
        ).fetchone()["frituurvet_interval_dagen"]
        vervangingen = db.execute(
            "SELECT * FROM frituurvet_vervangingen ORDER BY datum DESC, id DESC LIMIT 20"
        ).fetchall()
        return render_template(
            "keuken_instellingen.html",
            frituurvet_interval_dagen=interval,
            frituurvet_status=bereken_frituurvet_status(db),
            vervangingen=vervangingen,
        )
