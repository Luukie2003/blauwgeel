"""De keuken als eigen module: voorraad tellen, inboeken en verkoopprijzen, los van de gewone telling.

De keukenproducten blijven gewone producten in de categorie Keuken (productkaart.KEUKEN_CATEGORIE), maar staan niet in
de gewone telling of de looplijst. De keuken telt apart: wat er sinds de vorige keukentelling minder is (na wat er is
ingeboekt), is verkocht. Die omzet staat bij de keukentellingen en telt mee in Marge en in Omzet en kassa, maar niet
in de weekomzet en de prognose van de kantine.

Inkoop gaat per verpakking (de besteleenheid, bijvoorbeeld een doos frikandellen van 40) en de voorraad in porties of
stuks: 'aantal per besteleenheid' zegt hoeveel er in een verpakking zit."""

import json
from datetime import date, datetime, timedelta

import barcodes
from helpers.producten import besteleenheid_factor, omzet_per_eenheid, verwerk_auto_inactief
from helpers.tijd import now_str
from productkaart import KEUKEN_CATEGORIE, NIET_GEARCHIVEERD


def keuken_producten(db, alleen_actief=True):
    voorwaarde = "AND actief = 1" if alleen_actief else f"AND {NIET_GEARCHIVEERD}"
    return db.execute(
        f"SELECT * FROM producten WHERE categorie = ? {voorwaarde} ORDER BY subcategorie, naam COLLATE NOCASE",
        (KEUKEN_CATEGORIE,),
    ).fetchall()


def keuken_barcodes(db):
    """{barcode: {"product_id", "aantal", "omschrijving"}} van alle artikelen van keukenproducten, voor het scannen
    bij het tellen en inboeken. "aantal" is in de eenheid van het product: een zak AH frikandellen van 20 is 20, een
    doos Plus met 4 zakken van 15 is 60. Zo telt een doos van de ene supermarkt anders dan die van de andere."""
    uit = {}
    for a in db.execute(
        """SELECT a.*, p.eenheid FROM artikelen a JOIN producten p ON p.id = a.product_id
           WHERE p.categorie = ? AND (a.ean IS NOT NULL OR a.ean_omverpakking IS NOT NULL)""",
        (KEUKEN_CATEGORIE,),
    ).fetchall():
        per_verpakking = a["aantal_per_verpakking"] or 1
        if a["ean"]:
            uit[a["ean"]] = {"product_id": a["product_id"], "aantal": per_verpakking,
                             "omschrijving": barcodes.omschrijving(a)}
        if a["ean_omverpakking"] and a["per_omverpakking"]:
            uit[a["ean_omverpakking"]] = {"product_id": a["product_id"], "aantal": per_verpakking * a["per_omverpakking"],
                                          "omschrijving": barcodes.omschrijving(a, "omverpakking")}
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
    db.commit()
    return telling_id


def boek_keuken_in(db, verpakkingen, naam, datum, gebruiker_id=None, inkoopprijzen=None, gescand=None):
    """verpakkingen: {product_id: aantal verpakkingen}. Telt per product aantal maal 'aantal per besteleenheid' bij de
    voorraad op. inkoopprijzen: {product_id: nieuwe inkoopprijs per verpakking} (optioneel, alleen als die anders is).
    gescand: {product_id: stuks} uit het scannen van barcodes; hoeveel er in een doos zit komt dan van het artikel
    (per supermarkt anders), niet van de besteleenheid. Geeft het aantal ingeboekte producten."""
    producten = {p["id"]: p for p in keuken_producten(db)}
    ingeboekt = set()
    for pid, stuks in (gescand or {}).items():
        p = producten.get(pid)
        if p is None or stuks <= 0:
            continue
        db.execute("UPDATE producten SET voorraad = voorraad + ? WHERE id = ?", (stuks, pid))
        db.execute(
            """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
               VALUES (?, 'in', ?, ?, ?, ?, ?)""",
            (pid, stuks, datum, naam, gebruiker_id, f"Ingeboekt (keuken, gescand): {stuks} {p['eenheid'].lower()}"),
        )
        ingeboekt.add(pid)
    for pid, n in verpakkingen.items():
        p = producten.get(pid)
        if p is None or n <= 0:
            continue
        stuks = n * besteleenheid_factor(p)
        db.execute("UPDATE producten SET voorraad = voorraad + ? WHERE id = ?", (stuks, pid))
        db.execute(
            """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
               VALUES (?, 'in', ?, ?, ?, ?, ?)""",
            (pid, stuks, datum, naam, gebruiker_id,
             f"Ingeboekt (keuken): {n} {(p['besteleenheid'] or p['eenheid']).lower()}"),
        )
        ingeboekt.add(pid)
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
    db.commit()
    return len(ingeboekt)


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
