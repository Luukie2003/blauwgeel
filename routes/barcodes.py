"""Producten > Barcodes: artikelen met hun barcode (EAN) per product, een barcode opzoeken en een onbekende toevoegen
(zie barcodes.py). Ook een JSON-adres voor de app op de handterminal die er later bij komt."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import barcodes
import facturen
from database import get_db
from leveranciers import alle_leveranciers


def _producten(db, ook_id=None):
    """De producten waar een artikel bij kan horen (niet gearchiveerd), plus die van het artikel zelf."""
    return db.execute(
        """SELECT id, naam, categorie, eenheid, actief FROM producten
           WHERE COALESCE(gearchiveerd, 0) = 0 OR id = ?
           ORDER BY categorie, naam COLLATE NOCASE""",
        (ook_id or 0,),
    ).fetchall()


def _formulier(db, artikel=None, waarden=None):
    waarden = waarden or {}
    product_id = waarden.get("product_id") or (artikel["product_id"] if artikel else None)
    return render_template(
        "artikel_form.html",
        artikel=artikel,
        waarden=waarden,
        producten=_producten(db, product_id),
        leveranciers=alle_leveranciers(db),
        terug=waarden.get("terug") or request.args.get("terug", ""),
        zoekcode=waarden.get("zoekcode") or request.args.get("zoekcode", ""),
        ronde_id=waarden.get("ronde_id") or request.args.get("ronde_id", ""),
    )


def _door():
    return {"door": session.get("gebruiker_naam"), "gebruiker_id": session.get("gebruiker_id")}


def _terug_naar_ronde(db, ronde_id, code):
    """Vanuit een inboekronde (Factuur inboeken): de net gekoppelde barcode telt meteen mee, en terug naar de ronde."""
    uitkomst = facturen.scan(db, int(ronde_id), code)
    if uitkomst["status"] == "toegevoegd":
        flash(f"+ {uitkomst['melding']}", "success")
    return redirect(url_for("factuur_ronde", ronde_id=int(ronde_id)))


def _na_opslaan(form, artikel_id):
    if form.get("terug") == "ronde" and str(form.get("ronde_id", "")).isdigit() and form.get("zoekcode"):
        return _terug_naar_ronde(get_db(), form["ronde_id"], form["zoekcode"])
    if form.get("terug") == "zoeken" and form.get("zoekcode"):
        return redirect(url_for("barcode_zoeken", code=form["zoekcode"]))
    if form.get("terug") == "product" and form.get("product_id"):
        return redirect(url_for("product_bewerken", product_id=form["product_id"]) + "#artikelen")
    return redirect(url_for("barcodes_overzicht") + f"#artikel-{artikel_id}")


def register_routes(app):
    @app.route("/barcodes")
    def barcodes_overzicht():
        db = get_db()
        zoekterm = request.args.get("q", "").strip()
        artikelen = barcodes.alle_artikelen(db, zoekterm)
        per_product = []
        for a in artikelen:
            if not per_product or per_product[-1]["product_id"] != a["product_id"]:
                per_product.append({"product_id": a["product_id"], "naam": a["product_naam"], "categorie": a["categorie"],
                                    "eenheid": a["eenheid"], "artikelen": [],
                                    "inkoop": barcodes.inkoop_uit_artikelen(db, a["product_id"])})
            per_product[-1]["artikelen"].append(a)
        return render_template(
            "barcodes.html",
            per_product=per_product,
            aantal=len(artikelen),
            zoekterm=zoekterm,
            per_eenheid=barcodes.per_eenheid,
        )

    @app.route("/barcodes/zoek")
    def barcode_zoeken():
        """Een gescande (of ingetikte) barcode: wat het is, of de keuze om 'm toe te voegen als hij onbekend is."""
        db = get_db()
        tekst = request.args.get("code", "").strip()
        if not tekst:
            return redirect(url_for("barcodes_overzicht"))
        uitkomst = barcodes.zoek_barcode(db, tekst)
        artikelen = db.execute(
            """SELECT a.id, a.naam, p.naam AS product_naam, a.ean_omverpakking FROM artikelen a
               JOIN producten p ON p.id = a.product_id ORDER BY p.naam COLLATE NOCASE, a.naam COLLATE NOCASE"""
        ).fetchall() if uitkomst["geldig"] and not uitkomst["bekend"] else []
        return render_template("barcode_zoeken.html", uitkomst=uitkomst, artikelen=artikelen,
                               per_eenheid=barcodes.per_eenheid)

    @app.route("/barcodes/nieuw", methods=["GET", "POST"])
    def artikel_nieuw():
        db = get_db()
        if request.method == "POST":
            artikel_id, fout = barcodes.bewaar_artikel(db, request.form, **_door())
            if fout:
                flash(fout, "error")
                return _formulier(db, waarden=request.form)
            flash(f"Artikel '{request.form.get('naam', '').strip()}' opgeslagen.", "success")
            return _na_opslaan(request.form, artikel_id)
        waarden = {k: request.args.get(k, "") for k in ("ean", "ean_omverpakking", "product_id", "naam")}
        return _formulier(db, waarden=waarden)

    @app.route("/barcodes/<int:artikel_id>/bewerken", methods=["GET", "POST"])
    def artikel_bewerken(artikel_id):
        db = get_db()
        artikel = barcodes.artikel(db, artikel_id)
        if artikel is None:
            flash("Dat artikel bestaat niet meer.", "error")
            return redirect(url_for("barcodes_overzicht"))
        if request.method == "POST":
            _, fout = barcodes.bewaar_artikel(db, request.form, artikel_id, **_door())
            if fout:
                flash(fout, "error")
                return _formulier(db, artikel, waarden=request.form)
            flash(f"Artikel '{request.form.get('naam', '').strip()}' opgeslagen.", "success")
            return _na_opslaan(request.form, artikel_id)
        return _formulier(db, artikel)

    @app.route("/barcodes/<int:artikel_id>/verwijderen", methods=["POST"])
    def artikel_verwijderen(artikel_id):
        db = get_db()
        artikel = barcodes.artikel(db, artikel_id)
        if artikel is not None:
            barcodes.verwijder_artikel(db, artikel_id, **_door())
            flash(f"Artikel '{artikel['naam']}' en zijn barcodes zijn verwijderd. Het product zelf blijft.", "success")
        if request.form.get("terug") == "product" and artikel is not None:
            return redirect(url_for("product_bewerken", product_id=artikel["product_id"]) + "#artikelen")
        return redirect(url_for("barcodes_overzicht"))

    @app.route("/barcodes/doos", methods=["POST"])
    def barcode_doos_koppelen():
        """Een onbekende barcode is de doos van een artikel dat al bekend is."""
        db = get_db()
        code = request.form.get("code", "")
        artikel_id = request.form.get("artikel_id", "")
        fout = barcodes.koppel_doos(db, int(artikel_id) if artikel_id.isdigit() else 0, code, request.form.get("per_omverpakking"))
        ronde_id = request.form.get("ronde_id", "")
        if fout:
            flash(fout, "error")
        else:
            flash("Doos-barcode toegevoegd.", "success")
            if ronde_id.isdigit():
                return _terug_naar_ronde(db, ronde_id, code)
        if ronde_id.isdigit():
            return redirect(url_for("factuur_ronde", ronde_id=int(ronde_id), onbekend=code) + "#onbekend")
        return redirect(url_for("barcode_zoeken", code=code))

    @app.route("/api/barcode/<code>")
    def api_barcode(code):
        """Wat er achter een barcode zit, als JSON (voor de app op de handterminal)."""
        return jsonify(barcodes.als_json(barcodes.zoek_barcode(get_db(), code)))
