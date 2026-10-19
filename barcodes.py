"""Barcodes (EAN): welk artikel je precies inkoopt, en bij welk product het hoort.

Een product is wat je telt en verkoopt, en wat op de overzichten staat (bijvoorbeeld 'Witte wijn' of 'Frikandel'). Een
artikel is wat je daarvoor koopt: een merk en verpakking met een eigen barcode en inkoopprijs ('AH frikandellen, zak
van 20' of 'Chardonnay Les Jamelles, fles'). Meerdere artikelen kunnen bij hetzelfde product horen; op de overzichten
blijft het één product.

Heeft een product artikelen met een inkoopprijs, dan is de inkoopprijs van het product het gemiddelde daarvan per
eenheid (werk_inkoopprijs_bij): zolang er nog geen facturen gescand worden, weet de site niet hoeveel je van welk artikel
koopt, dus tellen ze even zwaar. Is er geen enkel artikel met een prijs, dan blijft de zelf ingevulde prijs staan.

Een artikel heeft hooguit twee barcodes: die van de verpakking zelf (zak, fles, blik) en die van de omverpakking (doos,
tray, krat) met een aantal verpakkingen erin. Elke barcode hoort bij precies één artikel. Scan je er een, dan weet de
site hoeveel van het product het is en wat het kost (zoek_barcode); dat is de basis voor het inboeken van facturen met
de handterminal."""

import re

from helpers.producten import besteleenheid_factor
from helpers.tijd import now_str

GELDIGE_LENGTES = (8, 13, 14)  # EAN-8, EAN-13 (UPC-A wordt 13) en de 14 cijfers van een doos (GTIN-14 / ITF-14)


def normaliseer(tekst):
    """De barcode in één vaste vorm, zodat dezelfde code altijd hetzelfde opgeslagen wordt: alleen cijfers, een UPC-A
    van 12 cijfers met een 0 ervoor (zo leest een scanner hem als EAN-13), en een doos-code van 14 cijfers die met 0
    begint zonder die 0 (dan is het gewoon dezelfde EAN-13). None als het geen getal is."""
    code = re.sub(r"\s+", "", tekst or "")
    if not code.isdigit():
        return None
    if len(code) == 12:
        code = "0" + code
    if len(code) == 14 and code.startswith("0"):
        code = code[1:]
    return code


def controlecijfer_klopt(code):
    """Het laatste cijfer van een EAN/GTIN is een controlecijfer (GS1): zo valt een tikfout meteen op."""
    if not code or not code.isdigit() or len(code) not in GELDIGE_LENGTES:
        return False
    cijfers = [int(c) for c in code]
    som = sum(c * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(cijfers[:-1])))
    return (10 - som % 10) % 10 == cijfers[-1]


def controleer(tekst):
    """(code, foutmelding): de genormaliseerde code, of None met een foutmelding. Leeg geeft (None, None)."""
    if not (tekst or "").strip():
        return None, None
    code = normaliseer(tekst)
    if code is None or len(code) not in GELDIGE_LENGTES:
        return None, f"'{tekst.strip()}' is geen barcode: een EAN heeft 8 of 13 cijfers, die van een doos soms 14."
    if not controlecijfer_klopt(code):
        return None, f"Barcode {code} klopt niet (het laatste cijfer hoort anders te zijn). Controleer de cijfers."
    return code, None


# ---------------------------------------------------------------------------
# Opzoeken
# ---------------------------------------------------------------------------

_ARTIKEL_SELECT = """
    SELECT a.*, p.naam AS product_naam, p.categorie, p.subcategorie, p.eenheid, p.voorraad, p.actief AS product_actief,
           COALESCE(p.gearchiveerd, 0) AS product_gearchiveerd, l.naam AS leverancier_naam
    FROM artikelen a
    JOIN producten p ON p.id = a.product_id
    LEFT JOIN leveranciers l ON l.id = a.leverancier_id
"""


def _bedrag(waarde):
    return f"€ {waarde:.2f}".replace(".", ",")


def per_eenheid(artikel):
    """De inkoopprijs per eenheid van het product (een frikandel, een fles), om artikelen te vergelijken."""
    aantal = artikel["aantal_per_verpakking"] or 1
    return (artikel["inkoopprijs"] or 0) / aantal


