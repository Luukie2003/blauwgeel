import hashlib
import re
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
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import backup as backup_module
import mail
from database import get_db, init_db, register_db
from pdf import bestellijst_pdf, periode_verkoop_pdf, verkoop_pdf, voorraadoverzicht_pdf

BASE_DIR = Path(__file__).parent
SECRET_KEY_PATH = BASE_DIR / "secret_key.txt"
BACKUP_BESTANDSNAAM = re.compile(
    r"^voorraad-(\d{4}-\d{2}-\d{2}|voor-herstel-\d{8}-\d{6})\.db$"
)

OPEN_ENDPOINTS = {"login", "static", "favicon_ico", "wachtwoord_vergeten", "wachtwoord_instellen"}

# Routes die alleen voor de rol 'beheerder' toegankelijk zijn. Vrijwilligers
# komen hier niet in -- zij kunnen de dagelijkse operatie doen (tellen,
# boeken, bestellijst, bijzonderheden) maar niet het assortiment, accounts,
# categorieën of back-ups beheren.
BEHEERDER_ENDPOINTS = {
    "accounts_lijst",
    "account_nieuw",
    "account_verwijderen",
    "account_rol_wijzigen",
    "account_email_wijzigen",
    "categorieen_lijst",
    "categorie_verwijderen",
    "subcategorie_nieuw",
    "subcategorie_verwijderen",
    "backups_lijst",
    "backup_nu",
    "backup_download",
    "backup_herstellen",
    "product_nieuw",
    "product_bewerken",
    "product_verwijderen",
    "product_actief_wisselen",
    "producten_minimumvoorraad",
    "producten_besteleenheid",
    "instellingen_pagina",
}

