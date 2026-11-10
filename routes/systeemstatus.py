"""Beheer > Systeemstatus: wanneer elke geplande taak (back-up, teamagenda's, weerbericht, weekoverzicht,
bereikbaarheid) voor het laatst heeft gedraaid en gelukt is (zie taakstatus.py), met de andere technische meldingen
ernaast. Alleen voor de systeembeheerder, het account dat eigenaar is (zie noodstop.py)."""

from flask import flash, redirect, render_template, session, url_for

import backup as backup_module
import mail
import noodstop
import taakstatus
from database import get_db
from foutenlog import recente_open_fouten
from opslag import laatst_gemeten


def register_routes(app):
    @app.route("/beheer/systeemstatus")
    def systeemstatus():
        db = get_db()
        if not noodstop.is_eigenaar(db, session.get("gebruiker_id")):
            flash("De systeemstatus is alleen voor de systeembeheerder.", "error")
            return redirect(url_for("dashboard"))
        return render_template(
            "systeemstatus.html",
            taken=taakstatus.overzicht(db),
            ontvanger=mail.systeembeheerder_adres(db),
            backup_status=backup_module.bereken_backup_status(),
            open_fouten=recente_open_fouten(db),
            opslag=laatst_gemeten(db),  # de bewaarde meting, zonder de schijf af te lopen
        )
