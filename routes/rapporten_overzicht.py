"""Alle rapporten (2.27.0): één pagina met alle rapporten per onderwerp, met in één zin wat je er ziet. Het menu houdt
alleen de rapporten die vaak gebruikt worden (navigatie.py, "verborgen"); de rest staat hier."""

from flask import current_app, render_template

from navigatie import RAPPORT_RUBRIEKEN, RAPPORT_UITLEG


def rubrieken(items):
    """[{"naam", "tekst", "rapporten": [{"endpoint", "label", "uitleg"}]}] voor de rapporten in 'items' (de menu-items
    die dit account mag zien), in de volgorde van RAPPORT_RUBRIEKEN; lege rubrieken vallen weg."""
    per_rubriek = {naam: [] for naam, _ in RAPPORT_RUBRIEKEN}
    for item in items:
        if item["groep"] != "Rapporten" or item["url_endpoint"] == "rapporten_overzicht":
            continue
        rubriek, uitleg = RAPPORT_UITLEG.get(item["url_endpoint"], ("Overig", ""))
        per_rubriek.setdefault(rubriek, []).append({"endpoint": item["url_endpoint"], "label": item["label"], "uitleg": uitleg})
    teksten = dict(RAPPORT_RUBRIEKEN)
    return [{"naam": naam, "tekst": teksten.get(naam, ""), "rapporten": lijst} for naam, lijst in per_rubriek.items() if lijst]


def register_routes(app):
    @app.route("/rapporten")
    def rapporten_overzicht():
        return render_template("rapporten.html", rubrieken=rubrieken(current_app.extensions["zichtbare_nav_items"]()))
