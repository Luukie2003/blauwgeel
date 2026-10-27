"""De keuken als eigen module: voorraad tellen, inboeken en verkoopprijzen, los van de gewone telling.

De keukenproducten blijven gewone producten in de categorie Keuken (productkaart.KEUKEN_CATEGORIE), maar staan niet in
de gewone telling of de looplijst. De keuken telt apart: wat er sinds de vorige keukentelling minder is (na wat er is
ingeboekt), is verkocht. Die omzet staat bij de keukentellingen en telt mee in Marge en in Omzet en kassa, maar niet
in de weekomzet en de prognose van de kantine.

Inkoop gaat per verpakking en de voorraad in porties of stuks. Wat er in een verpakking zit, verschilt per merk (een
zak AH frikandellen van 20, een doos Plus van 15): dat staat bij de gekoppelde barcodes (artikelen), en zonder barcode
bij het product zelf ('aantal per besteleenheid'). De keuken boekt nooit per stuk in, alleen per verpakking
(keuken_verpakkingen); tellen mag wel per stuk. Wat er weggegooid wordt, boek je als derving (muteer_keuken), anders
telt het bij de volgende telling als verkocht. Zit een product onder zijn minimum, dan komt het op de
boodschappenlijst; bij het inboeken gaat het er weer af (de keuken bestelt niet via de bestellijst)."""

import json
from datetime import date, datetime, timedelta

import barcodes
from derving import DERVING_REDENEN
from helpers.producten import besteleenheid_factor, boek_mutatie, inkoop_per_stuk, omzet_per_eenheid, verwerk_auto_inactief
from helpers.tijd import now_str
from productkaart import KEUKEN_CATEGORIE, NIET_GEARCHIVEERD

KEUKEN_NIET_BESTELLEN = ("Keukenspullen staan niet op de bestellijst: de keuken koopt zelf in. Zet het op de "
                         "boodschappenlijst (bij Keuken).")
# Hoeveel er minstens in een verpakking zit: de keuken boekt nooit per stuk in.
MIN_PER_VERPAKKING = 2
MAX_STUKS = 10000


def keuken_producten(db, alleen_actief=True):
    voorwaarde = "AND actief = 1" if alleen_actief else f"AND {NIET_GEARCHIVEERD}"
    return db.execute(
        f"SELECT * FROM producten WHERE categorie = ? {voorwaarde} ORDER BY subcategorie, naam COLLATE NOCASE",
        (KEUKEN_CATEGORIE,),
    ).fetchall()


def keuken_barcodes(db):
    """{barcode: {"product_id", "artikel_id", "aantal", "omschrijving"}} van alle artikelen van keukenproducten, voor
    het scannen bij het tellen en inboeken. "aantal" is in de eenheid van het product: een zak AH frikandellen van 20 is
    20, een doos Plus met 4 zakken van 15 is 60. Zo telt een doos van de ene supermarkt anders dan die van de andere.
    Staat er niet bij hoeveel erin zit (of maar 1), dan is "aantal" None: dan vraagt de app of de site het eerst (zie
    zet_keuken_verpakking), want per stuk inboeken doet de keuken niet."""
    uit = {}
    for a in db.execute(
        """SELECT a.*, p.eenheid FROM artikelen a JOIN producten p ON p.id = a.product_id
           WHERE p.categorie = ? AND (a.ean IS NOT NULL OR a.ean_omverpakking IS NOT NULL)""",
        (KEUKEN_CATEGORIE,),
    ).fetchall():
        per_verpakking = a["aantal_per_verpakking"] or 1
        if a["ean"]:
            uit[a["ean"]] = {"product_id": a["product_id"], "artikel_id": a["id"],
                             "aantal": per_verpakking if per_verpakking >= MIN_PER_VERPAKKING else None,
                             "omschrijving": barcodes.omschrijving(a)}
        if a["ean_omverpakking"] and a["per_omverpakking"]:
            in_doos = per_verpakking * a["per_omverpakking"]
            uit[a["ean_omverpakking"]] = {"product_id": a["product_id"], "artikel_id": a["id"],
                                          "aantal": in_doos if in_doos >= MIN_PER_VERPAKKING else None,
                                          "omschrijving": barcodes.omschrijving(a, "omverpakking")}
    return uit


