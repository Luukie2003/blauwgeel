"""Een telling verwerken: voorraad bijwerken, verkoop berekenen en afwijkingen signaleren."""

from flask import flash

from helpers import verwerk_auto_inactief


def signaleer_afwijkende_telling(db, product_id, voorraad_voor, geteld, limiet=8):
    """Vergelijkt de mutatie (verkocht + correctie) van een nieuwe telling
    met het gemiddelde van de laatste tellingen van dit product, om een
    tikfout te kunnen signaleren voordat de telling wordt opgeslagen.
    Retourneert None als er te weinig geschiedenis is om iets zinnigs
    over te zeggen."""
    vorige = db.execute(
        """SELECT verkocht, correctie FROM telling_regels
           WHERE product_id = ? ORDER BY telling_id DESC LIMIT ?""",
        (product_id, limiet),
    ).fetchall()
    if len(vorige) < 3:
        return None
    gemiddelde = sum(r["verkocht"] + r["correctie"] for r in vorige) / len(vorige)
    mutatie_nu = abs(geteld - voorraad_voor)
    if mutatie_nu <= max(gemiddelde * 3, 6):
        return None
    return {"gemiddelde": gemiddelde, "mutatie_nu": mutatie_nu}


def verwerk_telling(db, waarden, naam, opmerking, datum, gebruiker_id=None):
    """waarden: dict {product_id: geteld_aantal}. Maakt een telling aan,
    berekent per product het verschil met de huidige voorraad, en werkt
    voorraad + geschiedenis bij. Retourneert het nieuwe telling_id, of
    None als er niets te verwerken viel."""
    if not waarden:
        return None

    cur = db.execute(
        "INSERT INTO tellingen (datum, naam, gebruiker_id, opmerking) VALUES (?, ?, ?, ?)",
        (datum, naam, gebruiker_id, opmerking),
    )
    telling_id = cur.lastrowid

    # Alle geteld producten in 1 keer ophalen i.p.v. per product een losse
    # SELECT (was een N+1: bij een volledige telling van bijv. 150
    # producten scheelt dit ~150 queries).
    plekhouders = ",".join("?" * len(waarden))
    producten_bij_id = {
        p["id"]: p
        for p in db.execute(
            f"SELECT * FROM producten WHERE id IN ({plekhouders})", tuple(waarden.keys())
        ).fetchall()
    }

    for product_id, geteld in waarden.items():
        product = producten_bij_id.get(product_id)
        if product is None:
            continue
        verschil = geteld - product["voorraad"]
        verkocht = max(0, -verschil)
        correctie = max(0, verschil)

        db.execute(
            """INSERT INTO telling_regels
               (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht,
                correctie, verkoopprijs)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                telling_id,
                product_id,
                product["voorraad"],
                geteld,
                verkocht,
                correctie,
                product["verkoopprijs"],
            ),
        )
        db.execute(
            "UPDATE producten SET voorraad = ? WHERE id = ?", (geteld, product_id)
        )
        gedeactiveerd = verwerk_auto_inactief(db, product_id, geteld)
        if gedeactiveerd:
            flash(f"'{gedeactiveerd}' is automatisch op inactief gezet (voorraad op 0).", "warning")
        if verkocht > 0:
            db.execute(
                """INSERT INTO mutaties
                   (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                   VALUES (?, 'uit', ?, ?, ?, ?, ?, ?)""",
                (product_id, verkocht, datum, naam, gebruiker_id, f"Verkocht (telling #{telling_id})", telling_id),
            )
        elif correctie > 0:
            db.execute(
                """INSERT INTO mutaties
                   (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                   VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                (product_id, correctie, datum, naam, gebruiker_id, f"Correctie (telling #{telling_id})", telling_id),
            )

    db.commit()
    return telling_id
