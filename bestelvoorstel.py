"""Het bestelvoorstel per product: tot wanneer je moet bestellen, wat er tot de levering daarna verwacht wordt, het
advies, en hoeveel je zelf wilt bestellen (in hele colli), zoals op de handterminal van de supermarkt.

Bestelperiode (bestelperiode): bestel je bij een leverancier op vaste dagen vóór een tijd (Leveranciers), dan is het
uiterste bestelmoment de eerstvolgende besteldag vóór die tijd. Wat je dan bestelt, komt levertijd_dagen later; de
voorraad moet het daarna uithouden tot de levering van de bestelling erna. De prognose loopt dus tot die tweede levering.
Zonder leverancier of besteldagen: de komende 7 dagen, zoals voorheen.

Zelf gekozen aantal (zet_bestelaantal, 1.69.0): bij het product zie je het advies (bijvoorbeeld 1 tray) en zet je met
min en plus hoeveel colli je wilt bestellen (bijvoorbeeld 3 tray, of 0: niet bestellen). Dat aantal staat dan zo bij
"Voorgesteld om te bestellen", ook als het product boven het minimum zit of de prognose 0 is. Het geldt tot het product
besteld is (wis_bij_bestelling), net als manco.

De bijstelling in stuks van 1.68.0 (de prognose zelf plus of min) is sinds 1.72.0 weg: dat gaf een krom aantal dat
naar colli werd afgerond, en sinds 1.69.0 kies je gewoon het aantal colli.

Advies (advies): genoeg voor de periode (het 90%-punt van de verwachting, en minstens het minimum),
min wat er ligt en wat al onderweg is, naar boven afgerond op hele besteleenheden; moet er besteld worden en heeft het
product een vaste bestelhoeveelheid, dan minstens die. Dit is het enige besteladvies (sinds 1.71.0): de bestellijst, het
product, de Prognose, de tekorten op het overzicht, de uitdraai en de app halen het hier (adviezen, voor_product), zodat
er overal hetzelfde aantal staat. Het voorspelmodel zelf geeft alleen de verwachting en de kansen."""

import math
from datetime import datetime, time, timedelta

from helpers.producten import besteleenheid_factor, besteleenheid_naam, bestel_suggesties
from helpers.tijd import now_str
from leveranciers import besteldagen

STANDAARD_DAGEN = 7
MAX_DAGEN = 21
# De herinnering om te bestellen (bestelmomenten): zo lang van tevoren, maar niet 's nachts (dan de avond ervoor).
HERINNER_UREN = 3
NACHT_VAN, NACHT_TOT, AVOND = 22, 8, 20
HERINNER_DAGEN = 8  # zo ver vooruit plant de app de herinneringen
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
    """{product_id: {"eenheden", "door", "op", ...}} van wat nog geldt: "eenheden" is het zelf gekozen aantal colli en
    "door" wie het koos. (De tabel heet nog naar de bijstelling in stuks van 1.68.0; die kolom is altijd 0.)"""
    return {r["product_id"]: dict(r) for r in db.execute("SELECT * FROM bestel_bijstellingen").fetchall()}


def gekozen(bij):
    """Het zelf gekozen aantal colli uit een regel van bijstellingen(), of None."""
    return bij.get("eenheden") if bij else None


MAX_EENHEDEN = 999


def zet_bestelaantal(db, product_id, eenheden, door=None, gebruiker_id=None):
    """Zelf kiezen hoeveel colli je van dit product bestelt (0 = niet bestellen); None = weer het advies volgen."""
    if eenheden is None:
        db.execute("DELETE FROM bestel_bijstellingen WHERE product_id = ?", (product_id,))
    else:
        db.execute(
            """INSERT OR REPLACE INTO bestel_bijstellingen (product_id, stuks, eenheden, door, gebruiker_id, op)
               VALUES (?, 0, ?, ?, ?, ?)""",
            (product_id, max(0, min(MAX_EENHEDEN, int(eenheden))), door, gebruiker_id, now_str()),
        )
    db.commit()


def wis_bij_bestelling(db, product_ids):
    """Besteld: het gekozen aantal van deze producten is gebruikt. Commit niet."""
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