def keuken_verpakkingen(db):
    """{product_id: [{"sleutel", "naam", "aantal", "per_stuk"}]}: de verpakkingen waarin je een keukenproduct inboekt
    zonder te scannen, de kleinste eerst: elke gekoppelde zak of doos (per merk, met wat erin zit), en alleen voor een
    product zonder zulke verpakkingen (bijvoorbeeld gehaktballen van de slager) de verpakking die bij het product zelf
    staat. Zo staat een oude 'doos van 24' bij het product niet naast de zakken van 20 en 15 die je echt koopt. Alleen
    met minstens MIN_PER_VERPAKKING erin. per_stuk: de inkoopprijs per stuk, of None."""
    uit = {}
    for a in db.execute(
        """SELECT a.* FROM artikelen a JOIN producten p ON p.id = a.product_id WHERE p.categorie = ?
           ORDER BY a.naam COLLATE NOCASE, a.id""",
        (KEUKEN_CATEGORIE,),
    ).fetchall():
        n = a["aantal_per_verpakking"] or 1
        prijs = a["inkoopprijs"] or 0
        if n >= MIN_PER_VERPAKKING:
            uit.setdefault(a["product_id"], []).append(
                {"sleutel": f"artikel:{a['id']}", "naam": a["naam"], "aantal": n,
                 "per_stuk": round(prijs / n, 4) if prijs > 0 else None})
        if a["per_omverpakking"] and n * a["per_omverpakking"] >= MIN_PER_VERPAKKING:
            in_doos = n * a["per_omverpakking"]
            uit.setdefault(a["product_id"], []).append(
                {"sleutel": f"doos:{a['id']}", "naam": f"{a['naam']}, doos van {a['per_omverpakking']}", "aantal": in_doos,
                 "per_stuk": round(prijs / n, 4) if prijs > 0 else None})
    for p in keuken_producten(db, alleen_actief=False):
        factor = besteleenheid_factor(p)
        if factor >= MIN_PER_VERPAKKING and p["id"] not in uit:
            uit.setdefault(p["id"], []).append(
                {"sleutel": "product", "naam": (p["besteleenheid"] or "verpakking").lower(), "aantal": factor,
                 "per_stuk": round(inkoop_per_stuk(p), 4) if p["inkoopprijs"] else None})
    for lijst in uit.values():
        lijst.sort(key=lambda v: (v["aantal"], v["naam"].lower()))
    return uit


def verwerk_keuken_telling(db, waarden, naam, datum, gebruiker_id=None, opmerking="", begintelling=False):
    """waarden: {product_id: geteld}. Legt de keukentelling vast, zet de voorraad op het getelde aantal en boekt het
    verschil als verkocht (minder) of correctie (meer). Geeft het id van de telling, of None als er niets was.

    begintelling: de eerste telling (of opnieuw beginnen als de voorraad op de site niet meer klopt). Dan is het
    verschil geen verkoop maar een correctie, ook als er minder ligt: zo komt er geen omzet bij die nooit verkocht is."""
    producten = {p["id"]: p for p in keuken_producten(db, alleen_actief=False)}
    waarden = {pid: geteld for pid, geteld in waarden.items() if pid in producten and geteld >= 0}
    if not waarden:
        return None
    telling_id = db.execute(
        "INSERT INTO keuken_tellingen (datum, naam, gebruiker_id, opmerking, begintelling) VALUES (?, ?, ?, ?, ?)",
        (datum, naam, gebruiker_id, opmerking or None, 1 if begintelling else 0),
    ).lastrowid
    for pid, geteld in waarden.items():
        p = producten[pid]
        verschil = geteld - p["voorraad"]
        # Bij een begintelling is ook minder een correctie (negatief), geen verkoop.
        verkocht, correctie = (0, verschil) if begintelling else (max(0, -verschil), max(0, verschil))
        db.execute(
            """INSERT INTO keuken_telling_regels
               (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (telling_id, pid, p["voorraad"], geteld, verkocht, correctie, omzet_per_eenheid(p)),
        )
        db.execute("UPDATE producten SET voorraad = ? WHERE id = ?", (geteld, pid))
        verwerk_auto_inactief(db, pid, geteld)
        if verkocht or correctie:
            soort = "Begintelling" if begintelling else ("Verkocht" if verkocht else "Correctie")
            db.execute(
                """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pid, "uit" if verkocht or correctie < 0 else "in", verkocht or abs(correctie), datum, naam,
                 gebruiker_id, f"{soort} (keukentelling #{telling_id})"),
            )
    boodschappen_bij_tekort(db, waarden, naam)
    db.commit()
    return telling_id


