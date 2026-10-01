"""Club van 20-module: ledenadministratie met betalingen per seizoen,
projecten (waar het geld heen gaat), importeren/exporteren van de oude
spreadsheet, de scherminstellingen voor de Club van 20-dia's, en een
publieke pagina (QR-code op de wervingsdia). De rekenregels zelf staan in
club_van_20.py."""

from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import qr
from club_van_20 import (
    AFTEL_FORMAAT,
    aankondiging,
    BETAALWIJZEN,
    BIJDRAGE_STATUS_LABELS,
    PROJECT_STATUS_LABELS,
    alle_seizoenen,
    bijdrage_status,
    euro,
    financien,
    huidig_seizoen,
    is_zichtbaar,
    leden_met_bijdragen,
    normaliseer_seizoen,
    import_samenvatting,
    parse_import,
    rijen_naar_csv,
    rijen_uit_xlsx,
    sterren_voor,
    seizoen_kort,
    seizoen_totalen,
    sla_bijdrage_op,
    team_stand,
    verschuif_seizoen,
    verzoek_tekst,
    voer_import_uit,
    whatsapp_link,
    zichtbare_leden,
)
from database import get_db
from helpers import (
    KIOSK_AFBEELDINGEN_MAP,
    csv_response,
    is_ajax_verzoek,
    now_str,
    sla_afbeelding_op,
    vandaag_amsterdam,
)

LID_VELDEN = ("voornaam", "achternaam", "team", "telefoon", "email", "notitie")


