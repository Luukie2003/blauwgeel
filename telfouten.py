"""Waar we vaak mis tellen (2.26.0, bij Voorraad > Tellingen): per product hoe vaak er bij een telling meer stond dan de app
verwachtte, en welke producten waarschijnlijk door elkaar zijn geteld (verwisseld.py).

Meer dan verwacht is altijd een fout: een eerdere telfout (het product is toen te laag geteld en dus als verkocht geboekt),
een levering die niet is ingeboekt, of een verwisselde smaak. De eerste keer dat een product geteld wordt, telt niet mee:
dan is alles nieuw. De keuken telt apart en doet niet mee."""

from datetime import timedelta

import verwisseld
from productkaart import KEUKEN_CATEGORIE

WEKEN_KEUZES = (4, 8, 13, 26)
STANDAARD_WEKEN = 13


def kies_weken(waarde):
    try:
        weken = int(waarde)
    except (TypeError, ValueError):
        return STANDAARD_WEKEN
    return weken if weken in WEKEN_KEUZES else STANDAARD_WEKEN


def bereken(db, weken, vandaag):
    """{"vanaf", "tellingen", "regels", "te_veel", "stuks", "waarde", "producten": [...], "paren": [...]}."""
    vanaf = (vandaag - timedelta(weeks=weken)).strftime("%Y-%m-%d 00:00")
    per_product = {}
    regels = te_veel = 0
    for r in db.execute(
        """SELECT tr.product_id, tr.correctie, tr.verkoopprijs, p.naam, p.categorie, p.eenheid,
                  EXISTS (SELECT 1 FROM telling_regels r2 JOIN tellingen t2 ON t2.id = r2.telling_id
                          WHERE r2.product_id = tr.product_id AND t2.datum < t.datum) AS eerder
           FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id JOIN producten p ON p.id = tr.product_id
           WHERE t.datum >= ? AND p.categorie != ?""",
        (vanaf, KEUKEN_CATEGORIE),
    ).fetchall():
        if not r["eerder"]:
            continue
        regels += 1
        p = per_product.setdefault(r["product_id"], {"id": r["product_id"], "naam": r["naam"], "categorie": r["categorie"],
                                                     "eenheid": r["eenheid"], "keer": 0, "fout": 0, "stuks": 0, "waarde": 0.0})
        p["keer"] += 1
        if r["correctie"] > 0:
            te_veel += 1
            p["fout"] += 1
            p["stuks"] += r["correctie"]
            p["waarde"] += r["correctie"] * (r["verkoopprijs"] or 0)
    producten = sorted((p for p in per_product.values() if p["fout"]), key=lambda p: (-p["fout"], -p["stuks"], p["naam"].lower()))
    for p in producten:
        p["pct"] = p["fout"] / p["keer"] * 100

    paren = {}
    tellingen = db.execute("SELECT * FROM tellingen WHERE datum >= ? ORDER BY datum", (vanaf,)).fetchall()
    for t in tellingen:
        for paar in verwisseld.bij_telling(db, t):
            sleutel = tuple(sorted((paar["meer"]["naam"], paar["minder"]["naam"])))
            v = paren.setdefault(sleutel, {"namen": sleutel, "keer": 0, "stuks": 0, "laatst": None})
            v["keer"] += 1
            v["stuks"] += paar["aantal"]
            v["laatst"] = {"id": t["id"], "datum": t["datum"]}
    return {
        "vanaf": vanaf[:10], "tellingen": len(tellingen), "regels": regels, "te_veel": te_veel,
        "pct": te_veel / regels * 100 if regels else None,
        "stuks": sum(p["stuks"] for p in producten), "waarde": sum(p["waarde"] for p in producten),
        "producten": producten, "paren": sorted(paren.values(), key=lambda v: (-v["keer"], -v["stuks"])),
    }

