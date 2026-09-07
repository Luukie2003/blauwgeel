from datetime import datetime, timedelta

from flask import Response, flash, g, jsonify, redirect, render_template, request, session, url_for

from database import get_db
from helpers import (
    bereken_bestelling_status,
    bereken_frituurvet_status,
    bereken_kassa_telling_status,
    bereken_komende_thuiswedstrijden,
    bereken_laatste_telling_status,
    bereken_omzet_trend_periode,
    bereken_wedstrijd_geschiedenis,
    bereken_week_overzicht,
    csv_response,
    dagdeel_groet,
    format_datum,
    is_ajax_verzoek,
    now_str,
    stuur_tag_notificaties,
)
from pdf import periode_verkoop_pdf

# Handmatig bijgehouden versie-overzicht voor de Help-pagina. Geen
# geautomatiseerd systeem (geen releases/tags) -- gewoon een leesbaar logje
# van wat er is toegevoegd, bijgewerkt bij noemenswaardige wijzigingen.
HUIDIGE_VERSIE = "1.7.0"
WIJZIGINGEN = [
    {
        "versie": "1.7.0",
        "datum": "6 september 2026",
        "punten": [
            "Keuken heeft nu een eigen plek in het menu: voorraad en frituurvet-instellingen bij elkaar",
            "'+ Nieuw Keuken-product' zet de categorie meteen goed bij het aanmaken",
        ],
    },
    {
        "versie": "1.6.0",
        "datum": "6 september 2026",
        "punten": [
            "Keuken toegevoegd als categorie, voor frituursnacks, gehaktballen e.d. -- werkt met dezelfde voorraad, bestellijst en tellijsten als de rest",
            "Herinnering op het dashboard voor het vervangen van het frituurvet, met instelbare termijn (Instellingen)",
        ],
    },
    {
        "versie": "1.5.0",
        "datum": "6 september 2026",
        "punten": [
            "Boodschappenlijst voor losse inkopen buiten de vaste voorraad om (bijv. schoonmaakspullen)",
            "Leveringen inboeken op de handterminal: alles start als manco, pas aanvinken als het echt binnen is gecontroleerd",
            "Handterminal beperkt tot inboeken/controleren/manco melden; bestellen en leveringen inladen blijven desktop",
            "Zoekbalk en productpagina op de handterminal, bestellijst en inboeken als kaartjes i.p.v. een tabel",
            "Rotatiebug op de handterminal opgelost, meer icoon-knoppen, kortere instructieteksten",
            "Inloggen fors versneld (wachtwoord-controle nam voorheen ruim 0,7 seconde per poging in beslag)",
            "Tellingregel achteraf kunnen corrigeren, bijv. als er bij het tellen iets over het hoofd is gezien",
        ],
    },
    {
        "versie": "1.4.0",
        "datum": "25 augustus 2026",
        "punten": [
            "Bijzonderheden: mededelingen 'afhandelen' i.p.v. alleen verwijderen, met wie en wanneer",
            "Urgente mededelingen vallen op tussen de rest van het prikbord",
            "Een mededeling met één klik als de site-brede banner tonen",
        ],
    },
    {
        "versie": "1.3.0",
        "datum": "25 augustus 2026",
        "punten": [
            "Vier-ogen-principe bij kassatellingen: de teller keurt zijn eigen telling niet meer zelf goed",
            "Opmerking bij goedkeuring, apart van de opmerking van de teller",
            "Wie geteld en wie goedgekeurd heeft staat nu in het kasverslag (scherm en PDF)",
            "Team-agenda's en weer gecombineerd op de nieuwe Wedstrijden-pagina",
            "Voorspelde tekorten op de bestellijst, ook boven het minimum",
            "Correctie-boekingen licht rood gemarkeerd in de geschiedenis",
        ],
    },
    {
        "versie": "1.2.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Automatische tests bij elke push naar GitHub (CI)",
            "Signalering van verouderde dependencies (Dependabot)",
            "Beveiligingsheaders toegevoegd (Content-Security-Policy e.a.)",
            "Uurlijkse controle of de site bereikbaar is, met mailmelding bij storing",
        ],
    },
    {
        "versie": "1.1.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Geautomatiseerde tests voor de kernberekeningen (kassa, voorraad, inloggen)",
            "Overgestapt naar Python 3.13 (voorheen 3.9), zowel lokaal als op de server",
        ],
    },
    {
        "versie": "1.0.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Nieuwe kassa-module: tellen per coupure, afdracht/toevoeging boeken, kassa-geschiedenis",
            "Wekelijks overzicht: nieuwe pagina + opgemaakte maandagochtend-mail met logo",
            "Boekingen gekoppeld aan het echte ingelogde account i.p.v. een vrij in te typen naam",
            "Wegklikbare mededelingenbalk bovenaan de site, instelbaar door de beheerder",
            "Omzettrend op het dashboard en het verkooprapport",
        ],
    },
    {
        "versie": "0.4.0",
        "datum": "23 augustus 2026",
        "punten": [
            "Bestellen, ontvangen en leveringen inboeken per besteleenheid (bijv. kratten, dozen)",
            "Verkoopprijs vastgezet per telling, zodat latere prijswijzigingen historische omzet niet meer aantasten",
            "Inkoopprijzen, artikelcodes en besteleenheden bijgewerkt op basis van de leverancierslijst",
            "Subcategorieën onder hoofdcategorieën",
            "Zelf-registratie via e-mail, wachtwoord vergeten, en mailvoorkeuren per account",
            "Mobiele navigatie herzien, homescreen-icoon, eigen 404/500-paginas, favicons",
        ],
    },
    {
        "versie": "0.3.0",
        "datum": "22 augustus 2026",
        "punten": [
            "Categorieën als beheerbare lijst, filter/zoekbalk op de Producten-pagina",
            "Rollen en rechten voor accounts (beheerder/vrijwilliger)",
            "Uitgebreid voorraadoverzicht met waarde per categorie en PDF",
        ],
    },
    {
        "versie": "0.2.0",
        "datum": "21 augustus 2026",
        "punten": [
            "Automatische dagelijkse back-up, met terugzetten vanuit de app",
            "Prikbord (Bijzonderheden)",
            "Losse levering/factuur inboeken, controlescherm na de looplijst",
        ],
    },
    {
        "versie": "0.1.0",
        "datum": "20 augustus 2026",
        "punten": [
            "Eerste versie: producten, voorraad bijhouden, in-/uitboeken",
            "Inloggen en accountbeheer",
            "Voorraad tellen, ook via een looplijst voor onderweg met de telefoon",
            "Verkooprapport per periode (PDF), huisstijl s.v. Blauw-Geel 1915",
        ],
    },
]


