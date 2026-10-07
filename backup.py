"""Maakt een back-up van voorraad.db en ruimt oude back-ups op.

Bedoeld om dagelijks te draaien via een PythonAnywhere Scheduled Task:

    python3 backup.py

Gebruikt alleen de standaardbibliotheek (geen virtualenv nodig; mail.py
gebruikt ook alleen smtplib/email uit de standaardbibliotheek). Back-ups
komen in de map backups/, als voorraad-JJJJ-MM-DD.db. Back-ups ouder dan
BEWAARTERMIJN_DAGEN worden automatisch verwijderd.

Elke dag wordt de back-up ook als bijlage gemaild naar BACKUP_MAIL_NAAR,
als extra kopie buiten de server om (de database is maar enkele honderden
kB, dus dat is licht genoeg om dagelijks te doen -- bij een wekelijkse mail
ben je bij een kapotte server tot een week aan gegevens kwijt).

Elke back-up wordt direct na het maken gecontroleerd (PRAGMA
integrity_check). Is die niet in orde, dan wordt hij weggegooid en gaat er
een waarschuwingsmail uit, zodat je dat niet pas merkt als je hem nodig hebt.
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
# Na hoeveel dagen zonder nieuwe back-up de app een waarschuwing toont (de
# taak draait dagelijks, dus 1 gemiste dag is nog geen reden tot alarm).
MAX_LEEFTIJD_DAGEN = 2


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


def controleer_backup(pad):
    """Controleert of een back-up een heel, leesbaar SQLite-bestand is.
    Geeft (ok, melding) terug."""
    try:
        conn = sqlite3.connect(pad)
        try:
            resultaat = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.execute("SELECT COUNT(*) FROM producten").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as fout:
        return False, f"niet te openen of onvolledig: {fout}"
    if resultaat != "ok":
        return False, f"integriteitscontrole mislukt: {resultaat}"
    return True, "ok"


def bereken_backup_status(nu=None, backup_map=None):
    """Hoe vers is de nieuwste back-up? Voor de waarschuwing op het
    dashboard en op de Back-ups-pagina. 'laatste' is een datetime of None."""
    nu = nu or datetime.now()
    backup_map = backup_map or BACKUP_MAP
    bestanden = list(backup_map.glob("voorraad-????-??-??.db")) if backup_map.exists() else []
    if not bestanden:
        return {"ok": False, "laatste": None, "tekst": "Er is nog geen back-up gemaakt."}
    laatste = max(datetime.fromtimestamp(b.stat().st_mtime) for b in bestanden)
    dagen = (nu - laatste).days
    if dagen >= MAX_LEEFTIJD_DAGEN:
        return {
            "ok": False,
            "laatste": laatste,
            "tekst": f"De laatste back-up is {dagen} dagen oud. Controleer de dagelijkse back-uptaak.",
        }
    return {"ok": True, "laatste": laatste, "tekst": "Back-ups lopen goed."}


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
    onderwerp = f"Back-up {pad.stem}"
    tekst = (
        f"Bijgevoegd de back-up van de database van vandaag: {pad.name}.\n\n"
        "Dit is een automatische e-mail, als extra kopie naast de back-ups "
        "die al op de server staan."
    )
    gelukt = mail.stuur_mail(onderwerp, tekst, naar=BACKUP_MAIL_NAAR, bijlage_pad=pad)
    print(f"Back-up gemaild naar {BACKUP_MAIL_NAAR}: {'gelukt' if gelukt else 'mislukt'}")
    return gelukt


def meld_mislukte_backup(reden):
    onderwerp = "WAARSCHUWING: back-up van Kantine Beheer mislukt"
    tekst = (
        f"De dagelijkse back-up van de database is niet gelukt: {reden}\n\n"
        "Kijk op de server of voorraad.db in orde is. De oudere back-ups "
        "zijn niet aangeraakt."
    )
    mail.stuur_mail(onderwerp, tekst, naar=BACKUP_MAIL_NAAR)


if __name__ == "__main__":
    pad = maak_backup()
    if pad is None:
        meld_mislukte_backup("voorraad.db is niet gevonden.")
        raise SystemExit(1)
    ok, melding = controleer_backup(pad)
    if not ok:
        # Een kapotte back-up weggooien: anders telt hij mee als "de back-up
        # van vandaag" en wordt hij straks gemaild/als herstelpunt gebruikt.
        pad.unlink()
        print(f"Back-up afgekeurd en verwijderd: {melding}")
        meld_mislukte_backup(melding)
        raise SystemExit(1)
    ruim_oude_backups_op()
    mail_backup(pad)
