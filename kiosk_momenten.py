"""Mappen en momenten voor de dia's van de kantine-tv (1.76.0).

Mappen: een dia hoort bij een map, zoals "Halloween feest" of "Sponsoren" (zonder map: "Algemeen"). Een map zet je met
één klik aan of uit, en hij kan een begin en einde met tijd hebben (zaterdag 15:45 tot zondag 02:00): dan gaat hij
vanzelf aan en uit.

Momenten: een dia kan een tijdslot hebben (moment), zoals 17:00 Heksenbrouwsel. Hij staat dan alleen in de diashow van
zijn moment tot het volgende moment in dezelfde map (of tot moment_tot, het einde van de map, of anders een uur). De
eerste schijnwerper_minuten (standaard 5) neemt hij alle tv's over: de schijnwerper (templates/_kiosk_moment.html), ook
het prijzenscherm. Daarna staat er op het prijzenscherm een balk "Nu aan de bar" (balk_tekst) tot het volgende moment.
Loopt het programma uit, dan stuur je bij met toon_nu, stop_schijnwerper en schuif_op (op de Kiosk-hub, bij de dia's en
in de handterminal-app).

De tv's rekenen zelf uit wat er in beeld moet, met de klok van de server (de schermen krijgen de tijden en "nu" mee):
zo begint de schijnwerper op de minuut, ook als de verbinding even hapert, en ook op een tv waarvan de klok niet goed
staat."""

import json
from datetime import datetime, timedelta

FORMAAT = "%Y-%m-%d %H:%M"
STANDAARD_MINUTEN = 5
MAX_SCHIJNWERPER_MINUTEN = 30
SCHUIF_MINUTEN = 15
# Een moment zonder volgend moment, einde of einde van de map staat zo lang in de diashow.
STANDAARD_SLOT_MINUTEN = 60
# Zo ver vooruit krijgen de schermen de momenten alvast mee.
VOORUIT_UREN = 24

# Effecten over een dia (static/kiosk_effecten.js): sleutel -> (naam, kleur, standaard plek van de prijs in % van
# links en van boven). De plekken passen bij de ontwerpen van het Halloween feest; in het dia-formulier tik je een andere
# plek aan.
EFFECTEN = {
    "heksenketel": ("Heksenketel: groene bubbels, damp en druppels", "#7dff3a", (76, 52)),
    "vuur": ("Vuur: vonken en vlammen", "#ff8a1f", (84, 72)),
    "toverglans": ("Toverglans: paarse glitters en een heks op een bezem", "#e255ff", (83, 72)),
    "duivel": ("Duivel: rode bliksem, sintels en bloed", "#ff2a2a", (77, 73)),
    "zombie": ("Zombie: groen slijm en confetti", "#9dff2e", (55, 56)),
    "programma": ("Programma: vleermuizen, kaarslicht en het tijdslot van nu licht op", "#ff9326", None),
}
STANDAARD_KLEUR = "#ff9326"
# Het programma: de regels van boven naar beneden (hun tijd) en waar ze staan, in % van de afbeelding: het midden van de
# bovenste en de onderste regel, de hoogte van een regel en de linker- en rechterkant. Zo staat het in het ontwerp van
# het Halloween feest.
PROGRAMMA_STANDAARD = {
    "rijen": ["16:00", "17:00", "18:00", "19:00", "20:00", "21:00", "21:00", "01:00"],
    "boven": 25.6, "onder": 87.5, "hoogte": 8.4, "links": 9.4, "rechts": 66.5,
}


def tijdstip(tekst):
    """'2026-10-31 17:00' (of '2026-10-31T17:00', zoals een datum-en-tijdveld hem stuurt) -> datetime, anders None."""
    tekst = str(tekst or "").strip().replace("T", " ")[:16]
    try:
        return datetime.strptime(tekst, FORMAAT)
    except ValueError:
        return None


