from flask import jsonify, request

import uitrollen

# Wat er maximaal als body wordt geaccepteerd: het verzoek bevat niets dan een korte JSON.
MAX_BODY_BYTES = 2048


def register_routes(app):
    """Zie uitrollen.py. Beveiligd met een handtekening (geen sessie en geen CSRF-token,
    want dit wordt door een script aangeroepen); uitgeschakeld zonder geheim op de server."""

    @app.route("/uitrollen", methods=["POST"])
    def uitrollen_endpoint():
        geheim = uitrollen.lees_geheim()
        if geheim is None:
            return jsonify({"fout": "niet beschikbaar"}), 404
        if (request.content_length or 0) > MAX_BODY_BYTES:
            return jsonify({"fout": "ongeldige handtekening"}), 403
        body = request.get_data(cache=False)
        if not uitrollen.controleer_handtekening(
            geheim,
            request.headers.get("X-Uitrol-Tijd"),
            request.headers.get("X-Uitrol-Handtekening"),
            body,
        ):
            return jsonify({"fout": "ongeldige handtekening"}), 403

        resultaat = uitrollen.werk_code_bij(uitrollen.BASE_DIR)
        antwoord = jsonify(resultaat)
        antwoord.status_code = 200 if resultaat["ok"] else 500
        if resultaat["ok"] and resultaat["gewijzigd"]:
            # Pas herstarten nadat het antwoord is verstuurd, anders breekt dit verzoek zelf af.
            antwoord.call_on_close(uitrollen.herstart_web_app)
        return antwoord

    @app.route("/status")
    def status_pagina():
        """Welke versie draait er nu? Voor het uitroll-script, dat hiermee controleert dat de nieuwe
        code echt actief is."""
        from wijzigingen import HUIDIGE_VERSIE

        return jsonify({"versie": HUIDIGE_VERSIE, "commit": _OPGESTART_ALS})


# De code die bij het starten van dit proces op schijf stond: dat is wat er daadwerkelijk draait,
# ook als er daarna al weer nieuwere code is opgehaald maar de app nog niet is herstart.
_OPGESTART_ALS = uitrollen.huidige_commit()
