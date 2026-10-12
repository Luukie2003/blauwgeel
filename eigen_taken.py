"""Eigen taken: een beheerder voegt een taak toe aan "Wat moet er nu?" en koppelt die aan mensen.

Een taak kan bij een pagina horen (bijvoorbeeld "Prijzenlijst nalopen"): wie op de taak klikt, komt op die pagina.
Slaat iemand daar iets op, dan vraagt de site in een pop-up of de taak daarmee klaar is. Zo werkt het voor elke
pagina, niet alleen voor de prijzen: bij elke taak hoort een lijst met opslaan-acties (endpoints) die de vraag
oproepen, zie TAAK_SOORTEN, of bij "een pagina uit het menu" alle acties van die pagina (zie navigatie.py).

Een taak is voor een of meer mensen. Staat "iedereen" aan, dan moet elke gekozen persoon de taak zelf afronden en is
de taak pas klaar als de laatste dat heeft gedaan; anders is een van hen genoeg."""

from datetime import date, datetime

from helpers.mededelingen import TAG_PATROON
from helpers.toegang import heeft_sectie_toegang
from navigatie import NAV_ITEMS
from rechten import BEHEERDER_ENDPOINTS, ENDPOINT_SECTIE, OPEN_ENDPOINTS

SOORT_EIGEN = "eigen"
SOORT_PRESET = "preset:"
SOORT_PAGINA = "pagina:"

# Veelvoorkomende klussen. endpoint = de pagina waar de taak naartoe leidt; afronden_op = de opslaan-acties
# (POST-endpoints) waarna de site vraagt of de taak klaar is.
TAAK_SOORTEN = {
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


def maak_taak(db, titel, omschrijving, soort, deadline, gebruiker_ids, iedereen, door_naam):
    """Maakt een taak en wijst die toe. Geeft (taak_id, None) of (None, foutmelding)."""
    titel = (titel or "").strip()
    if not titel:
        return None, "Geef de taak een naam."
    if not gebruiker_ids:
        return None, "Tag minstens één persoon met een @, bijvoorbeeld @bakker."
    if deadline:
        try:
            datetime.strptime(deadline, "%Y-%m-%d")
        except ValueError:
            return None, "Die deadline is geen geldige datum."
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
        """INSERT INTO taken (titel, omschrijving, soort, deadline, iedereen, aangemaakt_door, aangemaakt_op)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (titel, (omschrijving or "").strip() or None, soort, deadline or None, 1 if iedereen else 0, door_naam,
         datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    for gebruiker_id in sorted(set(gebruiker_ids)):
        db.execute("INSERT INTO taak_toewijzingen (taak_id, gebruiker_id) VALUES (?, ?)", (cursor.lastrowid, gebruiker_id))
    db.commit()
    return cursor.lastrowid, None


def _verrijk(db, taken_rijen, vandaag=None):
    """Zet er per taak de toegewezen mensen (met of ze klaar zijn) en de deadline-status bij."""
    vandaag = vandaag or date.today().isoformat()
    uitkomst = []
    for t in taken_rijen:
        mensen = [
            dict(r)
            for r in db.execute(
                """SELECT g.id, g.naam, tz.afgerond_op FROM taak_toewijzingen tz
                   JOIN gebruikers g ON g.id = tz.gebruiker_id WHERE tz.taak_id = ? ORDER BY g.naam COLLATE NOCASE""",
                (t["id"],),
            ).fetchall()
        ]
        taak = dict(t)
        taak["mensen"] = mensen
        taak["te_laat"] = bool(t["deadline"] and t["afgerond_op"] is None and t["deadline"] < vandaag)
        taak["doel"] = doel(t["soort"])
        uitkomst.append(taak)
    return uitkomst


def taken_voor_gebruiker(db, gebruiker_id):
    """De open taken van deze persoon waar hij/zij zelf nog iets aan moet doen, dringendste eerst."""
    rijen = db.execute(
        """SELECT t.* FROM taken t JOIN taak_toewijzingen tz ON tz.taak_id = t.id
           WHERE tz.gebruiker_id = ? AND tz.afgerond_op IS NULL AND t.afgerond_op IS NULL
           ORDER BY (t.deadline IS NULL), t.deadline, t.id""",
        (gebruiker_id,),
    ).fetchall()
    return _verrijk(db, rijen)


def open_taken(db):
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


def rond_af(db, taak_id, gebruiker_id, naam, voor_iedereen=False):
    """Zet de taak voor deze persoon op afgerond (of, met voor_iedereen, voor alle gekozen mensen). Geeft de taak
    terug met 'klaar' (de hele taak is klaar), of None als er niets te doen was (onbekend, al klaar, of niet aan
    deze persoon toegewezen)."""
    taak = db.execute("SELECT * FROM taken WHERE id = ?", (taak_id,)).fetchone()
    if taak is None or taak["afgerond_op"] is not None:
        return None
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
    if klaar:
        db.execute("UPDATE taken SET afgerond_op = ?, afgerond_door = ? WHERE id = ?", (nu, naam, taak_id))
    db.commit()
    resultaat = dict(taak)
    resultaat["klaar"] = klaar
    return resultaat


def verwijder_taak(db, taak_id):
    cursor = db.execute("DELETE FROM taken WHERE id = ?", (taak_id,))
    db.commit()
    return cursor.rowcount > 0


def vraag_kandidaten(db, gebruiker_id, endpoint):
    """De open taken van deze persoon waarvan een opslaan-actie net is gedaan: de site vraagt dan of de taak klaar is."""
    return [t for t in taken_voor_gebruiker(db, gebruiker_id) if t["doel"] and endpoint in t["doel"]["afronden_op"]]
