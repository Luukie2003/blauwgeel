"""JSON-API voor de handterminal-app, deel 3: de kantine-tv vanaf de bar.

Wat je ter plekke wilt regelen, in een paar tikken: hoe de tv's erbij staan (aan of uit, wat ze tonen, opnieuw laden,
de wisselknop), de specials (het uitgelichte product en de prijs-acties aan of uit), de bardienst van vandaag en morgen
(een wissel ter plekke aanpassen) en dia's of hele blokken van de diashow aan of uit. Dia's maken en bewerken, de
indeling van het prijzenscherm, standen en een nieuwe tv koppelen blijven op de site (Kantine-tv).

Zelfde logica en tabellen als de site (kiosk_tvs.py, routes/kiosk/*), zelfde afspraken als routes/app_api.py. De rechten
staan in rechten.py, sectie kantine_tv."""

from datetime import timedelta

from flask import jsonify, session

import kiosk_momenten
import kiosk_timers
import kiosk_tvs
from database import get_db
from helpers import KIOSK_SPONSOR_SJABLONEN, KIOSK_TIJD_PATROON, now_str, vandaag_amsterdam
from routes.app_api import _data, _fout, eenmalig
from routes.kiosk.gedeeld import THEMAS, _scherm_instellingen, kiosk_thema, zet_kiosk_thema
from routes.kiosk.prijzen_gegevens import _uitgelicht_product

SJABLOON_NAMEN = dict(KIOSK_SPONSOR_SJABLONEN) | {"aangepast": "Eigen sjabloon"}

# De blokken van de diashow die je aan of uit kunt zetten (kolom in kiosk_scherm_instellingen, naam in de app).
DIA_BLOKKEN = (
    ("toon_sponsoren", "Dia's en mededelingen"),
    ("toon_club_van_20", "Club van 20"),
    ("toon_wedstrijden", "Komende thuiswedstrijden"),
    ("toon_standen", "Standen"),
    ("toon_motm", "Man of the Match"),
)

MAX_NAMEN = 120


def _tvs(db):
    instellingen = _scherm_instellingen(db)
    return {
        "tvs": [
            {"id": tv["id"], "naam": tv["naam"], "scherm": tv["scherm"], "status": kiosk_tvs.status(tv)}
            for tv in kiosk_tvs.alle_tvs(db)
        ],
        "schermen": [{"sleutel": k, "naam": v} for k, v in kiosk_tvs.SCHERMEN.items()],
        "wissel": instellingen["actief_tv_scherm"] if instellingen["actief_tv_scherm"] == "dias" else "prijzen",
    }


def _specials(db):
    acties = db.execute(
        """SELECT ka.id, ka.tekst, ka.actief, p.naam AS product_naam FROM kiosk_acties ka
           JOIN producten p ON p.id = ka.product_id ORDER BY ka.id"""
    ).fetchall()
    uitgelicht = _uitgelicht_product(db)
    titel = db.execute("SELECT uitgelicht_titel FROM kiosk_prijzen_instellingen WHERE id = 1").fetchone()
    return {
        "uitgelicht": uitgelicht and {"product_id": uitgelicht["product_id"], "naam": uitgelicht["naam"],
                                      "titel": uitgelicht["titel"], "uitverkocht": bool(uitgelicht["kiosk_uitverkocht"])},
        "uitgelicht_titel": (titel["uitgelicht_titel"] if titel else None) or "Snack van de week",
        "acties": [{"id": a["id"], "product": a["product_naam"], "tekst": a["tekst"] or None, "actief": bool(a["actief"])}
                   for a in acties],
    }


