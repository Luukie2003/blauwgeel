"""JSON-API voor de handterminal-app, deel 2: alles naast het dagelijkse voorraadwerk.

Met deze schermen heeft de app geen website meer nodig: de uitgebreide productinformatie, kassa en kluis tellen en
goedkeuren, de keuken (tellen, inboeken, frituurvet), boodschappen, de Club van 20-aanmeldingen, de agenda, de prognose,
het barcode-overzicht, de taken die een beheerder voor iemand klaarzet en een nieuw product aanmaken (bij een barcode
die bij nog geen enkel product hoort). Zelfde afspraken als routes/app_api.py:
inloggen met de code, het csrf_token in de header, een verzoek_id voor schrijfacties (zie eenmalig) en JSON in plaats
van een doorverwijzing als iets niet mag. De logica is die van de site (dezelfde functies), de rechten staan in
rechten.py.

Wat alleen op de site kan (corrigeren, bewerken, heropenen, een bestelling klaarzetten, de kantine-tv, prijzen
beheren), staat hier bewust niet in: de app zegt dan dat het niet in de app kan."""

from datetime import date, datetime

from flask import jsonify, request, session

import barcodes
import kiosk_timers
import productinfo
from activiteiten import bouw_agenda, kies_dagen
from aanmeldingen import aanmelden_status, bestaand_lid_voor, keur_goed, ruim_op, splits_naam, wijs_af
from club_van_20 import BETAALWIJZEN
from database import get_db
from eigen_taken import rond_af, taak_voor_persoon, vind_taak, vink_stap
from helpers import (
    bereken_frituurvet_status,
    bereken_kassalade_stand,
    bereken_kluis_stand,
    besteleenheid_naam,
    naar_besteleenheden,
    now_str,
)
from helpers.kas import KASSA_COUPURES
from helpers.tijd import vandaag_amsterdam
from keukenbeheer import boek_keuken_in, keuken_producten, keuken_tellingen, verwerk_keuken_telling
from leveranciers import alle_leveranciers
from productkaart import BESTELEENHEDEN, EENHEDEN
from routes.app_api import _data, _foto, _fout, _getal, _product, eenmalig, taak_vragen
from routes.kassa import keur_kassa_telling_goed, maak_kassa_telling
from routes.kluis import keur_kluis_telling_goed, maak_kluis_telling
from routes.logboek import schrijf_logboek

RECENTE_GELDTELLINGEN = 6
MAX_STUKS = 100000


