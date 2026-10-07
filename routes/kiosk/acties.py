"""Prijs-acties op het prijzenscherm."""

from flask import flash, jsonify, redirect, render_template, request, url_for

from database import get_db
from helpers import is_ajax_verzoek, now_str


# ---------- Prijs-acties (onderdeel van het prijzenscherm) ----------

def _actie_producten(db):
    """Actieve producten om als actie te kunnen kiezen -- de actie
    gebruikt daarna gewoon de foto/prijs van dat product, dus hier hoeft
    geen los uploadveld voor te komen."""
    return db.execute(
        "SELECT id, naam, categorie FROM producten WHERE actief = 1 ORDER BY categorie, naam"
    ).fetchall()


def register_routes(app):
    @app.route("/kiosk/prijzen/acties")
    def kiosk_acties():
        db = get_db()
        acties = db.execute(
            """SELECT ka.*, p.naam AS product_naam, p.afbeelding AS product_afbeelding,
                      p.verkoopprijs AS product_verkoopprijs
               FROM kiosk_acties ka JOIN producten p ON p.id = ka.product_id
               ORDER BY ka.id"""
        ).fetchall()
        return render_template("kiosk_acties.html", acties=acties)

    @app.route("/api/tablet/acties")
    def api_tablet_acties():
        """JSON-lijst voor de kiosk-tablet-app (los project, zie
        android-apps/tablet) -- "producten" hierin zijn de actieve producten
        waaruit gekozen kan worden bij het aanmaken/bewerken van een actie
        (zie _actie_producten hierboven). Schrijven gaat via de routes
        hieronder (nieuw/bewerken/verwijderen/toon), die bij
        is_ajax_verzoek() JSON i.p.v. een redirect teruggeven."""
        db = get_db()
        acties = db.execute(
            """SELECT ka.*, p.naam AS product_naam
               FROM kiosk_acties ka JOIN producten p ON p.id = ka.product_id
               ORDER BY ka.id"""
        ).fetchall()
        return jsonify(
            {
                "acties": [
                    {
                        "id": a["id"],
                        "product_id": a["product_id"],
                        "product_naam": a["product_naam"],
                        "tekst": a["tekst"] or "",
                        "actief": bool(a["actief"]),
                    }
                    for a in acties
                ],
                "producten": [
                    {"id": p["id"], "naam": p["naam"], "categorie": p["categorie"]}
                    for p in _actie_producten(db)
                ],
            }
        )

    @app.route("/kiosk/prijzen/acties/nieuw", methods=["GET", "POST"])
    def kiosk_actie_nieuw():
        db = get_db()
        if request.method == "POST":
            try:
                product_id = int(request.form.get("product_id") or 0)
            except ValueError:
                product_id = 0
            product = db.execute(
                "SELECT id FROM producten WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None:
                if is_ajax_verzoek():
                    return jsonify({"ok": False, "fout": "Kies een geldig product."})
                flash("Kies een geldig product.", "error")
            else:
                db.execute(
                    """INSERT INTO kiosk_acties (product_id, tekst, actief, aangemaakt_op)
                       VALUES (?, ?, ?, ?)""",
                    (
                        product_id,
                        request.form.get("tekst", "").strip() or None,
                        1 if request.form.get("actief") else 0,
                        now_str(),
                    ),
                )
                db.commit()
                if is_ajax_verzoek():
                    return jsonify({"ok": True})
                flash("Actie toegevoegd.", "success")
                return redirect(url_for("kiosk_acties"))
        return render_template("kiosk_actie_form.html", actie=None, producten=_actie_producten(db))

    @app.route("/kiosk/prijzen/acties/<int:actie_id>/bewerken", methods=["GET", "POST"])
    def kiosk_actie_bewerken(actie_id):
        db = get_db()
        actie = db.execute("SELECT * FROM kiosk_acties WHERE id = ?", (actie_id,)).fetchone()
        if actie is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Actie niet gevonden."}), 404
            flash("Actie niet gevonden.", "error")
            return redirect(url_for("kiosk_acties"))
        if request.method == "POST":
            try:
                product_id = int(request.form.get("product_id") or 0)
            except ValueError:
                product_id = 0
            product = db.execute(
                "SELECT id FROM producten WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None:
                if is_ajax_verzoek():
                    return jsonify({"ok": False, "fout": "Kies een geldig product."})
                flash("Kies een geldig product.", "error")
            else:
                db.execute(
                    "UPDATE kiosk_acties SET product_id = ?, tekst = ?, actief = ? WHERE id = ?",
                    (
                        product_id,
                        request.form.get("tekst", "").strip() or None,
                        1 if request.form.get("actief") else 0,
                        actie_id,
                    ),
                )
                db.commit()
                if is_ajax_verzoek():
                    return jsonify({"ok": True})
                flash("Actie bijgewerkt.", "success")
                return redirect(url_for("kiosk_acties"))
        return render_template(
            "kiosk_actie_form.html", actie=actie, producten=_actie_producten(db)
        )

    @app.route("/kiosk/prijzen/acties/<int:actie_id>/verwijderen", methods=["POST"])
    def kiosk_actie_verwijderen(actie_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_acties WHERE id = ?", (actie_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Actie verwijderd.", "success")
        return redirect(url_for("kiosk_acties"))

    @app.route("/kiosk/prijzen/acties/<int:actie_id>/toon", methods=["POST"])
    def kiosk_actie_toon_wisselen(actie_id):
        """Los aan/uit-knopje per actie -- zelfde 1-tik-patroon als de
        product-schuifjes hierboven, zie de PDA-weergave van
        kiosk_prijzen_instellingen.html."""
        db = get_db()
        actie = db.execute(
            """SELECT ka.*, p.naam AS product_naam FROM kiosk_acties ka
               JOIN producten p ON p.id = ka.product_id WHERE ka.id = ?""",
            (actie_id,),
        ).fetchone()
        if actie is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Actie niet gevonden."}), 404
            flash("Actie niet gevonden.", "error")
            return redirect(url_for("kiosk_prijzen_instellingen"))
        nieuwe_status = 0 if actie["actief"] else 1
        db.execute("UPDATE kiosk_acties SET actief = ? WHERE id = ?", (nieuwe_status, actie_id))
        db.commit()
        if is_ajax_verzoek():
            melding = (
                f"Actie '{actie['product_naam']}' staat nu aan."
                if nieuwe_status
                else f"Actie '{actie['product_naam']}' staat nu uit."
            )
            return jsonify({"ok": True, "actief": nieuwe_status, "melding": melding})
        return redirect(url_for("kiosk_prijzen_instellingen"))
