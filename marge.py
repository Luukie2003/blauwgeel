"""Marge-overzicht: wat levert elk product en elke categorie op, en welke producten verdienen het minst.

De omzet komt uit de tellingen (met de verkoopprijs van het moment van tellen). De winst is een schatting: omzet min
het aantal verkochte stuks maal de huidige inkoopprijs, want per telling wordt alleen de verkoopprijs vastgelegd. De
inkoopprijs staat bij een product per besteleenheid (bijvoorbeeld een krat van 24) en wordt hier door het aantal stuks per
besteleenheid gedeeld, want de verkoopprijs is per stuk. Een product zonder inkoopprijs telt niet mee in de marge en staat
apart genoemd."""

from datetime import timedelta

WEKEN_KEUZES = (4, 8, 13, 26, 52)
STANDAARD_WEKEN = 13
LAGE_MARGE_PCT = 30  # onder dit percentage valt een product op


def kies_weken(waarde):
    try:
        weken = int(waarde)
    except (TypeError, ValueError):
        return STANDAARD_WEKEN
    return weken if weken in WEKEN_KEUZES else STANDAARD_WEKEN


def bereken_marge(db, weken, vandaag):
    """{'producten', 'laagste', 'zonder_inkoop', 'beste', 'categorieen', 'totaal', 'vanaf'} over de laatste 'weken'
    weken (vandaag: een date)."""
    vanaf = (vandaag - timedelta(weeks=weken)).strftime("%Y-%m-%d 00:00")
    rijen = db.execute(
        """SELECT p.id, p.naam, p.categorie, p.eenheid, p.verkoopprijs, p.inkoopprijs, p.besteleenheid_factor, p.actief,
                  COALESCE(SUM(tr.verkocht), 0) AS aantal,
                  COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
           FROM producten p
           LEFT JOIN (SELECT r.* FROM telling_regels r JOIN tellingen t ON t.id = r.telling_id WHERE t.datum >= ?) tr
                  ON tr.product_id = p.id
           GROUP BY p.id
           ORDER BY p.categorie, p.naam COLLATE NOCASE""",
        (vanaf,),
    ).fetchall()
    producten = []
    for r in rijen:
        if r["verkoopprijs"] <= 0 and r["omzet"] <= 0:
            continue  # wordt niet los verkocht (bijvoorbeeld een fust): hier niets over te zeggen
        heeft_inkoop = r["inkoopprijs"] > 0
        inkoop_stuk = r["inkoopprijs"] / max(1, r["besteleenheid_factor"] or 1)  # de inkoopprijs is per besteleenheid
        marge_stuk = r["verkoopprijs"] - inkoop_stuk if heeft_inkoop and r["verkoopprijs"] > 0 else None
        producten.append(
            {
                "id": r["id"], "naam": r["naam"], "categorie": r["categorie"], "eenheid": r["eenheid"], "actief": bool(r["actief"]),
                "verkoopprijs": r["verkoopprijs"], "inkoopprijs": r["inkoopprijs"], "inkoop_stuk": inkoop_stuk,
                "aantal": r["aantal"], "omzet": r["omzet"],
                "heeft_inkoop": heeft_inkoop,
                "marge_stuk": marge_stuk,
                "marge_pct": marge_stuk / r["verkoopprijs"] * 100 if marge_stuk is not None else None,
                "winst": r["omzet"] - r["aantal"] * inkoop_stuk if heeft_inkoop else None,
            }
        )
    met_marge = [p for p in producten if p["marge_pct"] is not None]
    categorieen = {}
    for p in producten:
        c = categorieen.setdefault(p["categorie"], {"naam": p["categorie"], "omzet": 0.0, "omzet_met_inkoop": 0.0, "winst": 0.0})
        c["omzet"] += p["omzet"]
        if p["heeft_inkoop"]:
            c["omzet_met_inkoop"] += p["omzet"]
            c["winst"] += p["winst"]
    for c in categorieen.values():
        c["marge_pct"] = c["winst"] / c["omzet_met_inkoop"] * 100 if c["omzet_met_inkoop"] > 0 else None
    omzet = sum(p["omzet"] for p in producten)
    omzet_met_inkoop = sum(p["omzet"] for p in producten if p["heeft_inkoop"])
    winst = sum(p["winst"] for p in producten if p["heeft_inkoop"])
    return {
        "vanaf": vanaf[:10],
        "producten": producten,
        "laagste": sorted(met_marge, key=lambda p: (p["marge_pct"], p["naam"].lower()))[:15],
        "zonder_inkoop": sorted(
            (p for p in producten if not p["heeft_inkoop"] and p["verkoopprijs"] > 0), key=lambda p: -p["omzet"]
        ),
        "beste": sorted((p for p in producten if p["heeft_inkoop"] and p["aantal"] > 0), key=lambda p: -p["winst"])[:10],
        "categorieen": sorted((c for c in categorieen.values() if c["omzet"] > 0), key=lambda c: -c["omzet"]),  # alleen wat verkocht is
        "totaal": {
            "omzet": omzet,
            "winst": winst,
            "marge_pct": winst / omzet_met_inkoop * 100 if omzet_met_inkoop > 0 else None,
            "dekking_pct": omzet_met_inkoop / omzet * 100 if omzet > 0 else None,
        },
    }
