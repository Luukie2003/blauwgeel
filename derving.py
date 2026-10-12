"""Derving: wat er uit de voorraad verdwijnt zonder dat het verkocht is (breuk, over de datum, gratis weggegeven).

Bij het uitboeken kies je een reden; hier komt alles bij elkaar, met de waarde tegen inkoopprijs."""

from datetime import timedelta

DERVING_REDENEN = {
    "breuk": "Breuk of gemorst",
    "over_datum": "Over de datum of bedorven",
    "weggegeven": "Gratis weggegeven (proeverij, sponsor, bestuur)",
    "eigen_gebruik": "Eigen gebruik van vrijwilligers",
    "overig": "Anders",
}


def kies_reden(waarde):
    """Een geldige reden uit het formulier, anders None (gewoon uitboeken, geen derving)."""
    return waarde if waarde in DERVING_REDENEN else None


def bereken_derving(db, weken, vandaag):
    """{'per_reden', 'per_product', 'recent', 'totaal', 'vanaf'} over de laatste 'weken' weken (vandaag: een date)."""
    vanaf = (vandaag - timedelta(weeks=weken)).strftime("%Y-%m-%d 00:00")
    rijen = db.execute(
        """SELECT m.id, m.datum, m.aantal, m.naam, m.opmerking, m.reden, m.product_id,
                  p.naam AS product_naam, p.eenheid, p.inkoopprijs
           FROM mutaties m JOIN producten p ON p.id = m.product_id
           WHERE m.type = 'uit' AND m.reden IS NOT NULL AND m.reden != '' AND m.datum >= ?
           ORDER BY m.datum DESC, m.id DESC""",
        (vanaf,),
    ).fetchall()
    per_reden = {sleutel: {"naam": naam, "boekingen": 0, "stuks": 0, "waarde": 0.0} for sleutel, naam in DERVING_REDENEN.items()}
    per_product = {}
    for r in rijen:
        waarde = r["aantal"] * r["inkoopprijs"]
        reden = per_reden.get(r["reden"])
        if reden is None:
            continue  # een onbekende reden (bijvoorbeeld uit een oudere versie): niet meetellen
        reden["boekingen"] += 1
        reden["stuks"] += r["aantal"]
        reden["waarde"] += waarde
        p = per_product.setdefault(
            r["product_id"], {"naam": r["product_naam"], "eenheid": r["eenheid"], "boekingen": 0, "stuks": 0, "waarde": 0.0}
        )
        p["boekingen"] += 1
        p["stuks"] += r["aantal"]
        p["waarde"] += waarde
    return {
        "vanaf": vanaf[:10],
        "per_reden": [r for r in per_reden.values() if r["boekingen"]],
        "per_product": sorted(per_product.values(), key=lambda p: (-p["waarde"], p["naam"].lower())),
        "recent": [dict(r, reden_naam=DERVING_REDENEN.get(r["reden"], r["reden"])) for r in rijen[:40]],
        "totaal": {
            "boekingen": sum(r["boekingen"] for r in per_reden.values()),
            "waarde": sum(r["waarde"] for r in per_reden.values()),
        },
    }
