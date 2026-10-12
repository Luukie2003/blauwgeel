"""Eigen taken: een beheerder voegt een taak toe aan "Wat moet er nu?" en koppelt die aan mensen.

Een taak kan bij een pagina horen (bijvoorbeeld "Prijzenlijst nalopen"): wie op de taak klikt, komt op die pagina.
Slaat iemand daar iets op, dan vraagt de site in een pop-up of de taak daarmee klaar is. Zo werkt het voor elke
pagina, niet alleen voor de prijzen: bij elke taak hoort een lijst met opslaan-acties (endpoints) die de vraag
oproepen, zie TAAK_SOORTEN, of bij "een pagina uit het menu" alle acties van die pagina (zie navigatie.py).

Een taak is voor een of meer mensen. Staat "iedereen" aan, dan moet elke gekozen persoon de taak zelf afronden en is
de taak pas klaar als de laatste dat heeft gedaan; anders is een van hen genoeg.

Een taak kan stappen hebben (een checklist, bijvoorbeeld "Kantine openen"): elke persoon vinkt ze zelf af en kan de
taak pas afronden als alles is afgevinkt. En een taak kan terugkomen (elke week, elke twee weken, elke maand of op
elke verkoopdag): zodra hij klaar is, staat de volgende er. Die verschijnt pas een paar dagen voor de uiterste datum
(start_op), zodat er niet alvast een rij taken voor volgende maand op het overzicht staat."""

from datetime import date, datetime, timedelta

from helpers.mededelingen import TAG_PATROON
from helpers.tijd import vandaag_amsterdam
from helpers.toegang import heeft_sectie_toegang
from navigatie import NAV_ITEMS
from rechten import BEHEERDER_ENDPOINTS, ENDPOINT_SECTIE, OPEN_ENDPOINTS

SOORT_EIGEN = "eigen"
SOORT_PRESET = "preset:"
SOORT_PAGINA = "pagina:"

HERHALINGEN = {
    "week": "Elke week",
    "2weken": "Elke 2 weken",
    "maand": "Elke maand",
    "verkoopdagen": "Op elke verkoopdag",
}
# Hoeveel dagen voor de uiterste datum een terugkerende taak op het overzicht komt.
VOORAF_DAGEN = {"week": 3, "2weken": 5, "maand": 7, "verkoopdagen": 1}
MAX_STAPPEN = 25
MAX_TEKENS_STAP = 120

# Voorgestelde stappen voor de twee checklists van de kantine; de beheerder kan ze aanpassen bij het toevoegen.
CHECKLIST_VOORBEELDEN = {
    "Kantine openen": [
        "Licht en verwarming aan",
        "Koelkasten en tap controleren",
        "Kassa en wisselgeld klaarzetten",
        "Prijzenscherm en tv aanzetten",
        "Bar en toiletten controleren",
    ],
    "Kantine sluiten": [
        "Kassa tellen",
        "Tap en koeling afsluiten",
        "Bar en vloer schoonmaken",
        "Afval buiten zetten",
        "Licht uit, deur op slot",
    ],
}

# Veelvoorkomende klussen. endpoint = de pagina waar de taak naartoe leidt; afronden_op = de opslaan-acties
# (POST-endpoints) waarna de site vraagt of de taak klaar is.
TAAK_SOORTEN = {
    "prijzen_kijken": {
        "label": "Prijzenlijst nalopen (alleen kijken)",
        "endpoint": "prijslijst_pagina",
        "afronden_op": set(),  # hier rond je af met de knop op de pagina zelf: er wordt niets opgeslagen
    },
    "prijzen": {
        "label": "Prijzenlijst nalopen",
        "endpoint": "producten_prijzen",
        "afronden_op": {"producten_prijzen"},
    },
    "product_toevoegen": {
        "label": "Nieuw product toevoegen",
        "endpoint": "product_nieuw",
        "afronden_op": {"product_nieuw", "product_snel_toevoegen"},
    },
    "minimumvoorraad": {
        "label": "Minimumvoorraad en besteleenheid nalopen",
        "endpoint": "producten_bulk_bewerken",
        "afronden_op": {"producten_bulk_bewerken"},
    },
    "voorraad_tellen": {
        "label": "Voorraad tellen",
        "endpoint": "tellen",
        "afronden_op": {"tellen", "tellen_lopen_controleren"},
    },
    "kassa_tellen": {
        "label": "Kassa tellen",
        "endpoint": "kassa_tellen",
        "afronden_op": {"kassa_tellen"},
    },
    "kluis_tellen": {
        "label": "Kluis tellen",
        "endpoint": "kluis_tellen",
        "afronden_op": {"kluis_tellen"},
    },
    "bestelling_plaatsen": {
        "label": "Bestelling plaatsen",
        "endpoint": "bestellijst",
        "afronden_op": {"bestelling_aanmaken", "bestelling_nieuw"},
    },
    "bestelling_inboeken": {
        "label": "Bestelling inboeken",
        "endpoint": "bestellijst",
        "afronden_op": {"bestelling_inboeken", "levering_inboeken"},
    },
    "frituurvet": {
        "label": "Frituurvet vervangen",
        "endpoint": "keuken_voorraad",
        "afronden_op": {"frituurvet_vervangen"},
    },
    "dia": {
        "label": "Dia op de kantine-tv bijwerken",
        "endpoint": "kiosk_sponsoren_leden",
        "afronden_op": {"kiosk_sponsor_nieuw", "kiosk_sponsor_bewerken", "kiosk_sponsor_verwijderen"},
    },
}

