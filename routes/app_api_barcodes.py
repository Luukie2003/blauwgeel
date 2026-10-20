"""JSON-API voor de handterminal-app, deel 4: barcodes aanpassen en de koppelronde.

- Een artikel (wat je inkoopt, met de barcode van de verpakking en eventueel van de doos) aanpassen of verwijderen,
  met dezelfde controles als Producten > Barcodes op de site (barcodes.bewaar_artikel).
- De koppelronde: alle producten die nog geen barcode van een losse verpakking (de consumenteneenheid) hebben, één voor
  één. Je scant er één los exemplaar van (koppelen gaat via /api/app/barcodes/koppelen, zie routes/app_api.py), slaat
  het over, of zet het op "heeft geen barcode" (tapbier, een portie uit de keuken), zodat de lijst echt leeg kan.
  Dozen en kratten horen er niet bij: die komen bij het inboeken van facturen.

Zelfde afspraken als routes/app_api.py; de rechten staan in rechten.py (sectie voorraad)."""

from flask import jsonify, request, session

import barcodes
from database import get_db
from leveranciers import alle_leveranciers
from routes.app_api import _data, _foto, _fout, _product, eenmalig

# Welke producten in de koppelronde horen: wat nog verkocht wordt en niet in het archief staat.
_IN_RONDE = "p.actief = 1 AND COALESCE(p.gearchiveerd, 0) = 0"
# Heeft al een barcode van een losse verpakking.
_HEEFT_BARCODE = "EXISTS (SELECT 1 FROM artikelen a WHERE a.product_id = p.id AND a.ean IS NOT NULL)"


def _artikel_json(a):
    return {
        "id": a["id"], "naam": a["naam"], "merk": a["merk"] or None, "ean": a["ean"],
        "aantal": a["aantal_per_verpakking"], "inkoopprijs": a["inkoopprijs"] or None,
        "doos_ean": a["ean_omverpakking"], "per_doos": a["per_omverpakking"] or None,
        "leverancier_id": a["leverancier_id"], "opmerking": a["opmerking"] or None,
    }


def _koppelronde(db):
    rijen = db.execute(
        f"""SELECT p.id, p.naam, p.categorie, p.eenheid, p.afbeelding, COALESCE(p.geen_barcode, 0) AS geen_barcode,
                   {_HEEFT_BARCODE} AS gekoppeld
            FROM producten p WHERE {_IN_RONDE}
            ORDER BY p.categorie COLLATE NOCASE, p.naam COLLATE NOCASE"""
    ).fetchall()
    te_doen = [r for r in rijen if not r["gekoppeld"] and not r["geen_barcode"]]
    return {
        "te_doen": [{"id": r["id"], "naam": r["naam"], "categorie": r["categorie"] or "", "eenheid": r["eenheid"],
                     "foto_groot": _foto(r["afbeelding"], "middel")} for r in te_doen],
        "geen_barcode": [{"id": r["id"], "naam": r["naam"], "categorie": r["categorie"] or ""}
                         for r in rijen if r["geen_barcode"] and not r["gekoppeld"]],
        "gekoppeld": sum(1 for r in rijen if r["gekoppeld"]),
        "totaal": len(rijen),
    }


