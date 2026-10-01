"""Aanmelden voor de Club van 20: het publieke formulier (waar de knop bovenaan
de Club van 20-pagina naartoe leidt) en de concepttabel voor de beheerders
(Club van 20 > Aanmeldingen) waar elke aanmelding wordt goedgekeurd nadat de
betaling is gecontroleerd. De regels zelf staan in aanmeldingen.py."""

from flask import current_app, flash, redirect, render_template, request, session, url_for

from aanmeldingen import (
    AANMELD_BETAALWIJZEN,
    VOORBEELD_MAX_POGINGEN,
    VOORBEELD_MIN_TEKENS,
    aanmelden_status,
    aanmelden_status_voor,
    aantal_openstaand,
    bardienst_suggesties,
    bestaand_lid_voor,
    ip_hash,
    keur_goed,
    maak_aanmelding,
    max_tekens,
    ruim_op,
    splits_naam,
    stuur_melding_nieuwe_aanmelding,
    te_veel_aanmeldingen,
    valideer_aanmelding,
    voorbeeld_geblokkeerd,
    voorbeeld_gelukt,
    voorbeeld_mislukt,
    voorbeeldcode,
    voorbeeldcode_klopt,
    wijs_af,
    zet_voorbeeld,
)
from club_van_20 import BETAALWIJZEN, huidig_seizoen
from database import get_db
from helpers import vandaag_amsterdam


