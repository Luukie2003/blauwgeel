"""Beheer > Noodstop: de hele site en de tv-schermen afsluiten en weer openen (zie noodstop.py). Alleen voor de
eigenaar; de bewaking zelf (wat er dicht is tijdens een noodstop) staat in app.py (noodstop_bewaken)."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import noodstop
from database import get_db


def _alleen_eigenaar():
    """Een redirect als dit niet de eigenaar is, anders None."""
    if not noodstop.is_eigenaar(get_db(), session.get("gebruiker_id")):
        flash("De noodstop is alleen voor de eigenaar van de site.", "error")
        return redirect(url_for("dashboard"))
    return None


def _wachtwoord_klopt(db, wachtwoord):
    rij = db.execute("SELECT wachtwoord_hash FROM gebruikers WHERE id = ?", (session.get("gebruiker_id"),)).fetchone()
    return bool(rij and wachtwoord and check_password_hash(rij["wachtwoord_hash"], wachtwoord))


def register_routes(app):
    @app.route("/beheer/noodstop")
    def noodstop_pagina():
        if (weg := _alleen_eigenaar()) is not None:
            return weg
        db = get_db()
        gebeurtenissen = db.execute(
            """SELECT datum, gebruiker_naam, actie, omschrijving FROM logboek
               WHERE endpoint LIKE 'noodstop%' ORDER BY id DESC LIMIT 10"""
        ).fetchall()
        return render_template("noodstop.html", toestand=noodstop.toestand(db), wachten=noodstop.wachten(db),
                               gebeurtenissen=gebeurtenissen, min_code=noodstop.MIN_CODE_LENGTE)

    @app.route("/beheer/noodstop/dicht", methods=["POST"])
    def noodstop_dicht():
        """Alles afsluiten. Vraagt het wachtwoord, zodat een openstaande sessie op een ander toestel dit niet zomaar
        kan."""
        if (weg := _alleen_eigenaar()) is not None:
            return weg
        db = get_db()
        if not _wachtwoord_klopt(db, request.form.get("wachtwoord")):
            flash("Wachtwoord klopt niet; er is niets afgesloten.", "error")
            return redirect(url_for("noodstop_pagina"))
        noodstop.vergrendel(db, session.get("gebruiker_naam"), request.form.get("reden"))
        # Iedereen is uitgelogd (sessie_versie omhoog); deze sessie van de eigenaar blijft geldig.
        session["sessie_versie"] = db.execute(
            "SELECT sessie_versie FROM gebruikers WHERE id = ?", (session["gebruiker_id"],)
        ).fetchone()[0]
        flash("Noodstop: de site en de schermen zijn afgesloten en iedereen is uitgelogd. Alleen jij kunt nog "
              "inloggen.", "success")
        return redirect(url_for("noodstop_pagina"))

    @app.route("/beheer/noodstop/open", methods=["POST"])
    def noodstop_open():
        """Weer openen: wachtwoord én noodcode. Na te veel foute pogingen eerst even wachten."""
        if (weg := _alleen_eigenaar()) is not None:
            return weg
        db = get_db()
        if (minuten := noodstop.wachten(db)):
            flash(f"Te veel foute pogingen. Probeer het over {minuten} minuut/minuten opnieuw.", "error")
            return redirect(url_for("noodstop_pagina"))
        toestand = noodstop.toestand(db)
        goed = _wachtwoord_klopt(db, request.form.get("wachtwoord")) and (
            not toestand["code_ingesteld"] or noodstop.code_klopt(db, request.form.get("code"))
        )
        if not goed:
            noodstop.foute_poging(db)
            flash("Wachtwoord of noodcode klopt niet; de site blijft afgesloten.", "error")
            return redirect(url_for("noodstop_pagina"))
        noodstop.ontgrendel(db)
        flash("De site en de schermen zijn weer open. Iedereen moet opnieuw inloggen.", "success")
        return redirect(url_for("noodstop_pagina"))

    @app.route("/beheer/noodstop/code", methods=["POST"])
    def noodstop_code():
        """De noodcode instellen of veranderen: wachtwoord, en de oude code als er al een is."""
        if (weg := _alleen_eigenaar()) is not None:
            return weg
        db = get_db()
        toestand = noodstop.toestand(db)
        if not _wachtwoord_klopt(db, request.form.get("wachtwoord")) or (
            toestand["code_ingesteld"] and not noodstop.code_klopt(db, request.form.get("oude_code"))
        ):
            flash("Wachtwoord of huidige noodcode klopt niet; de noodcode is niet veranderd.", "error")
            return redirect(url_for("noodstop_pagina"))
        if request.form.get("code") != request.form.get("code_herhalen"):
            flash("De twee nieuwe noodcodes zijn niet hetzelfde.", "error")
            return redirect(url_for("noodstop_pagina"))
        fout = noodstop.zet_code(db, request.form.get("code"))
        flash(fout or "Noodcode opgeslagen. Bewaar 'm ergens veilig, los van je wachtwoord.", "error" if fout else "success")
        return redirect(url_for("noodstop_pagina"))

    @app.route("/noodstop/status")
    def noodstop_status():
        """Voor het vergrendel-scherm op de tv: is de noodstop nog actief? (Meer zegt het niet.)"""
        antwoord = jsonify({"actief": noodstop.is_actief(get_db())})
        antwoord.headers["Cache-Control"] = "no-store"
        return antwoord
