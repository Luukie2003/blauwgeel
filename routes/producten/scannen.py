"""QR-codes en schaplabels: scannen, de landingspagina, zoeken en de label-PDF's."""

from flask import Response, flash, jsonify, redirect, render_template, request, session, url_for

import barcodes
import productinfo
import qr
from database import get_db
from derving import DERVING_REDENEN
from helpers import PRODUCT_AFBEELDINGEN_MAP, besteleenheid_factor, kleine_afbeelding
from keukenbeheer import KEUKEN_NIET_BESTELLEN
from pdf import label_opties, schaplabels_pdf
from productkaart import KEUKEN_CATEGORIE


# Een product met de naam van zijn leverancier, voor op het schaplabel.
_LABEL_SQL = "SELECT p.*, l.naam AS leverancier_naam FROM producten p LEFT JOIN leveranciers l ON l.id = p.leverancier_id"


def _label_gegevens(product):
    """Zet een productrij (uit _LABEL_SQL) om in wat schaplabels_pdf nodig heeft: de gewone velden, een kant-en-klare QR
    (PNG-bytes) naar /scan/<id> -- de handterminal opent daarmee het product, met de bestelknoppen; een telefooncamera
    komt op de publieke landingspagina (scan_landing) -- en het pad naar de productfoto, dezelfde als op de site."""
    url = url_for("scan_landing", product_id=product["id"], _external=True)
    foto_pad = PRODUCT_AFBEELDINGEN_MAP / product["afbeelding"] if product["afbeelding"] else None
    return {
        "naam": product["naam"],
        "categorie": product["categorie"],
        "subcategorie": product["subcategorie"],
        "artikelcode": product["artikelcode"],
        "leverancier": product["leverancier_naam"],
        "min_voorraad": product["min_voorraad"],
        "eenheid": product["eenheid"],
        "besteleenheid": product["besteleenheid"],
        "besteleenheid_factor": besteleenheid_factor(product),
        "verkoopprijs": product["verkoopprijs"],
        "qr_png": qr.qr_png_bytes(url),
        "qr_hint": "Scan met de handterminal",
        "foto_pad": foto_pad if foto_pad and foto_pad.exists() else None,
    }