def boek_keuken_in(db, verpakkingen, naam, datum, gebruiker_id=None, inkoopprijzen=None, gescand=None, scans=None):
    """Inboeken, altijd per verpakking. Geeft {"producten": hoeveel producten er zijn ingeboekt, "overgeslagen": [wat
    niet kon, met de reden]}.
    - scans: de gescande barcodes, één per doos of zak; hoeveel erin zit komt van het artikel (per merk anders).
    - verpakkingen: {product_id: {sleutel: aantal verpakkingen}} met een sleutel uit keuken_verpakkingen, of (een app
      van voor 2.18.0) {product_id: aantal} voor de verpakking van het product zelf.
    - gescand (een app van voor 2.18.0): {product_id: stuks} uit het scannen.
    - inkoopprijzen: {product_id: nieuwe inkoopprijs per verpakking} (optioneel, alleen als die anders is).
    Een verpakking zonder bekend aantal (of met 1) wordt overgeslagen: de keuken boekt nooit per stuk in. Wat erbij
    komt, gaat van de boodschappenlijst als het niet meer onder het minimum zit."""
    producten = {p["id"]: p for p in keuken_producten(db)}
    ingeboekt = set()
    overgeslagen = []

    def boek(pid, stuks, uitleg):
        db.execute("UPDATE producten SET voorraad = voorraad + ? WHERE id = ?", (stuks, pid))
        db.execute(
            """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
               VALUES (?, 'in', ?, ?, ?, ?, ?)""",
            (pid, stuks, datum, naam, gebruiker_id, f"Ingeboekt (keuken): {uitleg}"),
        )
        ingeboekt.add(pid)

    if scans:
        bekend = keuken_barcodes(db)
        per_code = {}
        for tekst in scans:
            code = barcodes.normaliseer(str(tekst)) or str(tekst).strip()
            per_code[code] = per_code.get(code, 0) + 1
        for code, keer in per_code.items():
            d = bekend.get(code)
            if d is None or d["product_id"] not in producten:
                overgeslagen.append(f"barcode {code}: hoort bij geen actief keukenproduct")
            elif not d["aantal"]:
                overgeslagen.append(f"{d['omschrijving']}: er staat niet bij hoeveel erin zit")
            else:
                boek(d["product_id"], keer * d["aantal"], f"{keer}× {d['omschrijving']} (gescand)")
    for pid, stuks in (gescand or {}).items():
        p = producten.get(pid)
        if p is None or stuks <= 0:
            continue
        boek(pid, stuks, f"{stuks} {p['eenheid'].lower()} (gescand)")
    alle_verpakkingen = keuken_verpakkingen(db) if verpakkingen else {}
    for pid, keuzes in (verpakkingen or {}).items():
        p = producten.get(pid)
        if p is None:
            continue
        if not isinstance(keuzes, dict):
            keuzes = {"product": keuzes}
        for sleutel, n in keuzes.items():
            if not n or n <= 0:
                continue
            v = next((v for v in alle_verpakkingen.get(pid, []) if v["sleutel"] == sleutel), None)
            if v is None and sleutel == "product" and besteleenheid_factor(p) >= MIN_PER_VERPAKKING:
                # Een app van voor 2.18.0 boekt in de verpakking van het product, ook als er merken bij staan.
                v = {"naam": (p["besteleenheid"] or "verpakking").lower(), "aantal": besteleenheid_factor(p)}
            if v is None:
                overgeslagen.append(f"{p['naam']}: er staat niet bij hoeveel er in een verpakking zit")
                continue
            boek(pid, n * v["aantal"], f"{n}× {v['naam']} ({n * v['aantal']} {p['eenheid'].lower()})")
    for pid, prijs in (inkoopprijzen or {}).items():
        p = producten.get(pid)
        if p is None or prijs is None or abs(p["inkoopprijs"] - prijs) < 0.001:
            continue
        db.execute("UPDATE producten SET inkoopprijs = ? WHERE id = ?", (prijs, pid))
        db.execute(
            """INSERT INTO prijs_geschiedenis (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id)
               VALUES (?, 'inkoopprijs', ?, ?, ?, ?, ?)""",
            (pid, p["inkoopprijs"], prijs, datum, naam, gebruiker_id),
        )
    for pid in ingeboekt:
        nu = db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()
        if nu["voorraad"] >= (nu["min_voorraad"] or 0):
            vink_boodschap_af(db, nu, naam)
    db.commit()
    return {"producten": len(ingeboekt), "overgeslagen": overgeslagen}