def register_routes(app):
    @app.route("/help")
    def help_pagina():
        return render_template(
            "help.html", huidige_versie=HUIDIGE_VERSIE, wijzigingen=WIJZIGINGEN
        )

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

        return {
            "balken": balken,
            "top_verkopers": top_verkopers,
            "laatste_omzet": laatste_omzet,
            "gemiddelde_omzet": gemiddelde_omzet,
            "verschil_percentage": verschil_percentage,
        }

    @app.route("/")
    def dashboard():
        if g.get("weergave_modus") == "pda":
            # Geen van de zware dashboard-cijfers is relevant voor de
            # PDA-modus (puur een menu naar de vloerpagina's), dus die
            # queries hoeven hier niet te draaien.
            return render_template("pda_start.html", groet=dagdeel_groet())

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
        omzet_trend = bereken_omzet_trend(db)
        komende_thuiswedstrijden = bereken_komende_thuiswedstrijden(db)
        return render_template(
            "dashboard.html",
            producten=producten,
            laag=laag,
            recente_mutaties=recente_mutaties,
            open_bestellingen=open_bestellingen,
            omzet_trend=omzet_trend,
            komende_thuiswedstrijden=komende_thuiswedstrijden,
            laatste_telling_status=bereken_laatste_telling_status(db),
            kassa_telling_status=bereken_kassa_telling_status(db),
            bestelling_status=bereken_bestelling_status(db),
            frituurvet_status=bereken_frituurvet_status(db),
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
        komende_thuiswedstrijden = bereken_komende_thuiswedstrijden(db)
        wedstrijd_geschiedenis = bereken_wedstrijd_geschiedenis(db)
        return render_template(
            "wedstrijden.html",
            komende_thuiswedstrijden=komende_thuiswedstrijden,
            wedstrijd_geschiedenis=wedstrijd_geschiedenis,
        )

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
            cur = db.execute(
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
