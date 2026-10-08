"""De ledenadministratie: leden, betalingen per seizoen, projecten en de financiele cijfers."""

from helpers import now_str, vandaag_amsterdam
from club_van_20.seizoenen import huidig_seizoen, verschuif_seizoen


BIJDRAGE_STATUS_LABELS = {
    "niet_gevraagd": "Niet gevraagd",
    "gevraagd": "Gevraagd",
    "toegezegd": "Toegezegd",
    "betaald": "Betaald",
    "afgezegd": "Stopt",
}


BIJDRAGE_STATUSSEN = list(BIJDRAGE_STATUS_LABELS)


BETAALWIJZEN = {
    "contant": "Contant",
    "mollie": "Mollie (online)",
    "tikkie": "Tikkie / betaalverzoek",
    "bank": "Overschrijving",
    "anders": "Anders",
}


PROJECT_STATUS_LABELS = {
    "gepland": "Gepland",
    "bezig": "Mee bezig",
    "klaar": "Klaar",
}


# ---------- Leden + bijdragen ----------


def leden_met_bijdragen(db, alleen_actief=False):
    """Alle leden als dicts, elk met 'bijdragen' ({seizoen: dict}) en een
    paar afgeleide velden. 2 queries i.p.v. 1 per lid (het scherm pollt dit
    elke 10s)."""
    waar = "WHERE status != 'inactief'" if alleen_actief else ""
    leden = [
        dict(r)
        for r in db.execute(
            f"SELECT * FROM club_van_20_leden {waar} ORDER BY naam COLLATE NOCASE"
        ).fetchall()
    ]
    bijdragen_per_lid = {}
    for b in db.execute("SELECT * FROM club_van_20_bijdragen").fetchall():
        bijdragen_per_lid.setdefault(b["lid_id"], {})[b["seizoen"]] = dict(b)
    for lid in leden:
        bijdragen = bijdragen_per_lid.get(lid["id"], {})
        lid["bijdragen"] = bijdragen
        betaald = sorted(s for s, b in bijdragen.items() if b["status"] == "betaald")
        lid["betaalde_seizoenen"] = betaald
        lid["aantal_seizoenen"] = len(betaald) + (lid.get("eerdere_seizoenen") or 0)
        lid["eerste_seizoen"] = betaald[0] if betaald else None
        lid["totaal_betaald"] = sum(
            b["bedrag"] or 0 for b in bijdragen.values() if b["status"] == "betaald"
        )
        lid["volledige_naam"] = " ".join(
            deel for deel in (lid.get("voornaam"), lid.get("achternaam")) if deel
        )
    return leden


def bijdrage_status(lid, seizoen):
    b = lid["bijdragen"].get(seizoen)
    return b["status"] if b else "niet_gevraagd"


def is_nieuw_lid(lid, seizoen):
    """Eerste betaalde seizoen is dit seizoen (en geen eerdere seizoenen van
    vóór de administratie ingevuld)."""
    return lid["eerste_seizoen"] == seizoen and not (lid.get("eerdere_seizoenen") or 0)


def sla_bijdrage_op(db, lid_id, seizoen, status, bedrag=None, betaald_door=None,
                    betaalwijze=None, notitie=None, standaard_bedrag=20, gebruiker=None,
                    betaald_op=None, nul_toegestaan=False):
    """Upsert van 1 bijdrage. Bij 'betaald' zonder bedrag geldt het
    standaardbedrag, en zonder datum vandaag. 'niet_gevraagd' zonder verdere
    gegevens verwijdert de rij gewoon (= geen rij, zie de moduledocstring).
    Met nul_toegestaan blijft een bedrag van 0 bij 'betaald' staan (de import:
    verlengd, maar het geld is al in een eerder seizoen meegeteld)."""
    if status not in BIJDRAGE_STATUS_LABELS:
        raise ValueError(f"Onbekende status: {status}")
    if status == "betaald":
        if bedrag is None or (not bedrag and not nul_toegestaan):
            bedrag = standaard_bedrag
        betaald_op = betaald_op or vandaag_amsterdam().isoformat()
    else:
        bedrag = bedrag or 0
        betaald_op = None
    if status == "niet_gevraagd" and not (betaald_door or notitie):
        db.execute(
            "DELETE FROM club_van_20_bijdragen WHERE lid_id = ? AND seizoen = ?", (lid_id, seizoen)
        )
        return
    db.execute(
        """INSERT INTO club_van_20_bijdragen
               (lid_id, seizoen, status, bedrag, betaald_door, betaalwijze, betaald_op,
                notitie, bijgewerkt_door, bijgewerkt_op)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(lid_id, seizoen) DO UPDATE SET
               status = excluded.status,
               bedrag = excluded.bedrag,
               betaald_door = excluded.betaald_door,
               betaalwijze = excluded.betaalwijze,
               betaald_op = COALESCE(club_van_20_bijdragen.betaald_op, excluded.betaald_op),
               notitie = excluded.notitie,
               bijgewerkt_door = excluded.bijgewerkt_door,
               bijgewerkt_op = excluded.bijgewerkt_op""",
        (
            lid_id,
            seizoen,
            status,
            bedrag,
            (betaald_door or "").strip() or None,
            betaalwijze if betaalwijze in BETAALWIJZEN else None,
            betaald_op,
            (notitie or "").strip() or None,
            gebruiker,
            now_str(),
        ),
    )
    if status != "betaald":
        # COALESCE hierboven bewaart de oorspronkelijke betaaldatum bij het
        # opnieuw opslaan van een betaalde bijdrage -- maar een bijdrage die
        # níet (meer) betaald is, hoort ook geen betaaldatum te hebben.
        db.execute(
            "UPDATE club_van_20_bijdragen SET betaald_op = NULL WHERE lid_id = ? AND seizoen = ?",
            (lid_id, seizoen),
        )


