import secrets

from flask import (
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import qr
from database import get_db
from helpers import (
    bewaar_bier,
    is_ajax_verzoek,
    now_str,
    sla_stemoptie_afbeelding_op,
    stemming_is_open,
    tel_stemmers,
)
from pdf import stemming_poster_pdf

# Naam van het los cookie waarmee een anonieme stemmer wordt herkend (om
# dubbel stemmen op dezelfde stemvraag tegen te gaan). Bewust geen gebruik
# van de Flask-sessie zelf: die wordt bij inloggen geleegd, en stemmers zijn
# meestal niet eens ingelogd.
STEM_COOKIE = "stem_kiezer"
MAX_STEMOPTIES = 10


def register_routes(app):

    @app.route("/stemmen")
    def stemmen_overzicht():
        db = get_db()
        stemvragen = []
        for v in db.execute(
            "SELECT * FROM stemvragen ORDER BY actief DESC, id DESC"
        ).fetchall():
            aantal = db.execute(
                "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (v["id"],)
            ).fetchone()["n"]
            stemvragen.append({"vraag": v, "aantal_stemmen": aantal})
        return render_template("stemmen_overzicht.html", stemvragen=stemvragen)

    @app.route("/stemmen/nieuw", methods=["GET", "POST"])
    def stemvraag_nieuw():
        db = get_db()
        if request.method == "POST":
            titel = request.form.get("titel", "").strip()
            omschrijving = request.form.get("omschrijving", "").strip()
            sluit_op_datum = request.form.get("sluit_op", "").strip()
            sluit_op = f"{sluit_op_datum} 23:59" if sluit_op_datum else None
            toon_uitslag = 1 if request.form.get("toon_uitslag") else 0
            opmerking_toegestaan = 1 if request.form.get("opmerking_toegestaan") else 0
            aantal_keuzes = request.form.get("aantal_keuzes", type=int) or 1
            aantal_keuzes = max(1, min(aantal_keuzes, MAX_STEMOPTIES))
            regels = []
            for i in range(1, MAX_STEMOPTIES + 1):
                tekst = request.form.get(f"optie{i}", "").strip()
                if not tekst:
                    continue
                afbeelding = sla_stemoptie_afbeelding_op(request.files.get(f"afbeelding{i}"))
                if not afbeelding:
                    # Geen nieuwe upload: hergebruik de foto als deze naam al
                    # in de bieren-bibliotheek staat.
                    bekend = db.execute(
                        "SELECT afbeelding FROM bieren WHERE naam = ?", (tekst,)
                    ).fetchone()
                    if bekend:
                        afbeelding = bekend["afbeelding"]
                regels.append((tekst, afbeelding))
            if not titel:
                flash("Vul een titel/vraag in.", "error")
                return redirect(url_for("stemvraag_nieuw"))
            if len(regels) < 2:
                flash("Vul minstens 2 keuzes in.", "error")
                return redirect(url_for("stemvraag_nieuw"))
            cur = db.execute(
                """INSERT INTO stemvragen
                       (titel, omschrijving, aangemaakt_op, aangemaakt_door, sluit_op,
                        toon_uitslag, opmerking_toegestaan, aantal_keuzes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    titel, omschrijving or None, now_str(), session.get("gebruiker_naam"), sluit_op,
                    toon_uitslag, opmerking_toegestaan, aantal_keuzes,
                ),
            )
            stemvraag_id = cur.lastrowid
            for volgorde, (tekst, afbeelding) in enumerate(regels):
                db.execute(
                    "INSERT INTO stemopties (stemvraag_id, tekst, volgorde, afbeelding) VALUES (?, ?, ?, ?)",
                    (stemvraag_id, tekst, volgorde, afbeelding),
                )
                bewaar_bier(db, tekst, afbeelding)
            db.commit()
            flash("Stemming aangemaakt.", "success")
            return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))
        bieren = db.execute("SELECT * FROM bieren ORDER BY naam COLLATE NOCASE").fetchall()
        return render_template("stemvraag_form.html", max_stemopties=MAX_STEMOPTIES, bieren=bieren)

    @app.route("/stemmen/<int:stemvraag_id>")
    def stemvraag_detail(stemvraag_id):
        db = get_db()
        stemvraag = db.execute(
            "SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)
        ).fetchone()
        if stemvraag is None:
            flash("Stemming niet gevonden.", "error")
            return redirect(url_for("stemmen_overzicht"))
        opties = db.execute(
            """SELECT so.*,
                      (SELECT COUNT(*) FROM stemmen s WHERE s.stemoptie_id = so.id AND s.afgekeurd = 0) AS aantal
               FROM stemopties so WHERE so.stemvraag_id = ? ORDER BY so.volgorde""",
            (stemvraag_id,),
        ).fetchall()
        totaal_stemmen = sum(o["aantal"] for o in opties)
        totaal_stemmers = tel_stemmers(db, stemvraag_id)
        stemmen = db.execute(
            """SELECT s.*, so.tekst AS optie_tekst
               FROM stemmen s JOIN stemopties so ON so.id = s.stemoptie_id
               WHERE s.stemvraag_id = ? ORDER BY s.id DESC""",
            (stemvraag_id,),
        ).fetchall()
        stem_url = url_for("stem_pagina", stemvraag_id=stemvraag_id, _external=True)
        return render_template(
            "stemvraag_detail.html",
            stemvraag=stemvraag,
            opties=opties,
            totaal_stemmen=totaal_stemmen,
            totaal_stemmers=totaal_stemmers,
            stemmen=stemmen,
            stem_url=stem_url,
            qr_svg=qr.qr_svg(stem_url),
            max_stemopties=MAX_STEMOPTIES,
        )

    @app.route("/stemmen/<int:stemvraag_id>/poster.pdf")
    def stemvraag_poster_pdf(stemvraag_id):
        db = get_db()
        stemvraag = db.execute(
            "SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)
        ).fetchone()
        if stemvraag is None:
            flash("Stemming niet gevonden.", "error")
            return redirect(url_for("stemmen_overzicht"))
        stem_url = url_for("stem_pagina", stemvraag_id=stemvraag_id, _external=True)
        pdf_bytes = stemming_poster_pdf(stemvraag["titel"], qr.qr_png_bytes(stem_url))
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=stemming-{stemvraag_id}-poster.pdf"},
        )

    @app.route("/stemmen/stem/<int:stem_id>/afkeuren", methods=["POST"])
    def stem_afkeuren(stem_id):
        db = get_db()
        stem = db.execute("SELECT * FROM stemmen WHERE id = ?", (stem_id,)).fetchone()
        if stem is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Stem niet gevonden."}), 404
            flash("Stem niet gevonden.", "error")
            return redirect(url_for("stemmen_overzicht"))
        db.execute("UPDATE stemmen SET afgekeurd = 1 WHERE id = ?", (stem_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgekeurd": 1,
                    "melding": "Stem afgekeurd. Uitslag hierboven ververst bij de volgende paginalaad.",
                }
            )
        flash("Stem afgekeurd, telt niet meer mee in de uitslag.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stem["stemvraag_id"]))

    @app.route("/stemmen/stem/<int:stem_id>/goedkeuren", methods=["POST"])
    def stem_goedkeuren(stem_id):
        db = get_db()
        stem = db.execute("SELECT * FROM stemmen WHERE id = ?", (stem_id,)).fetchone()
        if stem is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Stem niet gevonden."}), 404
            flash("Stem niet gevonden.", "error")
            return redirect(url_for("stemmen_overzicht"))
        db.execute("UPDATE stemmen SET afgekeurd = 0 WHERE id = ?", (stem_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgekeurd": 0,
                    "melding": "Stem telt weer mee. Uitslag hierboven ververst bij de volgende paginalaad.",
                }
            )
        flash("Stem telt weer mee.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stem["stemvraag_id"]))

    @app.route("/stemmen/<int:stemvraag_id>/sluiten", methods=["POST"])
    def stemvraag_sluiten(stemvraag_id):
        db = get_db()
        db.execute("UPDATE stemvragen SET actief = 0 WHERE id = ?", (stemvraag_id,))
        db.commit()
        flash("Stemming gesloten voor nieuwe stemmen.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))

    @app.route("/stemmen/<int:stemvraag_id>/heropenen", methods=["POST"])
    def stemvraag_heropenen(stemvraag_id):
        db = get_db()
        db.execute("UPDATE stemvragen SET actief = 1 WHERE id = ?", (stemvraag_id,))
        db.commit()
        flash("Stemming heropend.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))

    @app.route("/stemmen/<int:stemvraag_id>/einddatum", methods=["POST"])
    def stemvraag_einddatum_instellen(stemvraag_id):
        db = get_db()
        sluit_op_datum = request.form.get("sluit_op", "").strip()
        sluit_op = f"{sluit_op_datum} 23:59" if sluit_op_datum else None
        db.execute("UPDATE stemvragen SET sluit_op = ? WHERE id = ?", (sluit_op, stemvraag_id))
        db.commit()
        flash("Einddatum bijgewerkt." if sluit_op else "Einddatum verwijderd.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))

    @app.route("/stemmen/<int:stemvraag_id>/instellingen", methods=["POST"])
    def stemvraag_instellingen_bijwerken(stemvraag_id):
        db = get_db()
        toon_uitslag = 1 if request.form.get("toon_uitslag") else 0
        opmerking_toegestaan = 1 if request.form.get("opmerking_toegestaan") else 0
        aantal_keuzes = request.form.get("aantal_keuzes", type=int) or 1
        aantal_keuzes = max(1, min(aantal_keuzes, MAX_STEMOPTIES))
        db.execute(
            """UPDATE stemvragen SET toon_uitslag = ?, opmerking_toegestaan = ?, aantal_keuzes = ?
               WHERE id = ?""",
            (toon_uitslag, opmerking_toegestaan, aantal_keuzes, stemvraag_id),
        )
        db.commit()
        flash("Instellingen bijgewerkt.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))

    @app.route("/stemmen/<int:stemvraag_id>/verwijderen", methods=["POST"])
    def stemvraag_verwijderen(stemvraag_id):
        db = get_db()
        db.execute("DELETE FROM stemvragen WHERE id = ?", (stemvraag_id,))
        db.commit()
        flash("Stemming verwijderd.", "success")
        return redirect(url_for("stemmen_overzicht"))

    @app.route("/stemmen/bieren")
    def bieren_lijst():
        db = get_db()
        bieren = db.execute("SELECT * FROM bieren ORDER BY naam COLLATE NOCASE").fetchall()
        return render_template("bieren_lijst.html", bieren=bieren)

    @app.route("/stemmen/bieren/<int:bier_id>/verwijderen", methods=["POST"])
    def bier_verwijderen(bier_id):
        db = get_db()
        db.execute("DELETE FROM bieren WHERE id = ?", (bier_id,))
        db.commit()
        flash("Verwijderd uit de bibliotheek.", "success")
        return redirect(url_for("bieren_lijst"))

    # ---------- Publieke stempagina (geen account nodig) ----------

    @app.route("/stem")
    def stem_overzicht_publiek():
        db = get_db()
        stemvragen = db.execute(
            "SELECT * FROM stemvragen ORDER BY aangemaakt_op DESC"
        ).fetchall()
        stemvraag_ids = [v["id"] for v in stemvragen]

        # Eén query voor de opties + één voor de stemmersaantallen, i.p.v.
        # twee aparte queries per stemvraag -- deze pagina is publiek (geen
        # login nodig, bereikbaar via de QR-code) en groeit met elke
        # stemming die de club ooit organiseert.
        opties_per_vraag = {}
        stemmers_per_vraag = {}
        if stemvraag_ids:
            placeholders = ",".join("?" * len(stemvraag_ids))
            for regel in db.execute(
                f"""SELECT so.*,
                           (SELECT COUNT(*) FROM stemmen s WHERE s.stemoptie_id = so.id AND s.afgekeurd = 0) AS aantal
                    FROM stemopties so
                    WHERE so.stemvraag_id IN ({placeholders})
                    ORDER BY so.volgorde""",
                stemvraag_ids,
            ).fetchall():
                opties_per_vraag.setdefault(regel["stemvraag_id"], []).append(regel)

            for regel in db.execute(
                f"""SELECT stemvraag_id, COUNT(DISTINCT kiezer_sleutel) AS n
                    FROM stemmen
                    WHERE afgekeurd = 0 AND stemvraag_id IN ({placeholders})
                    GROUP BY stemvraag_id""",
                stemvraag_ids,
            ).fetchall():
                stemmers_per_vraag[regel["stemvraag_id"]] = regel["n"]

        stemmingen = [
            {
                "vraag": v,
                "open": stemming_is_open(v),
                "opties": opties_per_vraag.get(v["id"], []),
                "totaal_stemmers": stemmers_per_vraag.get(v["id"], 0),
            }
            for v in stemvragen
        ]
        return render_template("stem_overzicht_publiek.html", stemmingen=stemmingen)

    @app.route("/stem/<int:stemvraag_id>", methods=["GET", "POST"])
    def stem_pagina(stemvraag_id):
        db = get_db()
        stemvraag = db.execute(
            "SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)
        ).fetchone()
        if stemvraag is None:
            return render_template("stem_niet_gevonden.html"), 404

        kiezer_sleutel = request.cookies.get(STEM_COOKIE)
        nieuwe_cookie = None
        if not kiezer_sleutel:
            kiezer_sleutel = secrets.token_hex(16)
            nieuwe_cookie = kiezer_sleutel

        def _al_gestemd(naam=None):
            """Twee onafhankelijke controles op maar 1x stemmen: dit device
            (cookie) en, zodra er een naam is, deze naam -- zodat wissen van
            cookies niet als omweg werkt. Een afgekeurde stem telt niet mee,
            die mag opnieuw."""
            if db.execute(
                "SELECT 1 FROM stemmen WHERE stemvraag_id = ? AND kiezer_sleutel = ? AND afgekeurd = 0",
                (stemvraag_id, kiezer_sleutel),
            ).fetchone():
                return True
            if naam and db.execute(
                "SELECT 1 FROM stemmen WHERE stemvraag_id = ? AND lower(naam) = lower(?) AND afgekeurd = 0",
                (stemvraag_id, naam),
            ).fetchone():
                return True
            return False

        al_gestemd = _al_gestemd()
        ingevulde_naam = ""

        foutmelding = None
        if request.method == "POST":
            ingevulde_naam = request.form.get("naam", "").strip()
            if not stemming_is_open(stemvraag):
                foutmelding = "Deze stemming is gesloten."
            elif not ingevulde_naam:
                foutmelding = "Vul je naam in."
            elif _al_gestemd(ingevulde_naam):
                foutmelding = "Je hebt al gestemd, bedankt!"
                al_gestemd = True
            else:
                aantal_keuzes = stemvraag["aantal_keuzes"] or 1
                if aantal_keuzes > 1:
                    gekozen_ids = list(dict.fromkeys(request.form.getlist("optie_id", type=int)))
                else:
                    enkele_id = request.form.get("optie_id", type=int)
                    gekozen_ids = [enkele_id] if enkele_id else []
                geldige_ids = {
                    row["id"]
                    for row in db.execute(
                        "SELECT id FROM stemopties WHERE stemvraag_id = ?", (stemvraag_id,)
                    ).fetchall()
                }
                gekozen_ids = [i for i in gekozen_ids if i in geldige_ids]

                if not gekozen_ids:
                    foutmelding = "Kies eerst een van de opties." if aantal_keuzes == 1 else "Kies minstens 1 optie."
                elif len(gekozen_ids) > aantal_keuzes:
                    foutmelding = f"Kies maximaal {aantal_keuzes} opties."
                else:
                    opmerking = None
                    if stemvraag["opmerking_toegestaan"]:
                        opmerking = request.form.get("opmerking", "").strip() or None
                    db.execute(
                        "DELETE FROM stemmen WHERE stemvraag_id = ? AND kiezer_sleutel = ? "
                        "AND stemoptie_id NOT IN ({})".format(",".join("?" * len(gekozen_ids))),
                        (stemvraag_id, kiezer_sleutel, *gekozen_ids),
                    )
                    for optie_id in gekozen_ids:
                        db.execute(
                            """INSERT INTO stemmen (stemvraag_id, stemoptie_id, kiezer_sleutel, naam, opmerking, datum)
                               VALUES (?, ?, ?, ?, ?, ?)
                               ON CONFLICT(stemvraag_id, kiezer_sleutel, stemoptie_id) DO UPDATE SET
                                   naam = excluded.naam,
                                   opmerking = excluded.opmerking,
                                   afgekeurd = 0,
                                   datum = excluded.datum""",
                            (stemvraag_id, optie_id, kiezer_sleutel, ingevulde_naam, opmerking, now_str()),
                        )
                    db.commit()
                    al_gestemd = True

        opties = db.execute(
            """SELECT so.*,
                      (SELECT COUNT(*) FROM stemmen s WHERE s.stemoptie_id = so.id AND s.afgekeurd = 0) AS aantal
               FROM stemopties so WHERE so.stemvraag_id = ? ORDER BY so.volgorde""",
            (stemvraag_id,),
        ).fetchall()
        totaal_stemmen = sum(o["aantal"] for o in opties)
        totaal_stemmers = tel_stemmers(db, stemvraag_id)

        pagina = render_template(
            "stem_pagina.html",
            stemvraag=stemvraag,
            opties=opties,
            totaal_stemmen=totaal_stemmen,
            totaal_stemmers=totaal_stemmers,
            al_gestemd=al_gestemd,
            foutmelding=foutmelding,
            ingevulde_naam=ingevulde_naam,
        )
        respons = Response(pagina)
        if nieuwe_cookie:
            respons.set_cookie(
                STEM_COOKIE,
                nieuwe_cookie,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                secure=current_app.config.get("SESSION_COOKIE_SECURE", True),
                samesite="Lax",
            )
        return respons