NAV_ITEMS = [
    {
        "endpoints": ["dashboard"],
        "url_endpoint": "dashboard",
        "label": "Overzicht",
    },
    {
        "endpoints": ["voorraadoverzicht"],
        "url_endpoint": "voorraadoverzicht",
        "label": "Voorraadoverzicht",
    },
    {
        "endpoints": [
            "producten_lijst",
            "product_nieuw",
            "product_bewerken",
            "categorieen_lijst",
            "producten_minimumvoorraad",
            "producten_besteleenheid",
        ],
        "url_endpoint": "producten_lijst",
        "label": "Producten",
    },
    {
        "endpoints": ["boeken", "levering_inboeken"],
        "url_endpoint": "boeken",
        "label": "In/uit boeken",
    },
    {
        "endpoints": [
            "tellen",
            "tellen_lopen",
            "tellen_lopen_starten",
            "tellen_lopen_controleren",
        ],
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
    {
        "endpoints": ["bijzonderheden"],
        "url_endpoint": "bijzonderheden",
        "label": "Bijzonderheden",
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
    app.jinja_env.filters["besteleenheid_naam"] = besteleenheid_naam
    app.jinja_env.filters["naar_besteleenheden"] = naar_besteleenheden

    @app.before_request
    def vereis_login():
        if request.endpoint in OPEN_ENDPOINTS or request.endpoint is None:
            return None
        if "gebruiker_id" not in session:
            return redirect(url_for("login", next=request.path))
        if "gebruiker_rol" not in session:
            # Sessie is aangemaakt voor rollen bestonden (of anderszins
            # verouderd) -- rol alsnog ophalen zodat je niet handmatig
            # hoeft uit/in te loggen na een update.
            db = get_db()
            gebruiker = db.execute(
                "SELECT rol FROM gebruikers WHERE id = ?", (session["gebruiker_id"],)
            ).fetchone()
            if gebruiker is None:
                session.clear()
                return redirect(url_for("login", next=request.path))
            session["gebruiker_rol"] = gebruiker["rol"]
        if request.endpoint in BEHEERDER_ENDPOINTS and session.get("gebruiker_rol") != "beheerder":
            flash("Deze pagina is alleen voor beheerders.", "error")
            return redirect(url_for("dashboard"))
        return None

    @app.context_processor
    def inject_nav():
        actieve_nav = next(
            (item for item in NAV_ITEMS if request.endpoint in item["endpoints"]),
            None,
        )
        banner_tekst = None
        if "gebruiker_id" in session:
            rij = get_db().execute(
                "SELECT banner_tekst FROM instellingen WHERE id = 1"
            ).fetchone()
            banner_tekst = rij["banner_tekst"] if rij else None
        return {
            "nav_items": NAV_ITEMS,
            "actieve_nav": actieve_nav,
            "huidige_gebruiker": session.get("gebruiker_naam"),
            "huidige_gebruiker_rol": session.get("gebruiker_rol"),
            "css_versie": int((BASE_DIR / "static" / "style.css").stat().st_mtime),
            "site_banner_tekst": banner_tekst,
        }

    @app.route("/favicon.ico")
    def favicon_ico():
        return send_from_directory(app.static_folder, "favicon.ico")

    @app.errorhandler(404)
    def pagina_niet_gevonden(fout):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def interne_fout(fout):
        return render_template("500.html"), 500

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


def genereer_wachtwoord_token(db, gebruiker_id, geldig_uren):
    """Maakt een eenmalige, tijdelijke link-token om een wachtwoord in te
    stellen (gebruikt voor zowel account-activatie als wachtwoord-vergeten).
    Er wordt alleen een hash van de token opgeslagen -- niet de token zelf --
    zodat een gelekte database-backup geen bruikbare inlogtokens bevat."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    verloopt = (datetime.now() + timedelta(hours=geldig_uren)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        "UPDATE gebruikers SET reset_token_hash = ?, reset_token_verloopt = ? WHERE id = ?",
        (token_hash, verloopt, gebruiker_id),
    )
    db.commit()
    return token


def vind_gebruiker_bij_token(db, token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    gebruiker = db.execute(
        "SELECT * FROM gebruikers WHERE reset_token_hash = ?", (token_hash,)
    ).fetchone()
    if gebruiker is None or not gebruiker["reset_token_verloopt"]:
        return None
    verloopt = datetime.strptime(gebruiker["reset_token_verloopt"], "%Y-%m-%d %H:%M")
    if verloopt < datetime.now():
        return None
    return gebruiker


def besteleenheid_naam(product):
    return product["besteleenheid"] or product["eenheid"]


def besteleenheid_factor(product):
    factor = product["besteleenheid_factor"] or 1
    return factor if factor > 0 else 1


def naar_besteleenheden(aantal_voorraadeenheden, product):
    """Rondt naar boven af naar hele besteleenheden (je bestelt geen halve krat)."""
    factor = besteleenheid_factor(product)
    return -(-max(0, aantal_voorraadeenheden) // factor)


def naar_voorraadeenheden(aantal_besteleenheden, product):
    return max(0, aantal_besteleenheden) * besteleenheid_factor(product)


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


def bereken_omzet_trend_periode(db, van, tot):
    """Omzet + best verkopende producten voor alle tellingen binnen een zelf
    gekozen periode -- gebruikt door het verkooprapport en het weekoverzicht.
    Rekent met de bevroren telling-prijs (tr.verkoopprijs), niet de actuele
    productprijs, zodat latere prijswijzigingen oude cijfers niet aanpassen."""
    tellingen = db.execute(
        """SELECT t.id, t.datum, t.naam,
                  COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
           FROM tellingen t
           LEFT JOIN telling_regels tr ON tr.telling_id = t.id
           WHERE t.datum >= ? AND t.datum <= ?
           GROUP BY t.id
           ORDER BY t.datum""",
        (f"{van} 00:00", f"{tot} 23:59"),
    ).fetchall()

    top_verkopers = []
    if tellingen:
        telling_ids = [t["id"] for t in tellingen]
        placeholders = ",".join("?" for _ in telling_ids)
        top_verkopers = db.execute(
            f"""SELECT p.naam AS product_naam, p.eenheid,
                       SUM(tr.verkocht) AS verkocht,
                       SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                FROM telling_regels tr
                JOIN producten p ON p.id = tr.product_id
                WHERE tr.telling_id IN ({placeholders})
                GROUP BY tr.product_id
                HAVING verkocht > 0
                ORDER BY omzet DESC
                LIMIT 6""",
            telling_ids,
        ).fetchall()

    max_omzet = max((t["omzet"] for t in tellingen), default=0)
    totale_omzet = sum(t["omzet"] for t in tellingen)

    balken = [
        {
            "datum_kort": datetime.strptime(t["datum"], "%Y-%m-%d %H:%M").strftime("%d-%m"),
            "omzet": t["omzet"],
            "hoogte_pct": (t["omzet"] / max_omzet * 100) if max_omzet else 0,
        }
        for t in tellingen
    ]

    return {
        "balken": balken,
        "top_verkopers": top_verkopers,
        "totale_omzet": totale_omzet,
    }


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


def bereken_week_overzicht(db, vandaag=None):
    """Overzicht van de meest recente volledig afgesloten week (maandag t/m
    zondag): omzet met vergelijking t.o.v. de week ervoor, top verkopers, en
    producten onder minimumvoorraad. Wordt zowel gebruikt voor de
    weekoverzicht-pagina als voor het wekelijkse e-mailtje (elke maandag)."""
    vandaag = vandaag or datetime.now().date()
    deze_week_maandag = vandaag - timedelta(days=vandaag.weekday())
    week_tot = deze_week_maandag - timedelta(days=1)
    week_van = week_tot - timedelta(days=6)
    vorige_week_tot = week_van - timedelta(days=1)
    vorige_week_van = vorige_week_tot - timedelta(days=6)

    huidige = bereken_omzet_trend_periode(db, week_van.isoformat(), week_tot.isoformat())
    vorige = bereken_omzet_trend_periode(
        db, vorige_week_van.isoformat(), vorige_week_tot.isoformat()
    )

    verschil_percentage = None
    if vorige["totale_omzet"] > 0:
        verschil_percentage = (
            (huidige["totale_omzet"] - vorige["totale_omzet"]) / vorige["totale_omzet"] * 100
        )

    open_bestellingen = db.execute(
        "SELECT * FROM bestellingen WHERE status = 'besteld' ORDER BY aangemaakt_op"
    ).fetchall()

    nieuwe_mededelingen = db.execute(
        "SELECT * FROM mededelingen WHERE datum >= ? AND datum <= ? ORDER BY id DESC",
        (f"{week_van.isoformat()} 00:00", f"{week_tot.isoformat()} 23:59"),
    ).fetchall()

    zonder_prijs = db.execute(
        """SELECT * FROM producten
           WHERE actief = 1 AND (verkoopprijs = 0 OR inkoopprijs = 0)
           ORDER BY categorie, naam"""
    ).fetchall()

    return {
        "week_van": week_van,
        "week_tot": week_tot,
        "totale_omzet": huidige["totale_omzet"],
        "vorige_omzet": vorige["totale_omzet"],
        "verschil_percentage": verschil_percentage,
        "top_verkopers": huidige["top_verkopers"],
        "onder_minimum": bestel_suggesties(db),
        "open_bestellingen": open_bestellingen,
        "nieuwe_mededelingen": nieuwe_mededelingen,
        "zonder_prijs": zonder_prijs,
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
                session["gebruiker_rol"] = gebruiker["rol"]
                db.execute(
                    "UPDATE gebruikers SET laatste_login = ? WHERE id = ?",
                    (now_str(), gebruiker["id"]),
                )
                db.commit()
                volgende = request.args.get("next") or url_for("dashboard")
                return redirect(volgende)
            flash("Onjuiste naam of wachtwoord.", "error")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Je bent uitgelogd.", "success")
        return redirect(url_for("login"))

    @app.route("/wachtwoord-vergeten", methods=["GET", "POST"])
    def wachtwoord_vergeten():
        if request.method == "POST":
            identificatie = request.form.get("naam_of_email", "").strip()
            db = get_db()
            gebruiker = db.execute(
                "SELECT * FROM gebruikers WHERE naam = ? OR email = ?",
                (identificatie, identificatie),
            ).fetchone()
            if gebruiker and gebruiker["email"]:
                token = genereer_wachtwoord_token(db, gebruiker["id"], geldig_uren=24)
                link = url_for("wachtwoord_instellen", token=token, _external=True)
                mail.stuur_mail(
                    "Wachtwoord opnieuw instellen -- Kantine Beheer",
                    f"Hoi {gebruiker['naam']},\n\n"
                    f"Er is een verzoek gedaan om je wachtwoord opnieuw in te stellen.\n"
                    f"Gebruik onderstaande link om een nieuw wachtwoord te kiezen "
                    f"(deze link is 24 uur geldig):\n\n"
                    f"{link}\n\n"
                    f"Heb je dit zelf niet aangevraagd? Dan kun je deze e-mail negeren.",
                    naar=gebruiker["email"],
                )
            flash(
                "Als dit account bestaat en er een e-mailadres bekend is, is er een "
                "e-mail met een link verstuurd.",
                "success",
            )
            return redirect(url_for("login"))

        return render_template("wachtwoord_vergeten.html")

    @app.route("/wachtwoord-instellen/<token>", methods=["GET", "POST"])
    def wachtwoord_instellen(token):
        db = get_db()
        gebruiker = vind_gebruiker_bij_token(db, token)
        if gebruiker is None:
            flash("Deze link is ongeldig of verlopen. Vraag een nieuwe aan.", "error")
            return redirect(url_for("wachtwoord_vergeten"))

        if request.method == "POST":
            nieuw = request.form.get("nieuw_wachtwoord", "")
            nieuw_herhaald = request.form.get("nieuw_wachtwoord_herhaald", "")
            if len(nieuw) < 4:
                flash("Wachtwoord moet minstens 4 tekens zijn.", "error")
            elif nieuw != nieuw_herhaald:
                flash("De wachtwoorden komen niet overeen.", "error")
            else:
                db.execute(
                    """UPDATE gebruikers
                       SET wachtwoord_hash = ?, reset_token_hash = NULL, reset_token_verloopt = NULL
                       WHERE id = ?""",
                    (generate_password_hash(nieuw, method="pbkdf2:sha256"), gebruiker["id"]),
                )
                db.execute(
                    "UPDATE gebruikers SET laatste_login = ? WHERE id = ?",
                    (now_str(), gebruiker["id"]),
                )
                db.commit()
                session.clear()
                session["gebruiker_id"] = gebruiker["id"]
                session["gebruiker_naam"] = gebruiker["naam"]
                session["gebruiker_rol"] = gebruiker["rol"]
                flash("Wachtwoord ingesteld. Je bent nu ingelogd.", "success")
                return redirect(url_for("dashboard"))

        return render_template("wachtwoord_instellen.html", gebruiker=gebruiker, token=token)

    @app.route("/accounts")
    def accounts_lijst():
        db = get_db()
        gebruikers = db.execute(
            "SELECT id, naam, email, rol, aangemaakt_op, laatste_login FROM gebruikers ORDER BY naam"
        ).fetchall()
        aantal_beheerders = db.execute(
            "SELECT COUNT(*) AS n FROM gebruikers WHERE rol = 'beheerder'"
        ).fetchone()["n"]
        return render_template(
            "accounts.html", gebruikers=gebruikers, aantal_beheerders=aantal_beheerders
        )

    @app.route("/accounts/nieuw", methods=["POST"])
    def account_nieuw():
        naam = request.form.get("naam", "").strip()
        email = request.form.get("email", "").strip()
        rol = request.form.get("rol", "vrijwilliger")
        if rol not in ("beheerder", "vrijwilliger"):
            rol = "vrijwilliger"
        db = get_db()

        if not naam or not email:
            flash("Naam en e-mailadres zijn verplicht.", "error")
        elif db.execute("SELECT id FROM gebruikers WHERE naam = ?", (naam,)).fetchone():
            flash(f"Er bestaat al een account met de naam '{naam}'.", "error")
        else:
            onbruikbaar_wachtwoord = generate_password_hash(
                secrets.token_hex(16), method="pbkdf2:sha256"
            )
            cursor = db.execute(
                """INSERT INTO gebruikers (naam, email, wachtwoord_hash, rol, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?)""",
                (naam, email, onbruikbaar_wachtwoord, rol, now_str()),
            )
            db.commit()
            token = genereer_wachtwoord_token(db, cursor.lastrowid, geldig_uren=72)
            link = url_for("wachtwoord_instellen", token=token, _external=True)
            mail.stuur_mail(
                "Welkom bij Kantine Beheer",
                f"Hoi {naam},\n\n"
                f"Er is een account voor je aangemaakt in het voorraadsysteem van de kantine.\n"
                f"Kies via onderstaande link je eigen wachtwoord (deze link is 72 uur geldig):\n\n"
                f"{link}\n\n"
                f"Je gebruikersnaam is: {naam}",
                naar=email,
            )
            flash(
                f"Account '{naam}' aangemaakt. Er is een e-mail verstuurd naar {email} "
                "om een wachtwoord in te stellen.",
                "success",
            )
        return redirect(url_for("accounts_lijst"))

    @app.route("/accounts/<int:gebruiker_id>/email", methods=["POST"])
    def account_email_wijzigen(gebruiker_id):
        db = get_db()
        email = request.form.get("email", "").strip()
        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        if gebruiker is None:
            flash("Account niet gevonden.", "error")
        else:
            db.execute(
                "UPDATE gebruikers SET email = ? WHERE id = ?", (email or None, gebruiker_id)
            )
            db.commit()
            flash(f"E-mailadres van '{gebruiker['naam']}' bijgewerkt.", "success")
        return redirect(url_for("accounts_lijst"))

    @app.route("/accounts/<int:gebruiker_id>/rol", methods=["POST"])
    def account_rol_wijzigen(gebruiker_id):
        db = get_db()
        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        if gebruiker is None:
            flash("Account niet gevonden.", "error")
            return redirect(url_for("accounts_lijst"))

        nieuwe_rol = "vrijwilliger" if gebruiker["rol"] == "beheerder" else "beheerder"
        if gebruiker["rol"] == "beheerder" and nieuwe_rol == "vrijwilliger":
            aantal_beheerders = db.execute(
                "SELECT COUNT(*) AS n FROM gebruikers WHERE rol = 'beheerder'"
            ).fetchone()["n"]
            if aantal_beheerders <= 1:
                flash(
                    "Dit is de laatste beheerder -- er moet altijd minstens één overblijven.",
                    "error",
                )
                return redirect(url_for("accounts_lijst"))

        db.execute("UPDATE gebruikers SET rol = ? WHERE id = ?", (nieuwe_rol, gebruiker_id))
        db.commit()
        flash(f"'{gebruiker['naam']}' is nu {nieuwe_rol}.", "success")
        return redirect(url_for("accounts_lijst"))

    @app.route("/accounts/<int:gebruiker_id>/verwijderen", methods=["POST"])
    def account_verwijderen(gebruiker_id):
        db = get_db()
        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        aantal = db.execute("SELECT COUNT(*) AS n FROM gebruikers").fetchone()["n"]
        if gebruiker is None:
            flash("Account niet gevonden.", "error")
        elif aantal <= 1:
            flash("Je kunt het laatste account niet verwijderen.", "error")
        elif gebruiker_id == session.get("gebruiker_id"):
            flash("Je kunt je eigen account niet verwijderen terwijl je bent ingelogd.", "error")
        elif gebruiker["rol"] == "beheerder" and db.execute(
            "SELECT COUNT(*) AS n FROM gebruikers WHERE rol = 'beheerder'"
        ).fetchone()["n"] <= 1:
            flash(
                "Dit is de laatste beheerder -- er moet altijd minstens één overblijven.",
                "error",
            )
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

    @app.route("/account/voorkeuren", methods=["GET", "POST"])
    def account_voorkeuren():
        db = get_db()
        gebruiker_id = session["gebruiker_id"]
        if request.method == "POST":
            db.execute(
                "UPDATE gebruikers SET mail_factuur = ?, mail_week_overzicht = ? WHERE id = ?",
                (
                    1 if request.form.get("mail_factuur") else 0,
                    1 if request.form.get("mail_week_overzicht") else 0,
                    gebruiker_id,
                ),
            )
            db.commit()
            flash("Voorkeuren opgeslagen.", "success")
            return redirect(url_for("account_voorkeuren"))

        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        return render_template("account_voorkeuren.html", gebruiker=gebruiker)

    @app.route("/help")
    def help_pagina():
        return render_template("help.html")

    # ---------- Instellingen ----------

    @app.route("/instellingen", methods=["GET", "POST"])
    def instellingen_pagina():
        db = get_db()
        if request.method == "POST":
            notificatie_email = request.form.get("notificatie_email", "").strip()
            banner_tekst = request.form.get("banner_tekst", "").strip()
            db.execute(
                "UPDATE instellingen SET notificatie_email = ?, banner_tekst = ? WHERE id = 1",
                (notificatie_email or None, banner_tekst or None),
            )
            db.commit()
            flash("Instellingen opgeslagen.", "success")
            return redirect(url_for("instellingen_pagina"))

        rij = db.execute(
            "SELECT notificatie_email, banner_tekst FROM instellingen WHERE id = 1"
        ).fetchone()
        return render_template(
            "instellingen.html",
            notificatie_email=rij["notificatie_email"] if rij else None,
            banner_tekst=rij["banner_tekst"] if rij else None,
        )

    # ---------- Back-ups ----------

    @app.route("/backups")
    def backups_lijst():
        backup_module.BACKUP_MAP.mkdir(exist_ok=True)
        bestanden = sorted(
            backup_module.BACKUP_MAP.glob("voorraad-*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        backups = [
            {
                "naam": b.name,
                "grootte_kb": round(b.stat().st_size / 1024, 1),
                "datum": datetime.fromtimestamp(b.stat().st_mtime).strftime(
                    "%d-%m-%Y %H:%M"
                ),
            }
            for b in bestanden
        ]
        return render_template("backups.html", backups=backups)

    @app.route("/backups/nu", methods=["POST"])
    def backup_nu():
        resultaat = backup_module.maak_backup()
        if resultaat is None:
            flash("Nog geen voorraad.db aanwezig om te back-uppen.", "error")
        else:
            flash(f"Back-up gemaakt: {resultaat.name}", "success")
        return redirect(url_for("backups_lijst"))

    @app.route("/backups/<bestandsnaam>/download")
    def backup_download(bestandsnaam):
        if not BACKUP_BESTANDSNAAM.match(bestandsnaam):
            flash("Ongeldige back-up.", "error")
            return redirect(url_for("backups_lijst"))
        return send_from_directory(
            backup_module.BACKUP_MAP, bestandsnaam, as_attachment=True
        )

    @app.route("/backups/<bestandsnaam>/herstellen", methods=["POST"])
    def backup_herstellen(bestandsnaam):
        if not BACKUP_BESTANDSNAAM.match(bestandsnaam):
            flash("Ongeldige back-up.", "error")
            return redirect(url_for("backups_lijst"))

        veiligheidskopie_naam = (
            f"voorraad-voor-herstel-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        )
        backup_module.maak_backup_met_naam(veiligheidskopie_naam)

        if backup_module.herstel_backup(bestandsnaam):
            flash(
                f"Database hersteld vanaf '{bestandsnaam}'. De staat van vlak "
                f"hiervoor is bewaard als '{veiligheidskopie_naam}', voor het "
                f"geval je dit ongedaan wilt maken.",
                "success",
            )
        else:
            flash("Herstellen is mislukt -- back-up niet gevonden.", "error")
        return redirect(url_for("dashboard"))

    # ---------- Overzicht ----------

    def bereken_omzet_trend(db, aantal_tellingen=8):
        """Omzet per telling (chronologisch) plus de best verkopende producten
        over die periode -- gebruikt voor het trendgrafiekje op het dashboard.
        Rekent altijd met de bevroren telling-prijs (tr.verkoopprijs), niet de
        actuele productprijs, om dezelfde reden als het verkooprapport."""
        ruwe_tellingen = db.execute(
            """SELECT t.id, t.datum, t.naam,
                      COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
               FROM tellingen t
               LEFT JOIN telling_regels tr ON tr.telling_id = t.id
               GROUP BY t.id
               ORDER BY t.datum DESC
               LIMIT ?""",
            (aantal_tellingen,),
        ).fetchall()
        tellingen = list(reversed(ruwe_tellingen))

        top_verkopers = []
        if tellingen:
            telling_ids = [t["id"] for t in tellingen]
            placeholders = ",".join("?" for _ in telling_ids)
            top_verkopers = db.execute(
                f"""SELECT p.naam AS product_naam, p.eenheid,
                           SUM(tr.verkocht) AS verkocht,
                           SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                    FROM telling_regels tr
                    JOIN producten p ON p.id = tr.product_id
                    WHERE tr.telling_id IN ({placeholders})
                    GROUP BY tr.product_id
                    HAVING verkocht > 0
                    ORDER BY omzet DESC
                    LIMIT 6""",
                telling_ids,
            ).fetchall()

        max_omzet = max((t["omzet"] for t in tellingen), default=0)
        laatste_omzet = tellingen[-1]["omzet"] if tellingen else 0
        eerdere_omzetten = [t["omzet"] for t in tellingen[:-1]]
        gemiddelde_omzet = (
            sum(eerdere_omzetten) / len(eerdere_omzetten) if eerdere_omzetten else 0
        )
        verschil_percentage = None
        if gemiddelde_omzet > 0:
            verschil_percentage = (laatste_omzet - gemiddelde_omzet) / gemiddelde_omzet * 100

        balken = [
            {
                "datum_kort": datetime.strptime(t["datum"], "%Y-%m-%d %H:%M").strftime("%d-%m"),
                "omzet": t["omzet"],
                "hoogte_pct": (t["omzet"] / max_omzet * 100) if max_omzet else 0,
            }
            for t in tellingen
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
        return render_template(
            "dashboard.html",
            producten=producten,
            laag=laag,
            recente_mutaties=recente_mutaties,
            open_bestellingen=open_bestellingen,
            omzet_trend=omzet_trend,
        )

    def bereken_voorraadoverzicht(db):
        """Verzamelt alle cijfers voor het voorraadoverzicht -- gebruikt door
        zowel de webpagina als de PDF, zodat ze altijd hetzelfde tonen."""
        producten = db.execute("SELECT * FROM producten ORDER BY categorie, naam").fetchall()

        totale_waarde = sum(p["voorraad"] * p["verkoopprijs"] for p in producten)
        zonder_voorraad = [p for p in producten if p["actief"] and p["voorraad"] == 0]
        onder_minimum = [p for p in producten if p["actief"] and p["voorraad"] < p["min_voorraad"]]
        zonder_prijs = [p for p in producten if p["actief"] and p["verkoopprijs"] == 0]
        inactief_met_voorraad = [p for p in producten if not p["actief"] and p["voorraad"] > 0]

        per_categorie = {}
        for p in producten:
            c = per_categorie.setdefault(p["categorie"], {"aantal": 0, "waarde": 0.0})
            c["aantal"] += 1
            c["waarde"] += p["voorraad"] * p["verkoopprijs"]
        categorie_lijst = sorted(
            [
                {
                    "naam": naam,
                    "aantal": info["aantal"],
                    "waarde": info["waarde"],
                    "percentage": (info["waarde"] / totale_waarde * 100) if totale_waarde else 0,
                }
                for naam, info in per_categorie.items()
            ],
            key=lambda x: x["waarde"],
            reverse=True,
        )

        top_waarde = sorted(
            producten, key=lambda p: p["voorraad"] * p["verkoopprijs"], reverse=True
        )[:10]

        laatste_tellingen = db.execute(
            """SELECT tr.product_id, MAX(t.datum) AS laatste_datum
               FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
               GROUP BY tr.product_id"""
        ).fetchall()
        laatste_per_product = {r["product_id"]: r["laatste_datum"] for r in laatste_tellingen}
        nooit_geteld = [p for p in producten if p["actief"] and p["id"] not in laatste_per_product]
        langst_niet_geteld = sorted(
            (
                {"product": p, "laatste_datum": laatste_per_product[p["id"]]}
                for p in producten
                if p["id"] in laatste_per_product
            ),
            key=lambda x: x["laatste_datum"],
        )[:5]

        return {
            "producten": producten,
            "totale_waarde": totale_waarde,
            "aantal_producten": len(producten),
            "aantal_categorieen": len(per_categorie),
            "zonder_voorraad": zonder_voorraad,
            "onder_minimum": onder_minimum,
            "zonder_prijs": zonder_prijs,
            "inactief_met_voorraad": inactief_met_voorraad,
            "nooit_geteld": nooit_geteld,
            "categorie_lijst": categorie_lijst,
            "top_waarde": top_waarde,
            "langst_niet_geteld": langst_niet_geteld,
        }

    @app.route("/voorraadoverzicht")
    def voorraadoverzicht():
        db = get_db()
        return render_template(
            "voorraadoverzicht.html", **bereken_voorraadoverzicht(db)
        )

    @app.route("/voorraadoverzicht/pdf")
    def voorraadoverzicht_pdf_route():
        db = get_db()
        gegevens = bereken_voorraadoverzicht(db)
        pdf_bytes = voorraadoverzicht_pdf(gegevens)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=voorraadoverzicht.pdf"},
        )

    # ---------- Producten ----------

    @app.route("/producten")
    def producten_lijst():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, subcategorie, naam"
        ).fetchall()
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = db.execute(
            "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
        ).fetchall()
        return render_template(
            "producten.html",
            producten=producten,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
        )

    @app.route("/producten/minimumvoorraad", methods=["GET", "POST"])
    def producten_minimumvoorraad():
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            aangepast = 0
            for p in producten:
                waarde = request.form.get(f"min_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    nieuw_minimum = int(waarde)
                except ValueError:
                    continue
                if nieuw_minimum < 0:
                    continue
                db.execute(
                    "UPDATE producten SET min_voorraad = ? WHERE id = ?",
                    (nieuw_minimum, p["id"]),
                )
                aangepast += 1
            db.commit()
            flash(f"Minimumvoorraad bijgewerkt voor {aangepast} product(en).", "success")
            return redirect(url_for("producten_minimumvoorraad"))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, naam"
        ).fetchall()
        return render_template("producten_minimum.html", producten=producten)

    @app.route("/producten/besteleenheid", methods=["GET", "POST"])
    def producten_besteleenheid():
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            aangepast = 0
            for p in producten:
                eenheid_waarde = request.form.get(f"eenheid_{p['id']}", "").strip()
                factor_waarde = request.form.get(f"factor_{p['id']}", "").strip()
                if factor_waarde == "":
                    continue
                try:
                    nieuwe_factor = int(factor_waarde)
                except ValueError:
                    continue
                if nieuwe_factor < 1:
                    continue
                db.execute(
                    "UPDATE producten SET besteleenheid = ?, besteleenheid_factor = ? WHERE id = ?",
                    (eenheid_waarde or None, nieuwe_factor, p["id"]),
                )
                aangepast += 1
            db.commit()
            flash(f"Besteleenheid bijgewerkt voor {aangepast} product(en).", "success")
            return redirect(url_for("producten_besteleenheid"))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, naam"
        ).fetchall()
        return render_template("producten_besteleenheid.html", producten=producten)

    @app.route("/producten/nieuw", methods=["GET", "POST"])
    def product_nieuw():
        db = get_db()
        if request.method == "POST":
            db.execute(
                """INSERT INTO producten
                   (artikelcode, naam, categorie, subcategorie, eenheid, voorraad, min_voorraad,
                    bestel_hoeveelheid, verkoopprijs, inkoopprijs, actief, besteleenheid,
                    besteleenheid_factor, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.form.get("artikelcode", "").strip() or None,
                    request.form["naam"].strip(),
                    request.form["categorie"].strip() or "Overig",
                    request.form.get("subcategorie", "").strip() or None,
                    request.form["eenheid"].strip() or "stuks",
                    int(request.form["voorraad"] or 0),
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    float(request.form.get("inkoopprijs") or 0),
                    1 if request.form.get("actief") else 0,
                    request.form.get("besteleenheid", "").strip() or None,
                    int(request.form.get("besteleenheid_factor") or 1),
                    request.form.get("opmerking", "").strip(),
                ),
            )
            db.commit()
            flash(f"Product '{request.form['naam']}' toegevoegd.", "success")
            return redirect(url_for("producten_lijst"))
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = db.execute(
            "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
        ).fetchall()
        return render_template(
            "product_form.html",
            product=None,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
        )

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
                   SET artikelcode = ?, naam = ?, categorie = ?, subcategorie = ?, eenheid = ?,
                       voorraad = ?, min_voorraad = ?, bestel_hoeveelheid = ?, verkoopprijs = ?,
                       inkoopprijs = ?, actief = ?, besteleenheid = ?, besteleenheid_factor = ?,
                       opmerking = ?
                   WHERE id = ?""",
                (
                    request.form.get("artikelcode", "").strip() or None,
                    request.form["naam"].strip(),
                    request.form["categorie"].strip() or "Overig",
                    request.form.get("subcategorie", "").strip() or None,
                    request.form["eenheid"].strip() or "stuks",
                    int(request.form["voorraad"] or 0),
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    float(request.form.get("inkoopprijs") or 0),
                    1 if request.form.get("actief") else 0,
                    request.form.get("besteleenheid", "").strip() or None,
                    int(request.form.get("besteleenheid_factor") or 1),
                    request.form.get("opmerking", "").strip(),
                    product_id,
                ),
            )
            db.commit()
            flash(f"Product '{request.form['naam']}' bijgewerkt.", "success")
            return redirect(url_for("producten_lijst"))
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = db.execute(
            "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
        ).fetchall()
        return render_template(
            "product_form.html",
            product=product,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
        )

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

    # Endpoints waar het snel-toevoegen-formulier (pop-up) naar mag
    # terugsturen. Whitelist i.p.v. een vrije URL, om open redirects te voorkomen.
    TERUG_NAAR_ENDPOINTS = {
        "levering_inboeken": "levering_inboeken",
        "producten_lijst": "producten_lijst",
    }

    @app.route("/producten/snel-toevoegen", methods=["POST"])
    def product_snel_toevoegen():
        db = get_db()
        terug_naar = TERUG_NAAR_ENDPOINTS.get(
            request.form.get("terug_naar", ""), "producten_lijst"
        )
        naam = request.form.get("naam", "").strip()

        if not naam:
            flash("Naam is verplicht.", "error")
            return redirect(url_for(terug_naar))

        db.execute(
            """INSERT INTO producten
               (artikelcode, naam, categorie, eenheid, voorraad, min_voorraad,
                bestel_hoeveelheid, verkoopprijs, actief, besteleenheid,
                besteleenheid_factor, opmerking)
               VALUES (?, ?, ?, ?, 0, 0, 0, 0, 1, ?, ?, '')""",
            (
                request.form.get("artikelcode", "").strip() or None,
                naam,
                request.form.get("categorie", "").strip() or "Overig",
                request.form.get("eenheid", "").strip() or "stuks",
                request.form.get("besteleenheid", "").strip() or None,
                int(request.form.get("besteleenheid_factor") or 1),
            ),
        )
        db.commit()
        flash(f"Product '{naam}' toegevoegd. Vul hieronder het aantal in.", "success")
        return redirect(url_for(terug_naar))

    @app.route("/producten/<int:product_id>/actief", methods=["POST"])
    def product_actief_wisselen(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        nieuwe_status = 0 if product["actief"] else 1
        db.execute(
            "UPDATE producten SET actief = ? WHERE id = ?", (nieuwe_status, product_id)
        )
        db.commit()
        return redirect(url_for("producten_lijst"))

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

    # ---------- In / uit boeken ----------

    @app.route("/boeken", methods=["GET", "POST"])
    def boeken():
        db = get_db()
        if request.method == "POST":
            product_id = int(request.form["product_id"])
            mtype = request.form["type"]
            aantal = int(request.form["aantal"])
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
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
                """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_id, mtype, aantal, now_str(), naam, gebruiker_id, opmerking),
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

    @app.route("/leveringen/inboeken", methods=["GET", "POST"])
    def levering_inboeken():
        db = get_db()
        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            referentie = request.form.get("referentie", "").strip()
            datum_input = request.form.get("datum", "").strip()
            datum = datum_input.replace("T", " ") if datum_input else now_str()
            opmerking = (
                f"Levering ingeboekt ({referentie})" if referentie else "Levering ingeboekt"
            )

            producten = db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()

            geboekte_regels = []
            for p in producten:
                waarde = request.form.get(f"aantal_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    aantal_besteleenheden = int(waarde)
                except ValueError:
                    continue
                if aantal_besteleenheden <= 0:
                    continue
                aantal = naar_voorraadeenheden(aantal_besteleenheden, p)
                db.execute(
                    "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                    (aantal, p["id"]),
                )
                db.execute(
                    """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                       VALUES (?, 'in', ?, ?, ?, ?, ?)""",
                    (p["id"], aantal, datum, naam, gebruiker_id, opmerking),
                )
                geboekte_regels.append((p, aantal, aantal_besteleenheden))

            if not geboekte_regels:
                flash("Geen aantallen ingevuld -- er is niets ingeboekt.", "error")
                return redirect(url_for("levering_inboeken"))

            db.commit()
            flash(
                f"Levering ingeboekt: {len(geboekte_regels)} product(en) bijgewerkt.",
                "success",
            )

            regels_tekst = "\n".join(
                f"  - {p['naam']}: +{aantal_be} {besteleenheid_naam(p)} (= {aantal} {p['eenheid']})"
                for p, aantal, aantal_be in geboekte_regels
            )
            ontvangers = [
                r["email"]
                for r in db.execute(
                    """SELECT email FROM gebruikers
                       WHERE mail_factuur = 1 AND email IS NOT NULL AND email != ''"""
                ).fetchall()
            ]
            if not ontvangers:
                instelling = db.execute(
                    "SELECT notificatie_email FROM instellingen WHERE id = 1"
                ).fetchone()
                if instelling and instelling["notificatie_email"]:
                    ontvangers = [instelling["notificatie_email"]]

            onderwerp = f"Levering ingeboekt{f' -- {referentie}' if referentie else ''}"
            tekst = (
                f"Er is een levering ingeboekt in het voorraadsysteem.\n\n"
                f"Datum: {format_datum(datum)}\n"
                f"Door: {naam or 'onbekend'}\n"
                f"Referentie: {referentie or '-'}\n\n"
                f"Producten:\n{regels_tekst}"
            )
            for ontvanger in ontvangers:
                mail.stuur_mail(onderwerp, tekst, naar=ontvanger)

            return redirect(url_for("boeken"))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        return render_template(
            "levering_inboeken.html",
            producten=producten,
            categorieen=categorieen,
            nu_datetime_local=now_datetime_local(),
        )

    # ---------- Voorraad tellen ----------

    def verwerk_telling(db, waarden, naam, opmerking, datum, gebruiker_id=None):
        """waarden: dict {product_id: geteld_aantal}. Maakt een telling aan,
        berekent per product het verschil met de huidige voorraad, en werkt
        voorraad + geschiedenis bij. Retourneert het nieuwe telling_id, of
        None als er niets te verwerken viel."""
        if not waarden:
            return None

        cur = db.execute(
            "INSERT INTO tellingen (datum, naam, gebruiker_id, opmerking) VALUES (?, ?, ?, ?)",
            (datum, naam, gebruiker_id, opmerking),
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
                   (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht,
                    correctie, verkoopprijs)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    telling_id,
                    product_id,
                    product["voorraad"],
                    geteld,
                    verkocht,
                    correctie,
                    product["verkoopprijs"],
                ),
            )
            db.execute(
                "UPDATE producten SET voorraad = ? WHERE id = ?", (geteld, product_id)
            )
            if verkocht > 0:
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                       VALUES (?, 'uit', ?, ?, ?, ?, ?, ?)""",
                    (product_id, verkocht, datum, naam, gebruiker_id, f"Verkocht (telling #{telling_id})", telling_id),
                )
            elif correctie > 0:
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                       VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                    (product_id, correctie, datum, naam, gebruiker_id, f"Correctie (telling #{telling_id})", telling_id),
                )

        db.commit()
        return telling_id

    @app.route("/tellen", methods=["GET", "POST"])
    def tellen():
        db = get_db()
        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
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

            telling_id = verwerk_telling(db, waarden, naam, opmerking, datum, gebruiker_id)
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
                        # Bar en voorraadhok zijn allebei geteld: optellen en
                        # naar het controlescherm, nog niet meteen opslaan.
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
                                geparsed[pid_str] = geteld_totaal

                        if not geparsed:
                            for sleutel in LOOP_SESSIE_SLEUTELS:
                                session.pop(sleutel, None)
                            flash("Geen aantallen ingevuld -- er is niets geteld.", "error")
                            return redirect(url_for("tellen"))

                        session["loop_review"] = geparsed
                        session.pop("loop_fase", None)
                        session.pop("loop_index", None)
                        session.modified = True
                        return redirect(url_for("tellen_lopen_controleren"))

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

    @app.route("/tellen/lopen/controleren", methods=["GET", "POST"])
    def tellen_lopen_controleren():
        db = get_db()
        review = session.get("loop_review")
        if not review:
            return redirect(url_for("tellen"))

        if request.method == "POST":
            actie = request.form.get("actie", "bevestigen")
            if actie == "annuleren":
                for sleutel in list(LOOP_SESSIE_SLEUTELS) + ["loop_review"]:
                    session.pop(sleutel, None)
                flash("Looplijst afgebroken, er is niets opgeslagen.", "error")
                return redirect(url_for("tellen"))

            waarden = {}
            for product_id_str in review:
                tekst = request.form.get(f"totaal_{product_id_str}", "").strip()
                if tekst == "":
                    continue
                try:
                    aantal = int(tekst)
                except ValueError:
                    continue
                if aantal < 0:
                    continue
                waarden[int(product_id_str)] = aantal

            for sleutel in list(LOOP_SESSIE_SLEUTELS) + ["loop_review"]:
                session.pop(sleutel, None)

            telling_id = verwerk_telling(
                db,
                waarden,
                session.get("gebruiker_naam"),
                "Via looplijst geteld (bar + voorraadhok)",
                now_str(),
                session.get("gebruiker_id"),
            )
            if telling_id is None:
                flash("Geen aantallen ingevuld -- er is niets geteld.", "error")
                return redirect(url_for("tellen"))
            flash(
                f"Telling #{telling_id} bevestigd: {len(waarden)} product(en) opgeslagen.",
                "success",
            )
            return redirect(url_for("telling_detail", telling_id=telling_id))

        bar_waarden = session.get("loop_bar", {})
        hok_waarden = session.get("loop_hok", {})
        regels = []
        for product_id_str, totaal in review.items():
            product = db.execute(
                "SELECT * FROM producten WHERE id = ?", (int(product_id_str),)
            ).fetchone()
            if product is None:
                continue
            regels.append(
                {
                    "product": product,
                    "bar": bar_waarden.get(product_id_str, "") or "0",
                    "hok": hok_waarden.get(product_id_str, "") or "0",
                    "totaal": totaal,
                }
            )
        regels.sort(key=lambda r: (r["product"]["categorie"], r["product"]["naam"]))

        return render_template("tellen_lopen_controleren.html", regels=regels)

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

        verkoop_regels = db.execute(
            """SELECT t.datum, tr.verkocht, tr.verkoopprijs
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
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
            """SELECT tr.*, p.naam AS product_naam, p.eenheid
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
            """SELECT p.naam AS product_naam, p.categorie, p.eenheid,
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

    # ---------- Bestellijst ----------

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
                """SELECT br.*, p.naam AS product_naam, p.eenheid,
                          p.besteleenheid, p.besteleenheid_factor
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
                """SELECT br.*, p.naam AS product_naam, p.eenheid,
                          p.besteleenheid, p.besteleenheid_factor
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
        besteld_door = session.get("gebruiker_naam")
        besteld_door_id = session.get("gebruiker_id")

        regels = []
        for pid in product_ids:
            aantal_besteleenheden = request.form.get(f"aantal_{pid}", "0")
            try:
                aantal_besteleenheden = int(aantal_besteleenheden)
            except ValueError:
                aantal_besteleenheden = 0
            if aantal_besteleenheden > 0:
                product = db.execute(
                    "SELECT * FROM producten WHERE id = ?", (int(pid),)
                ).fetchone()
                if product is None:
                    continue
                aantal = naar_voorraadeenheden(aantal_besteleenheden, product)
                if aantal > 0:
                    regels.append((int(pid), aantal))

        if not regels:
            flash("Geen producten geselecteerd voor de bestelling.", "error")
            return redirect(url_for("bestellijst"))

        cur = db.execute(
            """INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, besteld_door_id)
               VALUES ('besteld', ?, ?, ?)""",
            (now_str(), besteld_door, besteld_door_id),
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
            """SELECT br.*, p.naam AS product_naam, p.eenheid,
                      p.besteleenheid, p.besteleenheid_factor
               FROM bestelregels br JOIN producten p ON p.id = br.product_id
               WHERE br.bestelling_id = ?""",
            (bestelling_id,),
        ).fetchall()

        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            was_al_ontvangen = bestelling["status"] == "ontvangen"

            for regel in regels:
                aantal_str = request.form.get(f"ontvangen_{regel['id']}", "0")
                try:
                    aantal_besteleenheden = max(0, int(aantal_str))
                except ValueError:
                    aantal_besteleenheden = 0
                aantal_ontvangen = naar_voorraadeenheden(aantal_besteleenheden, regel)

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
                           (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, bestelling_id)
                           VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                        (
                            regel["product_id"],
                            aantal_ontvangen,
                            now_str(),
                            naam,
                            gebruiker_id,
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

    # ---------- Bijzonderheden (prikbord) ----------

    @app.route("/bijzonderheden", methods=["GET", "POST"])
    def bijzonderheden():
        db = get_db()
        if request.method == "POST":
            tekst = request.form.get("tekst", "").strip()
            if not tekst:
                flash("Vul een tekst in.", "error")
                return redirect(url_for("bijzonderheden"))
            db.execute(
                "INSERT INTO mededelingen (tekst, naam, datum) VALUES (?, ?, ?)",
                (tekst, session.get("gebruiker_naam"), now_str()),
            )
            db.commit()
            return redirect(url_for("bijzonderheden"))

        mededelingen = db.execute(
            "SELECT * FROM mededelingen ORDER BY id DESC"
        ).fetchall()
        return render_template("bijzonderheden.html", mededelingen=mededelingen)

    @app.route("/bijzonderheden/<int:mededeling_id>/verwijderen", methods=["POST"])
    def mededeling_verwijderen(mededeling_id):
        db = get_db()
        db.execute("DELETE FROM mededelingen WHERE id = ?", (mededeling_id,))
        db.commit()
        return redirect(url_for("bijzonderheden"))


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5050)