# ---------- Muteren en derven, en de verpakkingen instellen ----------

KEUKEN_MUTATIES = {
    "derving": "Weggegooid (derving)",
    "erbij": "Erbij (correctie)",
    "eraf": "Eraf (correctie)",
}


def muteer_keuken(db, product_id, soort, aantal, naam, gebruiker_id=None, reden=None, opmerking=""):
    """Een keukenproduct muteren: wat er weggegooid wordt (derving, met een reden uit DERVING_REDENEN; dan telt het niet
    als verkocht), of een correctie erbij of eraf. Gewoon per stuk. Geeft (melding, foutmelding)."""
    p = next((p for p in keuken_producten(db, alleen_actief=False) if p["id"] == product_id), None)
    if p is None:
        return None, "Dit is geen keukenproduct."
    if soort not in KEUKEN_MUTATIES:
        return None, "Kies wat je wilt boeken: weggegooid, erbij of eraf."
    if not isinstance(aantal, int) or not 0 < aantal <= MAX_STUKS:
        return None, "Vul een aantal van 1 of meer in."
    if soort == "derving" and reden not in DERVING_REDENEN:
        return None, "Kies waarom het weg is."
    opmerking = (opmerking or "").strip()[:200]
    uitleg = f"Keuken: {KEUKEN_MUTATIES[soort].lower()}" + (f", {opmerking}" if opmerking else "")
    uitkomst = boek_mutatie(db, product_id, "in" if soort == "erbij" else "uit", aantal, naam, gebruiker_id, uitleg,
                            reden if soort == "derving" else None)
    boodschappen_bij_tekort(db, [product_id], naam)
    db.commit()
    eenheid = (p["eenheid"] or "stuks").lower()
    wat = {"derving": "weggegooid", "erbij": "erbij geboekt", "eraf": "eraf geboekt"}[soort]
    return f"{aantal} {eenheid} {p['naam']} {wat}. Voorraad nu {uitkomst['voorraad']} {eenheid}.", None


