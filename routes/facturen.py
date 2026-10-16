"""Bestellen > Factuur inboeken: dozen en verpakkingen scannen en in één keer inboeken (zie facturen.py). Werkt in de
browser, ook op de handterminal (de scanner typt de barcode en drukt op Enter), en via JSON voor de app die er later
bij komt. Die logt in met de 6-cijferige code van een account (tablet_code_inloggen) en stuurt het csrf_token mee in
de header X-CSRF-Token."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import barcodes
import facturen
from database import get_db
from leveranciers import alle_leveranciers


def _door():
    return {"door": session.get("gebruiker_naam"), "door_id": session.get("gebruiker_id")}


def _producten(db):
    return db.execute(
        """SELECT id, naam, categorie, eenheid FROM producten
           WHERE actief = 1 AND COALESCE(gearchiveerd, 0) = 0 ORDER BY categorie, naam COLLATE NOCASE"""
    ).fetchall()


def _data():
    """Formulier of JSON: de app stuurt JSON, de browser een formulier."""
    return request.get_json(silent=True) or request.form


def _niet_gevonden_json():
    return jsonify({"fout": "Deze inboekronde bestaat niet."}), 404


def _scan_json(db, ronde_id, code):
    """Eén scan verwerken en als JSON teruggeven: de status ('toegevoegd', 'onbekend', 'ongeldig', 'gesloten'), wat
    het is en de bijgewerkte ronde."""
    uitkomst = facturen.scan(db, ronde_id, code)
    gegevens = facturen.ronde(db, ronde_id)
    if gegevens is None:
        return _niet_gevonden_json()
    return jsonify({
        "status": uitkomst["status"],
        "melding": uitkomst["melding"],
        "regel_id": uitkomst["regel_id"],
        "barcode": barcodes.als_json(uitkomst["barcode"]) if uitkomst["barcode"] else None,
        "ronde": facturen.als_json(gegevens),
    })


def register_routes(app):
    # ---------- In de browser ----------

    @app.route("/facturen")
    def facturen_overzicht():
        db = get_db()
        return render_template(
            "facturen.html",
            open_rondes=facturen.open_rondes(db),
            recente_rondes=facturen.recente_rondes(db),
            leveranciers=alle_leveranciers(db, alleen_actief=True),
            bestellingen=facturen.open_bestellingen(db),
        )

    @app.route("/facturen/nieuw", methods=["POST"])
    def factuur_start():
        ronde_id = facturen.start_ronde(
            get_db(), request.form.get("leverancier_id"), request.form.get("factuurnummer"),
            request.form.get("bestelling_id"), **_door(),
        )
        return redirect(url_for("factuur_ronde", ronde_id=ronde_id))

    @app.route("/facturen/<int:ronde_id>")
    def factuur_ronde(ronde_id):
        db = get_db()
        gegevens = facturen.ronde(db, ronde_id)
        if gegevens is None:
            flash("Deze inboekronde bestaat niet.", "error")
            return redirect(url_for("facturen_overzicht"))
        onbekend = request.args.get("onbekend", "")
        onbekende_barcode = barcodes.zoek_barcode(db, onbekend) if onbekend else None
        artikelen = db.execute(
            """SELECT a.id, a.naam, p.naam AS product_naam, a.ean_omverpakking FROM artikelen a
               JOIN producten p ON p.id = a.product_id ORDER BY p.naam COLLATE NOCASE, a.naam COLLATE NOCASE"""
        ).fetchall() if onbekende_barcode else []
        return render_template(
            "factuur_ronde.html",
            g_ronde=gegevens,
            onbekende_barcode=onbekende_barcode if onbekende_barcode and not onbekende_barcode["bekend"] else None,
            artikelen=artikelen,
            producten=_producten(db),
            leveranciers=alle_leveranciers(db, alleen_actief=True),
            bestellingen=facturen.open_bestellingen(db),
        )

    @app.route("/facturen/<int:ronde_id>/scan", methods=["POST"])
    def factuur_scan(ronde_id):
        uitkomst = facturen.scan(get_db(), ronde_id, request.form.get("code", ""))
        terug = url_for("factuur_ronde", ronde_id=ronde_id)
        if uitkomst["status"] == "toegevoegd":
            flash(f"+ {uitkomst['melding']}", "success")
        elif uitkomst["status"] == "onbekend":
            return redirect(url_for("factuur_ronde", ronde_id=ronde_id, onbekend=uitkomst["barcode"]["code"]) + "#onbekend")
        else:
            flash(uitkomst["melding"], "error")
        return redirect(terug)

    @app.route("/facturen/<int:ronde_id>/handmatig", methods=["POST"])
    def factuur_handmatig(ronde_id):
        fout = facturen.voeg_handmatig_toe(
            get_db(), ronde_id, request.form.get("product_id"), request.form.get("eenheden"), request.form.get("prijs")
        )
        flash(fout or "Toegevoegd.", "error" if fout else "success")
        return redirect(url_for("factuur_ronde", ronde_id=ronde_id))

    @app.route("/facturen/<int:ronde_id>/regels/<int:regel_id>", methods=["POST"])
    def factuur_regel_aantal(ronde_id, regel_id):
        aantal = 0 if request.form.get("weg") else request.form.get("aantal")
        fout = facturen.zet_aantal(get_db(), ronde_id, regel_id, aantal)
        if fout:
            flash(fout, "error")
        return redirect(url_for("factuur_ronde", ronde_id=ronde_id))

    @app.route("/facturen/<int:ronde_id>/gegevens", methods=["POST"])
    def factuur_gegevens(ronde_id):
        facturen.werk_gegevens_bij(get_db(), ronde_id, request.form)
        flash("Gegevens van de factuur opgeslagen.", "success")
        return redirect(url_for("factuur_ronde", ronde_id=ronde_id))

    @app.route("/facturen/<int:ronde_id>/afronden", methods=["POST"])
    def factuur_afronden(ronde_id):
        samenvatting, fout = facturen.afronden(get_db(), ronde_id, **_door())
        if fout:
            flash(fout, "error")
            return redirect(url_for("factuur_ronde", ronde_id=ronde_id))
        tekst = f"Factuur ingeboekt: {samenvatting['producten']} product(en), samen {samenvatting['eenheden']} erbij."
        if samenvatting["bestelling_id"]:
            tekst += f" Bestelling #{samenvatting['bestelling_id']} staat op ontvangen"
            tekst += f" ({samenvatting['manco']} niet geleverd)." if samenvatting["manco"] else "."
        flash(tekst, "success")
        return redirect(url_for("factuur_ronde", ronde_id=ronde_id))

    @app.route("/facturen/<int:ronde_id>/annuleren", methods=["POST"])
    def factuur_annuleren(ronde_id):
        facturen.annuleren(get_db(), ronde_id)
        flash("Inboekronde geannuleerd; er is niets ingeboekt.", "success")
        return redirect(url_for("facturen_overzicht"))

    # ---------- Voor de app op de handterminal (JSON) ----------

    @app.route("/api/facturen", methods=["GET", "POST"])
    def api_facturen():
        """GET: de open rondes en wat je nodig hebt om er een te beginnen. POST: een ronde beginnen
        ({leverancier_id, factuurnummer, bestelling_id}, alles mag leeg)."""
        db = get_db()
        if request.method == "POST":
            data = _data()
            ronde_id = facturen.start_ronde(db, data.get("leverancier_id"), data.get("factuurnummer"),
                                            data.get("bestelling_id"), bron="app", **_door())
            return jsonify(facturen.als_json(facturen.ronde(db, ronde_id))), 201
        return jsonify({
            "open": [facturen.als_json(facturen.ronde(db, r["id"])) for r in facturen.open_rondes(db)],
            "leveranciers": [{"id": r["id"], "naam": r["naam"]} for r in alle_leveranciers(db, alleen_actief=True)],
            "bestellingen": [dict(r) for r in facturen.open_bestellingen(db)],
            "producten": [dict(r) for r in _producten(db)],
        })

    @app.route("/api/facturen/<int:ronde_id>", methods=["GET", "POST"])
    def api_factuur(ronde_id):
        """GET: de ronde met zijn regels en totalen. POST: de gegevens bijwerken (leverancier, factuurnummer,
        factuurbedrag, bestelling, opmerking)."""
        db = get_db()
        if request.method == "POST":
            facturen.werk_gegevens_bij(db, ronde_id, _data())
        gegevens = facturen.ronde(db, ronde_id)
        return jsonify(facturen.als_json(gegevens)) if gegevens else _niet_gevonden_json()

    @app.route("/api/facturen/<int:ronde_id>/scan", methods=["POST"])
    def api_factuur_scan(ronde_id):
        """{code}: één scan (zie _scan_json)."""
        return _scan_json(get_db(), ronde_id, str(_data().get("code", "")))

    @app.route("/api/facturen/<int:ronde_id>/koppelen", methods=["POST"])
    def api_factuur_koppelen(ronde_id):
        """Een onbekende barcode koppelen en meteen meetellen. {code, soort: 'artikel', product_id, naam,
        aantal_per_verpakking, inkoopprijs, ...} maakt een nieuw artikel (de code als barcode van de verpakking, of met
        'doos': true van de doos, met per_omverpakking); {code, soort: 'doos', artikel_id, per_omverpakking} maakt het de
        doos van een bekend artikel."""
        db = get_db()
        data = _data()
        code = str(data.get("code", ""))
        if data.get("soort") == "doos":
            fout = barcodes.koppel_doos(db, int(data.get("artikel_id") or 0), code, data.get("per_omverpakking"))
        else:
            velden = dict(data)
            velden["ean_omverpakking" if data.get("doos") else "ean"] = code
            _, fout = barcodes.bewaar_artikel(db, velden, door=session.get("gebruiker_naam"),
                                              gebruiker_id=session.get("gebruiker_id"))
        if fout:
            return jsonify({"status": "fout", "melding": fout}), 400
        return _scan_json(db, ronde_id, code)

    @app.route("/api/facturen/<int:ronde_id>/regels/<int:regel_id>", methods=["POST"])
    def api_factuur_regel(ronde_id, regel_id):
        """{aantal}: hoe vaak een regel gescand is; 0 haalt hem weg."""
        db = get_db()
        fout = facturen.zet_aantal(db, ronde_id, regel_id, _data().get("aantal"))
        if fout:
            return jsonify({"status": "fout", "melding": fout}), 400
        gegevens = facturen.ronde(db, ronde_id)
        return jsonify(facturen.als_json(gegevens)) if gegevens else _niet_gevonden_json()

    @app.route("/api/facturen/<int:ronde_id>/afronden", methods=["POST"])
    def api_factuur_afronden(ronde_id):
        db = get_db()
        samenvatting, fout = facturen.afronden(db, ronde_id, **_door())
        if fout:
            return jsonify({"status": "fout", "melding": fout}), 400
        return jsonify({"status": "afgerond", "samenvatting": samenvatting,
                        "ronde": facturen.als_json(facturen.ronde(db, ronde_id))})
