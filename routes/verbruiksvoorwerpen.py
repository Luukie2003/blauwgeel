from flask import Response, flash, redirect, render_template, request, url_for

import qr
from database import get_db
from helpers import now_str
from pdf import schaplabels_pdf


def register_routes(app):
    @app.route("/verbruiksvoorwerpen", methods=["GET", "POST"])
    def verbruiksvoorwerpen_lijst():
        db = get_db()
        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            categorie = request.form.get("categorie", "").strip() or None
            if not naam:
                flash("Naam is verplicht.", "error")
            else:
                db.execute(
                    "INSERT INTO verbruiksvoorwerpen (naam, categorie, aangemaakt_op) VALUES (?, ?, ?)",
                    (naam, categorie, now_str()),
                )
                db.commit()
                flash(f"'{naam}' toegevoegd.", "success")
            return redirect(url_for("verbruiksvoorwerpen_lijst"))

        items = db.execute(
            "SELECT * FROM verbruiksvoorwerpen ORDER BY categorie, naam"
        ).fetchall()
        return render_template("verbruiksvoorwerpen.html", items=items)

    @app.route("/verbruiksvoorwerpen/<int:item_id>/verwijderen", methods=["POST"])
    def verbruiksvoorwerp_verwijderen(item_id):
        db = get_db()
        db.execute("DELETE FROM verbruiksvoorwerpen WHERE id = ?", (item_id,))
        db.commit()
        flash("Verwijderd.", "success")
        return redirect(url_for("verbruiksvoorwerpen_lijst"))

    @app.route("/verbruiksvoorwerpen/<int:item_id>/bestellijst-melden", methods=["POST"])
    def verbruiksvoorwerp_bestellijst_melden(item_id):
        db = get_db()
        item = db.execute(
            "SELECT * FROM verbruiksvoorwerpen WHERE id = ?", (item_id,)
        ).fetchone()
        if item is None:
            flash("Verbruiksvoorwerp niet gevonden.", "error")
            return redirect(url_for("verbruiksvoorwerpen_lijst"))
        db.execute(
            """INSERT INTO bestellijst_meldingen (tekst, bron, aangemaakt_op)
               VALUES (?, 'verbruiksvoorwerp', ?)""",
            (item["naam"], now_str()),
        )
        db.commit()
        flash(f"'{item['naam']}' op de bestellijst gezet.", "success")
        return redirect(url_for("verbruiksvoorwerpen_lijst"))

    def _label_gegevens_verbruiksvoorwerp(item):
        url = url_for("scan_landing_verbruiksvoorwerp", item_id=item["id"], _external=True)
        return {
            "naam": item["naam"],
            "categorie": item["categorie"] or "Verbruiksvoorwerp",
            "qr_png": qr.qr_png_bytes(url),
            # Verbruiksvoorwerpen hebben geen eigen afbeeldingsveld (in
            # tegenstelling tot producten) -- dus geen leeg foto-kadertje op
            # het label, de tekst krijgt die ruimte erbij.
            "heeft_foto_kolom": False,
        }

    @app.route("/scan/verbruiksvoorwerp/<int:item_id>")
    def scan_landing_verbruiksvoorwerp(item_id):
        """Waar de QR-code op een verbruiksvoorwerp-schaplabel naartoe wijst
        -- publiek, geen account nodig (zie OPEN_ENDPOINTS in app.py), zelfde
        opzet als scan_landing voor gewone producten. Geen 'naar
        productpagina'-knop: een verbruiksvoorwerp heeft geen eigen pagina
        om naartoe te gaan, alleen de melding is relevant."""
        db = get_db()
        item = db.execute(
            "SELECT * FROM verbruiksvoorwerpen WHERE id = ?", (item_id,)
        ).fetchone()
        if item is None:
            return render_template("scan_landing_verbruiksvoorwerp.html", item=None), 404
        return render_template("scan_landing_verbruiksvoorwerp.html", item=item)

    @app.route("/scan/verbruiksvoorwerp/<int:item_id>/melden", methods=["POST"])
    def scan_melden_verbruiksvoorwerp(item_id):
        db = get_db()
        item = db.execute(
            "SELECT * FROM verbruiksvoorwerpen WHERE id = ?", (item_id,)
        ).fetchone()
        if item is None:
            flash("Verbruiksvoorwerp niet gevonden.", "error")
            return redirect(url_for("scan_landing_verbruiksvoorwerp", item_id=item_id))
        db.execute(
            """INSERT INTO bestellijst_meldingen (tekst, bron, aangemaakt_op)
               VALUES (?, 'verbruiksvoorwerp', ?)""",
            (item["naam"], now_str()),
        )
        db.commit()
        flash("Bedankt! Dit is doorgegeven voor de bestellijst.", "success")
        return redirect(url_for("scan_landing_verbruiksvoorwerp", item_id=item_id))

    @app.route("/verbruiksvoorwerpen/<int:item_id>/label.pdf")
    def verbruiksvoorwerp_label_pdf(item_id):
        db = get_db()
        item = db.execute(
            "SELECT * FROM verbruiksvoorwerpen WHERE id = ?", (item_id,)
        ).fetchone()
        if item is None:
            flash("Verbruiksvoorwerp niet gevonden.", "error")
            return redirect(url_for("verbruiksvoorwerpen_lijst"))
        pdf_bytes = schaplabels_pdf([_label_gegevens_verbruiksvoorwerp(item)])
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f'inline; filename="label-{item["naam"]}.pdf"'},
        )

    @app.route("/verbruiksvoorwerpen/labels.pdf")
    def verbruiksvoorwerpen_labels_pdf():
        ids = []
        for deel in request.args.get("ids", "").split(","):
            deel = deel.strip()
            if deel.isdigit():
                ids.append(int(deel))
        if not ids:
            flash("Geen items geselecteerd om labels voor te printen.", "error")
            return redirect(url_for("verbruiksvoorwerpen_lijst"))
        ids = ids[:200]
        db = get_db()
        placeholders = ",".join("?" * len(ids))
        items = db.execute(
            f"SELECT * FROM verbruiksvoorwerpen WHERE id IN ({placeholders}) ORDER BY categorie, naam",
            ids,
        ).fetchall()
        if not items:
            flash("Geen van de geselecteerde items kon gevonden worden.", "error")
            return redirect(url_for("verbruiksvoorwerpen_lijst"))
        pdf_bytes = schaplabels_pdf([_label_gegevens_verbruiksvoorwerp(i) for i in items])
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": 'inline; filename="schaplabels-verbruiksvoorwerpen.pdf"'},
        )
