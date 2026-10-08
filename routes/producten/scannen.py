"""QR-codes en schaplabels: scannen, de landingspagina, zoeken en de label-PDF's."""

from flask import Response, flash, jsonify, redirect, render_template, request, url_for

import qr
from database import get_db
from helpers import PRODUCT_AFBEELDINGEN_MAP, now_str
from pdf import schaplabels_pdf


def _label_gegevens(product):
    """Zet een productrij om in wat schaplabels_pdf nodig heeft: de
    gewone velden plus een kant-en-klare QR (PNG-bytes) die naar de
    publieke scan-landingspagina linkt (geen account nodig, zie
    scan_landing) -- scanbaar met elke telefooncamera, niet alleen
    vanuit de handterminal-weergave zelf -- en het pad naar de
    productfoto, dezelfde die ook op de site wordt getoond."""
    url = url_for("scan_landing", product_id=product["id"], _external=True)
    foto_pad = PRODUCT_AFBEELDINGEN_MAP / product["afbeelding"] if product["afbeelding"] else None
    return {
        "naam": product["naam"],
        "categorie": product["categorie"],
        "subcategorie": product["subcategorie"],
        "artikelcode": product["artikelcode"],
        "min_voorraad": product["min_voorraad"],
        "eenheid": product["eenheid"],
        "qr_png": qr.qr_png_bytes(url),
        "foto_pad": foto_pad if foto_pad and foto_pad.exists() else None,
    }


def register_routes(app):
    @app.route("/scannen")
    def scannen():
        return render_template("scannen.html")

    @app.route("/scan/<int:product_id>")
    def scan_landing(product_id):
        """Waar de QR-code op een schaplabel naartoe wijst -- publiek, geen
        account nodig (zie OPEN_ENDPOINTS in app.py), met twee grote
        knoppen: naar de echte productpagina (die alsnog om inloggen vraagt)
        of direct -- zonder account -- melden voor de bestellijst."""
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            return render_template("scan_landing.html", product=None), 404
        return render_template("scan_landing.html", product=product)

    @app.route("/scan/<int:product_id>/melden", methods=["POST"])
    def scan_melden(product_id):
        db = get_db()
        product = db.execute(
            "SELECT id FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("scan_landing", product_id=product_id))
        db.execute(
            """INSERT INTO bestellijst_meldingen (product_id, bron, aangemaakt_op)
               VALUES (?, 'qr_scan', ?)""",
            (product_id, now_str()),
        )
        db.commit()
        flash("Bedankt! Dit is doorgegeven voor de bestellijst.", "success")
        return redirect(url_for("scan_landing", product_id=product_id))

    @app.route("/producten/zoeken")
    def product_zoeken():
        """Live zoeken op productnaam/artikelcode voor de zoekbalk boven in
        de handterminal-weergave -- geeft JSON terug, geen pagina."""
        db = get_db()
        term = request.args.get("q", "").strip()
        if len(term) < 2:
            return jsonify({"resultaten": []})
        patroon = f"%{term}%"
        rijen = db.execute(
            """SELECT id, naam, categorie, voorraad, min_voorraad, eenheid, afbeelding
               FROM producten
               WHERE actief = 1 AND (naam LIKE ? OR artikelcode LIKE ?)
               ORDER BY (naam NOT LIKE ?), naam
               LIMIT 15""",
            (patroon, patroon, f"{term}%"),
        ).fetchall()
        return jsonify({"resultaten": [dict(p) for p in rijen]})

    @app.route("/producten/<int:product_id>")
    def product_detail(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        mutaties = db.execute(
            """SELECT * FROM mutaties WHERE product_id = ?
               ORDER BY id DESC LIMIT 10""",
            (product_id,),
        ).fetchall()
        return render_template(
            "product_detail.html", product=product, mutaties=mutaties
        )

    @app.route("/producten/<int:product_id>/label.pdf")
    def product_label_pdf(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        pdf_bytes = schaplabels_pdf([_label_gegevens(product)])
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f'inline; filename="label-{product["naam"]}.pdf"'},
        )

    @app.route("/producten/labels.pdf")
    def producten_labels_pdf():
        ids = []
        for deel in request.args.get("ids", "").split(","):
            deel = deel.strip()
            if deel.isdigit():
                ids.append(int(deel))
        if not ids:
            flash("Geen producten geselecteerd om labels voor te printen.", "error")
            return redirect(url_for("producten_lijst"))
        # Cap tegen een té groot verzoek (bijv. geknoei met de query-string) --
        # in de praktijk selecteert niemand meer dan een paar tientallen
        # producten tegelijk.
        ids = ids[:200]
        db = get_db()
        placeholders = ",".join("?" * len(ids))
        producten = db.execute(
            f"SELECT * FROM producten WHERE id IN ({placeholders}) ORDER BY categorie, naam",
            ids,
        ).fetchall()
        if not producten:
            flash("Geen van de geselecteerde producten kon gevonden worden.", "error")
            return redirect(url_for("producten_lijst"))
        pdf_bytes = schaplabels_pdf([_label_gegevens(p) for p in producten])
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": 'inline; filename="schaplabels.pdf"'},
        )
