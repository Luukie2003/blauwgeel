"""Gekoppelde tv's (zie kiosk_tvs.py): koppelen met een code, het scherm van één tv, en het beheer op Kantine-tv."""

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for

import kiosk_tvs
import qr
from database import get_db
from helpers import is_ajax_verzoek
from routes.kiosk.dia_gegevens import _bouw_slides
from routes.kiosk.gedeeld import _scherm_instellingen, _versie, bewaarde_uitkomst
from routes.kiosk.prijzen_gegevens import _prijzen_poll, _prijzen_render_kwargs

# De tv vraagt zijn pagina even op voordat hij herlaadt (zie _kiosk_herstel.html): dat is geen echte herstart.
CONTROLE_KOP = "X-Kiosk-Controle"


def _tv_json(tv, nu=None):
    return {
        "id": tv["id"],
        "naam": tv["naam"],
        "scherm": tv["scherm"],
        "zoom": tv["zoom"],
        "status": kiosk_tvs.status(tv, nu),
    }


def register_routes(app):
    # ---------- Op de tv ----------

    @app.route("/kiosk/koppelen")
    def kiosk_koppelen():
        """Het adres voor een nieuwe tv: geeft hem een eigen token (bewaard in de tv) en gaat naar zijn eigen adres."""
        antwoord = app.make_response(render_template("kiosk_koppelen_start.html"))
        antwoord.headers["Cache-Control"] = "no-store"
        return antwoord

    @app.route("/kiosk/t/<token>")
    def kiosk_tv_scherm(token):
        """Het scherm van één gekoppelde tv, of (nog niet gekoppeld) de koppelcode."""
        if not kiosk_tvs.geldig_token(token):
            abort(404)
        db = get_db()
        tv = kiosk_tvs.tv_voor_token(db, token)
        voorbeeld = request.args.get("voorbeeld") == "1"
        if tv is None:
            code = None if voorbeeld else kiosk_tvs.koppelcode_voor(db, token)
            # De QR-code bij de koppelcode: scan hem met de handterminal-app (of een telefoon) en je koppelt meteen.
            koppel_qr = qr.qr_svg(url_for("kiosk_koppel_link", code=code, _external=True)) if code else None
            antwoord = app.make_response(render_template(
                "kiosk_koppelen.html", code=code, token=token, koppel_qr=koppel_qr,
                versie=_koppel_versie(code), versie_url=url_for("kiosk_tv_scherm_versie", token=token),
            ))
            antwoord.headers["Cache-Control"] = "no-store"
            return antwoord
        if not voorbeeld and not request.headers.get(CONTROLE_KOP):
            kiosk_tvs.hartslag(db, tv, geladen=True)
        instellingen = _scherm_instellingen(db)
        effectief = kiosk_tvs.effectief_scherm(tv, instellingen)
        eigen = kiosk_tvs.tv_versie(tv, effectief)
        versie_url = url_for("kiosk_tv_scherm_versie", token=token)
        koppeling = {"token": token, "zoom": tv["zoom"], "voorbeeld": voorbeeld, "naam": tv["naam"], "toont": effectief}
        if effectief == "dias":
            slides = _bouw_slides(db)
            antwoord = app.make_response(render_template(
                "kiosk_scherm.html",
                slides=slides,
                sponsors_elke=instellingen["sponsors_elke_dias"],
                versie=bewaarde_uitkomst("scherm", lambda: _versie(slides)) + "-" + eigen,
                versie_url=versie_url,
                tv_koppeling=koppeling,
            ))
        else:
            gegevens = _prijzen_render_kwargs(db, versie_url)
            gegevens["versie"] = gegevens["versie"] + "-" + eigen
            antwoord = app.make_response(render_template("kiosk_prijzen_scherm.html", tv_koppeling=koppeling, **gegevens))
        antwoord.headers["Cache-Control"] = "no-store"
        return antwoord

    @app.route("/kiosk/t/<token>/versie")
    def kiosk_tv_scherm_versie(token):
        """Wat de tv elke 10 seconden vraagt: is er iets veranderd? Met ?beeld=…&app=… (niet bij een voorbeeld op de
        site) is dat ook het teken dat hij aan staat."""
        if not kiosk_tvs.geldig_token(token):
            abort(404)
        db = get_db()
        tv = kiosk_tvs.tv_voor_token(db, token)
        if tv is None:
            return jsonify({"versie": _koppel_versie(kiosk_tvs.koppelcode_voor(db, token))})
        instellingen = _scherm_instellingen(db)
        effectief = kiosk_tvs.effectief_scherm(tv, instellingen)
        if request.args.get("beeld"):
            kiosk_tvs.hartslag(db, tv, toont=effectief, beeld=request.args.get("beeld"), app_versie=request.args.get("app"))
        eigen = kiosk_tvs.tv_versie(tv, effectief)
        if effectief == "dias":
            return jsonify({"versie": bewaarde_uitkomst("scherm", lambda: _versie(_bouw_slides(db))) + "-" + eigen})
        poll = dict(_prijzen_poll(db))
        poll["versie"] = poll["versie"] + "-" + eigen
        return jsonify(poll)

    @app.route("/kiosk/t/<token>/scherm", methods=["POST"])
    def kiosk_tv_scherm_kiezen(token):
        """De tv-app wisselt zelf (knop omlaag: de prijzenlijst, knop omhoog: de dia's), met JSON {toont}. Dat wordt
        de instelling van deze tv, net alsof je het op de site of de handterminal kiest; zo zie je daar ook wat hij
        toont, en het blijft zo na een herstart. Het geheime token van de tv is de toegang (geen inlog, geen cookies,
        dus ook geen csrf_token, zie csrf_beschermen in app.py)."""
        if not kiosk_tvs.geldig_token(token):
            abort(404)
        db = get_db()
        tv = kiosk_tvs.tv_voor_token(db, token)
        if tv is None:
            return jsonify({"ok": False, "melding": "Deze tv is (nog) niet gekoppeld."}), 404
        data = request.get_json(silent=True) or {}
        toont = "prijzen" if data.get("toont") == "prijzen" else "dias"
        kiosk_tvs.bewaar_instellingen(db, tv["id"], tv["naam"], toont, tv["zoom"])
        return jsonify({"ok": True, "toont": toont,
                        "melding": "Prijzenlijst" if toont == "prijzen" else "Dia's"})

    # ---------- Beheer (Kantine-tv) ----------

    @app.route("/kiosk/koppel/<code>")
    def kiosk_koppel_link(code):
        """Waar de QR-code op een nieuwe tv naartoe wijst: Kantine-tv met de code al ingevuld. De handterminal-app
        herkent dit adres zelf en koppelt de tv in de app (zie BasisActivity.openScan)."""
        code = "".join(c for c in code if c.isdigit())[:6]
        return redirect(url_for("kiosk_hub", code=code) + "#tvs")

    @app.route("/kiosk/tvs/koppelen", methods=["POST"])
    def kiosk_tv_koppelen():
        db = get_db()
        tv_id, fout = kiosk_tvs.koppel(
            db, request.form.get("code"), request.form.get("naam"), request.form.get("scherm"), session.get("gebruiker_naam")
        )
        if fout:
            flash(fout, "error")
        else:
            tv = db.execute("SELECT naam FROM kiosk_tvs WHERE id = ?", (tv_id,)).fetchone()
            flash(f"Tv '{tv['naam']}' is gekoppeld. Binnen een paar seconden toont hij wat je hebt gekozen.", "success")
        return redirect(url_for("kiosk_hub") + "#tvs")

    @app.route("/kiosk/tvs/<int:tv_id>/opslaan", methods=["POST"])
    def kiosk_tv_opslaan(tv_id):
        db = get_db()
        if db.execute("SELECT 1 FROM kiosk_tvs WHERE id = ?", (tv_id,)).fetchone() is None:
            abort(404)
        fout = kiosk_tvs.bewaar_instellingen(
            db, tv_id, request.form.get("naam"), request.form.get("scherm"), request.form.get("zoom")
        )
        melding = fout or "Opgeslagen. De tv neemt het binnen een paar seconden over."
        if is_ajax_verzoek():
            return jsonify({"ok": not fout, "melding": melding, "fout": fout}), (400 if fout else 200)
        flash(melding, "error" if fout else "success")
        return redirect(url_for("kiosk_hub") + "#tvs")

    @app.route("/kiosk/tvs/<int:tv_id>/herladen", methods=["POST"])
    def kiosk_tv_herladen(tv_id):
        db = get_db()
        tv = db.execute("SELECT naam FROM kiosk_tvs WHERE id = ?", (tv_id,)).fetchone()
        if tv is None:
            abort(404)
        kiosk_tvs.herlaad(db, tv_id)
        melding = f"Tv '{tv['naam']}' laadt binnen 10 seconden opnieuw (als hij aan staat)."
        if is_ajax_verzoek():
            return jsonify({"ok": True, "melding": melding})
        flash(melding, "success")
        return redirect(url_for("kiosk_hub") + "#tvs")

    @app.route("/kiosk/tvs/<int:tv_id>/verwijderen", methods=["POST"])
    def kiosk_tv_verwijderen(tv_id):
        db = get_db()
        tv = db.execute("SELECT naam FROM kiosk_tvs WHERE id = ?", (tv_id,)).fetchone()
        if tv is None:
            abort(404)
        db.execute("DELETE FROM kiosk_tvs WHERE id = ?", (tv_id,))
        db.commit()
        flash(f"Tv '{tv['naam']}' is ontkoppeld. Hij toont nu weer een koppelcode.", "success")
        return redirect(url_for("kiosk_hub") + "#tvs")

    @app.route("/kiosk/tvs/status")
    def kiosk_tvs_status():
        """Voor Kantine-tv: of de tv's aan staan, elke halve minuut bijgewerkt zonder de pagina te herladen."""
        return jsonify({"tvs": [_tv_json(tv) for tv in kiosk_tvs.alle_tvs(get_db())]})


def _koppel_versie(code):
    return "koppel-" + (code or "vol")