def advies(product, regel, al_onderweg=0):
    """Het advies voor een product. regel: de regel van het product uit voorspelling.maak_prognose (of None als er nog
    niets van verkocht is: dan is de prognose 0). {"verwacht", "hoog", "nodig", "advies_stuks", "advies_eenheden",
    "besteleenheid", "factor", "onderweg"}."""
    factor = besteleenheid_factor(product)
    verwacht = regel["verwacht"] if regel else 0.0
    hoog = regel["hoog"] if regel else 0.0
    onderweg = al_onderweg
    voorraad = max(0, product["voorraad"])
    nodig = max(product["min_voorraad"] or 0, hoog) - voorraad - onderweg
    stuks = max(0, math.ceil(nodig - 1e-9))
    vast = product["bestel_hoeveelheid"] if "bestel_hoeveelheid" in product.keys() else 0
    if stuks and vast and vast > 0:
        stuks = max(stuks, vast)  # een vaste bestelhoeveelheid: als er besteld moet worden, minstens die
    eenheden = -(-stuks // factor) if stuks else 0
    return {
        "verwacht": round(verwacht, 1),
        "hoog": round(hoog, 1),
        "nodig": stuks,
        "advies_stuks": eenheden * factor,
        "advies_eenheden": eenheden,
        "besteleenheid": besteleenheid_naam(product) if factor > 1 else product["eenheid"],
        "factor": factor,
        "onderweg": onderweg,
    }


def adviezen(db, nu=None):
    """Het besteladvies (advies) van alle actieve producten, elk met de bestelperiode van zijn leverancier (zonder
    besteldagen: STANDAARD_DAGEN). {"beschikbaar": of er een prognose is, "producten":
    {product_id: {**advies(...), "product", "regel" (de prognose van het product, of None), "dagen", "kans_tekort",
    "status"}}}. De kans en de status gaan over dezelfde periode, met de voorraad en wat onderweg is."""
    nu = nu or datetime.now()
    producten = {p["id"]: p for p in db.execute("SELECT * FROM producten WHERE actief = 1").fetchall()}
    periodes = {
        lev["id"]: bestelperiode(lev, nu)
        for lev in db.execute("SELECT * FROM leveranciers WHERE actief = 1").fetchall()
    }

    def dagen_van(p):
        periode = periodes.get(p["leverancier_id"])
        return periode["dagen"] if periode else STANDAARD_DAGEN

    al_onderweg = onderweg(db)
    per_dagen = prognoses(db, {dagen_van(p) for p in producten.values()} or {STANDAARD_DAGEN}, nu)
    uitkomst = {}
    for pid, p in producten.items():
        dagen = dagen_van(p)
        regel = (per_dagen.get(dagen) or {}).get(pid)
        uitkomst[pid] = {
            **advies(p, regel, al_onderweg.get(pid, 0)),
            "product": p,
            "regel": regel,
            "dagen": dagen,
            "kans_tekort": round(regel["kans_tekort"], 3) if regel else 0.0,
            "status": regel["status"] if regel else "ok",
        }
    return {"beschikbaar": any(v is not None for v in per_dagen.values()), "producten": uitkomst}


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
    uit = advies(product, per_id.get(product["id"]) if per_id else None, onderweg(db).get(product["id"], 0))
    keuze = gekozen(bij)
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
        "bijgesteld_door": bij["door"] if bij else None,  # wie het aantal koos
        # Voor de app tot en met 2.15.1, die de prognose als "met_bijstelling" leest.
        "bijstelling": 0,
        "met_bijstelling": uit["verwacht"],
        # Hoeveel colli je bestelt: wat je zelf koos, anders het advies.
        "gekozen": keuze,
        "bestellen_eenheden": keuze if keuze is not None else uit["advies_eenheden"],
        "voorraad": product["voorraad"],
        "min_voorraad": product["min_voorraad"] or 0,
        "eenheid": product["eenheid"],
    })
    return uit


def zet_op_bestellijst(db, product, door=None, gebruiker_id=None, nu=None):
    """"Op de bestellijst" (de knop op de productpagina en in de app): het product bij "Voorgesteld om te bestellen"
    zetten, met het advies en minstens 1 colli, als iemand nog geen aantal koos. Zit het onder het minimum, of koos
    iemand al een aantal, dan staat het er al. Geeft (het nieuwe bestelblok, melding)."""
    blok = voor_product(db, product, nu)
    keuze, colli = blok["gekozen"], blok["besteleenheid"]
    if keuze:
        return blok, f"{product['naam']} staat al bij Voorgesteld om te bestellen: {keuze} {colli}."
    if keuze is None and any(p["id"] == product["id"] for p in bestel_suggesties(db)):
        return blok, (f"{product['naam']} zit onder het minimum en staat al bij Voorgesteld om te bestellen "
                      f"(advies {blok['advies_eenheden']} {colli}).")
    aantal = max(1, blok["advies_eenheden"])
    zet_bestelaantal(db, product["id"], aantal, door, gebruiker_id)
    blok = voor_product(db, product, nu)
    al = f" Er is al {blok['onderweg']} {product['eenheid']} onderweg." if blok["onderweg"] else ""
    return blok, f"{product['naam']} staat bij Voorgesteld om te bestellen: {aantal} {colli}.{al}"