def omschrijving(artikel, niveau="verpakking"):
    """Bijvoorbeeld 'AH frikandellen, 20 stuks, € 20,00' of voor de doos 'AH frikandellen, doos van 4 (80 stuks),
    € 80,00'."""
    eenheid = artikel["eenheid"]
    if niveau == "omverpakking":
        aantal = artikel["aantal_per_verpakking"] * artikel["per_omverpakking"]
        return (f"{artikel['naam']}, doos van {artikel['per_omverpakking']} ({aantal} {eenheid}), "
                f"{_bedrag(artikel['inkoopprijs'] * artikel['per_omverpakking'])}")
    return f"{artikel['naam']}, {artikel['aantal_per_verpakking']} {eenheid}, {_bedrag(artikel['inkoopprijs'])}"


def zoek_barcode(db, tekst):
    """Wat er achter een gescande barcode zit:
    {"code", "geldig", "melding", "bekend", "niveau" ('verpakking' of 'omverpakking'), "artikel", "aantal" (in de
    eenheid van het product), "inkoopprijs" (voor wat je gescand hebt), "omschrijving", "suggestie"}.
    Is de code onbekend maar lijkt het de doos van een bekend artikel (een doos-code van 14 cijfers bevat de EAN van
    wat erin zit), dan staat dat artikel in "suggestie"."""
    code, fout = controleer(tekst)
    uitkomst = {"code": code or (tekst or "").strip(), "geldig": code is not None, "melding": fout, "bekend": False,
                "niveau": None, "artikel": None, "aantal": None, "inkoopprijs": None, "omschrijving": None,
                "suggestie": None}
    if code is None:
        return uitkomst
    artikel = db.execute(_ARTIKEL_SELECT + " WHERE a.ean = ? OR a.ean_omverpakking = ?", (code, code)).fetchone()
    if artikel is None:
        uitkomst["suggestie"] = _artikel_in_doos(db, code)
        return uitkomst
    niveau = "verpakking" if artikel["ean"] == code else "omverpakking"
    per_scan = artikel["per_omverpakking"] if niveau == "omverpakking" else 1
    uitkomst.update(
        bekend=True,
        niveau=niveau,
        artikel=artikel,
        aantal=artikel["aantal_per_verpakking"] * per_scan,
        inkoopprijs=round((artikel["inkoopprijs"] or 0) * per_scan, 2),
        omschrijving=omschrijving(artikel, niveau),
    )
    return uitkomst


def _artikel_in_doos(db, code):
    """Een doos-code van 14 cijfers is (op het eerste en het laatste cijfer na) de EAN-13 van wat erin zit."""
    if len(code) != 14:
        return None
    for artikel in db.execute(_ARTIKEL_SELECT + " WHERE a.ean IS NOT NULL AND length(a.ean) = 13").fetchall():
        if artikel["ean"][:12] == code[1:13]:
            return artikel
    return None


def artikelen_van(db, product_id):
    return db.execute(_ARTIKEL_SELECT + " WHERE a.product_id = ? ORDER BY a.naam COLLATE NOCASE", (product_id,)).fetchall()


def alle_artikelen(db, zoekterm=""):
    term = (zoekterm or "").strip()
    if not term:
        return db.execute(_ARTIKEL_SELECT + " ORDER BY p.categorie, p.naam COLLATE NOCASE, a.naam COLLATE NOCASE").fetchall()
    patroon = f"%{term}%"
    code = normaliseer(term)
    return db.execute(
        _ARTIKEL_SELECT
        + """ WHERE a.naam LIKE ? OR a.merk LIKE ? OR p.naam LIKE ? OR a.ean LIKE ? OR a.ean_omverpakking LIKE ?
                    OR a.ean = ? OR a.ean_omverpakking = ?
              ORDER BY p.categorie, p.naam COLLATE NOCASE, a.naam COLLATE NOCASE""",
        (patroon, patroon, patroon, patroon, patroon, code, code),
    ).fetchall()


def artikel(db, artikel_id):
    return db.execute(_ARTIKEL_SELECT + " WHERE a.id = ?", (artikel_id,)).fetchone()


