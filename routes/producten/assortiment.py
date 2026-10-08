"""Producten aanmaken, bewerken en verwijderen."""

import sqlite3

from flask import flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import (
    PRODUCT_AFBEELDINGEN_MAP,
    bewaar_subcategorie,
    now_str,
    sla_afbeelding_op,
    vervang_product_prijsopties,
)


# Endpoints waar het snel-toevoegen-formulier (pop-up) naar mag
# terugsturen. Whitelist i.p.v. een vrije URL, om open redirects te voorkomen.
TERUG_NAAR_ENDPOINTS = {
    "levering_inboeken": "levering_inboeken",
    "producten_lijst": "producten_lijst",
}


def register_routes(app):
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
            nieuw_id = db.execute(
                """INSERT INTO producten
                   (artikelcode, naam, categorie, subcategorie, eenheid, voorraad, min_voorraad,
                    bestel_hoeveelheid, verkoopprijs, inkoopprijs, actief, besteleenheid,
                    besteleenheid_factor, opmerking, afbeelding, glazen_per_fust, prijs_per_glas,
                    auto_inactief_bij_nul, toon_op_kiosk, kiosk_uitverkocht, kiosk_categorie)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    1 if request.form.get("toon_op_kiosk") else 0,
                    1 if request.form.get("kiosk_uitverkocht") else 0,
                    request.form.get("kiosk_categorie", "").strip() or None,
                ),
            ).lastrowid
            vervang_product_prijsopties(db, nieuw_id)
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
            prijsopties=[],
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
                       auto_inactief_bij_nul = ?, toon_op_kiosk = ?, kiosk_uitverkocht = ?,
                       kiosk_categorie = ?
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
                    1 if request.form.get("toon_op_kiosk") else 0,
                    1 if request.form.get("kiosk_uitverkocht") else 0,
                    request.form.get("kiosk_categorie", "").strip() or None,
                    product_id,
                ),
            )
            vervang_product_prijsopties(db, product_id)
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
        prijsopties = db.execute(
            "SELECT * FROM product_prijsopties WHERE product_id = ? ORDER BY volgorde, id",
            (product_id,),
        ).fetchall()
        return render_template(
            "product_form.html",
            product=product,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
            prijs_geschiedenis=prijs_geschiedenis,
            prijsopties=prijsopties,
        )

    @app.route("/producten/<int:product_id>/verwijderen", methods=["POST"])
    def product_verwijderen(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product:
            try:
                db.execute("DELETE FROM producten WHERE id = ?", (product_id,))
                db.commit()
                flash(f"Product '{product['naam']}' verwijderd.", "success")
            except sqlite3.IntegrityError:
                # Product staat nog in bestellingen en/of tellingen
                # (bestelregels/telling_regels hebben bewust geen ON DELETE
                # CASCADE, om die geschiedenis nooit stilzwijgend te laten
                # verdwijnen) -- i.p.v. een 500 gewoon vragen om het product
                # op inactief te zetten, dat verbergt 'm net zo goed overal
                # (bestellijst, tellen, kiosk) zonder de geschiedenis kwijt
                # te raken.
                db.rollback()
                flash(
                    f"'{product['naam']}' kan niet verwijderd worden: het staat nog in "
                    "bestellingen en/of tellingen. Zet het product op inactief in plaats "
                    "van te verwijderen -- dat verbergt 'm net zo goed.",
                    "error",
                )
        return redirect(url_for("producten_lijst"))

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
