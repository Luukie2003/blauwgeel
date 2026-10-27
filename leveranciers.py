"""Leveranciers: bij wie je wat bestelt, op welke dag en vóór hoe laat.

Een product hoort bij hooguit één leverancier (producten.leverancier_id). De bestellijst laat per leverancier zien wat
er besteld moet worden, wat dat ongeveer kost en of je boven het minimum bedrag zit, met een pdf per leverancier. Op
een vaste besteldag staat op het overzicht 'Vandaag bestellen bij ...' zodra er iets onder het minimum is."""

from helpers.producten import naar_besteleenheden
from helpers.tijd import now_str
from productkaart import KEUKEN_CATEGORIE

DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
DAGEN_LANG = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
GEEN = "geen"  # filterwaarde voor producten zonder leverancier


def besteldagen(lev):
    """De besteldagen als lijst weekdagnummers (0 = maandag)."""
    return sorted({int(d) for d in (lev["besteldagen"] or "").split(",") if d.strip().isdigit() and int(d) < 7})


def besteldagen_tekst(lev):
    dagen = besteldagen(lev)
    if not dagen:
        return ""
    tekst = ", ".join(DAGEN_LANG[d] for d in dagen)
    return tekst + (f" vóór {lev['bestellen_voor']}" if lev["bestellen_voor"] else "")


def alle_leveranciers(db, alleen_actief=False):
    voorwaarde = "WHERE l.actief = 1" if alleen_actief else ""
    return db.execute(
        f"""SELECT l.*, (SELECT COUNT(*) FROM producten p WHERE p.leverancier_id = l.id AND p.actief = 1) AS aantal_producten
            FROM leveranciers l {voorwaarde} ORDER BY l.actief DESC, l.naam COLLATE NOCASE"""
    ).fetchall()


def _tekst(form, veld):
    return " ".join((form.get(veld) or "").split()) or None


def _getal(form, veld, soort=int):
    try:
        return max(0, soort((form.get(veld) or "0").replace(",", ".")))
    except ValueError:
        return 0


