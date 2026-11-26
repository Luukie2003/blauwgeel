"""Afspraken met een leverancier of merk (2.22.0): na een gesprek met de vertegenwoordiger leg je vast wat er is afgesproken,
zoals "€ 1,00 korting per doos" of "1 doos gratis op 10", met een begin en eventueel een einde. De Merkanalyse laat zien
wat de afspraak tot nu toe zou moeten opleveren, en Factuur inboeken herinnert eraan als er iets van dat merk binnenkomt:
staat de korting op de factuur, en zit de gratis doos erbij?

Een doos is de besteleenheid van het product (een karton van 12). Wat er is ingekocht, komt uit de boekingen (een
ingeboekte factuur of bestelling, of een losse levering), zoals bij Inkoop en verkoop; correcties tellen niet mee."""

from datetime import date

from helpers.producten import besteleenheid_factor
from helpers.tijd import now_str
from inkoop_verkoop import is_correctie
from merkanalyse import merk_van
from productkaart import KEUKEN_CATEGORIE

SOORTEN = {"korting": "Korting per doos", "gratis": "Gratis doos", "anders": "Iets anders"}


def _euro(x):
    return f"€ {x:.2f}".replace(".", ",")


def tekst(a):
    """De afspraak in een zin: 'Korting: € 1,00 per doos', '1 doos gratis op 10' of de omschrijving."""
    if a["soort"] == "korting" and a["bedrag"]:
        basis = f"{_euro(a['bedrag'])} korting per doos"
    elif a["soort"] == "gratis" and a["aantal"]:
        basis = f"1 doos gratis op {a['aantal']}"
    else:
        basis = a["omschrijving"] or "Afspraak"
    if a["omschrijving"] and a["soort"] != "anders":
        basis += f" ({a['omschrijving']})"
    return basis


def _geldig(a, op):
    return a["vanaf"] <= op and (not a["tot"] or op <= a["tot"])


def voeg_toe(db, merk, soort, bedrag, aantal, omschrijving, vanaf, tot, door=None):
    """Een nieuwe afspraak; geeft een foutmelding of None."""
    merk = " ".join((merk or "").split())
    soort = soort if soort in SOORTEN else "anders"
    omschrijving = " ".join((omschrijving or "").split())[:200] or None
    try:
        vanaf = date.fromisoformat(vanaf or "").isoformat()
        tot = date.fromisoformat(tot).isoformat() if tot else None
    except ValueError:
        return "Vul een geldige begindatum in (en eventueel een einde)."
    if tot and tot < vanaf:
        return "Het einde ligt voor het begin."
    try:
        bedrag = float(str(bedrag).replace(",", ".")) if soort == "korting" and str(bedrag or "").strip() else None
        aantal = int(aantal or 0) if soort == "gratis" else None
    except ValueError:
        return "Vul een geldig bedrag of aantal in."
    if not merk:
        return "Kies een merk."
    if soort == "korting" and not (bedrag and 0 < bedrag < 1000):
        return "Vul de korting per doos in, bijvoorbeeld 1,00."
    if soort == "gratis" and not (aantal and 1 <= aantal <= 500):
        return "Vul in op hoeveel dozen je er een gratis krijgt, bijvoorbeeld 10."
    if soort == "anders" and not omschrijving:
        return "Beschrijf wat er is afgesproken."
    db.execute(
        """INSERT INTO afspraken (merk, soort, bedrag, aantal, omschrijving, vanaf, tot, aangemaakt_door, aangemaakt_op)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (merk, soort, bedrag, aantal, omschrijving, vanaf, tot, door, now_str()),
    )
    db.commit()
    return None


def verwijder(db, afspraak_id):
    db.execute("DELETE FROM afspraken WHERE id = ?", (afspraak_id,))
    db.commit()


def _producten_van(db, merk):
    return {p["id"]: p for p in db.execute("SELECT * FROM producten WHERE categorie != ?", (KEUKEN_CATEGORIE,)).fetchall()
            if (merk_van(p) or "").lower() == merk.lower()}


def dozen_ingekocht(db, merk, vanaf, tot=None):
    """Hoeveel dozen (besteleenheden) van dit merk er van vanaf tot en met tot zijn ingeboekt, zonder correcties."""
    producten = _producten_van(db, merk)
    if not producten:
        return 0.0
    totaal = 0.0
    for m in db.execute(
        f"""SELECT product_id, aantal, opmerking, bestelling_id FROM mutaties
            WHERE type = 'in' AND telling_id IS NULL AND substr(datum, 1, 10) >= ? AND substr(datum, 1, 10) <= ?
              AND product_id IN ({','.join('?' * len(producten))})""",
        (vanaf, tot or "9999-12-31", *producten),
    ).fetchall():
        if m["bestelling_id"] is None and is_correctie(m["opmerking"]):
            continue
        totaal += m["aantal"] / besteleenheid_factor(producten[m["product_id"]])
    return totaal


def van_merk(db, merk, vandaag=None):
    """De afspraken van een merk, de lopende eerst, elk met "tekst", "loopt" en wat hij tot nu toe zou moeten opleveren:
    "dozen" (ingekocht sinds het begin) en bij korting "korting" (euro), bij gratis "gratis" (dozen)."""
    vandaag = (vandaag or date.today()).isoformat()
    uit = []
    for r in db.execute("SELECT * FROM afspraken WHERE merk = ? COLLATE NOCASE ORDER BY vanaf DESC, id DESC", (merk,)).fetchall():
        a = dict(r)
        a["tekst"] = tekst(a)
        a["loopt"] = _geldig(a, vandaag)
        a["dozen"] = dozen_ingekocht(db, merk, a["vanaf"], min(a["tot"] or vandaag, vandaag))
        a["korting"] = a["dozen"] * a["bedrag"] if a["soort"] == "korting" and a["bedrag"] else None
        a["gratis"] = int(a["dozen"] // a["aantal"]) if a["soort"] == "gratis" and a["aantal"] else None
        uit.append(a)
    return sorted(uit, key=lambda a: not a["loopt"])  # de lopende eerst, verder de nieuwste eerst (zie de query)


def bij_factuur(db, product_ids, op=None):
    """De lopende afspraken van de merken in een levering (Factuur inboeken): [{"merk", "tekst", "dozen", "gratis",
    "soort"}], met hoeveel dozen er sinds het begin zijn ingekocht (zonder deze levering) en hoeveel gratis dozen daar
    dan bij horen."""
    op = (op or date.today()).isoformat()
    merken = {}
    for p in db.execute(f"SELECT * FROM producten WHERE id IN ({','.join('?' * len(product_ids))})", tuple(product_ids)).fetchall() if product_ids else []:
        naam = merk_van(p)
        if naam:
            merken.setdefault(naam.lower(), naam)
    uit = []
    for sleutel, naam in sorted(merken.items()):
        for r in db.execute("SELECT * FROM afspraken WHERE merk = ? COLLATE NOCASE ORDER BY vanaf", (naam,)).fetchall():
            if not _geldig(r, op):
                continue
            dozen = dozen_ingekocht(db, naam, r["vanaf"], op)
            uit.append({"merk": naam, "tekst": tekst(r), "soort": r["soort"], "dozen": dozen,
                        "gratis": int(dozen // r["aantal"]) if r["soort"] == "gratis" and r["aantal"] else None})
    return uit