def _kommagetal(waarde):
    """'12,50' of 12.5 -> 12.5 (None als het geen getal is)."""
    try:
        return round(float(str(waarde).strip().replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- productinformatie


def _info_json(db, product, beheerder):
    """Alles van de productpagina van de site wat zonder het voorspelmodel kan (zie productinfo.productinfo). De marge
    alleen voor een beheerder, net als op de site."""
    info = productinfo.productinfo(db, product)
    factor = info["factor"]
    lev = info["leverancier"]
    marge = None
    if beheerder:
        if info["marge"]:
            m = info["marge"]
            marge = {"pct": m["pct"], "stuk": m["stuk"], "doel": m["doel"], "onder_doel": m["onder_doel"]}
        else:
            marge = {"reden": "nog geen inkoopprijs" if not info["inkoop_stuk"] else "nog geen verkoopprijs"}
    levering = info["laatste_levering"]
    derving = info["derving"]
    return {
        "artikelcode": product["artikelcode"] or None,
        "opmerking": product["opmerking"] or None,
        "gearchiveerd": bool(product["gearchiveerd"]),
        "op_prijzenscherm": bool(product["toon_op_kiosk"]),
        "uitverkocht_op_scherm": bool(product["kiosk_uitverkocht"]),
        "niet_tellen": bool(product["niet_tellen"]),
        "factor": factor,
        "besteleenheid_naam": besteleenheid_naam(product),
        "in_besteleenheden": info["in_besteleenheden"],
        "verkoopprijs": product["verkoopprijs"] or None,
        "glazen_per_fust": product["glazen_per_fust"] or None,
        "prijs_per_glas": product["prijs_per_glas"] if product["glazen_per_fust"] else None,
        "verkoop_stuk": info["verkoop_stuk"],
        "inkoop_stuk": info["inkoop_stuk"] or None,
        "inkoop_besteleenheid": product["inkoopprijs"] if factor > 1 and product["inkoopprijs"] else None,
        "voorraadwaarde": info["voorraadwaarde"] if info["inkoop_stuk"] else None,
        "marge": marge,
        "prijsopties": [
            {"naam": o["naam"], "prijs": o["prijs"], "glazen": o["glazen"] if "glazen" in o.keys() else None}
            for o in info["prijsopties"]
        ],
        "gepland": [
            {"datum": g["ingangsdatum"], "prijs": g["nieuwe_prijs"], "opmerking": g["opmerking"] or None,
             "wat": g["optie_naam"] or ("prijs per glas" if g["soort"] == "prijs_per_glas" else "verkoopprijs")}
            for g in info["gepland"]
        ],
        "prijs_geschiedenis": [
            {"datum": w["datum"], "wat": "inkoop" if w["veld"] == "inkoopprijs" else "verkoop",
             "oud": w["oude_prijs"], "nieuw": w["nieuwe_prijs"], "naam": w["naam"]}
            for w in info["prijs_geschiedenis"]
        ],
        "leverancier": lev["naam"] if lev else None,
        "besteldagen": info["besteldagen"] or None,
        "bestel_hoeveelheid": product["bestel_hoeveelheid"] or None,
        "laatste_levering": {"datum": levering["datum"], "aantal": levering["aantal"], "naam": levering["naam"],
                             "leeftijd": productinfo.leeftijd(levering["datum"])} if levering else None,
        "onderweg": [
            {"id": b["id"], "datum": b["aangemaakt_op"], "referentie": b["referentie"] or None,
             "aantal": b["aantal_besteld"], "in_besteleenheden": naar_besteleenheden(b["aantal_besteld"], product)}
            for b in info["open_bestellingen"]
        ],
        "meldingen": info["meldingen"],
        "artikelen": [
            {"id": a["id"], "naam": a["naam"], "merk": a["merk"] or None, "ean": a["ean"], "doos_ean": a["ean_omverpakking"],
             "per_doos": a["per_omverpakking"] or None, "aantal": a["aantal_per_verpakking"],
             "inkoopprijs": a["inkoopprijs"] or None, "per_eenheid": barcodes.per_eenheid(a) or None,
             "leverancier": a["leverancier_naam"]}
            for a in info["artikelen"]
        ],
        "tellingen": [
            {"id": t["id"], "datum": t["datum"], "naam": t["naam"], "voor": t["voorraad_voor"], "geteld": t["geteld_aantal"],
             "verkocht": t["verkocht"], "omzet": t["verkocht"] * (t["verkoopprijs"] or 0)}
            for t in info["tellingen"]
        ],
        "laatst_geteld": productinfo.leeftijd(info["laatste_telling"]["datum"]) if info["laatste_telling"] else None,
        "derving": {"aantal": derving["aantal"], "keer": derving["keer"], "dagen": info["derving_dagen"],
                    "waarde": derving["aantal"] * info["inkoop_stuk"] if info["inkoop_stuk"] else None},
    }


def productinfo_json(db, product_id):
    """Het blok "info" bij api_app_product (zie routes/app_api.py), of None."""
    product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        return None
    return _info_json(db, product, session.get("gebruiker_rol") == "beheerder")


def _verkoop_json(verkoop):
    if not verkoop:
        return {"beschikbaar": False}
    v = verkoop["verwachting"]
    verwachting = None
    if v:
        verwachting = {k: v[k] for k in (
            "verwacht", "laag", "hoog", "status", "nu_op", "dekking_dagen", "kans_tekort", "onderweg", "advies_stuks",
            "advies_eenheden", "besteleenheid", "al_op_bestellijst", "weinig_data",
        )}
    return {
        "beschikbaar": True,
        "weken": [{"week": w["week"], "maandag": w["maandag"].isoformat(), "aantal": w["aantal"], "omzet": w["omzet"],
                   "nog_niet_af": w["nog_niet_af"], "lopend": w["lopend"]} for w in verkoop["weken"]],
        "hoogste": verkoop["hoogste"],
        "per_week": verkoop["per_week"],
        "weken_gemiddeld": verkoop["weken_gemiddeld"],
        "omzet_recent": verkoop["omzet_recent"],
        "zonder_verkoop": verkoop["zonder_verkoop"],
        "geteld_tot": verkoop["geteld_tot"].strftime("%Y-%m-%d %H:%M"),
        "verwachting": verwachting,
        "prognose_dagen": verkoop["prognose_dagen"],
    }


# ---------------------------------------------------------------- kassa en kluis


def _geld_telling_json(t, met_omzet):
    uit = {
        "id": t["id"],
        "datum": t["datum"],
        "naam": t["naam"],
        "verwacht": t["verwacht_bedrag"],
        "geteld": t["geteld_bedrag"],
        "verschil": t["verschil"],
        "opmerking": t["opmerking"] or None,
        "afgesloten": bool(t["afgesloten"]),
        "goedgekeurd_door": t["goedgekeurd_door"],
        "goedgekeurd_op": t["goedgekeurd_op"],
        "van_mij": t["gebruiker_id"] is not None and t["gebruiker_id"] == session.get("gebruiker_id"),
        "aantallen": {kolom: t[kolom] for kolom, _, _ in KASSA_COUPURES},
    }
    if met_omzet:
        uit["contante_omzet"] = t["contante_omzet"]
        uit["kaart_omzet"] = t["kaart_omzet"] or 0
    return uit


def _geld_overzicht(db, tabel, stand, met_omzet):
    concepten = db.execute(f"SELECT * FROM {tabel} WHERE afgesloten = 0 ORDER BY datum DESC, id DESC").fetchall()
    recent = db.execute(
        f"SELECT * FROM {tabel} WHERE afgesloten = 1 ORDER BY datum DESC, id DESC LIMIT ?", (RECENTE_GELDTELLINGEN,)
    ).fetchall()
    return {
        "stand": stand["stand"],
        "coupures": [{"veld": kolom, "waarde": waarde, "naam": naam} for kolom, waarde, naam in KASSA_COUPURES],
        "concepten": [_geld_telling_json(t, met_omzet) for t in concepten],
        "recent": [_geld_telling_json(t, met_omzet) for t in recent],
    }


def _geld_formulier(data, met_omzet):
    """De aantallen per coupure (en bij de kassa de omzet) als het formulier van de site."""
    aantallen = data.get("aantallen") if isinstance(data.get("aantallen"), dict) else {}
    form = {kolom: str(max(0, min(MAX_STUKS, _getal(aantallen.get(kolom), 0) or 0))) for kolom, _, _ in KASSA_COUPURES}
    form["opmerking"] = str(data.get("opmerking") or "")[:500]
    if met_omzet:
        form["contante_omzet"] = str(_kommagetal(data.get("contante_omzet") or 0) or 0)
        form["kaart_omzet"] = str(_kommagetal(data.get("kaart_omzet") or 0) or 0)
    return form


def _euro(bedrag):
    return f"€ {bedrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _verschil_tekst(verschil):
    if abs(verschil) < 0.005:
        return "Het klopt precies."
    return f"{_euro(abs(verschil))} {'te veel' if verschil > 0 else 'te weinig'}."


# ---------------------------------------------------------------- een nieuw product


def _categorieen(db):
    return [r["naam"] for r in db.execute("SELECT naam FROM categorieen ORDER BY naam COLLATE NOCASE").fetchall()]


def maak_product(db, data, door=None):
    """Een nieuw product vanaf de handterminal, zoals Snel toevoegen op de site: naam, categorie, eenheid en eventueel de
    besteleenheid (een krat van 24) en de verkoopprijs. Voorraad en minimum beginnen op 0; foto, leverancier en het
    prijzenscherm vul je later op de computer aan. Geeft (product_id, foutmelding)."""
    naam = " ".join(str(data.get("naam") or "").split())
    if not naam:
        return None, "Vul de naam van het product in."
    if len(naam) > 80:
        return None, "Die naam is te lang; houd het kort, bijvoorbeeld 'Hertog Jan 0.0 Fles'."
    if db.execute(
        "SELECT 1 FROM producten WHERE naam = ? COLLATE NOCASE AND COALESCE(gearchiveerd, 0) = 0", (naam,)
    ).fetchone():
        return None, f"Er is al een product '{naam}'. Kies dat in de lijst."
    categorie = str(data.get("categorie") or "").strip()
    if categorie not in _categorieen(db):
        categorie = "Overig"
    eenheid = str(data.get("eenheid") or "").strip()
    if eenheid not in EENHEDEN:
        return None, "Kies de eenheid waarin je het product telt (bijvoorbeeld Fles of Zakje)."
    besteleenheid = str(data.get("besteleenheid") or "").strip() or None
    factor = _getal(data.get("per_besteleenheid"), 1)
    if besteleenheid is not None and (besteleenheid not in BESTELEENHEDEN or factor < 2):
        return None, "Vul in hoeveel er in de besteleenheid zitten (2 of meer), of laat de besteleenheid leeg."
    if besteleenheid is None:
        factor = 1
    prijs = _kommagetal(data.get("verkoopprijs")) if str(data.get("verkoopprijs") or "").strip() else 0.0
    if prijs is None or prijs < 0:
        return None, "Vul een geldige verkoopprijs in (bijvoorbeeld 2,50), of laat hem leeg."
    product_id = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, bestel_hoeveelheid, verkoopprijs,
               actief, besteleenheid, besteleenheid_factor, opmerking)
           VALUES (?, ?, ?, 0, 0, 0, ?, 1, ?, ?, '')""",
        (naam, categorie, eenheid, prijs, besteleenheid, factor),
    ).lastrowid
    schrijf_logboek(db, "product_nieuw", f"Product '{naam}' aangemaakt op de handterminal{' door ' + door if door else ''}.")
    return product_id, None


def register_routes(app):
    # ------------------------------------------------------------ product

    @app.route("/api/app/producten/nieuw", methods=["GET", "POST"])
    def api_app_product_nieuw():
        """GET: de keuzes (categorieën, eenheden, besteleenheden). POST {naam, categorie, eenheid, besteleenheid,
        per_besteleenheid, verkoopprijs, verzoek_id}: het product aanmaken (zie maak_product); het antwoord is het
        product zoals in de productlijst, zodat de app er meteen een barcode aan kan koppelen."""
        if request.method == "GET":
            return jsonify({"categorieen": _categorieen(get_db()), "eenheden": EENHEDEN, "besteleenheden": BESTELEENHEDEN})
        data = _data()

        def maak(db):
            product_id, fout = maak_product(db, data, session.get("gebruiker_naam"))
            if fout:
                return {"fout": "fout", "melding": fout}, 400
            return {"product": _product(db, product_id), "melding": f"{data.get('naam', '').strip()} is aangemaakt."}, 200

        return eenmalig(maak)

    @app.route("/api/app/producten/<int:product_id>/artikelen", methods=["GET", "POST"])
    def api_app_artikel_nieuw(product_id):
        """GET: de leveranciers om uit te kiezen. POST {naam, merk, ean, aantal_per_verpakking, inkoopprijs,
        ean_omverpakking, per_omverpakking, leverancier_id, verzoek_id}: een nieuw artikel bij dit product, met dezelfde
        controles als Producten > Barcodes op de site (barcodes.bewaar_artikel). Het antwoord is het product met zijn
        barcodes, voor de productlijst op de handterminal."""
        db = get_db()
        if db.execute("SELECT 1 FROM producten WHERE id = ?", (product_id,)).fetchone() is None:
            return _fout("Dit product bestaat niet meer.", 404, "niet_gevonden")
        if request.method == "GET":
            return jsonify({"leveranciers": [{"id": r["id"], "naam": r["naam"]}
                                             for r in alle_leveranciers(db, alleen_actief=True)]})
        data = _data()

        def maak(db):
            velden = {sleutel: str(data.get(sleutel) or "").strip() for sleutel in (
                "naam", "merk", "ean", "aantal_per_verpakking", "inkoopprijs", "ean_omverpakking", "per_omverpakking",
                "leverancier_id")}
            velden["product_id"] = str(product_id)
            _, fout = barcodes.bewaar_artikel(db, velden, door=session.get("gebruiker_naam"),
                                              gebruiker_id=session.get("gebruiker_id"))
            if fout:
                return {"fout": "fout", "melding": fout}, 400
            return {"product": _product(db, product_id), "melding": f"Artikel '{velden['naam']}' toegevoegd."}, 200

        return eenmalig(maak)

    @app.route("/api/app/producten/<int:product_id>/verkoop")
    def api_app_product_verkoop(product_id):
        """Verkoop per week en de verwachting (het voorspelmodel): apart, want dat rekent op de server soms enkele
        seconden. Mislukt het, dan is er gewoon geen verkoopblok."""
        db = get_db()
        if db.execute("SELECT 1 FROM producten WHERE id = ?", (product_id,)).fetchone() is None:
            return _fout("Dit product bestaat niet meer.", 404, "niet_gevonden")
        try:
            verkoop = productinfo.verkoopinfo(db, product_id)
        except Exception as fout:  # het blok mag het productscherm nooit stuk maken
            print(f"[app] verkoop van {product_id} mislukt: {fout}")
            verkoop = None
        return jsonify(_verkoop_json(verkoop))

    @app.route("/api/app/producten/<int:product_id>/melden", methods=["POST"])
    def api_app_product_melden(product_id):
        """"Op de bestellijst", net als op de productpagina van de site."""

        def actie(db):
            product = db.execute("SELECT id, naam FROM producten WHERE id = ?", (product_id,)).fetchone()
            if product is None:
                return {"fout": "niet_gevonden", "melding": "Dit product bestaat niet meer."}, 404
            db.execute(
                "INSERT INTO bestellijst_meldingen (product_id, tekst, bron, aangemaakt_op) VALUES (?, ?, 'app', ?)",
                (product_id, f"Gemeld door {session.get('gebruiker_naam') or 'onbekend'}", now_str()),
            )
            meldingen = db.execute(
                "SELECT COUNT(*) FROM bestellijst_meldingen WHERE product_id = ? AND afgehandeld = 0", (product_id,)
            ).fetchone()[0]
            return {"melding": f"{product['naam']} staat op de bestellijst.", "meldingen": meldingen}, 200

        return eenmalig(actie)

    # ------------------------------------------------------------ kassa

    @app.route("/api/app/kassa")
    def api_app_kassa():
        db = get_db()
        return jsonify(_geld_overzicht(db, "kassa_tellingen", bereken_kassalade_stand(db), met_omzet=True))

    @app.route("/api/app/kassa/tellen", methods=["POST"])
    def api_app_kassa_tellen():
        """Een kassatelling als concept, precies als Kassa > Tellen op de site."""
        form = _geld_formulier(_data(), met_omzet=True)

        def actie(db):
            telling_id = maak_kassa_telling(db, form, session.get("gebruiker_naam"), session.get("gebruiker_id"))
            telling = db.execute("SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)).fetchone()
            return {
                "telling": _geld_telling_json(telling, True),
                "melding": f"Kassatelling opgeslagen als concept. {_verschil_tekst(telling['verschil'])}",
                "taak_vragen": taak_vragen(db, "kassa_tellen"),
            }, 200

        return eenmalig(actie)

    @app.route("/api/app/kassa/<int:telling_id>/goedkeuren", methods=["POST"])
    def api_app_kassa_goedkeuren(telling_id):
        opmerking = str(_data().get("opmerking") or "")[:500]

        def actie(db):
            fout = keur_kassa_telling_goed(db, telling_id, session.get("gebruiker_naam"), session.get("gebruiker_id"), opmerking)
            if fout:
                return {"fout": "niet_mogelijk", "melding": fout}, 409
            return {"melding": "Kassatelling goedgekeurd.", "stand": bereken_kassalade_stand(db)["stand"]}, 200

        return eenmalig(actie)

    # ------------------------------------------------------------ kluis (alleen beheerders, zie rechten.py)

    @app.route("/api/app/kluis")
    def api_app_kluis():
        db = get_db()
        return jsonify(_geld_overzicht(db, "kluis_tellingen", bereken_kluis_stand(db), met_omzet=False))

    @app.route("/api/app/kluis/tellen", methods=["POST"])
    def api_app_kluis_tellen():
        form = _geld_formulier(_data(), met_omzet=False)

        def actie(db):
            telling_id = maak_kluis_telling(db, form, session.get("gebruiker_naam"), session.get("gebruiker_id"))
            telling = db.execute("SELECT * FROM kluis_tellingen WHERE id = ?", (telling_id,)).fetchone()
            return {
                "telling": _geld_telling_json(telling, False),
                "melding": f"Kluistelling opgeslagen als concept. {_verschil_tekst(telling['verschil'])}",
                "taak_vragen": taak_vragen(db, "kluis_tellen"),
            }, 200

        return eenmalig(actie)

    @app.route("/api/app/kluis/<int:telling_id>/goedkeuren", methods=["POST"])
    def api_app_kluis_goedkeuren(telling_id):
        opmerking = str(_data().get("opmerking") or "")[:500]

        def actie(db):
            fout = keur_kluis_telling_goed(db, telling_id, session.get("gebruiker_naam"), session.get("gebruiker_id"), opmerking)
            if fout:
                return {"fout": "niet_mogelijk", "melding": fout}, 409
            return {"melding": "Kluistelling goedgekeurd.", "stand": bereken_kluis_stand(db)["stand"]}, 200

        return eenmalig(actie)

    # ------------------------------------------------------------ keuken

    def _frituurvet(db):
        f = bereken_frituurvet_status(db)
        laatste = f["laatste"]
        return {"datum": laatste["datum"] if laatste else None, "naam": laatste["naam"] if laatste else None,
                "dagen_geleden": f["dagen_geleden"], "interval": f["interval"], "ok": f["ok"]}

    @app.route("/api/app/keuken")
    def api_app_keuken():
        db = get_db()
        producten = [
            {"id": p["id"], "naam": p["naam"], "subcategorie": p["subcategorie"] or "", "eenheid": p["eenheid"] or "stuks",
             "voorraad": p["voorraad"], "min_voorraad": p["min_voorraad"] or 0,
             "verpakking": (p["besteleenheid"] or p["eenheid"] or "verpakking").lower(),
             "per_verpakking": max(1, p["besteleenheid_factor"] or 1), "foto": _foto(p["afbeelding"], "klein")}
            for p in keuken_producten(db)
        ]
        tellingen = [
            {"id": t["id"], "datum": t["datum"], "naam": t["naam"], "omzet": t["omzet"], "producten": t["aantal_producten"]}
            for t in keuken_tellingen(db, limiet=5)
        ]
        eerste = db.execute("SELECT 1 FROM keuken_tellingen LIMIT 1").fetchone() is None
        return jsonify({"producten": producten, "frituurvet": _frituurvet(db), "tellingen": tellingen,
                        "eerste_telling": eerste})

    def _aantallen(waarden):
        if not isinstance(waarden, dict):
            return {}
        uit = {}
        for sleutel, waarde in waarden.items():
            pid, n = _getal(sleutel), _getal(waarde)
            if pid is not None and n is not None and 0 <= n <= MAX_STUKS:
                uit[pid] = n
        return uit

    @app.route("/api/app/keuken/tellen", methods=["POST"])
    def api_app_keuken_tellen():
        """Keukentelling: wat er minder is dan de voorraad, is verkocht (zie verwerk_keuken_telling). Met
        "begintelling": true zet hij alleen de voorraad goed."""
        data = _data()
        waarden = _aantallen(data.get("waarden"))
        opmerking = str(data.get("opmerking") or "").strip()[:500]
        begintelling = data.get("begintelling") is True

        def actie(db):
            telling_id = verwerk_keuken_telling(
                db, waarden, session.get("gebruiker_naam"), now_str(), session.get("gebruiker_id"), opmerking,
                begintelling=begintelling,
            )
            if telling_id is None:
                return {"fout": "leeg", "melding": "Geen aantallen ingevuld: er is niets geteld."}, 400
            soort = "Begintelling" if begintelling else "Keukentelling"
            return {"telling_id": telling_id,
                    "melding": f"{soort} opgeslagen ({len(waarden)} {'product' if len(waarden) == 1 else 'producten'})."}, 200

        return eenmalig(actie)

    @app.route("/api/app/keuken/inboeken", methods=["POST"])
    def api_app_keuken_inboeken():
        """Keuken inboeken per verpakking (een doos frikandellen van 40: 1), zoals Keuken > Inboeken op de site, en/of
        "gescand": {product_id: stuks} uit gescande barcodes (wat er in een doos zit, verschilt per supermarkt)."""
        data = _data()
        verpakkingen = {pid: n for pid, n in _aantallen(data.get("verpakkingen")).items() if n > 0}
        gescand = {pid: n for pid, n in _aantallen(data.get("gescand")).items() if n > 0}

        def actie(db):
            aantal = boek_keuken_in(db, verpakkingen, session.get("gebruiker_naam"), now_str(), session.get("gebruiker_id"),
                                    gescand=gescand)
            if not aantal:
                return {"fout": "leeg", "melding": "Niets ingevuld om in te boeken."}, 400
            return {"melding": f"{aantal} {'product' if aantal == 1 else 'producten'} ingeboekt."}, 200

        return eenmalig(actie)

    @app.route("/api/app/frituurvet", methods=["POST"])
    def api_app_frituurvet():
        def actie(db):
            db.execute(
                "INSERT INTO frituurvet_vervangingen (datum, naam, gebruiker_id) VALUES (?, ?, ?)",
                (now_str(), session.get("gebruiker_naam"), session.get("gebruiker_id")),
            )
            return {"melding": "Frituurvet-vervanging geregistreerd.", "frituurvet": _frituurvet(db),
                    "taak_vragen": taak_vragen(db, "frituurvet_vervangen")}, 200

        return eenmalig(actie)

    # ------------------------------------------------------------ prijzenscherm: uitverkocht

    def _prijzenscherm(db):
        """De producten op het prijzenscherm (zie routes/kiosk/prijzen_gegevens.py), per groep zoals op de tv."""
        rijen = db.execute(
            """SELECT id, naam, categorie, kiosk_categorie, kiosk_uitverkocht, afbeelding FROM producten
               WHERE actief = 1 AND toon_op_kiosk = 1 ORDER BY naam COLLATE NOCASE"""
        ).fetchall()
        groepen = {}
        for r in rijen:
            groepen.setdefault(r["kiosk_categorie"] or r["categorie"] or "Overig", []).append(
                {"id": r["id"], "naam": r["naam"], "uitverkocht": bool(r["kiosk_uitverkocht"]),
                 "foto": _foto(r["afbeelding"], "klein")}
            )
        return {
            "groepen": [{"naam": naam, "producten": producten} for naam, producten in sorted(groepen.items())],
            "uitverkocht": sum(1 for r in rijen if r["kiosk_uitverkocht"]),
        }

    @app.route("/api/app/prijzenscherm")
    def api_app_prijzenscherm():
        return jsonify(_prijzenscherm(get_db()))

    @app.route("/api/app/producten/<int:product_id>/uitverkocht", methods=["POST"])
    def api_app_product_uitverkocht(product_id):
        """{uitverkocht: true/false}: zo staat hij op het prijzenscherm (doorgestreept, met de melding 'Uitverkocht' op
        de tv). Raakt de voorraad niet, net als de knop op de site (kiosk_product_uitverkocht_wisselen)."""
        db = get_db()
        product = db.execute("SELECT naam, toon_op_kiosk FROM producten WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return _fout("Dit product bestaat niet meer.", 404, "niet_gevonden")
        uitverkocht = bool(_data().get("uitverkocht"))
        db.execute("UPDATE producten SET kiosk_uitverkocht = ? WHERE id = ?", (1 if uitverkocht else 0, product_id))
        db.commit()
        if not product["toon_op_kiosk"]:
            melding = f"{product['naam']} staat niet op het prijzenscherm."
        elif uitverkocht:
            melding = f"{product['naam']} staat nu als uitverkocht op de tv."
        else:
            melding = f"{product['naam']} is weer te koop op de tv."
        return jsonify({**_prijzenscherm(db), "melding": melding, "uitverkocht_op_scherm": uitverkocht})

    # ------------------------------------------------------------ timer op de tv's

    def _timers(db):
        return {"timers": kiosk_timers.actieve(db), "voorstellen": kiosk_timers.voorstellen(db),
                "max_minuten": kiosk_timers.MAX_MINUTEN}

    @app.route("/api/app/timers", methods=["GET", "POST"])
    def api_app_timers():
        """De timers op de tv's (zie kiosk_timers.py); POST {naam, minuten, verzoek_id} start er een."""
        if request.method == "GET":
            return jsonify(_timers(get_db()))
        data = _data()

        def actie(db):
            timer_id, fout = kiosk_timers.start(db, data.get("naam"), data.get("minuten"), session.get("gebruiker_naam"))
            if fout:
                return {"fout": "fout", "melding": fout}, 400
            t = db.execute("SELECT naam, minuten, klaar_om FROM kiosk_timers WHERE id = ?", (timer_id,)).fetchone()
            return {**_timers(db), "melding": f"{t['naam']}: klaar om {t['klaar_om'][11:16]}. Staat op de tv's."}, 200

        return eenmalig(actie)

    @app.route("/api/app/timers/<int:timer_id>/verlengen", methods=["POST"])
    def api_app_timer_verlengen(timer_id):
        """{minuten (standaard 5), verzoek_id}"""
        minuten = kiosk_timers.schoon_minuten(_data().get("minuten")) or 5

        def actie(db):
            naam = kiosk_timers.verleng(db, timer_id, minuten)
            if naam is None:
                return {"fout": "niet_gevonden", "melding": "Deze timer staat er niet meer."}, 404
            return {**_timers(db), "melding": f"{naam}: {minuten} minuten erbij."}, 200

        return eenmalig(actie)

    @app.route("/api/app/timers/<int:timer_id>/stoppen", methods=["POST"])
    def api_app_timer_stoppen(timer_id):
        db = get_db()
        naam = kiosk_timers.stop(db, timer_id)
        melding = f"{naam}: van de tv's gehaald." if naam else "Deze timer stond er al niet meer."
        return jsonify({**_timers(db), "melding": melding})

    # ------------------------------------------------------------ boodschappen

    def _boodschappen(db):
        def rij(b):
            return {"id": b["id"], "tekst": b["tekst"], "door": b["aangemaakt_door"], "op": b["aangemaakt_op"],
                    "afgevinkt_door": b["afgevinkt_door"], "afgevinkt_op": b["afgevinkt_op"]}

        return {
            "open": [rij(b) for b in db.execute("SELECT * FROM boodschappen WHERE afgevinkt = 0 ORDER BY id").fetchall()],
            "afgevinkt": [rij(b) for b in db.execute(
                "SELECT * FROM boodschappen WHERE afgevinkt = 1 ORDER BY afgevinkt_op DESC LIMIT 30").fetchall()],
        }

    @app.route("/api/app/boodschappen", methods=["GET", "POST"])
    def api_app_boodschappen():
        if request.method == "GET":
            return jsonify(_boodschappen(get_db()))
        tekst = str(_data().get("tekst") or "").strip()[:200]
        if not tekst:
            return _fout("Vul in wat je nodig hebt.")

        def actie(db):
            db.execute(
                "INSERT INTO boodschappen (tekst, aangemaakt_door, aangemaakt_op) VALUES (?, ?, ?)",
                (tekst, session.get("gebruiker_naam"), now_str()),
            )
            return {**_boodschappen(db), "melding": f"{tekst} staat op de boodschappenlijst."}, 200

        return eenmalig(actie)

    @app.route("/api/app/boodschappen/<int:item_id>/afvinken", methods=["POST"])
    def api_app_boodschap_afvinken(item_id):
        """Afvinken, of (als hij al was afgevinkt) weer terugzetten. Met "af": true/false wordt het precies dat."""
        db = get_db()
        item = db.execute("SELECT * FROM boodschappen WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            return _fout("Dit staat niet meer op de lijst.", 404, "niet_gevonden")
        gewenst = _data().get("af")
        af = bool(gewenst) if isinstance(gewenst, bool) else not item["afgevinkt"]
        db.execute(
            "UPDATE boodschappen SET afgevinkt = ?, afgevinkt_door = ?, afgevinkt_op = ? WHERE id = ?",
            (1 if af else 0, session.get("gebruiker_naam") if af else None, now_str() if af else None, item_id),
        )
        db.commit()
        return jsonify(_boodschappen(db))

    @app.route("/api/app/boodschappen/<int:item_id>/verwijderen", methods=["POST"])
    def api_app_boodschap_verwijderen(item_id):
        db = get_db()
        db.execute("DELETE FROM boodschappen WHERE id = ?", (item_id,))
        db.commit()
        return jsonify(_boodschappen(db))

    # ------------------------------------------------------------ Club van 20-aanmeldingen

    def _club_instellingen(db):
        return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()

    @app.route("/api/app/aanmeldingen")
    def api_app_aanmeldingen():
        db = get_db()
        ruim_op(db)
        openstaand = []
        for r in db.execute("SELECT * FROM club_van_20_aanmeldingen WHERE status = 'nieuw' ORDER BY aangemaakt_op, id").fetchall():
            lid = bestaand_lid_voor(db, r)
            openstaand.append({
                "id": r["id"], "bordje": r["bordje"], "naam": r["naam"], "betaalwijze": r["betaalwijze"],
                "bedrag": r["bedrag"], "bardienst": r["bardienst"] or None, "op": r["aangemaakt_op"],
                "verlenging": bool(r["verlengt_lid_id"]),
                "lid": {"id": lid["id"], "naam": lid["naam"]} if lid else None,
                "bordje_anders": bool(lid and lid["naam"].lower() != r["bordje"].lower()),
            })
        behandeld = [
            {"bordje": r["bordje"], "naam": r["naam"], "status": r["status"], "op": r["behandeld_op"], "door": r["behandeld_door"]}
            for r in db.execute(
                "SELECT * FROM club_van_20_aanmeldingen WHERE status != 'nieuw' ORDER BY behandeld_op DESC, id DESC LIMIT 10"
            ).fetchall()
        ]
        status = aanmelden_status(_club_instellingen(db))
        return jsonify({"openstaand": openstaand, "behandeld": behandeld,
                        "status": {"aan": status["aan"], "open": status["open"], "opent": status["opent_label"]}})

    def _openstaande_aanmelding(db, aanmelding_id):
        rij = db.execute("SELECT * FROM club_van_20_aanmeldingen WHERE id = ?", (aanmelding_id,)).fetchone()
        return rij if rij is not None and rij["status"] == "nieuw" else None

    @app.route("/api/app/aanmeldingen/<int:aanmelding_id>/goedkeuren", methods=["POST"])
    def api_app_aanmelding_goedkeuren(aanmelding_id):
        """Goedkeuren zoals op de handterminal-pagina van de site: het lid (nieuw of verlengd) met de gegevens uit de
        aanmelding; ontbrekende gegevens vul je later op de computer aan."""
        data = _data()
        if data.get("betaling_gecontroleerd") is not True:
            return _fout("Vink aan dat je de betaling hebt gecontroleerd.")

        def actie(db):
            aanmelding = _openstaande_aanmelding(db, aanmelding_id)
            if aanmelding is None:
                return {"fout": "niet_gevonden", "melding": "Deze aanmelding is al behandeld of bestaat niet meer."}, 409
            lid = bestaand_lid_voor(db, aanmelding)
            voornaam, achternaam = splits_naam(aanmelding["naam"])
            gegevens = {
                "bordje": aanmelding["bordje"],
                "modus": "bestaand" if lid else "nieuw",
                "lid_id": lid["id"] if lid else None,
                "bordje_aanpassen": bool(data.get("bordje_aanpassen")),
                "voornaam": lid["voornaam"] if lid and lid["voornaam"] else voornaam,
                "achternaam": lid["achternaam"] if lid and lid["achternaam"] else achternaam,
                "bedrag": aanmelding["bedrag"],
                "betaalwijze": aanmelding["betaalwijze"] if aanmelding["betaalwijze"] in BETAALWIJZEN else None,
                "betaald_op": aanmelding["datum"],
            }
            _, fout = keur_goed(db, aanmelding, gegevens, session.get("gebruiker_naam"),
                                _club_instellingen(db)["club_van_20_bedrag"])
            if fout:
                db.rollback()
                return {"fout": "niet_mogelijk", "melding": fout}, 409
            return {"melding": f"{aanmelding['bordje']} is goedgekeurd en staat nu bij de leden."}, 200

        return eenmalig(actie)

    @app.route("/api/app/aanmeldingen/<int:aanmelding_id>/afwijzen", methods=["POST"])
    def api_app_aanmelding_afwijzen(aanmelding_id):
        reden = str(_data().get("reden") or "")[:120]

        def actie(db):
            aanmelding = _openstaande_aanmelding(db, aanmelding_id)
            if aanmelding is None:
                return {"fout": "niet_gevonden", "melding": "Deze aanmelding is al behandeld of bestaat niet meer."}, 409
            wijs_af(db, aanmelding_id, reden, session.get("gebruiker_naam"))
            return {"melding": f"Aanmelding van {aanmelding['bordje']} afgewezen."}, 200

        return eenmalig(actie)

    # ------------------------------------------------------------ agenda, prognose, barcodes

    @app.route("/api/app/agenda")
    def api_app_agenda():
        dagen = kies_dagen(request.args.get("dagen"))
        weken = []
        for w in bouw_agenda(get_db(), vandaag_amsterdam(), dagen):
            weken.append({
                "week": w["week"],
                "dagen": [{
                    "datum": d["datum"], "weekdag": d["weekdag"], "datum_tekst": d["datum_tekst"],
                    "vandaag": d["vandaag"], "morgen": d["morgen"], "open": d["open"],
                    "dicht_op_vaste_dag": d["dicht_op_vaste_dag"], "uitzondering": d["uitzondering"],
                    "uitzondering_tekst": d["uitzondering_tekst"], "training": d["training"],
                    "wedstrijden": [{"tijd": x["tijd"], "team": x["team"], "omschrijving": x["omschrijving"],
                                     "afgelast": bool(x["afgelast"])} for x in d["wedstrijden"]],
                    "evenementen": [{"naam": x["naam"], "soort": x["soort"], "groep": x["groep"]} for x in d["evenementen"]],
                    "bardiensten": [{"van": x["start_tijd"], "tot": x["eind_tijd"], "namen": x["namen"]} for x in d["bardiensten"]],
                    "weer": d["weer"],
                } for d in w["dagen"]],
            })
        return jsonify({"dagen": dagen, "weken": weken})

    @app.route("/api/app/prognose")
    def api_app_prognose():
        """De prognose (het voorspelmodel; kan op de server enkele seconden duren): wat er de komende dagen verkocht
        wordt en wat er op dreigt te raken."""
        from voorspelling import maak_prognose  # hier pas: het voorspelmodel is groot

        dagen = _getal(request.args.get("dagen"), 7)
        dagen = dagen if dagen in (3, 7, 14) else 7
        try:
            prognose = maak_prognose(get_db(), dagen=dagen)
        except Exception as fout:
            print(f"[app] prognose mislukt: {fout}")
            return _fout("De prognose kon niet worden berekend. Probeer het straks opnieuw.", 500, "server")
        if not prognose.get("beschikbaar"):
            return jsonify({"beschikbaar": False, "reden": prognose.get("reden"), "dagen": dagen})
        return jsonify({
            "beschikbaar": True,
            "dagen": dagen,
            "totaal": {k: prognose["totaal"][k] for k in ("omzet", "laag", "hoog")},
            "samenvatting": prognose["samenvatting"],
            "per_dag": [
                {"datum": d["datum"].isoformat(), "weekdag": d["weekdag_kort"], "open": d["open"], "omzet": d.get("omzet", 0),
                 "wedstrijden": len(d["wedstrijden"]) if isinstance(d["wedstrijden"], (list, tuple)) else int(d["wedstrijden"] or 0),
                 "evenementen": d["evenementen"] if isinstance(d["evenementen"], int) else len(d["evenementen"] or ()),
                 "training": bool(d["training"])}
                for d in prognose["dagen_overzicht"]
            ],
            "producten": [
                {"id": p["product"]["id"], "naam": p["product"]["naam"], "categorie": p["product"]["categorie"],
                 "eenheid": p["product"]["eenheid"], "voorraad": p["voorraad"], "verwacht": p["verwacht"],
                 "laag": p["laag"], "hoog": p["hoog"], "kans_tekort": p["kans_tekort"], "dekking_dagen": p["dekking_dagen"],
                 "status": p["status"], "advies_stuks": p["advies_stuks"], "advies_eenheden": p["advies_eenheden"],
                 "besteleenheid": p["besteleenheid"], "onderweg": p["onderweg"], "al_op_bestellijst": p["al_op_bestellijst"]}
                for p in prognose["producten"]
            ],
        })

    @app.route("/api/app/barcodes")
    def api_app_barcodes():
        """Alle artikelen met hun barcodes per product (Voorraad > Barcodes op de site), eventueel gezocht."""
        db = get_db()
        per_product = []
        for a in barcodes.alle_artikelen(db, request.args.get("q", "")):
            if not per_product or per_product[-1]["product_id"] != a["product_id"]:
                per_product.append({"product_id": a["product_id"], "naam": a["product_naam"], "categorie": a["categorie"],
                                    "eenheid": a["eenheid"], "artikelen": []})
            per_product[-1]["artikelen"].append({
                "naam": a["naam"], "merk": a["merk"] or None, "ean": a["ean"], "doos_ean": a["ean_omverpakking"],
                "per_doos": a["per_omverpakking"] or None, "aantal": a["aantal_per_verpakking"],
                "inkoopprijs": a["inkoopprijs"] or None, "leverancier": a["leverancier_naam"],
            })
        return jsonify({"producten": per_product, "aantal": sum(len(p["artikelen"]) for p in per_product)})

    # ------------------------------------------------------------ taken

    def _taak_json(taak, gebruiker_id):
        doel = taak["doel"]
        return {
            "id": taak["id"],
            "titel": taak["titel"],
            "omschrijving": taak["omschrijving"] or None,
            "deadline": taak["deadline"],
            "te_laat": taak["te_laat"],
            "stappen": [{"tekst": s, "af": i in taak["mijn_afgevinkt"]} for i, s in enumerate(taak["stappen_lijst"])],
            "anderen": [{"naam": m["naam"], "klaar": m["afgerond_op"] is not None} for m in taak["mensen"] if m["id"] != gebruiker_id],
            "door": taak["aangemaakt_door"],
            "doel": {"endpoint": doel["endpoint"], "label": doel["label"]} if doel else None,
        }

    @app.route("/api/app/taken/<int:taak_id>")
    def api_app_taak(taak_id):
        gebruiker_id = session.get("gebruiker_id")
        taak = taak_voor_persoon(get_db(), taak_id, gebruiker_id)
        if taak is None:
            return _fout("Deze taak staat niet (meer) open voor jou.", 404, "niet_gevonden")
        return jsonify(_taak_json(taak, gebruiker_id))

    @app.route("/api/app/taken/<int:taak_id>/stap", methods=["POST"])
    def api_app_taak_stap(taak_id):
        data = _data()
        index = _getal(data.get("stap"))
        uitkomst = None if index is None else vink_stap(get_db(), taak_id, session.get("gebruiker_id"), index, bool(data.get("af")))
        if uitkomst is None:
            return _fout("Deze stap bestaat niet (meer).", 404, "niet_gevonden")
        return jsonify(uitkomst)

    @app.route("/api/app/taken/<int:taak_id>/afronden", methods=["POST"])
    def api_app_taak_afronden(taak_id):
        def actie(db):
            taak = rond_af(db, taak_id, session.get("gebruiker_id"), session.get("gebruiker_naam"))
            if taak is None:
                return {"fout": "niet_gevonden", "melding": "Deze taak staat niet (meer) open voor jou."}, 404
            if taak.get("onvolledig"):
                gedaan, totaal = taak["onvolledig"]
                return {"fout": "onvolledig", "melding": f"Vink eerst alle stappen af ({gedaan} van {totaal})."}, 409
            if taak["klaar"]:
                volgende = taak["volgende"]
                tekst = f"Taak {taak['titel']} is klaar."
                if isinstance(volgende, (date, datetime)):
                    tekst += f" De volgende keer is {volgende.strftime('%d-%m')}."
                return {"melding": tekst}, 200
            nog = ", ".join(m["naam"] for m in vind_taak(db, taak_id)["mensen"] if m["afgerond_op"] is None)
            return {"melding": f"Taak {taak['titel']} is voor jou afgerond. Nog te doen door: {nog}."}, 200

        return eenmalig(actie)
