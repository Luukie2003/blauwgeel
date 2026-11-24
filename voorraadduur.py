"""Hoe lang een voorraad nog meegaat: het seintje bij Bestellijst nalopen als je meer bestelt dan er voorlopig op gaat
("genoeg voor ongeveer 20 weken").

Het tempo komt uit de tellingen zelf en niet uit de prognose: die kijkt maar een paar dagen vooruit en is in een week
zonder wedstrijd bijna nul. Per product telt de verkoop over de laatste WEKEN_TERUG weken, of sinds het voor het eerst
geteld is als dat korter is (een nieuw product lijkt anders veel te traag). Te kort of te weinig geteld: geen uitspraak."""

from datetime import datetime, timedelta

from inkoop_verkoop import LANG_WEKEN

WEKEN_TERUG = 13
MIN_WEKEN = 3
MIN_TELLINGEN = 3  # zoveel tellingen met verkoop erin, dus na de eerste keer tellen


def verkoop_per_week(db, nu=None):
    """{product_id: verkocht per week}, alleen van producten waar genoeg van bekend is (0.0: al die tijd niets verkocht).
    De eerste regel in de periode is alleen het begin: wat daarvoor verkocht is, hoort er niet bij."""
    nu = nu or datetime.now()
    vanaf = (nu - timedelta(weeks=WEKEN_TERUG)).strftime("%Y-%m-%d %H:%M")
    regels = {}
    for r in db.execute(
        """SELECT tr.product_id, t.datum, tr.verkocht FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
           WHERE t.datum >= ? ORDER BY t.datum, t.id""",
        (vanaf,),
    ).fetchall():
        regels.setdefault(r["product_id"], []).append(r)
    uitkomst = {}
    for pid, lijst in regels.items():
        weken = (datetime.fromisoformat(lijst[-1]["datum"]) - datetime.fromisoformat(lijst[0]["datum"])).total_seconds() / 604800
        if len(lijst) - 1 < MIN_TELLINGEN or weken < MIN_WEKEN:
            continue
        uitkomst[pid] = sum(max(0, r["verkocht"] or 0) for r in lijst[1:]) / weken
    return uitkomst


def te_veel(per_week, voorraad, onderweg, eenheden, factor):
    """Hoeveel weken het met deze bestelling duurt voor het op is, als dat te lang is; anders None. Te lang: ook met één
    colli minder is er genoeg voor LANG_WEKEN weken (één krat van iets dat langzaam gaat, is dus nooit te veel).
    per_week 0 (niets verkocht): float('inf'). Dezelfde regel staat in bestellijst_nalopen.html, voor terwijl je kiest."""
    if per_week is None or eenheden <= 0:
        return None
    zonder_laatste = max(0, voorraad) + onderweg + (eenheden - 1) * factor
    if per_week <= 0:
        return float("inf") if zonder_laatste > 0 else None
    if zonder_laatste / per_week < LANG_WEKEN:
        return None
    return (zonder_laatste + factor) / per_week