# Acties die bij het beheren van taken zelf horen: die roepen de afrondvraag nooit op.
TAAK_ENDPOINTS = {
    "eigen_taak_detail",
    "eigen_taak_stap",
    "eigen_taken_pagina",
    "eigen_taak_nieuw",
    "eigen_taak_verwijderen",
    "eigen_taak_afronden",
    "eigen_taak_nog_niet",
}


def _nav_item(endpoint):
    return next((i for i in NAV_ITEMS if i["url_endpoint"] == endpoint), None)


def pagina_keuzes():
    """[(waarde, label)] voor 'Een pagina uit het menu': alle pagina's in de zijbalk, met de groep erbij."""
    return [(f"{SOORT_PAGINA}{i['url_endpoint']}", f"{i['groep']} → {i['label']}") for i in NAV_ITEMS]


def doel(soort):
    """Waar een taak naartoe leidt en wat de afrondvraag oproept: {'label', 'endpoint', 'afronden_op'}, of None
    voor een taak zonder pagina (alleen afvinken). Een onbekende soort (bijvoorbeeld een verdwenen pagina) telt
    als een taak zonder pagina."""
    if soort and soort.startswith(SOORT_PRESET):
        return TAAK_SOORTEN.get(soort[len(SOORT_PRESET):])
    if soort and soort.startswith(SOORT_PAGINA):
        item = _nav_item(soort[len(SOORT_PAGINA):])
        if item:
            return {"label": item["label"], "endpoint": item["url_endpoint"], "afronden_op": set(item["endpoints"])}
    return None


def endpoint_toegankelijk(endpoint, rol, secties):
    """Mag dit account deze pagina openen? Dezelfde regels als de controle bij elk verzoek (zie app.py)."""
    if endpoint in OPEN_ENDPOINTS:
        return True
    if endpoint in BEHEERDER_ENDPOINTS and rol != "beheerder":
        return False
    sectie = ENDPOINT_SECTIE.get(endpoint)
    return not sectie or heeft_sectie_toegang(rol, secties, sectie)


def toewijsbare_gebruikers(db):
    return db.execute(
        "SELECT id, naam, rol, secties FROM gebruikers WHERE actief = 1 ORDER BY naam COLLATE NOCASE"
    ).fetchall()


def getagde_personen(db, voor_wie, *andere_teksten):
    """De accounts die met @naam aan de taak zijn getagd: (gebruiker_ids, onbekende_namen).

    Wie in 'Voor wie?' staat telt altijd mee, en een @naam daar die geen actief account is, komt terug als onbekend
    (een typfout mag niet stilletjes niemand opleveren). Een @naam in de naam of toelichting van de taak telt ook mee,
    maar daar is een onbekende naam geen fout: het kan ook gewoon een e-mailadres zijn."""
    actief = {r["naam"].lower(): r["id"] for r in toewijsbare_gebruikers(db)}
    ids, onbekend = [], []
    for tekst, streng in [(voor_wie, True)] + [(t, False) for t in andere_teksten]:
        for match in TAG_PATROON.finditer(tekst or ""):
            naam = match.group(1)
            gebruiker_id = actief.get(naam.lower())
            if gebruiker_id is not None:
                if gebruiker_id not in ids:
                    ids.append(gebruiker_id)
            elif streng and naam not in onbekend:
                onbekend.append(naam)
    return ids, onbekend


def schoon_stappen(tekst):
    """De stappen van een checklist uit een tekst met een stap per regel: lege regels weg, korte stappen, hooguit
    MAX_STAPPEN. Geeft de tekst terug zoals hij wordt bewaard (een stap per regel), of None."""
    stappen = [" ".join(r.split())[:MAX_TEKENS_STAP] for r in (tekst or "").splitlines()]
    stappen = [x for x in stappen if x][:MAX_STAPPEN]
    return "\n".join(stappen) or None