# ---------------------------------------------------------------------------
# Opslaan
# ---------------------------------------------------------------------------


def barcode_in_gebruik(db, code, behalve_artikel_id=None):
    """Het artikel dat deze barcode al heeft (als artikel of als doos), of None."""
    return db.execute(
        """SELECT a.id, a.naam, p.naam AS product_naam FROM artikelen a JOIN producten p ON p.id = a.product_id
           WHERE (a.ean = ? OR a.ean_omverpakking = ?) AND a.id != ?""",
        (code, code, behalve_artikel_id or 0),
    ).fetchone()


def _getal(form, veld, soort=int, standaard=0):
    try:
        return soort(str(form.get(veld) or "").replace(",", ".").strip() or standaard)
    except ValueError:
        return None


def inkoop_uit_artikelen(db, product_id):
    """{"per_eenheid": het gemiddelde, "artikelen": [(naam, prijs per eenheid)]} van de artikelen van dit product met
    een inkoopprijs, of None als er geen is."""
    rijen = db.execute(
        """SELECT naam, inkoopprijs, aantal_per_verpakking FROM artikelen
           WHERE product_id = ? AND inkoopprijs > 0 ORDER BY naam COLLATE NOCASE""",
        (product_id,),
    ).fetchall()
    if not rijen:
        return None
    prijzen = [(r["naam"], per_eenheid(r)) for r in rijen]
    return {"per_eenheid": sum(p for _, p in prijzen) / len(prijzen), "artikelen": prijzen}


def werk_inkoopprijs_bij(db, product_id, door=None, gebruiker_id=None):
    """Zet de inkoopprijs van het product (per besteleenheid, zoals altijd) op het gemiddelde van zijn artikelen, met
    een regel in de prijsgeschiedenis als hij verandert. Zonder artikelen met een prijs verandert er niets. Commit niet."""
    uit = inkoop_uit_artikelen(db, product_id)
    product = db.execute("SELECT inkoopprijs, besteleenheid_factor FROM producten WHERE id = ?", (product_id,)).fetchone()
    if uit is None or product is None:
        return None
    nieuw = round(uit["per_eenheid"] * besteleenheid_factor(product), 4)
    oud = product["inkoopprijs"] or 0
    if abs(nieuw - oud) > 0.001:
        db.execute("UPDATE producten SET inkoopprijs = ? WHERE id = ?", (nieuw, product_id))
        db.execute(
            """INSERT INTO prijs_geschiedenis (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id)
               VALUES (?, 'inkoopprijs', ?, ?, ?, ?, ?)""",
            (product_id, oud, nieuw, now_str(), door, gebruiker_id),
        )
    return nieuw


