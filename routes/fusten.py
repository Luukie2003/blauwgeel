from flask import redirect, url_for


def register_routes(app):
    @app.route("/fusten")
    def fusten_overzicht():
        """Fusten hebben geen eigen pagina meer -- de gegevens staan nu in
        een sectie op Voorraadoverzicht (zie bereken_voorraadoverzicht in
        routes/producten.py). Deze route blijft bestaan als omleiding, voor
        oude bladwijzers/links."""
        return redirect(url_for("voorraadoverzicht"))
