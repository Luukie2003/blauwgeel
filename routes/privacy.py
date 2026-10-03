"""De openbare privacyverklaring (/privacy). De tekst staat in
templates/privacy.html; alleen het contactadres is instelbaar (Instellingen)
en de datum "laatst bijgewerkt" staat hieronder. Pas BIJGEWERKT_OP aan zodra
de tekst inhoudelijk verandert, bijvoorbeeld bij een nieuwe verwerking."""

import re

from flask import render_template

from database import get_db

BIJGEWERKT_OP = "3 oktober 2026"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def register_routes(app):
    @app.route("/privacy")
    def privacyverklaring():
        rij = get_db().execute("SELECT privacy_contact FROM instellingen WHERE id = 1").fetchone()
        contact = ((rij["privacy_contact"] if rij else "") or "").strip()
        return render_template(
            "privacy.html",
            bijgewerkt=BIJGEWERKT_OP,
            contact_email=contact if _EMAIL.match(contact) else None,
            contact=contact if contact and not _EMAIL.match(contact) else None,
        )
