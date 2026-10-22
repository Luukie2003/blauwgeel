"""Overzicht en detail van afgeronde tellingen, correcties en PDF's."""

from datetime import datetime

from flask import Response, flash, g, redirect, render_template, request, session, url_for

from database import get_db
from helpers import bereken_trend, bestel_suggesties, format_datum, now_str, verwerk_auto_inactief
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

        # De verwachting, de trend en de omzet per week komen uit het voorspelmodel en dat rekent op de server soms
        # enkele seconden. Die haalt de pagina daarom na het laden apart op (zie tellingen_cijfers), zodat de
        # tellingen zelf meteen klaarstaan.
        return render_template(
            "pda_tellingen.html" if g.get("weergave_modus") == "pda" else "tellingen_overzicht.html",
            tellingen=tellingen,
        )

    @app.route("/tellingen/<int:telling_id>/regels")
    def telling_regels(telling_id):
        """De regels van één telling voor de "Bekijken"-pop-up, pas opgehaald als je hem opent. Vroeger stonden de regels
        van alle tellingen ooit al in de pagina: na een seizoen was dat een paar MB, wat op een telefoon traag laadt."""
        regels = get_db().execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        return render_template("_telling_regels.html", regels=regels)

    @app.route("/tellingen/cijfers")
    def tellingen_cijfers():
        """De verwachting, de trend en de omzet per week voor het tellingenoverzicht, apart opgehaald (zie hierboven).

        Omzet per week: de omzet van elke telling wordt verdeeld over de dagen die erbij horen (zie
        voorspelling.omzet_per_week), dus het maakt niet uit op welke dagen je telt. Alleen volledig gedekte weken
        tellen mee voor de trend."""
        db = get_db()
        omzet_per_week = omzet_per_week_berekend(db)
        huidige_jaar, huidige_week, _ = datetime.now().isocalendar()
        trend = bereken_trend(omzet_per_week, huidige_jaar, huidige_week)
        try:
            prognose = maak_prognose(db, dagen=7)
        except Exception as fout:  # het tellingenoverzicht mag nooit stuk gaan door de voorspelling
            print(f"[voorspelling] mislukt: {fout}")
            prognose = None

        return render_template(
            "_pda_tellingen_cijfers.html" if g.get("weergave_modus") == "pda" else "_tellingen_cijfers.html",
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

    def _later_geteld(db, telling):
        """De producten uit deze telling die daarna nog eens geteld zijn. Voor die producten is deze telling niet meer
        de laatste: de voorraad is sindsdien opnieuw vastgesteld, dus een correctie hier raakt de voorraad niet."""
        return {
            r[0]
            for r in db.execute(
                """SELECT DISTINCT tr.product_id FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
                   WHERE (t.datum > ? OR (t.datum = ? AND t.id > ?))
                     AND tr.product_id IN (SELECT product_id FROM telling_regels WHERE telling_id = ?)""",
                (telling["datum"], telling["datum"], telling["id"], telling["id"]),
            ).fetchall()
        }

    def _voorraad_volgens_telling(db, regel, telling):
        """Wat de voorraad zou moeten zijn volgens deze telling: het getelde aantal plus alles wat daarna is in- en
        uitgeboekt. Alleen zinvol als dit de laatste telling van het product is."""
        rij = db.execute(
            """SELECT COALESCE(SUM(CASE WHEN type = 'in' THEN aantal ELSE -aantal END), 0) FROM mutaties
               WHERE product_id = ? AND datum >= ? AND (telling_id IS NULL OR telling_id != ?)""",
            (regel["product_id"], telling["datum"], telling["id"]),
        ).fetchone()
        return regel["geteld_aantal"] + rij[0]

    def _voorraad_afwijkingen(db, telling, regels, later_geteld):
        """{regel_id: (huidige voorraad, volgens de telling)} voor de gecorrigeerde regels van producten waarvan dit de
        laatste telling is en waar de voorraad niet klopt met de telling en de boekingen daarna. Zo blijft er bij een
        correctie waarbij de voorraad niet meeging (van vóór 1.49.1, of met het vinkje uit) een knop staan om het recht
        te zetten; is de voorraad al met de hand goed gezet, dan niet."""
        uitkomst = {}
        for r in regels:
            if r["geteld_aantal_voor_correctie"] is None or r["product_id"] in later_geteld:
                continue
            huidig = db.execute("SELECT voorraad FROM producten WHERE id = ?", (r["product_id"],)).fetchone()[0]
            verwacht = _voorraad_volgens_telling(db, r, telling)
            if huidig != verwacht:
                uitkomst[r["id"]] = (huidig, verwacht)
        return uitkomst

    def _pas_voorraad_aan(db, product_id, verschil):
        """Telt 'verschil' bij de voorraad op; geeft (oud, nieuw, gedeactiveerde naam of None) terug."""
        oud = db.execute("SELECT voorraad FROM producten WHERE id = ?", (product_id,)).fetchone()["voorraad"]
        db.execute("UPDATE producten SET voorraad = voorraad + ? WHERE id = ?", (verschil, product_id))
        return oud, oud + verschil, verwerk_auto_inactief(db, product_id, oud + verschil)

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
        later_geteld = _later_geteld(db, telling)

        return render_template(
            "pda_telling_detail.html" if g.get("weergave_modus") == "pda" else "telling_detail.html",
            telling=telling,
            regels=regels,
            totaal_omzet=totaal_omzet,
            besteladvies=besteladvies,
            later_geteld=later_geteld,
            voorraad_afwijking=_voorraad_afwijkingen(db, telling, regels, later_geteld),
        )

    @app.route("/tellingen/regels/<int:regel_id>/corrigeren", methods=["POST"])
    def telling_regel_corrigeren(regel_id):
        """Corrigeert het geteld aantal (en dus verkocht/correctie) van 1
        productregel binnen een eerder afgeronde telling -- bijv. omdat er
        iets over het hoofd is gezien bij het tellen (een krat die nog in de
        koelkast stond). Past het verkocht/correctie-cijfer (en daarmee de
        omzet) van deze telling aan. Is dit de laatste telling van het
        product, dan gaat de huidige voorraad mee met het verschil (vinkje
        'voorraad_aanpassen', standaard aan): die was bij het tellen op het
        getelde aantal gezet. Bij een oudere telling niet, want daarna is
        de voorraad opnieuw geteld."""
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
        telling = db.execute("SELECT * FROM tellingen WHERE id = ?", (regel["telling_id"],)).fetchone()
        is_laatste = regel["product_id"] not in _later_geteld(db, telling)
        voorraad_mee = is_laatste and bool(request.form.get("voorraad_aanpassen"))

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
        voorraad_tekst = ""
        if voorraad_mee and nieuw_geteld != regel["geteld_aantal"]:
            oud, nieuw, gedeactiveerd = _pas_voorraad_aan(db, regel["product_id"], nieuw_geteld - regel["geteld_aantal"])
            voorraad_tekst = f" De voorraad is aangepast van {oud} naar {nieuw} {regel['eenheid']}."
            if gedeactiveerd:
                voorraad_tekst += f" '{gedeactiveerd}' staat nu op inactief (voorraad op 0)."

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
            f"{nieuw_geteld} {regel['eenheid']} geteld." + (voorraad_tekst or (
                "" if is_laatste else " De huidige voorraad is niet aangepast: dit product is daarna opnieuw geteld."
            )),
            "success",
        )
        return redirect(url_for("telling_detail", telling_id=regel["telling_id"]))

    @app.route("/tellingen/regels/<int:regel_id>/voorraad-bijwerken", methods=["POST"])
    def telling_regel_voorraad_bijwerken(regel_id):
        """Zet de voorraad op wat hij volgens deze (gecorrigeerde) telling en de boekingen daarna zou moeten zijn, voor
        als die bij de correctie niet meeging. Alleen bij de laatste telling van het product (zie _voorraad_afwijkingen)."""
        db = get_db()
        regel = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid FROM telling_regels tr
               JOIN producten p ON p.id = tr.product_id WHERE tr.id = ?""",
            (regel_id,),
        ).fetchone()
        if regel is None:
            flash("Tellingregel niet gevonden.", "error")
            return redirect(url_for("tellen"))
        telling = db.execute("SELECT * FROM tellingen WHERE id = ?", (regel["telling_id"],)).fetchone()
        terug = redirect(url_for("telling_detail", telling_id=regel["telling_id"]))
        if regel["product_id"] in _later_geteld(db, telling):
            flash(f"'{regel['product_naam']}' is daarna opnieuw geteld; de voorraad klopt daarmee al.", "error")
            return terug
        afwijking = _voorraad_afwijkingen(db, telling, [regel], set()).get(regel_id)
        if afwijking is None:
            flash(f"De voorraad van '{regel['product_naam']}' klopt al met de telling.", "success")
            return terug
        huidig, verwacht = afwijking
        oud, nieuw, gedeactiveerd = _pas_voorraad_aan(db, regel["product_id"], verwacht - huidig)
        db.commit()
        flash(
            f"Voorraad van '{regel['product_naam']}' aangepast van {oud} naar {nieuw} {regel['eenheid']}."
            + (f" '{gedeactiveerd}' staat nu op inactief (voorraad op 0)." if gedeactiveerd else ""),
            "success",
        )
        return terug

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
