"""Leden en hun betalingen per seizoen."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from aanmeldingen import aantal_openstaand
from club_van_20 import (
    BETAALWIJZEN,
    BIJDRAGE_STATUS_LABELS,
    alle_seizoenen,
    bijdrage_status,
    financien,
    huidig_seizoen,
    is_zichtbaar,
    leden_met_bijdragen,
    normaliseer_seizoen,
    scherm_bereik,
    seizoen_totalen,
    sla_bijdrage_op,
    sterren_voor,
    verschuif_seizoen,
    verzoek_tekst,
    whatsapp_link,
)
from database import get_db
from helpers import is_ajax_verzoek, now_str, vandaag_amsterdam
from routes.club_van_20.gedeeld import (
    LID_VELDEN,
    _bedrag,
    _gekozen_seizoen,
    _instellingen,
    _lid_of_404,
    _teams,
)


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


def register_routes(app):
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
            lid["op_scherm"], _ = is_zichtbaar(lid, huidig_seizoen(), scherm_bereik(instellingen)[0])
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
            aanmeldingen_open=aantal_openstaand(db),
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
        op_scherm, onbetaald = is_zichtbaar(lid, huidig, scherm_bereik(instellingen)[0])
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
