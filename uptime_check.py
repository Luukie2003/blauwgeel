"""Controleert of de site bereikbaar is en mailt een melding bij storing.

Bedoeld om elk uur te draaien via een PythonAnywhere Scheduled Task:

    python3 uptime_check.py

Gebruikt alleen de standaardbibliotheek (net als backup.py -- geen
virtualenv nodig). Onthoudt de laatste status in uptime_status.txt, zodat er
maar één mail wordt gestuurd bij het begin van een storing en één zodra de
site weer bereikbaar is, in plaats van elk uur opnieuw dezelfde melding.

Elke controle komt ook in de systeemstatus (taakstatus.py). Omdat deze taak elk
uur draait, merkt hij daarbij ook op dat een dagelijkse taak is stilgevallen.
"""

import urllib.request
from pathlib import Path

import mail
import taakstatus

BASE_DIR = Path(__file__).parent
STATUS_PAD = BASE_DIR / "uptime_status.txt"
DB_PAD = BASE_DIR / "voorraad.db"
CONTROLE_URL = "https://www.kantineblauwgeel.nl/login"
TIMEOUT_SECONDEN = 15


def site_bereikbaar():
    try:
        with urllib.request.urlopen(CONTROLE_URL, timeout=TIMEOUT_SECONDEN) as response:
            return response.status == 200, None
    except Exception as fout:
        return False, str(fout)


def vorige_status():
    if STATUS_PAD.exists():
        return STATUS_PAD.read_text().strip()
    return "ok"


def sla_status_op(status):
    STATUS_PAD.write_text(status)


def ontvanger():
    """Alleen de systeembeheerder (zie mail.systeembeheerder_adres); zonder e-mailadres daar het standaardadres."""
    return mail.systeembeheerder_adres(db_pad=DB_PAD)


def controleer():
    """Eén controle, zoals de taak die elk uur doet."""
    bereikbaar, foutmelding = site_bereikbaar()
    status = "ok" if bereikbaar else "down"
    vorige = vorige_status()

    if status != vorige:
        if status == "down":
            mail.stuur_mail(
                "Kantine Beheer is niet bereikbaar",
                f"De site {CONTROLE_URL} reageert niet goed sinds de laatste controle "
                "(elk uur).\n\n"
                f"Foutmelding: {foutmelding}\n\n"
                "Dit is een automatische melding, gestuurd bij het begin van de storing.",
                naar=ontvanger(),
            )
        else:
            mail.stuur_mail(
                "Kantine Beheer is weer bereikbaar",
                f"De site {CONTROLE_URL} reageert weer normaal.",
                naar=ontvanger(),
            )

    sla_status_op(status)
    # De controle zelf is gelukt, ook als de site plat ligt: daarover gaat de mail hierboven al.
    taakstatus.registreer(
        "bereikbaarheid", True, "Site bereikbaar" if bereikbaar else f"Site reageerde niet: {foutmelding}", db_pad=DB_PAD
    )
    print(f"Status: {status}" + (f" ({foutmelding})" if foutmelding else ""))


if __name__ == "__main__":
    controleer()
