from datetime import datetime
from pathlib import Path

from flask import Flask, Response, flash, redirect, render_template, request, url_for

from database import get_db, init_db, register_db
from pdf import bestellijst_pdf, verkoop_pdf

BASE_DIR = Path(__file__).parent

NAV_ITEMS = [
    {
        "endpoints": ["dashboard"],
        "url_endpoint": "dashboard",
        "label": "Overzicht",
    },
    {
        "endpoints": ["producten_lijst", "product_nieuw", "product_bewerken"],
        "url_endpoint": "producten_lijst",
        "label": "Producten",
    },
    {
        "endpoints": ["boeken"],
        "url_endpoint": "boeken",
        "label": "In/uit boeken",
    },
    {
        "endpoints": ["tellen", "telling_detail"],
        "url_endpoint": "tellen",
        "label": "Voorraad tellen",
    },
    {
        "endpoints": ["bestellijst", "bestelling_aanmaken", "bestelling_inboeken"],
        "url_endpoint": "bestellijst",
        "label": "Bestellijst",
    },
    {
        "endpoints": ["geschiedenis"],
        "url_endpoint": "geschiedenis",
        "label": "Geschiedenis",
    },
]


def create_app():
    app = Flask(__name__)
    app.config["DATABASE"] = str(BASE_DIR / "voorraad.db")
    app.config["SECRET_KEY"] = "kantine-voorraad-dev-key"

    register_db(app)
    init_db(app)

    app.jinja_env.filters["datum_nl"] = format_datum

    @app.context_processor
    def inject_nav():
        actieve_nav = next(
            (item for item in NAV_ITEMS if request.endpoint in item["endpoints"]),
            None,
        )
        return {"nav_items": NAV_ITEMS, "actieve_nav": actieve_nav}

    register_routes(app)
    return app


