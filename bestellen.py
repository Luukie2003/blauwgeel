"""Een bestelling klaarzetten: op de site (Bestellijst > Voorgesteld om te bestellen) en in de handterminal-app. Een
klaargezette bestelling is het concept van de factuur (zie facturen.py); wat er bij een vorige bestelling niet geleverd
was, is met deze bestelling opgevolgd (zie manco.py).

Per leverancier (maak_bestellingen, 1.70.0): wat bij Sligro vandaan komt, wordt een andere bestelling dan wat bij de
Makro vandaan komt. Zo gaat elke bestelling naar één leverancier (met de lijst als pdf of tekst om door te sturen, zie
bestelling_gegevens en bestel_tekst) en komt hij als één factuur binnen."""

import bestelvoorstel
import manco
from helpers.producten import besteleenheid_factor, besteleenheid_naam, naar_voorraadeenheden
from helpers.tijd import now_str
from pdf.basis import NAAM_CLUB


def maak_bestellingen(db, besteleenheden_per_product, door=None, door_id=None):
    """Zoals maak_bestelling, maar een bestelling per leverancier; wat geen leverancier heeft samen in één. Geeft
    [{"id", "leverancier_id", "leverancier", "regels"}]: leveranciers op naam, zonder leverancier als laatste. Leeg als er
    niets te bestellen was. Commit."""
    aantallen = {int(pid): n for pid, n in besteleenheden_per_product.items() if n and n > 0}
    if not aantallen:
        return []
    groepen = {}
    for r in db.execute(
        f"""SELECT p.id, l.id AS leverancier_id, l.naam AS leverancier FROM producten p
            LEFT JOIN leveranciers l ON l.id = p.leverancier_id WHERE p.id IN ({','.join('?' * len(aantallen))})""",
        tuple(aantallen),
    ).fetchall():
        groepen.setdefault((r["leverancier_id"], r["leverancier"]), {})[r["id"]] = aantallen[r["id"]]
    uitkomst = []
    for (lev_id, naam), groep in sorted(groepen.items(), key=lambda g: (g[0][0] is None, (g[0][1] or "").lower())):
        bestelling_id, n = maak_bestelling(db, groep, door, door_id, leverancier_id=lev_id)
        if bestelling_id:
            uitkomst.append({"id": bestelling_id, "leverancier_id": lev_id, "leverancier": naam, "regels": n})
    return uitkomst


def klaargezet_melding(bestellingen):
    """'Bestelling #12 klaargezet bij Sligro (5 producten).' of, bij meer, 'Twee bestellingen klaargezet: ...'."""
    def een(b):
        bij = f"bij {b['leverancier']}" if b["leverancier"] else "zonder leverancier"
        return f"#{b['id']} {bij} ({b['regels']} {'product' if b['regels'] == 1 else 'producten'})"

    if len(bestellingen) == 1:
        return f"Bestelling {een(bestellingen[0])} klaargezet."
    return f"{len(bestellingen)} bestellingen klaargezet, een per leverancier: " + ", ".join(een(b) for b in bestellingen) + "."


def maak_bestelling(db, besteleenheden_per_product, door=None, door_id=None, leverancier_id=None):
    """besteleenheden_per_product: {product_id: aantal besteleenheden (2 kratten)}. Maakt de bestelling met de aantallen
    in de eenheid van het product. Geeft (bestelling_id, aantal regels), of (None, 0) als er niets te bestellen was.
    Commit."""
    aantallen = {int(pid): n for pid, n in besteleenheden_per_product.items() if n and n > 0}
    if not aantallen:
        return None, 0
    producten = {
        p["id"]: p
        for p in db.execute(
            f"SELECT * FROM producten WHERE id IN ({','.join('?' * len(aantallen))})", tuple(aantallen)
        ).fetchall()
    }
    regels = [(pid, naar_voorraadeenheden(n, producten[pid])) for pid, n in aantallen.items() if pid in producten]
    regels = [(pid, aantal) for pid, aantal in regels if aantal > 0]
    if not regels:
        return None, 0
    bestelling_id = db.execute(
        """INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, besteld_door_id, leverancier_id)
           VALUES ('besteld', ?, ?, ?, ?)""",
        (now_str(), door, door_id, leverancier_id),
    ).lastrowid
    for product_id, aantal in regels:
        db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, ?)",
                   (bestelling_id, product_id, aantal))
    manco.volg_op_bij_bestelling(db, [pid for pid, _ in regels])
    bestelvoorstel.wis_bij_bestelling(db, [pid for pid, _ in regels])
    db.commit()
    return bestelling_id, len(regels)


def bestelling_gegevens(db, bestelling_id):
    """{"bestelling", "leverancier" (of None), "regels": [{naam, artikelcode, eenheden, besteleenheid, stuks, eenheid}]}
    voor de lijst die naar de leverancier gaat; None als de bestelling niet bestaat."""
    bestelling = db.execute("SELECT * FROM bestellingen WHERE id = ?", (bestelling_id,)).fetchone()
    if bestelling is None:
        return None
    leverancier = None
    if bestelling["leverancier_id"]:
        leverancier = db.execute("SELECT * FROM leveranciers WHERE id = ?", (bestelling["leverancier_id"],)).fetchone()
    regels = []
    for r in db.execute(
        """SELECT br.aantal_besteld, p.naam, p.artikelcode, p.eenheid, p.besteleenheid, p.besteleenheid_factor
           FROM bestelregels br JOIN producten p ON p.id = br.product_id
           WHERE br.bestelling_id = ? AND br.aantal_besteld > 0 ORDER BY p.categorie, p.naam COLLATE NOCASE""",
        (bestelling_id,),
    ).fetchall():
        factor = besteleenheid_factor(r)
        regels.append({
            "naam": r["naam"],
            "artikelcode": r["artikelcode"],
            "eenheden": -(-r["aantal_besteld"] // factor),
            "besteleenheid": besteleenheid_naam(r) if factor > 1 else r["eenheid"],
            "stuks": r["aantal_besteld"],
            "eenheid": r["eenheid"],
            "factor": factor,
        })
    return {"bestelling": bestelling, "leverancier": leverancier, "regels": regels}


def bestel_tekst(gegevens):
    """De bestelling als tekst, om te plakken in een mail, WhatsApp of het bestelformulier van de leverancier."""
    lev = gegevens["leverancier"]
    kop = f"Bestelling {NAAM_CLUB}"
    if lev and lev["klantnummer"]:
        kop += f" (klantnummer {lev['klantnummer']})"
    regels = [
        f"- {r['eenheden']} {r['besteleenheid']} {r['naam']}"
        + (f" ({r['stuks']} {r['eenheid']})" if r["factor"] > 1 else "")
        + (f", art.nr. {r['artikelcode']}" if r["artikelcode"] else "")
        for r in gegevens["regels"]
    ]
    door = gegevens["bestelling"]["besteld_door"]
    return "\n".join([kop + ":", *regels, "", f"Met vriendelijke groet,\n{door}" if door else "Met vriendelijke groet"])
