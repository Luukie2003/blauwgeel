"""Bardienstplanning op het prijzenscherm."""

from datetime import date

from flask import flash, jsonify, redirect, render_template, request, url_for

from database import get_db
from helpers import KIOSK_TIJD_PATROON, is_ajax_verzoek, now_str, vandaag_amsterdam


# ---------- Bardienst (onderdeel van het prijzenscherm) ----------

def _bardienst_uit_formulier():
    datum = request.form.get("datum", "").strip()
    try:
        date.fromisoformat(datum)
    except ValueError:
        # vandaag_amsterdam() i.p.v. date.today() (serverdatum, UTC op
        # deze hosting) -- anders komt een lege/ongeldige datum rond
        # middernacht een dag te vroeg te staan, precies de bug die de
        # bardienst-datumfix van 16 september 2026 al voor het scherm
        # oploste.
        datum = vandaag_amsterdam().isoformat()
    start_tijd = request.form.get("start_tijd", "").strip()
    if not KIOSK_TIJD_PATROON.match(start_tijd):
        start_tijd = "00:00"
    eind_tijd = request.form.get("eind_tijd", "").strip()
    if not KIOSK_TIJD_PATROON.match(eind_tijd):
        eind_tijd = "23:59"
    return {
        "datum": datum,
        "start_tijd": start_tijd,
        "eind_tijd": eind_tijd,
        "namen": request.form.get("namen", "").strip(),
    }


def register_routes(app):
    @app.route("/kiosk/prijzen/bardienst")
    def kiosk_bardienst():
        db = get_db()
        bardiensten = db.execute(
            "SELECT * FROM kiosk_bardiensten ORDER BY datum, start_tijd"
        ).fetchall()
        return render_template(
            "kiosk_bardienst.html", bardiensten=bardiensten, vandaag=vandaag_amsterdam().isoformat()
        )

    @app.route("/api/tablet/bardiensten")
    def api_tablet_bardiensten():
        """JSON-lijst voor de kiosk-tablet-app (los project, zie
        android-apps/tablet) -- schrijven gaat via dezelfde routes hieronder
        (nieuw/bewerken/verwijderen), die bij is_ajax_verzoek() JSON i.p.v.
        een redirect teruggeven."""
        db = get_db()
        bardiensten = db.execute(
            "SELECT * FROM kiosk_bardiensten ORDER BY datum, start_tijd"
        ).fetchall()
        return jsonify(
            {
                "bardiensten": [
                    {
                        "id": b["id"],
                        "datum": b["datum"],
                        "start_tijd": b["start_tijd"],
                        "eind_tijd": b["eind_tijd"],
                        "namen": b["namen"],
                    }
                    for b in bardiensten
                ]
            }
        )

    @app.route("/kiosk/prijzen/bardienst/nieuw", methods=["POST"])
    def kiosk_bardienst_nieuw():
        gegevens = _bardienst_uit_formulier()
        if not gegevens["namen"]:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Vul in wie er bardienst heeft."})
            flash("Vul in wie er bardienst heeft.", "error")
            return redirect(url_for("kiosk_bardienst"))
        db = get_db()
        db.execute(
            """INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op)
               VALUES (?, ?, ?, ?, ?)""",
            (gegevens["datum"], gegevens["start_tijd"], gegevens["eind_tijd"], gegevens["namen"], now_str()),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Bardienst toegevoegd.", "success")
        return redirect(url_for("kiosk_bardienst"))

    @app.route("/kiosk/prijzen/bardienst/<int:bardienst_id>/bewerken", methods=["GET", "POST"])
    def kiosk_bardienst_bewerken(bardienst_id):
        db = get_db()
        bardienst = db.execute(
            "SELECT * FROM kiosk_bardiensten WHERE id = ?", (bardienst_id,)
        ).fetchone()
        if bardienst is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Bardienst niet gevonden."}), 404
            flash("Bardienst niet gevonden.", "error")
            return redirect(url_for("kiosk_bardienst"))

        if request.method == "POST":
            gegevens = _bardienst_uit_formulier()
            if not gegevens["namen"]:
                if is_ajax_verzoek():
                    return jsonify({"ok": False, "fout": "Vul in wie er bardienst heeft."})
                flash("Vul in wie er bardienst heeft.", "error")
                return redirect(url_for("kiosk_bardienst_bewerken", bardienst_id=bardienst_id))
            db.execute(
                """UPDATE kiosk_bardiensten
                   SET datum = ?, start_tijd = ?, eind_tijd = ?, namen = ?
                   WHERE id = ?""",
                (
                    gegevens["datum"],
                    gegevens["start_tijd"],
                    gegevens["eind_tijd"],
                    gegevens["namen"],
                    bardienst_id,
                ),
            )
            db.commit()
            if is_ajax_verzoek():
                return jsonify({"ok": True})
            flash("Bardienst bijgewerkt.", "success")
            return redirect(url_for("kiosk_bardienst"))
        return render_template("kiosk_bardienst_form.html", bardienst=bardienst)

    @app.route("/kiosk/prijzen/bardienst/<int:bardienst_id>/verwijderen", methods=["POST"])
    def kiosk_bardienst_verwijderen(bardienst_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_bardiensten WHERE id = ?", (bardienst_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Bardienst verwijderd.", "success")
        return redirect(url_for("kiosk_bardienst"))