def _tot_op_de_seconde(tekst_):
    """De tijd waarop een handmatige of gestopte schijnwerper afloopt ('YYYY-MM-DD HH:MM:SS'), of None."""
    try:
        return datetime.strptime(str(tekst_ or "").strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return tijdstip(tekst_)


def tekst(moment):
    return moment.strftime(FORMAAT) if moment else None


def ms(moment):
    """Milliseconden sinds 1970 voor de schermen (JavaScript). Het proces rekent in Nederlandse tijd (tijdzone.py)."""
    return int(moment.timestamp() * 1000) if moment else None


def schoon_minuten(waarde, standaard=STANDAARD_MINUTEN):
    """Minuten in de schijnwerper: 0 (geen schijnwerper) t/m MAX_SCHIJNWERPER_MINUTEN."""
    try:
        return max(0, min(MAX_SCHIJNWERPER_MINUTEN, int(str(waarde).strip())))
    except (TypeError, ValueError):
        return standaard


def kleur(effect):
    return EFFECTEN[effect][1] if effect in EFFECTEN else STANDAARD_KLEUR


def effect_opties(dia):
    """De opties van het effect van een dia: de plek van de prijs ([links, boven] in %), en bij het programma de
    regels (zie PROGRAMMA_STANDAARD). Wat er niet bij staat, komt uit de standaard van het effect."""
    try:
        opties = json.loads(dia["effect_opties"] or "{}")
    except (TypeError, ValueError):
        opties = {}
    if not isinstance(opties, dict):
        opties = {}
    effect = dia["effect"]
    if effect in EFFECTEN and EFFECTEN[effect][2] and dia["sjabloon"] != "griezel":
        prijs = opties.get("prijs")
        if not (isinstance(prijs, list) and len(prijs) == 2 and all(isinstance(v, (int, float)) for v in prijs)):
            opties["prijs"] = list(EFFECTEN[effect][2])
    else:
        opties.pop("prijs", None)
    if effect == "programma":
        for sleutel, waarde in PROGRAMMA_STANDAARD.items():
            if sleutel == "rijen":
                rijen = opties.get("rijen")
                if not (isinstance(rijen, list) and rijen and all(isinstance(r, str) for r in rijen)):
                    opties["rijen"] = list(waarde)
            elif not isinstance(opties.get(sleutel), (int, float)):
                opties[sleutel] = waarde
    return opties


def schoon_opties(effect, prijs_links, prijs_boven, rijen_tekst, sjabloon=None):
    """De opties uit het dia-formulier als JSON (of None): de aangetikte plek van de prijs (niet bij een griezeldia:
    daar klopt de prijs zelf) en de tijden van de regels van het programma ("16:00, 17:00, ..."). De rest van het
    programma (waar de regels staan) blijft de standaard."""
    opties = {}
    try:
        links, boven = float(prijs_links), float(prijs_boven)
        if (0 <= links <= 100 and 0 <= boven <= 100 and effect in EFFECTEN and EFFECTEN[effect][2]
                and sjabloon != "griezel"):
            opties["prijs"] = [round(links, 1), round(boven, 1)]
    except (TypeError, ValueError):
        pass
    if effect == "programma":
        rijen = [r.strip() for r in str(rijen_tekst or "").replace(";", ",").split(",") if r.strip()]
        rijen = [r for r in rijen if len(r) <= 5 and r.replace(":", "").isdigit()][:12]
        if rijen:
            opties["rijen"] = rijen
    return json.dumps(opties) if opties else None


# ---------- Mappen ----------


def mappen(db):
    return db.execute("SELECT * FROM kiosk_dia_mappen ORDER BY volgorde, naam COLLATE NOCASE, id").fetchall()


def map_status(m, nu=None):
    """'uit', 'straks' (zijn begin komt nog), 'voorbij' (zijn einde is geweest) of 'aan'."""
    nu = nu or datetime.now()
    if not m["actief"]:
        return "uit"
    vanaf, tot = tijdstip(m["vanaf"]), tijdstip(m["tot"])
    if vanaf and nu < vanaf:
        return "straks"
    if tot and nu >= tot:
        return "voorbij"
    return "aan"


def bewaar_map(db, map_id, naam, vanaf, tot, actief=True):
    """Een map nieuw (map_id None) of aangepast. Geeft (id, foutmelding)."""
    naam = " ".join(str(naam or "").split())[:60]
    if not naam:
        return map_id, "Geef de map een naam, bijvoorbeeld 'Halloween feest'."
    vanaf, tot = tijdstip(vanaf), tijdstip(tot)
    if vanaf and tot and tot <= vanaf:
        return map_id, "Het einde van de map ligt voor het begin."
    if map_id:
        db.execute("UPDATE kiosk_dia_mappen SET naam = ?, vanaf = ?, tot = ?, actief = ? WHERE id = ?",
                   (naam, tekst(vanaf), tekst(tot), 1 if actief else 0, map_id))
    else:
        volgende = db.execute("SELECT COALESCE(MAX(volgorde), 0) + 1 FROM kiosk_dia_mappen").fetchone()[0]
        map_id = db.execute(
            "INSERT INTO kiosk_dia_mappen (naam, actief, vanaf, tot, volgorde, aangemaakt_op) VALUES (?, ?, ?, ?, ?, ?)",
            (naam, 1 if actief else 0, tekst(vanaf), tekst(tot), volgende, datetime.now().strftime(FORMAAT)),
        ).lastrowid
    db.commit()
    return map_id, None


def zet_map_aan(db, map_id, aan):
    db.execute("UPDATE kiosk_dia_mappen SET actief = ? WHERE id = ?", (1 if aan else 0, map_id))
    db.commit()


def verwijder_map(db, map_id):
    """De map weg; zijn dia's blijven, bij Algemeen."""
    db.execute("UPDATE kiosk_sponsoren SET map_id = NULL WHERE map_id = ?", (map_id,))
    db.execute("DELETE FROM kiosk_dia_mappen WHERE id = ?", (map_id,))
    db.commit()


# ---------- Wanneer een dia in de diashow staat ----------


def _momenten_per_map(dias):
    per_map = {}
    for d in dias:
        start = tijdstip(d["moment"])
        if start:
            per_map.setdefault(d["map_id"], []).append(start)
    for lijst in per_map.values():
        lijst.sort()
    return per_map


def _einde(dia, start, per_map, map_tot):
    eigen = tijdstip(dia["moment_tot"])
    if eigen and eigen > start:
        return eigen
    volgende = next((t for t in per_map.get(dia["map_id"], []) if t > start), None)
    if volgende:
        return volgende
    if map_tot and map_tot > start:
        return map_tot
    return start + timedelta(minutes=STANDAARD_SLOT_MINUTEN)


def _slots(db, dias):
    """{dia_id: (van, tot)} voor de dia's waarvan de map aan staat (of die bij Algemeen horen; ook een map die niet
    meer bestaat telt als Algemeen), los van de klok: van en tot zijn datetimes, of None als er geen grens is. Het
    tijdslot van een moment loopt tot zijn eigen einde, het volgende moment in dezelfde map, het einde van de map of
    anders STANDAARD_SLOT_MINUTEN; altijd binnen het begin en einde van de map."""
    alle = {m["id"]: m for m in mappen(db)}
    aan = [d for d in dias if alle.get(d["map_id"]) is None or alle[d["map_id"]]["actief"]]
    per_map = _momenten_per_map(aan)
    uit = {}
    for d in aan:
        m = alle.get(d["map_id"])
        van, tot = (tijdstip(m["vanaf"]), tijdstip(m["tot"])) if m is not None else (None, None)
        start = tijdstip(d["moment"])
        if start:
            einde = _einde(d, start, per_map, tot)
            van = max(van, start) if van else start
            tot = min(tot, einde) if tot else einde
        if van and tot and tot <= van:
            continue
        uit[d["id"]] = (van, tot)
    return uit


def vensters(db, dias, nu=None):
    """{dia_id: (van, tot)} voor de dia's (rijen uit kiosk_sponsoren die aan staan) die nu of binnen VOORUIT_UREN in de
    diashow horen (zie _slots). Een dia waarvan de map uit staat of voorbij is, of waarvan het tijdslot voorbij is,
    staat er niet in."""
    nu = nu or datetime.now()
    return {
        dia_id: (van, tot)
        for dia_id, (van, tot) in _slots(db, dias).items()
        if not (tot and tot <= nu) and not (van and van > nu + timedelta(hours=VOORUIT_UREN))
    }


def tijden_per_map(db, dias):
    """{map_id: [{"tijd": "17:00", "van", "einde"}]}: de tijdsloten per map (in ms, op tijd), voor het programma: dat
    licht het tijdslot van nu op. Twee dia's op hetzelfde moment tellen één keer."""
    slots = _slots(db, dias)
    per_map = {}
    for d in dias:
        start = tijdstip(d["moment"])
        if not start or d["id"] not in slots or slots[d["id"]][0] != start:
            continue
        lijst = per_map.setdefault(d["map_id"], [])
        if not any(m["van"] == ms(start) for m in lijst):
            lijst.append({"tijd": f"{start:%H:%M}", "van": ms(start), "einde": ms(slots[d["id"]][1])})
    for lijst in per_map.values():
        lijst.sort(key=lambda m: m["van"])
    return per_map


def programma(db, nu=None, dagen=7):
    """Alle dia's met een moment van de afgelopen 12 uur tot 'dagen' vooruit, op tijd, voor de Kiosk-hub en de app:
    [{"dia", "map", "van", "einde", "spot_tot", "status"}]. status: 'klaar', 'straks', 'schijnwerper', 'bezig',
    'map_uit' (de map staat uit, of het moment valt buiten de map) of 'dia_uit'."""
    nu = nu or datetime.now()
    alle_mappen = {m["id"]: m for m in mappen(db)}
    dias = db.execute(
        "SELECT * FROM kiosk_sponsoren WHERE moment IS NOT NULL AND moment != '' ORDER BY moment, volgorde, id"
    ).fetchall()
    slots = _slots(db, [d for d in dias if d["actief"]])
    handmatig = handmatige_schijnwerper(db, nu)
    gestopt = gestopte_schijnwerper(db, nu)
    uit = []
    for d in dias:
        start = tijdstip(d["moment"])
        if not start or not (nu - timedelta(hours=12) <= start <= nu + timedelta(days=dagen)):
            continue
        van, einde = slots.get(d["id"], (None, None))
        minuten = schoon_minuten(d["schijnwerper_minuten"])
        spot_tot = min(start + timedelta(minutes=minuten), einde) if minuten and einde else None
        if handmatig and handmatig["dia"]["id"] == d["id"]:
            status = "schijnwerper"
        elif not d["actief"]:
            status = "dia_uit"
        elif d["id"] not in slots or van != start:
            status = "map_uit"
        elif einde and einde <= nu:
            status = "klaar"
        elif nu < start:
            status = "straks"
        elif spot_tot and nu < spot_tot and not (gestopt and gestopt["dia_id"] == d["id"]):
            status = "schijnwerper"
        else:
            status = "bezig"
        uit.append({"dia": d, "map": alle_mappen.get(d["map_id"]), "van": start, "einde": einde, "spot_tot": spot_tot,
                    "status": status})
    return uit


def momenten(db, nu=None):
    """De momenten van nu tot VOORUIT_UREN vooruit, op tijd: [{"dia", "van", "spot_tot" (einde van de schijnwerper, of
    None zonder schijnwerper), "einde", "status": 'straks', 'schijnwerper', 'bezig'}], plus de dia die met de hand in
    de schijnwerper staat (die kan ook een dia zonder moment zijn: dan is van None)."""
    nu = nu or datetime.now()
    dias = db.execute("SELECT * FROM kiosk_sponsoren WHERE actief = 1 ORDER BY moment, volgorde, id").fetchall()
    open_ = vensters(db, dias, nu)
    uit = []
    for d in dias:
        start = tijdstip(d["moment"])
        if not start or d["id"] not in open_:
            continue
        van, tot = open_[d["id"]]
        if van != start:
            continue  # de map begint pas na het moment: dan geen schijnwerper (wel in de diashow)
        minuten = schoon_minuten(d["schijnwerper_minuten"])
        spot_tot = min(van + timedelta(minutes=minuten), tot) if minuten else None
        status = "straks" if nu < van else ("schijnwerper" if spot_tot and nu < spot_tot else "bezig")
        uit.append({"dia": d, "van": van, "spot_tot": spot_tot, "einde": tot, "status": status})
    handmatig = handmatige_schijnwerper(db, nu)
    if handmatig and not any(m["dia"]["id"] == handmatig["dia"]["id"] for m in uit):
        uit.append({"dia": handmatig["dia"], "van": None, "spot_tot": None, "einde": None, "status": "handmatig"})
    return uit


# ---------- Bijsturen op de avond ----------


def _instellingen(db):
    return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()


def handmatige_schijnwerper(db, nu=None):
    """{"dia", "tot"} als iemand een dia met "Nu tonen" in de schijnwerper zette en die tijd nog niet om is."""
    nu = nu or datetime.now()
    rij = _instellingen(db)
    tot = _tot_op_de_seconde(rij["schijnwerper_tot"]) if rij else None
    if not tot or tot <= nu:
        return None
    dia = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (rij["schijnwerper_dia_id"],)).fetchone()
    return {"dia": dia, "tot": tot} if dia else None


