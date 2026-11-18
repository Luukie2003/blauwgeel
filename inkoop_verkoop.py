"""Inkoop en verkoop: wat er in een periode is ingekocht, wat ervan verkocht is, wat het opleverde, wat er blijft liggen
en of de leveringen klopten met de bestellingen.

Inkoop is alles wat buiten een telling om is bijgeboekt (een ontvangen bestelling, een ingeboekte factuur, een losse
levering), behalve correcties (een opmerking met 'correctie' of 'gecorrigeerd'), min wat als retour is uitgeboekt. De
waarde is tegen de huidige inkoopprijs per stuk (zie inkoop_per_stuk). Verkocht en omzet komen uit de gewone tellingen,
met de verkoopprijs van het moment van tellen (zoals bij Marge). De keuken telt apart en doet hier niet mee, net als
producten met 'Niet tellen'.

'Verkocht' is wat er bij het tellen weg was, dus ook breuk of gratis drankjes die niet als derving zijn geboekt. Een
telverschil is een telling waarbij er meer stond dan de app verwachtte (een eerdere telfout of een levering die niet is
ingeboekt); de eerste keer dat een product wordt geteld, telt niet als telverschil."""

from datetime import datetime, timedelta

from helpers.producten import inkoop_per_stuk
from productkaart import KEUKEN_CATEGORIE

WEKEN_KEUZES = (4, 8, 13, 26, 52)
STANDAARD_WEKEN = 13
LANG_WEKEN = 6  # vanaf zoveel weken voorraad valt een product op
CORRECTIE_WOORDEN = ("correctie", "gecorrigeerd")
MAANDNAMEN = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def kies_weken(waarde):
    try:
        weken = int(waarde)
    except (TypeError, ValueError):
        return STANDAARD_WEKEN
    return weken if weken in WEKEN_KEUZES else STANDAARD_WEKEN


def is_correctie(opmerking):
    """Een bijboeking met deze opmerking is geen inkoop maar een correctie van de voorraad."""
    tekst = (opmerking or "").lower()
    return any(woord in tekst for woord in CORRECTIE_WOORDEN)


def is_retour(opmerking):
    """Een uitboeking met deze opmerking ging terug naar de leverancier: die telt van de inkoop af."""
    return "retour" in (opmerking or "").lower()


def _weken_tussen(van, tot):
    return (datetime.fromisoformat(tot) - datetime.fromisoformat(van)).total_seconds() / 86400 / 7


def _verkoopweken(db, vanaf):
    """Over hoeveel weken de verkoop in de periode loopt. De eerste telling in de periode telt de verkoop sinds de telling
    ervoor, dus vanaf die telling; is er geen eerdere, dan vanaf de eerste in de periode. None als dat minder dan een
    week is (dan zegt een weekgemiddelde nog niets)."""
    laatste = db.execute("SELECT MAX(datum) FROM tellingen WHERE datum >= ?", (vanaf,)).fetchone()[0]
    begin = db.execute("SELECT MAX(datum) FROM tellingen WHERE datum < ?", (vanaf,)).fetchone()[0] or db.execute(
        "SELECT MIN(datum) FROM tellingen WHERE datum >= ?", (vanaf,)
    ).fetchone()[0]
    if not laatste or not begin:
        return None, laatste
    weken = _weken_tussen(begin, laatste)
    return (weken if weken >= 1 else None), laatste


def _maandlabel(sleutel):
    jaar, maand = sleutel.split("-")
    return f"{MAANDNAMEN[int(maand) - 1]} {jaar}"


def _leeg_product():
    return {"inkoop": 0, "correctie": 0, "verkocht": 0, "omzet": 0.0, "telverschil": 0, "telverschil_waarde": 0.0}