def _bardiensten(db):
    """De bardiensten van vandaag en morgen (in Nederlandse tijd), met welke er nu bezig is."""
    vandaag = vandaag_amsterdam()
    morgen = vandaag + timedelta(days=1)
    bezig = kiosk_tvs.bardienst_bezig(db)
    rijen = db.execute(
        "SELECT * FROM kiosk_bardiensten WHERE datum BETWEEN ? AND ? ORDER BY datum, start_tijd",
        (vandaag.isoformat(), morgen.isoformat()),
    ).fetchall()
    return {
        "vandaag": vandaag.isoformat(),
        "morgen": morgen.isoformat(),
        "bardiensten": [
            {"id": b["id"], "datum": b["datum"], "start_tijd": b["start_tijd"], "eind_tijd": b["eind_tijd"],
             "namen": b["namen"], "bezig": bezig is not None and bezig["id"] == b["id"]}
            for b in rijen
        ],
    }


def _momenten(db):
    """Het programma (zie kiosk_momenten.programma) van de afgelopen 12 uur tot twee dagen vooruit, en of er nu iets
    in de schijnwerper staat."""
    programma = kiosk_momenten.programma(db, dagen=2)
    return {
        "momenten": [
            {"id": m["dia"]["id"], "titel": _dia_titel(db, m["dia"]), "tijd": f"{m['van']:%H:%M}", "datum": m["van"].isoformat(),
             "map": m["map"]["naam"] if m["map"] else None, "status": m["status"], "balk": m["dia"]["balk_tekst"]}
            for m in programma
        ],
        "schijnwerper": bool(kiosk_momenten.handmatige_schijnwerper(db))
        or any(m["status"] == "schijnwerper" for m in programma),
    }


def _overzicht(db):
    uitverkocht = db.execute(
        "SELECT COUNT(*) FROM producten WHERE actief = 1 AND toon_op_kiosk = 1 AND kiosk_uitverkocht = 1"
    ).fetchone()[0]
    return {**_tvs(db), **_specials(db), **_bardiensten(db), **_momenten(db), "uitverkocht": uitverkocht,
            "timers": len(kiosk_timers.actieve(db)), "thema": kiosk_thema(db),
            "themas": [{"sleutel": k, "naam": naam} for k, naam in THEMAS.items()]}


def _dia_titel(db, dia):
    """De titel van een dia; zonder titel het begin van de tekst, of de naam van het eigen sjabloon (zoals "Wilner
    Vleeswaren")."""
    if dia["titel"] or (dia["tekst"] or "").strip():
        return dia["titel"] or dia["tekst"].strip()[:40]
    sjabloon = db.execute("SELECT naam FROM kiosk_sjablonen_custom WHERE id = ?", (dia["custom_sjabloon_id"],)).fetchone()
    return sjabloon["naam"] if sjabloon else None


def _schijnwerper(db):
    """Wat er nu groot op alle tv's staat (met de hand, of de eerste minuten van een moment): {"id", "titel"} of None."""
    handmatig = kiosk_momenten.handmatige_schijnwerper(db)
    dia = handmatig["dia"] if handmatig else next(
        (m["dia"] for m in kiosk_momenten.programma(db, dagen=1) if m["status"] == "schijnwerper"), None)
    return {"id": dia["id"], "titel": _dia_titel(db, dia)} if dia else None


def _dias(db):
    instellingen = _scherm_instellingen(db)
    vandaag = vandaag_amsterdam().isoformat()
    dias = []
    for s in db.execute("SELECT * FROM kiosk_sponsoren ORDER BY volgorde, id").fetchall():
        if s["zichtbaar_tot"] and s["zichtbaar_tot"] < vandaag:
            periode = "voorbij"
        elif s["zichtbaar_vanaf"] and s["zichtbaar_vanaf"] > vandaag:
            periode = "later"
        else:
            periode = None
        dias.append({
            "id": s["id"],
            "titel": _dia_titel(db, s),
            "map_id": s["map_id"],
            "moment": s["moment"],
            "soort": SJABLOON_NAMEN.get(s["sjabloon"], s["sjabloon"]),
            "actief": bool(s["actief"]),
            "vanaf": s["zichtbaar_vanaf"],
            "tot": s["zichtbaar_tot"],
            "periode": periode,
        })
    mappen = [
        {"id": m["id"], "naam": m["naam"], "aan": bool(m["actief"]), "status": kiosk_momenten.map_status(m),
         "vanaf": m["vanaf"], "tot": m["tot"],
         "dias": db.execute("SELECT COUNT(*) FROM kiosk_sponsoren WHERE map_id = ?", (m["id"],)).fetchone()[0]}
        for m in kiosk_momenten.mappen(db)
    ]
    return {
        "blokken": [{"sleutel": k, "naam": naam, "aan": bool(instellingen[k])} for k, naam in DIA_BLOKKEN],
        "mappen": mappen,
        "dias": dias,
        "schijnwerper": _schijnwerper(db),
    }


