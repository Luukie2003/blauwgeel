"""Maakt een back-up van voorraad.db en ruimt oude back-ups op.

Bedoeld om dagelijks te draaien via een PythonAnywhere Scheduled Task:

    python3 backup.py

Gebruikt alleen de standaardbibliotheek (geen virtualenv nodig). Back-ups
komen in de map backups/, als voorraad-JJJJ-MM-DD.db. Back-ups ouder dan
BEWAARTERMIJN_DAGEN worden automatisch verwijderd.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
BRON = BASE_DIR / "voorraad.db"
BACKUP_MAP = BASE_DIR / "backups"
BEWAARTERMIJN_DAGEN = 90


def maak_backup():
    if not BRON.exists():
        print("voorraad.db bestaat nog niet -- niets om te back-uppen.")
        return None

    BACKUP_MAP.mkdir(exist_ok=True)
    vandaag = datetime.now().strftime("%Y-%m-%d")
    doel = BACKUP_MAP / f"voorraad-{vandaag}.db"

    # Via de sqlite backup-API in plaats van een losse bestandskopie, zodat
    # een back-up ook veilig is als de app op dat moment net iets wegschrijft.
    bron_conn = sqlite3.connect(BRON)
    doel_conn = sqlite3.connect(doel)
    with doel_conn:
        bron_conn.backup(doel_conn)
    bron_conn.close()
    doel_conn.close()

    print(f"Back-up gemaakt: {doel.name}")
    return doel


def ruim_oude_backups_op():
    if not BACKUP_MAP.exists():
        return
    grens = datetime.now() - timedelta(days=BEWAARTERMIJN_DAGEN)
    for bestand in BACKUP_MAP.glob("voorraad-*.db"):
        if datetime.fromtimestamp(bestand.stat().st_mtime) < grens:
            bestand.unlink()
            print(f"Oude back-up verwijderd: {bestand.name}")


if __name__ == "__main__":
    maak_backup()
    ruim_oude_backups_op()
