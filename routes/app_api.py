"""JSON-API voor de handterminal-app (android-apps/handterminal).

De app heeft eigen schermen voor het dagelijkse werk (startscherm, zoeken, boeken, tellen, barcodes koppelen) en vraagt
hier alleen de gegevens op; er wordt geen pagina gebouwd. Dat is veel sneller op de handterminal. De logica is dezelfde
als op de site: boeken via boek_mutatie, tellen via de looplijst (zelfde opgeslagen stand, dus pauzeren op de app en
verder op de site kan ook) en verwerk_telling, koppelen via barcodes.snel_koppelen. Factuur inboeken heeft al een eigen
API (zie routes/facturen.py).

Inloggen gaat met de persoonlijke code (tablet_code_inloggen); daarna stuurt de app de sessie-cookie mee, en bij elke
POST het csrf_token in de header X-CSRF-Token. Zonder sessie of zonder rechten krijgt de app JSON terug, nooit een
doorverwijzing (zie is_app_api in app.py). De rechten per endpoint staan in rechten.py.

Schrijfacties (boeken, een telling bevestigen, koppelen) mogen een verzoek_id meegeven. Hetzelfde verzoek_id nog een keer
geeft het bewaarde antwoord terug zonder het opnieuw te doen (zie eenmalig): zo kan de app een actie veilig opnieuw
sturen als de verbinding wegviel voordat het antwoord binnen was."""

import hashlib
import json

from flask import Response, jsonify, request, session, url_for

import barcodes
import kiosk_timers
from database import get_db
from derving import DERVING_REDENEN, kies_reden
from helpers import (
    bereken_bestellijst_meldingen,
    bestel_advies,
    bereken_pda_start,
    bestel_suggesties,
    besteleenheid_factor,
    besteleenheid_naam,
    boek_mutatie,
    dagdeel_groet,
    heeft_sectie_toegang,
    naar_besteleenheden,
    now_str,
    regels_per_bestelling,
    stuur_tag_notificaties,
)
from helpers.afbeeldingen import kleine_afbeelding
from productkaart import TELLEN_VOORWAARDE
from routes.tellen.looplijst import controle_regels, optellen
from routes.tellen.looplijst_opslag import bewaar_stand, bewaarde_stand, stand_verlopen, wis_stand
from routes.tellen.verwerken import verwerk_telling
from voorspelling import verwachte_verkoop_sinds_telling, verwachte_voorraad

# De nieuwste versie van de app. Draait er een oudere, dan meldt de app dat er een nieuwe is.
HANDTERMINAL_APP_VERSIE = "2.6.0"

MAX_AANTAL = 100000


def _data():
    gegevens = request.get_json(silent=True)
    return gegevens if isinstance(gegevens, dict) else {}


def _fout(melding, status=400, soort="fout"):
    return jsonify({"fout": soort, "melding": melding}), status


def _getal(waarde, standaard=None):
    try:
        return int(str(waarde).strip())
    except (TypeError, ValueError):
        return standaard


def _barcodes_per_product(db, product_id=None):
    """{product_id: [{"code", "niveau", "aantal", "artikel"}]}: wat een scan betekent, voor in de productlijst van de
    app. 'aantal' is in de eenheid van het product (een krat van 24 flessen: 24)."""
    sql = "SELECT product_id, naam, ean, ean_omverpakking, aantal_per_verpakking, per_omverpakking FROM artikelen"
    rijen = db.execute(sql + (" WHERE product_id = ?" if product_id else "") + " ORDER BY id",
                       (product_id,) if product_id else ()).fetchall()
    per_product = {}
    for a in rijen:
        per_verpakking = a["aantal_per_verpakking"] or 1
        doos = per_verpakking * (a["per_omverpakking"] or 1) if a["ean_omverpakking"] else None
        if a["ean"]:
            # doos_aantal/doos_code: de doos waar deze verpakking in zit, voor de vraag "volledige besteleenheid
            # inboeken?" als je een losse verpakking scant.
            per_product.setdefault(a["product_id"], []).append(
                {"code": a["ean"], "niveau": "verpakking", "aantal": per_verpakking, "artikel": a["naam"],
                 "doos_aantal": doos, "doos_code": a["ean_omverpakking"]})
        if a["ean_omverpakking"]:
            per_product.setdefault(a["product_id"], []).append(
                {"code": a["ean_omverpakking"], "niveau": "omverpakking",
                 "aantal": per_verpakking * (a["per_omverpakking"] or 1), "artikel": a["naam"]})
    return per_product


