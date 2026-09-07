from datetime import datetime, timedelta

from flask import current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import mail
from database import WACHTWOORD_HASH_METHODE, get_db
from helpers import genereer_wachtwoord_token, now_str, veilig_redirect_pad, vind_gebruiker_bij_token

# Brute-force-bescherming op het inlogscherm: na dit aantal mislukte
# pogingen voor dezelfde gebruikersnaam wordt die naam tijdelijk geblokkeerd,
# ongeacht of het wachtwoord daarna wel klopt.
LOGIN_MAX_POGINGEN = 5
LOGIN_LOCKOUT_MINUTEN = 15


def register_routes(app):
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "gebruiker_id" in session:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            wachtwoord = request.form.get("wachtwoord", "")
            db = get_db()

            poging = db.execute(
                "SELECT * FROM login_pogingen WHERE naam = ?", (naam,)
            ).fetchone()
            mislukte_pogingen = poging["mislukte_pogingen"] if poging else 0
            if poging and poging["geblokkeerd_tot"]:
                geblokkeerd_tot = datetime.strptime(
                    poging["geblokkeerd_tot"], "%Y-%m-%d %H:%M"
                )
                if geblokkeerd_tot > datetime.now():
                    resterend = max(
                        1, round((geblokkeerd_tot - datetime.now()).total_seconds() / 60)
                    )
                    flash(
                        f"Te veel mislukte inlogpogingen. Probeer het over ongeveer "
                        f"{resterend} minuut(en) opnieuw.",
                        "error",
                    )
                    return render_template("login.html")
                # Blokkade is verlopen -- weer met een schone lei beginnen.
                mislukte_pogingen = 0

            gebruiker = db.execute(
                "SELECT * FROM gebruikers WHERE naam = ?", (naam,)
            ).fetchone()
            if gebruiker and check_password_hash(gebruiker["wachtwoord_hash"], wachtwoord):
                if not gebruiker["wachtwoord_hash"].startswith(WACHTWOORD_HASH_METHODE + "$"):
                    # Hash met een ouder/trager aantal iteraties (werkzeug's
                    # eigen pbkdf2-standaard duurde hier ruim 0,6s per
                    # inlogpoging) -- nu we het wachtwoord toch al hebben
                    # geverifieerd, stilzwijgend vervangen door de huidige,
                    # snellere instelling. Elke gebruiker krijgt dit
                    # automatisch bij de eerstvolgende geslaagde login,
                    # zonder daar iets van te merken.
                    db.execute(
                        "UPDATE gebruikers SET wachtwoord_hash = ? WHERE id = ?",
                        (
                            generate_password_hash(wachtwoord, method=WACHTWOORD_HASH_METHODE),
                            gebruiker["id"],
                        ),
                    )
                db.execute("DELETE FROM login_pogingen WHERE naam = ?", (naam,))
                session.clear()
                session["gebruiker_id"] = gebruiker["id"]
                session["gebruiker_naam"] = gebruiker["naam"]
                session["gebruiker_rol"] = gebruiker["rol"]
                # Eenmalig vlaggetje (net als flash()) -- inject_nav() haalt
                # 'm er weer af zodra de eerste pagina na het inloggen is
                # gerenderd, zodat de welkom-pop-up maar 1x verschijnt.
                session["toon_welkom_popup"] = True
                db.execute(
                    "UPDATE gebruikers SET laatste_login = ? WHERE id = ?",
                    (now_str(), gebruiker["id"]),
                )
                db.commit()
                volgende = veilig_redirect_pad(request.args.get("next"), url_for("dashboard"))
                return redirect(volgende)

            nieuw_aantal = mislukte_pogingen + 1
            nieuwe_blokkade = None
            if nieuw_aantal >= LOGIN_MAX_POGINGEN:
                nieuwe_blokkade = (
                    datetime.now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTEN)
                ).strftime("%Y-%m-%d %H:%M")
            if poging:
                db.execute(
                    """UPDATE login_pogingen
                       SET mislukte_pogingen = ?, laatste_poging = ?, geblokkeerd_tot = ?
                       WHERE naam = ?""",
                    (nieuw_aantal, now_str(), nieuwe_blokkade, naam),
                )
            else:
                db.execute(
                    """INSERT INTO login_pogingen
                       (naam, mislukte_pogingen, laatste_poging, geblokkeerd_tot)
                       VALUES (?, ?, ?, ?)""",
                    (naam, nieuw_aantal, now_str(), nieuwe_blokkade),
                )
            db.commit()

            if nieuwe_blokkade:
                flash(
                    f"Te veel mislukte inlogpogingen. Probeer het over ongeveer "
                    f"{LOGIN_LOCKOUT_MINUTEN} minuten opnieuw.",
                    "error",
                )
            else:
                flash("Onjuiste naam of wachtwoord.", "error")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Je bent uitgelogd.", "success")
        return redirect(url_for("login"))

    def _zet_weergave_cookie_en_ga_terug(modus):
        """Onthoudt de gekozen weergave op dit toestel/browser (geen
        accountinstelling, dus geldt niet mee op een ander toestel) en
        stuurt terug naar waar de knop werd geklikt."""
        respons = redirect(request.referrer or url_for("dashboard"))
        respons.set_cookie(
            "weergave",
            modus,
            max_age=60 * 60 * 24 * 365,
            samesite="Lax",
            secure=current_app.config.get("SESSION_COOKIE_SECURE", True),
        )
        return respons

    @app.route("/weergave/pda")
    def weergave_pda():
        return _zet_weergave_cookie_en_ga_terug("pda")

    @app.route("/weergave/desktop")
    def weergave_desktop():
        return _zet_weergave_cookie_en_ga_terug("desktop")

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
                    "Kantine Beheer: wachtwoord opnieuw instellen",
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
                    (generate_password_hash(nieuw, method=WACHTWOORD_HASH_METHODE), gebruiker["id"]),
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
