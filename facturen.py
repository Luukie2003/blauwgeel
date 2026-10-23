"""Facturen inboeken door dozen en verpakkingen te scannen (Bestellen > Factuur inboeken, en later de app op de
handterminal).

Een inboekronde hoort bij één factuur: je scant wat er binnenkomt, de site zoekt per barcode het artikel op (zie
barcodes.py) en telt het op. Een doos die je twee keer scant, telt twee keer. Een onbekende barcode koppel je meteen
aan een product (als nieuw artikel, of als doos van een bekend artikel) en dan telt die scan alsnog mee. De ronde blijft
bewaard tot je hem afrondt: valt de handterminal in slaap, dan ben je niets kwijt.

Een klaargezette bestelling (Bestellen > Bestellijst) is het concept van de factuur: die staat hier klaar om in te
boeken (ronde_voor_bestelling). De ronde toont dan per besteld product wat er besteld is en wat er al gescand is; wat
zonder barcode binnenkomt zet je er in één keer bij ("zoals besteld", voeg_rest_toe). Wat er meekomt maar niet besteld
was, scan je gewoon mee.

Bij het afronden gaat de voorraad omhoog (een boeking per product). Hoort de ronde bij een openstaande bestelling, dan
staat die daarna op ontvangen: per bestelregel wat er is binnengekomen, wat niet is gescand is manco, en wat er extra
meekwam komt er als regel bij (besteld: 0)."""

import barcodes
from helpers.producten import besteleenheid_factor, besteleenheid_naam, inkoop_per_stuk
from helpers.tijd import now_str

STATUSSEN = ("open", "afgerond", "geannuleerd")


def _ronde_rij(db, ronde_id):
    return db.execute(
        """SELECT r.*, l.naam AS leverancier_naam, b.referentie AS bestelling_referentie
           FROM inboekrondes r
           LEFT JOIN leveranciers l ON l.id = r.leverancier_id
           LEFT JOIN bestellingen b ON b.id = r.bestelling_id
           WHERE r.id = ?""",
        (ronde_id,),
    ).fetchone()


def open_rondes(db):
    return db.execute(
        """SELECT r.*, l.naam AS leverancier_naam,
                  (SELECT COALESCE(SUM(aantal), 0) FROM inboekronde_regels WHERE ronde_id = r.id) AS scans
           FROM inboekrondes r LEFT JOIN leveranciers l ON l.id = r.leverancier_id
           WHERE r.status = 'open' ORDER BY r.gestart_op DESC"""
    ).fetchall()


def recente_rondes(db, aantal=10):
    return db.execute(
        """SELECT r.*, l.naam AS leverancier_naam FROM inboekrondes r
           LEFT JOIN leveranciers l ON l.id = r.leverancier_id
           WHERE r.status != 'open' ORDER BY COALESCE(r.afgerond_op, r.gestart_op) DESC LIMIT ?""",
        (aantal,),
    ).fetchall()


def open_bestellingen(db):
    """De klaargezette bestellingen (het concept van een factuur), nieuwste eerst, met hoeveel producten erop staan, een
    korte samenvatting en de open ronde waarin hij al wordt ingeboekt (ronde_id, of None)."""
    bestellingen = [
        dict(r)
        for r in db.execute(
            """SELECT b.id, b.aangemaakt_op, b.referentie, b.besteld_door,
                      (SELECT MAX(r.id) FROM inboekrondes r WHERE r.bestelling_id = b.id AND r.status = 'open') AS ronde_id
               FROM bestellingen b WHERE b.status = 'besteld' ORDER BY b.aangemaakt_op DESC, b.id DESC"""
        ).fetchall()
    ]
    for b in bestellingen:
        regels = _bestelregels(db, b["id"])
        b["producten"] = len(regels)
        b["samenvatting"] = ", ".join(f"{r['besteld_eenheden']} {r['besteleenheid']} {r['naam']}" for r in regels)
    return bestellingen