def _product_json(rij, codes):
    factor = besteleenheid_factor(rij)
    return {
        "id": rij["id"],
        "naam": rij["naam"],
        "categorie": rij["categorie"] or "",
        "subcategorie": rij["subcategorie"] or "",
        "merk": rij["merk"] or "",
        "eenheid": rij["eenheid"] or "stuks",
        "voorraad": rij["voorraad"],
        "min_voorraad": rij["min_voorraad"] or 0,
        "actief": bool(rij["actief"]),
        # Een krat, tray of doos: de knop "+1 krat" bij het boeken.
        "besteleenheid": (rij["besteleenheid"] or "doos") if factor > 1 else None,
        "per_besteleenheid": factor,
        "barcodes": codes.get(rij["id"], []),
        "foto": _foto(rij["afbeelding"], "klein"),
        "foto_groot": _foto(rij["afbeelding"], "middel"),
    }


def _foto(afbeelding, formaat):
    """Het adres van een (verkleinde) productfoto, of None. De app bewaart de foto's zelf (Fotos.kt)."""
    if not afbeelding:
        return None
    return url_for("static", filename="product_afbeeldingen/" + kleine_afbeelding(afbeelding, formaat))


_PRODUCT_SELECT = """SELECT id, naam, categorie, subcategorie, merk, eenheid, voorraad, min_voorraad, actief, besteleenheid,
                            besteleenheid_factor, afbeelding
                     FROM producten"""


def _product(db, product_id):
    rij = db.execute(_PRODUCT_SELECT + " WHERE id = ?", (product_id,)).fetchone()
    return None if rij is None else _product_json(rij, _barcodes_per_product(db, product_id))


def eenmalig(actie):
    """Voert een schrijfactie uit, maar per verzoek_id maar één keer (zie de uitleg bovenaan). actie(db) geeft
    (inhoud, status) terug; het antwoord wordt bewaard in dezelfde transactie als de actie, als die zelf niet al
    commit."""
    db = get_db()
    gebruiker_id = session.get("gebruiker_id")
    verzoek_id = str(_data().get("verzoek_id") or "")[:64]
    if verzoek_id:
        eerder = db.execute(
            "SELECT status, antwoord FROM app_verzoeken WHERE gebruiker_id = ? AND id = ?", (gebruiker_id, verzoek_id)
        ).fetchone()
        if eerder is not None:
            return Response(eerder["antwoord"], status=eerder["status"], mimetype="application/json")
    inhoud, status = actie(db)
    tekst = json.dumps(inhoud, ensure_ascii=False)
    if verzoek_id:
        db.execute(
            """INSERT OR REPLACE INTO app_verzoeken (id, gebruiker_id, status, antwoord, aangemaakt_op)
               VALUES (?, ?, ?, ?, ?)""",
            (verzoek_id, gebruiker_id, status, tekst, now_str()),
        )
    db.commit()
    return Response(tekst, status=status, mimetype="application/json")


def taak_vragen(db, endpoint):
    """De open taken van deze persoon die met deze actie klaar kunnen zijn: de app vraagt dan "Taak afgerond?", net als
    de site na het opslaan (zie vraag_of_taak_klaar_is in routes/eigen_taken.py)."""
    from eigen_taken import vraag_kandidaten

    try:
        return [{"id": t["id"], "titel": t["titel"]} for t in vraag_kandidaten(db, session.get("gebruiker_id"), endpoint)]
    except Exception as fout:  # de vraag is een extraatje: opslaan mag er nooit door mislukken
        print(f"[app] taakvraag overgeslagen: {fout}")
        return []


def _tel_producten(db):
    # Dezelfde volgorde als de looplijst op de site: de opgeslagen stand gaat per positie.
    return db.execute(
        f"""SELECT id, naam, categorie, eenheid, voorraad, afbeelding, besteleenheid, besteleenheid_factor
            FROM producten WHERE {TELLEN_VOORWAARDE} ORDER BY categorie, naam"""
    ).fetchall()


def _invoer(waarden):
    """De ingevulde aantallen van de looplijst: {product_id: aantal} als tekst, zoals de site ze ook bewaart."""
    if not isinstance(waarden, dict):
        return {}
    schoon = {}
    for sleutel, waarde in waarden.items():
        tekst = str(waarde).strip()
        if str(sleutel).isdigit() and tekst.isdigit() and len(tekst) <= 6:
            schoon[str(sleutel)] = tekst
    return schoon


