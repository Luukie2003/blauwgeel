from flask import flash, g, jsonify, redirect, render_template, request, session, url_for

import barcodes
from database import get_db
from derving import DERVING_REDENEN
from helpers import bereken_frituurvet_status, inkoop_per_stuk, kleine_afbeelding, now_str
from keukenbeheer import (
    KEUKEN_MUTATIES,
    boek_keuken_in,
    keuken_barcodes,
    keuken_producten,
    keuken_tellingen,
    keuken_verpakkingen,
    koppel_keuken_barcode,
    muteer_keuken,
    verwerk_keuken_telling,
    wis_keuken_stand,
    zet_keuken_prijzen,
    zet_keuken_verpakking,
    zet_product_verpakking,
)
from routes.producten import render_producten_pagina, render_voorraad_pda


def register_routes(app):
    @app.route("/frituurvet/vervangen", methods=["POST"])
    def frituurvet_vervangen():
        db = get_db()
        db.execute(
            "INSERT INTO frituurvet_vervangingen (datum, naam, gebruiker_id) VALUES (?, ?, ?)",
            (now_str(), session.get("gebruiker_naam"), session.get("gebruiker_id")),
        )
        db.commit()
        flash("Frituurvet-vervanging geregistreerd.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/keuken")
    def keuken_voorraad():
        # Hergebruikt de Producten-pagina, vergrendeld op categorie
        # 'Keuken' -- dezelfde tabel/acties i.p.v. een eigen bijna-
        # identiek sjabloon (zie render_producten_pagina in
        # routes/producten.py). Blijft een eigen route+endpoint, want deze
        # zit achter sectie 'keuken' i.p.v. 'voorraad': een vrijwilliger met
        # alleen keuken-rechten mag hier wel komen, maar niet op /producten.
        if g.get("weergave_modus") == "pda":
            return render_voorraad_pda(categorie="Keuken", titel="Keuken")
        return render_producten_pagina(categorie_vergrendeld="Keuken")

    @app.route("/keuken/instellingen", methods=["GET", "POST"])
    def keuken_instellingen():
        db = get_db()
        if request.method == "POST":
            try:
                interval = max(1, int(request.form.get("frituurvet_interval_dagen", "14")))
            except ValueError:
                interval = 14
            db.execute(
                "UPDATE instellingen SET frituurvet_interval_dagen = ? WHERE id = 1",
                (interval,),
            )
            db.commit()
            flash("Keuken-instellingen opgeslagen.", "success")
            return redirect(url_for("keuken_instellingen"))

        interval = db.execute(
            "SELECT frituurvet_interval_dagen FROM instellingen WHERE id = 1"
        ).fetchone()["frituurvet_interval_dagen"]
        vervangingen = db.execute(
            "SELECT * FROM frituurvet_vervangingen ORDER BY datum DESC, id DESC LIMIT 20"
        ).fetchall()
        return render_template(
            "keuken_instellingen.html",
            frituurvet_interval_dagen=interval,
            frituurvet_status=bereken_frituurvet_status(db),
            vervangingen=vervangingen,
        )

    # ---------- De keuken als eigen module: tellen, inboeken, prijzen (zie keukenbeheer.py) ----------

    def _getal(waarde, soort=int):
        try:
            return soort((waarde or "").strip().replace(",", "."))
        except ValueError:
            return None

    @app.route("/keuken/tellen", methods=["GET", "POST"])
    def keuken_tellen():
        db = get_db()
        if request.method == "POST":
            waarden = {}
            for p in keuken_producten(db):
                geteld = _getal(request.form.get(f"geteld_{p['id']}"))
                if geteld is not None and geteld >= 0:
                    waarden[p["id"]] = geteld
            begintelling = request.form.get("begintelling") == "1"
            telling_id = verwerk_keuken_telling(
                db, waarden, session.get("gebruiker_naam"), now_str(), session.get("gebruiker_id"),
                request.form.get("opmerking", "").strip(), begintelling=begintelling,
            )
            if telling_id is None:
                flash("Geen aantallen ingevuld: er is niets geteld.", "error")
                return redirect(url_for("keuken_tellen"))
            wis_keuken_stand(db, session.get("gebruiker_id"))
            soort = "Begintelling" if begintelling else "Keukentelling"
            flash(f"{soort} #{telling_id} opgeslagen ({len(waarden)} {'product' if len(waarden) == 1 else 'producten'}).", "success")
            # Uit de looplijst: dan wist het overzicht de stand die in de browser bewaard was (zie keuken_lopen.html).
            if request.form.get("bron") == "looplijst":
                return redirect(url_for("keuken_tellingen_overzicht", opgeslagen=1))
            return redirect(url_for("keuken_tellingen_overzicht"))
        return render_template("keuken_tellen.html", producten=keuken_producten(db), eerste_telling=_eerste_telling(db),
                               verpakkingen=keuken_verpakkingen(db))

    def _eerste_telling(db):
        """Nog nooit een keukentelling: dan staat 'begintelling' alvast aan."""
        return db.execute("SELECT 1 FROM keuken_tellingen LIMIT 1").fetchone() is None

    @app.route("/keuken/tellen/lopen")
    def keuken_tellen_lopen():
        """De looplijst van de keuken: product voor product tellen, losse stuks met de hand en volle dozen met een scan
        of een knop per verpakking (+20 voor de zak van 20). Blind: wat er op de site staat, zie je pas op het
        controlescherm. Alles gebeurt in de browser (de stand blijft op het toestel bewaard, ook zonder bereik); aan het
        eind gaat de telling in één keer naar keuken_tellen."""
        db = get_db()
        verpakkingen = keuken_verpakkingen(db)
        producten = [
            {
                "id": p["id"], "naam": p["naam"], "subcategorie": p["subcategorie"] or "", "eenheid": p["eenheid"],
                "voorraad": p["voorraad"],
                "verpakkingen": [{"naam": v["naam"], "aantal": v["aantal"]} for v in verpakkingen.get(p["id"], [])],
                "foto": url_for("static", filename="product_afbeeldingen/" + kleine_afbeelding(p["afbeelding"], "middel"))
                if p["afbeelding"] else "",
            }
            for p in keuken_producten(db)
        ]
        if not producten:
            flash("Nog geen actieve producten in de categorie Keuken.", "error")
            return redirect(url_for("keuken_tellen"))
        return render_template("keuken_lopen.html", producten=producten, barcodes=keuken_barcodes(db),
                               eerste_telling=_eerste_telling(db))

    @app.route("/keuken/barcode-koppelen", methods=["POST"])
    def keuken_barcode_koppelen():
        """Een onbekende barcode bij het tellen of inboeken meteen aan een keukenproduct koppelen, met hoeveel erin zit
        (een zak van 20, een doos van 40): die verschilt per supermarkt, dus elke verpakking wordt een eigen artikel.
        Minstens 2: de keuken boekt per verpakking in, nooit per stuk."""
        db = get_db()
        gegevens = request.get_json(silent=True) or request.form
        d, fout = koppel_keuken_barcode(
            db, gegevens.get("code"), barcodes._getal(gegevens, "product_id"), barcodes._getal(gegevens, "aantal"),
            gegevens.get("naam"), gegevens.get("inkoopprijs"), session.get("gebruiker_naam"), session.get("gebruiker_id"),
        )
        if fout:
            return jsonify({"fout": fout}), 400
        return jsonify(d)

    @app.route("/keuken/verpakking", methods=["POST"])
    def keuken_verpakking_zetten():
        """Hoeveel er in een gekoppelde zak of doos zit, als dat er nog niet bij stond: de eerste scan vraagt het."""
        db = get_db()
        gegevens = request.get_json(silent=True) or request.form
        d, fout = zet_keuken_verpakking(db, gegevens.get("code"), barcodes._getal(gegevens, "aantal"),
                                        session.get("gebruiker_naam"), session.get("gebruiker_id"))
        if fout:
            return jsonify({"fout": fout}), 400
        return jsonify({"code": barcodes.normaliseer(str(gegevens.get("code"))), **d})

    @app.route("/keuken/product-verpakking", methods=["POST"])
    def keuken_product_verpakking():
        """Een keukenproduct zonder barcode (gehaktballen van de slager): één keer instellen in welke verpakking het komt
        en hoeveel erin zit, dan boek je het daarna per verpakking in."""
        db = get_db()
        gegevens = request.get_json(silent=True) or request.form
        product_id = barcodes._getal(gegevens, "product_id")
        fout = zet_product_verpakking(db, product_id, gegevens.get("naam"), barcodes._getal(gegevens, "aantal"))
        if fout:
            return jsonify({"fout": fout}), 400
        return jsonify({"product_id": product_id, "verpakkingen": keuken_verpakkingen(db).get(product_id, [])})

    @app.route("/keuken/inboeken", methods=["GET", "POST"])
    def keuken_inboeken():
        """Inboeken wat er binnenkomt, altijd per verpakking: scannen (hoeveel erin zit, komt van het merk) of zonder
        barcode per verpakking ("pakket_<product>__<verpakking>", zie keuken_verpakkingen). De inkoopprijs pas je hier
        alleen aan bij een product zonder prijs per merk; die van een merk staat bij zijn barcode (Barcodes)."""
        db = get_db()
        if request.method == "POST":
            verpakkingen, inkoop = {}, {}
            for sleutel, waarde in request.form.items():
                pid, _, soort = sleutel.removeprefix("pakket_").partition("__")
                n = _getal(waarde) if sleutel.startswith("pakket_") else None
                if pid.isdigit() and soort and n and n > 0:
                    verpakkingen.setdefault(int(pid), {})[soort] = n
            for p in keuken_producten(db):
                prijs = _getal(request.form.get(f"inkoop_{p['id']}"), float)
                if prijs is not None and prijs >= 0:
                    inkoop[p["id"]] = round(prijs, 2)
            uitkomst = boek_keuken_in(db, verpakkingen, session.get("gebruiker_naam"), now_str(), session.get("gebruiker_id"),
                                      inkoop, scans=request.form.getlist("scan"))
            aantal = uitkomst["producten"]
            if aantal:
                flash(f"{aantal} {'product' if aantal == 1 else 'producten'} ingeboekt.", "success")
            elif not uitkomst["overgeslagen"]:
                flash("Er is niets ingeboekt (de inkoopprijzen zijn wel bewaard).", "success")
            if uitkomst["overgeslagen"]:
                flash("Niet ingeboekt: " + "; ".join(uitkomst["overgeslagen"]) + ".", "error")
            return redirect(url_for("keuken_inboeken"))
        prijs_per_merk = {r["product_id"] for r in db.execute("SELECT DISTINCT product_id FROM artikelen WHERE inkoopprijs > 0")}
        return render_template("keuken_inboeken.html", producten=keuken_producten(db), barcodes=keuken_barcodes(db),
                               verpakkingen=keuken_verpakkingen(db), prijs_per_merk=prijs_per_merk)

    @app.route("/keuken/muteren", methods=["GET", "POST"])
    def keuken_muteren():
        """Wat er weggegooid wordt (derving, met een reden) of een correctie erbij of eraf, per stuk. Zonder derving telt
        wat weg is bij de volgende telling als verkocht."""
        db = get_db()
        if request.method == "POST":
            melding, fout = muteer_keuken(
                db, _getal(request.form.get("product_id")), request.form.get("soort"), _getal(request.form.get("aantal")),
                session.get("gebruiker_naam"), session.get("gebruiker_id"), request.form.get("reden"),
                request.form.get("opmerking", ""),
            )
            flash(fout or melding, "error" if fout else "success")
            return redirect(url_for("keuken_muteren", product=request.form.get("product_id") if fout else None))
        recent = db.execute(
            """SELECT m.*, p.naam AS product_naam, p.eenheid FROM mutaties m JOIN producten p ON p.id = m.product_id
               WHERE p.categorie = 'Keuken' AND m.opmerking LIKE 'Keuken:%' ORDER BY m.datum DESC, m.id DESC LIMIT 20"""
        ).fetchall()
        return render_template("keuken_muteren.html", producten=keuken_producten(db), soorten=KEUKEN_MUTATIES,
                               redenen=DERVING_REDENEN, recent=recent, gekozen=_getal(request.args.get("product")))

    @app.route("/keuken/prijzen", methods=["GET", "POST"])
    def keuken_prijzen():
        db = get_db()
        if request.method == "POST":
            prijzen = {}
            for p in keuken_producten(db, alleen_actief=False):
                prijs = _getal(request.form.get(f"prijs_{p['id']}"), float)
                if prijs is not None and prijs >= 0:
                    prijzen[p["id"]] = round(prijs, 2)
            aantal = zet_keuken_prijzen(db, prijzen, session.get("gebruiker_naam"), now_str(), session.get("gebruiker_id"))
            flash(f"{aantal} {'prijs' if aantal == 1 else 'prijzen'} aangepast." if aantal else "Geen prijzen gewijzigd.", "success")
            return redirect(url_for("keuken_prijzen"))
        producten = [dict(p, inkoop_stuk=inkoop_per_stuk(p)) for p in keuken_producten(db, alleen_actief=False)]
        return render_template("keuken_prijzen.html", producten=producten)

    @app.route("/keuken/tellingen")
    def keuken_tellingen_overzicht():
        return render_template("keuken_tellingen.html", tellingen=keuken_tellingen(get_db()))
