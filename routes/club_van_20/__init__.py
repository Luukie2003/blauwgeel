"""Club van 20-module: ledenadministratie met betalingen per seizoen, projecten, importeren/exporteren, scherminstellingen en de publieke pagina.

De rekenregels zelf staan in het pakket club_van_20 (in de hoofdmap)."""

from club_van_20 import euro, seizoen_kort

from routes.club_van_20 import importeren, leden, projecten, scherm


def register_routes(app):
    app.jinja_env.filters["euro"] = euro
    app.jinja_env.filters["seizoen_kort"] = seizoen_kort

    leden.register_routes(app)
    projecten.register_routes(app)
    importeren.register_routes(app)
    scherm.register_routes(app)
