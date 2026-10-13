"""Gegevenscontrole: wat er aan de productgegevens niet klopt of ontbreekt, zodat marge, bestellijst en prognose kloppen.

Elke controle geeft een lijst producten met een korte toelichting. De pagina (Producten > Gegevenscontrole, beheerders)
zet ze onder elkaar, het belangrijkste eerst. De fout van 1.44.1 (inkoopprijs per krat als prijs per stuk gerekend) en
het tapbier dat nergens meetelde, hadden hier allebei tussen gestaan."""

from helpers.producten import categorienamen_zonder_verkoopprijsplicht, inkoop_per_stuk, omzet_per_eenheid
from productkaart import BESTELEENHEDEN, EENHEDEN, KEUKEN_CATEGORIE, NIET_GEARCHIVEERD, in_gewone_telling, normaliseer

HOGE_MARGE_PCT = 85  # daarboven is de inkoopprijs waarschijnlijk per stuk ingevuld in plaats van per krat
ERNST_VOLGORDE = {"hoog": 0, "middel": 1, "laag": 2}


def _bedrag(x):
    return f"€ {x:.2f}".replace(".", ",")


def _controle(sleutel, titel, uitleg, ernst, regels):
    return {"sleutel": sleutel, "titel": titel, "uitleg": uitleg, "ernst": ernst, "regels": regels}


def _regel(p, detail=""):
    return {"id": p["id"], "naam": p["naam"], "categorie": p["categorie"], "actief": bool(p["actief"]), "detail": detail}