def stappen_van(taak):
    return [x for x in (taak["stappen"] or "").split("\n") if x]


def _plus_maand(dag):
    jaar, maand = divmod(dag.month, 12)
    return date(dag.year + jaar, maand + 1, dag.day)


def volgende_datum(db, herhaling, deadline, vandaag):
    """De volgende uiterste datum van een terugkerende taak: de eerstvolgende datum in de reeks na de vorige die niet
    in het verleden ligt (was iemand te laat, dan schuift de reeks mee in plaats van dat er een rij verlopen taken
    ontstaat)."""
    if herhaling == "verkoopdagen":
        from voorspelling import dag_is_open, lees_verkoopdagen

        weekdagen, uitzonderingen = lees_verkoopdagen(db)
        dag = max(deadline + timedelta(days=1), vandaag)
        for _ in range(120):
            if dag_is_open(dag, weekdagen, uitzonderingen):
                return dag
            dag += timedelta(days=1)
        return max(deadline, vandaag) + timedelta(days=7)
    if herhaling == "maand":
        dag = _plus_maand(deadline)
        while dag < vandaag:
            dag = _plus_maand(dag)
        return dag
    stap = timedelta(days=14 if herhaling == "2weken" else 7)
    dag = deadline + stap
    while dag < vandaag:
        dag += stap
    return dag


def _start_op(herhaling, deadline, vandaag):
    """Vanaf welke datum een terugkerende taak op het overzicht staat (leeg: meteen)."""
    start = deadline - timedelta(days=VOORAF_DAGEN[herhaling])
    return start.isoformat() if start > vandaag else None