def _bestelregels(db, bestelling_id):
    """De regels van een bestelling, met de besteleenheid erbij (een krat van 24 en niet 24 flesjes)."""
    uitkomst = []
    for r in db.execute(
        """SELECT br.product_id, br.aantal_besteld, p.naam, p.eenheid, p.besteleenheid, p.besteleenheid_factor,
                  p.inkoopprijs
           FROM bestelregels br JOIN producten p ON p.id = br.product_id
           WHERE br.bestelling_id = ? AND br.aantal_besteld > 0 ORDER BY p.categorie, p.naam COLLATE NOCASE""",
        (bestelling_id,),
    ).fetchall():
        factor = besteleenheid_factor(r)
        uitkomst.append({
            "product_id": r["product_id"],
            "naam": r["naam"],
            "eenheid": r["eenheid"],
            "besteld": r["aantal_besteld"],
            "per_besteleenheid": factor,
            "besteleenheid": besteleenheid_naam(r) if factor > 1 else r["eenheid"],
            "besteld_eenheden": -(-r["aantal_besteld"] // factor),
            "inkoop_per_stuk": inkoop_per_stuk(r),
        })
    return uitkomst


def ronde_voor_bestelling(db, bestelling_id, door=None, door_id=None, bron="site"):
    """Een klaargezette bestelling inboeken: de open ronde die er al bij hoort, of een nieuwe (met de leverancier als
    alle producten van dezelfde leverancier komen). Geeft het id van de ronde, of None als de bestelling niet (meer)
    openstaat."""
    bestelling_id = _getal(bestelling_id) or 0
    if not db.execute("SELECT 1 FROM bestellingen WHERE id = ? AND status = 'besteld'", (bestelling_id,)).fetchone():
        return None
    bestaand = db.execute(
        "SELECT id FROM inboekrondes WHERE bestelling_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
        (bestelling_id,),
    ).fetchone()
    if bestaand:
        return bestaand["id"]
    leveranciers = {
        r["leverancier_id"]
        for r in db.execute(
            """SELECT p.leverancier_id FROM bestelregels br JOIN producten p ON p.id = br.product_id
               WHERE br.bestelling_id = ?""",
            (bestelling_id,),
        ).fetchall()
    }
    leverancier_id = next(iter(leveranciers)) if len(leveranciers) == 1 else None
    return start_ronde(db, leverancier_id, None, bestelling_id, door=door, door_id=door_id, bron=bron)


def _getal(waarde, soort=int):
    try:
        return soort(str("" if waarde is None else waarde).replace(",", ".").strip())
    except ValueError:
        return None


def start_ronde(db, leverancier_id=None, factuurnummer=None, bestelling_id=None, door=None, door_id=None, bron="site"):
    """Begint een nieuwe inboekronde; geeft het id terug."""
    leverancier_id = _getal(leverancier_id) or None
    bestelling_id = _getal(bestelling_id) or None
    if bestelling_id and not db.execute(
        "SELECT 1 FROM bestellingen WHERE id = ? AND status = 'besteld'", (bestelling_id,)
    ).fetchone():
        bestelling_id = None  # alleen een openstaande bestelling kan erbij horen
    ronde_id = db.execute(
        """INSERT INTO inboekrondes (leverancier_id, bestelling_id, factuurnummer, gestart_door, gestart_door_id,
               gestart_op, bron)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (leverancier_id, bestelling_id, " ".join(str(factuurnummer or "").split()) or None, door, door_id, now_str(),
         bron),
    ).lastrowid
    db.commit()
    return ronde_id


def werk_gegevens_bij(db, ronde_id, form):
    """Leverancier, factuurnummer, het bedrag op de factuur en de bestelling van een open ronde."""
    bestelling_id = _getal(form.get("bestelling_id")) or None
    if bestelling_id and not db.execute(
        "SELECT 1 FROM bestellingen WHERE id = ? AND status = 'besteld'", (bestelling_id,)
    ).fetchone():
        bestelling_id = None
    bedrag = _getal(form.get("factuurbedrag"), float)
    db.execute(
        """UPDATE inboekrondes SET leverancier_id = ?, factuurnummer = ?, factuurbedrag = ?, bestelling_id = ?,
               opmerking = ?
           WHERE id = ? AND status = 'open'""",
        (
            _getal(form.get("leverancier_id")) or None,
            " ".join(str(form.get("factuurnummer") or "").split()) or None,
            bedrag if bedrag is not None and bedrag >= 0 else None,
            bestelling_id,
            str(form.get("opmerking") or "").strip() or None,
            ronde_id,
        ),
    )
    db.commit()


def ronde(db, ronde_id):
    """De ronde met zijn regels en totalen, of None.
    {"ronde", "regels", "per_product": [{product, eenheden, bedrag, besteld}], "totaal", "scans", "verschil",
     "besteld": [...]} met bij een bestelling per besteld product wat er besteld is, wat er al gescand is en wat er nog
    mist ("rest", zie _besteld)."""
    rij = _ronde_rij(db, ronde_id)
    if rij is None:
        return None
    regels = db.execute(
        """SELECT g.*, p.naam AS product_naam, p.eenheid, p.voorraad
           FROM inboekronde_regels g JOIN producten p ON p.id = g.product_id
           WHERE g.ronde_id = ? ORDER BY g.laatst_gescand_op DESC, g.id DESC""",
        (ronde_id,),
    ).fetchall()
    per_product = {}
    for g in regels:
        p = per_product.setdefault(g["product_id"], {"product_id": g["product_id"], "naam": g["product_naam"],
                                                     "eenheid": g["eenheid"], "eenheden": 0, "bedrag": 0.0})
        p["eenheden"] += g["aantal"] * g["eenheden_per_stuk"]
        p["bedrag"] += g["aantal"] * g["prijs_per_stuk"]
    totaal = round(sum(p["bedrag"] for p in per_product.values()), 2)
    besteld = _besteld(db, rij, per_product)
    besteld_ids = {b["product_id"] for b in besteld}
    for p in per_product.values():
        p["besteld"] = p["product_id"] in besteld_ids
    return {
        "ronde": rij,
        "regels": regels,
        "per_product": sorted(per_product.values(), key=lambda p: p["naam"].lower()),
        "totaal": totaal,
        "scans": sum(g["aantal"] for g in regels),
        "verschil": round(totaal - rij["factuurbedrag"], 2) if rij["factuurbedrag"] is not None else None,
        "besteld": besteld,
    }


def _besteld(db, rij, per_product):
    """Bij een ronde die bij een bestelling hoort: per besteld product besteld, gescand en wat er nog mist, met de
    status 'binnen' (alles gescand), 'deels' of 'nog_niet'. Zonder bestelling: een lege lijst."""
    if not rij["bestelling_id"]:
        return []
    uitkomst = []
    for b in _bestelregels(db, rij["bestelling_id"]):
        gescand = per_product.get(b["product_id"], {}).get("eenheden", 0)
        rest = max(0, b["besteld"] - gescand)
        uitkomst.append({
            **b,
            "gescand": gescand,
            "rest": rest,
            "status": "binnen" if rest == 0 else ("deels" if gescand else "nog_niet"),
        })
    return uitkomst


def _is_open(db, ronde_id):
    rij = db.execute("SELECT status FROM inboekrondes WHERE id = ?", (ronde_id,)).fetchone()
    return rij is not None and rij["status"] == "open"


def scan(db, ronde_id, tekst):
    """Verwerkt één scan. Geeft {"status", "melding", "regel_id", "barcode"} terug, met status 'toegevoegd',
    'onbekend' (geldige barcode die nog niet bekend is: koppel 'm), 'ongeldig' of 'gesloten'. 'barcode' is de uitkomst
    van barcodes.zoek_barcode."""
    if not _is_open(db, ronde_id):
        return {"status": "gesloten", "melding": "Deze inboekronde is al afgerond.", "regel_id": None, "barcode": None}
    gevonden = barcodes.zoek_barcode(db, tekst)
    if not gevonden["geldig"]:
        return {"status": "ongeldig", "melding": gevonden["melding"], "regel_id": None, "barcode": gevonden}
    if not gevonden["bekend"]:
        return {"status": "onbekend", "melding": f"Barcode {gevonden['code']} is nog niet bekend.", "regel_id": None,
                "barcode": gevonden}
    a = gevonden["artikel"]
    nu = now_str()
    bestaand = db.execute(
        "SELECT id FROM inboekronde_regels WHERE ronde_id = ? AND code = ?", (ronde_id, gevonden["code"])
    ).fetchone()
    if bestaand:
        db.execute(
            "UPDATE inboekronde_regels SET aantal = aantal + 1, laatst_gescand_op = ? WHERE id = ?", (nu, bestaand["id"])
        )
        regel_id = bestaand["id"]
    else:
        regel_id = db.execute(
            """INSERT INTO inboekronde_regels (ronde_id, product_id, artikel_id, code, niveau, omschrijving, aantal,
                   eenheden_per_stuk, prijs_per_stuk, laatst_gescand_op)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (ronde_id, a["product_id"], a["id"], gevonden["code"], gevonden["niveau"], gevonden["omschrijving"],
             gevonden["aantal"], gevonden["inkoopprijs"] or 0, nu),
        ).lastrowid
    db.commit()
    return {"status": "toegevoegd", "melding": gevonden["omschrijving"], "regel_id": regel_id, "barcode": gevonden}


def voeg_handmatig_toe(db, ronde_id, product_id, eenheden, prijs=None):
    """Iets zonder barcode (of een barcode die even niet scant): een aantal van een product. Geeft een foutmelding of
    None terug."""
    if not _is_open(db, ronde_id):
        return "Deze inboekronde is al afgerond."
    product = db.execute("SELECT id, naam, eenheid FROM producten WHERE id = ?", (_getal(product_id) or 0,)).fetchone()
    if product is None:
        return "Kies een product."
    aantal = _getal(eenheden)
    if not aantal or aantal < 1:
        return "Vul een aantal van 1 of meer in."
    bedrag = _getal(prijs, float) or 0.0
    db.execute(
        """INSERT INTO inboekronde_regels (ronde_id, product_id, code, niveau, omschrijving, aantal, eenheden_per_stuk,
               prijs_per_stuk, laatst_gescand_op)
           VALUES (?, ?, NULL, 'handmatig', ?, 1, ?, ?, ?)""",
        (ronde_id, product["id"], f"{product['naam']} (zonder barcode)", aantal, max(0.0, bedrag), now_str()),
    )
    db.commit()
    return None


def plu_lijst(db, besteld=None, per_product=None):
    """De PLU-lijst: wat binnenkomt zonder barcode om te scannen (fusten, en producten die op 'heeft geen barcode' staan),
    om met een tik in te boeken. Per product hoeveel er in een besteleenheid zit (een fust is 1), wat die kost, wat er
    besteld is (bij een klaargezette bestelling) en wat er al bij deze factuur staat. Besteld eerst, dan op naam."""
    besteld = {b["product_id"]: b for b in (besteld or [])}
    per_product = per_product or {}
    uitkomst = []
    for p in db.execute(
        """SELECT * FROM producten
           WHERE actief = 1 AND COALESCE(gearchiveerd, 0) = 0
             AND (COALESCE(geen_barcode, 0) = 1 OR COALESCE(glazen_per_fust, 0) > 0)
           ORDER BY naam COLLATE NOCASE"""
    ).fetchall():
        factor = besteleenheid_factor(p)
        b = besteld.get(p["id"])
        uitkomst.append({
            "product_id": p["id"],
            "naam": p["naam"],
            "eenheid": p["eenheid"],
            "besteleenheid": besteleenheid_naam(p) if factor > 1 else p["eenheid"],
            "per_besteleenheid": factor,
            "prijs_per_besteleenheid": round(inkoop_per_stuk(p) * factor, 4),
            "fust": bool(p["glazen_per_fust"]),
            "besteld": b["besteld"] if b else 0,
            "gescand": per_product.get(p["id"], {}).get("eenheden", 0),
        })
    uitkomst.sort(key=lambda x: (not x["besteld"], x["naam"].lower()))
    return uitkomst


def voeg_plu_toe(db, ronde_id, product_id, aantal):
    """Uit de PLU-lijst: aantal besteleenheden (fusten, kratten) van een product zonder barcode. Tik je hetzelfde product
    nog een keer aan, dan komt het bij dezelfde regel (die je met min en plus nog kunt verbeteren). Geeft een
    foutmelding of None."""
    if not _is_open(db, ronde_id):
        return "Deze inboekronde is al afgerond."
    p = db.execute("SELECT * FROM producten WHERE id = ?", (_getal(product_id) or 0,)).fetchone()
    if p is None:
        return "Kies een product."
    aantal = _getal(aantal)
    if not aantal or aantal < 1:
        return "Vul een aantal van 1 of meer in."
    factor = besteleenheid_factor(p)
    eenheid = besteleenheid_naam(p) if factor > 1 else p["eenheid"]
    omschrijving = f"{p['naam']} ({eenheid}{f' van {factor}' if factor > 1 else ''}, zonder barcode)"
    nu = now_str()
    bestaand = db.execute(
        """SELECT id FROM inboekronde_regels
           WHERE ronde_id = ? AND product_id = ? AND niveau = 'plu' AND eenheden_per_stuk = ?""",
        (ronde_id, p["id"], factor),
    ).fetchone()
    if bestaand:
        db.execute("UPDATE inboekronde_regels SET aantal = aantal + ?, laatst_gescand_op = ? WHERE id = ?",
                   (aantal, nu, bestaand["id"]))
    else:
        db.execute(
            """INSERT INTO inboekronde_regels (ronde_id, product_id, code, niveau, omschrijving, aantal, eenheden_per_stuk,
                   prijs_per_stuk, laatst_gescand_op)
               VALUES (?, ?, NULL, 'plu', ?, ?, ?, ?, ?)""",
            (ronde_id, p["id"], omschrijving, aantal, factor, round(inkoop_per_stuk(p) * factor, 4), nu),
        )
    db.commit()
    return None


def volle_colli(db, regel_id):
    """Bij een scan van een losse verpakking (één flesje, één zak): hoeveel er in de hele colli zit en hoe die heet, als
    er iets groters bestaat. Eerst de doos van dat artikel (met een eigen barcode), anders de besteleenheid van het
    product (een krat Hertog Jan zonder barcode). Geeft {"aantal", "naam", "doos_code", "los"} of None. Zoals
    Product.volleEenheid in de app."""
    g = db.execute(
        """SELECT g.*, a.aantal_per_verpakking, a.ean_omverpakking, a.per_omverpakking, p.besteleenheid,
                  p.besteleenheid_factor, p.eenheid, p.naam AS product_naam
           FROM inboekronde_regels g JOIN producten p ON p.id = g.product_id
           LEFT JOIN artikelen a ON a.id = g.artikel_id WHERE g.id = ?""", (regel_id,),
    ).fetchone()
    if g is None or g["niveau"] != "verpakking":
        return None
    los = g["eenheden_per_stuk"] or 1
    if g["ean_omverpakking"] and g["per_omverpakking"] and los * g["per_omverpakking"] > los:
        return {"aantal": los * g["per_omverpakking"], "naam": "doos", "doos_code": g["ean_omverpakking"], "los": los,
                "eenheid": g["eenheid"], "product": g["product_naam"]}
    factor = besteleenheid_factor(g)
    if g["besteleenheid"] and factor > los:
        return {"aantal": factor, "naam": besteleenheid_naam(g), "doos_code": None, "los": los, "eenheid": g["eenheid"],
                "product": g["product_naam"]}
    return None


def maak_hele_colli(db, ronde_id, regel_id):
    """De laatste scan van een losse verpakking wordt de hele colli: met de doos-barcode als die er is (de losse scan
    gaat eraf, de doos erbij), anders telt de losse regel zo vaak extra als er in de colli zitten. Geeft een
    foutmelding of None."""
    colli = volle_colli(db, regel_id)
    if colli is None:
        return "Hier bestaat geen grotere colli van."
    if colli["doos_code"]:
        g = db.execute("SELECT aantal FROM inboekronde_regels WHERE id = ? AND ronde_id = ?", (regel_id, ronde_id)).fetchone()
        if g is None:
            return "Deze scan bestaat niet meer."
        fout = zet_aantal(db, ronde_id, regel_id, g["aantal"] - 1)
        if fout:
            return fout
        uitkomst = scan(db, ronde_id, colli["doos_code"])
        return None if uitkomst["status"] == "toegevoegd" else uitkomst["melding"]
    extra = max(0, colli["aantal"] // max(1, colli["los"]) - 1)
    db.execute("UPDATE inboekronde_regels SET aantal = aantal + ? WHERE id = ? AND ronde_id = ?", (extra, regel_id, ronde_id))
    db.commit()
    return None


def nog_niet_binnen(gegevens):
    """Voor 'Factuur gecontroleerd': wat er van de klaargezette bestelling nog mist (niets of te weinig gescand). Bij het
    inboeken wordt dat manco, net als bij Bestellingen > Inboeken."""
    return [
        {"product_id": b["product_id"], "naam": b["naam"], "besteld": b["besteld"], "gescand": b["gescand"],
         "rest": b["rest"], "eenheid": b["eenheid"], "status": b["status"]}
        for b in gegevens["besteld"] if b["rest"] > 0
    ]


def voeg_rest_toe(db, ronde_id, product_id=None):
    """Wat van de bestelling nog niet gescand is, erbij zetten zoals besteld (iets zonder barcode, of een doos die je
    niet apart scant): voor één product, of zonder product_id voor alles wat nog mist. Geeft (aantal producten,
    foutmelding) terug."""
    if not _is_open(db, ronde_id):
        return 0, "Deze inboekronde is al afgerond."
    gegevens = ronde(db, ronde_id)
    if not gegevens["besteld"]:
        return 0, "Deze factuur hoort niet bij een klaargezette bestelling."
    product_id = _getal(product_id) if product_id not in (None, "") else None
    nu = now_str()
    toegevoegd = 0
    for b in gegevens["besteld"]:
        if b["rest"] <= 0 or (product_id is not None and b["product_id"] != product_id):
            continue
        db.execute(
            """INSERT INTO inboekronde_regels (ronde_id, product_id, code, niveau, omschrijving, aantal, eenheden_per_stuk,
                   prijs_per_stuk, laatst_gescand_op)
               VALUES (?, ?, NULL, 'handmatig', ?, 1, ?, ?, ?)""",
            (ronde_id, b["product_id"], f"{b['naam']} (zoals besteld)", b["rest"],
             round(b["rest"] * b["inkoop_per_stuk"], 2), nu),
        )
        toegevoegd += 1
    db.commit()
    if not toegevoegd:
        return 0, "Daar mist niets meer van: alles is al gescand."
    return toegevoegd, None


def zet_aantal(db, ronde_id, regel_id, aantal):
    """Hoe vaak een regel gescand is aanpassen (bijv. een dubbele scan terugdraaien); 0 haalt de regel weg."""
    if not _is_open(db, ronde_id):
        return "Deze inboekronde is al afgerond."
    aantal = _getal(aantal)
    if aantal is None or aantal < 0:
        return "Vul een aantal van 0 of meer in."
    if aantal == 0:
        db.execute("DELETE FROM inboekronde_regels WHERE id = ? AND ronde_id = ?", (regel_id, ronde_id))
    else:
        db.execute("UPDATE inboekronde_regels SET aantal = ? WHERE id = ? AND ronde_id = ?", (aantal, regel_id, ronde_id))
    db.commit()
    return None


def zet_prijs(db, ronde_id, regel_id, prijs):
    """De prijs van één scan (een doos, een fust) aanpassen naar wat er op de factuur staat. Bij het afronden wordt dat de
    nieuwe inkoopprijs van het artikel of product (zie _werk_prijzen_bij). Geeft een foutmelding of None."""
    if not _is_open(db, ronde_id):
        return "Deze inboekronde is al afgerond."
    bedrag = _getal(str(prijs or "").replace(",", "."), float)
    if bedrag is None or bedrag < 0:
        return "Vul een prijs van 0 of meer in."
    db.execute("UPDATE inboekronde_regels SET prijs_per_stuk = ?, prijs_aangepast = 1 WHERE id = ? AND ronde_id = ?",
               (round(bedrag, 4), regel_id, ronde_id))
    db.commit()
    return None


def _werk_prijzen_bij(db, ronde_id, door=None, door_id=None):
    """Bij het afronden: elke scan waarvan de prijs naar de factuur is aangepast, wordt de inkoopprijs. Van een artikel
    (per verpakking; een doos-scan gedeeld door wat erin zit) en daarna het product (het gemiddelde van zijn artikelen,
    zie barcodes.werk_inkoopprijs_bij); zonder artikel (PLU, handmatig) meteen die van het product, per besteleenheid.
    Geeft het aantal bijgewerkte prijzen. Commit niet."""
    nu = now_str()
    aantal = 0
    producten = set()
    for g in db.execute(
        """SELECT g.*, a.inkoopprijs AS artikel_prijs, a.per_omverpakking, p.inkoopprijs AS product_prijs,
                  p.besteleenheid_factor
           FROM inboekronde_regels g JOIN producten p ON p.id = g.product_id
           LEFT JOIN artikelen a ON a.id = g.artikel_id
           WHERE g.ronde_id = ? AND g.prijs_aangepast = 1""", (ronde_id,),
    ).fetchall():
        if g["artikel_id"] and g["artikel_prijs"] is not None:
            per_verpakking = g["prijs_per_stuk"] / (g["per_omverpakking"] or 1 if g["niveau"] == "omverpakking" else 1)
            if abs(per_verpakking - (g["artikel_prijs"] or 0)) >= 0.005:
                db.execute("UPDATE artikelen SET inkoopprijs = ?, bijgewerkt_op = ? WHERE id = ?",
                           (round(per_verpakking, 4), nu, g["artikel_id"]))
                producten.add(g["product_id"])
                aantal += 1
        else:
            nieuw = round(g["prijs_per_stuk"] / max(1, g["eenheden_per_stuk"]) * besteleenheid_factor(g), 4)
            if abs(nieuw - (g["product_prijs"] or 0)) >= 0.005:
                db.execute("UPDATE producten SET inkoopprijs = ? WHERE id = ?", (nieuw, g["product_id"]))
                db.execute(
                    """INSERT INTO prijs_geschiedenis (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id)
                       VALUES (?, 'inkoopprijs', ?, ?, ?, ?, ?)""",
                    (g["product_id"], g["product_prijs"] or 0, nieuw, nu, door, door_id),
                )
                aantal += 1
    for product_id in producten:
        barcodes.werk_inkoopprijs_bij(db, product_id, door, door_id)
    return aantal


def annuleren(db, ronde_id):
    db.execute("UPDATE inboekrondes SET status = 'geannuleerd', afgerond_op = ? WHERE id = ? AND status = 'open'",
               (now_str(), ronde_id))
    db.commit()


def afronden(db, ronde_id, door=None, door_id=None):
    """Boekt alles in: de voorraad omhoog per product, en een gekoppelde bestelling op ontvangen. Geeft
    (samenvatting, foutmelding) terug; samenvatting = {"producten", "eenheden", "bestelling_id", "manco"}."""
    gegevens = ronde(db, ronde_id)
    if gegevens is None:
        return None, "Deze inboekronde bestaat niet."
    r = gegevens["ronde"]
    if r["status"] != "open":
        return None, "Deze inboekronde is al afgerond."
    if not gegevens["per_product"]:
        return None, "Er is nog niets gescand."
    nu = now_str()
    omschrijving = "Factuur" + (f" {r['factuurnummer']}" if r["factuurnummer"] else "") + (
        f" ({r['leverancier_naam']})" if r["leverancier_naam"] else ""
    ) + " ingeboekt"
    binnen = {p["product_id"]: p["eenheden"] for p in gegevens["per_product"]}

    manco = 0
    besteld = set()  # de producten uit de gekoppelde bestelling: hun boeking hoort bij die bestelling
    bestelling_id = r["bestelling_id"]
    if bestelling_id and db.execute(
        "SELECT 1 FROM bestellingen WHERE id = ? AND status = 'besteld'", (bestelling_id,)
    ).fetchone():
        # Net als Bestellingen > Inboeken: per bestelregel wat er binnen is; niet gescand = manco.
        for regel in db.execute("SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling_id,)).fetchall():
            besteld.add(regel["product_id"])
            ontvangen = binnen.get(regel["product_id"], 0)
            manco += 0 if ontvangen else 1
            db.execute(
                "UPDATE bestelregels SET aantal_ontvangen = ?, manco = ? WHERE id = ?",
                (ontvangen, 0 if ontvangen else 1, regel["id"]),
            )
        db.execute("UPDATE bestellingen SET status = 'ontvangen', ontvangen_op = ? WHERE id = ?", (nu, bestelling_id))
        # Wat er extra meekwam (niet besteld) hoort ook bij deze levering, net als bij Bestellingen > Inboeken.
        for product_id in binnen.keys() - besteld:
            db.execute(
                """INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld, aantal_ontvangen, manco)
                   VALUES (?, ?, 0, ?, 0)""",
                (bestelling_id, product_id, binnen[product_id]),
            )
            besteld.add(product_id)
    else:
        bestelling_id = None

    for product_id, eenheden in binnen.items():
        db.execute("UPDATE producten SET voorraad = voorraad + ? WHERE id = ?", (eenheden, product_id))
        db.execute(
            """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, bestelling_id)
               VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
            (product_id, eenheden, nu, door, door_id, omschrijving, bestelling_id if product_id in besteld else None),
        )
    prijzen = _werk_prijzen_bij(db, ronde_id, door, door_id)
    db.execute(
        "UPDATE inboekrondes SET status = 'afgerond', afgerond_op = ?, afgerond_door = ? WHERE id = ?",
        (nu, door, ronde_id),
    )
    db.commit()
    return {"producten": len(binnen), "eenheden": sum(binnen.values()), "bestelling_id": bestelling_id,
            "manco": manco, "prijzen": prijzen}, None


def als_json(gegevens):
    """Een ronde (zie ronde()) als JSON voor de app op de handterminal."""
    r = gegevens["ronde"]
    return {
        "id": r["id"],
        "status": r["status"],
        "leverancier_id": r["leverancier_id"],
        "leverancier": r["leverancier_naam"],
        "bestelling_id": r["bestelling_id"],
        "factuurnummer": r["factuurnummer"],
        "factuurbedrag": r["factuurbedrag"],
        "opmerking": r["opmerking"],
        "gestart_op": r["gestart_op"],
        "totaal": gegevens["totaal"],
        "verschil": gegevens["verschil"],
        "scans": gegevens["scans"],
        "regels": [
            {
                "id": g["id"], "product_id": g["product_id"], "product": g["product_naam"], "code": g["code"],
                "niveau": g["niveau"], "omschrijving": g["omschrijving"], "aantal": g["aantal"],
                "eenheden_per_stuk": g["eenheden_per_stuk"], "eenheden": g["aantal"] * g["eenheden_per_stuk"],
                "eenheid": g["eenheid"], "prijs_per_stuk": g["prijs_per_stuk"],
            }
            for g in gegevens["regels"]
        ],
        "per_product": gegevens["per_product"],
        "bestelling_referentie": r["bestelling_referentie"],
        "besteld": [{k: v for k, v in b.items() if k != "inkoop_per_stuk"} for b in gegevens["besteld"]],
        "nog_niet_binnen": nog_niet_binnen(gegevens),
    }
