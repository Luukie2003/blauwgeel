"""Producten > Gegevenscontrole (beheerders): wat er aan de productgegevens niet klopt, zie gegevenscontrole.py."""

from flask import render_template

from database import get_db
from gegevenscontrole import controleer


def register_routes(app):
    @app.route("/producten/gegevenscontrole")
    def gegevenscontrole():
        return render_template("gegevenscontrole.html", uitkomst=controleer(get_db()))
