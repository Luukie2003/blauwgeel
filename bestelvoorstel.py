"""Het bestelvoorstel per product: tot wanneer je moet bestellen, wat er tot de levering daarna verwacht wordt, en een
eigen bijstelling (plus of min) op die prognose, zoals op de handterminal van de supermarkt.

Bestelperiode (bestelperiode): bestel je bij een leverancier op vaste dagen vóór een tijd (Leveranciers), dan is het
uiterste bestelmoment de eerstvolgende besteldag vóór die tijd. Wat je dan bestelt, komt levertijd_dagen later; de
voorraad moet het daarna uithouden tot de levering van de bestelling erna. De prognose loopt dus tot die tweede levering.
Zonder leverancier of besteldagen: de komende 7 dagen, zoals voorheen.

Bijstelling: je ziet bij een product dat er bijvoorbeeld 14 verwacht worden, maar er komt een toernooi: +6. Dat telt
op bij de prognose, en daarmee bij het advies. Zo komt een product met een prognose van 0 toch bij "Voorgesteld om te
bestellen", of juist minder. De bijstelling geldt tot het product besteld is (wis_bij_bestelling), net als manco.

Advies (advies): genoeg voor de periode (het 90%-punt van de verwachting plus de bijstelling, en minstens het minimum),
min wat er ligt en wat al onderweg is, naar boven afgerond op hele besteleenheden."""

import math
from datetime import datetime, time, timedelta

from helpers.producten import besteleenheid_factor, besteleenheid_naam
from helpers.tijd import now_str
from leveranciers import besteldagen

STANDAARD_DAGEN = 7
MAX_DAGEN = 21
_DAG_KORT = ("ma", "di", "wo", "do", "vr", "za", "zo")


def dag_tekst(moment, met_tijd=False):
    """'vr 24-10' of 'vr 24-10 16:00'."""
    tekst = f"{_DAG_KORT[moment.weekday()]} {moment.strftime('%d-%m')}"
    return tekst + (f" {moment.strftime('%H:%M')}" if met_tijd else "")


def _bestellen_voor(lev):
    try:
        uur, minuut = (lev["bestellen_voor"] or "23:59").split(":")[:2]
        return time(int(uur), int(minuut))
    except (ValueError, TypeError):
        return time(23, 59)


def _volgend_bestelmoment(dagen, voor, na):
    """Het eerste bestelmoment (besteldag om 'voor') dat later is dan 'na'."""
    for i in range(15):
        dag = na.date() + timedelta(days=i)
        moment = datetime.combine(dag, voor)
        if dag.weekday() in dagen and moment > na:
            return moment
    return None


def bestelperiode(lev, nu=None):
    """{"uiterst": datetime, "levering": date, "volgende_levering": date, "dagen", "leverancier"} van een leverancier
    met besteldagen, of None (dan geldt STANDAARD_DAGEN)."""
    if lev is None:
        return None
    dagen = besteldagen(lev)
    if not dagen:
        return None
    nu = nu or datetime.now()
    voor = _bestellen_voor(lev)
    uiterst = _volgend_bestelmoment(dagen, voor, nu)
    if uiterst is None:
        return None
    daarna = _volgend_bestelmoment(dagen, voor, uiterst + timedelta(minutes=1))
    levertijd = max(0, lev["levertijd_dagen"] or 0)
    levering = uiterst.date() + timedelta(days=levertijd)
    volgende = (daarna.date() if daarna else uiterst.date() + timedelta(days=7)) + timedelta(days=levertijd)
    return {
        "uiterst": uiterst,
        "levering": levering,
        "volgende_levering": volgende,
        "dagen": min(MAX_DAGEN, max(1, (volgende - nu.date()).days)),
        "leverancier": lev["naam"],
    }


def periode_voor(db, product, nu=None):
    lev = None
    if product["leverancier_id"]:
        lev = db.execute("SELECT * FROM leveranciers WHERE id = ? AND actief = 1", (product["leverancier_id"],)).fetchone()
    return bestelperiode(lev, nu)


def bijstellingen(db):
    """{product_id: {"stuks", "door", "op"}} van de bijstellingen die nog gelden."""
    return {r["product_id"]: dict(r) for r in db.execute("SELECT * FROM bestel_bijstellingen").fetchall()}


