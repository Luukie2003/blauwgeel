from datetime import date, datetime, timedelta

from flask import Response, flash, g, jsonify, redirect, render_template, request, session, url_for

import backup as backup_module
from club_van_20 import bereken_club_van_20_status
from database import get_db
from helpers import (
    bouw_taken,
    bereken_bestelling_status,
    bereken_frituurvet_status,
    bereken_kassa_telling_status,
    bereken_komende_thuiswedstrijden,
    bereken_laatste_telling_status,
    bereken_omzet_trend_periode,
    bereken_voorspelde_tekorten,
    bestel_suggesties,
    bouw_weektrend,
    bereken_pda_start,
    bereken_wedstrijd_geschiedenis,
    bereken_week_overzicht,
    csv_response,
    dagdeel_groet,
    format_datum,
    heeft_sectie_toegang,
    is_ajax_verzoek,
    now_str,
    stuur_tag_notificaties,
)
from helpers.tijd import vandaag_amsterdam
from helpers.wedstrijden import OVERIG_TEAM, agenda_teams, voeg_thuiswedstrijd_toe
from pdf import periode_verkoop_pdf
from voorspelling import maak_prognose
from wijzigingen import HUIDIGE_VERSIE, MODULES, MODULES_UITLEG, WIJZIGINGEN

_WEEKDAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
WEDSTRIJDEN_VOORUIT_DAGEN = 60  # zo ver vooruit toont de Wedstrijden-pagina de thuiswedstrijden