def koppel_keuken_barcode(db, tekst, product_id, aantal, naam=None, inkoopprijs=None, door=None, gebruiker_id=None):
    """Een onbekende barcode bij het tellen of inboeken meteen aan een keukenproduct koppelen, met hoeveel erin zit (een
    zak van 20, een doos van 40): dat verschilt per merk, dus elke verpakking wordt een eigen artikel. Minstens
    MIN_PER_VERPAKKING: de keuken boekt nooit per stuk in. Geeft ({"code", ...zoals in keuken_barcodes}, foutmelding)."""
    if product_id not in {p["id"] for p in keuken_producten(db)}:
        return None, "Kies een keukenproduct."
    if not isinstance(aantal, int) or not MIN_PER_VERPAKKING <= aantal <= MAX_STUKS:
        return None, "Vul in hoeveel er in deze verpakking zit (2 of meer): in de keuken boek je per verpakking in, nooit per stuk."
    _, fout = barcodes.snel_koppelen(db, str(tekst or ""), product_id, door=door, gebruiker_id=gebruiker_id,
                                     per_verpakking=aantal, inkoopprijs=str(inkoopprijs or "").replace(",", ".") or None,
                                     naam=str(naam or "").strip() or None)
    if fout:
        return None, fout
    code = barcodes.normaliseer(str(tekst))
    return {"code": code, **keuken_barcodes(db)[code]}, None