def register_routes(app):
    # ------------------------------------------------------------ een artikel aanpassen

    @app.route("/api/app/artikelen/<int:artikel_id>", methods=["GET", "POST"])
    def api_app_artikel(artikel_id):
        """GET: het artikel en de leveranciers. POST {naam, merk, ean, aantal_per_verpakking, inkoopprijs,
        ean_omverpakking, per_omverpakking, leverancier_id}: aanpassen; wat niet wordt meegestuurd blijft zoals het
        was, een leeg veld haalt het weg (bijvoorbeeld de barcode). Het antwoord is het product, voor de catalogus."""
        db = get_db()
        a = db.execute("SELECT * FROM artikelen WHERE id = ?", (artikel_id,)).fetchone()
        if a is None:
            return _fout("Dit artikel bestaat niet meer.", 404, "niet_gevonden")
        if request.method == "GET":
            return jsonify({"artikel": _artikel_json(a),
                            "leveranciers": [{"id": r["id"], "naam": r["naam"]}
                                             for r in alle_leveranciers(db, alleen_actief=True)]})
        data = _data()
        velden = {
            "product_id": a["product_id"], "naam": a["naam"], "merk": a["merk"] or "", "ean": a["ean"] or "",
            "aantal_per_verpakking": a["aantal_per_verpakking"], "inkoopprijs": a["inkoopprijs"] or "",
            "ean_omverpakking": a["ean_omverpakking"] or "", "per_omverpakking": a["per_omverpakking"] or "",
            "leverancier_id": a["leverancier_id"] or "", "opmerking": a["opmerking"] or "",
        }
        for sleutel in velden:
            if sleutel in data and sleutel != "product_id":
                velden[sleutel] = "" if data[sleutel] is None else str(data[sleutel]).strip()
        if not velden["ean_omverpakking"]:
            velden["per_omverpakking"] = ""  # doos weg: dan ook geen aantal in de doos
        _, fout = barcodes.bewaar_artikel(db, velden, artikel_id, door=session.get("gebruiker_naam"),
                                          gebruiker_id=session.get("gebruiker_id"))
        if fout:
            return _fout(fout)
        return jsonify({"product": _product(db, a["product_id"]), "melding": f"Artikel '{velden['naam']}' opgeslagen."})

    @app.route("/api/app/artikelen/<int:artikel_id>/verwijderen", methods=["POST"])
    def api_app_artikel_verwijderen(artikel_id):
        db = get_db()
        a = db.execute("SELECT product_id, naam FROM artikelen WHERE id = ?", (artikel_id,)).fetchone()
        if a is None:
            return _fout("Dit artikel bestaat niet meer.", 404, "niet_gevonden")
        barcodes.verwijder_artikel(db, artikel_id, session.get("gebruiker_naam"), session.get("gebruiker_id"))
        return jsonify({"product": _product(db, a["product_id"]), "melding": f"Artikel '{a['naam']}' verwijderd."})

    # ------------------------------------------------------------ de koppelronde

    @app.route("/api/app/koppelronde")
    def api_app_koppelronde():
        return jsonify(_koppelronde(get_db()))

    @app.route("/api/app/koppelronde/geen-barcode", methods=["POST"])
    def api_app_koppelronde_geen_barcode():
        """{product_id, geen (true: heeft geen barcode, false: weer in de koppelronde)}"""
        data = _data()
        db = get_db()
        product = db.execute("SELECT naam FROM producten WHERE id = ?", (data.get("product_id"),)).fetchone()
        if product is None:
            return _fout("Dit product bestaat niet meer.", 404, "niet_gevonden")
        geen = bool(data.get("geen"))
        db.execute("UPDATE producten SET geen_barcode = ? WHERE id = ?", (1 if geen else 0, data.get("product_id")))
        db.commit()
        melding = (f"{product['naam']}: heeft geen barcode." if geen
                   else f"{product['naam']} staat weer in de koppelronde.")
        return jsonify({**_koppelronde(db), "melding": melding})

    @app.route("/api/app/koppelronde/ongedaan", methods=["POST"])
    def api_app_koppelronde_ongedaan():
        """{code, verzoek_id}: de net gekoppelde barcode weer los. Was het artikel alleen voor die barcode gemaakt
        (verder niets ingevuld), dan gaat het hele artikel weg."""
        data = _data()

        def actie(db):
            code, _ = barcodes.controleer(str(data.get("code") or ""))
            a = db.execute("SELECT * FROM artikelen WHERE ean = ?", (code,)).fetchone() if code else None
            if a is None:
                return {"fout": "niet_gevonden", "melding": "Deze barcode is al niet meer gekoppeld."}, 404
            product = db.execute("SELECT naam FROM producten WHERE id = ?", (a["product_id"],)).fetchone()
            leeg = (not a["ean_omverpakking"] and not a["inkoopprijs"] and not a["merk"] and not a["leverancier_id"]
                    and not a["opmerking"])
            if leeg:
                barcodes.verwijder_artikel(db, a["id"], session.get("gebruiker_naam"), session.get("gebruiker_id"))
            else:
                db.execute("UPDATE artikelen SET ean = NULL WHERE id = ?", (a["id"],))
            return {**_koppelronde(db), "product": _product(db, a["product_id"]),
                    "melding": f"Barcode {code} is weer los van {product['naam']}."}, 200

        return eenmalig(actie)
