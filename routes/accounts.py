import secrets

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import mail
from database import WACHTWOORD_HASH_METHODE, get_db
from helpers import SECTIE_LABELS, SECTIES, genereer_wachtwoord_token, now_str


def _secties_uit_formulier():
    """Leest de aangevinkte secties-checkboxes en geeft ze terug als
    comma-tekst, precies zoals opgeslagen in gebruikers.secties. Onbekende
    waarden (geknoei met het formulier) worden genegeerd."""
    gekozen = [s for s in request.form.getlist("secties") if s in SECTIES]
    return ",".join(gekozen)


def register_routes(app):
    @app.route("/accounts")
    def accounts_lijst():
        db = get_db()
        gebruikers = db.execute(
            "SELECT id, naam, email, rol, secties, aangemaakt_op, laatste_login "
            "FROM gebruikers ORDER BY naam"
        ).fetchall()
        aantal_beheerders = db.execute(
            "SELECT COUNT(*) AS n FROM gebruikers WHERE rol = 'beheerder'"
        ).fetchone()["n"]
        return render_template(
            "accounts.html",
            gebruikers=gebruikers,
            aantal_beheerders=aantal_beheerders,
            alle_secties=SECTIES,
            sectie_labels=SECTIE_LABELS,
        )

    @app.route("/accounts/nieuw", methods=["POST"])
    def account_nieuw():
        naam = request.form.get("naam", "").strip()
        email = request.form.get("email", "").strip()
        rol = request.form.get("rol", "vrijwilliger")
        if rol not in ("beheerder", "vrijwilliger"):
            rol = "vrijwilliger"
        secties = _secties_uit_formulier()
        db = get_db()

        if not naam or not email:
            flash("Naam en e-mailadres zijn verplicht.", "error")
        elif db.execute("SELECT id FROM gebruikers WHERE naam = ?", (naam,)).fetchone():
            flash(f"Er bestaat al een account met de naam '{naam}'.", "error")
        else:
            onbruikbaar_wachtwoord = generate_password_hash(
                secrets.token_hex(16), method=WACHTWOORD_HASH_METHODE
            )
            cursor = db.execute(
                """INSERT INTO gebruikers (naam, email, wachtwoord_hash, rol, secties, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (naam, email, onbruikbaar_wachtwoord, rol, secties, now_str()),
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
                    "Dit is de laatste beheerder. Er moet altijd minstens één overblijven.",
                    "error",
                )
                return redirect(url_for("accounts_lijst"))

        db.execute("UPDATE gebruikers SET rol = ? WHERE id = ?", (nieuwe_rol, gebruiker_id))
        db.commit()
        flash(f"'{gebruiker['naam']}' is nu {nieuwe_rol}.", "success")
        return redirect(url_for("accounts_lijst"))

    @app.route("/accounts/<int:gebruiker_id>/secties", methods=["POST"])
    def account_secties_wijzigen(gebruiker_id):
        db = get_db()
        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        if gebruiker is None:
            flash("Account niet gevonden.", "error")
            return redirect(url_for("accounts_lijst"))

        secties = _secties_uit_formulier()
        db.execute("UPDATE gebruikers SET secties = ? WHERE id = ?", (secties, gebruiker_id))
        db.commit()
        flash(f"Rechten van '{gebruiker['naam']}' bijgewerkt.", "success")
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
                "Dit is de laatste beheerder. Er moet altijd minstens één overblijven.",
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
                    (generate_password_hash(nieuw, method=WACHTWOORD_HASH_METHODE), gebruiker["id"]),
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
