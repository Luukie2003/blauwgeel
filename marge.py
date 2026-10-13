"""Marge-overzicht: wat levert elk product en elke categorie op, en welke producten verdienen het minst.

De omzet komt uit de tellingen (met de verkoopprijs van het moment van tellen). De winst is een schatting: omzet min
het aantal verkochte stuks maal de huidige inkoopprijs, want per telling wordt alleen de verkoopprijs vastgelegd. De
inkoopprijs staat bij een product per besteleenheid (bijvoorbeeld een krat van 24) en wordt hier door het aantal stuks per
besteleenheid gedeeld, want de verkoopprijs is per stuk. Een product zonder inkoopprijs telt niet mee in de marge en staat
apart genoemd."""

from datetime import timedelta

from helpers.producten import inkoop_per_stuk, omzet_per_eenheid

WEKEN_KEUZES = (4, 8, 13, 26, 52)
STANDAARD_WEKEN = 13
LAGE_MARGE_PCT = 30  # onder dit percentage valt een product op


def lees_doelmarge(db):
    """De doelmarge (in %) uit de instellingen: daaronder stelt het rapport Marge een nieuwe prijs voor."""
    rij = db.execute("SELECT doelmarge_pct FROM instellingen WHERE id = 1").fetchone()
    return rij[0] if rij and rij[0] else LAGE_MARGE_PCT


def bewaar_doelmarge(db, pct):
    db.execute("UPDATE instellingen SET doelmarge_pct = ? WHERE id = 1", (max(5, min(90, int(pct))),))
    db.commit()


def _naar_boven_op_tien_cent(bedrag):
    return -(-round(bedrag * 100) // 10) / 10


def prijsadvies(p, doel_pct):
    """(veld op Prijzen aanpassen, voorgestelde prijs) om op 'doel_pct' marge uit te komen, naar boven afgerond op
    10 cent; None als dat niet kan of al zo is. Bij een fust gaat het om de prijs per glas."""
    if not p["heeft_inkoop"] or p["marge_pct"] is None or p["marge_pct"] >= doel_pct:
        return None
    if p.get("glazen_per_fust"):
        prijs = _naar_boven_op_tien_cent(p["inkoop_stuk"] / p["glazen_per_fust"] / (1 - doel_pct / 100))
        return (f"glas_{p['id']}", prijs) if prijs > (p.get("prijs_per_glas") or 0) else None
    prijs = _naar_boven_op_tien_cent(p["inkoop_stuk"] / (1 - doel_pct / 100))
    return (f"prijs_{p['id']}", prijs) if prijs > p["verkoopprijs"] else None


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
                  p.glazen_per_fust, p.prijs_per_glas,
                  COALESCE(SUM(tr.verkocht), 0) AS aantal,
                  COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
           FROM producten p
           LEFT JOIN (SELECT r.product_id, r.verkocht, r.verkoopprijs
                      FROM telling_regels r JOIN tellingen t ON t.id = r.telling_id WHERE t.datum >= ?
                      UNION ALL  -- de keuken telt apart (zie keukenbeheer.py)
                      SELECT k.product_id, k.verkocht, k.verkoopprijs
                      FROM keuken_telling_regels k JOIN keuken_tellingen kt ON kt.id = k.telling_id WHERE kt.datum >= ?) tr
                  ON tr.product_id = p.id
           GROUP BY p.id
           ORDER BY p.categorie, p.naam COLLATE NOCASE""",
        (vanaf, vanaf),
    ).fetchall()
    producten = []
    for r in rijen:
        verkoopprijs = omzet_per_eenheid(r)  # bij een fust: glazen maal de prijs per glas
        if verkoopprijs <= 0 and r["omzet"] <= 0:
            continue  # wordt niet los verkocht en levert niets op: hier niets over te zeggen
        heeft_inkoop = r["inkoopprijs"] > 0
        inkoop_stuk = inkoop_per_stuk(r)
        marge_stuk = verkoopprijs - inkoop_stuk if heeft_inkoop and verkoopprijs > 0 else None
        producten.append(
            {
                "id": r["id"], "naam": r["naam"], "categorie": r["categorie"], "eenheid": r["eenheid"], "actief": bool(r["actief"]),
                "verkoopprijs": verkoopprijs, "inkoopprijs": r["inkoopprijs"], "inkoop_stuk": inkoop_stuk,
                "glazen_per_fust": r["glazen_per_fust"], "prijs_per_glas": r["prijs_per_glas"],
                "aantal": r["aantal"], "omzet": r["omzet"],
                "heeft_inkoop": heeft_inkoop,
                "marge_stuk": marge_stuk,
                "marge_pct": marge_stuk / verkoopprijs * 100 if marge_stuk is not None else None,
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


VERLIES_GLAZEN = (0, 3, 6)  # hoeveel glazen per fust verloren gaan aan schuim, spoelen en proeven


def bereken_tap(db):
    """Per fust (glazen per fust ingevuld): wat een glas kost en oplevert, wat er per fust overblijft als er wat
    verloren gaat aan schuim en spoelen, na hoeveel glazen het fust is terugverdiend, en de kostprijs van een
    prijsoptie (bijv. een pitcher) waarbij is ingevuld hoeveel glazen erin gaan."""
    fusten = db.execute(
        """SELECT * FROM producten WHERE glazen_per_fust > 0 AND inkoopprijs > 0
           ORDER BY actief DESC, naam COLLATE NOCASE"""
    ).fetchall()
    uitkomst = []
    for f in fusten:
        inkoop_fust = inkoop_per_stuk(f)  # een fust is zelf de eenheid
        glas = inkoop_fust / f["glazen_per_fust"]
        prijs = f["prijs_per_glas"]
        opties = [
            {
                "naam": o["naam"],
                "prijs": o["prijs"],
                "glazen": o["glazen"],
                "kostprijs": o["glazen"] * glas,
                "marge_pct": (o["prijs"] - o["glazen"] * glas) / o["prijs"] * 100 if o["prijs"] > 0 else None,
            }
            for o in db.execute(
                "SELECT * FROM product_prijsopties WHERE product_id = ? AND glazen > 0 ORDER BY volgorde, id", (f["id"],)
            ).fetchall()
        ]
        uitkomst.append(
            {
                "id": f["id"],
                "naam": f["naam"],
                "actief": bool(f["actief"]),
                "inkoop_fust": inkoop_fust,
                "glazen": f["glazen_per_fust"],
                "kostprijs_glas": glas,
                "prijs_glas": prijs,
                "marge_glas_pct": (prijs - glas) / prijs * 100 if prijs > 0 else None,
                "terugverdiend_na": -(-inkoop_fust // prijs) if prijs > 0 else None,
                "verlies": [
                    {"glazen": v, "winst": (f["glazen_per_fust"] - v) * prijs - inkoop_fust}
                    for v in VERLIES_GLAZEN
                    if v < f["glazen_per_fust"]
                ],
                "opties": opties,
            }
        )
    return uitkomst