def bereken_inkoop_verkoop(db, weken, vandaag):
    """Het rapport over de laatste 'weken' weken (vandaag: een date). Zie de uitleg bovenaan."""
    vanaf = (vandaag - timedelta(weeks=weken)).strftime("%Y-%m-%d 00:00")
    alle_producten = {p["id"]: dict(p) for p in db.execute("SELECT * FROM producten").fetchall()}
    meetellen = {
        pid for pid, p in alle_producten.items() if p["categorie"] != KEUKEN_CATEGORIE and not p.get("niet_tellen")
    }
    per = {pid: _leeg_product() for pid in meetellen}
    maanden = {}

    def maand(datum):
        return maanden.setdefault(datum[:7], {"inkoop": 0.0, "verkocht": 0.0, "omzet": 0.0})

    for m in db.execute(
        """SELECT product_id, type, aantal, datum, opmerking, bestelling_id FROM mutaties
           WHERE telling_id IS NULL AND datum >= ?""",
        (vanaf,),
    ).fetchall():
        if m["product_id"] not in per:
            continue
        d = per[m["product_id"]]
        waarde = m["aantal"] * inkoop_per_stuk(alle_producten[m["product_id"]])
        if m["type"] == "in":
            if m["bestelling_id"] is None and is_correctie(m["opmerking"]):
                d["correctie"] += m["aantal"]
                continue
            d["inkoop"] += m["aantal"]
            maand(m["datum"])["inkoop"] += waarde
        elif is_retour(m["opmerking"]):
            d["inkoop"] -= m["aantal"]
            maand(m["datum"])["inkoop"] -= waarde

    for r in db.execute(
        """SELECT r.product_id, r.verkocht, r.verkoopprijs, r.correctie, t.datum,
                  EXISTS (SELECT 1 FROM telling_regels r2 JOIN tellingen t2 ON t2.id = r2.telling_id
                          WHERE r2.product_id = r.product_id AND t2.datum < t.datum) AS eerder_geteld
           FROM telling_regels r JOIN tellingen t ON t.id = r.telling_id
           WHERE t.datum >= ?""",
        (vanaf,),
    ).fetchall():
        if r["product_id"] not in per:
            continue
        d = per[r["product_id"]]
        d["verkocht"] += r["verkocht"]
        d["omzet"] += r["verkocht"] * r["verkoopprijs"]
        if r["eerder_geteld"] and r["correctie"] > 0:
            d["telverschil"] += r["correctie"]
            d["telverschil_waarde"] += r["correctie"] * r["verkoopprijs"]
        m = maand(r["datum"])
        m["verkocht"] += r["verkocht"] * inkoop_per_stuk(alle_producten[r["product_id"]])
        m["omzet"] += r["verkocht"] * r["verkoopprijs"]

    onderweg = {
        r["product_id"]: r["aantal"]
        for r in db.execute(
            """SELECT r.product_id, SUM(r.aantal_besteld) AS aantal FROM bestelregels r
               JOIN bestellingen b ON b.id = r.bestelling_id WHERE b.status != 'ontvangen' GROUP BY r.product_id"""
        ).fetchall()
    }

    verkoopweken, laatste_telling = _verkoopweken(db, vanaf)
    producten = []
    for pid in meetellen:
        p, d = alle_producten[pid], per[pid]
        if not (d["inkoop"] or d["verkocht"] or p["voorraad"] > 0 or onderweg.get(pid)):
            continue
        ink = inkoop_per_stuk(p)
        heeft_inkoop = ink > 0
        kostprijs = d["verkocht"] * ink
        winst = d["omzet"] - kostprijs if heeft_inkoop else None
        per_week = d["verkocht"] / verkoopweken if verkoopweken else None
        voorraad = max(0, p["voorraad"])
        komt = onderweg.get(pid, 0)
        producten.append(
            {
                "id": pid, "naam": p["naam"], "categorie": p["categorie"], "eenheid": p["eenheid"], "actief": bool(p["actief"]),
                "heeft_inkoop": heeft_inkoop, "inkoop_stuk": ink, **d,
                "inkoop_waarde": d["inkoop"] * ink, "kostprijs": kostprijs, "winst": winst,
                "marge_pct": winst / d["omzet"] * 100 if winst is not None and d["omzet"] > 0 else None,
                "voorraad": voorraad, "voorraad_waarde": voorraad * ink, "onderweg": komt,
                "per_week": per_week,
                "weken_voorraad": voorraad / per_week if per_week else None,
                "weken_na_levering": (voorraad + komt) / per_week if per_week and komt else None,
            }
        )
    producten.sort(key=lambda r: (-r["omzet"], r["naam"].lower()))

    categorieen = {}
    for r in producten:
        c = categorieen.setdefault(
            r["categorie"], {"naam": r["categorie"], "inkoop": 0.0, "omzet": 0.0, "omzet_met_inkoop": 0.0, "winst": 0.0, "voorraad": 0.0}
        )
        c["inkoop"] += r["inkoop_waarde"]
        c["omzet"] += r["omzet"]
        c["voorraad"] += r["voorraad_waarde"]
        if r["heeft_inkoop"]:
            c["omzet_met_inkoop"] += r["omzet"]
            c["winst"] += r["winst"]
    for c in categorieen.values():
        c["marge_pct"] = c["winst"] / c["omzet_met_inkoop"] * 100 if c["omzet_met_inkoop"] > 0 else None

    omzet = sum(r["omzet"] for r in producten)
    omzet_met_inkoop = sum(r["omzet"] for r in producten if r["heeft_inkoop"])
    inkoop = sum(r["inkoop_waarde"] for r in producten)
    kostprijs = sum(r["kostprijs"] for r in producten if r["heeft_inkoop"])
    winst = sum(r["winst"] for r in producten if r["heeft_inkoop"])
    telverschillen = sorted((r for r in producten if r["telverschil"] > 0), key=lambda r: (-r["telverschil"], r["naam"].lower()))

    return {
        "vanaf": vanaf[:10],
        "laatste_telling": laatste_telling,
        "verkoopweken": verkoopweken,
        "lang_weken": LANG_WEKEN,
        "totaal": {
            "inkoop": inkoop,
            "inkoop_stuks": sum(r["inkoop"] for r in producten),
            "omzet": omzet,
            "verkocht": sum(r["verkocht"] for r in producten),
            "kostprijs": kostprijs,
            "winst": winst,
            "marge_pct": winst / omzet_met_inkoop * 100 if omzet_met_inkoop > 0 else None,
            "omzet_per_euro": omzet / inkoop if inkoop > 0 else None,
            "groei": inkoop - kostprijs,
            "voorraad": sum(r["voorraad_waarde"] for r in producten),
            "telverschil": sum(r["telverschil"] for r in producten),
            "telverschil_waarde": sum(r["telverschil_waarde"] for r in producten),
        },
        "per_maand": [
            {"maand": sleutel, "label": _maandlabel(sleutel), **waarden, "verschil": waarden["inkoop"] - waarden["verkocht"]}
            for sleutel, waarden in sorted(maanden.items())
        ],
        "categorieen": sorted((c for c in categorieen.values() if c["omzet"] or c["inkoop"]), key=lambda c: -c["omzet"]),
        "producten": producten,
        "lang_liggen": sorted(
            (r for r in producten if r["actief"] and r["voorraad"] > 0 and r["weken_voorraad"] is not None and r["weken_voorraad"] >= LANG_WEKEN),
            key=lambda r: (-r["voorraad_waarde"], r["naam"].lower()),
        ),
        "na_levering": sorted(
            (r for r in producten if r["weken_na_levering"] is not None and r["weken_na_levering"] >= LANG_WEKEN),
            key=lambda r: -r["weken_na_levering"],
        ),
        "niet_verkocht": sum(1 for r in producten if r["actief"] and r["voorraad"] > 0 and r["verkocht"] == 0),
        "telverschillen": telverschillen[:10],
        "leveringen": bereken_leveringen(db, vanaf, alle_producten),
    }


