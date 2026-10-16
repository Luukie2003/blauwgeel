"""Producten aanmaken, bewerken en verwijderen."""

import sqlite3

from flask import flash, redirect, render_template, request, session, url_for

import barcodes
from database import get_db
from productinfo import HANDMATIG_AANGEPAST
from productkaart import BESTELEENHEDEN, EENHEDEN, artikelcode_in_gebruik, eenheid_uit_formulier
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


def _productkaart_velden(db, product_id=None, huidige_code=None):
    """Eenheid, besteleenheid, merk, 'Niet tellen' en de artikelcode uit het formulier. Is de artikelcode al van een
    ander product, dan blijft de oude staan (bij een nieuw product: geen) en komt er een melding."""
    artikelcode = request.form.get("artikelcode", "").strip() or None
    ander = artikelcode_in_gebruik(db, artikelcode, product_id)
    if ander:
        flash(
            f"Artikelcode {artikelcode} hoort al bij '{ander}'. "
            + ("De oude artikelcode is blijven staan." if product_id else "Het product is zonder artikelcode opgeslagen."),
            "warning",
        )
        artikelcode = huidige_code
    return {
        "artikelcode": artikelcode,
        "eenheid": eenheid_uit_formulier(request.form, "eenheid", EENHEDEN) or "Stuks",
        "besteleenheid": eenheid_uit_formulier(request.form, "besteleenheid", BESTELEENHEDEN) or None,
        "merk": " ".join(request.form.get("merk", "").split()) or None,
        "niet_tellen": 1 if request.form.get("niet_tellen") else 0,
        "leverancier_id": _leverancier_uit_formulier(db),
    }


def _leverancier_uit_formulier(db):
    waarde = request.form.get("leverancier_id", "")
    if not waarde.isdigit():
        return None
    return int(waarde) if db.execute("SELECT 1 FROM leveranciers WHERE id = ?", (int(waarde),)).fetchone() else None