def format_datum(value):
    if not value:
        return ""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return dt.strftime("%d-%m-%Y %H:%M")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def register_routes(app):
    @app.route("/")
    def dashboard():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, naam"
        ).fetchall()
        laag = [p for p in producten if p["voorraad"] < p["min_voorraad"]]
        recente_mutaties = db.execute(
            """SELECT m.*, p.naam AS product_naam, p.eenheid
               FROM mutaties m JOIN producten p ON p.id = m.product_id
               ORDER BY m.id DESC LIMIT 8"""
        ).fetchall()
        open_bestellingen = db.execute(
            "SELECT COUNT(*) AS n FROM bestellingen WHERE status = 'besteld'"
        ).fetchone()["n"]
        return render_template(
            "dashboard.html",
            producten=producten,
            laag=laag,
            recente_mutaties=recente_mutaties,
            open_bestellingen=open_bestellingen,
        )

    # ---------- Producten ----------

    @app.route("/producten")
    def producten_lijst():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, naam"
        ).fetchall()
        return render_template("producten.html", producten=producten)

    @app.route("/producten/nieuw", methods=["GET", "POST"])
    def product_nieuw():
        if request.method == "POST":
            db = get_db()
            db.execute(
                """INSERT INTO producten
                   (naam, categorie, eenheid, voorraad, min_voorraad, bestel_hoeveelheid,
                    verkoopprijs, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.form["naam"].strip(),
                    request.form["categorie"].strip() or "Overig",
                    request.form["eenheid"].strip() or "stuks",
                    int(request.form["voorraad"] or 0),
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    request.form.get("opmerking", "").strip(),
                ),
            )
            db.commit()
            flash(f"Product '{request.form['naam']}' toegevoegd.", "success")
            return redirect(url_for("producten_lijst"))
        return render_template("product_form.html", product=None)

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
            db.execute(
                """UPDATE producten
                   SET naam = ?, categorie = ?, eenheid = ?, voorraad = ?,
                       min_voorraad = ?, bestel_hoeveelheid = ?, verkoopprijs = ?,
                       opmerking = ?
                   WHERE id = ?""",
                (
                    request.form["naam"].strip(),
                    request.form["categorie"].strip() or "Overig",
                    request.form["eenheid"].strip() or "stuks",
                    int(request.form["voorraad"] or 0),
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    request.form.get("opmerking", "").strip(),
                    product_id,
                ),
            )
            db.commit()
            flash(f"Product '{request.form['naam']}' bijgewerkt.", "success")
            return redirect(url_for("producten_lijst"))
        return render_template("product_form.html", product=product)

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

    # ---------- In / uit boeken ----------

    @app.route("/boeken", methods=["GET", "POST"])
    def boeken():
        db = get_db()
        if request.method == "POST":
            product_id = int(request.form["product_id"])
            mtype = request.form["type"]
            aantal = int(request.form["aantal"])
            naam = request.form.get("naam", "").strip()
            opmerking = request.form.get("opmerking", "").strip()

            product = db.execute(
                "SELECT * FROM producten WHERE id = ?", (product_id,)
            ).fetchone()

            if product is None or aantal <= 0:
                flash("Ongeldige boeking.", "error")
                return redirect(url_for("boeken"))

            delta = aantal if mtype == "in" else -aantal
            nieuwe_voorraad = product["voorraad"] + delta

            db.execute(
                "UPDATE producten SET voorraad = ? WHERE id = ?",
                (nieuwe_voorraad, product_id),
            )
            db.execute(
                """INSERT INTO mutaties (product_id, type, aantal, datum, naam, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (product_id, mtype, aantal, now_str(), naam, opmerking),
            )
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
            return redirect(url_for("boeken"))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, naam"
        ).fetchall()
        recente_mutaties = db.execute(
            """SELECT m.*, p.naam AS product_naam, p.eenheid
               FROM mutaties m JOIN producten p ON p.id = m.product_id
               ORDER BY m.id DESC LIMIT 15"""
        ).fetchall()
        return render_template(
            "boeken.html", producten=producten, recente_mutaties=recente_mutaties
        )

    # ---------- Voorraad tellen ----------

    @app.route("/tellen", methods=["GET", "POST"])
    def tellen():
        db = get_db()
        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            opmerking = request.form.get("opmerking", "").strip()
            producten = db.execute(
                "SELECT * FROM producten ORDER BY categorie, naam"
            ).fetchall()

            regels = []
            for p in producten:
                waarde = request.form.get(f"geteld_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    geteld = int(waarde)
                except ValueError:
                    continue
                if geteld < 0:
                    continue
                verschil = geteld - p["voorraad"]
                regels.append(
                    {
                        "product": p,
                        "voorraad_voor": p["voorraad"],
                        "geteld": geteld,
                        "verkocht": max(0, -verschil),
                        "correctie": max(0, verschil),
                    }
                )

            if not regels:
                flash("Geen aantallen ingevuld -- er is niets geteld.", "error")
                return redirect(url_for("tellen"))

            cur = db.execute(
                "INSERT INTO tellingen (datum, naam, opmerking) VALUES (?, ?, ?)",
                (now_str(), naam, opmerking),
            )
            telling_id = cur.lastrowid

            for r in regels:
                db.execute(
                    """INSERT INTO telling_regels
                       (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        telling_id,
                        r["product"]["id"],
                        r["voorraad_voor"],
                        r["geteld"],
                        r["verkocht"],
                        r["correctie"],
                    ),
                )
                db.execute(
                    "UPDATE producten SET voorraad = ? WHERE id = ?",
                    (r["geteld"], r["product"]["id"]),
                )
                if r["verkocht"] > 0:
                    db.execute(
                        """INSERT INTO mutaties
                           (product_id, type, aantal, datum, naam, opmerking, telling_id)
                           VALUES (?, 'uit', ?, ?, ?, ?, ?)""",
                        (
                            r["product"]["id"],
                            r["verkocht"],
                            now_str(),
                            naam,
                            f"Verkocht (telling #{telling_id})",
                            telling_id,
                        ),
                    )
                elif r["correctie"] > 0:
                    db.execute(
                        """INSERT INTO mutaties
                           (product_id, type, aantal, datum, naam, opmerking, telling_id)
                           VALUES (?, 'in', ?, ?, ?, ?, ?)""",
                        (
                            r["product"]["id"],
                            r["correctie"],
                            now_str(),
                            naam,
                            f"Correctie (telling #{telling_id})",
                            telling_id,
                        ),
                    )

            db.commit()
            flash(
                f"Telling #{telling_id} verwerkt: {len(regels)} product(en) geteld.",
                "success",
            )
            return redirect(url_for("telling_detail", telling_id=telling_id))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, naam"
        ).fetchall()
        tellingen = db.execute(
            "SELECT * FROM tellingen ORDER BY id DESC LIMIT 15"
        ).fetchall()
        return render_template("tellen.html", producten=producten, tellingen=tellingen)

    @app.route("/tellingen/<int:telling_id>")
    def telling_detail(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Telling niet gevonden.", "error")
            return redirect(url_for("tellen"))

        regels = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid, p.verkoopprijs
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        totaal_omzet = sum(r["verkocht"] * r["verkoopprijs"] for r in regels)

        return render_template(
            "telling_detail.html",
            telling=telling,
            regels=regels,
            totaal_omzet=totaal_omzet,
        )

    @app.route("/tellingen/<int:telling_id>/pdf")
    def telling_pdf(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Telling niet gevonden.", "error")
            return redirect(url_for("tellen"))

        regels = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid, p.verkoopprijs
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        vorige_telling = db.execute(
            "SELECT * FROM tellingen WHERE id < ? ORDER BY id DESC LIMIT 1",
            (telling_id,),
        ).fetchone()

        van = format_datum(vorige_telling["datum"]) if vorige_telling else "eerste telling"
        periode_tekst = f"Periode: {van}  t/m  {format_datum(telling['datum'])}"
        pdf_bytes = verkoop_pdf(telling_id, periode_tekst, regels)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-telling-{telling_id}.pdf"
            },
        )

    # ---------- Bestellijst ----------

    def bestel_suggesties(db):
        product_ids_in_open_bestelling = {
            row["product_id"]
            for row in db.execute(
                """SELECT br.product_id FROM bestelregels br
                   JOIN bestellingen b ON b.id = br.bestelling_id
                   WHERE b.status = 'besteld'"""
            ).fetchall()
        }
        return [
            p
            for p in db.execute(
                "SELECT * FROM producten WHERE voorraad < min_voorraad ORDER BY categorie, naam"
            ).fetchall()
            if p["id"] not in product_ids_in_open_bestelling
        ]

    @app.route("/bestellijst")
    def bestellijst():
        db = get_db()

        suggesties = bestel_suggesties(db)

        open_bestellingen = db.execute(
            "SELECT * FROM bestellingen WHERE status = 'besteld' ORDER BY id DESC"
        ).fetchall()
        open_bestellingen_met_regels = []
        for b in open_bestellingen:
            regels = db.execute(
                """SELECT br.*, p.naam AS product_naam, p.eenheid
                   FROM bestelregels br JOIN producten p ON p.id = br.product_id
                   WHERE br.bestelling_id = ?""",
                (b["id"],),
            ).fetchall()
            open_bestellingen_met_regels.append((b, regels))

        recent_ontvangen = db.execute(
            """SELECT * FROM bestellingen WHERE status = 'ontvangen'
               ORDER BY id DESC LIMIT 5"""
        ).fetchall()

        return render_template(
            "bestellijst.html",
            suggesties=suggesties,
            open_bestellingen=open_bestellingen_met_regels,
            recent_ontvangen=recent_ontvangen,
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
        besteld_door = request.form.get("besteld_door", "").strip()

        regels = []
        for pid in product_ids:
            aantal = request.form.get(f"aantal_{pid}", "0")
            try:
                aantal = int(aantal)
            except ValueError:
                aantal = 0
            if aantal > 0:
                regels.append((int(pid), aantal))

        if not regels:
            flash("Geen producten geselecteerd voor de bestelling.", "error")
            return redirect(url_for("bestellijst"))

        cur = db.execute(
            """INSERT INTO bestellingen (status, aangemaakt_op, besteld_door)
               VALUES ('besteld', ?, ?)""",
            (now_str(), besteld_door),
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
            """SELECT br.*, p.naam AS product_naam, p.eenheid
               FROM bestelregels br JOIN producten p ON p.id = br.product_id
               WHERE br.bestelling_id = ?""",
            (bestelling_id,),
        ).fetchall()

        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            for regel in regels:
                aantal_str = request.form.get(f"ontvangen_{regel['id']}", "0")
                try:
                    aantal_ontvangen = int(aantal_str)
                except ValueError:
                    aantal_ontvangen = 0

                db.execute(
                    "UPDATE bestelregels SET aantal_ontvangen = ? WHERE id = ?",
                    (aantal_ontvangen, regel["id"]),
                )

                if aantal_ontvangen > 0:
                    db.execute(
                        "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                        (aantal_ontvangen, regel["product_id"]),
                    )
                    db.execute(
                        """INSERT INTO mutaties
                           (product_id, type, aantal, datum, naam, opmerking, bestelling_id)
                           VALUES (?, 'in', ?, ?, ?, ?, ?)""",
                        (
                            regel["product_id"],
                            aantal_ontvangen,
                            now_str(),
                            naam,
                            "Ontvangen uit bestelling",
                            bestelling_id,
                        ),
                    )

            db.execute(
                "UPDATE bestellingen SET status = 'ontvangen', ontvangen_op = ? WHERE id = ?",
                (now_str(), bestelling_id),
            )
            db.commit()
            flash("Bestelling ingeboekt en voorraad bijgewerkt.", "success")
            return redirect(url_for("bestellijst"))

        return render_template(
            "inboeken.html", bestelling=bestelling, regels=regels
        )

    # ---------- Geschiedenis ----------

    @app.route("/geschiedenis")
    def geschiedenis():
        db = get_db()
        product_id = request.args.get("product_id", type=int)

        query = """SELECT m.*, p.naam AS product_naam, p.eenheid
                    FROM mutaties m JOIN producten p ON p.id = m.product_id"""
        params = ()
        if product_id:
            query += " WHERE m.product_id = ?"
            params = (product_id,)
        query += " ORDER BY m.id DESC LIMIT 300"

        mutaties = db.execute(query, params).fetchall()
        producten = db.execute("SELECT id, naam FROM producten ORDER BY naam").fetchall()
        return render_template(
            "geschiedenis.html",
            mutaties=mutaties,
            producten=producten,
            gekozen_product_id=product_id,
        )


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5050)
