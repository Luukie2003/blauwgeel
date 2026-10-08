"""Scherminstellingen voor de Club van 20-dia's en de publieke pagina."""

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import qr
from aanmeldingen import (
    STANDAARD_MAX_TEKENS,
    VOORBEELD_MIN_TEKENS,
    aanmelden_status,
    aanmelden_status_voor,
)
from club_van_20 import (
    aankondiging,
    financien,
    huidig_seizoen,
    leden_met_bijdragen,
    onbetaald_actie,
    team_stand,
    zichtbare_leden,
)
from database import get_db
from helpers import KIOSK_AFBEELDINGEN_MAP, is_ajax_verzoek, sla_afbeelding_op
from routes.club_van_20.gedeeld import (
    _aftelmoment,
    _bedrag,
    _datum,
    _getal,
    _instellingen,
    _veilige_link,
)


def register_routes(app):
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
            # De code voor het voorbeeld van het aanmeldformulier (geheime knop):
            # leeg = uit; te kort wordt niet opgeslagen, de oude blijft dan staan.
            ingevulde_code = (request.form.get("club_van_20_voorbeeldcode") or "").strip()[:60]
            code_te_kort = 0 < len(ingevulde_code) < VOORBEELD_MIN_TEKENS
            voorbeeldcode_nieuw = (
                instellingen["club_van_20_voorbeeldcode"] if code_te_kort else (ingevulde_code or None)
            )
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
                       club_van_20_seizoenen_per_ster = ?, club_van_20_glans_vanaf_sterren = ?,
                       club_van_20_aanmelden_aan = ?, club_van_20_bordje_max_tekens = ?,
                       club_van_20_voorbeeldcode = ?,
                       club_van_20_onbetaald_tot = ?, club_van_20_onbetaald_seizoenen = ?
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
                    1 if request.form.get("club_van_20_aanmelden_aan") else 0,
                    max(5, min(60, _getal("club_van_20_bordje_max_tekens", STANDAARD_MAX_TEKENS))),
                    voorbeeldcode_nieuw,
                    _datum(request.form.get("club_van_20_onbetaald_tot")),
                    max(0, min(20, _getal("club_van_20_onbetaald_seizoenen", 3))),
                ),
            )
            db.commit()
            melding = "Club van 20-instellingen opgeslagen."
            if code_te_kort:
                melding += f" De code voor het voorbeeld is niet gewijzigd: gebruik minstens {VOORBEELD_MIN_TEKENS} tekens."
            if is_ajax_verzoek():
                return jsonify({"ok": True, "melding": melding})
            flash(melding, "warning" if code_te_kort else "success")
            return redirect(url_for("club_van_20_instellingen"))
        publiek_url = url_for("club_van_20_publiek", _external=True)
        op_scherm = zichtbare_leden(db, instellingen)
        return render_template(
            "club_van_20_instellingen.html",
            instellingen=instellingen,
            publiek_url=publiek_url,
            publiek_qr_svg=qr.qr_svg(publiek_url),
            aantal_op_scherm=len(op_scherm),
            aantal_onbetaald_op_scherm=sum(1 for lid in op_scherm if not lid["betaald"]),
            onbetaald_actie=onbetaald_actie(instellingen),
            aanmelden=aanmelden_status(instellingen),
            voorbeeld_min_tekens=VOORBEELD_MIN_TEKENS,
        )

    # ---------- Publieke pagina (QR-code op de wervingsdia) ----------

    @app.route("/club-van-20/doe-mee")
    def club_van_20_publiek():
        db = get_db()
        instellingen = _instellingen(db)
        # Ook tijdens de tijdelijke herinnering (onbetaalden lichtrood op het
        # scherm) staan hier alleen wie dit seizoen echt meedoet.
        zichtbaar = [lid for lid in zichtbare_leden(db, instellingen) if lid["betaald"]]
        return render_template(
            "club_van_20_publiek.html",
            instellingen=instellingen,
            aankondiging=aankondiging(instellingen),
            aanmelden=aanmelden_status_voor(instellingen, session),
            namen=zichtbaar,
            teams=team_stand(zichtbaar, leden_met_bijdragen(db, alleen_actief=True)),
            geld=financien(db, instellingen["club_van_20_bedrag"]),
            seizoen=huidig_seizoen(),
        )