def gestopte_schijnwerper(db, nu=None):
    """{"dia_id", "tot"}: de schijnwerper van dit moment is met "Stop" afgebroken, tot die tijd."""
    nu = nu or datetime.now()
    rij = _instellingen(db)
    tot = _tot_op_de_seconde(rij["schijnwerper_stop_tot"]) if rij else None
    if not tot or tot <= nu or not rij["schijnwerper_stop_id"]:
        return None
    return {"dia_id": rij["schijnwerper_stop_id"], "tot": tot}


def toon_nu(db, dia_id, minuten=None, nu=None):
    """Deze dia nu in de schijnwerper, op alle tv's (binnen 5 seconden), voor zijn eigen aantal minuten (of 5).
    Geeft (melding, foutmelding)."""
    nu = nu or datetime.now()
    dia = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (dia_id,)).fetchone()
    if dia is None:
        return None, "Deze dia bestaat niet meer."
    minuten = schoon_minuten(minuten if minuten is not None else dia["schijnwerper_minuten"]) or STANDAARD_MINUTEN
    db.execute(
        """UPDATE kiosk_scherm_instellingen SET schijnwerper_dia_id = ?, schijnwerper_tot = ?,
               schijnwerper_stop_id = NULL, schijnwerper_stop_tot = NULL WHERE id = 1""",
        (dia_id, (nu + timedelta(minutes=minuten)).strftime("%Y-%m-%d %H:%M:%S")),
    )
    db.commit()
    naam = dia["titel"] or "De dia"
    return f"{naam} staat nu {minuten} minuten groot op alle tv's.", None