def zet_bijstelling(db, product_id, stuks, door=None, gebruiker_id=None):
    """De bijstelling van een product op 'stuks' (plus of min, in de eenheid van het product); 0 haalt hem weg."""
    stuks = int(stuks)
    if stuks == 0:
        db.execute("DELETE FROM bestel_bijstellingen WHERE product_id = ?", (product_id,))
    else:
        db.execute(
            """INSERT OR REPLACE INTO bestel_bijstellingen (product_id, stuks, door, gebruiker_id, op)
               VALUES (?, ?, ?, ?, ?)""",
            (product_id, stuks, door, gebruiker_id, now_str()),
        )
    db.commit()


def wis_bij_bestelling(db, product_ids):
    """Besteld: de bijstelling van deze producten is gebruikt. Commit niet."""
    ids = list(product_ids)
    if ids:
        db.execute(f"DELETE FROM bestel_bijstellingen WHERE product_id IN ({','.join('?' * len(ids))})", ids)


def onderweg(db):
    """{product_id: aantal} van wat al besteld is maar nog niet binnen."""
    return {
        r["product_id"]: r["aantal"]
        for r in db.execute(
            """SELECT br.product_id, SUM(br.aantal_besteld) AS aantal FROM bestelregels br
               JOIN bestellingen b ON b.id = br.bestelling_id WHERE b.status = 'besteld' GROUP BY br.product_id"""
        ).fetchall()
    }


def advies(product, regel, bijstelling=0, al_onderweg=0):
    """Het advies voor een product. regel: de regel van het product uit voorspelling.maak_prognose (of None als er nog
    niets van verkocht is: dan is de prognose 0). {"verwacht", "hoog", "bijstelling", "nodig", "advies_stuks",
    "advies_eenheden", "besteleenheid", "factor", "onderweg"}."""
    factor = besteleenheid_factor(product)
    verwacht = regel["verwacht"] if regel else 0.0
    hoog = regel["hoog"] if regel else 0.0
    onderweg = al_onderweg
    voorraad = max(0, product["voorraad"])
    nodig = max(product["min_voorraad"] or 0, hoog + bijstelling) - voorraad - onderweg
    stuks = max(0, math.ceil(nodig - 1e-9))
    eenheden = -(-stuks // factor) if stuks else 0
    return {
        "verwacht": round(verwacht, 1),
        "hoog": round(hoog, 1),
        "bijstelling": bijstelling,
        "met_bijstelling": round(max(0.0, verwacht + bijstelling), 1),
        "nodig": stuks,
        "advies_stuks": eenheden * factor,
        "advies_eenheden": eenheden,
        "besteleenheid": besteleenheid_naam(product) if factor > 1 else product["eenheid"],
        "factor": factor,
        "onderweg": onderweg,
    }


def prognoses(db, dagen_set, nu=None):
    """{dagen: {product_id: regel}} voor elke gevraagde periode (het voorspelmodel bewaart elke uitkomst een dag)."""
    from voorspelling import maak_prognose

    uit = {}
    for dagen in sorted(set(dagen_set)):
        try:
            p = maak_prognose(db, dagen=dagen, nu=nu)
        except Exception as fout:  # het bestellen mag nooit stuk gaan door de voorspelling
            print(f"[voorspelling] mislukt ({dagen} dagen): {fout}")
            p = {"beschikbaar": False}
        uit[dagen] = {r["product"]["id"]: r for r in p.get("producten", [])} if p.get("beschikbaar") else None
    return uit


def voor_product(db, product, nu=None):
    """Alles voor het bestelblok van één product (productscherm in de app en op de site)."""
    periode = periode_voor(db, product, nu)
    dagen = periode["dagen"] if periode else STANDAARD_DAGEN
    per_id = prognoses(db, [dagen], nu)[dagen]
    bij = bijstellingen(db).get(product["id"])
    uit = advies(product, per_id.get(product["id"]) if per_id else None, bij["stuks"] if bij else 0,
                 onderweg(db).get(product["id"], 0))
    uit.update({
        "dagen": dagen,
        "prognose_beschikbaar": per_id is not None,
        "uiterst": periode["uiterst"].strftime("%Y-%m-%d %H:%M") if periode else None,
        "levering": periode["levering"].isoformat() if periode else None,
        "volgende_levering": periode["volgende_levering"].isoformat() if periode else None,
        "leverancier": periode["leverancier"] if periode else None,
        "uiterst_tekst": dag_tekst(periode["uiterst"], met_tijd=True) if periode else None,
        "levering_tekst": dag_tekst(periode["levering"]) if periode else None,
        "volgende_levering_tekst": dag_tekst(periode["volgende_levering"]) if periode else None,
        "bijgesteld_door": bij["door"] if bij else None,
        "voorraad": product["voorraad"],
        "min_voorraad": product["min_voorraad"] or 0,
        "eenheid": product["eenheid"],
    })
    return uit
