"""Een bestelling klaarzetten: op de site (Bestellijst > Voorgesteld om te bestellen) en in de handterminal-app. Een
klaargezette bestelling is het concept van de factuur (zie facturen.py); wat er bij een vorige bestelling niet geleverd
was, is met deze bestelling opgevolgd (zie manco.py)."""

import manco
from helpers.producten import naar_voorraadeenheden
from helpers.tijd import now_str


def maak_bestelling(db, besteleenheden_per_product, door=None, door_id=None):
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
        "INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, besteld_door_id) VALUES ('besteld', ?, ?, ?)",
        (now_str(), door, door_id),
    ).lastrowid
    for product_id, aantal in regels:
        db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, ?)",
                   (bestelling_id, product_id, aantal))
    manco.volg_op_bij_bestelling(db, [pid for pid, _ in regels])
    db.commit()
    return bestelling_id, len(regels)
