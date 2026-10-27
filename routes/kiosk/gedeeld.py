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


# Een thema over alle schermen heen (1.74.0): versiering die over het prijzenscherm en de dia's komt, zonder iets aan
# de inhoud te veranderen (zie templates/_kiosk_thema.html). Aan of uit met één klik op de Kiosk-hub of in de
# handterminal-app (Kantine-tv).
THEMAS = {"halloween": "Halloween"}


def kiosk_thema(db):
    """Het thema dat nu op de schermen staat ("halloween"), of None."""
    rij = _scherm_instellingen(db)
    thema = rij["thema"] if rij is not None and "thema" in rij.keys() else None
    return thema if thema in THEMAS else None


def zet_kiosk_thema(db, thema):
    """Een thema aan (een sleutel uit THEMAS) of uit (None). De schermen nemen het binnen 10 seconden over: het thema
    telt mee in hun versie (dias_versie en _prijzen_poll_van). Geeft het thema dat nu staat."""
    thema = thema if thema in THEMAS else None
    db.execute("UPDATE kiosk_scherm_instellingen SET thema = ? WHERE id = 1", (thema,))
    db.commit()
    return thema


def dias_versie(db, slides, *extra):
    """De versie van het dia-scherm: de dia's en het thema. [extra] geeft een eigen versie, zoals voor /kiosk/tv."""
    return _versie(*extra, slides, kiosk_thema(db))


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
