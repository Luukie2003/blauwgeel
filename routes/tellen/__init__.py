"""Voorraad tellen, de looplijst en het overzicht van tellingen.

Vroeger 1 bestand van ruim 750 regels; nu per onderwerp opgesplitst. Alle routes
behouden hun eigen endpoint-namen."""

from routes.tellen import looplijst, tellen, tellingen


def register_routes(app):
    tellen.register_routes(app)
    looplijst.register_routes(app)
    tellingen.register_routes(app)