def register_routes(app):
    def _instellingen(db):
        return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()

    def _mollie_link(instellingen):
        link = (instellingen["club_van_20_betaallink"] or "").strip()
        return link if link.lower().startswith(("https://", "http://")) else None

    def _bedrag(waarde):
        try:
            return float((waarde or "").replace(",", ".")) if (waarde or "").strip() else None
        except ValueError:
            return None

    def _client_ip():
        # PythonAnywhere zet het echte adres in X-Real-IP; anders het directe adres.
        return request.headers.get("X-Real-IP") or request.remote_addr or "onbekend"

    # ---------- Publiek formulier ----------

    @app.route("/club-van-20/aanmelden", methods=["GET", "POST"])
    def club_van_20_aanmelden():
        db = get_db()
        instellingen = _instellingen(db)
        mollie = _mollie_link(instellingen)
        status = aanmelden_status_voor(instellingen, session)
        context = {
            "instellingen": instellingen,
            "status": status,
            "mollie_link": mollie,
            "betaalwijzen": {k: v for k, v in AANMELD_BETAALWIJZEN.items() if k != "mollie" or mollie},
            "max_tekens": max_tekens(instellingen),
            "bardiensten": bardienst_suggesties(db),
            "waarden": {},
            "fouten": {},
        }
        if request.method == "POST" and status["open"]:
            # Honeypot: een veld dat mensen niet zien en bots wel invullen.
            if request.form.get("website"):
                return redirect(url_for("club_van_20_aanmelden_bedankt"))
            waarden, fouten = valideer_aanmelding(request.form, instellingen, bool(mollie))
            ip_h = ip_hash(_client_ip(), current_app.secret_key)
            if not fouten and te_veel_aanmeldingen(db, ip_h):
                fouten["algemeen"] = "Er zijn nu even te veel aanmeldingen. Probeer het over een uur nog eens, of vraag het aan de bar."
            if fouten:
                context.update(waarden=waarden, fouten=fouten)
                return render_template("club_van_20_aanmelden.html", **context), 400
            _, is_nieuw = maak_aanmelding(
                db, waarden, huidig_seizoen(), instellingen["club_van_20_bedrag"], ip_h
            )
            ruim_op(db)
            if is_nieuw:
                stuur_melding_nieuwe_aanmelding(
                    db, waarden, url_for("club_van_20_aanmeldingen", _external=True)
                )
            session["aanmelding_klaar"] = {
                "bordje": waarden["bordje"],
                "betaalwijze": waarden["betaalwijze"],
                "bardienst": waarden["bardienst"],
            }
            return redirect(url_for("club_van_20_aanmelden_bedankt"))
        return render_template("club_van_20_aanmelden.html", **context)

    @app.route("/club-van-20/aanmelden/voorbeeld", methods=["GET", "POST"])
    def club_van_20_aanmelden_voorbeeld():
        """De geheime knop: met de ingestelde code (Scherm & werving) zie je het
        aanmeldformulier al vóór het openingsmoment, als voorbeeld. Een
        aanmelding die je dan verstuurt, komt gewoon in de lijst bij
        Aanmeldingen (en je kunt 'm afwijzen), zodat je alles kunt uitproberen."""
        db = get_db()
        instellingen = _instellingen(db)
        beschikbaar = bool(voorbeeldcode(instellingen))
        fout = None
        status = 200
        if request.method == "POST" and beschikbaar:
            pogingen = session.get("voorbeeld_pogingen", 0)
            ip_h = ip_hash(_client_ip(), current_app.secret_key)
            if pogingen >= VOORBEELD_MAX_POGINGEN or voorbeeld_geblokkeerd(db, ip_h):
                fout, status = "Te veel pogingen. Probeer het later nog eens.", 429
            elif voorbeeldcode_klopt(instellingen, request.form.get("code")):
                session.pop("voorbeeld_pogingen", None)
                voorbeeld_gelukt(db, ip_h)
                zet_voorbeeld(session, instellingen)
                return redirect(url_for("club_van_20_aanmelden"))
            else:
                session["voorbeeld_pogingen"] = pogingen + 1
                voorbeeld_mislukt(db, ip_h)
                fout, status = "Dat is niet de juiste code.", 400
        return (
            render_template(
                "club_van_20_aanmelden_voorbeeld.html",
                instellingen=instellingen,
                beschikbaar=beschikbaar,
                fout=fout,
                min_tekens=VOORBEELD_MIN_TEKENS,
            ),
            status,
        )

    @app.route("/club-van-20/aanmelden/voorbeeld/stop")
    def club_van_20_aanmelden_voorbeeld_stop():
        session.pop("aanmelden_voorbeeld", None)
        return redirect(url_for("club_van_20_publiek"))

    @app.route("/club-van-20/aanmelden/bedankt")
    def club_van_20_aanmelden_bedankt():
        db = get_db()
        instellingen = _instellingen(db)
        return render_template(
            "club_van_20_aanmelden_bedankt.html",
            instellingen=instellingen,
            klaar=session.get("aanmelding_klaar"),
            mollie_link=_mollie_link(instellingen),
        )

    # ---------- Concepttabel voor de beheerders ----------

    @app.route("/club-van-20/aanmeldingen")
    def club_van_20_aanmeldingen():
        db = get_db()
        instellingen = _instellingen(db)
        ruim_op(db)
        rijen = db.execute(
            "SELECT * FROM club_van_20_aanmeldingen WHERE status = 'nieuw' ORDER BY aangemaakt_op, id"
        ).fetchall()
        openstaand = []
        for r in rijen:
            lid = bestaand_lid_voor(db, r)
            voornaam, achternaam = splits_naam(r["naam"])
            openstaand.append(
                {
                    **dict(r),
                    "lid": dict(lid) if lid else None,
                    "voornaam": lid["voornaam"] if lid and lid["voornaam"] else voornaam,
                    "achternaam": lid["achternaam"] if lid and lid["achternaam"] else achternaam,
                }
            )
        behandeld = db.execute(
            """SELECT a.*, l.naam AS lid_naam FROM club_van_20_aanmeldingen a
               LEFT JOIN club_van_20_leden l ON l.id = a.lid_id
               WHERE a.status != 'nieuw' ORDER BY a.behandeld_op DESC, a.id DESC LIMIT 50"""
        ).fetchall()
        return render_template(
            "club_van_20_aanmeldingen.html",
            openstaand=openstaand,
            behandeld=behandeld,
            teams=[
                r["team"]
                for r in db.execute(
                    """SELECT DISTINCT team FROM club_van_20_leden
                       WHERE team IS NOT NULL AND team != '' ORDER BY team COLLATE NOCASE"""
                ).fetchall()
            ],
            betaalwijzen=BETAALWIJZEN,
            max_tekens=max_tekens(instellingen),
            instellingen=instellingen,
            status=aanmelden_status(instellingen),
            vandaag=vandaag_amsterdam().isoformat(),
        )

    def _openstaande_aanmelding(db, aanmelding_id):
        rij = db.execute(
            "SELECT * FROM club_van_20_aanmeldingen WHERE id = ?", (aanmelding_id,)
        ).fetchone()
        if rij is None or rij["status"] != "nieuw":
            flash("Deze aanmelding is al behandeld of bestaat niet meer.", "error")
            return None
        return rij

    @app.route("/club-van-20/aanmeldingen/<int:aanmelding_id>/goedkeuren", methods=["POST"])
    def club_van_20_aanmelding_goedkeuren(aanmelding_id):
        db = get_db()
        aanmelding = _openstaande_aanmelding(db, aanmelding_id)
        if aanmelding is None:
            return redirect(url_for("club_van_20_aanmeldingen"))
        if not request.form.get("betaling_gecontroleerd"):
            flash("Vink aan dat je de betaling hebt gecontroleerd.", "error")
            return redirect(url_for("club_van_20_aanmeldingen"))
        maximum = max_tekens(_instellingen(db))
        bordje = (request.form.get("bordje") or "").strip()
        if len(bordje) > maximum:
            flash(f"Het bordje mag hooguit {maximum} tekens zijn.", "error")
            return redirect(url_for("club_van_20_aanmeldingen"))
        gegevens = {k: request.form.get(k) for k in (
            "bordje", "modus", "voornaam", "achternaam", "team", "telefoon", "email", "betaalwijze", "betaald_op",
        )}
        gegevens["lid_id"] = request.form.get("lid_id", type=int)
        gegevens["bordje_aanpassen"] = bool(request.form.get("bordje_aanpassen"))
        gegevens["bedrag"] = _bedrag(request.form.get("bedrag"))
        if gegevens["betaalwijze"] not in BETAALWIJZEN:
            gegevens["betaalwijze"] = None
        lid_id, fout = keur_goed(
            db,
            aanmelding,
            gegevens,
            session.get("gebruiker_naam"),
            _instellingen(db)["club_van_20_bedrag"],
        )
        if fout:
            db.rollback()
            flash(fout, "error")
            return redirect(url_for("club_van_20_aanmeldingen"))
        flash(
            f"'{aanmelding['bordje']}' is goedgekeurd en staat nu bij de leden "
            f"(het bordje komt op het scherm).",
            "success",
        )
        return redirect(url_for("club_van_20_aanmeldingen"))

    @app.route("/club-van-20/aanmeldingen/<int:aanmelding_id>/afwijzen", methods=["POST"])
    def club_van_20_aanmelding_afwijzen(aanmelding_id):
        db = get_db()
        aanmelding = _openstaande_aanmelding(db, aanmelding_id)
        if aanmelding is None:
            return redirect(url_for("club_van_20_aanmeldingen"))
        wijs_af(db, aanmelding_id, request.form.get("reden"), session.get("gebruiker_naam"))
        flash(f"Aanmelding van '{aanmelding['bordje']}' afgewezen.", "success")
        return redirect(url_for("club_van_20_aanmeldingen"))