def bewaar_leverancier(db, form, leverancier_id=None):
    """Slaat de gegevens uit het formulier op; geeft (id, foutmelding) terug."""
    naam = _tekst(form, "naam")
    if not naam:
        return leverancier_id, "Vul een naam in."
    dubbel = db.execute(
        "SELECT id FROM leveranciers WHERE naam = ? COLLATE NOCASE AND id != ?", (naam, leverancier_id or 0)
    ).fetchone()
    if dubbel:
        return leverancier_id, f"Er is al een leverancier '{naam}'."
    waarden = (
        naam,
        _tekst(form, "contactpersoon"),
        _tekst(form, "telefoon"),
        _tekst(form, "website"),
        _tekst(form, "klantnummer"),
        _tekst(form, "bestelwijze"),
        ",".join(str(d) for d in range(7) if form.get(f"dag_{d}")),
        _tekst(form, "bestellen_voor"),
        _getal(form, "levertijd_dagen"),
        _getal(form, "minimum_bedrag", float),
        (form.get("opmerking") or "").strip() or None,
        1 if form.get("actief") else 0,
    )
    if leverancier_id:
        db.execute(
            """UPDATE leveranciers SET naam = ?, contactpersoon = ?, telefoon = ?, website = ?, klantnummer = ?,
                   bestelwijze = ?, besteldagen = ?, bestellen_voor = ?, levertijd_dagen = ?, minimum_bedrag = ?,
                   opmerking = ?, actief = ?
               WHERE id = ?""",
            (*waarden, leverancier_id),
        )
    else:
        leverancier_id = db.execute(
            """INSERT INTO leveranciers (naam, contactpersoon, telefoon, website, klantnummer, bestelwijze, besteldagen,
                   bestellen_voor, levertijd_dagen, minimum_bedrag, opmerking, actief, aangemaakt_op)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (*waarden, now_str()),
        ).lastrowid
    db.commit()
    return leverancier_id, None


def koppel_producten(db, leverancier_id, product_ids):
    """Precies deze producten horen bij de leverancier: aangevinkt wordt gekoppeld (ook als het eerst bij een ander
    hoorde), wat eerst bij deze leverancier hoorde en nu niet is aangevinkt, wordt losgekoppeld."""
    ids = {int(i) for i in product_ids if str(i).isdigit()}
    if ids:
        db.execute(
            f"UPDATE producten SET leverancier_id = NULL WHERE leverancier_id = ? AND id NOT IN ({','.join('?' * len(ids))})",
            (leverancier_id, *ids),
        )
    else:
        db.execute("UPDATE producten SET leverancier_id = NULL WHERE leverancier_id = ?", (leverancier_id,))
    if ids:
        db.execute(
            f"UPDATE producten SET leverancier_id = ? WHERE id IN ({','.join('?' * len(ids))})",
            (leverancier_id, *ids),
        )
    db.commit()


def verwijder_leverancier(db, leverancier_id):
    db.execute("UPDATE producten SET leverancier_id = NULL WHERE leverancier_id = ?", (leverancier_id,))
    db.execute("DELETE FROM leveranciers WHERE id = ?", (leverancier_id,))
    db.commit()


def bestel_aantal(p):
    """Hoeveel besteleenheden de bestellijst voorstelt (zelfde regel als in bestellijst.html)."""
    tekort = p["bestel_hoeveelheid"] if p["bestel_hoeveelheid"] > 0 else (p["min_voorraad"] - p["voorraad"])
    return naar_besteleenheden(tekort, p)


def per_leverancier(db, suggesties, vandaag=None):
    """De voorstellen van de bestellijst gegroepeerd per leverancier (wie geen leverancier heeft: apart, achteraan),
    met de geschatte inkoopwaarde en of die boven het minimum bedrag zit. Leeg als er geen leveranciers zijn."""
    leveranciers = {r["id"]: r for r in db.execute("SELECT * FROM leveranciers").fetchall()}
    if not leveranciers:
        return []
    groepen = {}
    for p in suggesties:
        lev_id = p["leverancier_id"] if p["leverancier_id"] in leveranciers else None
        groep = groepen.setdefault(lev_id, {"leverancier": leveranciers.get(lev_id), "producten": [], "waarde": 0.0})
        groep["producten"].append(p)
        groep["waarde"] += bestel_aantal(p) * (p["inkoopprijs"] or 0)
    uitkomst = []
    for lev_id, groep in groepen.items():
        lev = groep["leverancier"]
        groep["sleutel"] = lev_id or GEEN
        groep["naam"] = lev["naam"] if lev else "Geen leverancier"
        groep["besteldagen"] = besteldagen_tekst(lev) if lev else ""
        groep["vandaag"] = bool(lev and vandaag is not None and vandaag.weekday() in besteldagen(lev))
        groep["onder_minimum"] = bool(lev and lev["minimum_bedrag"] and groep["waarde"] < lev["minimum_bedrag"])
        uitkomst.append(groep)
    uitkomst.sort(key=lambda g: (g["leverancier"] is None, not g["vandaag"], g["naam"].lower()))
    return uitkomst


def filter_suggesties(suggesties, sleutel):
    """Alleen de voorstellen van één leverancier ('geen' = zonder leverancier); None of '' = alles."""
    if not sleutel:
        return suggesties
    if sleutel == GEEN:
        return [p for p in suggesties if not p["leverancier_id"]]
    return [p for p in suggesties if str(p["leverancier_id"]) == str(sleutel)]


def vandaag_bestellen(db, vandaag):
    """[(leverancier, aantal producten onder het minimum)] voor de leveranciers waar vandaag een besteldag is."""
    uitkomst = []
    for lev in alle_leveranciers(db, alleen_actief=True):
        if vandaag.weekday() not in besteldagen(lev):
            continue
        aantal = db.execute(
            """SELECT COUNT(*) FROM producten
               WHERE leverancier_id = ? AND actief = 1 AND voorraad < min_voorraad AND categorie != ?
                 AND id NOT IN (SELECT br.product_id FROM bestelregels br JOIN bestellingen b ON b.id = br.bestelling_id
                                WHERE b.status = 'besteld')""",
            (lev["id"], KEUKEN_CATEGORIE),
        ).fetchone()[0]
        if aantal:
            uitkomst.append((lev, aantal))
    return uitkomst
