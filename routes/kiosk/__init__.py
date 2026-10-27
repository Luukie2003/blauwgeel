"""Kantine-tv (kiosk): prijzenscherm, dia's, sponsoren en de tv-weergave.

Vroeger 1 bestand van ruim 2000 regels; nu opgesplitst per onderdeel. Alle
routes behouden hun eigen endpoint-namen, dus url_for() en de rechten in
app.py werken ongewijzigd."""

from database import get_db
from routes.kiosk import prijzen, bardienst, acties, sponsoren_sjablonen, scherm, timer, tvs
from routes.kiosk.gedeeld import kiosk_thema


def register_routes(app):
    @app.context_processor
    def _kiosk_thema_voor_schermen():
        # Voor templates/_kiosk_thema.html: een functie, dus alleen een query als een scherm hem aanroept.
        return {"kiosk_thema": lambda: kiosk_thema(get_db())}

    prijzen.register_routes(app)
    bardienst.register_routes(app)
    acties.register_routes(app)
    sponsoren_sjablonen.register_routes(app)
    scherm.register_routes(app)
    tvs.register_routes(app)
    timer.register_routes(app)
