"""Het plan voor een sluitperiode (Bestellen > Prognose > Winterstop): wat er vóór de stop nog besteld moet worden, wat er
blijft liggen en dus beter eerst op kan, en wat er nodig is om weer open te gaan.

Een sluitperiode is een reeks van minstens MIN_DAGEN dagen waarop de kantine dicht is (zie voorspelling.lees_kalender: de
verkoopdagen, de thuiswedstrijden, de evenementen en de uitzonderingen). Het rekent met wat er nu waarschijnlijk ligt, met
wat onderweg is en met de verwachte verkoop uit het voorspelmodel. Een minimum telt vóór de stop niet mee: daarvoor bestel
je niet nog even bij."""

import math
from datetime import datetime, time, timedelta

import bestelvoorstel
from helpers.producten import besteleenheid_factor, besteleenheid_naam, inkoop_per_stuk
from productkaart import KEUKEN_CATEGORIE
from voorspelling import lees_kalender, verwacht_tussen, verwachte_verkoop_sinds_telling, verwachte_voorraad
from voorspelling.basis import DAG_BEGIN_UUR

MIN_DAGEN = 14
WEKEN_VOORUIT = 26
HERSTART_DAGEN = 14  # wat er nodig is voor de eerste twee weken na de stop


def perioden(db, vandaag):
    """De sluitperioden van het komende half jaar: [{"van", "tot" (eerste en laatste dichte dag), "dagen", "laatste_open"
    (None: de kantine is nu al dicht), "eerste_open"}]. Waar nog geen dag bekend is waarop hij weer opengaat, valt niets te
    plannen: die staat er niet bij."""
    eind = vandaag + timedelta(weeks=WEKEN_VOORUIT)
    open_dagen = sorted(d for d, k in lees_kalender(db, vandaag, eind).items() if k["open"])
    uit, vorige = [], vandaag - timedelta(days=1)
    for dag in open_dagen:
        dicht = (dag - vorige).days - 1
        if dicht >= MIN_DAGEN:
            uit.append({"van": vorige + timedelta(days=1), "tot": dag - timedelta(days=1), "dagen": dicht,
                        "laatste_open": vorige if vorige >= vandaag else None, "eerste_open": dag})
        vorige = dag
    return uit


def laatste_bestelmoment(lev, voor, nu):
    """Het laatste bestelmoment bij deze leverancier waarvan de levering er uiterlijk op 'voor' (date) is, of None."""
    uit, vanaf = None, nu
    while (p := bestelvoorstel.bestelperiode(lev, vanaf)) is not None and p["levering"] <= voor:
        uit, vanaf = p["uiterst"], p["uiterst"] + timedelta(minutes=1)
    return uit


def _begin(dag):
    return datetime.combine(dag, time(DAG_BEGIN_UUR))


def plan(db, periode, nu=None):
    """{"beschikbaar" (is er een voorspelling), "producten", "bestellen", "opmaken", "wachten", "herstart", "waarde_over",
    "bestel_voor", "bestel_herstart"} voor één periode. De lijsten zijn delen van "producten"."""
    nu = nu or datetime.now()
    voor = verwacht_tussen(db, nu, _begin(periode["van"]), nu) if periode["laatste_open"] else {}
    na = verwacht_tussen(db, _begin(periode["eerste_open"]), _begin(periode["eerste_open"] + timedelta(days=HERSTART_DAGEN)), nu)
    sinds = verwachte_verkoop_sinds_telling(db, nu)
    onderweg = bestelvoorstel.onderweg(db)
    leveranciers = {r["id"]: r for r in db.execute("SELECT * FROM leveranciers WHERE actief = 1").fetchall()}
    producten = []
    for p in db.execute(
        """SELECT * FROM producten WHERE actief = 1 AND categorie != ? AND COALESCE(niet_tellen, 0) = 0
           ORDER BY categorie COLLATE NOCASE, naam COLLATE NOCASE""",
        (KEUKEN_CATEGORIE,),
    ).fetchall():
        pid, factor = p["id"], besteleenheid_factor(p)
        stand = verwachte_voorraad(sinds.get(pid), p["voorraad"])
        ligt = stand["verwacht"] if stand else max(0, p["voorraad"])
        komt = onderweg.get(pid, 0)
        v, n = voor.get(pid), na.get(pid)
        if not (ligt or komt or v or n):
            continue
        verwacht, hoog = (v["verwacht"], v["hoog"]) if v else (0.0, 0.0)
        na_hoog = n["hoog"] if n else 0.0
        minimum = p["min_voorraad"] or 0
        eenheden = -(-math.ceil(max(0.0, hoog - ligt - komt) - 1e-9) // factor)
        over = max(0, round(ligt + komt + eenheden * factor - verwacht))
        herstart = -(-math.ceil(max(0.0, max(minimum, na_hoog) - over) - 1e-9) // factor)
        producten.append({
            "id": pid, "naam": p["naam"], "categorie": p["categorie"], "eenheid": p["eenheid"], "ligt": ligt, "onderweg": komt,
            "verwacht": round(verwacht), "hoog": round(hoog), "bestellen": eenheden, "over": over,
            "waarde": over * inkoop_per_stuk(p), "na": round(n["verwacht"]) if n else 0, "herstart": herstart,
            "colli": besteleenheid_naam(p) if factor > 1 else p["eenheid"], "factor": factor, "minimum": minimum,
            "leverancier_id": p["leverancier_id"],
            # Opmaken: ook na de eerste twee weken open ligt er nog van, en het is meer dan het minimum. Zonder voorspelling
            # (te weinig geteld of nooit verkocht) valt daar niets over te zeggen; dat zijn de niet-lopers.
            "opmaken": bool(v or n) and over > max(minimum, na_hoog) and eenheden == 0,
            "wachten": eenheden == 0 and ligt + komt < minimum and periode["laatste_open"] is not None,
        })

    def momenten(welke, tot):
        uit = []
        for lev_id in {p["leverancier_id"] for p in welke if p["leverancier_id"] in leveranciers}:
            moment = laatste_bestelmoment(leveranciers[lev_id], tot, nu) if tot else None
            if moment:
                uit.append((leveranciers[lev_id]["naam"], bestelvoorstel.dag_tekst(moment, met_tijd=True)))
        return sorted(uit, key=lambda m: m[0].lower())

    bestellen = [p for p in producten if p["bestellen"] > 0]
    herstart = [p for p in producten if p["herstart"] > 0]
    return {
        "beschikbaar": bool(voor or na),
        "producten": producten,
        "bestellen": bestellen,
        "opmaken": sorted((p for p in producten if p["opmaken"]), key=lambda p: (-p["waarde"], p["naam"].lower())),
        "wachten": [p for p in producten if p["wachten"]],
        "herstart": herstart,
        "waarde_over": sum(p["waarde"] for p in producten),
        "bestel_voor": momenten(bestellen, periode["laatste_open"]),
        "bestel_herstart": momenten(herstart, periode["eerste_open"]),
    }