def maak_taak(db, titel, omschrijving, soort, deadline, gebruiker_ids, iedereen, door_naam, herhaling=None, stappen=None):
    """Maakt een taak en wijst die toe. Geeft (taak_id, None) of (None, foutmelding)."""
    titel = (titel or "").strip()
    if not titel:
        return None, "Geef de taak een naam."
    if not gebruiker_ids:
        return None, "Tag minstens één persoon met een @, bijvoorbeeld @bakker."
    deadline_datum = None
    if deadline:
        try:
            deadline_datum = datetime.strptime(deadline, "%Y-%m-%d").date()
        except ValueError:
            return None, "Die deadline is geen geldige datum."
    herhaling = herhaling if herhaling in HERHALINGEN else None
    if herhaling and deadline_datum is None:
        return None, "Kies een uiterste datum voor de eerste keer: daarna komt de taak vanzelf terug."
    if herhaling == "maand" and deadline_datum.day > 28:
        return None, "Kies voor een maandelijkse taak een datum tot en met de 28e, zodat hij elke maand kan terugkomen."
    gekozen = doel(soort)
    if soort != SOORT_EIGEN and gekozen is None:
        return None, "Kies waar de taak over gaat."
    rijen = {r["id"]: r for r in toewijsbare_gebruikers(db)}
    if any(g not in rijen for g in gebruiker_ids):
        return None, "Een gekozen persoon bestaat niet (meer) of is geblokkeerd."
    if gekozen:
        zonder_toegang = [
            rijen[g]["naam"] for g in gebruiker_ids if not endpoint_toegankelijk(gekozen["endpoint"], rijen[g]["rol"], rijen[g]["secties"])
        ]
        if zonder_toegang:
            return None, f"{', '.join(zonder_toegang)} heeft geen toegang tot '{gekozen['label']}'. Kies een andere persoon of pas de rechten aan bij Accounts."
    cursor = db.execute(
        """INSERT INTO taken (titel, omschrijving, soort, deadline, iedereen, aangemaakt_door, aangemaakt_op,
                              herhaling, start_op, stappen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (titel, (omschrijving or "").strip() or None, soort, deadline or None, 1 if iedereen else 0, door_naam,
         datetime.now().strftime("%Y-%m-%d %H:%M"), herhaling,
         _start_op(herhaling, deadline_datum, vandaag_amsterdam()) if herhaling else None, schoon_stappen(stappen)),
    )
    for gebruiker_id in sorted(set(gebruiker_ids)):
        db.execute("INSERT INTO taak_toewijzingen (taak_id, gebruiker_id) VALUES (?, ?)", (cursor.lastrowid, gebruiker_id))
    db.commit()
    return cursor.lastrowid, None


def _afgevinkt(tekst):
    return {int(x) for x in (tekst or "").split(",") if x.strip().isdigit()}


def _verrijk(db, taken_rijen, vandaag=None, gebruiker_id=None):
    """Zet er per taak de toegewezen mensen (met of ze klaar zijn), de stappen en de deadline-status bij.
    Met gebruiker_id ook welke stappen die persoon al heeft afgevinkt ('mijn_afgevinkt')."""
    vandaag = vandaag or vandaag_amsterdam().isoformat()
    uitkomst = []
    for t in taken_rijen:
        mensen = []
        for r in db.execute(
            """SELECT g.id, g.naam, tz.afgerond_op, tz.afgevinkt FROM taak_toewijzingen tz
               JOIN gebruikers g ON g.id = tz.gebruiker_id WHERE tz.taak_id = ? ORDER BY g.naam COLLATE NOCASE""",
            (t["id"],),
        ).fetchall():
            mens = dict(r)
            mens["afgevinkt"] = sorted(_afgevinkt(mens["afgevinkt"]))
            mensen.append(mens)
        taak = dict(t)
        taak["mensen"] = mensen
        taak["stappen_lijst"] = stappen_van(t)
        taak["mijn_afgevinkt"] = next((m["afgevinkt"] for m in mensen if m["id"] == gebruiker_id), [])
        taak["te_laat"] = bool(t["deadline"] and t["afgerond_op"] is None and t["deadline"] < vandaag)
        taak["gepland"] = bool(t["start_op"] and t["afgerond_op"] is None and t["start_op"] > vandaag)
        taak["herhaling_label"] = HERHALINGEN.get(t["herhaling"])
        taak["doel"] = doel(t["soort"])
        uitkomst.append(taak)
    return uitkomst


def taken_voor_gebruiker(db, gebruiker_id):
    """De open taken van deze persoon waar hij/zij zelf nog iets aan moet doen, dringendste eerst. Een terugkerende
    taak die nog niet aan de beurt is (zie start_op) staat er nog niet bij."""
    vandaag = vandaag_amsterdam().isoformat()
    rijen = db.execute(
        """SELECT t.* FROM taken t JOIN taak_toewijzingen tz ON tz.taak_id = t.id
           WHERE tz.gebruiker_id = ? AND tz.afgerond_op IS NULL AND t.afgerond_op IS NULL
             AND (t.start_op IS NULL OR t.start_op <= ?)
           ORDER BY (t.deadline IS NULL), t.deadline, t.id""",
        (gebruiker_id, vandaag),
    ).fetchall()
    return _verrijk(db, rijen, vandaag, gebruiker_id)


def open_taken(db):
    """Alle openstaande taken voor de beheerpagina, ook de terugkerende die nog niet aan de beurt zijn."""
    rijen = db.execute(
        "SELECT * FROM taken WHERE afgerond_op IS NULL ORDER BY (deadline IS NULL), deadline, id"
    ).fetchall()
    return _verrijk(db, rijen)


def afgeronde_taken(db, aantal=15):
    rijen = db.execute("SELECT * FROM taken WHERE afgerond_op IS NOT NULL ORDER BY afgerond_op DESC, id DESC LIMIT ?", (aantal,)).fetchall()
    return _verrijk(db, rijen)


def vind_taak(db, taak_id):
    rij = db.execute("SELECT * FROM taken WHERE id = ?", (taak_id,)).fetchone()
    return _verrijk(db, [rij])[0] if rij else None


def taak_voor_persoon(db, taak_id, gebruiker_id):
    """De taak zoals deze persoon hem ziet (met zijn eigen afgevinkte stappen), of None als hij niet aan hem is
    toegewezen of al klaar is."""
    rij = db.execute(
        """SELECT t.* FROM taken t JOIN taak_toewijzingen tz ON tz.taak_id = t.id
           WHERE t.id = ? AND tz.gebruiker_id = ? AND tz.afgerond_op IS NULL AND t.afgerond_op IS NULL""",
        (taak_id, gebruiker_id),
    ).fetchone()
    return _verrijk(db, [rij], gebruiker_id=gebruiker_id)[0] if rij else None


def vink_stap(db, taak_id, gebruiker_id, index, aan):
    """Vinkt een stap van de checklist aan of uit voor deze persoon. Geeft {'afgevinkt': [...], 'totaal': n} of None
    (geen geldige taak, stap of persoon)."""
    taak = taak_voor_persoon(db, taak_id, gebruiker_id)
    if taak is None or not 0 <= index < len(taak["stappen_lijst"]):
        return None
    gevinkt = set(taak["mijn_afgevinkt"])
    gevinkt.add(index) if aan else gevinkt.discard(index)
    db.execute(
        "UPDATE taak_toewijzingen SET afgevinkt = ? WHERE taak_id = ? AND gebruiker_id = ?",
        (",".join(str(i) for i in sorted(gevinkt)), taak_id, gebruiker_id),
    )
    db.commit()
    return {"afgevinkt": sorted(gevinkt), "totaal": len(taak["stappen_lijst"])}


def _maak_volgende(db, taak, vandaag):
    """De volgende keer van een terugkerende taak, voor dezelfde mensen. Geeft de nieuwe uiterste datum."""
    volgende = volgende_datum(db, taak["herhaling"], date.fromisoformat(taak["deadline"]), vandaag)
    cursor = db.execute(
        """INSERT INTO taken (titel, omschrijving, soort, deadline, iedereen, aangemaakt_door, aangemaakt_op,
                              herhaling, start_op, stappen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (taak["titel"], taak["omschrijving"], taak["soort"], volgende.isoformat(), taak["iedereen"],
         taak["aangemaakt_door"], datetime.now().strftime("%Y-%m-%d %H:%M"), taak["herhaling"],
         _start_op(taak["herhaling"], volgende, vandaag), taak["stappen"]),
    )
    db.execute(
        "INSERT INTO taak_toewijzingen (taak_id, gebruiker_id) SELECT ?, gebruiker_id FROM taak_toewijzingen WHERE taak_id = ?",
        (cursor.lastrowid, taak["id"]),
    )
    return volgende


def rond_af(db, taak_id, gebruiker_id, naam, voor_iedereen=False):
    """Zet de taak voor deze persoon op afgerond (of, met voor_iedereen, voor alle gekozen mensen). Geeft de taak
    terug met 'klaar' (de hele taak is klaar) en 'volgende' (de datum van de volgende keer bij een terugkerende taak),
    of None als er niets te doen was (onbekend, al klaar, of niet aan deze persoon toegewezen). Heeft de taak
    stappen die nog niet allemaal zijn afgevinkt, dan verandert er niets en komt er 'onvolledig': (afgevinkt, totaal)
    bij."""
    taak = db.execute("SELECT * FROM taken WHERE id = ?", (taak_id,)).fetchone()
    if taak is None or taak["afgerond_op"] is not None:
        return None
    stappen = stappen_van(taak)
    if stappen and not voor_iedereen:
        mijn = taak_voor_persoon(db, taak_id, gebruiker_id)
        if mijn is None:
            return None
        if len(mijn["mijn_afgevinkt"]) < len(stappen):
            resultaat = dict(taak)
            resultaat.update(klaar=False, volgende=None, onvolledig=(len(mijn["mijn_afgevinkt"]), len(stappen)))
            return resultaat
    nu = datetime.now().strftime("%Y-%m-%d %H:%M")
    if voor_iedereen:
        db.execute("UPDATE taak_toewijzingen SET afgerond_op = ? WHERE taak_id = ? AND afgerond_op IS NULL", (nu, taak_id))
    else:
        eigen = db.execute(
            "UPDATE taak_toewijzingen SET afgerond_op = ? WHERE taak_id = ? AND gebruiker_id = ? AND afgerond_op IS NULL",
            (nu, taak_id, gebruiker_id),
        )
        if eigen.rowcount == 0:
            return None
    nog_open = db.execute(
        "SELECT COUNT(*) FROM taak_toewijzingen WHERE taak_id = ? AND afgerond_op IS NULL", (taak_id,)
    ).fetchone()[0]
    klaar = voor_iedereen or not taak["iedereen"] or nog_open == 0
    volgende = None
    if klaar:
        db.execute("UPDATE taken SET afgerond_op = ?, afgerond_door = ? WHERE id = ?", (nu, naam, taak_id))
        if taak["herhaling"] in HERHALINGEN and taak["deadline"]:
            volgende = _maak_volgende(db, taak, vandaag_amsterdam())
    db.commit()
    resultaat = dict(taak)
    resultaat.update(klaar=klaar, volgende=volgende)
    return resultaat


def verwijder_taak(db, taak_id):
    cursor = db.execute("DELETE FROM taken WHERE id = ?", (taak_id,))
    db.commit()
    return cursor.rowcount > 0


def vraag_kandidaten(db, gebruiker_id, endpoint):
    """De open taken van deze persoon waarvan een opslaan-actie net is gedaan: de site vraagt dan of de taak klaar is."""
    return [t for t in taken_voor_gebruiker(db, gebruiker_id) if t["doel"] and endpoint in t["doel"]["afronden_op"]]
