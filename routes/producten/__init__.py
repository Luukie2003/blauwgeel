"""Producten, voorraadoverzicht, assortimentsbeheer, schaplabels en categorieen.

Vroeger 1 bestand van ruim 900 regels; nu per onderwerp opgesplitst. Alle routes
behouden hun eigen endpoint-namen."""

from routes.producten import assortiment, categorieen, overzicht, scannen, voorraadoverzicht
from routes.producten.overzicht import render_producten_pagina, render_voorraad_pda


def register_routes(app):
    voorraadoverzicht.register_routes(app)
    overzicht.register_routes(app)
    assortiment.register_routes(app)
    scannen.register_routes(app)
    categorieen.register_routes(app)


__all__ = ["register_routes", "render_producten_pagina", "render_voorraad_pda"]