def bereken_leveringen(db, vanaf, alle_producten):
    """Per bestelling die sinds 'vanaf' is binnengekomen: wat er besteld was tegen wat er geleverd is (aantallen en
    waarde tegen inkoopprijs), met de regels die afwijken."""
    bestellingen = []
    for b in db.execute(
        "SELECT * FROM bestellingen WHERE status = 'ontvangen' AND ontvangen_op >= ? ORDER BY ontvangen_op DESC, id DESC", (vanaf,)
    ).fetchall():
        regels = db.execute("SELECT * FROM bestelregels WHERE bestelling_id = ?", (b["id"],)).fetchall()
        afwijkend, besteld, geleverd = [], 0.0, 0.0
        for r in regels:
            ink = inkoop_per_stuk(alle_producten[r["product_id"]])
            ontvangen = r["aantal_ontvangen"] if r["aantal_ontvangen"] is not None else r["aantal_besteld"]
            besteld += r["aantal_besteld"] * ink
            geleverd += ontvangen * ink
            if ontvangen != r["aantal_besteld"]:
                afwijkend.append(
                    {"naam": alle_producten[r["product_id"]]["naam"], "besteld": r["aantal_besteld"], "geleverd": ontvangen,
                     "verschil": ontvangen - r["aantal_besteld"]}
                )
        bestellingen.append(
            {"id": b["id"], "aangemaakt_op": b["aangemaakt_op"], "ontvangen_op": b["ontvangen_op"], "referentie": b["referentie"],
             "regels": len(regels), "regels_goed": len(regels) - len(afwijkend), "besteld": besteld, "geleverd": geleverd,
             "afwijkend": sorted(afwijkend, key=lambda a: -abs(a["verschil"]))}
        )
    regels = sum(b["regels"] for b in bestellingen)
    return {
        "bestellingen": bestellingen,
        "regels": regels,
        "regels_goed": sum(b["regels_goed"] for b in bestellingen),
        "besteld": sum(b["besteld"] for b in bestellingen),
        "geleverd": sum(b["geleverd"] for b in bestellingen),
    }