def register_routes(app):
    @app.route("/help")
    def help_pagina():
        return render_template(
            "help.html",
            huidige_versie=HUIDIGE_VERSIE,
            wijzigingen=WIJZIGINGEN,
            modules=MODULES,
            modules_uitleg=MODULES_UITLEG,
        )

    @app.route("/tips")
    def tips_pagina():
        return render_template("tips.html")

    def bereken_omzet_trend(db, aantal_dagen=8):
        """Omzet per dag (chronologisch, tellingen van dezelfde dag samengevoegd
        tot één balk) plus de best verkopende producten over die periode --
        gebruikt voor het trendgrafiekje op het dashboard. Rekent altijd met
        de bevroren telling-prijs (tr.verkoopprijs), niet de actuele
        productprijs, om dezelfde reden als het verkooprapport."""
        ruwe_dagen = db.execute(
            """SELECT date(t.datum) AS dag,
                      COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
               FROM tellingen t
               LEFT JOIN telling_regels tr ON tr.telling_id = t.id
               GROUP BY dag
               ORDER BY dag DESC
               LIMIT ?""",
            (aantal_dagen,),
        ).fetchall()
        dagen = list(reversed(ruwe_dagen))

        top_verkopers = []
        if dagen:
            dag_lijst = [d["dag"] for d in dagen]
            placeholders = ",".join("?" for _ in dag_lijst)
            top_verkopers = db.execute(
                f"""SELECT p.naam AS product_naam, p.eenheid,
                           SUM(tr.verkocht) AS verkocht,
                           SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                    FROM telling_regels tr
                    JOIN producten p ON p.id = tr.product_id
                    JOIN tellingen t ON t.id = tr.telling_id
                    WHERE date(t.datum) IN ({placeholders})
                    GROUP BY tr.product_id
                    HAVING SUM(tr.verkocht) > 0
                    ORDER BY omzet DESC
                    LIMIT 6""",
                dag_lijst,
            ).fetchall()

        max_omzet = max((d["omzet"] for d in dagen), default=0)
        laatste_omzet = dagen[-1]["omzet"] if dagen else 0
        eerdere_omzetten = [d["omzet"] for d in dagen[:-1]]
        gemiddelde_omzet = (
            sum(eerdere_omzetten) / len(eerdere_omzetten) if eerdere_omzetten else 0
        )
        verschil_percentage = None
        if gemiddelde_omzet > 0:
            verschil_percentage = (laatste_omzet - gemiddelde_omzet) / gemiddelde_omzet * 100

        balken = [
            {
                "datum_kort": datetime.strptime(d["dag"], "%Y-%m-%d").strftime("%d-%m"),
                "omzet": d["omzet"],
                "hoogte_pct": (d["omzet"] / max_omzet * 100) if max_omzet else 0,
            }
            for d in dagen
        ]

        # Per week is eerlijker dan per telling: de tijd tussen tellingen wisselt (3 of 6 dagen) en daarmee de omzet
        # per balk. Lukt het rekenen niet (bijv. nog geen tellingen), dan blijven de balken per telling over.
        weektrend = None
        try:
            import voorspelling

            weken = voorspelling.omzet_per_week(db)
            if weken:
                wedstrijd_datums = [
                    r["datum"][:10]
                    for r in db.execute("SELECT datum FROM wedstrijden WHERE thuis = 1 AND afgelast = 0").fetchall()
                ]
                weektrend = bouw_weektrend(weken, wedstrijd_datums, datetime.now().date())
        except Exception as fout:  # het dashboard mag nooit stuk gaan door de weekberekening
            print(f"[dashboard] weektrend mislukt, terugval op tellingen: {fout}")

        return {
            "balken": balken,
            "top_verkopers": top_verkopers,
            "laatste_omzet": laatste_omzet,
            "gemiddelde_omzet": gemiddelde_omzet,
            "verschil_percentage": verschil_percentage,
            "weektrend": weektrend,
        }

    @app.route("/")
    def dashboard():
        if g.get("weergave_modus") == "pda":
            # De zware dashboard-cijfers (omzettrend, top-verkopers) zijn niet
            # relevant op de vloer; wel een paar korte regels met wat er nu
            # aandacht nodig heeft (zie bereken_pda_start).
            pda = bereken_pda_start(
                get_db(), session.get("gebruiker_rol"), session.get("gebruiker_secties"), session.get("gebruiker_id")
            )
            pda["eigen_taken"] = [{**t, "url": url_for(t["endpoint"], **t["kwargs"])} for t in pda["eigen_taken"]]
            return render_template("pda_start.html", groet=dagdeel_groet(), **pda)

        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
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
        komende_thuiswedstrijden = bereken_komende_thuiswedstrijden(db)
        taken = [
            {**t, "url": url_for(t["endpoint"], **t["kwargs"])}
            for t in bouw_taken(
                db, session.get("gebruiker_rol"), session.get("gebruiker_secties"), session.get("gebruiker_id")
            )
        ]
        return render_template(
            "dashboard.html",
            taken=taken,
            producten=producten,
            laag=laag,
            recente_mutaties=recente_mutaties,
            open_bestellingen=open_bestellingen,
            komende_thuiswedstrijden=komende_thuiswedstrijden,
            laatste_telling_status=bereken_laatste_telling_status(db),
            kassa_telling_status=bereken_kassa_telling_status(db),
            bestelling_status=bereken_bestelling_status(db),
            frituurvet_status=bereken_frituurvet_status(db),
            # Alleen beheerders hebben iets aan (en toegang tot) de back-ups;
            # de waarschuwing verschijnt alleen als er iets mis is.
            backup_status=(
                backup_module.bereken_backup_status()
                if session.get("gebruiker_rol") == "beheerder"
                else None
            ),
            # Alleen voor wie de Club van 20-sectie heeft (beheerders altijd) --
            # deze query overslaan voor wie de tegel toch niet te zien krijgt.
            club_van_20_status=(
                bereken_club_van_20_status(db)
                if heeft_sectie_toegang(
                    session.get("gebruiker_rol"), session.get("gebruiker_secties"), "club_van_20"
                )
                else None
            ),
        )

    @app.route("/dashboard/omzettrend")
    def dashboard_omzettrend():
        """De kaart 'Omzettrend' van het dashboard. Apart opgehaald, zodat het dashboard niet wacht op de weekcijfers
        (die komen uit het voorspelmodel en dat rekent soms enkele seconden)."""
        return render_template("_dashboard_omzettrend.html", omzet_trend=bereken_omzet_trend(get_db()))

    @app.route("/dashboard/wedstrijddag")
    def dashboard_wedstrijddag():
        """De kaart 'Thuiswedstrijd' van het overzicht: de eerstvolgende thuiswedstrijd van de komende dagen, wat het
        voorspelmodel die dag aan omzet verwacht en welke producten kunnen opraken, zodat je op tijd bestelt. Leeg als er
        de komende dagen geen thuiswedstrijd is. Apart opgehaald omdat het voorspelmodel soms enkele seconden rekent."""
        db = get_db()
        komend = bereken_komende_thuiswedstrijden(db, dagen=5)
        if not komend:
            return ""
        dag = komend[0]
        datum = date.fromisoformat(dag["datum"])
        dagen_tot = (datum - vandaag_amsterdam()).days
        verwacht = None
        try:
            prognose = maak_prognose(db, dagen=7)
            if prognose["beschikbaar"]:
                dag_prognose = next((d for d in prognose["dagen_overzicht"] if d["datum"] == datum), None)
                if dag_prognose and dag_prognose["open"]:
                    verwacht = dag_prognose["omzet"]
        except Exception as fout:  # de kaart mag het overzicht nooit stuk maken
            print(f"[wedstrijddag] prognose mislukt: {fout}")
        tekorten = bereken_voorspelde_tekorten(db)
        onder_minimum = bestel_suggesties(db)
        return render_template(
            "_dashboard_wedstrijddag.html",
            dag=dag,
            weekdag=_WEEKDAGEN[datum.weekday()],
            dagen_tot=dagen_tot,
            verwacht=verwacht,
            tekorten=tekorten[:5],
            aantal_tekorten=len(tekorten),
            onder_minimum=len(onder_minimum),
            dringend=dagen_tot <= 3 and bool(tekorten or onder_minimum),
        )

    @app.route("/verkooprapport")
    def verkooprapport():
        van = request.args.get("van") or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        tot = request.args.get("tot") or datetime.now().strftime("%Y-%m-%d")
        db = get_db()
        omzet_trend = bereken_omzet_trend_periode(db, van, tot)
        return render_template(
            "verkooprapport.html", van=van, tot=tot, omzet_trend=omzet_trend
        )

    @app.route("/week-overzicht")
    def week_overzicht():
        db = get_db()
        overzicht = bereken_week_overzicht(db)
        return render_template("week_overzicht.html", overzicht=overzicht)

    @app.route("/wedstrijden")
    def wedstrijden_overzicht():
        db = get_db()
        # Ook afgelaste wedstrijden, zodat je een afgelasting hier kunt terugdraaien. Verder vooruit dan elders, zodat
        # een zelf toegevoegde wedstrijd over een paar weken hier ook al staat.
        komende_thuiswedstrijden = bereken_komende_thuiswedstrijden(
            db, dagen=WEDSTRIJDEN_VOORUIT_DAGEN, inclusief_afgelast=True
        )
        wedstrijd_geschiedenis = bereken_wedstrijd_geschiedenis(db, inclusief_afgelast=True)
        return render_template(
            "wedstrijden.html",
            komende_thuiswedstrijden=komende_thuiswedstrijden,
            wedstrijd_geschiedenis=wedstrijd_geschiedenis,
            vooruit_dagen=WEDSTRIJDEN_VOORUIT_DAGEN,
            teams=agenda_teams(db),
            overig_team=OVERIG_TEAM,
        )

    @app.route("/wedstrijden/toevoegen", methods=["POST"])
    def wedstrijd_toevoegen():
        """Zelf een thuiswedstrijd toevoegen die (nog) niet in de teamagenda staat. Telt daarna mee zoals elke andere:
        in de prognose, op een dag die alleen bij een thuiswedstrijd open is, en op de agenda."""
        db = get_db()
        fout = voeg_thuiswedstrijd_toe(
            db,
            request.form.get("datum"),
            request.form.get("tijd"),
            request.form.get("team"),
            request.form.get("omschrijving"),
        )
        if fout:
            flash(fout, "error")
        else:
            flash("Thuiswedstrijd toegevoegd. De prognose en de agenda rekenen er meteen mee.", "success")
        return redirect(url_for("wedstrijden_overzicht") + "#toevoegen")

    @app.route("/wedstrijden/<int:wedstrijd_id>/verwijderen", methods=["POST"])
    def wedstrijd_verwijderen(wedstrijd_id):
        """Alleen een zelf toegevoegde wedstrijd kan weg; een wedstrijd uit de teamagenda zet je op afgelast."""
        db = get_db()
        wedstrijd = db.execute("SELECT * FROM wedstrijden WHERE id = ?", (wedstrijd_id,)).fetchone()
        if wedstrijd is None or not wedstrijd["handmatig"]:
            flash("Alleen een zelf toegevoegde wedstrijd kun je verwijderen; zet een andere op 'Afgelast?'.", "error")
            return redirect(url_for("wedstrijden_overzicht"))
        db.execute("DELETE FROM wedstrijden WHERE id = ? AND handmatig = 1", (wedstrijd_id,))
        db.commit()
        flash(f"'{wedstrijd['omschrijving']}' is verwijderd.", "success")
        return redirect(url_for("wedstrijden_overzicht"))

    @app.route("/wedstrijden/<int:wedstrijd_id>/afgelast", methods=["POST"])
    def wedstrijd_afgelast_wisselen(wedstrijd_id):
        """Een wedstrijd als afgelast markeren (of terugzetten op "gaat door").
        Een afgelaste thuiswedstrijd telt nergens meer mee, bijvoorbeeld niet in de
        prognose. De keuze blijft staan, ook als de agenda-koppeling het later
        anders meldt."""
        db = get_db()
        wedstrijd = db.execute("SELECT * FROM wedstrijden WHERE id = ?", (wedstrijd_id,)).fetchone()
        terug = {
            "prognose": url_for("prognose_pagina") + "#thuiswedstrijden",
            "wedstrijden": url_for("wedstrijden_overzicht"),
        }.get(request.form.get("terug"), url_for("wedstrijden_overzicht"))
        if wedstrijd is None:
            flash("Die wedstrijd bestaat niet meer.", "error")
            return redirect(terug)
        afgelast = 1 if request.form.get("afgelast") == "1" else 0
        db.execute(
            "UPDATE wedstrijden SET afgelast = ?, afgelast_bron = 'handmatig' WHERE id = ?",
            (afgelast, wedstrijd_id),
        )
        db.commit()
        flash(
            f"'{wedstrijd['omschrijving']}' staat als afgelast en telt niet meer mee."
            if afgelast
            else f"'{wedstrijd['omschrijving']}' gaat weer door en telt weer mee.",
            "success",
        )
        return redirect(terug)

    @app.route("/verkooprapport/pdf")
    def verkooprapport_pdf_route():
        van = request.args.get("van", "").strip() or (
            datetime.now() - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        tot = request.args.get("tot", "").strip() or datetime.now().strftime("%Y-%m-%d")

        db = get_db()
        # Sommeert per regel verkocht * de destijds vastgezette prijs, i.p.v.
        # de huidige prijs van het product -- een periode kan meerdere
        # tellingen omvatten waartussen de prijs kan zijn gewijzigd.
        regels = db.execute(
            """SELECT p.naam AS product_naam, p.categorie, p.subcategorie, p.eenheid,
                      SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                      SUM(tr.verkocht * tr.verkoopprijs) AS omzet
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
               JOIN producten p ON p.id = tr.product_id
               WHERE t.datum >= ? AND t.datum <= ?
               GROUP BY tr.product_id
               ORDER BY p.categorie, p.naam""",
            (f"{van} 00:00", f"{tot} 23:59"),
        ).fetchall()

        pdf_bytes = periode_verkoop_pdf(format_datum(f"{van} 00:00"), format_datum(f"{tot} 23:59"), regels)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-{van}-tot-{tot}.pdf"
            },
        )

    @app.route("/verkooprapport/csv")
    def verkooprapport_csv_route():
        van = request.args.get("van", "").strip() or (
            datetime.now() - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        tot = request.args.get("tot", "").strip() or datetime.now().strftime("%Y-%m-%d")

        db = get_db()
        regels = db.execute(
            """SELECT p.naam AS product_naam, p.categorie, p.subcategorie, p.eenheid,
                      SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                      SUM(tr.verkocht * tr.verkoopprijs) AS omzet
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
               JOIN producten p ON p.id = tr.product_id
               WHERE t.datum >= ? AND t.datum <= ?
               GROUP BY tr.product_id
               ORDER BY p.categorie, p.naam""",
            (f"{van} 00:00", f"{tot} 23:59"),
        ).fetchall()
        rijen = [
            (
                r["product_naam"],
                r["categorie"],
                r["subcategorie"] or "",
                r["verkocht"],
                r["eenheid"],
                f"{r['omzet']:.2f}".replace(".", ","),
            )
            for r in regels
            if r["verkocht"] > 0
        ]
        return csv_response(
            f"verkooprapport-{van}-tot-{tot}.csv",
            ["Product", "Categorie", "Subcategorie", "Verkocht", "Eenheid", "Omzet"],
            rijen,
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

    # ---------- Bijzonderheden (prikbord) ----------

    @app.route("/bijzonderheden", methods=["GET", "POST"])
    def bijzonderheden():
        db = get_db()
        if request.method == "POST":
            tekst = request.form.get("tekst", "").strip()
            if not tekst:
                flash("Vul een tekst in.", "error")
                return redirect(url_for("bijzonderheden"))
            naam = session.get("gebruiker_naam")
            db.execute(
                "INSERT INTO mededelingen (tekst, naam, datum, urgent) VALUES (?, ?, ?, ?)",
                (tekst, naam, now_str(), 1 if request.form.get("urgent") else 0),
            )
            db.commit()
            stuur_tag_notificaties(
                db, tekst, naam, "nieuwe mededeling", url_for("bijzonderheden", _external=True)
            )
            return redirect(url_for("bijzonderheden"))

        # Nog niet afgehandeld eerst (urgent bovenaan), afgehandelde
        # onderaan -- zodat het prikbord niet dichtslibt met opgeloste
        # dingen, maar ze ook niet spoorloos verdwijnen zoals bij
        # verwijderen.
        mededelingen = db.execute(
            "SELECT * FROM mededelingen ORDER BY afgehandeld ASC, urgent DESC, id DESC"
        ).fetchall()
        opmerkingen_per_mededeling = {}
        for regel in db.execute(
            "SELECT * FROM mededeling_opmerkingen ORDER BY id ASC"
        ).fetchall():
            opmerkingen_per_mededeling.setdefault(regel["mededeling_id"], []).append(regel)
        gebruikersnamen = [
            g["naam"] for g in db.execute("SELECT naam FROM gebruikers ORDER BY naam").fetchall()
        ]
        return render_template(
            "bijzonderheden.html",
            mededelingen=mededelingen,
            opmerkingen_per_mededeling=opmerkingen_per_mededeling,
            gebruikersnamen=gebruikersnamen,
        )

    @app.route("/bijzonderheden/<int:mededeling_id>/opmerking", methods=["POST"])
    def mededeling_opmerking_toevoegen(mededeling_id):
        db = get_db()
        mededeling = db.execute(
            "SELECT * FROM mededelingen WHERE id = ?", (mededeling_id,)
        ).fetchone()
        if mededeling is None:
            flash("Mededeling niet gevonden.", "error")
            return redirect(url_for("bijzonderheden"))
        tekst = request.form.get("tekst", "").strip()
        if not tekst:
            flash("Vul een tekst in.", "error")
            return redirect(url_for("bijzonderheden"))
        naam = session.get("gebruiker_naam")
        db.execute(
            "INSERT INTO mededeling_opmerkingen (mededeling_id, tekst, naam, gebruiker_id, datum) "
            "VALUES (?, ?, ?, ?, ?)",
            (mededeling_id, tekst, naam, session.get("gebruiker_id"), now_str()),
        )
        db.commit()
        stuur_tag_notificaties(
            db, tekst, naam, "reactie op een mededeling", url_for("bijzonderheden", _external=True)
        )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/verwijderen", methods=["POST"])
    def mededeling_verwijderen(mededeling_id):
        db = get_db()
        db.execute("DELETE FROM mededelingen WHERE id = ?", (mededeling_id,))
        db.commit()
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/afhandelen", methods=["POST"])
    def mededeling_afhandelen(mededeling_id):
        db = get_db()
        db.execute(
            """UPDATE mededelingen
               SET afgehandeld = 1, afgehandeld_door = ?, afgehandeld_op = ?
               WHERE id = ?""",
            (session.get("gebruiker_naam"), now_str(), mededeling_id),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgehandeld": 1,
                    "melding": "Afgehandeld. Zakt bij de volgende paginalaad naar onderen.",
                }
            )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/heropenen", methods=["POST"])
    def mededeling_heropenen(mededeling_id):
        db = get_db()
        db.execute(
            """UPDATE mededelingen
               SET afgehandeld = 0, afgehandeld_door = NULL, afgehandeld_op = NULL
               WHERE id = ?""",
            (mededeling_id,),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgehandeld": 0,
                    "melding": "Heropend. Komt bij de volgende paginalaad weer bovenaan te staan.",
                }
            )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/pin-als-banner", methods=["POST"])
    def mededeling_pinnen_als_banner(mededeling_id):
        db = get_db()
        mededeling = db.execute(
            "SELECT * FROM mededelingen WHERE id = ?", (mededeling_id,)
        ).fetchone()
        if mededeling is None:
            flash("Mededeling niet gevonden.", "error")
            return redirect(url_for("bijzonderheden"))
        db.execute(
            "UPDATE instellingen SET banner_tekst = ? WHERE id = 1", (mededeling["tekst"],)
        )
        db.commit()
        flash("Mededeling als banner bovenaan de site gezet.", "success")
        return redirect(url_for("bijzonderheden"))
