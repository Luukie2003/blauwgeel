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
from database import get_db
from derving import DERVING_REDENEN, kies_reden
from helpers import (
    bereken_pda_start,
    besteleenheid_factor,
    boek_mutatie,
    dagdeel_groet,
    heeft_sectie_toegang,
    now_str,
)
from productkaart import TELLEN_VOORWAARDE
from routes.tellen.looplijst import controle_regels, optellen
from routes.tellen.looplijst_opslag import bewaar_stand, bewaarde_stand, wis_stand
from routes.tellen.verwerken import verwerk_telling
from voorspelling import verwachte_verkoop_sinds_telling, verwachte_voorraad

# De nieuwste versie van de app. Draait er een oudere, dan meldt de app dat er een nieuwe is.
HANDTERMINAL_APP_VERSIE = "2.0.0"

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
        if a["ean"]:
            per_product.setdefault(a["product_id"], []).append(
                {"code": a["ean"], "niveau": "verpakking", "aantal": per_verpakking, "artikel": a["naam"]})
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
        "besteleenheid": rij["besteleenheid"] if factor > 1 and rij["besteleenheid"] else None,
        "per_besteleenheid": factor,
        "barcodes": codes.get(rij["id"], []),
    }


_PRODUCT_SELECT = """SELECT id, naam, categorie, subcategorie, merk, eenheid, voorraad, min_voorraad, actief, besteleenheid,
                            besteleenheid_factor
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


def _tel_producten(db):
    # Dezelfde volgorde als de looplijst op de site: de opgeslagen stand gaat per positie.
    return db.execute(
        f"SELECT id, naam, categorie, eenheid, voorraad FROM producten WHERE {TELLEN_VOORWAARDE} ORDER BY categorie, naam"
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


def register_routes(app):
    @app.route("/api/app/start")
    def api_app_start():
        """Alles voor het startscherm: wie je bent, wat je mag, wat aandacht nodig heeft en welke pagina's er zijn."""
        db = get_db()
        rol, secties, gebruiker_id = session.get("gebruiker_rol"), session.get("gebruiker_secties"), session.get("gebruiker_id")
        pda = bereken_pda_start(db, rol, secties, gebruiker_id)
        toegang = {s: heeft_sectie_toegang(rol, secties, s) for s in ("voorraad", "kassa", "keuken", "club_van_20")}
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
            "taken": [{"titel": t["titel"], "detail": t["detail"], "urgent": bool(t["urgent"]),
                       "pad": url_for(t["endpoint"], **t["kwargs"])} for t in pda["eigen_taken"]],
            "paginas": _webpaginas(rol, secties, pda),
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
        """Eén product met de laatste boekingen, de laatste telling en de artikelen."""
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
        """{code, product_id, per_doos (leeg: één verpakking; anders hoeveel er in de doos of krat zitten), verzoek_id}"""
        data = _data()

        def koppel(db):
            code = str(data.get("code") or "")
            _, fout = barcodes.snel_koppelen(db, code, data.get("product_id"), data.get("per_doos"),
                                             door=session.get("gebruiker_naam"), gebruiker_id=session.get("gebruiker_id"))
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
                           "verwacht": verwachte_voorraad(verwachting.get(p["id"]), p["voorraad"])}
                          for p in _tel_producten(db)],
            "stand": bewaarde_stand(db, session.get("gebruiker_id")),
        })

    @app.route("/api/app/tellen/stand", methods=["POST"])
    def api_app_tellen_stand():
        """{fase: 'bar'|'hok', index, bar: {product_id: aantal}, hok: {...}}: de stand bewaren (pauzeren, of gewoon
        tussendoor), zodat je later verder kunt, ook op een ander toestel of op de site."""
        data = _data()
        fase = "hok" if data.get("fase") == "hok" else "bar"
        bewaar_stand(get_db(), session.get("gebruiker_id"), fase, max(0, _getal(data.get("index"), 0)),
                     _invoer(data.get("bar")), _invoer(data.get("hok")))
        return jsonify({"status": "bewaard"})

    @app.route("/api/app/tellen/controleren", methods=["POST"])
    def api_app_tellen_controleren():
        """{bar, hok}: bar en voorraadhok zijn geteld. Telt ze op en geeft het controlescherm terug: per product de
        aantallen, wat er verwacht werd en of het opvallend afwijkt. Er wordt nog niets opgeslagen in de voorraad."""
        db = get_db()
        data = _data()
        bar, hok = _invoer(data.get("bar")), _invoer(data.get("hok"))
        review = optellen(_tel_producten(db), bar, hok)
        if not review:
            return _fout("Er is nog niets ingevuld.")
        bewaar_stand(db, session.get("gebruiker_id"), "hok", 0, bar, hok, review)
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
        """{waarden: {product_id: totaal}, verzoek_id}: de telling opslaan, net als 'Bevestigen' op de site."""
        data = _data()

        def bevestig(db):
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
                    "pad": url_for("telling_detail", telling_id=telling_id)}, 200

        return eenmalig(bevestig)

    @app.route("/api/app/tellen/stoppen", methods=["POST"])
    def api_app_tellen_stoppen():
        """De looplijst afbreken: de bewaarde stand weg, er wordt niets opgeslagen."""
        wis_stand(get_db(), session.get("gebruiker_id"))
        return jsonify({"status": "gestopt"})
