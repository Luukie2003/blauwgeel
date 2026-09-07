"""Losse inkopen buiten de vaste voorraad om (bijv. schoonmaakspullen,
kantoorbenodigdheden) -- niet gekoppeld aan een product uit de
producten-tabel, gewoon een gedeelde lijst om aan te vinken."""

from flask import flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import now_str


def register_routes(app):
    @app.route("/boodschappenlijst", methods=["GET", "POST"])
    def boodschappenlijst():
        db = get_db()
        if request.method == "POST":
            tekst = request.form.get("tekst", "").strip()
            if not tekst:
                flash("Vul in wat je nodig hebt.", "error")
            else:
                db.execute(
                    "INSERT INTO boodschappen (tekst, aangemaakt_door, aangemaakt_op) VALUES (?, ?, ?)",
                    (tekst, session.get("gebruiker_naam"), now_str()),
                )
                db.commit()
                flash(f"'{tekst}' toegevoegd aan de boodschappenlijst.", "success")
            return redirect(url_for("boodschappenlijst"))

        open_items = db.execute(
            "SELECT * FROM boodschappen WHERE afgevinkt = 0 ORDER BY id"
        ).fetchall()
        afgevinkt_items = db.execute(
            "SELECT * FROM boodschappen WHERE afgevinkt = 1 ORDER BY afgevinkt_op DESC LIMIT 30"
        ).fetchall()
        return render_template(
            "boodschappenlijst.html", open_items=open_items, afgevinkt_items=afgevinkt_items
        )

    @app.route("/boodschappenlijst/<int:item_id>/afvinken", methods=["POST"])
    def boodschap_afvinken(item_id):
        db = get_db()
        item = db.execute("SELECT * FROM boodschappen WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            flash("Item niet gevonden.", "error")
            return redirect(url_for("boodschappenlijst"))

        nieuwe_status = 0 if item["afgevinkt"] else 1
        db.execute(
            """UPDATE boodschappen SET afgevinkt = ?, afgevinkt_door = ?, afgevinkt_op = ?
               WHERE id = ?""",
            (
                nieuwe_status,
                session.get("gebruiker_naam") if nieuwe_status else None,
                now_str() if nieuwe_status else None,
                item_id,
            ),
        )
        db.commit()
        return redirect(url_for("boodschappenlijst"))

    @app.route("/boodschappenlijst/<int:item_id>/verwijderen", methods=["POST"])
    def boodschap_verwijderen(item_id):
        db = get_db()
        item = db.execute("SELECT * FROM boodschappen WHERE id = ?", (item_id,)).fetchone()
        if item is not None:
            db.execute("DELETE FROM boodschappen WHERE id = ?", (item_id,))
            db.commit()
            flash(f"'{item['tekst']}' verwijderd van de boodschappenlijst.", "success")
        return redirect(url_for("boodschappenlijst"))
