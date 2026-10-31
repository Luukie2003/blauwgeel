"""Mappen, momenten en de schijnwerper van de kantine-tv (1.76.0, zie kiosk_momenten.py): de gegevens voor de schermen,
de mappen beheren, en bijsturen op de avond (Nu tonen, Stop, Later, Voorbeeld)."""

import hashlib
import json
from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, url_for

import kiosk_momenten
import kiosk_tvs
from database import get_db
from helpers import is_ajax_verzoek
from routes.kiosk.dia_gegevens import _sponsor_slide
from routes.kiosk.gedeeld import bewaarde_uitkomst

ms = kiosk_momenten.ms


def _schermdia(dia, eigen_sjablonen, producten_bij_id, tijden):
    """Een dia zoals de schijnwerper hem toont: dezelfde inhoud als in de diashow (_kiosk_sponsor_inhoud.html)."""
    slide = _sponsor_slide(dia, eigen_sjablonen, producten_bij_id, None, tijden)
    if slide is None:
        return None
    return {
        "id": dia["id"],
        "titel": dia["titel"] or "",
        "klasse": f"slide slide-sponsor sjabloon-{slide['sjabloon']} tekst-{slide['tekst_grootte']}",
        "inhoud": render_template("_kiosk_sponsor_inhoud.html", slide=slide),
        "effect": slide["effect"],
        "opties": slide["opties"],
        "kleur": slide["kleur"],
    }


def schermgegevens(db, extra_dia_id=None):
    """Wat de schermen nodig hebben voor de schijnwerper en de balk (zie templates/_kiosk_moment.html): de momenten van
    nu tot een dag vooruit, elk met zijn inhoud ("van", "spot" = einde van de schijnwerper, "einde": in ms), de
    schijnwerper die met de hand loopt of is gestopt, een versie (zodat de schermen alleen iets nieuws ophalen als er
    iets veranderd is) en de klok van de server ("nu", in ms). extra_dia_id: deze dia er ook bij (Voorbeeld)."""

    def bereken():
        nu = datetime.now()
        eigen = {r["id"]: r for r in db.execute("SELECT * FROM kiosk_sjablonen_custom").fetchall()}
        prijzen = {r["id"]: r for r in db.execute("SELECT id, verkoopprijs FROM producten").fetchall()}
        tijden = kiosk_momenten.tijden_per_map(db, db.execute("SELECT * FROM kiosk_sponsoren WHERE actief = 1").fetchall())
        lijst = []
        for m in kiosk_momenten.momenten(db, nu):
            item = _schermdia(m["dia"], eigen, prijzen, tijden)
            if item is None:
                continue
            start = kiosk_momenten.tijdstip(m["dia"]["moment"])
            item.update({
                "van": ms(m["van"]), "spot": ms(m["spot_tot"]), "einde": ms(m["einde"]),
                "tijd": f"{start:%H:%M}" if start else "",
                "balk": (m["dia"]["balk_tekst"] or "").strip() or None,
            })
            lijst.append(item)
        if extra_dia_id and not any(i["id"] == extra_dia_id for i in lijst):
            dia = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (extra_dia_id,)).fetchone()
            item = _schermdia(dia, eigen, prijzen, tijden) if dia else None
            if item:
                start = kiosk_momenten.tijdstip(dia["moment"])
                item.update({"van": None, "spot": None, "einde": None, "tijd": f"{start:%H:%M}" if start else "",
                             "balk": (dia["balk_tekst"] or "").strip() or None})
                lijst.append(item)
        handmatig = kiosk_momenten.handmatige_schijnwerper(db, nu)
        gestopt = kiosk_momenten.gestopte_schijnwerper(db, nu)
        gegevens = {
            "momenten": lijst,
            "handmatig": {"id": handmatig["dia"]["id"], "tot": ms(handmatig["tot"])} if handmatig else None,
            "gestopt": {"id": gestopt["dia_id"], "tot": ms(gestopt["tot"])} if gestopt else None,
        }
        gegevens["versie"] = hashlib.md5(json.dumps(gegevens, sort_keys=True).encode()).hexdigest()[:12]
        return gegevens

    gegevens = bereken() if extra_dia_id else bewaarde_uitkomst("momenten", bereken)
    return {**gegevens, "nu": ms(datetime.now())}


def _terug(melding, fout=None):
    """Terug naar waar de knop stond: 'terug' uit het formulier (een pad op deze site, met #tabblad), anders de vorige
    pagina."""
    if is_ajax_verzoek():
        return jsonify({"ok": fout is None, "melding": fout or melding}), (400 if fout else 200)
    flash(fout or melding, "error" if fout else "success")
    terug = request.form.get("terug") or ""
    if not (terug.startswith("/") and not terug.startswith("//")):
        terug = request.referrer or url_for("kiosk_hub")
    return redirect(terug)


