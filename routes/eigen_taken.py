"""Eigen taken in "Wat moet er nu?": toevoegen, afronden en de vraag "Taak afgerond?" na het opslaan."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import mail
from database import get_db
from helpers.tijd import vandaag_amsterdam
from eigen_taken import (
    CHECKLIST_VOORBEELDEN,
    HERHALINGEN,
    SOORT_EIGEN,
    SOORT_PRESET,
    TAAK_ENDPOINTS,
    TAAK_SOORTEN,
    afgeronde_taken,
    getagde_personen,
    maak_taak,
    open_taken,
    pagina_keuzes,
    rond_af,
    taak_voor_persoon,
    taken_voor_gebruiker,
    toewijsbare_gebruikers,
    verwijder_taak,
    vind_taak,
    vink_stap,
    vraag_kandidaten,
)


def _veilig_terug(pad):
    """Alleen een pad binnen de site (geen andere site via //of een volledige URL)."""
    if pad and pad.startswith("/") and not pad.startswith("//") and "\\" not in pad:
        return pad
    return url_for("dashboard")


def _mail_getagden(db, taak_id):
    """Mailt elke getagde persoon met een e-mailadres (behalve de maker zelf) dat er een taak voor hem of haar is.
    Een mislukte mail mag het toevoegen van de taak nooit laten mislukken (stuur_mail vangt dat zelf af)."""
    taak = vind_taak(db, taak_id)
    wie = session.get("gebruiker_naam")
    link = url_for("dashboard", _external=True)
    for mens in taak["mensen"]:
        gebruiker = db.execute("SELECT naam, email FROM gebruikers WHERE id = ?", (mens["id"],)).fetchone()
        if not gebruiker or not gebruiker["email"] or gebruiker["naam"] == wie:
            continue
        regels = [f"{wie or 'Iemand'} heeft je getagd op een taak:", "", f"\"{taak['titel']}\""]
        if taak["omschrijving"]:
            regels += ["", taak["omschrijving"]]
        if taak["deadline"]:
            regels += ["", f"Uiterlijk {taak['deadline'][8:10]}-{taak['deadline'][5:7]}-{taak['deadline'][:4]}"]
        regels += ["", f"Je ziet de taak bij 'Wat moet er nu?' op {link}"]
        mail.stuur_mail(f"Je bent getagd op een taak: {taak['titel']}", "\n".join(regels), naar=gebruiker["email"])


def register_routes(app):
    @app.route("/taken")
    def eigen_taken_pagina():
        db = get_db()
        return render_template(
            "eigen_taken.html",
            open_taken=open_taken(db),
            afgeronde_taken=afgeronde_taken(db),
            gebruikersnamen=[g["naam"] for g in toewijsbare_gebruikers(db)],
            presets=[(f"{SOORT_PRESET}{sleutel}", s["label"]) for sleutel, s in TAAK_SOORTEN.items()],
            paginas=pagina_keuzes(),
            soort_eigen=SOORT_EIGEN,
            herhalingen=list(HERHALINGEN.items()),
            checklist_voorbeelden=CHECKLIST_VOORBEELDEN,
            vandaag=vandaag_amsterdam().isoformat(),
        )

    @app.route("/taken/nieuw", methods=["POST"])
    def eigen_taak_nieuw():
        db = get_db()
        titel, omschrijving = request.form.get("titel"), request.form.get("omschrijving")
        ids, onbekend = getagde_personen(db, request.form.get("voor_wie"), titel, omschrijving)
        if onbekend:
            flash(f"Dit account ken ik niet: {', '.join('@' + n for n in onbekend)}. Typ een @ en kies uit de lijst.", "error")
            return redirect(url_for("eigen_taken_pagina"))
        taak_id, fout = maak_taak(
            db,
            titel,
            omschrijving,
            request.form.get("soort") or SOORT_EIGEN,
            request.form.get("deadline") or None,
            ids,
            request.form.get("wie_rondt_af") != "een",
            session.get("gebruiker_naam"),
            request.form.get("herhaling") or None,
            request.form.get("stappen"),
        )
        if fout:
            flash(fout, "error")
        else:
            namen = ", ".join(m["naam"] for m in vind_taak(db, taak_id)["mensen"])
            flash(f"Taak toegevoegd voor {namen}. Hij staat nu bij 'Wat moet er nu?' van de getagde mensen.", "success")
            _mail_getagden(db, taak_id)
        return redirect(url_for("eigen_taken_pagina"))

    @app.route("/taken/<int:taak_id>/verwijderen", methods=["POST"])
    def eigen_taak_verwijderen(taak_id):
        if verwijder_taak(get_db(), taak_id):
            flash("Taak verwijderd.", "success")
        else:
            flash("Die taak bestaat niet meer.", "error")
        return redirect(url_for("eigen_taken_pagina"))

    @app.route("/taken/<int:taak_id>/openen")
    def eigen_taak_openen(taak_id):
        """Waar de taak in 'Wat moet er nu?' naartoe leidt: de bijbehorende pagina, of (bij een taak zonder pagina)
        meteen de vraag of de taak klaar is."""
        taak = next((t for t in taken_voor_gebruiker(get_db(), session["gebruiker_id"]) if t["id"] == taak_id), None)
        if taak is None:
            flash("Die taak staat niet (meer) open voor jou.", "error")
            return redirect(url_for("dashboard"))
        if taak["stappen_lijst"]:
            return redirect(url_for("eigen_taak_detail", taak_id=taak_id))
        if taak["doel"]:
            return redirect(url_for(taak["doel"]["endpoint"]))
        session["taak_vragen"] = [taak_id]
        return redirect(url_for("dashboard"))

    @app.route("/taken/<int:taak_id>")
    def eigen_taak_detail(taak_id):
        """De checklist van een taak: de stappen om af te vinken, en pas als alles klaar is kun je de taak afronden."""
        taak = taak_voor_persoon(get_db(), taak_id, session["gebruiker_id"])
        if taak is None:
            flash("Die taak staat niet (meer) open voor jou.", "error")
            return redirect(url_for("dashboard"))
        anderen = [m["naam"] for m in taak["mensen"] if m["id"] != session["gebruiker_id"]]
        return render_template("eigen_taak_detail.html", taak=taak, anderen=anderen)

    @app.route("/taken/<int:taak_id>/stap", methods=["POST"])
    def eigen_taak_stap(taak_id):
        """Een stap van de checklist aan- of uitvinken (wordt direct bewaard, zodat je halverwege kunt stoppen)."""
        try:
            index = int(request.form.get("stap", ""))
        except ValueError:
            return jsonify({"ok": False}), 400
        uitkomst = vink_stap(get_db(), taak_id, session["gebruiker_id"], index, request.form.get("aan") == "1")
        if uitkomst is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, **uitkomst})

    @app.route("/taken/<int:taak_id>/afronden", methods=["POST"])
    def eigen_taak_afronden(taak_id):
        db = get_db()
        voor_iedereen = request.form.get("voor_iedereen") == "1" and session.get("gebruiker_rol") == "beheerder"
        taak = rond_af(db, taak_id, session["gebruiker_id"], session.get("gebruiker_naam"), voor_iedereen=voor_iedereen)
        if taak is None:
            flash("Die taak staat niet (meer) open voor jou.", "error")
        elif taak.get("onvolledig"):
            gedaan, totaal = taak["onvolledig"]
            flash(f"Vink eerst alle stappen af ({gedaan} van {totaal}), dan kun je de taak afronden.", "error")
            return redirect(url_for("eigen_taak_detail", taak_id=taak_id))
        elif taak["klaar"]:
            volgende = f" De volgende keer is {taak['volgende'].strftime('%d-%m')}." if taak["volgende"] else ""
            flash(f"Taak \"{taak['titel']}\" is klaar.{volgende}", "success")
        else:
            vind = vind_taak(db, taak_id)
            nog = ", ".join(m["naam"] for m in vind["mensen"] if m["afgerond_op"] is None)
            flash(f"Taak \"{taak['titel']}\" is voor jou afgerond. Nog te doen door: {nog}.", "success")
        return redirect(_veilig_terug(request.form.get("terug")))

    @app.route("/taken/<int:taak_id>/nog-niet", methods=["POST"])
    def eigen_taak_nog_niet(taak_id):
        """'Nog niet' bij de vraag: de taak blijft staan, er verandert niets."""
        return redirect(_veilig_terug(request.form.get("terug")))

    @app.after_request
    def vraag_of_taak_klaar_is(response):
        """Heeft iemand net iets opgeslagen dat bij een open taak van die persoon hoort, dan onthouden we dat; de
        volgende pagina toont dan de vraag 'Taak afgerond?' (zie _taak_vraag.html)."""
        if (
            request.method != "POST"
            or not 300 <= response.status_code < 400
            or "gebruiker_id" not in session
            or request.endpoint is None
            or request.endpoint in TAAK_ENDPOINTS
        ):
            return response
        if any(melding[0] == "error" for melding in session.get("_flashes", [])):
            return response  # het opslaan is niet gelukt: dan is de taak ook nog niet klaar
        try:
            kandidaten = vraag_kandidaten(get_db(), session["gebruiker_id"], request.endpoint)
        except Exception as fout:  # de vraag is een extraatje: opslaan mag er nooit door mislukken
            print(f"[taken] afrondvraag overgeslagen: {fout}")
            return response
        if kandidaten:
            session["taak_vragen"] = [t["id"] for t in kandidaten]
        return response

    @app.context_processor
    def inject_taak_vragen():
        def taak_vragen():
            """De taken waarvoor deze pagina de vraag 'afgerond?' toont. De vraag komt één keer: daarna is hij weg."""
            ids = session.pop("taak_vragen", None) or []
            if not ids or "gebruiker_id" not in session:
                return []
            open_voor_mij = {t["id"]: t for t in taken_voor_gebruiker(get_db(), session["gebruiker_id"])}
            return [open_voor_mij[i] for i in ids if i in open_voor_mij]

        return {"taak_vragen": taak_vragen}
