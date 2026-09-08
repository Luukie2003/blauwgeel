from flask import flash, redirect, render_template, request, session, url_for

import mail
from database import get_db
from helpers import (
    besteleenheid_naam,
    format_datum,
    naar_voorraadeenheden,
    now_datetime_local,
    now_str,
    verwerk_auto_inactief,
)


def register_routes(app):
    @app.route("/boeken", methods=["GET", "POST"])
    def boeken():
        db = get_db()
        if request.method == "POST":
            product_id = int(request.form["product_id"])
            mtype = request.form["type"]
            aantal = int(request.form["aantal"])
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            opmerking = request.form.get("opmerking", "").strip()
            terug_naar_product = request.form.get("terug_naar_product", type=int)
            volgende = (
                url_for("product_detail", product_id=terug_naar_product)
                if terug_naar_product
                else url_for("boeken")
            )

            product = db.execute(
                "SELECT * FROM producten WHERE id = ?", (product_id,)
            ).fetchone()

            if product is None or aantal <= 0:
                flash("Ongeldige boeking.", "error")
                return redirect(volgende)

            delta = aantal if mtype == "in" else -aantal
            nieuwe_voorraad = product["voorraad"] + delta

            db.execute(
                "UPDATE producten SET voorraad = ? WHERE id = ?",
                (nieuwe_voorraad, product_id),
            )
            db.execute(
                """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_id, mtype, aantal, now_str(), naam, gebruiker_id, opmerking),
            )
            gedeactiveerd = verwerk_auto_inactief(db, product_id, nieuwe_voorraad)
            db.commit()

            if nieuwe_voorraad < 0:
                flash(
                    f"'{product['naam']}' geboekt, maar de voorraad staat nu op "
                    f"{nieuwe_voorraad}. Controleer de telling.",
                    "warning",
                )
            else:
                werkwoord = "bijgeboekt bij" if mtype == "in" else "afgeboekt van"
                flash(f"{aantal} {werkwoord} '{product['naam']}'.", "success")
            if gedeactiveerd:
                flash(f"'{gedeactiveerd}' is automatisch op inactief gezet (voorraad op 0).", "warning")
            return redirect(volgende)

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        recente_mutaties = db.execute(
            """SELECT m.*, p.naam AS product_naam, p.eenheid
               FROM mutaties m JOIN producten p ON p.id = m.product_id
               ORDER BY m.id DESC LIMIT 15"""
        ).fetchall()
        return render_template(
            "boeken.html", producten=producten, recente_mutaties=recente_mutaties
        )

    @app.route("/leveringen/inboeken", methods=["GET", "POST"])
    def levering_inboeken():
        db = get_db()
        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            referentie = request.form.get("referentie", "").strip()
            datum_input = request.form.get("datum", "").strip()
            datum = datum_input.replace("T", " ") if datum_input else now_str()
            opmerking = (
                f"Levering ingeboekt ({referentie})" if referentie else "Levering ingeboekt"
            )

            producten = db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()

            geboekte_regels = []
            for p in producten:
                waarde = request.form.get(f"aantal_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    aantal_besteleenheden = int(waarde)
                except ValueError:
                    continue
                if aantal_besteleenheden <= 0:
                    continue
                aantal = naar_voorraadeenheden(aantal_besteleenheden, p)
                db.execute(
                    "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                    (aantal, p["id"]),
                )
                db.execute(
                    """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                       VALUES (?, 'in', ?, ?, ?, ?, ?)""",
                    (p["id"], aantal, datum, naam, gebruiker_id, opmerking),
                )
                verwerk_auto_inactief(db, p["id"], p["voorraad"] + aantal)
                geboekte_regels.append((p, aantal, aantal_besteleenheden))

            if not geboekte_regels:
                flash("Geen aantallen ingevuld: er is niets ingeboekt.", "error")
                return redirect(url_for("levering_inboeken"))

            db.commit()
            flash(
                f"Levering ingeboekt: {len(geboekte_regels)} product(en) bijgewerkt.",
                "success",
            )

            regels_tekst = "\n".join(
                f"  - {p['naam']}: +{aantal_be} {besteleenheid_naam(p)} (= {aantal} {p['eenheid']})"
                for p, aantal, aantal_be in geboekte_regels
            )
            ontvangers = [
                r["email"]
                for r in db.execute(
                    """SELECT email FROM gebruikers
                       WHERE mail_factuur = 1 AND email IS NOT NULL AND email != ''"""
                ).fetchall()
            ]
            if not ontvangers:
                instelling = db.execute(
                    "SELECT notificatie_email FROM instellingen WHERE id = 1"
                ).fetchone()
                if instelling and instelling["notificatie_email"]:
                    ontvangers = [instelling["notificatie_email"]]

            onderwerp = f"Levering ingeboekt{f' ({referentie})' if referentie else ''}"
            tekst = (
                f"Er is een levering ingeboekt in het voorraadsysteem.\n\n"
                f"Datum: {format_datum(datum)}\n"
                f"Door: {naam or 'onbekend'}\n"
                f"Referentie: {referentie or '-'}\n\n"
                f"Producten:\n{regels_tekst}"
            )
            for ontvanger in ontvangers:
                mail.stuur_mail(onderwerp, tekst, naar=ontvanger)

            return redirect(url_for("boeken"))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        return render_template(
            "levering_inboeken.html",
            producten=producten,
            categorieen=categorieen,
            nu_datetime_local=now_datetime_local(),
        )

    # ---------- Voorraad tellen ----------