def _webpaginas(rol, secties, pda):
    """De pagina's die (nog) geen eigen scherm in de app hebben: die opent de app als website, ingelogd."""
    heeft = lambda sectie: heeft_sectie_toegang(rol, secties, sectie)  # noqa: E731
    beheerder = rol == "beheerder"
    paginas = []

    def pagina(label, endpoint, groep, teller=None, let_op=False, **kwargs):
        paginas.append({"label": label, "pad": url_for(endpoint, **kwargs), "groep": groep,
                        "teller": teller or None, "let_op": bool(let_op)})

    if heeft("voorraad"):
        pagina("Bestellijst", "bestellijst", "Bestellen", pda.get("open_bestellingen"))
        pagina("Boodschappen", "boodschappenlijst", "Bestellen")
        pagina("Prognose", "prognose_pagina", "Bestellen")
        pagina("Agenda", "agenda", "Bestellen")
        pagina("Tellingen", "tellingen_overzicht", "Voorraad")
        pagina("Geschiedenis", "geschiedenis", "Voorraad")
        pagina("Barcodes", "barcodes_overzicht", "Voorraad")
    pagina("Prikbord", "bijzonderheden", "Kantine", pda.get("mededelingen_open"), pda.get("mededelingen_urgent"))
    if heeft("kassa"):
        pagina("Kassa", "kassa_tellen", "Kantine")
    if heeft("keuken"):
        pagina("Keuken", "keuken_voorraad", "Kantine")
    if beheerder:
        pagina("Kantine-tv", "kiosk_prijzen_instellingen", "Kantine")
        pagina("Kluis", "kluis_tellen", "Beheer")
    if heeft("club_van_20"):
        pagina("Club van 20", "club_van_20_aanmeldingen", "Beheer", pda.get("club_aanmeldingen_open"))
    return paginas


def _kassa_start(db, pda):
    status = pda["kassa_status"] or {}
    return {"status": status.get("status"), "tekst": status.get("tekst"),
            "concepten": db.execute("SELECT COUNT(*) FROM kassa_tellingen WHERE afgesloten = 0").fetchone()[0]}


def _frituurvet_start(status):
    if status is None:
        return None
    return {"ok": status["ok"], "dagen_geleden": status["dagen_geleden"], "interval": status["interval"]}


