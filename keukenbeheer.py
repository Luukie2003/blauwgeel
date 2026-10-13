"""De keuken als eigen module: voorraad tellen, inboeken en verkoopprijzen, los van de gewone telling.

De keukenproducten blijven gewone producten in de categorie Keuken (productkaart.KEUKEN_CATEGORIE), maar staan niet in
de gewone telling of de looplijst. De keuken telt apart: wat er sinds de vorige keukentelling minder is (na wat er is
ingeboekt), is verkocht. Die omzet staat bij de keukentellingen en telt mee in Marge en in Omzet en kassa, maar niet
in de weekomzet en de prognose van de kantine.

Inkoop gaat per verpakking (de besteleenheid, bijvoorbeeld een doos frikandellen van 40) en de voorraad in porties of
stuks: 'aantal per besteleenheid' zegt hoeveel er in een verpakking zit."""

from helpers.producten import besteleenheid_factor, omzet_per_eenheid, verwerk_auto_inactief
from productkaart import KEUKEN_CATEGORIE


def keuken_producten(db, alleen_actief=True):
    voorwaarde = "AND actief = 1" if alleen_actief else ""
    return db.execute(
        f"SELECT * FROM producten WHERE categorie = ? {voorwaarde} ORDER BY subcategorie, naam COLLATE NOCASE",
        (KEUKEN_CATEGORIE,),
    ).fetchall()


def verwerk_keuken_telling(db, waarden, naam, datum, gebruiker_id=None, opmerking=""):
    """waarden: {product_id: geteld}. Legt de keukentelling vast, zet de voorraad op het getelde aantal en boekt het
    verschil als verkocht (minder) of correctie (meer). Geeft het id van de telling, of None als er niets was."""
    producten = {p["id"]: p for p in keuken_producten(db, alleen_actief=False)}
    waarden = {pid: geteld for pid, geteld in waarden.items() if pid in producten and geteld >= 0}
    if not waarden:
        return None
    telling_id = db.execute(
        "INSERT INTO keuken_tellingen (datum, naam, gebruiker_id, opmerking) VALUES (?, ?, ?, ?)",
        (datum, naam, gebruiker_id, opmerking or None),
    ).lastrowid
    for pid, geteld in waarden.items():
        p = producten[pid]
        verschil = geteld - p["voorraad"]
        verkocht, correctie = max(0, -verschil), max(0, verschil)
        db.execute(
            """INSERT INTO keuken_telling_regels
               (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (telling_id, pid, p["voorraad"], geteld, verkocht, correctie, omzet_per_eenheid(p)),
        )
        db.execute("UPDATE producten SET voorraad = ? WHERE id = ?", (geteld, pid))
        verwerk_auto_inactief(db, pid, geteld)
        if verkocht or correctie:
            db.execute(
                """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pid, "uit" if verkocht else "in", verkocht or correctie, datum, naam, gebruiker_id,
                 f"{'Verkocht' if verkocht else 'Correctie'} (keukentelling #{telling_id})"),
            )
    db.commit()
    return telling_id


def boek_keuken_in(db, verpakkingen, naam, datum, gebruiker_id=None, inkoopprijzen=None):
    """verpakkingen: {product_id: aantal verpakkingen}. Telt per product aantal maal 'aantal per besteleenheid' bij de
    voorraad op. inkoopprijzen: {product_id: nieuwe inkoopprijs per verpakking} (optioneel, alleen als die anders is).
    Geeft het aantal ingeboekte producten."""
    producten = {p["id"]: p for p in keuken_producten(db)}
    aantal = 0
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
        aantal += 1
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
    return aantal


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