def register_routes(app):
    app.jinja_env.filters["euro"] = euro
    app.jinja_env.filters["seizoen_kort"] = seizoen_kort

    def _instellingen(db):
        return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()

    def _bedrag(waarde):
        try:
            return float((waarde or "").replace(",", ".")) if (waarde or "").strip() else None
        except ValueError:
            return None

    def _getal(veld, standaard):
        try:
            return int(request.form.get(veld) or standaard)
        except ValueError:
            return standaard

    def _veilige_link(waarde):
        """Alleen http(s)-links: de betaallink komt als knop op de publieke
        pagina, dus geen javascript:- of andere vreemde schema's."""
        waarde = (waarde or "").strip()
        return waarde if waarde.lower().startswith(("https://", "http://")) else None

    def _aftelmoment(waarde):
        """datetime-local uit het formulier ("2026-10-05T00:00"), of None als
        het leeg of onleesbaar is."""
        try:
            return datetime.strptime((waarde or "").strip(), AFTEL_FORMAAT).strftime(AFTEL_FORMAAT)
        except ValueError:
            return None

    def _gekozen_seizoen(waarde):
        return normaliseer_seizoen(waarde or "") or huidig_seizoen()

    def _teams(db):
        return [
            r["team"]
            for r in db.execute(
                """SELECT DISTINCT team FROM club_van_20_leden
                   WHERE team IS NOT NULL AND team != '' ORDER BY team COLLATE NOCASE"""
            ).fetchall()
        ]

    def _lid_of_404(db, lid_id):
        return db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()

    # ---------- Leden & betalingen ----------

    @app.route("/club-van-20")
    def club_van_20_overzicht():
        db = get_db()
        instellingen = _instellingen(db)
        seizoenen = alle_seizoenen(db)
        seizoen = _gekozen_seizoen(request.args.get("seizoen"))
        if seizoen not in seizoenen:
            seizoenen = sorted(set(seizoenen) | {seizoen})
        zoek = (request.args.get("q") or "").strip().lower()
        team = request.args.get("team") or ""
        status_filter = request.args.get("status") or ""
        weergave = request.args.get("weergave") or "actief"
        if weergave == "inactief":
            weergave = "gearchiveerd"

        alle_leden = leden_met_bijdragen(db)
        tellers = {s: 0 for s in BIJDRAGE_STATUS_LABELS}
        leden = []
        per_ster = instellingen["club_van_20_seizoenen_per_ster"]
        for lid in alle_leden:
            lid["sterren"] = sterren_voor(lid["aantal_seizoenen"], per_ster)
            lid["status_seizoen"] = bijdrage_status(lid, seizoen)
            lid["op_scherm"], _ = is_zichtbaar(
                lid, huidig_seizoen(), instellingen["club_van_20_zichtbaar_seizoenen"]
            )
            if lid["status"] != "inactief":
                tellers[lid["status_seizoen"]] += 1
            if weergave == "actief" and lid["status"] == "inactief":
                continue
            if weergave == "gearchiveerd" and lid["status"] != "inactief":
                continue
            if zoek and zoek not in f"{lid['naam']} {lid['volledige_naam']}".lower():
                continue
            if team and (lid.get("team") or "") != team:
                continue
            if status_filter and lid["status_seizoen"] != status_filter:
                continue
            leden.append(lid)

        return render_template(
            "club_van_20_overzicht.html",
            leden=leden,
            aantal_totaal=len(alle_leden),
            seizoenen=seizoenen,
            seizoen=seizoen,
            huidig=huidig_seizoen(),
            totalen=seizoen_totalen(db),
            tellers=tellers,
            geld=financien(db, instellingen["club_van_20_bedrag"], seizoen),
            teams=_teams(db),
            filters={"q": request.args.get("q") or "", "team": team, "status": status_filter, "weergave": weergave},
            status_labels=BIJDRAGE_STATUS_LABELS,
            betaalwijzen=BETAALWIJZEN,
            instellingen=instellingen,
        )

    @app.route("/club-van-20/leden/<int:lid_id>/bijdrage", methods=["POST"])
    def club_van_20_bijdrage_opslaan(lid_id):
        db = get_db()
        lid = _lid_of_404(db, lid_id)
        seizoen = normaliseer_seizoen(request.form.get("seizoen", ""))
        status = request.form.get("status", "")
        if lid is None or seizoen is None or status not in BIJDRAGE_STATUS_LABELS:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Ongeldige invoer."}), 400
            flash("Ongeldige invoer.", "error")
            return redirect(request.referrer or url_for("club_van_20_overzicht"))
        instellingen = _instellingen(db)
        bestaand = db.execute(
            "SELECT * FROM club_van_20_bijdragen WHERE lid_id = ? AND seizoen = ?", (lid_id, seizoen)
        ).fetchone()
        # Velden die niet in het formulier zaten (bijv. alleen de snelle
        # statusknop in het overzicht) houden hun bestaande waarde.
        def _veld(naam):
            if naam in request.form:
                return request.form.get(naam)
            return bestaand[naam] if bestaand else None

        bedrag = _bedrag(request.form.get("bedrag")) if "bedrag" in request.form else None
        if bedrag is None and bestaand and status == "betaald" and bestaand["status"] == "betaald":
            bedrag = bestaand["bedrag"]
        sla_bijdrage_op(
            db,
            lid_id,
            seizoen,
            status,
            bedrag=bedrag,
            betaald_door=_veld("betaald_door"),
            betaalwijze=_veld("betaalwijze"),
            notitie=_veld("notitie"),
            standaard_bedrag=instellingen["club_van_20_bedrag"],
            gebruiker=session.get("gebruiker_naam"),
        )
        db.commit()
        rij = db.execute(
            "SELECT * FROM club_van_20_bijdragen WHERE lid_id = ? AND seizoen = ?", (lid_id, seizoen)
        ).fetchone()
        melding = f"{lid['naam']}: {seizoen} staat op '{BIJDRAGE_STATUS_LABELS[status]}'."
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "melding": melding,
                    "status": status,
                    "label": BIJDRAGE_STATUS_LABELS[status],
                    "bedrag": rij["bedrag"] if rij else 0,
                    "totalen": {
                        s: {"bedrag": t["bedrag"], "betaald": t["betaald"]}
                        for s, t in seizoen_totalen(db).items()
                    },
                }
            )
        flash(melding, "success")
        return redirect(request.referrer or url_for("club_van_20_overzicht"))

    def _archiveer(db, ids, archiveren):
        """Archiveren = van het scherm en uit de lijsten (status 'inactief'),
        maar met behoud van de betaalhistorie -- i.t.t. verwijderen. Terugzetten
        maakt een lid weer gewoon actief."""
        if archiveren:
            db.executemany(
                """UPDATE club_van_20_leden SET status = 'inactief', gearchiveerd_op = ?
                   WHERE id = ? AND status != 'inactief'""",
                [(vandaag_amsterdam().isoformat(), lid_id) for lid_id in ids],
            )
        else:
            db.executemany(
                "UPDATE club_van_20_leden SET status = 'actief', gearchiveerd_op = NULL WHERE id = ?",
                [(lid_id,) for lid_id in ids],
            )

    @app.route("/club-van-20/leden/<int:lid_id>/archiveren", methods=["POST"])
    def club_van_20_lid_archiveren(lid_id):
        db = get_db()
        lid = _lid_of_404(db, lid_id)
        if lid is None:
            flash("Lid niet gevonden.", "error")
            return redirect(url_for("club_van_20_overzicht"))
        archiveren = request.form.get("actie") != "terugzetten"
        _archiveer(db, [lid_id], archiveren)
        db.commit()
        melding = (
            f"'{lid['naam']}' is gearchiveerd en staat niet meer op het scherm."
            if archiveren
            else f"'{lid['naam']}' is teruggezet bij de actieve leden."
        )
        if is_ajax_verzoek():
            return jsonify({"ok": True, "melding": melding, "gearchiveerd": archiveren})
        flash(melding, "success")
        return redirect(request.referrer or url_for("club_van_20_overzicht"))

    @app.route("/club-van-20/bulk", methods=["POST"])
    def club_van_20_bulk():
        db = get_db()
        seizoen = normaliseer_seizoen(request.form.get("seizoen", ""))
        status = request.form.get("status", "")
        ids = [int(i) for i in request.form.getlist("lid_ids") if i.isdigit()]
        actie = request.form.get("actie")
        if actie in ("archiveren", "terugzetten") and ids:
            _archiveer(db, ids, actie == "archiveren")
            db.commit()
            woord = "gearchiveerd" if actie == "archiveren" else "teruggezet"
            flash(f"{len(ids)} {'lid' if len(ids) == 1 else 'leden'} {woord}.", "success")
            return redirect(request.referrer or url_for("club_van_20_overzicht"))
        if seizoen is None or status not in BIJDRAGE_STATUS_LABELS or not ids:
            flash("Selecteer eerst een of meer leden en een status.", "error")
            return redirect(request.referrer or url_for("club_van_20_overzicht"))
        instellingen = _instellingen(db)
        for lid_id in ids:
            if _lid_of_404(db, lid_id) is None:
                continue
            bestaand = db.execute(
                "SELECT * FROM club_van_20_bijdragen WHERE lid_id = ? AND seizoen = ?", (lid_id, seizoen)
            ).fetchone()
            sla_bijdrage_op(
                db,
                lid_id,
                seizoen,
                status,
                bedrag=bestaand["bedrag"] if bestaand and status == "betaald" else None,
                betaald_door=bestaand["betaald_door"] if bestaand else None,
                betaalwijze=bestaand["betaalwijze"] if bestaand else None,
                notitie=bestaand["notitie"] if bestaand else None,
                standaard_bedrag=instellingen["club_van_20_bedrag"],
                gebruiker=session.get("gebruiker_naam"),
            )
        db.commit()
        flash(
            f"{len(ids)} {'lid' if len(ids) == 1 else 'leden'} op '{BIJDRAGE_STATUS_LABELS[status]}' gezet voor {seizoen}.",
            "success",
        )
        return redirect(request.referrer or url_for("club_van_20_overzicht"))

    def _lid_uit_formulier():
        gegevens = {veld: (request.form.get(veld) or "").strip() or None for veld in LID_VELDEN}
        gegevens["naam"] = (request.form.get("naam") or "").strip()
        if not gegevens["naam"]:
            gegevens["naam"] = " ".join(
                d for d in (gegevens["voornaam"], gegevens["achternaam"]) if d
            )
        gegevens["extra_groot"] = 1 if request.form.get("extra_groot") else 0
        try:
            gegevens["eerdere_seizoenen"] = max(0, int(request.form.get("eerdere_seizoenen") or 0))
        except ValueError:
            gegevens["eerdere_seizoenen"] = 0
        return gegevens

    def _naam_bezet(db, naam, behalve_id=None):
        rij = db.execute(
            "SELECT id FROM club_van_20_leden WHERE LOWER(naam) = LOWER(?) AND id != ?",
            (naam, behalve_id or 0),
        ).fetchone()
        return rij is not None

    @app.route("/club-van-20/leden/nieuw", methods=["GET", "POST"])
    def club_van_20_lid_nieuw():
        db = get_db()
        if request.method == "POST":
            gegevens = _lid_uit_formulier()
            if not gegevens["naam"]:
                flash("Vul een naambordje of een naam in.", "error")
            elif _naam_bezet(db, gegevens["naam"]):
                flash(f"Er is al een lid met naambordje '{gegevens['naam']}'.", "error")
            else:
                cursor = db.execute(
                    """INSERT INTO club_van_20_leden
                           (naam, voornaam, achternaam, team, telefoon, email, notitie,
                            extra_groot, status, eerdere_seizoenen, startdatum, aangemaakt_op)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        gegevens["naam"],
                        *(gegevens[v] for v in LID_VELDEN),
                        gegevens["extra_groot"],
                        "actief",
                        gegevens["eerdere_seizoenen"],
                        vandaag_amsterdam().isoformat(),
                        now_str(),
                    ),
                )
                status = request.form.get("status_seizoen") or "niet_gevraagd"
                if status in BIJDRAGE_STATUS_LABELS and status != "niet_gevraagd":
                    sla_bijdrage_op(
                        db,
                        cursor.lastrowid,
                        huidig_seizoen(),
                        status,
                        bedrag=_bedrag(request.form.get("bedrag")),
                        betaalwijze=request.form.get("betaalwijze"),
                        betaald_door=request.form.get("betaald_door"),
                        standaard_bedrag=_instellingen(db)["club_van_20_bedrag"],
                        gebruiker=session.get("gebruiker_naam"),
                    )
                db.commit()
                flash(f"'{gegevens['naam']}' toegevoegd aan de Club van 20.", "success")
                if request.form.get("nog_een"):
                    return redirect(url_for("club_van_20_lid_nieuw"))
                return redirect(url_for("club_van_20_overzicht"))
        return render_template(
            "club_van_20_lid_form.html",
            lid=None,
            teams=_teams(db),
            huidig=huidig_seizoen(),
            status_labels=BIJDRAGE_STATUS_LABELS,
            betaalwijzen=BETAALWIJZEN,
            instellingen=_instellingen(db),
        )

    @app.route("/club-van-20/leden/<int:lid_id>", methods=["GET", "POST"])
    def club_van_20_lid_bewerken(lid_id):
        db = get_db()
        if _lid_of_404(db, lid_id) is None:
            flash("Lid niet gevonden.", "error")
            return redirect(url_for("club_van_20_overzicht"))
        if request.method == "POST":
            gegevens = _lid_uit_formulier()
            if not gegevens["naam"]:
                flash("Vul een naambordje of een naam in.", "error")
            elif _naam_bezet(db, gegevens["naam"], lid_id):
                flash(f"Er is al een lid met naambordje '{gegevens['naam']}'.", "error")
            else:
                db.execute(
                    """UPDATE club_van_20_leden
                       SET naam = ?, voornaam = ?, achternaam = ?, team = ?, telefoon = ?,
                           email = ?, notitie = ?, extra_groot = ?, eerdere_seizoenen = ?
                       WHERE id = ?""",
                    (
                        gegevens["naam"],
                        *(gegevens[v] for v in LID_VELDEN),
                        gegevens["extra_groot"],
                        gegevens["eerdere_seizoenen"],
                        lid_id,
                    ),
                )
                db.commit()
                flash(f"'{gegevens['naam']}' bijgewerkt.", "success")
                return redirect(url_for("club_van_20_lid_bewerken", lid_id=lid_id))

        instellingen = _instellingen(db)
        lid = next(l for l in leden_met_bijdragen(db) if l["id"] == lid_id)
        lid["sterren"] = sterren_voor(lid["aantal_seizoenen"], instellingen["club_van_20_seizoenen_per_ster"])
        seizoenen = sorted(set(alle_seizoenen(db)) | set(lid["bijdragen"]), reverse=True)
        huidig = huidig_seizoen()
        tekst = verzoek_tekst(
            instellingen["club_van_20_verzoek_tekst"],
            lid,
            huidig,
            instellingen["club_van_20_bedrag"],
            instellingen["club_van_20_betaallink"],
        )
        op_scherm, onbetaald = is_zichtbaar(lid, huidig, instellingen["club_van_20_zichtbaar_seizoenen"])
        return render_template(
            "club_van_20_lid_form.html",
            lid=lid,
            seizoenen=seizoenen,
            huidig=huidig,
            volgend=verschuif_seizoen(huidig, 1),
            teams=_teams(db),
            status_labels=BIJDRAGE_STATUS_LABELS,
            betaalwijzen=BETAALWIJZEN,
            instellingen=instellingen,
            verzoek=tekst,
            whatsapp=whatsapp_link(lid.get("telefoon"), tekst),
            op_scherm=op_scherm,
            onbetaald=onbetaald,
        )

    @app.route("/club-van-20/leden/<int:lid_id>/verwijderen", methods=["POST"])
    def club_van_20_lid_verwijderen(lid_id):
        db = get_db()
        lid = _lid_of_404(db, lid_id)
        if lid is not None:
            db.execute("DELETE FROM club_van_20_bijdragen WHERE lid_id = ?", (lid_id,))
            db.execute("DELETE FROM club_van_20_leden WHERE id = ?", (lid_id,))
            db.commit()
            flash(f"'{lid['naam']}' en de bijbehorende betalingen zijn verwijderd.", "success")
        return redirect(url_for("club_van_20_overzicht"))

    # ---------- Projecten ----------

    def _project_uit_formulier():
        naam = (request.form.get("naam") or "").strip()
        status = request.form.get("status") or "gepland"
        return {
            "naam": naam,
            "omschrijving": (request.form.get("omschrijving") or "").strip() or None,
            "raming": _bedrag(request.form.get("raming")) or 0,
            "kosten": _bedrag(request.form.get("kosten")),
            "status": status if status in PROJECT_STATUS_LABELS else "gepland",
            "volgorde": _getal("volgorde", 0),
            "toon_op_scherm": 1 if request.form.get("toon_op_scherm") else 0,
        }

    @app.route("/club-van-20/projecten", methods=["GET", "POST"])
    def club_van_20_projecten():
        db = get_db()
        if request.method == "POST":
            p = _project_uit_formulier()
            if not p["naam"]:
                flash("Vul een naam in voor het project.", "error")
            else:
                if "volgorde" not in request.form or not request.form.get("volgorde"):
                    p["volgorde"] = (
                        db.execute("SELECT COALESCE(MAX(volgorde), 0) + 1 AS n FROM club_van_20_projecten").fetchone()["n"]
                    )
                db.execute(
                    """INSERT INTO club_van_20_projecten
                           (naam, omschrijving, raming, kosten, status, volgorde, toon_op_scherm,
                            afgerond_op, afbeelding, aangemaakt_op)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        p["naam"],
                        p["omschrijving"],
                        p["raming"],
                        p["kosten"],
                        p["status"],
                        p["volgorde"],
                        1,
                        vandaag_amsterdam().isoformat() if p["status"] == "klaar" else None,
                        sla_afbeelding_op(request.files.get("afbeelding"), KIOSK_AFBEELDINGEN_MAP),
                        now_str(),
                    ),
                )
                db.commit()
                flash(f"Project '{p['naam']}' toegevoegd.", "success")
            return redirect(url_for("club_van_20_projecten"))
        instellingen = _instellingen(db)
        return render_template(
            "club_van_20_projecten.html",
            geld=financien(db, instellingen["club_van_20_bedrag"]),
            project_statussen=PROJECT_STATUS_LABELS,
        )

    @app.route("/club-van-20/projecten/<int:project_id>", methods=["GET", "POST"])
    def club_van_20_project_bewerken(project_id):
        db = get_db()
        project = db.execute("SELECT * FROM club_van_20_projecten WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            flash("Project niet gevonden.", "error")
            return redirect(url_for("club_van_20_projecten"))
        if request.method == "POST":
            p = _project_uit_formulier()
            if not p["naam"]:
                flash("Vul een naam in voor het project.", "error")
            else:
                afbeelding = sla_afbeelding_op(request.files.get("afbeelding"), KIOSK_AFBEELDINGEN_MAP)
                if request.form.get("afbeelding_verwijderen"):
                    afbeelding_waarde = None
                else:
                    afbeelding_waarde = afbeelding or project["afbeelding"]
                afgerond_op = project["afgerond_op"]
                if p["status"] == "klaar" and not afgerond_op:
                    afgerond_op = vandaag_amsterdam().isoformat()
                elif p["status"] != "klaar":
                    afgerond_op = None
                db.execute(
                    """UPDATE club_van_20_projecten
                       SET naam = ?, omschrijving = ?, raming = ?, kosten = ?, status = ?,
                           volgorde = ?, toon_op_scherm = ?, afbeelding = ?, afgerond_op = ?
                       WHERE id = ?""",
                    (
                        p["naam"],
                        p["omschrijving"],
                        p["raming"],
                        p["kosten"],
                        p["status"],
                        p["volgorde"],
                        p["toon_op_scherm"],
                        afbeelding_waarde,
                        afgerond_op,
                        project_id,
                    ),
                )
                db.commit()
                flash(f"Project '{p['naam']}' opgeslagen.", "success")
                return redirect(url_for("club_van_20_projecten"))
        return render_template(
            "club_van_20_project_form.html", project=project, project_statussen=PROJECT_STATUS_LABELS
        )

    @app.route("/club-van-20/projecten/<int:project_id>/status", methods=["POST"])
    def club_van_20_project_status(project_id):
        db = get_db()
        status = request.form.get("status")
        project = db.execute("SELECT * FROM club_van_20_projecten WHERE id = ?", (project_id,)).fetchone()
        if project is None or status not in PROJECT_STATUS_LABELS:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Ongeldige invoer."}), 400
            return redirect(url_for("club_van_20_projecten"))
        afgerond_op = project["afgerond_op"] or vandaag_amsterdam().isoformat() if status == "klaar" else None
        db.execute(
            "UPDATE club_van_20_projecten SET status = ?, afgerond_op = ? WHERE id = ?",
            (status, afgerond_op, project_id),
        )
        db.commit()
        melding = f"'{project['naam']}' staat nu op '{PROJECT_STATUS_LABELS[status]}'."
        if is_ajax_verzoek():
            return jsonify({"ok": True, "melding": melding})
        flash(melding, "success")
        return redirect(url_for("club_van_20_projecten"))

    @app.route("/club-van-20/projecten/<int:project_id>/verwijderen", methods=["POST"])
    def club_van_20_project_verwijderen(project_id):
        db = get_db()
        db.execute("DELETE FROM club_van_20_projecten WHERE id = ?", (project_id,))
        db.commit()
        flash("Project verwijderd.", "success")
        return redirect(url_for("club_van_20_projecten"))

    # ---------- Importeren / exporteren ----------

    @app.route("/club-van-20/importeren", methods=["GET", "POST"])
    def club_van_20_importeren():
        db = get_db()
        instellingen = _instellingen(db)
        tekst = ""
        voorbeeld = None
        if request.method == "POST":
            bestand = request.files.get("bestand")
            xlsx_fout = None
            if bestand and bestand.filename:
                ruw = bestand.read()
                if bestand.filename.lower().endswith((".xlsx", ".xlsm")):
                    # Excel-bestand: omzetten naar dezelfde tekst als een
                    # CSV-import, zodat voorbeeld en bevestigen identiek werken.
                    try:
                        tekst = rijen_naar_csv(rijen_uit_xlsx(ruw))
                    except ValueError as fout:
                        xlsx_fout = str(fout)
                else:
                    try:
                        tekst = ruw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        tekst = ruw.decode("latin-1")
            else:
                tekst = request.form.get("tekst", "")
            voorbeeld = parse_import(tekst, instellingen["club_van_20_bedrag"])
            if xlsx_fout:
                voorbeeld["fout"] = xlsx_fout
            if voorbeeld["fout"]:
                flash(voorbeeld["fout"], "error")
                voorbeeld = None
            elif request.form.get("bevestig"):
                nieuw, bijgewerkt = voer_import_uit(
                    db,
                    voorbeeld["rijen"],
                    gebruiker=session.get("gebruiker_naam"),
                    standaard_bedrag=instellingen["club_van_20_bedrag"],
                )
                db.commit()
                flash(f"Import klaar: {nieuw} nieuwe leden, {bijgewerkt} bijgewerkt.", "success")
                return redirect(url_for("club_van_20_overzicht"))
            else:
                bestaande = {
                    r["naam"].lower()
                    for r in db.execute("SELECT naam FROM club_van_20_leden").fetchall()
                }
                for rij in voorbeeld["rijen"]:
                    rij["bestaat"] = rij["naam"].lower() in bestaande
                voorbeeld["samenvatting"] = import_samenvatting(db, voorbeeld["rijen"])
                voorbeeld["totalen"] = {
                    s: sum(
                        r["bijdragen"][s]["bedrag"]
                        for r in voorbeeld["rijen"]
                        if s in r["bijdragen"] and r["bijdragen"][s]["status"] == "betaald"
                    )
                    for s in voorbeeld["seizoenen"]
                }
        return render_template(
            "club_van_20_importeren.html", tekst=tekst, voorbeeld=voorbeeld, status_labels=BIJDRAGE_STATUS_LABELS
        )

    @app.route("/club-van-20/export.csv")
    def club_van_20_exporteren():
        db = get_db()
        seizoenen = alle_seizoenen(db)
        huidig = huidig_seizoen()
        kop = ["Voornaam", "Achternaam", "Team", "Naambordje", *seizoenen,
               f"Status {huidig}", "Betaald door", "Telefoon", "E-mail", "Notitie", "Actief"]
        rijen = []
        for lid in leden_met_bijdragen(db):
            bedragen = []
            for s in seizoenen:
                b = lid["bijdragen"].get(s)
                bedragen.append(f"{b['bedrag']:g}" if b and b["status"] == "betaald" else "")
            huidige = lid["bijdragen"].get(huidig) or {}
            rijen.append(
                [
                    lid.get("voornaam") or "",
                    lid.get("achternaam") or "",
                    lid.get("team") or "",
                    lid["naam"],
                    *bedragen,
                    BIJDRAGE_STATUS_LABELS[bijdrage_status(lid, huidig)],
                    huidige.get("betaald_door") or "",
                    lid.get("telefoon") or "",
                    lid.get("email") or "",
                    lid.get("notitie") or "",
                    "nee" if lid["status"] == "inactief" else "ja",
                ]
            )
        return csv_response(f"club-van-20-{vandaag_amsterdam().isoformat()}.csv", kop, rijen)

    # ---------- Scherm & instellingen ----------

    @app.route("/club-van-20/instellingen", methods=["GET", "POST"])
    def club_van_20_instellingen():
        db = get_db()
        instellingen = _instellingen(db)
        if request.method == "POST":
            achtergrond = instellingen["club_van_20_achtergrond"]
            nieuwe = sla_afbeelding_op(request.files.get("achtergrond"), KIOSK_AFBEELDINGEN_MAP)
            if nieuwe:
                achtergrond = nieuwe
            elif request.form.get("achtergrond_verwijderen"):
                achtergrond = None
            db.execute(
                """UPDATE kiosk_scherm_instellingen
                   SET toon_club_van_20 = ?, club_van_20_titel = ?, club_van_20_namen_per_slide = ?,
                       club_van_20_kolommen = ?, club_van_20_duur_seconden = ?,
                       club_van_20_zichtbaar_seizoenen = ?, club_van_20_markeer_onbetaald = ?,
                       club_van_20_lege_vakjes = ?, club_van_20_laatste_dia_vullen = ?,
                       club_van_20_bedrag = ?, club_van_20_achtergrond = ?,
                       club_van_20_toon_teller = ?, club_van_20_toon_teams = ?,
                       club_van_20_toon_nieuw = ?, club_van_20_toon_werving = ?,
                       club_van_20_werving_tekst = ?, club_van_20_betaallink = ?,
                       club_van_20_verzoek_tekst = ?,
                       club_van_20_aankondiging_tekst = ?, club_van_20_aankondiging_aftellen_tot = ?,
                       club_van_20_aankondiging_na_tekst = ?, club_van_20_aankondiging_op_dia = ?,
                       club_van_20_seizoenen_per_ster = ?, club_van_20_glans_vanaf_sterren = ?
                   WHERE id = 1""",
                (
                    1 if request.form.get("toon_club_van_20") else 0,
                    (request.form.get("club_van_20_titel") or "").strip() or "Club van 20",
                    min(80, max(1, _getal("club_van_20_namen_per_slide", 24))),
                    min(8, max(1, _getal("club_van_20_kolommen", 4))),
                    max(3, _getal("club_van_20_duur_seconden", 12)),
                    max(0, _getal("club_van_20_zichtbaar_seizoenen", 2)),
                    1 if request.form.get("club_van_20_markeer_onbetaald") else 0,
                    1 if request.form.get("club_van_20_lege_vakjes") else 0,
                    1 if request.form.get("club_van_20_laatste_dia_vullen") else 0,
                    _bedrag(request.form.get("club_van_20_bedrag")) or 20,
                    achtergrond,
                    1 if request.form.get("club_van_20_toon_teller") else 0,
                    1 if request.form.get("club_van_20_toon_teams") else 0,
                    1 if request.form.get("club_van_20_toon_nieuw") else 0,
                    1 if request.form.get("club_van_20_toon_werving") else 0,
                    (request.form.get("club_van_20_werving_tekst") or "").strip(),
                    _veilige_link(request.form.get("club_van_20_betaallink")),
                    (request.form.get("club_van_20_verzoek_tekst") or "").strip(),
                    (request.form.get("club_van_20_aankondiging_tekst") or "").strip() or None,
                    _aftelmoment(request.form.get("club_van_20_aankondiging_aftellen_tot")),
                    (request.form.get("club_van_20_aankondiging_na_tekst") or "").strip() or None,
                    1 if request.form.get("club_van_20_aankondiging_op_dia") else 0,
                    max(1, min(20, _getal("club_van_20_seizoenen_per_ster", 3))),
                    max(1, min(20, _getal("club_van_20_glans_vanaf_sterren", 2))),
                ),
            )
            db.commit()
            if is_ajax_verzoek():
                return jsonify({"ok": True, "melding": "Club van 20-instellingen opgeslagen."})
            flash("Club van 20-instellingen opgeslagen.", "success")
            return redirect(url_for("club_van_20_instellingen"))
        publiek_url = url_for("club_van_20_publiek", _external=True)
        return render_template(
            "club_van_20_instellingen.html",
            instellingen=instellingen,
            publiek_url=publiek_url,
            publiek_qr_svg=qr.qr_svg(publiek_url),
            aantal_op_scherm=len(zichtbare_leden(db, instellingen)),
        )

    # ---------- Publieke pagina (QR-code op de wervingsdia) ----------

    @app.route("/club-van-20/doe-mee")
    def club_van_20_publiek():
        db = get_db()
        instellingen = _instellingen(db)
        zichtbaar = zichtbare_leden(db, instellingen)
        return render_template(
            "club_van_20_publiek.html",
            instellingen=instellingen,
            aankondiging=aankondiging(instellingen),
            namen=zichtbaar,
            teams=team_stand(zichtbaar, leden_met_bijdragen(db, alleen_actief=True)),
            geld=financien(db, instellingen["club_van_20_bedrag"]),
            seizoen=huidig_seizoen(),
        )
