"""De productpagina (/producten/<id>): alles over één product op één plek.

productinfo() verzamelt wat snel uit de database komt (voorraad, prijzen, marge, inkoop en leverancier, open
bestellingen, barcodes, tellingen, derving). verkoopinfo() rekent met het voorspelmodel (de verkoop per week en de
verwachting voor de komende dagen) en wordt door de pagina apart opgehaald (zie routes/producten/scannen.py), want dat
kan op de server de eerste keer na een telling enkele seconden duren."""

from datetime import date, datetime, timedelta

import barcodes
from helpers.producten import besteleenheid_factor, inkoop_per_stuk, omzet_per_eenheid
from leveranciers import besteldagen_tekst
from marge import lees_doelmarge

TELLINGEN = 6  # zoveel van de laatste tellingen staan op de pagina
PRIJS_GESCHIEDENIS = 5
DERVING_DAGEN = 90
WEKEN_GRAFIEK = 12
WEKEN_GEMIDDELD = 4
WEKEN_NIET_VERKOCHT = 3  # vanaf zoveel weken zonder verkoop staat er een melding
HANDMATIG_AANGEPAST = "Voorraad aangepast via Bewerken"  # de opmerking bij zo'n boeking (zie product_bewerken)


def productinfo(db, product):
    """Alles voor de productpagina wat zonder het voorspelmodel kan."""
    pid = product["id"]
    factor = besteleenheid_factor(product)
    inkoop_stuk = inkoop_per_stuk(product)
    verkoop_stuk = omzet_per_eenheid(product)  # bij een fust: glazen maal de prijs per glas
    marge = None
    if inkoop_stuk > 0 and verkoop_stuk > 0:
        marge_stuk = verkoop_stuk - inkoop_stuk
        pct = marge_stuk / verkoop_stuk * 100
        doel = lees_doelmarge(db)
        marge = {"stuk": marge_stuk, "pct": pct, "doel": doel, "onder_doel": pct < doel}

    leverancier = None
    if product["leverancier_id"]:
        leverancier = db.execute("SELECT * FROM leveranciers WHERE id = ?", (product["leverancier_id"],)).fetchone()

    tellingen = db.execute(
        """SELECT t.id, t.datum, t.naam, r.voorraad_voor, r.geteld_aantal, r.verkocht, r.verkoopprijs
           FROM telling_regels r JOIN tellingen t ON t.id = r.telling_id
           WHERE r.product_id = ? ORDER BY t.datum DESC, t.id DESC LIMIT ?""",
        (pid, TELLINGEN),
    ).fetchall()

    vanaf = (datetime.now() - timedelta(days=DERVING_DAGEN)).strftime("%Y-%m-%d 00:00")
    derving = db.execute(
        """SELECT COALESCE(SUM(aantal), 0) AS aantal, COUNT(*) AS keer FROM mutaties
           WHERE product_id = ? AND type = 'uit' AND reden IS NOT NULL AND reden != '' AND datum >= ?""",
        (pid, vanaf),
    ).fetchone()

    return {
        "factor": factor,
        "in_besteleenheden": product["voorraad"] / factor if factor > 1 else None,
        "inkoop_stuk": inkoop_stuk,
        "verkoop_stuk": verkoop_stuk,
        "voorraadwaarde": max(product["voorraad"], 0) * inkoop_stuk,
        "marge": marge,
        "leverancier": leverancier,
        "besteldagen": besteldagen_tekst(leverancier) if leverancier else "",
        "prijsopties": db.execute(
            "SELECT * FROM product_prijsopties WHERE product_id = ? ORDER BY volgorde, id", (pid,)
        ).fetchall(),
        "gepland": db.execute(
            """SELECT g.*, o.naam AS optie_naam FROM prijs_wijzigingen_gepland g
               LEFT JOIN product_prijsopties o ON o.id = g.optie_id
               WHERE g.product_id = ? ORDER BY g.ingangsdatum""",
            (pid,),
        ).fetchall(),
        "prijs_geschiedenis": db.execute(
            "SELECT * FROM prijs_geschiedenis WHERE product_id = ? ORDER BY datum DESC, id DESC LIMIT ?",
            (pid, PRIJS_GESCHIEDENIS),
        ).fetchall(),
        "open_bestellingen": db.execute(
            """SELECT b.id, b.aangemaakt_op, b.referentie, br.aantal_besteld FROM bestelregels br
               JOIN bestellingen b ON b.id = br.bestelling_id
               WHERE br.product_id = ? AND b.status = 'besteld' ORDER BY b.aangemaakt_op""",
            (pid,),
        ).fetchall(),
        "laatste_levering": db.execute(
            """SELECT datum, aantal, naam, opmerking FROM mutaties
               WHERE product_id = ? AND type = 'in' AND telling_id IS NULL AND COALESCE(opmerking, '') NOT LIKE ?
               ORDER BY datum DESC, id DESC LIMIT 1""",
            (pid, HANDMATIG_AANGEPAST + "%"),
        ).fetchone(),
        "meldingen": db.execute(
            "SELECT COUNT(*) FROM bestellijst_meldingen WHERE product_id = ? AND afgehandeld = 0", (pid,)
        ).fetchone()[0],
        "artikelen": barcodes.artikelen_van(db, pid),
        "tellingen": tellingen,
        "laatste_telling": tellingen[0] if tellingen else None,
        "derving": derving,
        "derving_dagen": DERVING_DAGEN,
    }


