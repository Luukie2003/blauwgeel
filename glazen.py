"""Een product dat per glas verkocht wordt: een fust (getapt) of een fles (shots, wijn). Bij het product staat hoeveel glazen
erin gaan en de prijs per glas; een fust of fles die bij een telling weg is, telt dan als zoveel glazen (zie
helpers.producten.omzet_per_eenheid).

Een fles die eerst zonder aantal glazen stond, telde in de oude tellingen voor de prijs van één glas: 7 flessen à € 3,50 in
plaats van 7 x 28 glazen. Elke tellingregel onthoudt zijn eigen prijs, dus die verandert niet vanzelf mee. te_corrigeren
zoekt die regels op en corrigeer rekent ze om: de prijs van toen (per glas) maal het aantal glazen van nu."""

from helpers.producten import is_fles_per_glas

__all__ = ["corrigeer", "is_fles_per_glas", "te_corrigeren"]

PER_GLAS_FACTOR = 1.5  # een prijs tot anderhalf keer die van een glas is de prijs van één glas, niet van de hele fles


def te_corrigeren(db, product):
    """De tellingregels van een fles per glas waarin iets verkocht is voor de prijs van één glas (of zonder prijs), de
    nieuwste eerst: [{"id", "telling_id", "datum", "verkocht", "oud" (prijs), "nieuw", "erbij" (omzet)}]."""
    if not is_fles_per_glas(product) or product["glazen_per_fust"] < 2 or product["prijs_per_glas"] <= 0:
        return []
    uit = []
    for r in db.execute(
        """SELECT tr.id, tr.telling_id, t.datum, tr.verkocht, COALESCE(tr.verkoopprijs, 0) AS prijs
           FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
           WHERE tr.product_id = ? AND tr.verkocht > 0 ORDER BY t.datum DESC, t.id DESC""",
        (product["id"],),
    ).fetchall():
        if r["prijs"] > product["prijs_per_glas"] * PER_GLAS_FACTOR:
            continue  # dit is al de opbrengst van een hele fles
        nieuw = round((r["prijs"] or product["prijs_per_glas"]) * product["glazen_per_fust"], 2)
        uit.append({"id": r["id"], "telling_id": r["telling_id"], "datum": r["datum"], "verkocht": r["verkocht"],
                    "oud": r["prijs"], "nieuw": nieuw, "erbij": round(r["verkocht"] * (nieuw - r["prijs"]), 2)})
    return uit


def corrigeer(db, product):
    """Rekent die regels om. Geeft (aantal regels, omzet erbij). Nog een keer uitvoeren doet niets meer."""
    regels = te_corrigeren(db, product)
    for r in regels:
        db.execute("UPDATE telling_regels SET verkoopprijs = ? WHERE id = ?", (r["nieuw"], r["id"]))
    db.commit()
    return len(regels), round(sum(r["erbij"] for r in regels), 2)
