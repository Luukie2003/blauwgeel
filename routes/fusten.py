from flask import render_template

from database import get_db
from helpers import bereken_fust_verkopen


def register_routes(app):
    @app.route("/fusten")
    def fusten_overzicht():
        db = get_db()
        fust_producten = db.execute(
            "SELECT * FROM producten WHERE glazen_per_fust > 0 ORDER BY categorie, naam"
        ).fetchall()
        fust_verkopen = bereken_fust_verkopen(db)
        return render_template(
            "fusten.html", fust_producten=fust_producten, fust_verkopen=fust_verkopen
        )
