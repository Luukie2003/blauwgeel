"""Categorieen en subcategorieen beheren."""

from flask import flash, jsonify, redirect, render_template, request, url_for

from database import get_db
from helpers import is_ajax_verzoek


def register_routes(app):
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
