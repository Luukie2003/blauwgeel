"""Producten, besteleenheden, bestelsuggesties en voorspelde tekorten."""

from flask import request


def verwerk_auto_inactief(db, product_id, nieuwe_voorraad):
    """Zet een product automatisch op inactief zodra de voorraad op 0 (of
    lager) komt -- maar alleen als de eigenaar dat voor dit product heeft
    aangevinkt (kolom auto_inactief_bij_nul) en het nu nog actief staat.
    Wordt aangeroepen vanaf elke plek die producten.voorraad bijwerkt
    (boeken, leveringen, tellen, bestelling in-/terugboeken, handmatig
    bewerken) zodat het gedrag overal hetzelfde is.

    Geeft de productnaam terug als het product hierdoor is gedeactiveerd
    (handig voor een flash-melding), anders None."""
    if nieuwe_voorraad > 0:
        return None
    product = db.execute(
        "SELECT naam, actief, auto_inactief_bij_nul FROM producten WHERE id = ?",
        (product_id,),
    ).fetchone()
    if not product or not product["auto_inactief_bij_nul"] or not product["actief"]:
        return None
    db.execute("UPDATE producten SET actief = 0 WHERE id = ?", (product_id,))
    return product["naam"]


def besteleenheid_naam(product):
    return product["besteleenheid"] or product["eenheid"]


def besteleenheid_factor(product):
    factor = product["besteleenheid_factor"] or 1
    return factor if factor > 0 else 1


