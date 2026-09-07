from flask import Response, flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import (
    bereken_voorspelde_tekorten,
    bestel_suggesties,
    naar_besteleenheden,
    naar_voorraadeenheden,
    now_str,
    regels_per_bestelling,
)
from pdf import bestellijst_pdf


def register_routes(app):

    @app.route("/bestellijst")
    def bestellijst():
        db = get_db()

        suggesties = bestel_suggesties(db)

        # Producten die je zelf kunt toevoegen aan de "voorgesteld"-bestelling
        # (bijv. iets dat nog niet krap is, maar toch meebesteld moet worden).
        # Producten die al voorgesteld zijn of al op een openstaande bestelling
        # staan, hoeven hier niet nogmaals in de keuzelijst.
        suggestie_ids = {p["id"] for p in suggesties}
        product_ids_in_open_bestelling = {
            row["product_id"]
            for row in db.execute(
                """SELECT br.product_id FROM bestelregels br
                   JOIN bestellingen b ON b.id = br.bestelling_id
                   WHERE b.status = 'besteld'"""
            ).fetchall()
        }
        overige_producten = [
            p
            for p in db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()
            if p["id"] not in suggestie_ids and p["id"] not in product_ids_in_open_bestelling
        ]

        open_bestellingen = db.execute(
            "SELECT * FROM bestellingen WHERE status = 'besteld' ORDER BY id DESC"
        ).fetchall()
        recent_ontvangen = db.execute(
            """SELECT * FROM bestellingen WHERE status = 'ontvangen'
               ORDER BY id DESC LIMIT 5"""
        ).fetchall()
        regels_per_id = regels_per_bestelling(
            db, [b["id"] for b in open_bestellingen] + [b["id"] for b in recent_ontvangen]
        )
        open_bestellingen_met_regels = [
            (b, regels_per_id.get(b["id"], [])) for b in open_bestellingen
        ]
        recent_ontvangen_met_regels = [
            (b, regels_per_id.get(b["id"], [])) for b in recent_ontvangen
        ]

        return render_template(
            "bestellijst.html",
            suggesties=suggesties,
            overige_producten=overige_producten,
            voorspelde_tekorten=bereken_voorspelde_tekorten(db),
            open_bestellingen=open_bestellingen_met_regels,
            recent_ontvangen=recent_ontvangen_met_regels,
        )

    @app.route("/bestellijst/pdf")
    def bestellijst_pdf_route():
        db = get_db()
        suggesties = bestel_suggesties(db)
        pdf_bytes = bestellijst_pdf(suggesties)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=bestellijst.pdf"},
        )

    @app.route("/bestellijst/aanmaken", methods=["POST"])
    def bestelling_aanmaken():
        db = get_db()
        product_ids = request.form.getlist("product_id")
        besteld_door = session.get("gebruiker_naam")
        besteld_door_id = session.get("gebruiker_id")

        regels = []
        for pid in product_ids:
            aantal_besteleenheden = request.form.get(f"aantal_{pid}", "0")
            try:
                aantal_besteleenheden = int(aantal_besteleenheden)
            except ValueError:
                aantal_besteleenheden = 0
            if aantal_besteleenheden > 0:
                product = db.execute(
                    "SELECT * FROM producten WHERE id = ?", (int(pid),)
                ).fetchone()
                if product is None:
                    continue
                aantal = naar_voorraadeenheden(aantal_besteleenheden, product)
                if aantal > 0:
                    regels.append((int(pid), aantal))

        if not regels:
            flash("Geen producten geselecteerd voor de bestelling.", "error")
            return redirect(url_for("bestellijst"))

        cur = db.execute(
            """INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, besteld_door_id)
               VALUES ('besteld', ?, ?, ?)""",
            (now_str(), besteld_door, besteld_door_id),
        )
        bestelling_id = cur.lastrowid
        for product_id, aantal in regels:
            db.execute(
                """INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld)
                   VALUES (?, ?, ?)""",
                (bestelling_id, product_id, aantal),
            )
        db.commit()
        flash(f"Bestelling aangemaakt met {len(regels)} product(en).", "success")
        return redirect(url_for("bestellijst"))

    @app.route("/bestellijst/nieuw", methods=["GET", "POST"])
    def bestelling_nieuw():
        """Een factuur/bestelling handmatig klaarzetten -- los van de
        automatische lage-voorraad-suggesties. Voor als je al ergens hebt
        besteld (telefonisch, via een website) en dat vast wilt vastleggen,
        om 'm pas te boeken zodra de levering echt binnenkomt."""
        db = get_db()
        if request.method == "POST":
            referentie = request.form.get("referentie", "").strip()
            besteld_door = session.get("gebruiker_naam")
            besteld_door_id = session.get("gebruiker_id")

            producten = db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()
            regels = []
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
                if aantal > 0:
                    regels.append((p["id"], aantal))

            if not regels:
                flash("Geen aantallen ingevuld: er is niets klaargezet.", "error")
                return redirect(url_for("bestelling_nieuw"))

            cur = db.execute(
                """INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, besteld_door_id, referentie)
                   VALUES ('besteld', ?, ?, ?, ?)""",
                (now_str(), besteld_door, besteld_door_id, referentie or None),
            )
            bestelling_id = cur.lastrowid
            for product_id, aantal in regels:
                db.execute(
                    """INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld)
                       VALUES (?, ?, ?)""",
                    (bestelling_id, product_id, aantal),
                )
            db.commit()
            flash(
                f"Bestelling #{bestelling_id} klaargezet met {len(regels)} product(en). "
                "Boek 'm in zodra de levering binnenkomt.",
                "success",
            )
            return redirect(url_for("bestellijst"))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        return render_template("bestelling_nieuw.html", producten=producten)

    @app.route("/bestellingen/<int:bestelling_id>/bewerken", methods=["GET", "POST"])
    def bestelling_bewerken(bestelling_id):
        """Past een al klaargezette bestelling aan -- bijv. na een verkeerde
        klik of gewijzigde aantallen -- zolang hij nog niet is ingeboekt.
        Vervangt de bestelregels net als bij het aanmaken, i.p.v. losse
        regels bij te werken, dat blijft zo het simpelst en het meest
        voorspelbaar."""
        db = get_db()
        bestelling = db.execute(
            "SELECT * FROM bestellingen WHERE id = ?", (bestelling_id,)
        ).fetchone()
        if bestelling is None:
            flash("Bestelling niet gevonden.", "error")
            return redirect(url_for("bestellijst"))
        if bestelling["status"] != "besteld":
            flash("Deze bestelling is al ingeboekt en kan niet meer bewerkt worden.", "error")
            return redirect(url_for("bestellijst"))

        # Ook inactieve producten meenemen als ze al op deze bestelling
        # stonden -- anders verdwijnt die regel stilletjes bij het opslaan.
        producten = db.execute(
            """SELECT * FROM producten
               WHERE actief = 1 OR id IN (SELECT product_id FROM bestelregels WHERE bestelling_id = ?)
               ORDER BY categorie, naam""",
            (bestelling_id,),
        ).fetchall()

        if request.method == "POST":
            referentie = request.form.get("referentie", "").strip()
            regels = []
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
                if aantal > 0:
                    regels.append((p["id"], aantal))

            if not regels:
                flash("Geen aantallen ingevuld: er is niets aangepast.", "error")
                return redirect(url_for("bestelling_bewerken", bestelling_id=bestelling_id))

            db.execute("DELETE FROM bestelregels WHERE bestelling_id = ?", (bestelling_id,))
            for product_id, aantal in regels:
                db.execute(
                    """INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld)
                       VALUES (?, ?, ?)""",
                    (bestelling_id, product_id, aantal),
                )
            db.execute(
                "UPDATE bestellingen SET referentie = ? WHERE id = ?",
                (referentie or None, bestelling_id),
            )
            db.commit()
            flash(f"Bestelling #{bestelling_id} bijgewerkt met {len(regels)} product(en).", "success")
            return redirect(url_for("bestellijst"))

        huidige_regels = db.execute(
            "SELECT product_id, aantal_besteld FROM bestelregels WHERE bestelling_id = ?",
            (bestelling_id,),
        ).fetchall()
        producten_bij_id = {p["id"]: p for p in producten}
        huidige_aantallen = {}
        for regel in huidige_regels:
            product = producten_bij_id.get(regel["product_id"])
            if product is None:
                continue
            huidige_aantallen[regel["product_id"]] = naar_besteleenheden(regel["aantal_besteld"], product)

        return render_template(
            "bestelling_nieuw.html",
            producten=producten,
            bestelling=bestelling,
            huidige_aantallen=huidige_aantallen,
        )

    @app.route("/bestellingen/<int:bestelling_id>/inboeken", methods=["GET", "POST"])
    def bestelling_inboeken(bestelling_id):
        db = get_db()
        bestelling = db.execute(
            "SELECT * FROM bestellingen WHERE id = ?", (bestelling_id,)
        ).fetchone()
        if bestelling is None:
            flash("Bestelling niet gevonden.", "error")
            return redirect(url_for("bestellijst"))

        regels = db.execute(
            """SELECT br.*, p.naam AS product_naam, p.eenheid, p.afbeelding,
                      p.besteleenheid, p.besteleenheid_factor
               FROM bestelregels br JOIN producten p ON p.id = br.product_id
               WHERE br.bestelling_id = ?""",
            (bestelling_id,),
        ).fetchall()

        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            was_al_ontvangen = bestelling["status"] == "ontvangen"
            aantal_manco = 0

            for regel in regels:
                binnen = bool(request.form.get(f"binnen_{regel['id']}"))
                if binnen:
                    aantal_str = request.form.get(f"ontvangen_{regel['id']}", "0")
                    try:
                        aantal_besteleenheden = max(0, int(aantal_str))
                    except ValueError:
                        aantal_besteleenheden = 0
                    aantal_ontvangen = naar_voorraadeenheden(aantal_besteleenheden, regel)
                    manco = 0
                else:
                    aantal_ontvangen = 0
                    manco = 1
                    aantal_manco += 1

                vorige_ontvangen = regel["aantal_ontvangen"] or 0
                delta = aantal_ontvangen - vorige_ontvangen

                db.execute(
                    "UPDATE bestelregels SET aantal_ontvangen = ?, manco = ? WHERE id = ?",
                    (aantal_ontvangen, manco, regel["id"]),
                )
                if delta != 0:
                    db.execute(
                        "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                        (delta, regel["product_id"]),
                    )

                # Mutatie voor deze regel opnieuw opbouwen, zodat de geschiedenis
                # ook na een correctie het actuele ontvangen aantal weerspiegelt.
                db.execute(
                    "DELETE FROM mutaties WHERE bestelling_id = ? AND product_id = ?",
                    (bestelling_id, regel["product_id"]),
                )
                if aantal_ontvangen > 0:
                    db.execute(
                        """INSERT INTO mutaties
                           (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, bestelling_id)
                           VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                        (
                            regel["product_id"],
                            aantal_ontvangen,
                            now_str(),
                            naam,
                            gebruiker_id,
                            "Ontvangen uit bestelling (aangepast)"
                            if was_al_ontvangen
                            else "Ontvangen uit bestelling",
                            bestelling_id,
                        ),
                    )

            # Producten die niet oorspronkelijk besteld waren, maar wel met
            # deze levering zijn meegekomen (bijv. de leverancier stuurde
            # spontaan iets extra's mee, of iets vergeten te bestellen).
            nieuwe_product_ids = request.form.getlist("nieuw_product_id", type=int)
            nieuwe_aantallen = request.form.getlist("nieuw_aantal")
            bestaande_product_ids = {r["product_id"] for r in regels}
            al_toegevoegd = set()
            aantal_extra = 0
            for product_id, waarde in zip(nieuwe_product_ids, nieuwe_aantallen):
                if product_id in bestaande_product_ids or product_id in al_toegevoegd:
                    continue
                al_toegevoegd.add(product_id)
                try:
                    aantal_besteleenheden = max(0, int(waarde))
                except ValueError:
                    aantal_besteleenheden = 0
                if aantal_besteleenheden <= 0:
                    continue
                product = db.execute(
                    "SELECT * FROM producten WHERE id = ?", (product_id,)
                ).fetchone()
                if product is None:
                    continue
                aantal_ontvangen = naar_voorraadeenheden(aantal_besteleenheden, product)

                db.execute(
                    """INSERT INTO bestelregels
                       (bestelling_id, product_id, aantal_besteld, aantal_ontvangen, manco)
                       VALUES (?, ?, 0, ?, 0)""",
                    (bestelling_id, product_id, aantal_ontvangen),
                )
                db.execute(
                    "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                    (aantal_ontvangen, product_id),
                )
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, bestelling_id)
                       VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                    (
                        product_id,
                        aantal_ontvangen,
                        now_str(),
                        naam,
                        gebruiker_id,
                        "Extra meegekomen bij bestelling (niet oorspronkelijk besteld)",
                        bestelling_id,
                    ),
                )
                aantal_extra += 1

            melding_extra = f", {aantal_extra} extra product(en) toegevoegd" if aantal_extra else ""
            melding_manco = f", {aantal_manco} product(en) manco" if aantal_manco else ""
            if was_al_ontvangen:
                db.commit()
                flash(f"Bestelling aangepast en voorraad bijgewerkt{melding_extra}{melding_manco}.", "success")
            else:
                db.execute(
                    "UPDATE bestellingen SET status = 'ontvangen', ontvangen_op = ? WHERE id = ?",
                    (now_str(), bestelling_id),
                )
                db.commit()
                flash(f"Bestelling ingeboekt en voorraad bijgewerkt{melding_extra}{melding_manco}.", "success")
            return redirect(url_for("bestellijst"))

        beschikbare_producten = db.execute(
            """SELECT * FROM producten WHERE actief = 1
               AND id NOT IN (SELECT product_id FROM bestelregels WHERE bestelling_id = ?)
               ORDER BY categorie, naam""",
            (bestelling_id,),
        ).fetchall()

        return render_template(
            "inboeken.html",
            bestelling=bestelling,
            regels=regels,
            beschikbare_producten=beschikbare_producten,
        )

    @app.route("/bestellingen/<int:bestelling_id>/verwijderen", methods=["POST"])
    def bestelling_verwijderen(bestelling_id):
        db = get_db()
        bestelling = db.execute(
            "SELECT * FROM bestellingen WHERE id = ?", (bestelling_id,)
        ).fetchone()
        if bestelling is None:
            flash("Bestelling niet gevonden.", "error")
            return redirect(url_for("bestellijst"))

        regels = db.execute(
            "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling_id,)
        ).fetchall()
        for regel in regels:
            ontvangen = regel["aantal_ontvangen"] or 0
            if ontvangen > 0:
                db.execute(
                    "UPDATE producten SET voorraad = voorraad - ? WHERE id = ?",
                    (ontvangen, regel["product_id"]),
                )

        db.execute("DELETE FROM mutaties WHERE bestelling_id = ?", (bestelling_id,))
        db.execute("DELETE FROM bestellingen WHERE id = ?", (bestelling_id,))
        db.commit()
        flash(f"Bestelling #{bestelling_id} verwijderd.", "success")
        return redirect(url_for("bestellijst"))
