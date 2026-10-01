"""Beheer van de sponsoren met logo (Kantine-tv > Sponsoren): toevoegen,
bewerken, aan/uit, volgorde en groep, plus hoe ze tussen de dia's van het
kantine scherm en over de prijzenlijst heen komen. De opbouw van de dia's
zelf staat in sponsoren.py."""

from flask import flash, jsonify, redirect, render_template, request, url_for

from database import get_db
from helpers import KIOSK_AFBEELDINGEN_MAP, is_ajax_verzoek, now_str, sla_afbeelding_op
from sponsoren import bouw_sponsor_dias, kop_meervoud


def register_routes(app):
    def _instellingen(db):
        return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()

    def _getal(veld, standaard, minimum=0):
        try:
            return max(minimum, int(request.form.get(veld) or standaard))
        except ValueError:
            return standaard

    def _groepen(db):
        return [
            r["groep"]
            for r in db.execute(
                """SELECT DISTINCT groep FROM kiosk_sponsorlogos
                   WHERE groep IS NOT NULL AND groep != '' ORDER BY groep COLLATE NOCASE"""
            ).fetchall()
        ]

    @app.route("/kiosk/sponsorlogos", methods=["GET", "POST"])
    def kiosk_sponsorlogos():
        db = get_db()
        if request.method == "POST":
            naam = (request.form.get("naam") or "").strip()
            logo = sla_afbeelding_op(request.files.get("logo"), KIOSK_AFBEELDINGEN_MAP)
            if not naam:
                flash("Vul de naam van de sponsor in.", "error")
            else:
                volgorde = db.execute(
                    "SELECT COALESCE(MAX(volgorde), 0) + 1 AS n FROM kiosk_sponsorlogos"
                ).fetchone()["n"]
                db.execute(
                    """INSERT INTO kiosk_sponsorlogos
                           (naam, logo, groep, witte_achtergrond, actief, volgorde, aangemaakt_op)
                       VALUES (?, ?, ?, ?, 1, ?, ?)""",
                    (
                        naam,
                        logo,
                        (request.form.get("groep") or "").strip() or None,
                        1 if request.form.get("witte_achtergrond") else 0,
                        volgorde,
                        now_str(),
                    ),
                )
                db.commit()
                flash(
                    f"Sponsor '{naam}' toegevoegd."
                    + ("" if logo else " Er is geen (bruikbaar) logo geüpload, dus de naam komt als tekst in beeld."),
                    "success",
                )
            return redirect(url_for("kiosk_sponsorlogos"))
        instellingen = _instellingen(db)
        return render_template(
            "kiosk_sponsorlogos.html",
            sponsoren=db.execute(
                "SELECT * FROM kiosk_sponsorlogos ORDER BY volgorde, naam COLLATE NOCASE"
            ).fetchall(),
            groepen=_groepen(db),
            instellingen=instellingen,
            kop_meervoud_automatisch=kop_meervoud(instellingen["sponsors_kop"]),
            voorbeeld_dias=bouw_sponsor_dias(db, instellingen),
        )

    @app.route("/kiosk/sponsorlogos/instellingen", methods=["POST"])
    def kiosk_sponsorlogos_instellingen():
        db = get_db()
        instellingen = _instellingen(db)
        achtergrond = instellingen["sponsors_achtergrond"]
        nieuwe = sla_afbeelding_op(request.files.get("sponsors_achtergrond"), KIOSK_AFBEELDINGEN_MAP)
        if nieuwe:
            achtergrond = nieuwe
        elif request.form.get("achtergrond_verwijderen"):
            achtergrond = None
        db.execute(
            """UPDATE kiosk_scherm_instellingen
               SET sponsors_kop = ?, sponsors_kop_meervoud = ?, sponsors_toon_groepsnaam = ?, sponsors_achtergrond = ?, sponsors_logos_per_dia = ?,
                   sponsors_toon_dias = ?, sponsors_elke_dias = ?, sponsors_duur_seconden = ?,
                   sponsors_toon_prijzen = ?, sponsors_prijzen_interval = ?, sponsors_prijzen_duur = ?
               WHERE id = 1""",
            (
                (request.form.get("sponsors_kop") or "").strip() or "Mede mogelijk gemaakt door",
                (request.form.get("sponsors_kop_meervoud") or "").strip(),
                1 if request.form.get("sponsors_toon_groepsnaam") else 0,
                achtergrond,
                min(6, _getal("sponsors_logos_per_dia", 4, 1)),
                1 if request.form.get("sponsors_toon_dias") else 0,
                _getal("sponsors_elke_dias", 2, 1),
                _getal("sponsors_duur_seconden", 8, 3),
                1 if request.form.get("sponsors_toon_prijzen") else 0,
                _getal("sponsors_prijzen_interval", 60, 10),
                _getal("sponsors_prijzen_duur", 8, 3),
            ),
        )
        db.commit()
        flash("Instellingen voor de sponsoren opgeslagen.", "success")
        return redirect(url_for("kiosk_sponsorlogos"))

    @app.route("/kiosk/sponsorlogos/<int:sponsor_id>", methods=["GET", "POST"])
    def kiosk_sponsorlogo_bewerken(sponsor_id):
        db = get_db()
        sponsor = db.execute("SELECT * FROM kiosk_sponsorlogos WHERE id = ?", (sponsor_id,)).fetchone()
        if sponsor is None:
            flash("Sponsor niet gevonden.", "error")
            return redirect(url_for("kiosk_sponsorlogos"))
        if request.method == "POST":
            naam = (request.form.get("naam") or "").strip()
            if not naam:
                flash("Vul de naam van de sponsor in.", "error")
            else:
                logo = sla_afbeelding_op(request.files.get("logo"), KIOSK_AFBEELDINGEN_MAP) or sponsor["logo"]
                if request.form.get("logo_verwijderen"):
                    logo = None
                db.execute(
                    """UPDATE kiosk_sponsorlogos
                       SET naam = ?, logo = ?, groep = ?, witte_achtergrond = ?, volgorde = ?, actief = ?
                       WHERE id = ?""",
                    (
                        naam,
                        logo,
                        (request.form.get("groep") or "").strip() or None,
                        1 if request.form.get("witte_achtergrond") else 0,
                        _getal("volgorde", sponsor["volgorde"]),
                        1 if request.form.get("actief") else 0,
                        sponsor_id,
                    ),
                )
                db.commit()
                flash(f"Sponsor '{naam}' opgeslagen.", "success")
                return redirect(url_for("kiosk_sponsorlogos"))
        instellingen = _instellingen(db)
        return render_template(
            "kiosk_sponsorlogo_form.html",
            sponsor=sponsor,
            groepen=_groepen(db),
            voorbeeld_dia=bouw_sponsor_dias(db, instellingen, [sponsor])[0],
        )

    @app.route("/kiosk/sponsorlogos/<int:sponsor_id>/actief", methods=["POST"])
    def kiosk_sponsorlogo_actief_wisselen(sponsor_id):
        db = get_db()
        sponsor = db.execute("SELECT * FROM kiosk_sponsorlogos WHERE id = ?", (sponsor_id,)).fetchone()
        if sponsor is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Sponsor niet gevonden."}), 404
            return redirect(url_for("kiosk_sponsorlogos"))
        actief = 0 if sponsor["actief"] else 1
        db.execute("UPDATE kiosk_sponsorlogos SET actief = ? WHERE id = ?", (actief, sponsor_id))
        db.commit()
        melding = f"'{sponsor['naam']}' staat nu {'aan' if actief else 'uit'}."
        if is_ajax_verzoek():
            return jsonify({"ok": True, "actief": bool(actief), "melding": melding})
        flash(melding, "success")
        return redirect(url_for("kiosk_sponsorlogos"))

    @app.route("/kiosk/sponsorlogos/<int:sponsor_id>/verwijderen", methods=["POST"])
    def kiosk_sponsorlogo_verwijderen(sponsor_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_sponsorlogos WHERE id = ?", (sponsor_id,))
        db.commit()
        flash("Sponsor verwijderd.", "success")
        return redirect(url_for("kiosk_sponsorlogos"))
