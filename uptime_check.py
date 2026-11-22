"""Controleert of de site bereikbaar is en mailt een melding bij storing.

Bedoeld om elk uur te draaien via een PythonAnywhere Scheduled Task:

    python3 uptime_check.py

Gebruikt alleen de standaardbibliotheek (net als backup.py -- geen
virtualenv nodig). Onthoudt de laatste status in uptime_status.txt, zodat er
maar één mail wordt gestuurd bij het begin van een storing en één zodra de
site weer bereikbaar is, in plaats van elk uur opnieuw dezelfde melding.

Eén trage of mislukte poging is nog geen storing: bij PythonAnywhere hapert
een enkel verzoek soms even (in november 2026 een paar keer 's ochtends, met
een time-out na 15 seconden terwijl de site een uur later gewoon reageerde).
Daarom wordt het na een mislukte poging nog een paar keer geprobeerd, met een
minuut ertussen, en gaat de mail pas uit als geen enkele poging lukt.

Elke controle komt ook in de systeemstatus (taakstatus.py), ook een hapering
die vanzelf over ging. Omdat deze taak elk uur draait, merkt hij daarbij ook op
dat een dagelijkse taak is stilgevallen.
"""

import time
import urllib.request
from pathlib import Path

import mail
import taakstatus

BASE_DIR = Path(__file__).parent
STATUS_PAD = BASE_DIR / "uptime_status.txt"
DB_PAD = BASE_DIR / "voorraad.db"
CONTROLE_URL = "https://www.kantineblauwgeel.nl/login"
TIMEOUT_SECONDEN = 30
POGINGEN = 3
PAUZE_SECONDEN = 60


def site_bereikbaar():
    """Eén poging: (bereikbaar, foutmelding)."""
    try:
        with urllib.request.urlopen(CONTROLE_URL, timeout=TIMEOUT_SECONDEN) as response:
            if response.status == 200:
                return True, None
            return False, f"HTTP-status {response.status}"
    except Exception as fout:
        return False, str(fout)


def _wacht(seconden):
    time.sleep(seconden)


def probeer():
    """Tot POGINGEN keer, met PAUZE_SECONDEN ertussen; stopt zodra een poging lukt. Geeft (bereikbaar, fouten) terug:
    fouten zijn de foutmeldingen van de mislukte pogingen, in volgorde."""
    fouten = []
    for poging in range(1, POGINGEN + 1):
        bereikbaar, foutmelding = site_bereikbaar()
        if bereikbaar:
            return True, fouten
        fouten.append(foutmelding)
        if poging < POGINGEN:
            _wacht(PAUZE_SECONDEN)
    return False, fouten


def vorige_status():
    if STATUS_PAD.exists():
        return STATUS_PAD.read_text().strip()
    return "ok"


def sla_status_op(status):
    STATUS_PAD.write_text(status)


def ontvanger():
    """Alleen de systeembeheerder (zie mail.systeembeheerder_adres); zonder e-mailadres daar het standaardadres."""
    return mail.systeembeheerder_adres(db_pad=DB_PAD)


def samenvatting(bereikbaar, fouten):
    """Wat de controle meldt, in één zin: voor de systeemstatus en de uitvoer van de taak."""
    if bereikbaar and not fouten:
        return "Site bereikbaar"
    if bereikbaar:
        return f"Site bereikbaar, pas bij poging {len(fouten) + 1} (eerst: {fouten[0]})"
    return f"Site reageerde niet, ook niet na {len(fouten)} pogingen: {fouten[-1]}"


def controleer():
    """Eén controle, zoals de taak die elk uur doet."""
    bereikbaar, fouten = probeer()
    status = "ok" if bereikbaar else "down"
    vorige = vorige_status()

    if status != vorige:
        if status == "down":
            mail.stuur_mail(
                "Kantine Beheer is niet bereikbaar",
                f"De site {CONTROLE_URL} reageert niet goed: {POGINGEN} pogingen achter elkaar, met telkens "
                f"{PAUZE_SECONDEN // 60} minuut ertussen, kregen geen goed antwoord.\n\n"
                f"Foutmelding (laatste poging): {fouten[-1]}\n\n"
                "De controle draait elk uur. Dit is een automatische melding, gestuurd bij het begin van de storing; "
                "zodra de site weer reageert, krijg je daar ook een mail over.",
                naar=ontvanger(),
            )
        else:
            mail.stuur_mail(
                "Kantine Beheer is weer bereikbaar",
                f"De site {CONTROLE_URL} reageert weer normaal.",
                naar=ontvanger(),
            )

    sla_status_op(status)
    melding = samenvatting(bereikbaar, fouten)
    # De controle zelf is gelukt, ook als de site plat ligt: daarover gaat de mail hierboven al.
    taakstatus.registreer("bereikbaarheid", True, melding, db_pad=DB_PAD)
    print(f"Status: {status} ({melding})")


if __name__ == "__main__":
    controleer()
