"""Controleert of de site bereikbaar is en mailt een melding bij storing.

Bedoeld om elk uur te draaien via een PythonAnywhere Scheduled Task:

    python3 uptime_check.py

Gebruikt alleen de standaardbibliotheek (net als backup.py -- geen
virtualenv nodig). Onthoudt de laatste status in uptime_status.txt, zodat er
maar één mail wordt gestuurd bij het begin van een storing en één zodra de
site weer bereikbaar is, in plaats van elk uur opnieuw dezelfde melding.
"""

import urllib.request
from pathlib import Path

import mail

BASE_DIR = Path(__file__).parent
STATUS_PAD = BASE_DIR / "uptime_status.txt"
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


if __name__ == "__main__":
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
            )
        else:
            mail.stuur_mail(
                "Kantine Beheer is weer bereikbaar",
                f"De site {CONTROLE_URL} reageert weer normaal.",
            )

    sla_status_op(status)
    print(f"Status: {status}" + (f" ({foutmelding})" if foutmelding else ""))