def register_routes(app):
    @app.route("/api/app/start")
    def api_app_start():
        """Alles voor het startscherm: wie je bent, wat je mag, wat aandacht nodig heeft en welke pagina's er zijn."""
        db = get_db()
        rol, secties, gebruiker_id = session.get("gebruiker_rol"), session.get("gebruiker_secties"), session.get("gebruiker_id")
        pda = bereken_pda_start(db, rol, secties, gebruiker_id)
        toegang = {s: heeft_sectie_toegang(rol, secties, s) for s in ("voorraad", "kassa", "keuken", "club_van_20", "kantine_tv")}
        telling = None
        if pda["telling_status"] is not None:
            laatste = pda["telling_status"]["laatste"]
            telling = {"datum": laatste["datum"] if laatste else None, "door": laatste["naam"] if laatste else None,
                       "dagen_geleden": pda["telling_status"]["dagen_geleden"], "ok": pda["telling_status"]["ok"]}
        looplijst = None
        if toegang["voorraad"] and (stand := bewaarde_stand(db, gebruiker_id)):
            looplijst = {"fase": stand["fase"], "nummer": stand["index"] + 1, "in_controle": stand["review"] is not None,
                         "totaal": len(_tel_producten(db)), "bijgewerkt_op": stand["bijgewerkt_op"]}
        return jsonify({
            "naam": session.get("gebruiker_naam"),
            "groet": dagdeel_groet(),
            "beheerder": rol == "beheerder",
            "toegang": toegang,
            "laag": pda["laag"],
            "open_facturen": pda["open_facturen"],
            "open_bestellingen": pda["open_bestellingen"],
            "mededelingen_open": pda["mededelingen_open"],
            "mededelingen_urgent": pda["mededelingen_urgent"],
            "telling": telling,
            "looplijst": looplijst,
            # Een taak opent in de app een eigen scherm (de stappen, afronden en waar je hem doet: "doel", het endpoint
            # van de pagina op de site; heeft de app daar geen scherm voor, dan zegt hij dat het niet in de app kan).
            "taken": [{"id": t["taak_id"], "titel": t["titel"], "detail": t["detail"], "urgent": bool(t["urgent"]),
                       "doel": t["doel"], "stappen": t["stappen"],
                       "pad": url_for(t["endpoint"], **t["kwargs"])} for t in pda["eigen_taken"]],
            "kassa": _kassa_start(db, pda) if toegang["kassa"] else None,
            "kluis_concepten": db.execute("SELECT COUNT(*) FROM kluis_tellingen WHERE afgesloten = 0").fetchone()[0]
            if rol == "beheerder" else None,
            "frituurvet": _frituurvet_start(pda["frituurvet_status"]) if toegang["keuken"] else None,
            "aanmeldingen_open": db.execute("SELECT COUNT(*) FROM club_van_20_aanmeldingen WHERE status = 'nieuw'").fetchone()[0]
            if toegang["club_van_20"] else None,
            "paginas": _webpaginas(rol, secties, pda),
            # De timers op de tv's (zie kiosk_timers.py) en wat er op het prijzenscherm als uitverkocht staat.
            "timers": kiosk_timers.actieve(db),
            "uitverkocht_op_tv": [r[0] for r in db.execute(
                """SELECT naam FROM producten WHERE actief = 1 AND toon_op_kiosk = 1 AND kiosk_uitverkocht = 1
                   ORDER BY naam COLLATE NOCASE""").fetchall()] if toegang["voorraad"] else None,
            "app_versie": HANDTERMINAL_APP_VERSIE,
        })

    @app.route("/api/app/producten")
    def api_app_producten():
        """Alle producten met hun barcodes, in één keer: de app zoekt en scant daarin zelf, zonder op de server te
        wachten. Met ETag: is er niets veranderd, dan alleen '304'."""
        db = get_db()
        codes = _barcodes_per_product(db)
        rijen = db.execute(
            _PRODUCT_SELECT + " WHERE COALESCE(gearchiveerd, 0) = 0 ORDER BY categorie COLLATE NOCASE, naam COLLATE NOCASE"
        ).fetchall()
        tekst = json.dumps({"producten": [_product_json(r, codes) for r in rijen], "derving_redenen": DERVING_REDENEN},
                           ensure_ascii=False, sort_keys=True)
        etag = '"' + hashlib.sha1(tekst.encode("utf-8")).hexdigest()[:20] + '"'
        if request.headers.get("If-None-Match") == etag:
            return Response(status=304, headers={"ETag": etag})
        return Response(tekst, mimetype="application/json", headers={"ETag": etag})

    @app.route("/api/app/producten/<int:product_id>")
    def api_app_product(product_id):
        """Eén product met de laatste boekingen, de laatste telling en (in "info") alles van de productpagina van de site
        wat zonder het voorspelmodel kan; de verkoop per week haalt de app apart op (api_app_product_verkoop)."""
        from routes.app_api_meer import productinfo_json  # hier pas: app_api_meer gebruikt deze module zelf ook

        db = get_db()
        product = _product(db, product_id)
        if product is None:
            return _fout("Dit product bestaat niet meer.", 404, "niet_gevonden")
        mutaties = db.execute(
            """SELECT type, aantal, datum, naam, opmerking, reden FROM mutaties WHERE product_id = ?
               ORDER BY id DESC LIMIT 8""", (product_id,),
        ).fetchall()
        laatste_telling = db.execute(
            """SELECT t.id, t.datum, t.naam, r.geteld_aantal FROM telling_regels r JOIN tellingen t ON t.id = r.telling_id
               WHERE r.product_id = ? ORDER BY t.id DESC LIMIT 1""", (product_id,),
        ).fetchone()
        verkoopprijs = db.execute("SELECT verkoopprijs FROM producten WHERE id = ?", (product_id,)).fetchone()[0]
        return jsonify({
            "product": product,
            "verkoopprijs": verkoopprijs,
            "mutaties": [{**dict(m), "reden": DERVING_REDENEN.get(m["reden"]) if m["reden"] else None} for m in mutaties],
            "laatste_telling": dict(laatste_telling) if laatste_telling else None,
            "info": productinfo_json(db, product_id),
            "pad": url_for("product_detail", product_id=product_id),
        })

    @app.route("/api/app/producten/<int:product_id>/boeken", methods=["POST"])
    def api_app_boeken(product_id):
        """{type: 'in'|'uit', aantal, reden (bij eruit, mag leeg), opmerking, verzoek_id}"""
        data = _data()

        def boek(db):
            mtype = data.get("type")
            aantal = _getal(data.get("aantal"), 0)
            if mtype not in ("in", "uit") or not 0 < aantal <= MAX_AANTAL:
                return {"fout": "fout", "melding": "Kies erin of eruit, en een aantal van 1 of meer."}, 400
            opmerking = " ".join(str(data.get("opmerking") or "").split())[:200]
            reden = kies_reden(data.get("reden")) if mtype == "uit" else None
            geboekt = boek_mutatie(db, product_id, mtype, aantal, session.get("gebruiker_naam"),
                                   session.get("gebruiker_id"), opmerking, reden)
            if geboekt is None:
                return {"fout": "niet_gevonden", "melding": "Dit product bestaat niet meer."}, 404
            p = geboekt["product"]
            melding = f"{aantal} {p['eenheid']} {'erin' if mtype == 'in' else 'eruit'} geboekt bij {p['naam']}."
            waarschuwing = None
            if geboekt["voorraad"] < 0:
                waarschuwing = f"De voorraad staat nu op {geboekt['voorraad']}. Controleer de telling."
            elif geboekt["gedeactiveerd"]:
                waarschuwing = f"'{p['naam']}' is automatisch op inactief gezet (voorraad op 0)."
            return {"melding": melding, "waarschuwing": waarschuwing, "voorraad": geboekt["voorraad"],
                    "product": _product(db, product_id)}, 200

        return eenmalig(boek)

    @app.route("/api/app/barcodes/koppelen", methods=["POST"])
    def api_app_barcode_koppelen():
        """{code, product_id, per_doos (leeg: één verpakking; anders hoeveel er in de doos of krat zitten), verzoek_id}.
        Uitgebreid (spullen uit de keuken): ook per_verpakking, inkoopprijs en naam (zie barcodes.snel_koppelen)."""
        data = _data()

        def koppel(db):
            code = str(data.get("code") or "")
            _, fout = barcodes.snel_koppelen(db, code, data.get("product_id"), data.get("per_doos"),
                                             door=session.get("gebruiker_naam"), gebruiker_id=session.get("gebruiker_id"),
                                             per_verpakking=data.get("per_verpakking"), inkoopprijs=data.get("inkoopprijs"),
                                             naam=str(data.get("naam") or "").strip() or None)
            if fout:
                return {"fout": "fout", "melding": fout}, 400
            uitkomst = barcodes.zoek_barcode(db, code)
            return {"barcode": barcodes.als_json(uitkomst), "product": _product(db, uitkomst["artikel"]["product_id"])}, 200

        return eenmalig(koppel)

    # ---------- Tellen (de looplijst) ----------

    @app.route("/api/app/tellen")
    def api_app_tellen():
        """De producten van de looplijst, in volgorde, met wat er ongeveer hoort te staan, en de bewaarde stand (of
        null). Het tellen zelf gebeurt op de handterminal; die geeft de stand af en toe door."""
        db = get_db()
        try:
            verwachting = verwachte_verkoop_sinds_telling(db)
        except Exception as fout:
            print(f"[voorspelling] verwachte voorraad mislukt: {fout}")
            verwachting = {}
        return jsonify({
            "producten": [{"id": p["id"], "naam": p["naam"], "categorie": p["categorie"] or "", "eenheid": p["eenheid"],
                           "voorraad": p["voorraad"],
                           "verwacht": verwachte_voorraad(verwachting.get(p["id"]), p["voorraad"]),
                           "foto_groot": _foto(p["afbeelding"], "middel"),
                           "besteleenheid": besteleenheid_naam(p) if besteleenheid_factor(p) > 1 else None,
                           "per_besteleenheid": besteleenheid_factor(p)}
                          for p in _tel_producten(db)],
            "stand": bewaarde_stand(db, session.get("gebruiker_id")),
        })

    def _afgebroken(db, data):
        """Een 409 als deze looplijst (loop_id) intussen ergens anders is afgebroken, opgeslagen of opnieuw begonnen;
        de app stopt dan ook (zie stand_verlopen). 'nieuw': de eerste keer dat de app deze looplijst doorgeeft."""
        reden = stand_verlopen(db, session.get("gebruiker_id"), data.get("loop_id"), bool(data.get("nieuw")))
        return _fout(reden, 409, "afgebroken") if reden else None

    @app.route("/api/app/tellen/stand", methods=["POST"])
    def api_app_tellen_stand():
        """{fase: 'bar'|'hok', index, bar: {product_id: aantal}, hok: {...}, loop_id, nieuw}: de stand bewaren
        (pauzeren, of gewoon tussendoor), zodat je later verder kunt, ook op een ander toestel of op de site. Is de
        looplijst intussen ergens anders afgebroken of opgeslagen, dan een 409 (fout: afgebroken)."""
        db = get_db()
        data = _data()
        if (fout := _afgebroken(db, data)) is not None:
            return fout
        fase = "hok" if data.get("fase") == "hok" else "bar"
        bewaar_stand(db, session.get("gebruiker_id"), fase, max(0, _getal(data.get("index"), 0)),
                     _invoer(data.get("bar")), _invoer(data.get("hok")), loop_id=data.get("loop_id") or None)
        return jsonify({"status": "bewaard"})

    @app.route("/api/app/tellen/controleren", methods=["POST"])
    def api_app_tellen_controleren():
        """{bar, hok}: bar en voorraadhok zijn geteld. Telt ze op en geeft het controlescherm terug: per product de
        aantallen, wat er verwacht werd en of het opvallend afwijkt. Er wordt nog niets opgeslagen in de voorraad."""
        db = get_db()
        data = _data()
        if (fout := _afgebroken(db, data)) is not None:
            return fout
        bar, hok = _invoer(data.get("bar")), _invoer(data.get("hok"))
        review = optellen(_tel_producten(db), bar, hok)
        if not review:
            return _fout("Er is nog niets ingevuld.")
        bewaar_stand(db, session.get("gebruiker_id"), "hok", 0, bar, hok, review, loop_id=data.get("loop_id") or None)
        regels = controle_regels(db, review, bar, hok)
        return jsonify({"regels": [
            {"product_id": r["product"]["id"], "naam": r["product"]["naam"], "categorie": r["product"]["categorie"] or "",
             "eenheid": r["product"]["eenheid"], "voorraad": r["product"]["voorraad"], "bar": r["bar"], "hok": r["hok"],
             "totaal": r["totaal"], "verwacht": r["verwacht"], "afwijking": r["afwijking"],
             "model_afwijking": r["model_afwijking"]}
            for r in regels
        ]})

    @app.route("/api/app/tellen/bevestigen", methods=["POST"])
    def api_app_tellen_bevestigen():
        """{waarden: {product_id: totaal}, loop_id, verzoek_id}: de telling opslaan, net als 'Bevestigen' op de site.
        Is deze looplijst intussen ergens anders afgebroken of al opgeslagen, dan een 409: zo komt er geen dubbele
        telling."""
        data = _data()

        def bevestig(db):
            reden = stand_verlopen(db, session.get("gebruiker_id"), data.get("loop_id"))
            if reden:
                return {"fout": "afgebroken", "melding": reden}, 409
            waarden = {}
            for sleutel, waarde in (data.get("waarden") or {}).items():
                aantal = _getal(waarde)
                if str(sleutel).isdigit() and aantal is not None and 0 <= aantal <= MAX_AANTAL:
                    waarden[int(sleutel)] = aantal
            gebruiker_id = session.get("gebruiker_id")
            telling_id = verwerk_telling(db, waarden, session.get("gebruiker_naam"),
                                         "Via de handterminal-app geteld (bar + voorraadhok)", now_str(), gebruiker_id)
            session.pop("_flashes", None)  # meldingen van verwerk_telling zijn voor de site, niet voor de app
            if telling_id is None:
                return {"fout": "fout", "melding": "Er is nog niets ingevuld."}, 400
            wis_stand(db, gebruiker_id)
            return {"telling_id": telling_id, "aantal": len(waarden),
                    "pad": url_for("telling_detail", telling_id=telling_id),
                    "taak_vragen": taak_vragen(db, "tellen_lopen_controleren")}, 200

        return eenmalig(bevestig)

    @app.route("/api/app/tellen/stoppen", methods=["POST"])
    def api_app_tellen_stoppen():
        """{loop_id}: de looplijst afbreken, de bewaarde stand weg; er wordt niets opgeslagen. Met loop_id alleen als het
        nog die looplijst is (een late 'stoppen' gooit geen nieuwere weg)."""
        wis_stand(get_db(), session.get("gebruiker_id"), _data().get("loop_id") or None)
        return jsonify({"status": "gestopt"})

    # ---------- Prikbord ----------

    def _prikbord(db):
        mededelingen = db.execute(
            """SELECT * FROM mededelingen WHERE afgehandeld = 0
               UNION ALL SELECT * FROM (SELECT * FROM mededelingen WHERE afgehandeld = 1 ORDER BY id DESC LIMIT 10)
               ORDER BY afgehandeld ASC, urgent DESC, id DESC"""
        ).fetchall()
        reacties = {}
        for r in db.execute("SELECT mededeling_id, tekst, naam, datum FROM mededeling_opmerkingen ORDER BY id").fetchall():
            reacties.setdefault(r["mededeling_id"], []).append({"tekst": r["tekst"], "naam": r["naam"], "datum": r["datum"]})
        return {"mededelingen": [
            {"id": m["id"], "tekst": m["tekst"], "naam": m["naam"], "datum": m["datum"], "urgent": bool(m["urgent"]),
             "afgehandeld": bool(m["afgehandeld"]), "afgehandeld_door": m["afgehandeld_door"],
             "reacties": reacties.get(m["id"], [])}
            for m in mededelingen
        ]}

    @app.route("/api/app/prikbord", methods=["GET", "POST"])
    def api_app_prikbord():
        """GET: wat er openstaat (urgent eerst) en de laatste tien afgehandelde. POST {tekst, urgent, verzoek_id}: een
        nieuwe mededeling, net als op de site (Bijzonderheden)."""
        if request.method == "GET":
            return jsonify(_prikbord(get_db()))
        data = _data()

        def plaats(db):
            tekst = str(data.get("tekst") or "").strip()[:2000]
            if not tekst:
                return {"fout": "fout", "melding": "Vul een tekst in."}, 400
            naam = session.get("gebruiker_naam")
            db.execute("INSERT INTO mededelingen (tekst, naam, datum, urgent) VALUES (?, ?, ?, ?)",
                       (tekst, naam, now_str(), 1 if data.get("urgent") else 0))
            db.commit()
            stuur_tag_notificaties(db, tekst, naam, "nieuwe mededeling", url_for("bijzonderheden", _external=True))
            return _prikbord(db), 200

        return eenmalig(plaats)

    @app.route("/api/app/prikbord/<int:mededeling_id>/afhandelen", methods=["POST"])
    def api_app_prikbord_afhandelen(mededeling_id):
        db = get_db()
        db.execute(
            "UPDATE mededelingen SET afgehandeld = 1, afgehandeld_door = ?, afgehandeld_op = ? WHERE id = ? AND afgehandeld = 0",
            (session.get("gebruiker_naam"), now_str(), mededeling_id),
        )
        db.commit()
        return jsonify(_prikbord(db))

    @app.route("/api/app/prikbord/<int:mededeling_id>/reactie", methods=["POST"])
    def api_app_prikbord_reactie(mededeling_id):
        """{tekst, verzoek_id}: een reactie onder een mededeling."""
        data = _data()

        def reageer(db):
            if db.execute("SELECT 1 FROM mededelingen WHERE id = ?", (mededeling_id,)).fetchone() is None:
                return {"fout": "niet_gevonden", "melding": "Deze mededeling bestaat niet meer."}, 404
            tekst = str(data.get("tekst") or "").strip()[:2000]
            if not tekst:
                return {"fout": "fout", "melding": "Vul een tekst in."}, 400
            naam = session.get("gebruiker_naam")
            db.execute(
                "INSERT INTO mededeling_opmerkingen (mededeling_id, tekst, naam, gebruiker_id, datum) VALUES (?, ?, ?, ?, ?)",
                (mededeling_id, tekst, naam, session.get("gebruiker_id"), now_str()),
            )
            db.commit()
            stuur_tag_notificaties(db, tekst, naam, "reactie op een mededeling", url_for("bijzonderheden", _external=True))
            return _prikbord(db), 200

        return eenmalig(reageer)

    # ---------- Geschiedenis, tellingen en de bestellijst (bekijken) ----------

    @app.route("/api/app/geschiedenis")
    def api_app_geschiedenis():
        """De laatste boekingen van alle producten (of van één, met ?product_id=)."""
        db = get_db()
        product_id = request.args.get("product_id", type=int)
        rijen = db.execute(
            """SELECT m.type, m.aantal, m.datum, m.naam, m.opmerking, m.reden, p.id AS product_id, p.naam AS product,
                      p.eenheid
               FROM mutaties m JOIN producten p ON p.id = m.product_id"""
            + (" WHERE m.product_id = ?" if product_id else "") + " ORDER BY m.id DESC LIMIT 150",
            (product_id,) if product_id else (),
        ).fetchall()
        return jsonify({"mutaties": [{**dict(r), "reden": DERVING_REDENEN.get(r["reden"]) if r["reden"] else None}
                                     for r in rijen]})

    @app.route("/api/app/tellingen")
    def api_app_tellingen():
        """De laatste twintig tellingen."""
        rijen = get_db().execute(
            """SELECT t.id, t.datum, t.naam, t.opmerking,
                      (SELECT COUNT(*) FROM telling_regels WHERE telling_id = t.id) AS aantal_producten,
                      (SELECT COALESCE(SUM(verkocht * verkoopprijs), 0) FROM telling_regels WHERE telling_id = t.id) AS omzet
               FROM tellingen t ORDER BY t.id DESC LIMIT 20"""
        ).fetchall()
        return jsonify({"tellingen": [dict(r) for r in rijen]})

    @app.route("/api/app/tellingen/<int:telling_id>")
    def api_app_telling(telling_id):
        db = get_db()
        telling = db.execute("SELECT id, datum, naam, opmerking FROM tellingen WHERE id = ?", (telling_id,)).fetchone()
        if telling is None:
            return _fout("Deze telling bestaat niet (meer).", 404, "niet_gevonden")
        regels = db.execute(
            """SELECT tr.product_id, p.naam AS product, p.eenheid, tr.voorraad_voor, tr.geteld_aantal, tr.verkocht,
                      tr.correctie, tr.verkoopprijs
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""", (telling_id,),
        ).fetchall()
        return jsonify({"telling": dict(telling), "regels": [dict(r) for r in regels],
                        "omzet": round(sum(r["verkocht"] * (r["verkoopprijs"] or 0) for r in regels), 2)})

    @app.route("/api/app/bestellijst")
    def api_app_bestellijst():
        """Wat er besteld moet worden (onder het minimum en nog niet besteld), wat bezoekers via de QR-code meldden,
        en de bestellingen die onderweg zijn. Een bestelling klaarzetten blijft op de computer."""
        db = get_db()
        meldingen = bereken_bestellijst_meldingen(db)
        open_bestellingen = db.execute(
            "SELECT id, aangemaakt_op, referentie FROM bestellingen WHERE status = 'besteld' ORDER BY id DESC"
        ).fetchall()
        regels = regels_per_bestelling(db, [b["id"] for b in open_bestellingen])

        def product(p):
            factor = besteleenheid_factor(p)
            return {"id": p["id"], "naam": p["naam"], "categorie": p["categorie"] or "", "eenheid": p["eenheid"],
                    "voorraad": p["voorraad"], "min_voorraad": p["min_voorraad"] or 0,
                    "bestel_hoeveelheid": p["bestel_hoeveelheid"],
                    "besteleenheid": besteleenheid_naam(p) if factor > 1 else None, "per_besteleenheid": factor}

        return jsonify({
            "bestellen": [product(p) for p in bestel_suggesties(db)],
            "gemeld": [{**product(m["product"]), "keer": m["aantal"], "laatste_melding": m["laatste_melding"]}
                       for m in meldingen["producten"]],
            "teksten": [{"id": t["id"], "tekst": t["tekst"], "aangemaakt_op": t["aangemaakt_op"]} for t in meldingen["teksten"]],
            "onderweg": [
                {"id": b["id"], "aangemaakt_op": b["aangemaakt_op"], "referentie": b["referentie"],
                 "regels": [{"product": r["product_naam"], "aantal": naar_besteleenheden(r["aantal_besteld"], r),
                             "eenheid": besteleenheid_naam(r)} for r in regels.get(b["id"], [])]}
                for b in open_bestellingen
            ],
        })

    @app.route("/api/app/bestellijst/prognose")
    def api_app_bestellijst_prognose():
        """De prognose bij de bestellijst (zie bestel_advies): apart, want het voorspelmodel rekent soms enkele
        seconden. Per voorgesteld product de verwachte verkoop en het advies, en wat er waarschijnlijk opraakt."""
        advies = bestel_advies(get_db())
        for p in advies["extra"]:
            p["foto"] = _foto(p.pop("afbeelding"), "klein")
        advies["producten"] = {str(pid): v for pid, v in advies["producten"].items()}
        return jsonify(advies)

    @app.route("/api/app/bestellijst/gemeld/<int:product_id>/afhandelen", methods=["POST"])
    def api_app_bestellijst_melding_afhandelen(product_id):
        """De QR-meldingen van dit product afhandelen (bijvoorbeeld omdat het al besteld is)."""
        db = get_db()
        db.execute(
            """UPDATE bestellijst_meldingen SET afgehandeld = 1, afgehandeld_door = ?, afgehandeld_op = ?
               WHERE product_id = ? AND afgehandeld = 0""",
            (session.get("gebruiker_naam"), now_str(), product_id),
        )
        db.commit()
        return api_app_bestellijst()
