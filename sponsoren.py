"""Sponsoren met logo ("Mede mogelijk gemaakt door") voor het kantine scherm
en de prijzenlijst, in de stijl van de oude Canva-dia's: 1 dia per sponsor,
of 1 dia per groep (bijv. "Zaterdag 1") met meerdere logo's samen.

Op het kantine scherm komen deze dia's niet als 1 blok, maar tussen de
andere dia's door (na elke N dia's de volgende sponsor, zie de JS in
kiosk_scherm.html); op de prijzenlijst verschijnen ze om de zoveel seconden
even over de prijzen heen (zie kiosk_prijzen_scherm.html). De beheerpagina
staat in routes/sponsoren.py.
"""

import math

from helpers import KIOSK_AFBEELDINGEN_MAP

_VERHOUDING_CACHE = {}


def logo_verhouding(bestandsnaam):
    """Breedte : hoogte van een logo (1.0 = vierkant), uit het bestand zelf.
    Zonder (leesbaar) bestand 1.0. Onthouden per bestandsnaam: uploads krijgen
    altijd een nieuwe, willekeurige naam."""
    if not bestandsnaam:
        return 1.0
    if bestandsnaam not in _VERHOUDING_CACHE:
        try:
            from PIL import Image

            with Image.open(KIOSK_AFBEELDINGEN_MAP / bestandsnaam) as plaatje:
                breed, hoog = plaatje.size
            _VERHOUDING_CACHE[bestandsnaam] = round(breed / hoog, 3) if breed and hoog else 1.0
        except Exception:
            return 1.0
    return _VERHOUDING_CACHE[bestandsnaam]


def actieve_sponsoren(db):
    return db.execute(
        "SELECT * FROM kiosk_sponsorlogos WHERE actief = 1 ORDER BY volgorde, naam COLLATE NOCASE"
    ).fetchall()


def bouw_sponsor_dias(db, instellingen, sponsoren=None):
    """De sponsordia's in volgorde: een groep neemt de plek in van zijn
    eerste sponsor (op volgorde) en krijgt alle logo's van die groep, in
    stukken van 'logos per dia'. Zonder actieve sponsoren een lege lijst."""
    sponsoren = actieve_sponsoren(db) if sponsoren is None else sponsoren
    per_dia = max(1, instellingen["sponsors_logos_per_dia"])
    groepen = {}
    volgorde = []
    for s in sponsoren:
        groep = (s["groep"] or "").strip()
        sleutel = groep.lower() if groep else f"los-{s['id']}"
        if sleutel not in groepen:
            groepen[sleutel] = {"titel": groep or None, "logos": []}
            volgorde.append(sleutel)
        groepen[sleutel]["logos"].append(
            {
                "naam": s["naam"],
                "logo": s["logo"],
                "wit": bool(s["witte_achtergrond"]),
                "verhouding": logo_verhouding(s["logo"]),
            }
        )
    dias = []
    for sleutel in volgorde:
        groep = groepen[sleutel]
        for i in range(0, len(groep["logos"]), per_dia):
            dias.append(
                {
                    "type": "sponsorlogos",
                    "duur": max(3, instellingen["sponsors_duur_seconden"]),
                    "titel": groep["titel"],
                    "kop": instellingen["sponsors_kop"],
                    "achtergrond": instellingen["sponsors_achtergrond"],
                    "logos": _met_aandeel(groep["logos"][i : i + per_dia]),
                }
            )
    return dias


def _met_aandeel(logos):
    """Geeft elk logo een 'aandeel' van de rijbreedte (som = 1) voor dia's
    waarop de logo's naast elkaar staan: evenredig met de wortel van de
    verhouding, zodat een breed logo (Robertus) meer ruimte krijgt dan een
    vierkant (Gelkinge), maar niet zoveel dat het vierkante piepklein wordt.
    Het oppervlak van de logo's blijft zo ongeveer gelijk."""
    gewichten = [math.sqrt(l["verhouding"]) for l in logos]
    totaal = sum(gewichten) or 1.0
    return [dict(l, aandeel=round(g / totaal, 4)) for l, g in zip(logos, gewichten)]