def bewaar_artikel(db, form, artikel_id=None, door=None, gebruiker_id=None):
    """Slaat een artikel op uit het formulier; geeft (id, foutmelding) terug. Werkt daarna de inkoopprijs van het
    product bij (en van het vorige product, als het artikel verhuist)."""
    naam = " ".join(str(form.get("naam") or "").split())
    if not naam:
        return artikel_id, "Vul de naam van het artikel in, bijvoorbeeld 'AH frikandellen'."
    product_id = _getal(form, "product_id")
    if not product_id or db.execute("SELECT 1 FROM producten WHERE id = ?", (product_id,)).fetchone() is None:
        return artikel_id, "Kies bij welk product dit artikel hoort."
    aantal = _getal(form, "aantal_per_verpakking", int, 1)
    if aantal is None or aantal < 1:
        return artikel_id, "Vul bij 'Hoeveel zit erin' een heel getal van 1 of meer in."
    inkoopprijs = _getal(form, "inkoopprijs", float, 0)
    if inkoopprijs is None or inkoopprijs < 0:
        return artikel_id, "Vul een geldige inkoopprijs in (bijvoorbeeld 4,50), of laat 'm leeg."
    per_omverpakking = _getal(form, "per_omverpakking", int, 0)
    if per_omverpakking is None or per_omverpakking < 0:
        return artikel_id, "Vul bij 'Hoeveel in de doos' een heel getal in, of laat het leeg."
    ean, fout = controleer(str(form.get("ean") or ""))
    if fout:
        return artikel_id, fout
    ean_doos, fout = controleer(str(form.get("ean_omverpakking") or ""))
    if fout:
        return artikel_id, fout
    if ean_doos and per_omverpakking < 1:
        return artikel_id, "Vul in hoeveel er in de doos zitten; zonder dat aantal weet de site niet wat een gescande doos is."
    if ean and ean == ean_doos:
        return artikel_id, "De barcode van het artikel en die van de doos zijn hetzelfde; vul de doos-barcode alleen in als die anders is."
    for code in (ean, ean_doos):
        if code and (bezet := barcode_in_gebruik(db, code, artikel_id)):
            return artikel_id, f"Barcode {code} hoort al bij '{bezet['naam']}' ({bezet['product_naam']})."
    leverancier_id = _getal(form, "leverancier_id") or None
    vorig = db.execute("SELECT product_id FROM artikelen WHERE id = ?", (artikel_id or 0,)).fetchone()
    waarden = (
        product_id,
        naam,
        " ".join((form.get("merk") or "").split()) or None,
        leverancier_id,
        ean,
        aantal,
        round(inkoopprijs, 4),
        ean_doos,
        per_omverpakking,
        (form.get("opmerking") or "").strip() or None,
    )
    if artikel_id:
        db.execute(
            """UPDATE artikelen SET product_id = ?, naam = ?, merk = ?, leverancier_id = ?, ean = ?,
                   aantal_per_verpakking = ?, inkoopprijs = ?, ean_omverpakking = ?, per_omverpakking = ?, opmerking = ?,
                   bijgewerkt_op = ?
               WHERE id = ?""",
            (*waarden, now_str(), artikel_id),
        )
    else:
        artikel_id = db.execute(
            """INSERT INTO artikelen (product_id, naam, merk, leverancier_id, ean, aantal_per_verpakking, inkoopprijs,
                   ean_omverpakking, per_omverpakking, opmerking, aangemaakt_op)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (*waarden, now_str()),
        ).lastrowid
    for pid in {product_id, vorig["product_id"] if vorig else product_id}:
        werk_inkoopprijs_bij(db, pid, door, gebruiker_id)
    db.commit()
    return artikel_id, None


def koppel_doos(db, artikel_id, tekst, per_omverpakking):
    """Zet een (nieuw gescande) barcode als doos bij een bestaand artikel. Geeft een foutmelding of None terug."""
    code, fout = controleer(tekst)
    if fout or code is None:
        return fout or "Geen barcode ingevuld."
    try:
        aantal = int(per_omverpakking)
    except (TypeError, ValueError):
        aantal = 0
    if aantal < 1:
        return "Vul in hoeveel er in de doos zitten."
    if db.execute("SELECT 1 FROM artikelen WHERE id = ?", (artikel_id,)).fetchone() is None:
        return "Kies het artikel dat in de doos zit."
    if bezet := barcode_in_gebruik(db, code, artikel_id):
        return f"Barcode {code} hoort al bij '{bezet['naam']}' ({bezet['product_naam']})."
    if db.execute("SELECT 1 FROM artikelen WHERE id = ? AND ean = ?", (artikel_id, code)).fetchone():
        return "Dit is de barcode van het artikel zelf, niet van de doos."
    db.execute(
        "UPDATE artikelen SET ean_omverpakking = ?, per_omverpakking = ?, bijgewerkt_op = ? WHERE id = ?",
        (code, aantal, now_str(), artikel_id),
    )
    db.commit()
    return None


def snel_koppelen(db, tekst, product_id, per_doos=None, door=None, gebruiker_id=None):
    """Koppelt een gescande barcode in één stap aan een product, zonder verder iets in te vullen: zonder per_doos is het
    één verpakking (een fles, een blik), met per_doos een doos of krat met zoveel erin, geteld in de eenheid van het
    product (een krat met 24 flessen: 24). Het artikel krijgt de naam van
    het product; merk, leverancier en inkoopprijs kunnen later nog op de barcodepagina. Heeft het product al een artikel
    waar dit stukje nog ontbreekt (een fles zonder doos-barcode, of andersom), dan komt de barcode daarbij.
    Geeft (artikel_id, foutmelding) terug."""
    code, fout = controleer(tekst)
    if fout or code is None:
        return None, fout or "Scan of typ eerst een barcode."
    try:
        product_id = int(product_id or 0)
    except (TypeError, ValueError):
        product_id = 0
    product = db.execute("SELECT id, naam FROM producten WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        return None, "Kies bij welk product deze barcode hoort."
    if bezet := barcode_in_gebruik(db, code):
        return None, f"Barcode {code} hoort al bij '{bezet['naam']}' ({bezet['product_naam']})."
    if per_doos in (None, "", 0, "0"):
        zonder_fles = db.execute(
            "SELECT id FROM artikelen WHERE product_id = ? AND ean IS NULL ORDER BY id LIMIT 1", (product_id,)
        ).fetchone()
        if zonder_fles:
            db.execute("UPDATE artikelen SET ean = ?, bijgewerkt_op = ? WHERE id = ?",
                       (code, now_str(), zonder_fles["id"]))
            db.commit()
            return zonder_fles["id"], None
        return bewaar_artikel(db, {"product_id": product_id, "naam": product["naam"], "ean": code},
                              door=door, gebruiker_id=gebruiker_id)
    try:
        per_doos = int(per_doos)
    except (TypeError, ValueError):
        per_doos = 0
    if per_doos < 1:
        return None, "Vul in hoeveel er in de doos of krat zitten."
    # Een artikel zonder doos-barcode waar het aantal in past: een doos van 60 frikandellen bij de zak van 20 is een
    # doos van 3 zakken.
    for artikel in db.execute(
        """SELECT id, aantal_per_verpakking FROM artikelen WHERE product_id = ? AND ean_omverpakking IS NULL
           ORDER BY id""", (product_id,),
    ).fetchall():
        per_verpakking = artikel["aantal_per_verpakking"] or 1
        if per_doos % per_verpakking == 0:
            fout = koppel_doos(db, artikel["id"], code, per_doos // per_verpakking)
            return (None, fout) if fout else (artikel["id"], None)
    return bewaar_artikel(
        db, {"product_id": product_id, "naam": product["naam"], "ean_omverpakking": code, "per_omverpakking": per_doos},
        door=door, gebruiker_id=gebruiker_id,
    )


def verwijder_artikel(db, artikel_id, door=None, gebruiker_id=None):
    rij = db.execute("SELECT product_id FROM artikelen WHERE id = ?", (artikel_id,)).fetchone()
    db.execute("DELETE FROM artikelen WHERE id = ?", (artikel_id,))
    if rij:
        werk_inkoopprijs_bij(db, rij["product_id"], door, gebruiker_id)
    db.commit()


def als_json(uitkomst):
    """zoek_barcode() als JSON voor de app op de handterminal."""
    a = uitkomst["artikel"]
    return {
        "code": uitkomst["code"],
        "geldig": uitkomst["geldig"],
        "melding": uitkomst["melding"],
        "bekend": uitkomst["bekend"],
        "niveau": uitkomst["niveau"],
        "aantal": uitkomst["aantal"],
        "inkoopprijs": uitkomst["inkoopprijs"],
        "omschrijving": uitkomst["omschrijving"],
        "artikel": None if a is None else {
            "id": a["id"],
            "naam": a["naam"],
            "merk": a["merk"],
            "leverancier": a["leverancier_naam"],
            "ean": a["ean"],
            "ean_omverpakking": a["ean_omverpakking"],
            "aantal_per_verpakking": a["aantal_per_verpakking"],
            "per_omverpakking": a["per_omverpakking"],
            "inkoopprijs_per_verpakking": a["inkoopprijs"],
        },
        "product": None if a is None else {
            "id": a["product_id"],
            "naam": a["product_naam"],
            "categorie": a["categorie"],
            "eenheid": a["eenheid"],
            "voorraad": a["voorraad"],
        },
        "suggestie": None if uitkomst["suggestie"] is None else {
            "artikel_id": uitkomst["suggestie"]["id"],
            "naam": uitkomst["suggestie"]["naam"],
            "product": uitkomst["suggestie"]["product_naam"],
        },
    }