def stop_schijnwerper(db, nu=None):
    """De schijnwerper die nu loopt (met de hand of van een moment) eraf; de dia blijft gewoon in de diashow. Geeft
    een melding."""
    nu = nu or datetime.now()
    handmatig = handmatige_schijnwerper(db, nu)
    lopend = next((m for m in momenten(db, nu) if m["status"] == "schijnwerper"), None)
    db.execute("UPDATE kiosk_scherm_instellingen SET schijnwerper_dia_id = NULL, schijnwerper_tot = NULL WHERE id = 1")
    if lopend and not handmatig:
        db.execute("UPDATE kiosk_scherm_instellingen SET schijnwerper_stop_id = ?, schijnwerper_stop_tot = ? WHERE id = 1",
                   (lopend["dia"]["id"], lopend["spot_tot"].strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()
    if not handmatig and not lopend:
        return "Er stond niets in de schijnwerper."
    return "De schijnwerper is eraf; de tv's zijn binnen 5 seconden weer gewoon."


def schuif_op(db, dia_id, minuten=SCHUIF_MINUTEN):
    """Het moment van deze dia later (of met een negatief aantal minuten eerder), bijvoorbeeld als het programma
    uitloopt. Alleen dit moment: het vorige tijdslot loopt dan wat langer door. Geeft (melding, foutmelding)."""
    dia = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (dia_id,)).fetchone()
    if dia is None:
        return None, "Deze dia bestaat niet meer."
    start = tijdstip(dia["moment"])
    if not start:
        return None, "Deze dia heeft geen moment om op te schuiven."
    nieuw = start + timedelta(minutes=minuten)
    eigen_tot = tijdstip(dia["moment_tot"])
    db.execute("UPDATE kiosk_sponsoren SET moment = ?, moment_tot = ? WHERE id = ?",
               (tekst(nieuw), tekst(eigen_tot + timedelta(minutes=minuten)) if eigen_tot else None, dia_id))
    db.commit()
    return f"{dia['titel'] or 'De dia'} komt nu om {nieuw:%H:%M}.", None
