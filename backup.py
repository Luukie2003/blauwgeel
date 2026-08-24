"""Maakt een back-up van voorraad.db en ruimt oude back-ups op.

Bedoeld om dagelijks te draaien via een PythonAnywhere Scheduled Task:

    python3 backup.py

Gebruikt alleen de standaardbibliotheek (geen virtualenv nodig; mail.py
gebruikt ook alleen smtplib/email uit de standaardbibliotheek). Back-ups
komen in de map backups/, als voorraad-JJJJ-MM-DD.db. Back-ups ouder dan
BEWAARTERMIJN_DAGEN worden automatisch verwijderd.

Elke maandag wordt de back-up van die dag ook als bijlage gemaild naar
BACKUP_MAIL_NAAR, als extra kopie buiten de server om.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import mail

BASE_DIR = Path(__file__).parent
BRON = BASE_DIR / "voorraad.db"
BACKUP_MAP = BASE_DIR / "backups"
BEWAARTERMIJN_DAGEN = 90
BACKUP_MAIL_NAAR = "no-reply@kantineblauwgeel.nl"


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


def maak_backup_met_naam(bestandsnaam):
    """Maakt een eenmalige back-up onder een specifieke bestandsnaam, buiten
    het dagelijkse voorraad-JJJJ-MM-DD.db-patroon om. Gebruikt als
    veiligheidskopie vlak voor een herstel-actie."""
    if not BRON.exists():
        return None
    BACKUP_MAP.mkdir(exist_ok=True)
    doel = BACKUP_MAP / bestandsnaam
    bron_conn = sqlite3.connect(BRON)
    doel_conn = sqlite3.connect(doel)
    with doel_conn:
        bron_conn.backup(doel_conn)
    bron_conn.close()
    doel_conn.close()
    return doel


def herstel_backup(bestandsnaam):
    """Zet voorraad.db terug naar de inhoud van de gekozen back-up."""
    gekozen_backup = BACKUP_MAP / bestandsnaam
    if not gekozen_backup.exists():
        return False
    backup_conn = sqlite3.connect(gekozen_backup)
    live_conn = sqlite3.connect(BRON)
    with live_conn:
        backup_conn.backup(live_conn)
    backup_conn.close()
    live_conn.close()
    return True


def ruim_oude_backups_op():
    if not BACKUP_MAP.exists():
        return
    grens = datetime.now() - timedelta(days=BEWAARTERMIJN_DAGEN)
    for bestand in BACKUP_MAP.glob("voorraad-*.db"):
        if datetime.fromtimestamp(bestand.stat().st_mtime) < grens:
            bestand.unlink()
            print(f"Oude back-up verwijderd: {bestand.name}")


def mail_backup(pad):
    """Mailt de gegeven back-up als bijlage naar BACKUP_MAIL_NAAR. Faalt
    stil (net als mail.stuur_mail zelf) als er geen email_instellingen.py
    is -- de back-up zelf staat dan alsnog gewoon op de server."""
    onderwerp = f"Wekelijkse back-up {pad.stem}"
    tekst = (
        f"Bijgevoegd de wekelijkse back-up van de database: {pad.name}.\n\n"
        "Dit is een automatische e-mail, als extra kopie naast de back-ups "
        "die al op de server staan."
    )
    gelukt = mail.stuur_mail(onderwerp, tekst, naar=BACKUP_MAIL_NAAR, bijlage_pad=pad)
    print(f"Back-up gemaild naar {BACKUP_MAIL_NAAR}: {'gelukt' if gelukt else 'mislukt'}")
    return gelukt


if __name__ == "__main__":
    pad = maak_backup()
    ruim_oude_backups_op()
    if pad and datetime.now().weekday() == 0:  # maandag
        mail_backup(pad)