def _keuzelijsten(db):
    """Wat de productkaart nodig heeft voor de keuzelijsten van eenheid, besteleenheid en merk."""
    return {
        "eenheden": EENHEDEN,
        "besteleenheden": BESTELEENHEDEN,
        "leveranciers": db.execute("SELECT id, naam, actief FROM leveranciers ORDER BY actief DESC, naam COLLATE NOCASE").fetchall(),
        "merken": [
            r["merk"]
            for r in db.execute(
                "SELECT DISTINCT merk FROM producten WHERE merk IS NOT NULL AND merk != '' ORDER BY merk COLLATE NOCASE"
            ).fetchall()
        ],
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
            kaart = _productkaart_velden(db)
            nieuw_id = db.execute(
                """INSERT INTO producten
                   (artikelcode, naam, categorie, subcategorie, eenheid, voorraad, min_voorraad,
                    bestel_hoeveelheid, verkoopprijs, inkoopprijs, actief, besteleenheid,
                    besteleenheid_factor, opmerking, afbeelding, glazen_per_fust, prijs_per_glas,
                    auto_inactief_bij_nul, toon_op_kiosk, kiosk_uitverkocht, kiosk_categorie, merk, niet_tellen,
                    leverancier_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    kaart["artikelcode"],
                    request.form["naam"].strip(),
                    categorie,
                    subcategorie,
                    kaart["eenheid"],
                    nieuwe_voorraad,
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    float(request.form.get("inkoopprijs") or 0),
                    actief,
                    kaart["besteleenheid"],
                    int(request.form.get("besteleenheid_factor") or 1),
                    request.form.get("opmerking", "").strip(),
                    afbeelding,
                    int(request.form.get("glazen_per_fust") or 0),
                    float(request.form.get("prijs_per_glas") or 0),
                    auto_inactief_bij_nul,
                    1 if request.form.get("toon_op_kiosk") else 0,
                    1 if request.form.get("kiosk_uitverkocht") else 0,
                    request.form.get("kiosk_categorie", "").strip() or None,
                    kaart["merk"],
                    kaart["niet_tellen"],
                    kaart["leverancier_id"],
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
            **_keuzelijsten(db),
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

        # Met artikelen met een inkoopprijs (Barcodes) rekent de site de inkoopprijs zelf uit; dan telt het veld niet.
        inkoop_artikelen = barcodes.inkoop_uit_artikelen(db, product_id)
        if request.method == "POST":
            nieuwe_verkoopprijs = float(request.form["verkoopprijs"] or 0)
            nieuwe_inkoopprijs = (
                product["inkoopprijs"] if inkoop_artikelen else float(request.form.get("inkoopprijs") or 0)
            )
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
            kaart = _productkaart_velden(db, product_id, product["artikelcode"])
            db.execute(
                """UPDATE producten
                   SET artikelcode = ?, naam = ?, categorie = ?, subcategorie = ?, eenheid = ?,
                       voorraad = ?, min_voorraad = ?, bestel_hoeveelheid = ?, verkoopprijs = ?,
                       inkoopprijs = ?, actief = ?, besteleenheid = ?, besteleenheid_factor = ?,
                       opmerking = ?, afbeelding = ?, glazen_per_fust = ?, prijs_per_glas = ?,
                       auto_inactief_bij_nul = ?, toon_op_kiosk = ?, kiosk_uitverkocht = ?,
                       kiosk_categorie = ?, merk = ?, niet_tellen = ?, leverancier_id = ?
                   WHERE id = ?""",
                (
                    kaart["artikelcode"],
                    request.form["naam"].strip(),
                    categorie,
                    subcategorie,
                    kaart["eenheid"],
                    nieuwe_voorraad,
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    nieuwe_verkoopprijs,
                    nieuwe_inkoopprijs,
                    actief,
                    kaart["besteleenheid"],
                    int(request.form.get("besteleenheid_factor") or 1),
                    request.form.get("opmerking", "").strip(),
                    afbeelding,
                    int(request.form.get("glazen_per_fust") or 0),
                    float(request.form.get("prijs_per_glas") or 0),
                    auto_inactief_bij_nul,
                    1 if request.form.get("toon_op_kiosk") else 0,
                    1 if request.form.get("kiosk_uitverkocht") else 0,
                    request.form.get("kiosk_categorie", "").strip() or None,
                    kaart["merk"],
                    kaart["niet_tellen"],
                    kaart["leverancier_id"],
                    product_id,
                ),
            )
            vervang_product_prijsopties(db, product_id)
            barcodes.werk_inkoopprijs_bij(db, product_id, naam, gebruiker_id)  # een andere besteleenheid telt mee
            # Een andere voorraad hier is een boeking zonder formulier: leg 'm vast, anders is later niet na te gaan
            # waar het verschil vandaan komt.
            verschil = nieuwe_voorraad - product["voorraad"]
            if verschil:
                db.execute(
                    """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (product_id, "in" if verschil > 0 else "uit", abs(verschil), datum, naam, gebruiker_id,
                     f"{HANDMATIG_AANGEPAST} ({product['voorraad']} → {nieuwe_voorraad})"),
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
            artikelen=barcodes.artikelen_van(db, product_id),
            inkoop_artikelen=inkoop_artikelen,
            per_eenheid=barcodes.per_eenheid,
            **_keuzelijsten(db),
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
                if product["actief"]:
                    tekst = (
                        "Zet het op inactief: dan staat het nergens meer (bestellijst, tellen, tv, productlijst) en "
                        "blijft de geschiedenis kloppen."
                    )
                else:
                    tekst = (
                        "Het staat al op inactief, dus het telt nergens meer mee en staat niet meer in de productlijst "
                        "(alleen als je 'Inactieve tonen' aanvinkt)."
                    )
                flash(
                    f"'{product['naam']}' kan niet verwijderd worden, want het staat in oude tellingen of bestellingen "
                    f"en die moeten blijven kloppen. {tekst}",
                    "error",
                )
        return redirect(url_for("producten_lijst"))

    # ---------- Archiveren: een oud product dat niet weg kan uit alle lijsten halen (zie productkaart.NIET_GEARCHIVEERD) ----------

    def _archiveer(db, product_ids):
        """Zet de producten op inactief en gearchiveerd; geeft de producten die dat werden."""
        producten = db.execute(
            f"SELECT id, naam, voorraad, eenheid FROM producten WHERE gearchiveerd = 0 AND id IN ({','.join('?' * len(product_ids))})",
            product_ids,
        ).fetchall() if product_ids else []
        for p in producten:
            db.execute(
                "UPDATE producten SET actief = 0, gearchiveerd = 1, gearchiveerd_op = ? WHERE id = ?", (now_str(), p["id"])
            )
        db.commit()
        return producten

    @app.route("/producten/<int:product_id>/archiveren", methods=["POST"])
    def product_archiveren(product_id):
        db = get_db()
        gedaan = _archiveer(db, [product_id])
        if gedaan:
            p = gedaan[0]
            flash(
                f"'{p['naam']}' is gearchiveerd: het staat in geen enkele lijst meer, maar de tellingen en rapporten van "
                "toen blijven kloppen. Terugzetten kan onder Producten > Gearchiveerd."
                + (f" Let op: er stond nog {p['voorraad']} {p['eenheid']} op voorraad." if p["voorraad"] > 0 else ""),
                "success",
            )
        return redirect(url_for("producten_lijst"))

    @app.route("/producten/archiveren", methods=["POST"])
    def producten_archiveren():
        """De selectie op de productpagina archiveren. Alleen producten die al inactief zijn: een actief product
        archiveer je bewust, los bij het product zelf."""
        db = get_db()
        ids = [int(i) for i in request.form.get("ids", "").split(",") if i.strip().isdigit()]
        inactief = [
            r["id"]
            for r in db.execute(
                f"SELECT id FROM producten WHERE actief = 0 AND id IN ({','.join('?' * len(ids))})", ids
            ).fetchall()
        ] if ids else []
        gedaan = _archiveer(db, inactief)
        overgeslagen = len(ids) - len(inactief)
        if gedaan:
            flash(f"{len(gedaan)} {'product' if len(gedaan) == 1 else 'producten'} gearchiveerd.", "success")
        if overgeslagen:
            flash(
                f"{overgeslagen} {'product is' if overgeslagen == 1 else 'producten zijn'} niet gearchiveerd, want "
                f"{'het staat' if overgeslagen == 1 else 'ze staan'} nog op actief. Zet ze eerst op inactief, of "
                "archiveer ze los bij het product.",
                "warning",
            )
        if not ids:
            flash("Selecteer eerst de producten die je wilt archiveren.", "error")
        return redirect(url_for("producten_lijst"))

    @app.route("/producten/gearchiveerd")
    def producten_gearchiveerd():
        producten = get_db().execute(
            "SELECT * FROM producten WHERE gearchiveerd = 1 ORDER BY categorie, naam COLLATE NOCASE"
        ).fetchall()
        return render_template("producten_gearchiveerd.html", producten=producten)

    @app.route("/producten/<int:product_id>/terugzetten", methods=["POST"])
    def product_terugzetten(product_id):
        """Terug uit het archief; het blijft inactief tot je het zelf weer aanzet."""
        db = get_db()
        product = db.execute("SELECT naam FROM producten WHERE id = ?", (product_id,)).fetchone()
        db.execute("UPDATE producten SET gearchiveerd = 0, gearchiveerd_op = NULL WHERE id = ?", (product_id,))
        db.commit()
        if product:
            flash(f"'{product['naam']}' staat weer in de productlijst, als inactief product.", "success")
        return redirect(url_for("producten_gearchiveerd"))

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