def _maandag(dag):
    return dag - timedelta(days=dag.weekday())


def bestelblok(db, product, nu=None):
    """Het bestelblok los (bestelvoorstel.voor_product), voor als er nog geen verkoopinfo is; None als het mislukt."""
    import bestelvoorstel

    try:
        return bestelvoorstel.voor_product(db, product, nu)
    except Exception as fout:  # het blok mag de productpagina nooit stuk maken
        print(f"[productpagina] bestelblok van {product['id']} mislukt: {fout}")
        return None


def verkoopinfo(db, product_id, vandaag=None, nu=None):
    """De verkoop per week (uit de tellingen, over de dagen verdeeld zoals in het voorspelmodel) en de verwachting
    voor de komende 7 dagen, en het bestelblok (bestelvoorstel.voor_product). None als er nog geen telling is."""
    from voorspelling import maak_prognose, verdeling  # hier pas: het voorspelmodel is groot

    nu = nu or datetime.now()
    vandaag = vandaag or nu.date()
    data = verdeling(db, nu)
    if data is None:
        return None
    eerste_week = _maandag(data["eerste"].date())
    deze_week = _maandag(vandaag)
    weken = []
    for i in range(WEKEN_GRAFIEK - 1, -1, -1):
        maandag = deze_week - timedelta(weeks=i)
        if maandag < eerste_week:
            continue
        aantal = euro = 0.0
        for d in range(7):
            regel = data["producten"].get(maandag + timedelta(days=d), {}).get(product_id)
            if regel:
                aantal += regel[0]
                euro += regel[1]
        weken.append({
            "maandag": maandag,
            "week": maandag.isocalendar()[1],
            "aantal": aantal,
            "omzet": euro,
            "lopend": maandag == deze_week,
            # Een week waarvan de laatste telling niet alle dagen dekt, is nog niet af.
            "nog_niet_af": datetime.combine(maandag + timedelta(days=7), datetime.min.time()) > data["laatste"],
        })
    afgerond = [w for w in weken if not w["nog_niet_af"]]
    recent = afgerond[-WEKEN_GEMIDDELD:]
    per_week = sum(w["aantal"] for w in recent) / len(recent) if recent else None
    zonder_verkoop = 0
    for w in reversed(afgerond):
        if w["aantal"] >= 0.5:
            break
        zonder_verkoop += 1

    prognose = maak_prognose(db, 7, nu=nu)
    verwachting = None
    if prognose.get("beschikbaar"):
        verwachting = next((p for p in prognose["producten"] if p["product"]["id"] == product_id), None)

    # Het bestelblok: tot wanneer bestellen, de prognose tot de levering daarna en een eventuele bijstelling.
    import bestelvoorstel

    product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()
    bestellen = bestelvoorstel.voor_product(db, product, nu) if product is not None else None

    hoogste = max((w["aantal"] for w in weken), default=0)
    return {
        "bestellen": bestellen,
        "weken": weken,
        "hoogste": hoogste,
        "per_week": per_week,
        "weken_gemiddeld": len(recent),
        "omzet_recent": sum(w["omzet"] for w in recent),
        "zonder_verkoop": zonder_verkoop if zonder_verkoop >= WEKEN_NIET_VERKOCHT else 0,
        "geteld_tot": data["laatste"],
        "verwachting": verwachting,
        "prognose_dagen": prognose.get("dagen", 7) if prognose.get("beschikbaar") else None,
    }


def leeftijd(datum_tekst, vandaag=None):
    """'vandaag', 'gisteren', '3 dagen geleden' of '5 weken geleden' voor een datum als '2026-10-13 17:23'."""
    if not datum_tekst:
        return ""
    dag = date.fromisoformat(datum_tekst[:10])
    dagen = ((vandaag or date.today()) - dag).days
    if dagen <= 0:
        return "vandaag"
    if dagen == 1:
        return "gisteren"
    if dagen < 14:
        return f"{dagen} dagen geleden"
    return f"{dagen // 7} weken geleden"