def register_routes(app):
    @app.route("/scannen")
    def scannen():
        return render_template("scannen.html")

    @app.route("/scan/<int:product_id>")
    def scan_landing(product_id):
        """Waar de QR-code op een schaplabel naartoe wijst. Op de handterminal opent de app bij een scan meteen het
        product (informatie, en bestellen). Met een telefoon: ben je ingelogd, dan meteen de productpagina; anders deze
        publieke pagina met het product en een knop naar de productpagina (die om inloggen vraagt). Melden voor de
        bestellijst via de QR-code kan sinds 1.72.0 niet meer: dat gaat via de handterminal of de productpagina."""
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            return render_template("scan_landing.html", product=None), 404
        if session.get("gebruiker_id"):
            return redirect(url_for("product_detail", product_id=product_id))
        return render_template("scan_landing.html", product=product)

    @app.route("/producten/zoeken")
    def product_zoeken():
        """Live zoeken op productnaam/artikelcode voor de zoekbalk boven in
        de handterminal-weergave -- geeft JSON terug, geen pagina. Een
        gescande barcode (zie barcodes.py) geeft het product van dat artikel
        ("barcode": wat het is), of "onbekende_barcode" als hij nog niet
        bekend is; de zoekbalk springt daar bij Enter meteen naartoe."""
        db = get_db()
        term = request.args.get("q", "").strip()
        if len(term) < 2:
            return jsonify({"resultaten": []})
        code = barcodes.normaliseer(term)
        gevonden = barcodes.zoek_barcode(db, term) if code and len(code) >= 8 else None
        if gevonden and gevonden["bekend"]:
            product = db.execute(
                "SELECT id, naam, categorie, voorraad, min_voorraad, eenheid, afbeelding FROM producten WHERE id = ?",
                (gevonden["artikel"]["product_id"],),
            ).fetchone()
            return jsonify({
                "resultaten": [dict(product, afbeelding=kleine_afbeelding(product["afbeelding"]))],
                "barcode": {"code": gevonden["code"], "omschrijving": gevonden["omschrijving"]},
            })
        patroon = f"%{term}%"
        rijen = db.execute(
            """SELECT id, naam, categorie, voorraad, min_voorraad, eenheid, afbeelding
               FROM producten
               WHERE actief = 1 AND (naam LIKE ? OR artikelcode LIKE ?)
               ORDER BY (naam NOT LIKE ?), naam
               LIMIT 15""",
            (patroon, patroon, f"{term}%"),
        ).fetchall()
        if not rijen and gevonden and gevonden["geldig"]:
            # Een geldige barcode die nergens bij hoort (ook niet als artikelcode): die kun je toevoegen.
            return jsonify({"resultaten": [], "onbekende_barcode": gevonden["code"]})
        # De foto staat in een zoeklijstje op 40 px: de verkleinde versie volstaat.
        resultaten = [dict(p, afbeelding=kleine_afbeelding(p["afbeelding"])) for p in rijen]
        return jsonify({"resultaten": resultaten})

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
            "product_detail.html",
            product=product,
            mutaties=mutaties,
            derving_redenen=DERVING_REDENEN,
            info=productinfo.productinfo(db, product),
            leeftijd=productinfo.leeftijd,
            per_eenheid=barcodes.per_eenheid,
        )

    @app.route("/producten/<int:product_id>/verkoop")
    def product_detail_verkoop(product_id):
        """Het blok 'Verkoop en verwachting' van de productpagina: apart opgehaald, want het voorspelmodel rekent op de
        server soms enkele seconden."""
        db = get_db()
        product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return ""
        try:
            verkoop = productinfo.verkoopinfo(db, product_id)
        except Exception as fout:  # het blok mag de productpagina nooit stuk maken
            print(f"[productpagina] verkoop van {product_id} mislukt: {fout}")
            verkoop = None
        bestellen = verkoop["bestellen"] if verkoop else productinfo.bestelblok(db, product)
        return render_template("_product_verkoop.html", product=product, verkoop=verkoop, bestellen=bestellen)

    @app.route("/producten/<int:product_id>/bestellen", methods=["POST"])
    def product_bestelaantal(product_id):
        """Zelf kiezen hoeveel colli je van dit product bestelt (min en plus, of een aantal invullen); 'advies' = weer
        het advies volgen. Zie bestelvoorstel.py."""
        import bestelvoorstel

        db = get_db()
        product = db.execute("SELECT categorie FROM producten WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        if product["categorie"] == KEUKEN_CATEGORIE:
            flash(KEUKEN_NIET_BESTELLEN, "error")
            return redirect(url_for("product_detail", product_id=product_id))
        # De knoppen sturen 'eenheden' mee; Enter in het invulvak (een lege 'eenheden') het getal uit 'aantal'.
        keuze = request.form.get("eenheden") or request.form.get("aantal", "")
        if keuze == "advies":
            eenheden = None
        else:
            try:
                eenheden = max(0, min(bestelvoorstel.MAX_EENHEDEN, int(keuze)))
            except ValueError:
                flash("Vul een aantal in.", "error")
                return redirect(url_for("product_detail", product_id=product_id) + "#verkoop")
        bestelvoorstel.zet_bestelaantal(db, product_id, eenheden, session.get("gebruiker_naam"), session.get("gebruiker_id"))
        if eenheden is None:
            flash("Weer het advies.", "success")
        else:
            flash("Niet bestellen; staat zo op de bestellijst." if eenheden == 0
                  else "Opgeslagen; staat zo bij Voorgesteld om te bestellen.", "success")
        return redirect(url_for("product_detail", product_id=product_id) + "#verkoop")

    @app.route("/producten/<int:product_id>/melden", methods=["POST"])
    def product_melden(product_id):
        """'Op de bestellijst': het product bij "Voorgesteld om te bestellen" zetten (zie bestelvoorstel.zet_op_bestellijst).
        Op de handterminal: de QR-code op het schaplabel of de barcode scannen, en dan dezelfde knop."""
        import bestelvoorstel

        db = get_db()
        product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        _, melding = bestelvoorstel.zet_op_bestellijst(db, product, session.get("gebruiker_naam"), session.get("gebruiker_id"))
        flash(melding, "success")
        return redirect(url_for("product_detail", product_id=product_id) + "#verkoop")

    @app.route("/producten/<int:product_id>/label.pdf")
    def product_label_pdf(product_id):
        db = get_db()
        product = db.execute(_LABEL_SQL + " WHERE p.id = ?", (product_id,)).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        pdf_bytes = schaplabels_pdf([_label_gegevens(product)], **label_opties(request.args))
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
        producten = db.execute(f"{_LABEL_SQL} WHERE p.id IN ({placeholders}) ORDER BY p.categorie, p.naam", ids).fetchall()
        if not producten:
            flash("Geen van de geselecteerde producten kon gevonden worden.", "error")
            return redirect(url_for("producten_lijst"))
        pdf_bytes = schaplabels_pdf([_label_gegevens(p) for p in producten], **label_opties(request.args))
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": 'inline; filename="schaplabels.pdf"'},
        )