def controleer(db):
    """Alle controles, met de controles zonder bevindingen apart: {'controles': [...], 'in_orde': [...], 'aantal'}."""
    producten = db.execute(
        f"SELECT * FROM producten WHERE {NIET_GEARCHIVEERD} ORDER BY categorie, naam COLLATE NOCASE"
    ).fetchall()
    actief = [p for p in producten if p["actief"]]
    zonder_prijsplicht = categorienamen_zonder_verkoopprijsplicht(db)
    geteld = {r[0] for r in db.execute("SELECT DISTINCT product_id FROM telling_regels").fetchall()}

    controles = []

    regels = []
    for p in actief:
        verkoop, inkoop = omzet_per_eenheid(p), inkoop_per_stuk(p)
        if verkoop > 0 and inkoop > 0 and verkoop < inkoop:
            regels.append(_regel(p, f"verkoop {_bedrag(verkoop)}, inkoop per {(p['eenheid'] or 'stuk').lower()} {_bedrag(inkoop)}"))
    controles.append(_controle(
        "onder_inkoop", "Verkoopprijs onder de inkoopprijs",
        "Op elk verkocht stuk wordt verlies gemaakt, of de inkoopprijs of het aantal per besteleenheid klopt niet.",
        "hoog", regels,
    ))

    regels = []
    for p in actief:
        verkoop, inkoop = omzet_per_eenheid(p), inkoop_per_stuk(p)
        if verkoop > 0 and inkoop > 0 and (verkoop - inkoop) / verkoop * 100 > HOGE_MARGE_PCT:
            marge = (verkoop - inkoop) / verkoop * 100
            regels.append(_regel(p, f"{marge:.0f}% marge: is de inkoopprijs per {p['besteleenheid'] or p['eenheid']} ingevuld?"))
    controles.append(_controle(
        "hoge_marge", f"Marge boven {HOGE_MARGE_PCT}%",
        "Zo veel verdien je zelden: vaak staat de inkoopprijs per stuk ingevuld terwijl hij per krat of doos hoort.",
        "middel", regels,
    ))

    regels = []
    for p in actief:
        if p["besteleenheid"] and p["besteleenheid"].lower() != (p["eenheid"] or "").lower() and (p["besteleenheid_factor"] or 1) <= 1:
            regels.append(_regel(p, f"1 {p['besteleenheid']} = 1 {p['eenheid']}?"))
    controles.append(_controle(
        "besteleenheid_zonder_aantal", "Besteleenheid zonder aantal",
        "Er staat een besteleenheid (zoals Krat), maar niet hoeveel stuks erin zitten. Dan klopt de inkoopprijs per stuk niet.",
        "hoog", regels,
    ))

    regels = []
    for p in actief:
        if (p["eenheid"] or "").lower() == "fust" and (p["glazen_per_fust"] <= 0 or p["prijs_per_glas"] <= 0):
            regels.append(_regel(p, "glazen per fust of prijs per glas ontbreekt"))
    controles.append(_controle(
        "fust_zonder_glazen", "Fust zonder glazen of glasprijs",
        "Een leeg fust telt pas mee in de omzet als glazen per fust en de prijs per glas zijn ingevuld.",
        "hoog", regels,
    ))

    regels = []
    for p in actief:
        if p["categorie"] in zonder_prijsplicht or p["niet_tellen"] or (p["eenheid"] or "").lower() == "fust":
            continue  # een fust staat al bij 'Fust zonder glazen of glasprijs' als het daar ontbreekt
        if omzet_per_eenheid(p) <= 0:
            regels.append(_regel(p))
    controles.append(_controle(
        "geen_verkoopprijs", "Geen verkoopprijs",
        "Wat verkocht wordt telt voor € 0 in de omzet.",
        "hoog", regels,
    ))

    controles.append(_controle(
        "geen_inkoopprijs", "Geen inkoopprijs",
        "Zonder inkoopprijs valt er niets over de marge te zeggen.",
        "middel", [_regel(p, p["categorie"]) for p in actief if p["inkoopprijs"] <= 0],
    ))

    regels = []
    for p in actief:
        if (in_gewone_telling(p) or p["categorie"] == KEUKEN_CATEGORIE) and p["min_voorraad"] <= 0:
            regels.append(_regel(p, f"voorraad {p['voorraad']} {p['eenheid']}"))
    controles.append(_controle(
        "geen_minimum", "Geen minimumvoorraad",
        "Zonder minimum komt het product nooit vanzelf op de bestellijst. Bewust? Zet het dan op 'Niet tellen' of op inactief.",
        "middel", regels,
    ))

    dubbel = {}
    for p in producten:
        code = (p["artikelcode"] or "").strip().upper()
        if code:
            dubbel.setdefault(code, []).append(p)
    regels = [_regel(p, f"artikelcode {code}") for code, lijst in sorted(dubbel.items()) if len(lijst) > 1 for p in lijst]
    controles.append(_controle(
        "dubbele_artikelcode", "Dubbele artikelcode",
        "Twee producten met dezelfde code: bij scannen of een prijslijst inlezen is niet duidelijk welke bedoeld is.",
        "middel", regels,
    ))

    controles.append(_controle(
        "nooit_geteld", "Nog nooit geteld",
        "Staat in de gewone telling maar is nooit geteld, dus er is nog geen verkoop of omzet van bekend.",
        "laag", [_regel(p) for p in actief if in_gewone_telling(p) and p["id"] not in geteld],
    ))

    regels = []
    for p in producten:
        afwijkend = []
        if p["eenheid"] and normaliseer(p["eenheid"], EENHEDEN) not in EENHEDEN:
            afwijkend.append(f"eenheid '{p['eenheid']}'")
        elif p["eenheid"] and p["eenheid"] not in EENHEDEN:
            afwijkend.append(f"eenheid '{p['eenheid']}' (schrijfwijze: {normaliseer(p['eenheid'], EENHEDEN)})")
        if p["besteleenheid"] and normaliseer(p["besteleenheid"], BESTELEENHEDEN) not in BESTELEENHEDEN:
            afwijkend.append(f"besteleenheid '{p['besteleenheid']}'")
        elif p["besteleenheid"] and p["besteleenheid"] not in BESTELEENHEDEN:
            afwijkend.append(f"besteleenheid '{p['besteleenheid']}' (schrijfwijze: {normaliseer(p['besteleenheid'], BESTELEENHEDEN)})")
        if afwijkend:
            regels.append(_regel(p, ", ".join(afwijkend)))
    controles.append(_controle(
        "afwijkende_eenheid", "Eenheid buiten de vaste lijst",
        "Kies op de productkaart een eenheid uit de lijst, zodat bijvoorbeeld 'Fles' en 'Flesje' niet door elkaar staan.",
        "laag", regels,
    ))

    controles.append(_controle(
        "inactief_met_voorraad", "Inactief, maar nog voorraad",
        "Deze voorraad telt nergens mee. Zet het product weer actief of boek de voorraad uit.",
        "laag", [_regel(p, f"{p['voorraad']} {p['eenheid']}") for p in producten if not p["actief"] and p["voorraad"] > 0],
    ))

    controles.sort(key=lambda c: ERNST_VOLGORDE[c["ernst"]])
    met = [c for c in controles if c["regels"]]
    return {
        "controles": met,
        "in_orde": [c for c in controles if not c["regels"]],
        "aantal": sum(len(c["regels"]) for c in met),
    }