def _kt_status(db):
    """Voor de kop van de kantine-tv-pagina's (_kt_kop.html): hoeveel tv's er aan staan en wat er groot op de tv staat."""
    tvs = [kiosk_tvs.status(tv) for tv in kiosk_tvs.alle_tvs(db)]
    return {"tvs_aan": sum(1 for s in tvs if s["aan"]), "tvs": len(tvs),
            "schijnwerper": kiosk_momenten.in_schijnwerper(db)}


def register_routes(app):
    @app.context_processor
    def _momenten_voor_schermen():
        # Voor templates/_kiosk_moment.html, _kiosk_klok.html en _kt_kop.html: functies, dus alleen een query als een
        # pagina erom vraagt.
        return {
            "kiosk_momenten": lambda extra_dia_id=None: schermgegevens(get_db(), extra_dia_id),
            "kiosk_nu_ms": lambda: ms(datetime.now()),
            "kt_status": lambda: _kt_status(get_db()),
        }

    # ---------- Bijsturen op de avond ----------

    @app.route("/kiosk/momenten/<int:dia_id>/nu", methods=["POST"])
    def kiosk_moment_nu(dia_id):
        """Deze dia nu in de schijnwerper op alle tv's (zie kiosk_momenten.toon_nu)."""
        melding, fout = kiosk_momenten.toon_nu(get_db(), dia_id)
        return _terug(melding, fout)

    @app.route("/kiosk/momenten/stop", methods=["POST"])
    def kiosk_moment_stop():
        return _terug(kiosk_momenten.stop_schijnwerper(get_db()))

    @app.route("/kiosk/momenten/<int:dia_id>/later", methods=["POST"])
    def kiosk_moment_later(dia_id):
        """Het moment van deze dia een kwartier later (of met minuten=-15 eerder)."""
        try:
            minuten = max(-120, min(120, int(request.form.get("minuten") or kiosk_momenten.SCHUIF_MINUTEN)))
        except ValueError:
            minuten = kiosk_momenten.SCHUIF_MINUTEN
        melding, fout = kiosk_momenten.schuif_op(get_db(), dia_id, minuten)
        return _terug(melding, fout)

    @app.route("/kiosk/momenten/<int:dia_id>/voorbeeld")
    def kiosk_moment_voorbeeld(dia_id):
        """De schijnwerper van deze dia in de browser, zonder dat de tv's iets merken."""
        db = get_db()
        if db.execute("SELECT 1 FROM kiosk_sponsoren WHERE id = ?", (dia_id,)).fetchone() is None:
            flash("Deze dia bestaat niet meer.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        return render_template("kiosk_moment_voorbeeld.html", moment_voorbeeld=dia_id,
                               prijzenscherm=request.args.get("scherm") == "prijzen")

    @app.route("/kiosk/griezel-voorbeeld")
    def kiosk_griezel_voorbeeld():
        """Een griezeldia zoals hij op de tv komt, voor het live voorbeeld bij het dia-formulier: een pagina van 1920 bij
        1080 die het formulier verkleind in een iframe toont, zodat de maten (in vw en vh) kloppen. Bij een programma
        licht de eerste regel op, zodat je ziet hoe dat eruitziet."""
        db = get_db()
        args = request.args
        effect = args.get("effect") if args.get("effect") in kiosk_momenten.EFFECTEN else None
        try:
            map_id = int(args.get("map_id") or 0) or None
        except ValueError:
            map_id = None
        dia = {
            "id": 0, "sjabloon": "griezel", "titel": (args.get("titel") or "").strip() or None,
            "tekst": (args.get("tekst") or "").strip() or None,
            "label": " ".join((args.get("label") or "").split())[:30] or None,
            "moment": kiosk_momenten.tekst(kiosk_momenten.tijdstip(args.get("moment"))), "map_id": map_id,
            "effect": effect, "effect_opties": kiosk_momenten.schoon_opties(effect, None, None, None, "griezel",
                                                                            args.get("tekening")),
            "weergave_duur_seconden": 10, "herhalingen": 1, "video": None, "video_duur": None, "video_hele_duur": 0,
            "video_geluid": 0, "afbeelding": None, "overgang": "fade", "tekst_grootte": "normaal",
            "achtergrond_afbeelding": None, "custom_sjabloon_id": None, "webpagina_url": None,
        }
        tijden = kiosk_momenten.tijden_per_map(db, db.execute("SELECT * FROM kiosk_sponsoren WHERE actief = 1").fetchall())
        slide = _sponsor_slide(dia, {}, {}, None, tijden)
        if slide.get("programma_rijen"):
            slide["opties"]["momenten"] = [{"tijd": slide["programma_rijen"][0]["tijd"], "van": 0, "einde": 9 * 10**15}]
        return render_template("kiosk_griezel_voorbeeld.html", slide=slide)

    @app.route("/kiosk/dias/<int:dia_id>/miniatuur")
    def kiosk_dia_miniatuur(dia_id):
        """Het plaatje op de tegel van een dia bij Dia's (1.79.0): de dia zoals op de tv, op een pagina van 1920 bij 1080
        die de tegel verkleind in een iframe toont. Zonder de bewegende effecten; die laat Voorbeeld zien."""
        db = get_db()
        dia = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (dia_id,)).fetchone()
        if dia is None:
            return "Deze dia bestaat niet meer.", 404
        eigen = {r["id"]: r for r in db.execute("SELECT * FROM kiosk_sjablonen_custom").fetchall()}
        prijzen = {r["id"]: r for r in db.execute("SELECT id, verkoopprijs FROM producten").fetchall()}
        tijden = kiosk_momenten.tijden_per_map(db, db.execute("SELECT * FROM kiosk_sponsoren WHERE actief = 1").fetchall())
        return render_template("kiosk_dia_miniatuur.html", slide=_sponsor_slide(dia, eigen, prijzen, None, tijden))

    @app.route("/kiosk/dias/<int:dia_id>/aan", methods=["POST"])
    def kiosk_dia_wisselen(dia_id):
        """Een dia aan of uit in de diashow (aan=1 of 0), met de schakelaar op zijn tegel bij Dia's (1.79.0)."""
        db = get_db()
        dia = db.execute("SELECT titel FROM kiosk_sponsoren WHERE id = ?", (dia_id,)).fetchone()
        if dia is None:
            return _terug(None, "Deze dia bestaat niet meer.")
        aan = request.form.get("aan") == "1"
        db.execute("UPDATE kiosk_sponsoren SET actief = ? WHERE id = ?", (1 if aan else 0, dia_id))
        db.commit()
        naam = f"'{dia['titel']}'" if dia["titel"] else "De dia"
        return _terug(f"{naam} staat nu {'aan' if aan else 'uit'}.")

    # ---------- Mappen ----------

    @app.route("/kiosk/dia-mappen/opslaan", methods=["POST"])
    def kiosk_dia_map_opslaan():
        """Een nieuwe map (zonder map_id) of een map aangepast: naam, en eventueel begin en einde met tijd."""
        db = get_db()
        try:
            map_id = int(request.form.get("map_id") or 0) or None
        except ValueError:
            map_id = None
        if map_id and db.execute("SELECT 1 FROM kiosk_dia_mappen WHERE id = ?", (map_id,)).fetchone() is None:
            return _terug(None, "Deze map bestaat niet meer.")
        _, fout = kiosk_momenten.bewaar_map(db, map_id, request.form.get("naam"), request.form.get("vanaf"),
                                            request.form.get("tot"), actief=request.form.get("actief", "1") == "1")
        return _terug("Map opgeslagen." if map_id else "Map toegevoegd.", fout)

    @app.route("/kiosk/dia-mappen/<int:map_id>/aan", methods=["POST"])
    def kiosk_dia_map_wisselen(map_id):
        """Een hele map aan of uit (aan=1 of 0), met één klik."""
        db = get_db()
        m = db.execute("SELECT * FROM kiosk_dia_mappen WHERE id = ?", (map_id,)).fetchone()
        if m is None:
            return _terug(None, "Deze map bestaat niet meer.")
        aan = request.form.get("aan") == "1"
        kiosk_momenten.zet_map_aan(db, map_id, aan)
        return _terug(f"{m['naam']} staat nu {'aan' if aan else 'uit'}: binnen 10 seconden op de tv's.")

    @app.route("/kiosk/dia-mappen/<int:map_id>/verwijderen", methods=["POST"])
    def kiosk_dia_map_verwijderen(map_id):
        db = get_db()
        m = db.execute("SELECT naam FROM kiosk_dia_mappen WHERE id = ?", (map_id,)).fetchone()
        if m is None:
            return _terug(None, "Deze map bestaat niet meer.")
        kiosk_momenten.verwijder_map(db, map_id)
        return _terug(f"Map '{m['naam']}' verwijderd; de dia's erin staan nu bij Algemeen.")
