"""Instellingen en gegevens voor de kaartjes (pdf/kaartjes.py maakt de pdf, routes/kaartjes.py de pagina).

De instellingen (welk ontwerp, welke hardlopers, hoeveel vellen, kleur) staan in 1 rij in kaartjes_instellingen.
De hardlopers typ je zelf; als hulp is er een lijst van wat dit seizoen het meest is verkocht, met merken samengenomen
(alle Bozu-smaken samen), zodat je er met 1 klik een kunt overnemen."""

from club_van_20 import huidig_seizoen
from pdf.kaartjes import OPTIE_PER_SLEUTEL, STANDAARD_OPTIE, schoon_hardlopers
from seizoensrapport import seizoen_start

MAX_VELLEN = 50
AANTAL_SUGGESTIES = 14


def lees_instellingen(db):
    """{'optie', 'hardlopers' (lijst), 'hardlopers_tekst', 'vellen', 'zwartwit'}."""
    rij = db.execute("SELECT * FROM kaartjes_instellingen WHERE id = 1").fetchone()
    optie = rij["optie"] if rij and rij["optie"] in OPTIE_PER_SLEUTEL else STANDAARD_OPTIE
    tekst = rij["hardlopers"] if rij else ""
    return {
        "optie": optie,
        "hardlopers": schoon_hardlopers(tekst)[0],
        "hardlopers_tekst": tekst,
        "vellen": max(1, min(MAX_VELLEN, rij["vellen"])) if rij else 1,
        "zwartwit": bool(rij["zwartwit"]) if rij else False,
    }


def bewaar_instellingen(db, optie, hardlopers_tekst, vellen, zwartwit):
    """Slaat de keuzes op; geeft het aantal hardlopers terug dat niet op het kaartje past (en dus is weggelaten)."""
    namen, weggelaten = schoon_hardlopers(hardlopers_tekst)
    if optie not in OPTIE_PER_SLEUTEL:
        optie = STANDAARD_OPTIE
    db.execute(
        "UPDATE kaartjes_instellingen SET optie = ?, hardlopers = ?, vellen = ?, zwartwit = ? WHERE id = 1",
        (optie, "\n".join(namen), max(1, min(MAX_VELLEN, vellen)), 1 if zwartwit else 0),
    )
    db.commit()
    return weggelaten


def _gemeenschappelijk_begin(namen):
    """De woorden waarmee alle namen beginnen: ['Bozu Green', 'Bozu Peach'] -> 'Bozu'."""
    delen = [naam.split() for naam in namen]
    begin = []
    for woorden in zip(*delen):
        if len({w.lower() for w in woorden}) != 1:
            break
        begin.append(woorden[0])
    return " ".join(begin) or namen[0].split()[0]


def groepeer_op_merk(rijen, aantal=AANTAL_SUGGESTIES):
    """Producten met hetzelfde eerste woord worden 1 regel (alle Bozu-smaken, AA Drink in alle soorten):
    [(naam, aantal)] -> [{'naam', 'aantal', 'producten'}], het meest verkocht eerst. De naam van een groep is het
    begin dat alle producten delen; een product dat alleen staat houdt zijn volledige naam."""
    groepen = {}
    for naam, verkocht in rijen:
        if not naam or verkocht <= 0:
            continue
        groepen.setdefault(naam.split()[0].lower(), []).append((naam, verkocht))
    resultaat = []
    for leden in groepen.values():
        namen = [naam for naam, _ in leden]
        resultaat.append(
            {
                "naam": namen[0] if len(namen) == 1 else _gemeenschappelijk_begin(namen),
                "aantal": round(sum(v for _, v in leden)),
                "producten": len(leden),
            }
        )
    resultaat.sort(key=lambda r: (-r["aantal"], r["naam"].lower()))
    return resultaat[:aantal]


def topverkopers(db, aantal=AANTAL_SUGGESTIES):
    """Wat dit seizoen (vanaf 1 juli) het meest is verkocht, op aantal stuks, per merk (zie groepeer_op_merk)."""
    begin = seizoen_start(huidig_seizoen()).isoformat()
    rijen = db.execute(
        """SELECT p.naam AS naam, SUM(tr.verkocht) AS verkocht
           FROM telling_regels tr
           JOIN tellingen t ON t.id = tr.telling_id
           JOIN producten p ON p.id = tr.product_id
           WHERE t.datum >= ?
           GROUP BY tr.product_id""",
        (f"{begin} 00:00",),
    ).fetchall()
    return groepeer_op_merk([(r["naam"], r["verkocht"] or 0) for r in rijen], aantal)
