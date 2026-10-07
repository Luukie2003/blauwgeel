"""Kantine-tv (kiosk): prijzenscherm, dia's, sponsoren en de tv-weergave.

Vroeger 1 bestand van ruim 2000 regels; nu opgesplitst per onderdeel. Alle
routes behouden hun eigen endpoint-namen, dus url_for() en de rechten in
app.py werken ongewijzigd."""

from routes.kiosk import prijzen, bardienst, acties, sponsoren_sjablonen, scherm


def register_routes(app):
    prijzen.register_routes(app)
    bardienst.register_routes(app)
    acties.register_routes(app)
    sponsoren_sjablonen.register_routes(app)
    scherm.register_routes(app)
