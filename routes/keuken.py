from flask import flash, g, jsonify, redirect, render_template, request, session, url_for

import barcodes
from database import get_db
from helpers import bereken_frituurvet_status, inkoop_per_stuk, kleine_afbeelding, now_str
from keukenbeheer import (
    boek_keuken_in,
    keuken_barcodes,
    keuken_producten,
    keuken_tellingen,
    verwerk_keuken_telling,
    wis_keuken_stand,
    zet_keuken_prijzen,
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
        return render_template("keuken_tellen.html", producten=keuken_producten(db), eerste_telling=_eerste_telling(db))

    def _eerste_telling(db):
        """Nog nooit een keukentelling: dan staat 'begintelling' alvast aan."""
        return db.execute("SELECT 1 FROM keuken_tellingen LIMIT 1").fetchone() is None

    @app.route("/keuken/tellen/lopen")
    def keuken_tellen_lopen():
        """De looplijst van de keuken: product voor product tellen, losse stuks met de hand en volle dozen met een scan.
        Alles gebeurt in de browser (de stand blijft op het toestel bewaard, ook zonder bereik); aan het eind gaat de
        telling in één keer naar keuken_tellen."""
        db = get_db()
        producten = [
            {
                "id": p["id"], "naam": p["naam"], "subcategorie": p["subcategorie"] or "", "eenheid": p["eenheid"],
                "voorraad": p["voorraad"], "factor": p["besteleenheid_factor"] or 1,
                "besteleenheid": (p["besteleenheid"] or "").lower(),
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
        (een zak van 20, een doos van 40): die verschilt per supermarkt, dus elke verpakking wordt een eigen artikel."""
        db = get_db()
        gegevens = request.get_json(silent=True) or request.form
        product_id = barcodes._getal(gegevens, "product_id")
        if product_id not in {p["id"] for p in keuken_producten(db)}:
            return jsonify({"fout": "Kies een keukenproduct."}), 400
        aantal = barcodes._getal(gegevens, "aantal")
        if not aantal or aantal < 1:
            return jsonify({"fout": "Vul in hoeveel er in deze verpakking of doos zit."}), 400
        artikel_id, fout = barcodes.snel_koppelen(
            db, gegevens.get("code"), product_id, door=session.get("gebruiker_naam"),
            gebruiker_id=session.get("gebruiker_id"), per_verpakking=aantal,
            inkoopprijs=str(gegevens.get("inkoopprijs") or "").replace(",", ".") or None,
            naam=(gegevens.get("naam") or "").strip() or None,
        )
        if fout:
            return jsonify({"fout": fout}), 400
        code = barcodes.normaliseer(gegevens.get("code"))
        return jsonify({"code": code, **keuken_barcodes(db)[code]})

    @app.route("/keuken/inboeken", methods=["GET", "POST"])
    def keuken_inboeken():
        db = get_db()
        if request.method == "POST":
            verpakkingen, inkoop, gescand = {}, {}, {}
            for p in keuken_producten(db):
                n = _getal(request.form.get(f"aantal_{p['id']}"))
                if n:
                    verpakkingen[p["id"]] = n
                stuks = _getal(request.form.get(f"gescand_{p['id']}"))
                if stuks:
                    gescand[p["id"]] = stuks
                prijs = _getal(request.form.get(f"inkoop_{p['id']}"), float)
                if prijs is not None and prijs >= 0:
                    inkoop[p["id"]] = round(prijs, 2)
            aantal = boek_keuken_in(db, verpakkingen, session.get("gebruiker_naam"), now_str(), session.get("gebruiker_id"), inkoop,
                                    gescand=gescand)
            flash(f"{aantal} {'product' if aantal == 1 else 'producten'} ingeboekt." if aantal else "Inkoopprijzen opgeslagen; er is niets ingeboekt.", "success")
            return redirect(url_for("keuken_inboeken"))
        return render_template("keuken_inboeken.html", producten=keuken_producten(db), barcodes=keuken_barcodes(db))

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
