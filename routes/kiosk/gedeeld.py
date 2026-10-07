"""Kleine hulpfuncties die alle onderdelen van de Kantine-tv (prijzenscherm, dia's, tv) delen."""

import hashlib
import sqlite3


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
