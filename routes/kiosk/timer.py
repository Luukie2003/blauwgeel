"""Timer op de tv-schermen (zie kiosk_timers.py): de pagina Timer, voor iedereen die is ingelogd."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import kiosk_timers
from database import get_db
from helpers import is_ajax_verzoek


def _stand(db):
    return {"timers": kiosk_timers.actieve(db), "voorstellen": kiosk_timers.voorstellen(db)}


def register_routes(app):
    @app.route("/timer")
    def timer_pagina():
        db = get_db()
        return render_template("timer.html", max_minuten=kiosk_timers.MAX_MINUTEN, **_stand(db))

    @app.route("/timer/stand")
    def timer_stand():
        """De lopende timers, voor de pagina zelf (die ververst zo ook wat iemand anders startte of weghaalde)."""
        return jsonify(_stand(get_db()))

    def _klaar(melding, fout=False):
        if is_ajax_verzoek():
            return jsonify({"ok": not fout, "melding": melding, **_stand(get_db())}), (400 if fout else 200)
        flash(melding, "error" if fout else "success")
        return redirect(url_for("timer_pagina"))

    @app.route("/timer/starten", methods=["POST"])
    def timer_starten():
        db = get_db()
        naam, minuten = request.form.get("naam"), request.form.get("minuten")
        timer_id, fout = kiosk_timers.start(db, naam, minuten, session.get("gebruiker_naam"))
        if fout:
            return _klaar(fout, fout=True)
        timer = db.execute("SELECT naam, minuten, klaar_om FROM kiosk_timers WHERE id = ?", (timer_id,)).fetchone()
        return _klaar(f"{timer['naam']}: de timer van {timer['minuten']} minuten loopt (klaar om {timer['klaar_om'][11:16]}).")

    @app.route("/timer/<int:timer_id>/verlengen", methods=["POST"])
    def timer_verlengen(timer_id):
        minuten = kiosk_timers.schoon_minuten(request.form.get("minuten")) or 5
        naam = kiosk_timers.verleng(get_db(), timer_id, minuten)
        if naam is None:
            return _klaar("Deze timer staat er niet meer.", fout=True)
        return _klaar(f"{naam}: {minuten} minuten erbij.")

    @app.route("/timer/<int:timer_id>/stoppen", methods=["POST"])
    def timer_stoppen(timer_id):
        naam = kiosk_timers.stop(get_db(), timer_id)
        if naam is None:
            return _klaar("Deze timer stond er al niet meer.")
        return _klaar(f"{naam}: de timer is van de tv's gehaald.")
