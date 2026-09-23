import re
from datetime import datetime, timedelta

from flask import current_app, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import mail
from database import WACHTWOORD_HASH_METHODE, get_db
from helpers import csrf_token, genereer_wachtwoord_token, now_str, veilig_redirect_pad, vind_gebruiker_bij_token

# Brute-force-bescherming op het inlogscherm: na dit aantal mislukte
# pogingen voor dezelfde gebruikersnaam wordt die naam tijdelijk geblokkeerd,
# ongeacht of het wachtwoord daarna wel klopt.
LOGIN_MAX_POGINGEN = 5
LOGIN_LOCKOUT_MINUTEN = 15

# Precies 6 cijfers -- zie tablet_code_instellen hieronder.
TABLET_CODE_PATROON = re.compile(r"^\d{6}$")

# Zelfde soort brute-force-bescherming als hierboven, maar dan per IP-adres
# i.p.v. gebruikersnaam -- zie tablet_code_inloggen onderaan dit bestand.
TABLET_CODE_MAX_POGINGEN = 10
TABLET_CODE_LOCKOUT_MINUTEN = 15


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
            if gebruiker and check_password_hash(gebruiker["wachtwoord_hash"], wachtwoord) and not gebruiker["actief"]:
                # Wachtwoord klopt, maar het account is geblokkeerd (zie
                # account_actief_wisselen) -- geen mislukte-pogingenteller
                # ophogen (het wachtwoord was immers goed), gewoon een
                # duidelijke, andere melding dan "onjuiste naam of
                # wachtwoord" tonen.
                flash(
                    "Dit account is geblokkeerd. Neem contact op met een beheerder.", "error"
                )
                return render_template("login.html")
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
        if not gebruiker["actief"]:
            flash("Dit account is geblokkeerd. Neem contact op met een beheerder.", "error")
            return redirect(url_for("login"))

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

    def _tablet_code_al_in_gebruik(db, code, uitgezonderd_gebruiker_id):
        """Codes zijn gehasht opgeslagen (net als wachtwoorden) -- de enige
        manier om te weten of code X al bezet is, is 'm tegen elke bestaande
        hash aan te houden (zie tablet_code_instellen). Bij een handvol tot
        een paar tientallen accounts is dat verwaarloosbaar traag."""
        rijen = db.execute(
            "SELECT tablet_code_hash FROM gebruikers WHERE tablet_code_hash IS NOT NULL AND id != ?",
            (uitgezonderd_gebruiker_id,),
        ).fetchall()
        return any(check_password_hash(r["tablet_code_hash"], code) for r in rijen)

    @app.route("/tablet-code/instellen", methods=["GET", "POST"])
    def tablet_code_instellen():
        """Elk account stelt hier een eigen 6-cijferige code in -- verplicht
        bij de eerste keer inloggen (zie vereis_login in app.py), en
        daarna vrijblijvend te wijzigen (zie account_voorkeuren.html). Die
        code is bedoeld om zonder gebruikersnaam aan te melden op de
        kiosk-tablet/tv-app die los van deze website wordt gebouwd -- deze
        pagina regelt alleen het instellen/bewaren ervan, niet die app zelf."""
        db = get_db()
        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (session["gebruiker_id"],)
        ).fetchone()
        if gebruiker is None:
            return redirect(url_for("login"))

        if request.method == "POST":
            code = request.form.get("code", "").strip()
            code_herhaald = request.form.get("code_herhaald", "").strip()
            if not TABLET_CODE_PATROON.match(code):
                flash("De code moet precies 6 cijfers zijn.", "error")
            elif code != code_herhaald:
                flash("De codes komen niet overeen.", "error")
            elif _tablet_code_al_in_gebruik(db, code, gebruiker["id"]):
                flash("Deze code is al in gebruik door een ander account -- kies een andere.", "error")
            else:
                db.execute(
                    "UPDATE gebruikers SET tablet_code_hash = ? WHERE id = ?",
                    (generate_password_hash(code, method=WACHTWOORD_HASH_METHODE), gebruiker["id"]),
                )
                db.commit()
                flash("Tablet-code opgeslagen.", "success")
                volgende = veilig_redirect_pad(
                    request.form.get("next") or request.args.get("next"), url_for("dashboard")
                )
                return redirect(volgende)

        return render_template(
            "tablet_code_instellen.html",
            heeft_al_code=gebruiker["tablet_code_hash"] is not None,
            next=request.args.get("next", ""),
        )

    @app.route("/api/tablet-code/inloggen", methods=["POST"])
    def tablet_code_inloggen():
        """JSON-API voor de kiosk-tablet-app (los project, zie android-apps/
        tablet) -- zoekt het account waarvan de 6-cijferige code overeenkomt
        (zie tablet_code_instellen hierboven) en logt dat account in, precies
        zoals het normale /login-formulier doet (zelfde sessie-opbouw), zodat
        de app daarna met dat account ingelogd de gewone website kan tonen
        (producten, acties, bardiensten, ...) -- geen aparte rechten-laag,
        gewoon wat dat account al mag zien. De JSON-respons meldt alleen
        geldig/ongeldig terug; welk account het is blijkt uit de sessie-
        cookie die de app na een geldige code overneemt in zijn WebView.
        Eigen brute-force-bescherming per IP-adres (i.p.v. de sessie-/
        gebruikersnaam-gebonden bescherming van het normale inlogscherm),
        want er is nog geen sessie op het moment van deze aanroep zelf.
        Uitgezonderd van csrf_beschermen (zie app.py): dat mechanisme
        veronderstelt een browser met een sessie, wat hier nog niet bestaat."""
        db = get_db()
        ip = request.remote_addr or "onbekend"

        poging = db.execute(
            "SELECT * FROM tablet_code_pogingen WHERE ip_adres = ?", (ip,)
        ).fetchone()
        if poging and poging["geblokkeerd_tot"]:
            geblokkeerd_tot = datetime.strptime(poging["geblokkeerd_tot"], "%Y-%m-%d %H:%M")
            if geblokkeerd_tot > datetime.now():
                return jsonify({"geldig": False, "fout": "te_veel_pogingen"}), 429

        data = request.get_json(silent=True) or {}
        code = str(data.get("code", "")).strip()

        gebruiker = None
        if TABLET_CODE_PATROON.match(code):
            rijen = db.execute(
                "SELECT * FROM gebruikers WHERE tablet_code_hash IS NOT NULL AND actief = 1"
            ).fetchall()
            gebruiker = next(
                (r for r in rijen if check_password_hash(r["tablet_code_hash"], code)), None
            )

        if gebruiker is not None:
            db.execute("DELETE FROM tablet_code_pogingen WHERE ip_adres = ?", (ip,))
            session.clear()
            session["gebruiker_id"] = gebruiker["id"]
            session["gebruiker_naam"] = gebruiker["naam"]
            session["gebruiker_rol"] = gebruiker["rol"]
            session["toon_welkom_popup"] = True
            db.execute(
                "UPDATE gebruikers SET laatste_login = ? WHERE id = ?",
                (now_str(), gebruiker["id"]),
            )
            db.commit()
            return jsonify({"geldig": True})

        mislukte_pogingen = (poging["mislukte_pogingen"] if poging else 0) + 1
        nieuwe_blokkade = None
        if mislukte_pogingen >= TABLET_CODE_MAX_POGINGEN:
            nieuwe_blokkade = (
                datetime.now() + timedelta(minutes=TABLET_CODE_LOCKOUT_MINUTEN)
            ).strftime("%Y-%m-%d %H:%M")
        if poging:
            db.execute(
                """UPDATE tablet_code_pogingen
                   SET mislukte_pogingen = ?, laatste_poging = ?, geblokkeerd_tot = ?
                   WHERE ip_adres = ?""",
                (mislukte_pogingen, now_str(), nieuwe_blokkade, ip),
            )
        else:
            db.execute(
                """INSERT INTO tablet_code_pogingen
                       (ip_adres, mislukte_pogingen, laatste_poging, geblokkeerd_tot)
                   VALUES (?, ?, ?, ?)""",
                (ip, mislukte_pogingen, now_str(), nieuwe_blokkade),
            )
        db.commit()
        return jsonify({"geldig": False})

    @app.route("/api/tablet/csrf")
    def api_tablet_csrf():
        """De tablet-app doet zijn schrijfacties (producten/acties/
        bardiensten) via gewone form-encoded POSTs naar de bestaande routes
        (zie routes/producten.py en routes/kiosk.py), dus die lopen gewoon
        door csrf_beschermen -- de app heeft dus, net als een browser, een
        geldig csrf_token nodig. Hier haalt-ie 'm op na het inloggen, in
        plaats van 'm (zoals een browser) uit een verborgen formulierveld
        te lezen."""
        return jsonify({"csrf_token": csrf_token()})
