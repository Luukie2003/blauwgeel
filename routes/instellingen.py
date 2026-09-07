import re
from datetime import date, datetime

from flask import current_app, flash, redirect, render_template, request, send_from_directory, url_for

import agenda
import backup as backup_module
from database import get_db

BACKUP_BESTANDSNAAM = re.compile(
    r"^voorraad-(\d{4}-\d{2}-\d{2}|voor-herstel-\d{8}-\d{6})\.db$"
)


def register_routes(app):
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

    # ---------- Club instellingen (teamagenda's) ----------

    @app.route("/club-instellingen")
    def club_instellingen():
        db = get_db()
        feeds = db.execute("SELECT * FROM agenda_feeds ORDER BY id").fetchall()
        aantal_wedstrijden = db.execute(
            "SELECT COUNT(*) AS n FROM wedstrijden WHERE datum >= ?", (date.today().isoformat(),)
        ).fetchone()["n"]
        return render_template(
            "club_instellingen.html",
            feeds=feeds,
            aantal_wedstrijden=aantal_wedstrijden,
        )

    @app.route("/club-instellingen/toevoegen", methods=["POST"])
    def club_agenda_toevoegen():
        url = request.form.get("url", "").strip()
        if not url:
            flash("Vul een agenda-link in.", "error")
        else:
            db = get_db()
            db.execute("INSERT INTO agenda_feeds (url) VALUES (?)", (url,))
            db.commit()
            flash("Agenda-link toegevoegd. Klik op 'Nu verversen' om 'm op te halen.", "success")
        return redirect(url_for("club_instellingen"))

    @app.route("/club-instellingen/<int:feed_id>/verwijderen", methods=["POST"])
    def club_agenda_verwijderen(feed_id):
        db = get_db()
        db.execute("DELETE FROM agenda_feeds WHERE id = ?", (feed_id,))
        db.commit()
        flash("Agenda-link verwijderd.", "success")
        return redirect(url_for("club_instellingen"))

    @app.route("/club-instellingen/verversen", methods=["POST"])
    def club_agenda_verversen():
        aantal = agenda.ververs_wedstrijden(db_pad=current_app.config["DATABASE"])
        if aantal is None:
            flash("Geen agenda-links ingesteld om te verversen.", "error")
        else:
            flash(f"Agenda's ververst: {aantal} nieuwe wedstrijden toegevoegd.", "success")
        return redirect(url_for("club_instellingen"))

    @app.route("/club-instellingen/controleren", methods=["POST"])
    def club_agenda_controleren():
        db = get_db()
        urls = [r["url"] for r in db.execute("SELECT url FROM agenda_feeds").fetchall()]
        if not urls:
            flash("Geen agenda-links om te controleren.", "error")
        else:
            for resultaat in agenda.controleer_feeds(urls):
                if resultaat["ok"]:
                    flash(
                        f"{resultaat['team']}: bereikbaar, {resultaat['aantal']} wedstrijden gevonden.",
                        "success",
                    )
                else:
                    flash(f"Link mislukt ({resultaat['url']}): {resultaat['fout']}", "error")
        return redirect(url_for("club_instellingen"))

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
            flash("Herstellen is mislukt: back-up niet gevonden.", "error")
        return redirect(url_for("dashboard"))
