"""Overzicht en detail van afgeronde tellingen, correcties en PDF's."""

from datetime import datetime

from flask import Response, flash, g, redirect, render_template, request, session, url_for

from database import get_db
from helpers import bereken_trend, bestel_suggesties, format_datum, now_str
from pdf import periode_verkoop_pdf, verkoop_pdf
from voorspelling import maak_prognose, omzet_per_week as omzet_per_week_berekend


def register_routes(app):
    @app.route("/tellingen")
    def tellingen_overzicht():
        db = get_db()
        tellingen = db.execute(
            """SELECT t.*,
                      (SELECT COUNT(*) FROM telling_regels WHERE telling_id = t.id) AS aantal_producten,
                      (SELECT COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0)
                         FROM telling_regels tr
                         WHERE tr.telling_id = t.id) AS omzet
               FROM tellingen t
               ORDER BY t.id DESC"""
        ).fetchall()

        # Per telling de regels erbij, voor de "Bekijken"-pop-up -- scheelt
        # een aparte pagina-navigatie voor een snel kijkje.
        regels_per_telling = {
            t["id"]: db.execute(
                """SELECT tr.*, p.naam AS product_naam, p.eenheid
                   FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
                   WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
                (t["id"],),
            ).fetchall()
            for t in tellingen
        }

        # Omzet per week: de omzet van elke telling wordt verdeeld over de dagen die
        # erbij horen (zie voorspelling.omzet_per_week), dus het maakt niet uit
        # op welke dagen je telt. Alleen volledig gedekte weken tellen mee voor
        # de trend.
        omzet_per_week = omzet_per_week_berekend(db)
        huidige_jaar, huidige_week, _ = datetime.now().isocalendar()
        trend = bereken_trend(omzet_per_week, huidige_jaar, huidige_week)
        try:
            prognose = maak_prognose(db, dagen=7)
        except Exception as fout:  # het tellingenoverzicht mag nooit stuk gaan door de voorspelling
            print(f"[voorspelling] mislukt: {fout}")
            prognose = None

        return render_template(
            "pda_tellingen.html" if g.get("weergave_modus") == "pda" else "tellingen_overzicht.html",
            tellingen=tellingen,
            regels_per_telling=regels_per_telling,
            omzet_per_week=omzet_per_week,
            huidige_jaar=huidige_jaar,
            huidige_week=huidige_week,
            trend=trend,
            prognose=prognose,
        )

    @app.route("/tellingen/gecombineerd/pdf")
    def tellingen_gecombineerd_pdf():
        """PDF van een zelf geselecteerde greep tellingen -- de regels worden
        per product bij elkaar opgeteld, net als bij het periode-verkooprapport
        (dat gebruikt een datumrange; dit gebruikt een losse selectie)."""
        ids = request.args.getlist("ids", type=int)
        if not ids:
            flash("Selecteer minstens één telling om te combineren.", "error")
            return redirect(url_for("tellingen_overzicht"))

        db = get_db()
        placeholders = ",".join("?" for _ in ids)
        regels = db.execute(
            f"""SELECT p.naam AS product_naam, p.categorie, p.eenheid,
                       SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                       SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                FROM telling_regels tr
                JOIN tellingen t ON t.id = tr.telling_id
                JOIN producten p ON p.id = tr.product_id
                WHERE tr.telling_id IN ({placeholders})
                GROUP BY tr.product_id
                ORDER BY p.categorie, p.naam""",
            ids,
        ).fetchall()
        grens = db.execute(
            f"SELECT MIN(datum) AS van, MAX(datum) AS tot FROM tellingen WHERE id IN ({placeholders})",
            ids,
        ).fetchone()

        pdf_bytes = periode_verkoop_pdf(
            format_datum(grens["van"]) if grens["van"] else "",
            format_datum(grens["tot"]) if grens["tot"] else "",
            regels,
        )
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-selectie-{len(ids)}-tellingen.pdf"
            },
        )

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
            """SELECT tr.*, p.naam AS product_naam, p.eenheid
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        totaal_omzet = sum(r["verkocht"] * r["verkoopprijs"] for r in regels)
        besteladvies = bestel_suggesties(db)

        return render_template(
            "pda_telling_detail.html" if g.get("weergave_modus") == "pda" else "telling_detail.html",
            telling=telling,
            regels=regels,
            totaal_omzet=totaal_omzet,
            besteladvies=besteladvies,
        )

    @app.route("/tellingen/regels/<int:regel_id>/corrigeren", methods=["POST"])
    def telling_regel_corrigeren(regel_id):
        """Corrigeert het geteld aantal (en dus verkocht/correctie) van 1
        productregel binnen een eerder afgeronde telling -- bijv. omdat er
        iets over het hoofd is gezien bij het tellen (een krat die nog in de
        koelkast stond). Raakt bewust nooit de actuele voorraad: die had je
        al apart via boeken in/uit rechtgezet. Dit corrigeert alleen het
        historische verkocht/correctie-cijfer (en daarmee de omzetcijfers)
        van deze ene telling."""
        db = get_db()
        regel = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid, t.datum AS telling_datum
               FROM telling_regels tr
               JOIN producten p ON p.id = tr.product_id
               JOIN tellingen t ON t.id = tr.telling_id
               WHERE tr.id = ?""",
            (regel_id,),
        ).fetchone()
        if regel is None:
            flash("Tellingregel niet gevonden.", "error")
            return redirect(url_for("tellen"))

        try:
            nieuw_geteld = int(request.form.get("geteld_aantal", ""))
        except (TypeError, ValueError):
            flash("Vul een geldig aantal in.", "error")
            return redirect(url_for("telling_detail", telling_id=regel["telling_id"]))
        if nieuw_geteld < 0:
            flash("Aantal kan niet negatief zijn.", "error")
            return redirect(url_for("telling_detail", telling_id=regel["telling_id"]))

        opmerking = request.form.get("correctie_opmerking", "").strip()
        naam = session.get("gebruiker_naam")
        gebruiker_id = session.get("gebruiker_id")

        verschil = nieuw_geteld - regel["voorraad_voor"]
        nieuw_verkocht = max(0, -verschil)
        nieuw_correctie = max(0, verschil)

        db.execute(
            """UPDATE telling_regels
               SET geteld_aantal_voor_correctie = ?,
                   gecorrigeerd_door_id = ?,
                   gecorrigeerd_door = ?,
                   gecorrigeerd_op = ?,
                   correctie_opmerking = ?,
                   geteld_aantal = ?,
                   verkocht = ?,
                   correctie = ?
               WHERE id = ?""",
            (
                regel["geteld_aantal"],
                gebruiker_id,
                naam,
                now_str(),
                opmerking,
                nieuw_geteld,
                nieuw_verkocht,
                nieuw_correctie,
                regel_id,
            ),
        )

        # De mutatie die destijds voor dit product bij deze telling is
        # aangemaakt moet meeveranderen, anders blijft de geschiedenis het
        # oude (foute) verkocht/correctie-cijfer tonen.
        db.execute(
            "DELETE FROM mutaties WHERE telling_id = ? AND product_id = ?",
            (regel["telling_id"], regel["product_id"]),
        )
        if nieuw_verkocht > 0:
            db.execute(
                """INSERT INTO mutaties
                   (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                   VALUES (?, 'uit', ?, ?, ?, ?, ?, ?)""",
                (
                    regel["product_id"],
                    nieuw_verkocht,
                    regel["telling_datum"],
                    naam,
                    gebruiker_id,
                    f"Verkocht (telling #{regel['telling_id']}, gecorrigeerd)",
                    regel["telling_id"],
                ),
            )
        elif nieuw_correctie > 0:
            db.execute(
                """INSERT INTO mutaties
                   (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                   VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                (
                    regel["product_id"],
                    nieuw_correctie,
                    regel["telling_datum"],
                    naam,
                    gebruiker_id,
                    f"Correctie (telling #{regel['telling_id']}, gecorrigeerd)",
                    regel["telling_id"],
                ),
            )
        db.commit()

        flash(
            f"Telling voor '{regel['product_naam']}' gecorrigeerd: {regel['geteld_aantal']} → "
            f"{nieuw_geteld} {regel['eenheid']} geteld.",
            "success",
        )
        return redirect(url_for("telling_detail", telling_id=regel["telling_id"]))

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
            """SELECT tr.*, p.naam AS product_naam, p.eenheid
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
