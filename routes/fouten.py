"""Beheer > Foutmeldingen: de serverfouten van de site (zie foutenlog.py)."""

from flask import flash, redirect, render_template, request, url_for

from database import get_db


def register_routes(app):
    @app.route("/fouten")
    def fouten_lijst():
        alles = request.args.get("alles") == "1"
        fouten = get_db().execute(
            f"SELECT * FROM fouten {'' if alles else 'WHERE opgelost = 0'} ORDER BY opgelost, laatste_op DESC LIMIT 100"
        ).fetchall()
        return render_template("fouten.html", fouten=fouten, alles=alles)

    @app.route("/fouten/<int:fout_id>/opgelost", methods=["POST"])
    def fout_opgelost(fout_id):
        db = get_db()
        db.execute("UPDATE fouten SET opgelost = 1 WHERE id = ?", (fout_id,))
        db.commit()
        flash("Gemarkeerd als opgelost. Treedt de fout opnieuw op, dan komt hij terug in de lijst.", "success")
        return redirect(url_for("fouten_lijst"))
