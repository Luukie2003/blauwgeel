"""Kleine hulpfuncties die alle onderdelen van de Kantine-tv (prijzenscherm, dia's, tv) delen."""

import hashlib
import os
import sqlite3
import time

from flask import current_app


def _voor_hash(waarde):
    """sqlite3.Row's eigen __repr__ toont een geheugenadres (verschilt
    dus bij elke nieuwe query, ook zonder inhoudelijke wijziging) --
    zet 'm daarom om naar een gewone tuple voor een stabiele repr()."""
    if isinstance(waarde, sqlite3.Row):
        return tuple(waarde)
    if isinstance(waarde, dict):
        return {k: _voor_hash(v) for k, v in waarde.items()}
    if isinstance(waarde, (list, tuple)):
        return [_voor_hash(v) for v in waarde]
    return waarde


def _versie(*delen):
    """Compacte 'vingerafdruk' van wat er nu op een kiosk-scherm te zien
    zou zijn. De schermen pollen deze via /versie-endpoints en herladen
    zichzelf zodra 'ie verandert -- zo komt een prijswijziging, een
    nieuwe sponsor of een aangepaste instelling binnen enkele seconden
    door op de TV, zonder dat de hele pagina om de zoveel minuten voor
    niets hoeft te herladen."""
    ruw = "|".join(repr(_voor_hash(deel)) for deel in delen)
    return hashlib.md5(ruw.encode()).hexdigest()[:12]


def _scherm_instellingen(db):
    return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()


def _prijzen_instellingen(db):
    return db.execute("SELECT * FROM kiosk_prijzen_instellingen WHERE id = 1").fetchone()


# De schermen vragen elke 10 seconden of er iets veranderd is (de versie-polls). Dat opnieuw uitrekenen kost op de server
# een paar tienden van een seconde per scherm, terwijl er meestal niets verandert. Daarom bewaart elk serverproces
# de uitkomst zolang de database dezelfde is.
_BEWAARDE_UITKOMSTEN = {}


def _database_stempel():
    """Verandert zodra iemand iets in de database bewaart (de 'file change counter' die SQLite zelf in de kop van het
    bestand ophoogt, plus grootte en tijdstip van het bestand), en elke minuut: wat van de klok afhangt (een dia die
    vanaf vandaag zichtbaar is, een wedstrijd van vandaag) is zo binnen een minuut bijgewerkt. None als er geen
    databasebestand is om te controleren (dan wordt er niets bewaard)."""
    pad = current_app.config.get("DATABASE")
    try:
        gegevens = os.stat(pad)
        with open(pad, "rb") as bestand:
            bestand.seek(24)
            teller = bestand.read(4)
    except (OSError, TypeError):
        return None
    return (str(pad), teller, gegevens.st_size, gegevens.st_mtime_ns, int(time.time() // 60))


def bewaarde_uitkomst(sleutel, bereken):
    """bereken() is de uitkomst die bij de huidige database hoort; die wordt per proces bewaard onder 'sleutel' zolang
    de database (zie _database_stempel) dezelfde is. Het scherm zelf en zijn versie-poll halen hun versie hier allebei
    op, zodat ze nooit net verschillen en het scherm niet voor niets herlaadt."""
    stempel = _database_stempel()
    if stempel is None:
        return bereken()
    gevonden = _BEWAARDE_UITKOMSTEN.get((stempel[0], sleutel))
    if gevonden is not None and gevonden[0] == stempel:
        return gevonden[1]
    uitkomst = bereken()  # de stempel is van vóór het rekenen: een wijziging tijdens het rekenen telt de volgende keer
    _BEWAARDE_UITKOMSTEN[(stempel[0], sleutel)] = (stempel, uitkomst)
    return uitkomst