def naar_besteleenheden(aantal_voorraadeenheden, product):
    """Rondt naar boven af naar hele besteleenheden (je bestelt geen halve krat)."""
    factor = besteleenheid_factor(product)
    return -(-max(0, aantal_voorraadeenheden) // factor)


def naar_voorraadeenheden(aantal_besteleenheden, product):
    return max(0, aantal_besteleenheden) * besteleenheid_factor(product)


def bewaar_subcategorie(db, categorie, subcategorie):
    """Registreert een nieuwe subcategorie automatisch zodra hij bij een
    product wordt ingevuld, zodat hij meteen ook bij andere producten te
    kiezen is -- zonder eerst naar Categorieën beheren te hoeven."""
    if not categorie or not subcategorie:
        return
    db.execute(
        "INSERT OR IGNORE INTO subcategorieen (categorie, naam) VALUES (?, ?)",
        (categorie, subcategorie),
    )


def categorienamen_zonder_verkoopprijsplicht(db):
    """Categorieën waarvoor een verkoopprijs niet verplicht is (bijv.
    fusten -- die worden nooit als geheel verkocht, alleen per glas
    getapt). Producten hierin mogen op € 0,00 staan zonder dat dit als
    ontbrekende prijs wordt gemeld."""
    return {
        r["naam"]
        for r in db.execute(
            "SELECT naam FROM categorieen WHERE verkoopprijs_verplicht = 0"
        ).fetchall()
    }


def bereken_fust_verkopen(db, limiet=100):
    """Waarschijnlijke verkopen per fust, afgeleid uit de gewone
    voorraadtellingen: als een fust-product (glazen_per_fust > 0) minder
    wordt geteld dan de vorige keer, telt dat als lege fust(en). Aantal
    glazen en bedrag zijn een schatting op basis van glazen_per_fust en
    prijs_per_glas -- er is geen registratie per getapt glas, dus 'wanneer'
    is hier net zo precies als de tellingen zelf."""
    regels = db.execute(
        """SELECT t.datum, p.naam AS product_naam, tr.verkocht,
                  p.glazen_per_fust, p.prijs_per_glas
           FROM telling_regels tr
           JOIN tellingen t ON t.id = tr.telling_id
           JOIN producten p ON p.id = tr.product_id
           WHERE p.glazen_per_fust > 0 AND tr.verkocht > 0
           ORDER BY t.datum DESC, t.id DESC
           LIMIT ?""",
        (limiet,),
    ).fetchall()

    gebeurtenissen = []
    totaal_fusten = 0
    totaal_glazen = 0
    totaal_bedrag = 0.0
    for r in regels:
        glazen = r["verkocht"] * r["glazen_per_fust"]
        bedrag = glazen * r["prijs_per_glas"]
        gebeurtenissen.append(
            {
                "datum": r["datum"],
                "product_naam": r["product_naam"],
                "aantal_fusten": r["verkocht"],
                "glazen": glazen,
                "bedrag": bedrag,
            }
        )
        totaal_fusten += r["verkocht"]
        totaal_glazen += glazen
        totaal_bedrag += bedrag

    return {
        "gebeurtenissen": gebeurtenissen,
        "totaal_fusten": totaal_fusten,
        "totaal_glazen": totaal_glazen,
        "totaal_bedrag": totaal_bedrag,
    }


def vervang_product_prijsopties(db, product_id):
    """Slaat de prijsopties van een product op vanuit het formulier
    (parallelle 'optie_naam'/'optie_prijs'-lijsten, zie product_form.html) --
    bestaande opties worden eerst verwijderd en dan opnieuw ingevoegd, net
    als bij subcategorieën. Rijen met een lege naam (een leeggelaten extra
    rij in de bouwer) worden overgeslagen."""
    db.execute("DELETE FROM product_prijsopties WHERE product_id = ?", (product_id,))
    namen = request.form.getlist("optie_naam")
    prijzen = request.form.getlist("optie_prijs")
    volgorde = 0
    for naam, prijs in zip(namen, prijzen):
        naam = naam.strip()
        if not naam:
            continue
        try:
            prijs_waarde = float(prijs or 0)
        except ValueError:
            prijs_waarde = 0.0
        db.execute(
            "INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES (?, ?, ?, ?)",
            (product_id, naam, prijs_waarde, volgorde),
        )
        volgorde += 1


def bestel_suggesties(db):
    product_ids_in_open_bestelling = {
        row["product_id"]
        for row in db.execute(
            """SELECT br.product_id FROM bestelregels br
               JOIN bestellingen b ON b.id = br.bestelling_id
               WHERE b.status = 'besteld'"""
        ).fetchall()
    }
    return [
        p
        for p in db.execute(
            """SELECT * FROM producten
               WHERE actief = 1 AND voorraad < min_voorraad
               ORDER BY categorie, naam"""
        ).fetchall()
        if p["id"] not in product_ids_in_open_bestelling
    ]


def regels_per_bestelling(db, bestelling_ids):
    """Haalt de bestelregels voor meerdere bestellingen in één query op,
    gegroepeerd per bestelling_id -- voorkomt een aparte query per
    bestelling in een loop (bestellijst() toont dit al snel voor tien-tallen
    bestellingen tegelijk)."""
    if not bestelling_ids:
        return {}
    placeholders = ",".join("?" * len(bestelling_ids))
    per_bestelling = {}
    for regel in db.execute(
        f"""SELECT br.*, p.naam AS product_naam, p.eenheid,
                   p.besteleenheid, p.besteleenheid_factor
            FROM bestelregels br JOIN producten p ON p.id = br.product_id
            WHERE br.bestelling_id IN ({placeholders})""",
        bestelling_ids,
    ).fetchall():
        per_bestelling.setdefault(regel["bestelling_id"], []).append(regel)
    return per_bestelling


def bereken_voorspelde_tekorten(db, dagen_vooruit=7):
    """Producten die waarschijnlijk uitverkocht raken in de komende
    `dagen_vooruit` dagen, ook als de voorraad nu nog boven het minimum zit --
    in tegenstelling tot bestel_suggesties(), dat pas waarschuwt als het al te
    laat is. Gebruikt het voorspelmodel in voorspelling.py (leert uit de eigen
    tellingen hoeveel een thuiswedstrijd, trainingsavond en het weer
    uitmaken). Een product dat al onder het minimum zit en dus op de
    bestellijst staat, of waarvan de vraag al gedekt is door een bestelling die
    onderweg is, komt hier niet nog eens in."""
    from voorspelling import maak_prognose

    try:
        prognose = maak_prognose(db, dagen=dagen_vooruit)
    except Exception as fout:  # de bestellijst mag nooit stuk gaan door de voorspelling
        print(f"[voorspelling] mislukt: {fout}")
        return []
    if not prognose["beschikbaar"]:
        return []
    resultaat = []
    for p in prognose["producten"]:
        tekort = p["verwacht"] - p["voorraad"] - p["onderweg"]
        if p["al_op_bestellijst"] or tekort <= 0:
            continue
        resultaat.append(
            {
                "product": p["product"],
                "verwacht_verbruik": round(p["verwacht"]),
                "verwacht_tekort": round(tekort),
                "kans_tekort": p["kans_tekort"],
                "advies_stuks": p["advies_stuks"],
                "advies_eenheden": p["advies_eenheden"],
                "besteleenheid": p["besteleenheid"],
            }
        )
    resultaat.sort(key=lambda x: x["verwacht_tekort"], reverse=True)
    return resultaat


def bereken_bestellijst_meldingen(db):
    """Onafgehandelde meldingen voor de bestellijst die niet uit de gewone
    voorraadberekening komen: bezoekers die zonder account de QR-code van
    een product scanden en op 'Melden voor bestellijst' drukten (per
    product gegroepeerd, met een teller en het laatste tijdstip), en losse
    tekstmeldingen voor verbruiksvoorwerpen die een beheerder handmatig op
    de bestellijst heeft gezet. Zie bestellijst_meldingen in schema.sql."""
    product_rijen = db.execute(
        """SELECT product_id, COUNT(*) AS aantal, MAX(aangemaakt_op) AS laatste_melding
           FROM bestellijst_meldingen
           WHERE afgehandeld = 0 AND product_id IS NOT NULL
           GROUP BY product_id
           ORDER BY laatste_melding DESC"""
    ).fetchall()
    # Alle gemelde producten in 1 keer ophalen i.p.v. per melding een losse
    # SELECT -- volgorde van product_rijen (laatste_melding DESC) blijft
    # behouden doordat we daarover blijven itereren, niet over de query hier.
    producten_bij_id = {}
    if product_rijen:
        plekhouders = ",".join("?" * len(product_rijen))
        producten_bij_id = {
            p["id"]: p
            for p in db.execute(
                f"SELECT * FROM producten WHERE id IN ({plekhouders})",
                tuple(r["product_id"] for r in product_rijen),
            ).fetchall()
        }
    producten_gemeld = []
    for r in product_rijen:
        product = producten_bij_id.get(r["product_id"])
        if product is None:
            continue
        producten_gemeld.append(
            {"product": product, "aantal": r["aantal"], "laatste_melding": r["laatste_melding"]}
        )

    tekst_meldingen = db.execute(
        """SELECT * FROM bestellijst_meldingen
           WHERE afgehandeld = 0 AND product_id IS NULL
           ORDER BY aangemaakt_op DESC"""
    ).fetchall()

    return {"producten": producten_gemeld, "teksten": tekst_meldingen}
