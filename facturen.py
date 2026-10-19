"""Facturen inboeken door dozen en verpakkingen te scannen (Bestellen > Factuur inboeken, en later de app op de
handterminal).

Een inboekronde hoort bij één factuur: je scant wat er binnenkomt, de site zoekt per barcode het artikel op (zie
barcodes.py) en telt het op. Een doos die je twee keer scant, telt twee keer. Een onbekende barcode koppel je meteen
aan een product (als nieuw artikel, of als doos van een bekend artikel) en dan telt die scan alsnog mee. De ronde blijft
bewaard tot je hem afrondt: valt de handterminal in slaap, dan ben je niets kwijt.

Bij het afronden gaat de voorraad omhoog (een boeking per product). Hoort de ronde bij een openstaande bestelling, dan
staat die daarna op ontvangen: per bestelregel wat er is binnengekomen, en wat niet is gescand is manco, net als bij
Bestellingen > Inboeken."""

import barcodes
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
    return db.execute(
        "SELECT id, aangemaakt_op, referentie FROM bestellingen WHERE status = 'besteld' ORDER BY aangemaakt_op DESC"
    ).fetchall()


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
    {"ronde", "regels", "per_product": [{product, eenheden, bedrag}], "totaal", "scans", "verschil"}"""
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
    return {
        "ronde": rij,
        "regels": regels,
        "per_product": sorted(per_product.values(), key=lambda p: p["naam"].lower()),
        "totaal": totaal,
        "scans": sum(g["aantal"] for g in regels),
        "verschil": round(totaal - rij["factuurbedrag"], 2) if rij["factuurbedrag"] is not None else None,
    }


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
    else:
        bestelling_id = None

    for product_id, eenheden in binnen.items():
        db.execute("UPDATE producten SET voorraad = voorraad + ? WHERE id = ?", (eenheden, product_id))
        db.execute(
            """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, bestelling_id)
               VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
            (product_id, eenheden, nu, door, door_id, omschrijving, bestelling_id if product_id in besteld else None),
        )
    db.execute(
        "UPDATE inboekrondes SET status = 'afgerond', afgerond_op = ?, afgerond_door = ? WHERE id = ?",
        (nu, door, ronde_id),
    )
    db.commit()
    return {"producten": len(binnen), "eenheden": sum(binnen.values()), "bestelling_id": bestelling_id,
            "manco": manco}, None


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
    }
