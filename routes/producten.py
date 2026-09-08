from flask import Response, flash, jsonify, redirect, render_template, request, session, url_for

import qr
from database import get_db
from helpers import (
    PRODUCT_AFBEELDINGEN_MAP,
    bewaar_subcategorie,
    categorienamen_zonder_verkoopprijsplicht,
    csv_response,
    is_ajax_verzoek,
    now_str,
    sla_afbeelding_op,
)
from pdf import schaplabels_pdf, voorraadoverzicht_pdf


def register_routes(app):
    def bereken_voorraadoverzicht(db):
        """Verzamelt alle cijfers voor het voorraadoverzicht -- gebruikt door
        zowel de webpagina als de PDF, zodat ze altijd hetzelfde tonen."""
        producten = db.execute("SELECT * FROM producten ORDER BY categorie, naam").fetchall()
        niet_verplicht = categorienamen_zonder_verkoopprijsplicht(db)

        totale_waarde = sum(p["voorraad"] * p["verkoopprijs"] for p in producten)
        zonder_voorraad = [p for p in producten if p["actief"] and p["voorraad"] == 0]
        onder_minimum = [p for p in producten if p["actief"] and p["voorraad"] < p["min_voorraad"]]
        zonder_prijs = [
            p for p in producten
            if p["actief"] and p["verkoopprijs"] == 0 and p["categorie"] not in niet_verplicht
        ]
        inactief_met_voorraad = [p for p in producten if not p["actief"] and p["voorraad"] > 0]

        per_categorie = {}
        for p in producten:
            c = per_categorie.setdefault(p["categorie"], {"aantal": 0, "waarde": 0.0, "subcats": {}})
            c["aantal"] += 1
            c["waarde"] += p["voorraad"] * p["verkoopprijs"]
            sub = c["subcats"].setdefault(p["subcategorie"], {"aantal": 0, "waarde": 0.0})
            sub["aantal"] += 1
            sub["waarde"] += p["voorraad"] * p["verkoopprijs"]

        def _subcategorie_lijst(info):
            # Alleen tonen als er binnen deze categorie echt subcategorieën in
            # gebruik zijn -- anders levert elke categorie een nietszeggende
            # "Overig 100%"-regel op.
            if not any(naam is not None for naam in info["subcats"]):
                return []
            return sorted(
                [
                    {
                        "naam": naam or "Overig",
                        "aantal": sub_info["aantal"],
                        "waarde": sub_info["waarde"],
                        "percentage": (sub_info["waarde"] / info["waarde"] * 100) if info["waarde"] else 0,
                    }
                    for naam, sub_info in info["subcats"].items()
                ],
                key=lambda x: x["waarde"],
                reverse=True,
            )

        categorie_lijst = sorted(
            [
                {
                    "naam": naam,
                    "aantal": info["aantal"],
                    "waarde": info["waarde"],
                    "percentage": (info["waarde"] / totale_waarde * 100) if totale_waarde else 0,
                    "subcategorieen": _subcategorie_lijst(info),
                }
                for naam, info in per_categorie.items()
            ],
            key=lambda x: x["waarde"],
            reverse=True,
        )

        top_waarde = sorted(
            producten, key=lambda p: p["voorraad"] * p["verkoopprijs"], reverse=True
        )[:10]

        laatste_tellingen = db.execute(
            """SELECT tr.product_id, MAX(t.datum) AS laatste_datum
               FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
               GROUP BY tr.product_id"""
        ).fetchall()
        laatste_per_product = {r["product_id"]: r["laatste_datum"] for r in laatste_tellingen}
        nooit_geteld = [p for p in producten if p["actief"] and p["id"] not in laatste_per_product]
        langst_niet_geteld = sorted(
            (
                {"product": p, "laatste_datum": laatste_per_product[p["id"]]}
                for p in producten
                if p["actief"] and p["id"] in laatste_per_product
            ),
            key=lambda x: x["laatste_datum"],
        )[:5]

        return {
            "producten": producten,
            "totale_waarde": totale_waarde,
            "aantal_producten": len(producten),
            "aantal_categorieen": len(per_categorie),
            "zonder_voorraad": zonder_voorraad,
            "onder_minimum": onder_minimum,
            "zonder_prijs": zonder_prijs,
            "inactief_met_voorraad": inactief_met_voorraad,
            "nooit_geteld": nooit_geteld,
            "categorie_lijst": categorie_lijst,
            "top_waarde": top_waarde,
            "langst_niet_geteld": langst_niet_geteld,
        }

    @app.route("/voorraadoverzicht")
    def voorraadoverzicht():
        db = get_db()
        return render_template(
            "voorraadoverzicht.html", **bereken_voorraadoverzicht(db)
        )

    @app.route("/voorraadoverzicht/pdf")
    def voorraadoverzicht_pdf_route():
        db = get_db()
        gegevens = bereken_voorraadoverzicht(db)
        pdf_bytes = voorraadoverzicht_pdf(gegevens)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=voorraadoverzicht.pdf"},
        )

    @app.route("/voorraadoverzicht/csv")
    def voorraadoverzicht_csv_route():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, subcategorie, naam"
        ).fetchall()
        rijen = [
            (
                p["artikelcode"] or "",
                p["naam"],
                p["categorie"],
                p["subcategorie"] or "",
                p["voorraad"],
                p["eenheid"],
                p["min_voorraad"],
                f"{p['verkoopprijs']:.2f}".replace(".", ","),
                f"{p['voorraad'] * p['verkoopprijs']:.2f}".replace(".", ","),
                "Ja" if p["actief"] else "Nee",
            )
            for p in producten
        ]
        return csv_response(
            "voorraadoverzicht.csv",
            ["Artikelcode", "Naam", "Categorie", "Subcategorie", "Voorraad", "Eenheid",
             "Minimum", "Verkoopprijs", "Waarde", "Actief"],
            rijen,
        )

    # ---------- Producten ----------

    @app.route("/producten")
    def producten_lijst():
        db = get_db()
        # Categorie eerst (voor de groepering hieronder in het sjabloon),
        # daarna actief/subcategorie/naam zoals voorheen -- Jinja's
        # groupby-filter sorteert stabiel op alleen 'categorie', dus deze
        # volgorde blijft binnen elke groep behouden.
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, actief DESC, subcategorie, naam"
        ).fetchall()
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = db.execute(
            "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
        ).fetchall()
        return render_template(
            "producten.html",
            producten=producten,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
            niet_verplicht_categorieen=categorienamen_zonder_verkoopprijsplicht(db),
        )

    @app.route("/producten/minimumvoorraad", methods=["GET", "POST"])
    def producten_minimumvoorraad():
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            aangepast = 0
            for p in producten:
                waarde = request.form.get(f"min_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    nieuw_minimum = int(waarde)
                except ValueError:
                    continue
                if nieuw_minimum < 0:
                    continue
                db.execute(
                    "UPDATE producten SET min_voorraad = ? WHERE id = ?",
                    (nieuw_minimum, p["id"]),
                )
                aangepast += 1
            db.commit()
            flash(f"Minimumvoorraad bijgewerkt voor {aangepast} product(en).", "success")
            return redirect(url_for("producten_minimumvoorraad"))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY actief DESC, categorie, naam"
        ).fetchall()
        return render_template("producten_minimum.html", producten=producten)

    @app.route("/producten/besteleenheid", methods=["GET", "POST"])
    def producten_besteleenheid():
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            aangepast = 0
            for p in producten:
                eenheid_waarde = request.form.get(f"eenheid_{p['id']}", "").strip()
                factor_waarde = request.form.get(f"factor_{p['id']}", "").strip()
                if factor_waarde == "":
                    continue
                try:
                    nieuwe_factor = int(factor_waarde)
                except ValueError:
                    continue
                if nieuwe_factor < 1:
                    continue
                db.execute(
                    "UPDATE producten SET besteleenheid = ?, besteleenheid_factor = ? WHERE id = ?",
                    (eenheid_waarde or None, nieuwe_factor, p["id"]),
                )
                aangepast += 1
            db.commit()
            flash(f"Besteleenheid bijgewerkt voor {aangepast} product(en).", "success")
            return redirect(url_for("producten_besteleenheid"))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY actief DESC, categorie, naam"
        ).fetchall()
        return render_template("producten_besteleenheid.html", producten=producten)

    @app.route("/producten/nieuw", methods=["GET", "POST"])
    def product_nieuw():
        db = get_db()
        if request.method == "POST":
            afbeelding = sla_afbeelding_op(request.files.get("afbeelding"), PRODUCT_AFBEELDINGEN_MAP)
            categorie = request.form["categorie"].strip() or "Overig"
            subcategorie = request.form.get("subcategorie", "").strip() or None
            bewaar_subcategorie(db, categorie, subcategorie)
            nieuwe_voorraad = int(request.form["voorraad"] or 0)
            auto_inactief_bij_nul = 1 if request.form.get("auto_inactief_bij_nul") else 0
            actief = 1 if request.form.get("actief") else 0
            gedwongen_inactief = bool(auto_inactief_bij_nul and nieuwe_voorraad <= 0 and actief)
            if gedwongen_inactief:
                actief = 0
            db.execute(
                """INSERT INTO producten
                   (artikelcode, naam, categorie, subcategorie, eenheid, voorraad, min_voorraad,
                    bestel_hoeveelheid, verkoopprijs, inkoopprijs, actief, besteleenheid,
                    besteleenheid_factor, opmerking, afbeelding, glazen_per_fust, prijs_per_glas,
                    auto_inactief_bij_nul)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.form.get("artikelcode", "").strip() or None,
                    request.form["naam"].strip(),
                    categorie,
                    subcategorie,
                    request.form["eenheid"].strip() or "stuks",
                    nieuwe_voorraad,
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    float(request.form.get("inkoopprijs") or 0),
                    actief,
                    request.form.get("besteleenheid", "").strip() or None,
                    int(request.form.get("besteleenheid_factor") or 1),
                    request.form.get("opmerking", "").strip(),
                    afbeelding,
                    int(request.form.get("glazen_per_fust") or 0),
                    float(request.form.get("prijs_per_glas") or 0),
                    auto_inactief_bij_nul,
                ),
            )
            db.commit()
            flash(f"Product '{request.form['naam']}' toegevoegd.", "success")
            if gedwongen_inactief:
                flash(
                    f"'{request.form['naam']}' is automatisch op inactief gezet (voorraad op 0).",
                    "warning",
                )
            return redirect(url_for("producten_lijst"))
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = [
            dict(r)
            for r in db.execute(
                "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
            ).fetchall()
        ]
        return render_template(
            "product_form.html",
            product=None,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
            voorgestelde_categorie=request.args.get("categorie", "").strip(),
        )

    @app.route("/producten/<int:product_id>/bewerken", methods=["GET", "POST"])
    def product_bewerken(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))

        if request.method == "POST":
            nieuwe_verkoopprijs = float(request.form["verkoopprijs"] or 0)
            nieuwe_inkoopprijs = float(request.form.get("inkoopprijs") or 0)
            nieuwe_afbeelding = sla_afbeelding_op(request.files.get("afbeelding"), PRODUCT_AFBEELDINGEN_MAP)
            if nieuwe_afbeelding:
                afbeelding = nieuwe_afbeelding
            elif request.form.get("afbeelding_verwijderen"):
                afbeelding = None
            else:
                afbeelding = product["afbeelding"]
            datum = now_str()
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            for veld, oude_prijs, nieuwe_prijs in (
                ("verkoopprijs", product["verkoopprijs"], nieuwe_verkoopprijs),
                ("inkoopprijs", product["inkoopprijs"], nieuwe_inkoopprijs),
            ):
                if abs(oude_prijs - nieuwe_prijs) > 0.001:
                    db.execute(
                        """INSERT INTO prijs_geschiedenis
                           (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id),
                    )

            categorie = request.form["categorie"].strip() or "Overig"
            subcategorie = request.form.get("subcategorie", "").strip() or None
            bewaar_subcategorie(db, categorie, subcategorie)
            nieuwe_voorraad = int(request.form["voorraad"] or 0)
            auto_inactief_bij_nul = 1 if request.form.get("auto_inactief_bij_nul") else 0
            actief = 1 if request.form.get("actief") else 0
            gedwongen_inactief = bool(auto_inactief_bij_nul and nieuwe_voorraad <= 0 and actief)
            if gedwongen_inactief:
                actief = 0
            db.execute(
                """UPDATE producten
                   SET artikelcode = ?, naam = ?, categorie = ?, subcategorie = ?, eenheid = ?,
                       voorraad = ?, min_voorraad = ?, bestel_hoeveelheid = ?, verkoopprijs = ?,
                       inkoopprijs = ?, actief = ?, besteleenheid = ?, besteleenheid_factor = ?,
                       opmerking = ?, afbeelding = ?, glazen_per_fust = ?, prijs_per_glas = ?,
                       auto_inactief_bij_nul = ?
                   WHERE id = ?""",
                (
                    request.form.get("artikelcode", "").strip() or None,
                    request.form["naam"].strip(),
                    categorie,
                    subcategorie,
                    request.form["eenheid"].strip() or "stuks",
                    nieuwe_voorraad,
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    nieuwe_verkoopprijs,
                    nieuwe_inkoopprijs,
                    actief,
                    request.form.get("besteleenheid", "").strip() or None,
                    int(request.form.get("besteleenheid_factor") or 1),
                    request.form.get("opmerking", "").strip(),
                    afbeelding,
                    int(request.form.get("glazen_per_fust") or 0),
                    float(request.form.get("prijs_per_glas") or 0),
                    auto_inactief_bij_nul,
                    product_id,
                ),
            )
            db.commit()
            flash(f"Product '{request.form['naam']}' bijgewerkt.", "success")
            if gedwongen_inactief:
                flash(
                    f"'{request.form['naam']}' is automatisch op inactief gezet (voorraad op 0).",
                    "warning",
                )
            return redirect(url_for("producten_lijst"))
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = [
            dict(r)
            for r in db.execute(
                "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
            ).fetchall()
        ]
        prijs_geschiedenis = db.execute(
            """SELECT * FROM prijs_geschiedenis WHERE product_id = ?
               ORDER BY datum DESC, id DESC""",
            (product_id,),
        ).fetchall()
        return render_template(
            "product_form.html",
            product=product,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
            prijs_geschiedenis=prijs_geschiedenis,
        )

    @app.route("/producten/<int:product_id>/verwijderen", methods=["POST"])
    def product_verwijderen(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product:
            db.execute("DELETE FROM producten WHERE id = ?", (product_id,))
            db.commit()
            flash(f"Product '{product['naam']}' verwijderd.", "success")
        return redirect(url_for("producten_lijst"))

    # Endpoints waar het snel-toevoegen-formulier (pop-up) naar mag
    # terugsturen. Whitelist i.p.v. een vrije URL, om open redirects te voorkomen.
    TERUG_NAAR_ENDPOINTS = {
        "levering_inboeken": "levering_inboeken",
        "producten_lijst": "producten_lijst",
    }

    @app.route("/producten/snel-toevoegen", methods=["POST"])
    def product_snel_toevoegen():
        db = get_db()
        terug_naar = TERUG_NAAR_ENDPOINTS.get(
            request.form.get("terug_naar", ""), "producten_lijst"
        )
        naam = request.form.get("naam", "").strip()

        if not naam:
            flash("Naam is verplicht.", "error")
            return redirect(url_for(terug_naar))

        db.execute(
            """INSERT INTO producten
               (artikelcode, naam, categorie, eenheid, voorraad, min_voorraad,
                bestel_hoeveelheid, verkoopprijs, actief, besteleenheid,
                besteleenheid_factor, opmerking)
               VALUES (?, ?, ?, ?, 0, 0, 0, 0, 1, ?, ?, '')""",
            (
                request.form.get("artikelcode", "").strip() or None,
                naam,
                request.form.get("categorie", "").strip() or "Overig",
                request.form.get("eenheid", "").strip() or "stuks",
                request.form.get("besteleenheid", "").strip() or None,
                int(request.form.get("besteleenheid_factor") or 1),
            ),
        )
        db.commit()
        flash(f"Product '{naam}' toegevoegd. Vul hieronder het aantal in.", "success")
        return redirect(url_for(terug_naar))

    @app.route("/producten/<int:product_id>/actief", methods=["POST"])
    def product_actief_wisselen(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Product niet gevonden."}), 404
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        nieuwe_status = 0 if product["actief"] else 1
        db.execute(
            "UPDATE producten SET actief = ? WHERE id = ?", (nieuwe_status, product_id)
        )
        db.commit()
        if is_ajax_verzoek():
            melding = (
                f"'{product['naam']}' is actief. Komt bij de volgende paginalaad weer bovenaan te staan."
                if nieuwe_status
                else f"'{product['naam']}' is inactief. Zakt bij de volgende paginalaad naar onderen."
            )
            return jsonify({"ok": True, "actief": nieuwe_status, "melding": melding})
        return redirect(url_for("producten_lijst"))

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

    @app.route("/categorieen", methods=["GET", "POST"])
    def categorieen_lijst():
        db = get_db()
        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            if not naam:
                flash("Vul een naam in voor de categorie.", "error")
            else:
                bestaat = db.execute(
                    "SELECT id FROM categorieen WHERE naam = ?", (naam,)
                ).fetchone()
                if bestaat:
                    flash(f"Categorie '{naam}' bestaat al.", "error")
                else:
                    db.execute("INSERT INTO categorieen (naam) VALUES (?)", (naam,))
                    db.commit()
                    flash(f"Categorie '{naam}' toegevoegd.", "success")
            return redirect(url_for("categorieen_lijst"))

        categorieen = db.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM producten WHERE categorie = c.naam) AS aantal_producten
               FROM categorieen c ORDER BY c.naam"""
        ).fetchall()
        subcategorieen = db.execute(
            """SELECT s.*, (SELECT COUNT(*) FROM producten
                             WHERE categorie = s.categorie AND subcategorie = s.naam) AS aantal_producten
               FROM subcategorieen s ORDER BY s.categorie, s.naam"""
        ).fetchall()
        subcategorieen_per_categorie = {}
        for s in subcategorieen:
            subcategorieen_per_categorie.setdefault(s["categorie"], []).append(s)
        return render_template(
            "categorieen.html",
            categorieen=categorieen,
            subcategorieen_per_categorie=subcategorieen_per_categorie,
        )

    @app.route("/categorieen/<int:categorie_id>/verwijderen", methods=["POST"])
    def categorie_verwijderen(categorie_id):
        db = get_db()
        categorie = db.execute(
            "SELECT * FROM categorieen WHERE id = ?", (categorie_id,)
        ).fetchone()
        if categorie is None:
            flash("Categorie niet gevonden.", "error")
            return redirect(url_for("categorieen_lijst"))
        in_gebruik = db.execute(
            "SELECT COUNT(*) AS n FROM producten WHERE categorie = ?", (categorie["naam"],)
        ).fetchone()["n"]
        if in_gebruik > 0:
            flash(
                f"Categorie '{categorie['naam']}' is nog in gebruik bij {in_gebruik} "
                "product(en) en kan niet verwijderd worden.",
                "error",
            )
            return redirect(url_for("categorieen_lijst"))
        db.execute("DELETE FROM categorieen WHERE id = ?", (categorie_id,))
        db.execute("DELETE FROM subcategorieen WHERE categorie = ?", (categorie["naam"],))
        db.commit()
        flash(f"Categorie '{categorie['naam']}' verwijderd.", "success")
        return redirect(url_for("categorieen_lijst"))

    @app.route("/categorieen/<int:categorie_id>/verkoopprijs-verplicht", methods=["POST"])
    def categorie_verkoopprijs_verplicht_wisselen(categorie_id):
        db = get_db()
        categorie = db.execute(
            "SELECT * FROM categorieen WHERE id = ?", (categorie_id,)
        ).fetchone()
        if categorie is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Categorie niet gevonden."}), 404
            flash("Categorie niet gevonden.", "error")
            return redirect(url_for("categorieen_lijst"))
        nieuwe_status = 0 if categorie["verkoopprijs_verplicht"] else 1
        db.execute(
            "UPDATE categorieen SET verkoopprijs_verplicht = ? WHERE id = ?",
            (nieuwe_status, categorie_id),
        )
        db.commit()
        if is_ajax_verzoek():
            melding = (
                "Verkoopprijs weer verplicht."
                if nieuwe_status
                else "Verkoopprijs niet meer verplicht voor deze categorie."
            )
            return jsonify({"ok": True, "verkoopprijs_verplicht": nieuwe_status, "melding": melding})
        return redirect(url_for("categorieen_lijst"))

    @app.route("/subcategorieen/nieuw", methods=["POST"])
    def subcategorie_nieuw():
        db = get_db()
        categorie = request.form.get("categorie", "").strip()
        naam = request.form.get("naam", "").strip()
        if not categorie or not naam:
            flash("Vul een categorie en een naam in voor de subcategorie.", "error")
        else:
            bestaat = db.execute(
                "SELECT id FROM subcategorieen WHERE categorie = ? AND naam = ?",
                (categorie, naam),
            ).fetchone()
            if bestaat:
                flash(f"Subcategorie '{naam}' bestaat al binnen '{categorie}'.", "error")
            else:
                db.execute(
                    "INSERT INTO subcategorieen (categorie, naam) VALUES (?, ?)",
                    (categorie, naam),
                )
                db.commit()
                flash(f"Subcategorie '{naam}' toegevoegd aan '{categorie}'.", "success")
        return redirect(url_for("categorieen_lijst"))

    @app.route("/subcategorieen/<int:subcategorie_id>/verwijderen", methods=["POST"])
    def subcategorie_verwijderen(subcategorie_id):
        db = get_db()
        subcategorie = db.execute(
            "SELECT * FROM subcategorieen WHERE id = ?", (subcategorie_id,)
        ).fetchone()
        if subcategorie is None:
            flash("Subcategorie niet gevonden.", "error")
            return redirect(url_for("categorieen_lijst"))
        in_gebruik = db.execute(
            "SELECT COUNT(*) AS n FROM producten WHERE categorie = ? AND subcategorie = ?",
            (subcategorie["categorie"], subcategorie["naam"]),
        ).fetchone()["n"]
        if in_gebruik > 0:
            flash(
                f"Subcategorie '{subcategorie['naam']}' is nog in gebruik bij {in_gebruik} "
                "product(en) en kan niet verwijderd worden.",
                "error",
            )
            return redirect(url_for("categorieen_lijst"))
        db.execute("DELETE FROM subcategorieen WHERE id = ?", (subcategorie_id,))
        db.commit()
        flash(f"Subcategorie '{subcategorie['naam']}' verwijderd.", "success")
        return redirect(url_for("categorieen_lijst"))