def seizoen_totalen(db):
    """{seizoen: {bedrag, betaald, gevraagd, toegezegd, afgezegd}} over alle
    (ook inactieve) leden -- geld dat binnen is, blijft binnen."""
    totalen = {}
    for r in db.execute(
        """SELECT seizoen, status, COUNT(*) AS n, COALESCE(SUM(bedrag), 0) AS som
           FROM club_van_20_bijdragen GROUP BY seizoen, status"""
    ).fetchall():
        t = totalen.setdefault(
            r["seizoen"], {"bedrag": 0, "betaald": 0, "gevraagd": 0, "toegezegd": 0, "afgezegd": 0}
        )
        if r["status"] == "betaald":
            t["bedrag"] += r["som"]
        if r["status"] in t:
            t[r["status"]] += r["n"]
    return totalen


# ---------- Geld en projecten ----------


def project_kosten(project):
    return project["kosten"] if project["kosten"] is not None else (project["raming"] or 0)


def financien(db, bedrag_per_bordje=20, seizoen=None):
    """Opgehaald (totaal en dit seizoen), besteed, beschikbaar en het
    eerstvolgende doel. Besteed = kosten van projecten die klaar zijn of
    waar al aan gewerkt wordt (werkelijke kosten, of anders de raming);
    het eerstvolgende geplande project is het 'doel' waar het beschikbare
    geld naartoe spaart."""
    seizoen = seizoen or huidig_seizoen()
    totalen = seizoen_totalen(db)
    opgehaald = sum(t["bedrag"] for t in totalen.values())
    dit = totalen.get(seizoen, {"bedrag": 0, "betaald": 0})
    projecten = [
        dict(p)
        for p in db.execute(
            "SELECT * FROM club_van_20_projecten ORDER BY volgorde, id"
        ).fetchall()
    ]
    besteed = sum(project_kosten(p) for p in projecten if p["status"] in ("klaar", "bezig"))
    beschikbaar = opgehaald - besteed
    # Het beschikbare geld wordt in volgorde over de geplande projecten
    # "verdeeld": wat al helemaal bij elkaar is gespaard, telt als gespaard,
    # en het doel is het eerste project waar nog geld voor nodig is (of het
    # laatste, als alles al gespaard is).
    doel = None
    gepland = [p for p in projecten if p["status"] == "gepland"]
    rest = max(0, beschikbaar)
    for p in gepland:
        p["gespaard"] = min(rest, p["raming"] or 0) >= (p["raming"] or 0)
        if p["gespaard"]:
            rest -= p["raming"] or 0
    if gepland:
        p = next((p for p in gepland if not p["gespaard"]), gepland[-1])
        raming = p["raming"] or 0
        gespaard = raming if p["gespaard"] else max(0, min(rest, raming))
        nog_nodig = max(0, raming - gespaard)
        doel = {
            "naam": p["naam"],
            "raming": raming,
            "gespaard": gespaard,
            "procent": round(gespaard / raming * 100) if raming else 100,
            "nog_nodig": nog_nodig,
            "nog_bordjes": -(-int(nog_nodig) // int(bedrag_per_bordje)) if bedrag_per_bordje else 0,
        }
    return {
        "opgehaald": opgehaald,
        "opgehaald_seizoen": dit["bedrag"],
        "betaald_seizoen": dit["betaald"],
        "besteed": besteed,
        "beschikbaar": beschikbaar,
        "doel": doel,
        "projecten": projecten,
        "gerealiseerd": [
            p for p in projecten if p["status"] in ("klaar", "bezig") and p["toon_op_scherm"]
        ],
        "gepland": [p for p in projecten if p["status"] == "gepland" and p["toon_op_scherm"]],
    }


def euro(bedrag, decimalen=False):
    """€ 1.840 (of € 1.840,00) -- Nederlandse notatie."""
    tekst = f"{bedrag:,.2f}" if decimalen else f"{round(bedrag):,}"
    return "€ " + tekst.replace(",", "X").replace(".", ",").replace("X", ".")


# ---------- Dashboard ----------


def bereken_club_van_20_status(db):
    """Statusblokje op het dashboard: hoeveel leden die dit seizoen
    'verwacht' worden (actief, niet gestopt, en betaald in een van de 2
    vorige seizoenen of al gevraagd/toegezegd) nog niet betaald hebben. Groen
    zodra iedereen binnen is; oranje zolang er nog iemand openstaat."""
    seizoen = huidig_seizoen()
    vorige = {verschuif_seizoen(seizoen, -1), verschuif_seizoen(seizoen, -2)}
    open_leden = []
    niet_gevraagd = 0
    betaald = 0
    for lid in leden_met_bijdragen(db, alleen_actief=True):
        status = bijdrage_status(lid, seizoen)
        if status == "betaald":
            betaald += 1
            continue
        if status == "afgezegd":
            continue
        if status in ("gevraagd", "toegezegd") or vorige & set(lid["betaalde_seizoenen"]):
            open_leden.append({"naam": lid["naam"], "status": status})
            if status == "niet_gevraagd":
                niet_gevraagd += 1
    return {
        "seizoen": seizoen,
        "leden": open_leden,
        "aantal": len(open_leden),
        "niet_gevraagd": niet_gevraagd,
        "betaald": betaald,
        "ok": not open_leden,
    }