def _getal_of(waarde, standaard):
    try:
        return int(str(waarde).strip())
    except (TypeError, ValueError):
        return standaard


def _tijd(waarde, standaard):
    waarde = str(waarde or "").strip()
    return waarde if KIOSK_TIJD_PATROON.match(waarde) else standaard


def register_routes(app):
    @app.route("/api/app/kantine-tv")
    def api_app_kantine_tv():
        return jsonify(_overzicht(get_db()))

    # ------------------------------------------------------------ tv's

    @app.route("/api/app/kantine-tv/tvs/<int:tv_id>/scherm", methods=["POST"])
    def api_app_tv_scherm(tv_id):
        """{scherm: prijzen | dias | wissel}: wat deze tv toont. Naam en zoom blijven zoals ze zijn."""
        db = get_db()
        tv = db.execute("SELECT * FROM kiosk_tvs WHERE id = ?", (tv_id,)).fetchone()
        if tv is None:
            return _fout("Deze tv is niet meer gekoppeld.", 404, "niet_gevonden")
        scherm = _data().get("scherm")
        fout = kiosk_tvs.bewaar_instellingen(db, tv_id, tv["naam"], scherm, tv["zoom"])
        if fout:
            return _fout(fout)
        naam = kiosk_tvs.SCHERMEN[scherm].split(" (")[0].lower()
        return jsonify({**_overzicht(db), "melding": f"{tv['naam']} toont nu: {naam}. Binnen een paar seconden op de tv."})

    @app.route("/api/app/kantine-tv/tvs/koppelen", methods=["POST"])
    def api_app_tv_koppelen():
        """{code (6 cijfers, van de tv of uit de QR-code), naam, scherm, verzoek_id}: een nieuwe tv koppelen, zoals
        Kantine-tv → Tv koppelen op de site (kiosk_tvs.koppel)."""
        data = _data()

        def actie(db):
            tv_id, fout = kiosk_tvs.koppel(db, str(data.get("code") or ""), data.get("naam"), data.get("scherm"),
                                           session.get("gebruiker_naam"))
            if fout:
                return {"fout": "fout", "melding": fout}, 400
            tv = db.execute("SELECT naam FROM kiosk_tvs WHERE id = ?", (tv_id,)).fetchone()
            return {**_overzicht(db), "melding": f"Tv '{tv['naam']}' is gekoppeld. Binnen een paar seconden toont hij wat je koos."}, 200

        return eenmalig(actie)

    @app.route("/api/app/kantine-tv/tvs/<int:tv_id>/herladen", methods=["POST"])
    def api_app_tv_herladen(tv_id):
        db = get_db()
        tv = db.execute("SELECT naam FROM kiosk_tvs WHERE id = ?", (tv_id,)).fetchone()
        if tv is None:
            return _fout("Deze tv is niet meer gekoppeld.", 404, "niet_gevonden")
        kiosk_tvs.herlaad(db, tv_id)
        return jsonify({**_overzicht(db), "melding": f"{tv['naam']} laadt binnen 10 seconden opnieuw (als hij aan staat)."})

    @app.route("/api/app/kantine-tv/thema", methods=["POST"])
    def api_app_tv_thema():
        """{thema: "halloween" of null}: een thema op alle schermen aan, of uit (zoals op de Kiosk-hub)."""
        db = get_db()
        thema = zet_kiosk_thema(db, _data().get("thema") or None)
        melding = f"{THEMAS[thema]}-thema staat aan: binnen 10 seconden op alle tv's." if thema \
            else "Thema uit: de tv's zijn binnen 10 seconden weer gewoon."
        return jsonify({**_overzicht(db), "melding": melding})

    @app.route("/api/app/kantine-tv/wissel", methods=["POST"])
    def api_app_tv_wissel():
        """{toont: prijzen | dias}: wat de wisselschermen tonen (de wisselknop van Kantine-tv)."""
        toont = "dias" if _data().get("toont") == "dias" else "prijzen"
        db = get_db()
        db.execute("UPDATE kiosk_scherm_instellingen SET actief_tv_scherm = ? WHERE id = 1", (toont,))
        db.commit()
        melding = "De wisselschermen tonen nu de dia's." if toont == "dias" else "De wisselschermen tonen nu de prijzenlijst."
        return jsonify({**_overzicht(db), "melding": melding})

    # ------------------------------------------------------------ specials

    @app.route("/api/app/kantine-tv/acties/<int:actie_id>", methods=["POST"])
    def api_app_tv_actie(actie_id):
        """{actief: true/false}: de prijs-actie (de pop-up over het prijzenscherm) aan of uit."""
        db = get_db()
        actie = db.execute(
            "SELECT p.naam FROM kiosk_acties ka JOIN producten p ON p.id = ka.product_id WHERE ka.id = ?", (actie_id,)
        ).fetchone()
        if actie is None:
            return _fout("Deze actie bestaat niet meer.", 404, "niet_gevonden")
        actief = bool(_data().get("actief"))
        db.execute("UPDATE kiosk_acties SET actief = ? WHERE id = ?", (1 if actief else 0, actie_id))
        db.commit()
        return jsonify({**_overzicht(db), "melding": f"Actie {actie['naam']} staat nu {'aan' if actief else 'uit'}."})

    @app.route("/api/app/kantine-tv/uitgelicht", methods=["POST"])
    def api_app_tv_uitgelicht():
        """{product_id (leeg: uit), titel}: het uitgelichte product op het prijzenscherm, zoals 'Snack van de week'."""
        data = _data()
        db = get_db()
        product_id = data.get("product_id")
        product = None
        if product_id not in (None, ""):
            product = db.execute("SELECT id, naam FROM producten WHERE id = ? AND actief = 1", (product_id,)).fetchone()
            if product is None:
                return _fout("Kies een product dat nog verkocht wordt.")
        huidig = db.execute("SELECT uitgelicht_titel FROM kiosk_prijzen_instellingen WHERE id = 1").fetchone()
        titel = " ".join(str(data.get("titel") or "").split())[:60] or (huidig and huidig["uitgelicht_titel"]) or "Snack van de week"
        db.execute(
            "UPDATE kiosk_prijzen_instellingen SET uitgelicht_product_id = ?, uitgelicht_titel = ? WHERE id = 1",
            (product["id"] if product else None, titel),
        )
        db.commit()
        melding = f"{titel}: {product['naam']}. Staat op het prijzenscherm." if product else "Er staat geen product meer uitgelicht."
        return jsonify({**_overzicht(db), "melding": melding})

    @app.route("/api/app/kantine-tv/producten")
    def api_app_tv_producten():
        """Waaruit je het uitgelichte product kiest: alle producten die nog verkocht worden."""
        rijen = get_db().execute(
            "SELECT id, naam, categorie, toon_op_kiosk FROM producten WHERE actief = 1 ORDER BY naam COLLATE NOCASE"
        ).fetchall()
        return jsonify({"producten": [{"id": r["id"], "naam": r["naam"], "categorie": r["categorie"] or "",
                                       "op_prijzenscherm": bool(r["toon_op_kiosk"])} for r in rijen]})

    # ------------------------------------------------------------ bardienst

    def _bardienst_uit(data, bestaand=None):
        """(gegevens, fout) uit {datum, start_tijd, eind_tijd, namen}; bij bewerken blijft wat niet is meegestuurd."""
        namen = " ".join(str(data.get("namen") if "namen" in data else (bestaand["namen"] if bestaand else "")).split())
        if not namen:
            return None, "Vul in wie er bardienst heeft."
        if len(namen) > MAX_NAMEN:
            return None, "Dat zijn te veel tekens voor de namen."
        vandaag = vandaag_amsterdam()
        toegestaan = {vandaag.isoformat(), (vandaag + timedelta(days=1)).isoformat()}
        datum = str(data.get("datum") or (bestaand["datum"] if bestaand else vandaag.isoformat()))
        if bestaand is None and datum not in toegestaan:
            return None, "In de app plan je een bardienst voor vandaag of morgen. De rest doe je op de site."
        return {
            "datum": datum,
            "start_tijd": _tijd(data.get("start_tijd"), bestaand["start_tijd"] if bestaand else "00:00"),
            "eind_tijd": _tijd(data.get("eind_tijd"), bestaand["eind_tijd"] if bestaand else "23:59"),
            "namen": namen,
        }, None

    @app.route("/api/app/kantine-tv/bardiensten", methods=["POST"])
    def api_app_tv_bardienst_nieuw():
        """{datum (vandaag of morgen), start_tijd, eind_tijd, namen, verzoek_id}"""
        gegevens, fout = _bardienst_uit(_data())
        if fout:
            return _fout(fout)

        def actie(db):
            db.execute(
                """INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?)""",
                (gegevens["datum"], gegevens["start_tijd"], gegevens["eind_tijd"], gegevens["namen"], now_str()),
            )
            return {**_overzicht(db), "melding": f"Bardienst {gegevens['start_tijd']}-{gegevens['eind_tijd']} staat erbij."}, 200

        return eenmalig(actie)

    @app.route("/api/app/kantine-tv/bardiensten/<int:bardienst_id>", methods=["POST"])
    def api_app_tv_bardienst(bardienst_id):
        """{namen, start_tijd, eind_tijd}: een bardienst aanpassen, bijvoorbeeld een wissel ter plekke."""
        db = get_db()
        bestaand = db.execute("SELECT * FROM kiosk_bardiensten WHERE id = ?", (bardienst_id,)).fetchone()
        if bestaand is None:
            return _fout("Deze bardienst bestaat niet meer.", 404, "niet_gevonden")
        gegevens, fout = _bardienst_uit(_data(), bestaand)
        if fout:
            return _fout(fout)
        db.execute(
            "UPDATE kiosk_bardiensten SET start_tijd = ?, eind_tijd = ?, namen = ? WHERE id = ?",
            (gegevens["start_tijd"], gegevens["eind_tijd"], gegevens["namen"], bardienst_id),
        )
        db.commit()
        return jsonify({**_overzicht(db), "melding": "Bardienst aangepast. Staat binnen een paar seconden op de tv."})

    @app.route("/api/app/kantine-tv/bardiensten/<int:bardienst_id>/verwijderen", methods=["POST"])
    def api_app_tv_bardienst_verwijderen(bardienst_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_bardiensten WHERE id = ?", (bardienst_id,))
        db.commit()
        return jsonify({**_overzicht(db), "melding": "Bardienst verwijderd."})

    # ------------------------------------------------------------ dia's

    @app.route("/api/app/kantine-tv/dias")
    def api_app_tv_dias():
        return jsonify(_dias(get_db()))

    @app.route("/api/app/kantine-tv/dias/<int:dia_id>", methods=["POST"])
    def api_app_tv_dia(dia_id):
        """{actief: true/false}: deze dia draait wel of niet mee in de diashow."""
        db = get_db()
        dia = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (dia_id,)).fetchone()
        if dia is None:
            return _fout("Deze dia bestaat niet meer.", 404, "niet_gevonden")
        actief = bool(_data().get("actief"))
        db.execute("UPDATE kiosk_sponsoren SET actief = ? WHERE id = ?", (1 if actief else 0, dia_id))
        db.commit()
        titel = _dia_titel(db, dia)
        naam = f"'{titel}'" if titel else "De dia"
        return jsonify({**_dias(db), "melding": f"{naam} staat nu {'aan' if actief else 'uit'}."})

    @app.route("/api/app/kantine-tv/mappen/<int:map_id>", methods=["POST"])
    def api_app_tv_map(map_id):
        """{aan: true/false}: een hele map dia's (zoals "Halloween feest") aan of uit."""
        db = get_db()
        m = db.execute("SELECT * FROM kiosk_dia_mappen WHERE id = ?", (map_id,)).fetchone()
        if m is None:
            return _fout("Deze map bestaat niet meer.", 404, "niet_gevonden")
        aan = bool(_data().get("aan"))
        kiosk_momenten.zet_map_aan(db, map_id, aan)
        return jsonify({**_dias(db), "melding": f"{m['naam']} staat nu {'aan' if aan else 'uit'}."})

    # ------------------------------------------------------------ momenten en de schijnwerper

    def _bijgewerkt(db, melding):
        """Het antwoord na de schijnwerper aan of uit: het hele overzicht, of met {lijst: "dias"} de diashow (vanuit
        Diashow in de app, 2.20.0)."""
        return jsonify({**(_dias(db) if _data().get("lijst") == "dias" else _overzicht(db)), "melding": melding})

    @app.route("/api/app/kantine-tv/momenten/<int:dia_id>/nu", methods=["POST"])
    def api_app_tv_moment_nu(dia_id):
        """Deze dia nu in de schijnwerper op alle tv's (zie kiosk_momenten.toon_nu); dat kan elke dia zijn, ook een dia
        zonder moment (zoals het programma)."""
        db = get_db()
        melding, fout = kiosk_momenten.toon_nu(db, dia_id)
        if fout:
            return _fout(fout, 404, "niet_gevonden")
        return _bijgewerkt(db, melding)

    @app.route("/api/app/kantine-tv/momenten/<int:dia_id>/later", methods=["POST"])
    def api_app_tv_moment_later(dia_id):
        """{minuten} (standaard 15): het moment van deze dia later, of met een negatief aantal eerder."""
        db = get_db()
        minuten = _getal_of(_data().get("minuten"), kiosk_momenten.SCHUIF_MINUTEN)
        melding, fout = kiosk_momenten.schuif_op(db, dia_id, max(-120, min(120, minuten)))
        if fout:
            return _fout(fout)
        return jsonify({**_overzicht(db), "melding": melding})

    @app.route("/api/app/kantine-tv/schijnwerper/stop", methods=["POST"])
    def api_app_tv_schijnwerper_stop():
        db = get_db()
        return _bijgewerkt(db, kiosk_momenten.stop_schijnwerper(db))

    @app.route("/api/app/kantine-tv/dia-blokken/<sleutel>", methods=["POST"])
    def api_app_tv_dia_blok(sleutel):
        """{aan: true/false}: een heel blok van de diashow (bijvoorbeeld de standen) aan of uit."""
        namen = dict(DIA_BLOKKEN)
        if sleutel not in namen:
            return _fout("Dit onderdeel van de diashow bestaat niet.", 404, "niet_gevonden")
        aan = bool(_data().get("aan"))
        db = get_db()
        # sleutel komt uit DIA_BLOKKEN (hierboven gecontroleerd), dus veilig als kolomnaam.
        db.execute(f"UPDATE kiosk_scherm_instellingen SET {sleutel} = ? WHERE id = 1", (1 if aan else 0,))
        db.commit()
        return jsonify({**_dias(db), "melding": f"{namen[sleutel]}: staat nu {'aan' if aan else 'uit'}."})