def herinner_moment(uiterst):
    """Wanneer de app eraan herinnert dat je moet bestellen: HERINNER_UREN voor het uiterste moment, maar valt dat 's
    nachts (22.00-8.00 uur), dan om 20.00 uur de avond ervoor."""
    moment = uiterst - timedelta(hours=HERINNER_UREN)
    if moment.hour >= NACHT_VAN:
        return datetime.combine(moment.date(), time(AVOND))
    if moment.hour < NACHT_TOT:
        return datetime.combine(moment.date() - timedelta(days=1), time(AVOND))
    return moment


def _vorig_bestelmoment(lev, uiterst):
    dagen, voor = besteldagen(lev), _bestellen_voor(lev)
    for i in range(1, 8):
        dag = uiterst.date() - timedelta(days=i)
        if dag.weekday() in dagen:
            return datetime.combine(dag, voor)
    return uiterst - timedelta(days=7)


def _voorgesteld_per_leverancier(db):
    """{leverancier_id: aantal producten} van wat nu bij "Voorgesteld om te bestellen" staat zonder de prognose: onder
    het minimum (en nog niet besteld) of zelf gekozen (zie zet_bestelaantal)."""
    ids = {p["id"] for p in bestel_suggesties(db)}
    ids |= {pid for pid, b in bijstellingen(db).items() if (gekozen(b) or 0) > 0}
    if not ids:
        return {}
    uitkomst = {}
    for r in db.execute(
        f"SELECT leverancier_id FROM producten WHERE id IN ({','.join('?' * len(ids))}) AND leverancier_id IS NOT NULL",
        tuple(ids),
    ).fetchall():
        uitkomst[r["leverancier_id"]] = uitkomst.get(r["leverancier_id"], 0) + 1
    return uitkomst


def bestelmomenten(db, nu=None, dagen=HERINNER_DAGEN):
    """De uiterste bestelmomenten van de komende 'dagen' dagen, van elke actieve leverancier met besteldagen: voor de
    herinnering in de handterminal-app (een melding op het startscherm en een notificatie, ook als de app dicht is).
    Per moment: wanneer de app herinnert, hoeveel producten er nu voor die leverancier klaarstaan (zonder de prognose,
    zie _voorgesteld_per_leverancier) en of er sinds het vorige bestelmoment al een bestelling is klaargezet. Op tijd."""
    nu = nu or datetime.now()
    aantallen = _voorgesteld_per_leverancier(db)
    uitkomst = []
    for lev in db.execute("SELECT * FROM leveranciers WHERE actief = 1 ORDER BY naam COLLATE NOCASE").fetchall():
        vanaf = nu
        while (periode := bestelperiode(lev, vanaf)) is not None and periode["uiterst"] <= nu + timedelta(days=dagen):
            uiterst = periode["uiterst"]
            al_besteld = db.execute(
                "SELECT 1 FROM bestellingen WHERE leverancier_id = ? AND aangemaakt_op > ? AND aangemaakt_op <= ? LIMIT 1",
                (lev["id"], _vorig_bestelmoment(lev, uiterst).strftime("%Y-%m-%d %H:%M"), uiterst.strftime("%Y-%m-%d %H:%M")),
            ).fetchone() is not None
            uitkomst.append({
                "leverancier_id": lev["id"],
                "leverancier": lev["naam"],
                "uiterst": uiterst.strftime("%Y-%m-%d %H:%M"),
                "uiterst_tekst": dag_tekst(uiterst, met_tijd=True),
                "tijd": uiterst.strftime("%H:%M"),
                "levering_tekst": dag_tekst(periode["levering"]),
                "herinnering": herinner_moment(uiterst).strftime("%Y-%m-%d %H:%M"),
                "aantal": aantallen.get(lev["id"], 0),
                "al_besteld": al_besteld,
            })
            vanaf = uiterst + timedelta(minutes=1)
    return sorted(uitkomst, key=lambda m: m["uiterst"])
