"""Projecten: waar het geld heen gaat."""

from flask import flash, jsonify, redirect, render_template, request, url_for

from club_van_20 import PROJECT_STATUS_LABELS, financien
from database import get_db
from helpers import (
    KIOSK_AFBEELDINGEN_MAP,
    is_ajax_verzoek,
    now_str,
    sla_afbeelding_op,
    vandaag_amsterdam,
)
from routes.club_van_20.gedeeld import _bedrag, _getal, _instellingen


# ---------- Projecten ----------

def _project_uit_formulier():
    naam = (request.form.get("naam") or "").strip()
    status = request.form.get("status") or "gepland"
    return {
        "naam": naam,
        "omschrijving": (request.form.get("omschrijving") or "").strip() or None,
        "raming": _bedrag(request.form.get("raming")) or 0,
        "kosten": _bedrag(request.form.get("kosten")),
        "status": status if status in PROJECT_STATUS_LABELS else "gepland",
        "volgorde": _getal("volgorde", 0),
        "toon_op_scherm": 1 if request.form.get("toon_op_scherm") else 0,
    }


def register_routes(app):
    @app.route("/club-van-20/projecten", methods=["GET", "POST"])
    def club_van_20_projecten():
        db = get_db()
        if request.method == "POST":
            p = _project_uit_formulier()
            if not p["naam"]:
                flash("Vul een naam in voor het project.", "error")
            else:
                if "volgorde" not in request.form or not request.form.get("volgorde"):
                    p["volgorde"] = (
                        db.execute("SELECT COALESCE(MAX(volgorde), 0) + 1 AS n FROM club_van_20_projecten").fetchone()["n"]
                    )
                db.execute(
                    """INSERT INTO club_van_20_projecten
                           (naam, omschrijving, raming, kosten, status, volgorde, toon_op_scherm,
                            afgerond_op, afbeelding, aangemaakt_op)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        p["naam"],
                        p["omschrijving"],
                        p["raming"],
                        p["kosten"],
                        p["status"],
                        p["volgorde"],
                        1,
                        vandaag_amsterdam().isoformat() if p["status"] == "klaar" else None,
                        sla_afbeelding_op(request.files.get("afbeelding"), KIOSK_AFBEELDINGEN_MAP),
                        now_str(),
                    ),
                )
                db.commit()
                flash(f"Project '{p['naam']}' toegevoegd.", "success")
            return redirect(url_for("club_van_20_projecten"))
        instellingen = _instellingen(db)
        return render_template(
            "club_van_20_projecten.html",
            geld=financien(db, instellingen["club_van_20_bedrag"]),
            project_statussen=PROJECT_STATUS_LABELS,
        )

    @app.route("/club-van-20/projecten/<int:project_id>", methods=["GET", "POST"])
    def club_van_20_project_bewerken(project_id):
        db = get_db()
        project = db.execute("SELECT * FROM club_van_20_projecten WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            flash("Project niet gevonden.", "error")
            return redirect(url_for("club_van_20_projecten"))
        if request.method == "POST":
            p = _project_uit_formulier()
            if not p["naam"]:
                flash("Vul een naam in voor het project.", "error")
            else:
                afbeelding = sla_afbeelding_op(request.files.get("afbeelding"), KIOSK_AFBEELDINGEN_MAP)
                if request.form.get("afbeelding_verwijderen"):
                    afbeelding_waarde = None
                else:
                    afbeelding_waarde = afbeelding or project["afbeelding"]
                afgerond_op = project["afgerond_op"]
                if p["status"] == "klaar" and not afgerond_op:
                    afgerond_op = vandaag_amsterdam().isoformat()
                elif p["status"] != "klaar":
                    afgerond_op = None
                db.execute(
                    """UPDATE club_van_20_projecten
                       SET naam = ?, omschrijving = ?, raming = ?, kosten = ?, status = ?,
                           volgorde = ?, toon_op_scherm = ?, afbeelding = ?, afgerond_op = ?
                       WHERE id = ?""",
                    (
                        p["naam"],
                        p["omschrijving"],
                        p["raming"],
                        p["kosten"],
                        p["status"],
                        p["volgorde"],
                        p["toon_op_scherm"],
                        afbeelding_waarde,
                        afgerond_op,
                        project_id,
                    ),
                )
                db.commit()
                flash(f"Project '{p['naam']}' opgeslagen.", "success")
                return redirect(url_for("club_van_20_projecten"))
        return render_template(
            "club_van_20_project_form.html", project=project, project_statussen=PROJECT_STATUS_LABELS
        )

    @app.route("/club-van-20/projecten/<int:project_id>/status", methods=["POST"])
    def club_van_20_project_status(project_id):
        db = get_db()
        status = request.form.get("status")
        project = db.execute("SELECT * FROM club_van_20_projecten WHERE id = ?", (project_id,)).fetchone()
        if project is None or status not in PROJECT_STATUS_LABELS:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Ongeldige invoer."}), 400
            return redirect(url_for("club_van_20_projecten"))
        afgerond_op = project["afgerond_op"] or vandaag_amsterdam().isoformat() if status == "klaar" else None
        db.execute(
            "UPDATE club_van_20_projecten SET status = ?, afgerond_op = ? WHERE id = ?",
            (status, afgerond_op, project_id),
        )
        db.commit()
        melding = f"'{project['naam']}' staat nu op '{PROJECT_STATUS_LABELS[status]}'."
        if is_ajax_verzoek():
            return jsonify({"ok": True, "melding": melding})
        flash(melding, "success")
        return redirect(url_for("club_van_20_projecten"))

    @app.route("/club-van-20/projecten/<int:project_id>/verwijderen", methods=["POST"])
    def club_van_20_project_verwijderen(project_id):
        db = get_db()
        db.execute("DELETE FROM club_van_20_projecten WHERE id = ?", (project_id,))
        db.commit()
        flash("Project verwijderd.", "success")
        return redirect(url_for("club_van_20_projecten"))
