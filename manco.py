"""Manco opvolgen: wat bij een ontvangen bestelling niet (of te weinig) is geleverd.

Bij het inboeken (Factuur gecontroleerd, of Bestellingen > Inboeken) staat per bestelregel wat er binnenkwam. Wat er
minder kwam dan besteld, is 'open manco' tot het is opgevolgd: het product staat weer op een nieuwe bestelling
(volg_op_bij_bestelling), of iemand vond het niet meer nodig (handel_af). Zo lang komt het terug bij "Voorgesteld om te
bestellen" op de bestellijst, en staat het per leverancier op de pagina Bestellingen."""

from helpers.producten import besteleenheid_factor, besteleenheid_naam, naar_besteleenheden


def open_manco(db):
    """De bestelregels met een open manco, nieuwste bestelling eerst. Per regel: wat er besteld en ontvangen is, het tekort
    (in de eenheid van het product en in besteleenheden), de bestelling en de leverancier van het product."""
    uit = []
    for r in db.execute(
        """SELECT br.id AS regel_id, br.bestelling_id, br.product_id, br.aantal_besteld,
                  COALESCE(br.aantal_ontvangen, 0) AS aantal_ontvangen, b.ontvangen_op, b.referentie,
                  p.naam, p.eenheid, p.besteleenheid, p.besteleenheid_factor, p.voorraad, p.leverancier_id,
                  l.naam AS leverancier_naam
           FROM bestelregels br
           JOIN bestellingen b ON b.id = br.bestelling_id
           JOIN producten p ON p.id = br.product_id
           LEFT JOIN leveranciers l ON l.id = p.leverancier_id
           WHERE b.status = 'ontvangen' AND COALESCE(br.manco_afgehandeld, 0) = 0
             AND br.aantal_besteld > COALESCE(br.aantal_ontvangen, 0)
             AND p.actief = 1 AND COALESCE(p.gearchiveerd, 0) = 0
           ORDER BY b.ontvangen_op DESC, br.id DESC"""
    ).fetchall():
        tekort = r["aantal_besteld"] - r["aantal_ontvangen"]
        uit.append({
            **dict(r),
            "tekort": tekort,
            "tekort_besteleenheden": naar_besteleenheden(tekort, r),
            "besteleenheid_naam": besteleenheid_naam(r) if besteleenheid_factor(r) > 1 else r["eenheid"],
            "niets_geleverd": r["aantal_ontvangen"] == 0,
        })
    return uit


def open_manco_per_product(db):
    """{product_id: [regels]}: alles wat van een product nog niet geleverd is (soms bij meer dan één bestelling)."""
    per_product = {}
    for m in open_manco(db):
        per_product.setdefault(m["product_id"], []).append(m)
    return per_product


def per_leverancier(db):
    """[(leverancier_naam of None, [regels])]: de open manco per leverancier, op naam (zonder leverancier achteraan)."""
    groepen = {}
    for m in open_manco(db):
        groepen.setdefault(m["leverancier_naam"], []).append(m)
    return sorted(groepen.items(), key=lambda g: (g[0] is None, (g[0] or "").lower()))


def volg_op_bij_bestelling(db, product_ids):
    """Een nieuwe bestelling met deze producten: hun open manco is daarmee opgevolgd. Commit niet."""
    ids = list(product_ids)
    if not ids:
        return
    db.execute(
        f"""UPDATE bestelregels SET manco_afgehandeld = 1
            WHERE product_id IN ({','.join('?' * len(ids))}) AND COALESCE(manco_afgehandeld, 0) = 0
              AND bestelling_id IN (SELECT id FROM bestellingen WHERE status = 'ontvangen')""",
        ids,
    )


def handel_af(db, product_id):
    """'Niet meer nodig': het open manco van dit product hoeft niet meer opgevolgd te worden."""
    volg_op_bij_bestelling(db, [product_id])
    db.commit()