def zet_keuken_verpakking(db, code, aantal, door=None, gebruiker_id=None):
    """Hoeveel er in een gekoppelde zak of doos zit (die er nog niet bij stond). Geeft (barcode-gegevens zoals in
    keuken_barcodes, foutmelding). Werkt daarna de inkoopprijs van het product bij (zie barcodes.werk_inkoopprijs_bij)."""
    code = barcodes.normaliseer(str(code or ""))
    artikel = db.execute(
        """SELECT a.* FROM artikelen a JOIN producten p ON p.id = a.product_id
           WHERE p.categorie = ? AND (a.ean = ? OR a.ean_omverpakking = ?)""",
        (KEUKEN_CATEGORIE, code, code),
    ).fetchone()
    if artikel is None:
        return None, "Deze barcode hoort bij geen keukenproduct."
    if not isinstance(aantal, int) or not MIN_PER_VERPAKKING <= aantal <= MAX_STUKS:
        return None, "Vul in hoeveel er in deze verpakking zit (2 of meer): in de keuken boek je per verpakking in."
    if artikel["ean"] == code:
        db.execute("UPDATE artikelen SET aantal_per_verpakking = ?, bijgewerkt_op = ? WHERE id = ?",
                   (aantal, now_str(), artikel["id"]))
    else:
        # De doos: zoveel zakken (of losse stuks) van het artikel.
        per_zak = artikel["aantal_per_verpakking"] or 1
        if aantal % per_zak:
            return None, f"In deze doos zitten verpakkingen van {per_zak}: vul het totaal in, een veelvoud van {per_zak}."
        db.execute("UPDATE artikelen SET per_omverpakking = ?, bijgewerkt_op = ? WHERE id = ?",
                   (aantal // per_zak, now_str(), artikel["id"]))
    barcodes.werk_inkoopprijs_bij(db, artikel["product_id"], door, gebruiker_id)
    db.commit()
    return keuken_barcodes(db).get(code), None


def zet_product_verpakking(db, product_id, naam, aantal):
    """Een keukenproduct zonder barcode (bijvoorbeeld gehaktballen van de slager): in welke verpakking het komt en
    hoeveel erin zit, zodat je het per verpakking inboekt. Geeft een foutmelding of None."""
    p = next((p for p in keuken_producten(db, alleen_actief=False) if p["id"] == product_id), None)
    if p is None:
        return "Dit is geen keukenproduct."
    if not isinstance(aantal, int) or not MIN_PER_VERPAKKING <= aantal <= MAX_STUKS:
        return "Vul in hoeveel er in een verpakking zit (2 of meer)."
    naam = " ".join(str(naam or "").split())[:30] or "Doos"
    # De inkoopprijs staat per besteleenheid: omrekenen, zodat een stuk even duur blijft. Met artikelen met een prijs
    # rekent werk_inkoopprijs_bij hem daarna opnieuw uit.
    db.execute("UPDATE producten SET besteleenheid = ?, besteleenheid_factor = ?, inkoopprijs = ? WHERE id = ?",
               (naam[:1].upper() + naam[1:], aantal, round(inkoop_per_stuk(p) * aantal, 4), product_id))
    barcodes.werk_inkoopprijs_bij(db, product_id)
    db.commit()
    return None


# ---------- De boodschappenlijst: de keuken koopt zelf in, niet via de bestellijst ----------


def boodschap_tekst(product):
    return f"{product['naam']} (keuken)"


def zet_op_boodschappenlijst(db, product, door=None):
    """Een keukenproduct op de boodschappenlijst ("Frikandel (keuken)"), als hij er nog niet (open) op staat. Geeft True
    als hij erbij kwam. Commit niet."""
    tekst = boodschap_tekst(product)
    if db.execute("SELECT 1 FROM boodschappen WHERE tekst = ? AND afgevinkt = 0", (tekst,)).fetchone():
        return False
    db.execute("INSERT INTO boodschappen (tekst, aangemaakt_door, aangemaakt_op) VALUES (?, ?, ?)",
               (tekst, door, now_str()))
    return True


def vink_boodschap_af(db, product, door=None):
    """Ingeboekt en weer genoeg: de open boodschap van dit keukenproduct is gekocht. Commit niet."""
    db.execute("UPDATE boodschappen SET afgevinkt = 1, afgevinkt_door = ?, afgevinkt_op = ? WHERE tekst = ? AND afgevinkt = 0",
               (door, now_str(), boodschap_tekst(product)))


def boodschappen_bij_tekort(db, product_ids, door=None):
    """De keukenproducten die nu onder hun minimum zitten, op de boodschappenlijst. Commit niet."""
    ids = [int(pid) for pid in product_ids]
    if not ids:
        return
    for p in db.execute(
        f"""SELECT * FROM producten WHERE id IN ({','.join('?' * len(ids))}) AND categorie = ? AND actief = 1
            AND min_voorraad > 0 AND voorraad < min_voorraad""",
        (*ids, KEUKEN_CATEGORIE),
    ).fetchall():
        zet_op_boodschappenlijst(db, p, door)


def zet_keuken_prijzen(db, prijzen, naam, datum, gebruiker_id=None):
    """prijzen: {product_id: nieuwe verkoopprijs}. Werkt de prijs bij (met prijsgeschiedenis); geeft het aantal."""
    producten = {p["id"]: p for p in keuken_producten(db, alleen_actief=False)}
    aantal = 0
    for pid, prijs in prijzen.items():
        p = producten.get(pid)
        if p is None or prijs is None or abs(p["verkoopprijs"] - prijs) < 0.001:
            continue
        db.execute("UPDATE producten SET verkoopprijs = ? WHERE id = ?", (prijs, pid))
        db.execute(
            """INSERT INTO prijs_geschiedenis (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id)
               VALUES (?, 'verkoopprijs', ?, ?, ?, ?, ?)""",
            (pid, p["verkoopprijs"], prijs, datum, naam, gebruiker_id),
        )
        aantal += 1
    db.commit()
    return aantal


def keuken_tellingen(db, limiet=30):
    """De laatste keukentellingen met hun omzet en regels, nieuwste eerst."""
    tellingen = [
        dict(t)
        for t in db.execute(
            """SELECT k.*, COALESCE(SUM(r.verkocht * r.verkoopprijs), 0) AS omzet, COUNT(r.id) AS aantal_producten
               FROM keuken_tellingen k LEFT JOIN keuken_telling_regels r ON r.telling_id = k.id
               GROUP BY k.id ORDER BY k.datum DESC, k.id DESC LIMIT ?""",
            (limiet,),
        ).fetchall()
    ]
    if tellingen:
        ids = [t["id"] for t in tellingen]
        regels = {}
        for r in db.execute(
            f"""SELECT r.*, p.naam AS product_naam, p.eenheid FROM keuken_telling_regels r
                JOIN producten p ON p.id = r.product_id WHERE r.telling_id IN ({','.join('?' * len(ids))})
                ORDER BY p.naam COLLATE NOCASE""",
            ids,
        ).fetchall():
            regels.setdefault(r["telling_id"], []).append(r)
        for t in tellingen:
            t["regels"] = regels.get(t["id"], [])
    return tellingen


# ---------- De keukentelling die nog loopt, gedeeld tussen de site en de handterminal-app ----------


def keuken_stand(db, gebruiker_id):
    """{"loop_id", "stand", "bijgewerkt_op"} van iemands lopende keukentelling, of None."""
    rij = db.execute("SELECT * FROM keuken_loop WHERE gebruiker_id = ?", (gebruiker_id,)).fetchone()
    if rij is None:
        return None
    try:
        stand = json.loads(rij["stand"])
    except ValueError:
        return None
    return {"loop_id": rij["loop_id"], "stand": stand, "bijgewerkt_op": rij["bijgewerkt_op"]}


def bewaar_keuken_stand(db, gebruiker_id, loop_id, stand, nieuw=False):
    """Bewaart de stand. Staat er al een andere telling (een ander loop_id) en is dit geen nieuwe, dan is er op een ander
    toestel opnieuw begonnen: dan wordt er niets bewaard en geeft hij False. Anders True."""
    huidig = db.execute("SELECT loop_id FROM keuken_loop WHERE gebruiker_id = ?", (gebruiker_id,)).fetchone()
    if huidig is not None and huidig["loop_id"] != loop_id and not nieuw:
        return False
    db.execute(
        "INSERT OR REPLACE INTO keuken_loop (gebruiker_id, loop_id, stand, bijgewerkt_op) VALUES (?, ?, ?, ?)",
        (gebruiker_id, loop_id, json.dumps(stand), now_str()),
    )
    db.commit()
    return True


def wis_keuken_stand(db, gebruiker_id, loop_id=None):
    """Afgebroken of opgeslagen. Met loop_id alleen als het nog die telling is (een late 'afbreken' wist geen nieuwere)."""
    if loop_id:
        db.execute("DELETE FROM keuken_loop WHERE gebruiker_id = ? AND loop_id = ?", (gebruiker_id, loop_id))
    else:
        db.execute("DELETE FROM keuken_loop WHERE gebruiker_id = ?", (gebruiker_id,))
    db.commit()


# ---------- Keukenomzet per week (dashboard) ----------


def keuken_omzet_per_dag(db):
    """{datum: omzet} van de keuken: de omzet van elke keukentelling verdeeld over de dagen sinds de vorige keukentelling
    (zoals de weekomzet van de kantine), zodat het niet uitmaakt op welke dag je telt. De eerste telling (en een
    begintelling) heeft geen omzet."""
    tellingen = db.execute(
        """SELECT k.datum, COALESCE(SUM(r.verkocht * r.verkoopprijs), 0) AS omzet
           FROM keuken_tellingen k LEFT JOIN keuken_telling_regels r ON r.telling_id = k.id
           GROUP BY k.id ORDER BY k.datum, k.id"""
    ).fetchall()
    per_dag = {}
    vorige = None
    for t in tellingen:
        dag = datetime.strptime(t["datum"][:10], "%Y-%m-%d").date()
        if vorige is not None and t["omzet"]:
            dagen = [vorige + timedelta(days=i) for i in range(1, max(1, (dag - vorige).days) + 1)]
            for d in dagen:
                per_dag[d] = per_dag.get(d, 0) + t["omzet"] / len(dagen)
        vorige = dag
    return per_dag


def keuken_omzet_in(per_dag, van, tot):
    """De keukenomzet van van t/m tot (date of 'YYYY-MM-DD')."""
    van = van if isinstance(van, date) else date.fromisoformat(str(van)[:10])
    tot = tot if isinstance(tot, date) else date.fromisoformat(str(tot)[:10])
    return round(sum(v for d, v in per_dag.items() if van <= d <= tot), 2)
