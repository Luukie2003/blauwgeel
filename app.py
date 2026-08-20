import secrets
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_db, register_db
from pdf import bestellijst_pdf, periode_verkoop_pdf, verkoop_pdf

BASE_DIR = Path(__file__).parent
SECRET_KEY_PATH = BASE_DIR / "secret_key.txt"

OPEN_ENDPOINTS = {"login", "static"}

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
        "endpoints": ["tellen", "tellen_lopen", "tellen_lopen_starten"],
        "url_endpoint": "tellen",
        "label": "Voorraad tellen",
    },
    {
        "endpoints": ["tellingen_overzicht", "telling_detail"],
        "url_endpoint": "tellingen_overzicht",
        "label": "Tellingen",
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


def get_secret_key():
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_PATH.write_text(key)
    return key


def create_app():
    app = Flask(__name__)
    app.config["DATABASE"] = str(BASE_DIR / "voorraad.db")
    app.config["SECRET_KEY"] = get_secret_key()

    register_db(app)
    init_db(app)

    app.jinja_env.filters["datum_nl"] = format_datum

    @app.before_request
    def vereis_login():
        if request.endpoint in OPEN_ENDPOINTS or request.endpoint is None:
            return None
        if "gebruiker_id" not in session:
            return redirect(url_for("login", next=request.path))
        return None

    @app.context_processor
    def inject_nav():
        actieve_nav = next(
            (item for item in NAV_ITEMS if request.endpoint in item["endpoints"]),
            None,
        )
        return {
            "nav_items": NAV_ITEMS,
            "actieve_nav": actieve_nav,
            "huidige_gebruiker": session.get("gebruiker_naam"),
            "css_versie": int((BASE_DIR / "static" / "style.css").stat().st_mtime),
        }

    register_routes(app)
    return app


def format_datum(value):
    if not value:
        return ""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return dt.strftime("%d-%m-%Y %H:%M")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def now_datetime_local():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def bereken_trend(omzet_per_week, huidige_jaar, huidige_week):
    """Voortschrijdend gemiddelde + trendrichting op basis van volledig
    afgesloten weken (de lopende week telt niet mee, die is nog niet klaar).

    omzet_per_week: lijst met dicts (jaar, week, omzet, ...), nieuwste eerst.
    """
    afgeronde_weken = [
        w for w in omzet_per_week if (w["jaar"], w["week"]) != (huidige_jaar, huidige_week)
    ]
    chronologisch = list(reversed(afgeronde_weken))  # oud -> nieuw

    if len(chronologisch) < 2:
        return None

    recente = chronologisch[-4:]
    verwachting = sum(w["omzet"] for w in recente) / len(recente)

    n = len(chronologisch)
    xs = list(range(n))
    ys = [w["omzet"] for w in chronologisch]
    x_gem = sum(xs) / n
    y_gem = sum(ys) / n
    teller = sum((x - x_gem) * (y - y_gem) for x, y in zip(xs, ys))
    noemer = sum((x - x_gem) ** 2 for x in xs)
    richting_per_week = teller / noemer if noemer else 0

    if abs(richting_per_week) < 0.02 * (y_gem or 1):
        richting = "stabiel"
    elif richting_per_week > 0:
        richting = "stijgend"
    else:
        richting = "dalend"

    return {
        "verwachting": verwachting,
        "richting": richting,
        "richting_per_week": richting_per_week,
        "gebaseerd_op_weken": len(recente),
    }


def register_routes(app):
    # ---------- Inloggen / accounts ----------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "gebruiker_id" in session:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            wachtwoord = request.form.get("wachtwoord", "")
            db = get_db()
            gebruiker = db.execute(
                "SELECT * FROM gebruikers WHERE naam = ?", (naam,)
            ).fetchone()
            if gebruiker and check_password_hash(gebruiker["wachtwoord_hash"], wachtwoord):
                session.clear()
                session["gebruiker_id"] = gebruiker["id"]
                session["gebruiker_naam"] = gebruiker["naam"]
                volgende = request.args.get("next") or url_for("dashboard")
                return redirect(volgende)
            flash("Onjuiste naam of wachtwoord.", "error")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Je bent uitgelogd.", "success")
        return redirect(url_for("login"))

    @app.route("/accounts")
    def accounts_lijst():
        db = get_db()
        gebruikers = db.execute(
            "SELECT id, naam, aangemaakt_op FROM gebruikers ORDER BY naam"
        ).fetchall()
        return render_template("accounts.html", gebruikers=gebruikers)

    @app.route("/accounts/nieuw", methods=["POST"])
    def account_nieuw():
        naam = request.form.get("naam", "").strip()
        wachtwoord = request.form.get("wachtwoord", "")
        db = get_db()

        if not naam or not wachtwoord:
            flash("Naam en wachtwoord zijn verplicht.", "error")
        elif len(wachtwoord) < 4:
            flash("Wachtwoord moet minstens 4 tekens zijn.", "error")
        elif db.execute("SELECT id FROM gebruikers WHERE naam = ?", (naam,)).fetchone():
            flash(f"Er bestaat al een account met de naam '{naam}'.", "error")
        else:
            db.execute(
                "INSERT INTO gebruikers (naam, wachtwoord_hash, aangemaakt_op) VALUES (?, ?, ?)",
                (naam, generate_password_hash(wachtwoord, method="pbkdf2:sha256"), now_str()),
            )
            db.commit()
            flash(f"Account '{naam}' aangemaakt.", "success")
        return redirect(url_for("accounts_lijst"))

    @app.route("/accounts/<int:gebruiker_id>/verwijderen", methods=["POST"])
    def account_verwijderen(gebruiker_id):
        db = get_db()
        aantal = db.execute("SELECT COUNT(*) AS n FROM gebruikers").fetchone()["n"]
        if aantal <= 1:
            flash("Je kunt het laatste account niet verwijderen.", "error")
        elif gebruiker_id == session.get("gebruiker_id"):
            flash("Je kunt je eigen account niet verwijderen terwijl je bent ingelogd.", "error")
        else:
            db.execute("DELETE FROM gebruikers WHERE id = ?", (gebruiker_id,))
            db.commit()
            flash("Account verwijderd.", "success")
        return redirect(url_for("accounts_lijst"))

    @app.route("/account/wachtwoord", methods=["GET", "POST"])
    def account_wachtwoord():
        if request.method == "POST":
            huidig = request.form.get("huidig_wachtwoord", "")
            nieuw = request.form.get("nieuw_wachtwoord", "")
            nieuw_herhaald = request.form.get("nieuw_wachtwoord_herhaald", "")
            db = get_db()
            gebruiker = db.execute(
                "SELECT * FROM gebruikers WHERE id = ?", (session["gebruiker_id"],)
            ).fetchone()

            if not check_password_hash(gebruiker["wachtwoord_hash"], huidig):
                flash("Huidig wachtwoord is onjuist.", "error")
            elif len(nieuw) < 4:
                flash("Nieuw wachtwoord moet minstens 4 tekens zijn.", "error")
            elif nieuw != nieuw_herhaald:
                flash("Nieuwe wachtwoorden komen niet overeen.", "error")
            else:
                db.execute(
                    "UPDATE gebruikers SET wachtwoord_hash = ? WHERE id = ?",
                    (generate_password_hash(nieuw, method="pbkdf2:sha256"), gebruiker["id"]),
                )
                db.commit()
                flash("Wachtwoord gewijzigd.", "success")
                return redirect(url_for("dashboard"))

        return render_template("account_wachtwoord.html")

    @app.route("/help")
    def help_pagina():
        return render_template("help.html")

    # ---------- Overzicht ----------

    @app.route("/")
    def dashboard():
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
                   (artikelcode, naam, categorie, eenheid, voorraad, min_voorraad,
                    bestel_hoeveelheid, verkoopprijs, actief, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.form.get("artikelcode", "").strip() or None,
                    request.form["naam"].strip(),
                    request.form["categorie"].strip() or "Overig",
                    request.form["eenheid"].strip() or "stuks",
                    int(request.form["voorraad"] or 0),
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    1 if request.form.get("actief") else 0,
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
                   SET artikelcode = ?, naam = ?, categorie = ?, eenheid = ?, voorraad = ?,
                       min_voorraad = ?, bestel_hoeveelheid = ?, verkoopprijs = ?,
                       actief = ?, opmerking = ?
                   WHERE id = ?""",
                (
                    request.form.get("artikelcode", "").strip() or None,
                    request.form["naam"].strip(),
                    request.form["categorie"].strip() or "Overig",
                    request.form["eenheid"].strip() or "stuks",
                    int(request.form["voorraad"] or 0),
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    1 if request.form.get("actief") else 0,
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
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
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

    def verwerk_telling(db, waarden, naam, opmerking, datum):
        """waarden: dict {product_id: geteld_aantal}. Maakt een telling aan,
        berekent per product het verschil met de huidige voorraad, en werkt
        voorraad + geschiedenis bij. Retourneert het nieuwe telling_id, of
        None als er niets te verwerken viel."""
        if not waarden:
            return None

        cur = db.execute(
            "INSERT INTO tellingen (datum, naam, opmerking) VALUES (?, ?, ?)",
            (datum, naam, opmerking),
        )
        telling_id = cur.lastrowid

        for product_id, geteld in waarden.items():
            product = db.execute(
                "SELECT * FROM producten WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None:
                continue
            verschil = geteld - product["voorraad"]
            verkocht = max(0, -verschil)
            correctie = max(0, verschil)

            db.execute(
                """INSERT INTO telling_regels
                   (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (telling_id, product_id, product["voorraad"], geteld, verkocht, correctie),
            )
            db.execute(
                "UPDATE producten SET voorraad = ? WHERE id = ?", (geteld, product_id)
            )
            if verkocht > 0:
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, opmerking, telling_id)
                       VALUES (?, 'uit', ?, ?, ?, ?, ?)""",
                    (product_id, verkocht, datum, naam, f"Verkocht (telling #{telling_id})", telling_id),
                )
            elif correctie > 0:
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, opmerking, telling_id)
                       VALUES (?, 'in', ?, ?, ?, ?, ?)""",
                    (product_id, correctie, datum, naam, f"Correctie (telling #{telling_id})", telling_id),
                )

        db.commit()
        return telling_id

    @app.route("/tellen", methods=["GET", "POST"])
    def tellen():
        db = get_db()
        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            opmerking = request.form.get("opmerking", "").strip()
            datum_input = request.form.get("datum", "").strip()
            datum = datum_input.replace("T", " ") if datum_input else now_str()

            producten = db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()

            waarden = {}
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
                waarden[p["id"]] = geteld

            telling_id = verwerk_telling(db, waarden, naam, opmerking, datum)
            if telling_id is None:
                flash("Geen aantallen ingevuld -- er is niets geteld.", "error")
                return redirect(url_for("tellen"))

            flash(
                f"Telling #{telling_id} verwerkt: {len(waarden)} product(en) geteld.",
                "success",
            )
            return redirect(url_for("telling_detail", telling_id=telling_id))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        return render_template(
            "tellen.html",
            producten=producten,
            nu_datetime_local=now_datetime_local(),
        )

    LOOP_SESSIE_SLEUTELS = ("loop_fase", "loop_index", "loop_bar", "loop_hok")

    @app.route("/tellen/lopen/starten")
    def tellen_lopen_starten():
        for sleutel in LOOP_SESSIE_SLEUTELS:
            session.pop(sleutel, None)
        return redirect(url_for("tellen_lopen"))

    @app.route("/tellen/lopen", methods=["GET", "POST"])
    def tellen_lopen():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        if not producten:
            flash("Geen actieve producten om te tellen.", "error")
            return redirect(url_for("tellen"))
        totaal = len(producten)

        if request.method == "POST":
            actie = request.form.get("actie", "volgende")
            if actie == "stoppen":
                for sleutel in LOOP_SESSIE_SLEUTELS:
                    session.pop(sleutel, None)
                flash("Looplijst afgebroken, er is niets opgeslagen.", "error")
                return redirect(url_for("tellen"))

            fase = session.get("loop_fase", "bar")
            index = session.get("loop_index", 0)
            bar_waarden = session.get("loop_bar", {})
            hok_waarden = session.get("loop_hok", {})
            huidige_dict = bar_waarden if fase == "bar" else hok_waarden

            if 0 <= index < totaal:
                product_id = str(producten[index]["id"])
                waarde = request.form.get("geteld", "").strip()
                if waarde != "":
                    huidige_dict[product_id] = waarde
                elif product_id in huidige_dict:
                    del huidige_dict[product_id]

            if actie == "vorige":
                index -= 1
                if index < 0:
                    if fase == "hok":
                        fase = "bar"
                        index = totaal - 1
                    else:
                        index = 0
            else:
                index += 1
                if index >= totaal:
                    if fase == "bar":
                        fase = "hok"
                        index = 0
                    else:
                        # Bar en voorraadhok zijn allebei geteld: optellen en opslaan.
                        geparsed = {}
                        for p in producten:
                            pid_str = str(p["id"])
                            bar_tekst = bar_waarden.get(pid_str, "")
                            hok_tekst = hok_waarden.get(pid_str, "")
                            if bar_tekst == "" and hok_tekst == "":
                                continue
                            try:
                                bar_aantal = int(bar_tekst) if bar_tekst != "" else 0
                            except ValueError:
                                bar_aantal = 0
                            try:
                                hok_aantal = int(hok_tekst) if hok_tekst != "" else 0
                            except ValueError:
                                hok_aantal = 0
                            geteld_totaal = bar_aantal + hok_aantal
                            if geteld_totaal >= 0:
                                geparsed[p["id"]] = geteld_totaal

                        for sleutel in LOOP_SESSIE_SLEUTELS:
                            session.pop(sleutel, None)

                        telling_id = verwerk_telling(
                            db,
                            geparsed,
                            session.get("gebruiker_naam"),
                            "Via looplijst geteld (bar + voorraadhok)",
                            now_str(),
                        )
                        if telling_id is None:
                            flash("Geen aantallen ingevuld -- er is niets geteld.", "error")
                            return redirect(url_for("tellen"))
                        flash(
                            f"Telling #{telling_id} verwerkt: {len(geparsed)} product(en) "
                            "geteld via de looplijst (bar + voorraadhok).",
                            "success",
                        )
                        return redirect(url_for("telling_detail", telling_id=telling_id))

            session["loop_fase"] = fase
            session["loop_index"] = index
            session["loop_bar"] = bar_waarden
            session["loop_hok"] = hok_waarden
            session.modified = True
            return redirect(url_for("tellen_lopen"))

        fase = session.get("loop_fase", "bar")
        index = session.get("loop_index", 0)
        if index >= totaal:
            index = 0
        bar_waarden = session.get("loop_bar", {})
        hok_waarden = session.get("loop_hok", {})
        huidig = producten[index]
        huidige_dict = bar_waarden if fase == "bar" else hok_waarden
        huidige_waarde = huidige_dict.get(str(huidig["id"]), "")
        bar_waarde_hint = bar_waarden.get(str(huidig["id"]), "") if fase == "hok" else None

        stap_nu = (0 if fase == "bar" else totaal) + index
        voortgang_percentage = round(stap_nu / (totaal * 2) * 100, 1)

        return render_template(
            "tellen_lopen.html",
            product=huidig,
            index=index,
            totaal=totaal,
            fase=fase,
            bar_waarde_hint=bar_waarde_hint,
            huidige_waarde=huidige_waarde,
            voortgang_percentage=voortgang_percentage,
        )

    @app.route("/tellingen")
    def tellingen_overzicht():
        db = get_db()
        tellingen = db.execute(
            """SELECT t.*,
                      (SELECT COUNT(*) FROM telling_regels WHERE telling_id = t.id) AS aantal_producten,
                      (SELECT COALESCE(SUM(tr.verkocht * p.verkoopprijs), 0)
                         FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
                         WHERE tr.telling_id = t.id) AS omzet
               FROM tellingen t
               ORDER BY t.id DESC"""
        ).fetchall()

        verkoop_regels = db.execute(
            """SELECT t.datum, tr.verkocht, p.verkoopprijs
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
               JOIN producten p ON p.id = tr.product_id
               WHERE tr.verkocht > 0"""
        ).fetchall()

        weken = {}
        for r in verkoop_regels:
            dt = datetime.strptime(r["datum"], "%Y-%m-%d %H:%M")
            jaar, week, _ = dt.isocalendar()
            sleutel = (jaar, week)
            if sleutel not in weken:
                maandag = dt - timedelta(days=dt.weekday())
                zondag = maandag + timedelta(days=6)
                weken[sleutel] = {
                    "jaar": jaar,
                    "week": week,
                    "van": maandag.strftime("%Y-%m-%d"),
                    "tot": zondag.strftime("%Y-%m-%d"),
                    "omzet": 0.0,
                }
            weken[sleutel]["omzet"] += r["verkocht"] * r["verkoopprijs"]

        omzet_per_week = sorted(
            weken.values(), key=lambda w: (w["jaar"], w["week"]), reverse=True
        )
        huidige_jaar, huidige_week, _ = datetime.now().isocalendar()
        trend = bereken_trend(omzet_per_week, huidige_jaar, huidige_week)

        return render_template(
            "tellingen_overzicht.html",
            tellingen=tellingen,
            omzet_per_week=omzet_per_week,
            huidige_jaar=huidige_jaar,
            huidige_week=huidige_week,
            trend=trend,
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
            """SELECT tr.*, p.naam AS product_naam, p.eenheid, p.verkoopprijs
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        totaal_omzet = sum(r["verkocht"] * r["verkoopprijs"] for r in regels)
        besteladvies = bestel_suggesties(db)

        return render_template(
            "telling_detail.html",
            telling=telling,
            regels=regels,
            totaal_omzet=totaal_omzet,
            besteladvies=besteladvies,
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

    @app.route("/verkooprapport")
    def verkooprapport():
        van = request.args.get("van") or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        tot = request.args.get("tot") or datetime.now().strftime("%Y-%m-%d")
        return render_template("verkooprapport.html", van=van, tot=tot)

    @app.route("/verkooprapport/pdf")
    def verkooprapport_pdf_route():
        van = request.args.get("van", "").strip() or (
            datetime.now() - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        tot = request.args.get("tot", "").strip() or datetime.now().strftime("%Y-%m-%d")

        db = get_db()
        regels = db.execute(
            """SELECT p.naam AS product_naam, p.categorie, p.eenheid, p.verkoopprijs,
                      SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie
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
                """SELECT * FROM producten
                   WHERE actief = 1 AND voorraad < min_voorraad
                   ORDER BY categorie, naam"""
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
        recent_ontvangen_met_regels = []
        for b in recent_ontvangen:
            regels = db.execute(
                """SELECT br.*, p.naam AS product_naam, p.eenheid
                   FROM bestelregels br JOIN producten p ON p.id = br.product_id
                   WHERE br.bestelling_id = ?""",
                (b["id"],),
            ).fetchall()
            recent_ontvangen_met_regels.append((b, regels))

        return render_template(
            "bestellijst.html",
            suggesties=suggesties,
            open_bestellingen=open_bestellingen_met_regels,
            recent_ontvangen=recent_ontvangen_met_regels,
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
            was_al_ontvangen = bestelling["status"] == "ontvangen"

            for regel in regels:
                aantal_str = request.form.get(f"ontvangen_{regel['id']}", "0")
                try:
                    aantal_ontvangen = max(0, int(aantal_str))
                except ValueError:
                    aantal_ontvangen = 0

                vorige_ontvangen = regel["aantal_ontvangen"] or 0
                delta = aantal_ontvangen - vorige_ontvangen

                db.execute(
                    "UPDATE bestelregels SET aantal_ontvangen = ? WHERE id = ?",
                    (aantal_ontvangen, regel["id"]),
                )
                if delta != 0:
                    db.execute(
                        "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                        (delta, regel["product_id"]),
                    )

                # Mutatie voor deze regel opnieuw opbouwen, zodat de geschiedenis
                # ook na een correctie het actuele ontvangen aantal weerspiegelt.
                db.execute(
                    "DELETE FROM mutaties WHERE bestelling_id = ? AND product_id = ?",
                    (bestelling_id, regel["product_id"]),
                )
                if aantal_ontvangen > 0:
                    db.execute(
                        """INSERT INTO mutaties
                           (product_id, type, aantal, datum, naam, opmerking, bestelling_id)
                           VALUES (?, 'in', ?, ?, ?, ?, ?)""",
                        (
                            regel["product_id"],
                            aantal_ontvangen,
                            now_str(),
                            naam,
                            "Ontvangen uit bestelling (aangepast)"
                            if was_al_ontvangen
                            else "Ontvangen uit bestelling",
                            bestelling_id,
                        ),
                    )

            if was_al_ontvangen:
                db.commit()
                flash("Bestelling aangepast en voorraad bijgewerkt.", "success")
            else:
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

    @app.route("/bestellingen/<int:bestelling_id>/verwijderen", methods=["POST"])
    def bestelling_verwijderen(bestelling_id):
        db = get_db()
        bestelling = db.execute(
            "SELECT * FROM bestellingen WHERE id = ?", (bestelling_id,)
        ).fetchone()
        if bestelling is None:
            flash("Bestelling niet gevonden.", "error")
            return redirect(url_for("bestellijst"))

        regels = db.execute(
            "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling_id,)
        ).fetchall()
        for regel in regels:
            ontvangen = regel["aantal_ontvangen"] or 0
            if ontvangen > 0:
                db.execute(
                    "UPDATE producten SET voorraad = voorraad - ? WHERE id = ?",
                    (ontvangen, regel["product_id"]),
                )

        db.execute("DELETE FROM mutaties WHERE bestelling_id = ?", (bestelling_id,))
        db.execute("DELETE FROM bestellingen WHERE id = ?", (bestelling_id,))
        db.commit()
        flash(f"Bestelling #{bestelling_id} verwijderd.", "success")
        return redirect(url_for("bestellijst"))

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
