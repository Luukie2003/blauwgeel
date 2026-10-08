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

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import mail
import onderhoud

BASE_DIR = Path(__file__).parent
BRON = BASE_DIR / "voorraad.db"
BACKUP_MAP = BASE_DIR / "backups"
BEWAARTERMIJN_DAGEN = 90
BACKUP_MAIL_NAAR = "no-reply@kantineblauwgeel.nl"
# Na hoeveel dagen zonder nieuwe back-up de app een waarschuwing toont (de
# taak draait dagelijks, dus 1 gemiste dag is nog geen reden tot alarm).
MAX_LEEFTIJD_DAGEN = 2
# Eens per maand wordt een back-up echt "terugzet-getest", zie controleer_herstel.
HERSTELCONTROLE_BESTAND = "laatste-herstelcontrole.json"
# Zonder deze tabellen is een back-up niet bruikbaar om mee te herstellen.
VERPLICHTE_TABELLEN = (
    "producten", "gebruikers", "instellingen", "mutaties", "tellingen", "telling_regels",
    "kassa_tellingen", "kluis_tellingen",
)


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


def controleer_herstel(pad, live_pad=None):
    """Test of een back-up echt te gebruiken is om mee te herstellen, op dezelfde
    manier als herstel_backup() dat doet maar dan in een wegwerp-database: de
    back-up wordt erin teruggezet, heel doorgelezen (elke tabel, elke regel) en
    gecontroleerd op de tabellen die je nodig hebt. Raakt voorraad.db nooit aan.

    Geeft {"ok", "melding", "backup", "tabellen", "rijen", "datum"} terug."""
    pad = Path(pad)
    resultaat = {
        "datum": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "backup": pad.name,
        "ok": False,
        "melding": "",
        "tabellen": 0,
        "rijen": 0,
    }
    with tempfile.TemporaryDirectory() as tmp:
        herstel_pad = Path(tmp) / "herstel.db"
        try:
            bron = sqlite3.connect(pad)
            doel = sqlite3.connect(herstel_pad)
            try:
                with doel:
                    bron.backup(doel)  # precies wat "Herstellen" doet
            finally:
                bron.close()
            try:
                if doel.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    resultaat["melding"] = "integriteitscontrole van de teruggezette back-up mislukt"
                    return resultaat
                tabellen = [
                    r[0]
                    for r in doel.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                ]
                ontbrekend = [t for t in VERPLICHTE_TABELLEN if t not in tabellen]
                if ontbrekend:
                    resultaat["melding"] = "tabellen ontbreken: " + ", ".join(ontbrekend)
                    return resultaat
                rijen = {t: doel.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tabellen}
            finally:
                doel.close()
        except sqlite3.Error as fout:
            resultaat["melding"] = f"niet terug te zetten: {fout}"
            return resultaat

    resultaat["tabellen"] = len(rijen)
    resultaat["rijen"] = sum(rijen.values())
    if rijen["gebruikers"] < 1:
        resultaat["melding"] = "er staan geen accounts in de back-up"
        return resultaat
    # Een back-up met opeens veel minder producten dan de echte database is verdacht.
    live_pad = Path(live_pad or BRON)
    if live_pad.exists() and rijen["producten"] < 1:
        try:
            live = sqlite3.connect(live_pad)
            live_producten = live.execute("SELECT COUNT(*) FROM producten").fetchone()[0]
            live.close()
        except sqlite3.Error:
            live_producten = 0
        if live_producten >= 10:
            resultaat["melding"] = f"de back-up bevat geen producten, de echte database {live_producten}"
            return resultaat
    resultaat["ok"] = True
    resultaat["melding"] = f"terugzetten gelukt: {len(rijen)} tabellen, {resultaat['rijen']} regels"
    return resultaat


def schrijf_herstelcontrole(resultaat, backup_map=None):
    backup_map = Path(backup_map or BACKUP_MAP)
    backup_map.mkdir(exist_ok=True)
    (backup_map / HERSTELCONTROLE_BESTAND).write_text(json.dumps(resultaat, indent=2), encoding="utf-8")


def lees_herstelcontrole(backup_map=None):
    """De uitkomst van de laatste herstelcontrole, of None als die nog nooit is gedraaid."""
    pad = Path(backup_map or BACKUP_MAP) / HERSTELCONTROLE_BESTAND
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def herstelcontrole_is_aan_de_beurt(nu=None, backup_map=None):
    """Op de 1e van de maand, of als er nog nooit een is gedraaid."""
    nu = nu or datetime.now()
    return nu.day == 1 or lees_herstelcontrole(backup_map) is None


def bereken_backup_status(nu=None, backup_map=None):
    """Hoe vers is de nieuwste back-up, en lukte de laatste herstelcontrole? Voor
    de waarschuwing op het dashboard en op de Back-ups-pagina. 'laatste' is een
    datetime of None; 'herstel' de uitkomst van controleer_herstel() of None."""
    nu = nu or datetime.now()
    backup_map = backup_map or BACKUP_MAP
    herstel = lees_herstelcontrole(backup_map)
    bestanden = list(backup_map.glob("voorraad-????-??-??.db")) if backup_map.exists() else []
    if not bestanden:
        return {"ok": False, "laatste": None, "herstel": herstel, "tekst": "Er is nog geen back-up gemaakt."}
    laatste = max(datetime.fromtimestamp(b.stat().st_mtime) for b in bestanden)
    dagen = (nu - laatste).days
    if dagen >= MAX_LEEFTIJD_DAGEN:
        return {
            "ok": False,
            "laatste": laatste,
            "herstel": herstel,
            "tekst": f"De laatste back-up is {dagen} dagen oud. Controleer de dagelijkse back-uptaak.",
        }
    if herstel and not herstel["ok"]:
        return {
            "ok": False,
            "laatste": laatste,
            "herstel": herstel,
            "tekst": f"De laatste herstelcontrole is mislukt: {herstel['melding']}.",
        }
    return {"ok": True, "laatste": laatste, "herstel": herstel, "tekst": "Back-ups lopen goed."}


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


def meld_mislukte_herstelcontrole(resultaat):
    onderwerp = "WAARSCHUWING: back-up van Kantine Beheer is niet terug te zetten"
    tekst = (
        f"De maandelijkse herstelcontrole van {resultaat['backup']} is mislukt: {resultaat['melding']}\n\n"
        "Dat betekent dat je deze back-up misschien niet kunt gebruiken als het nodig is. "
        "Kijk op de Back-ups-pagina of op de server wat er aan de hand is."
    )
    mail.stuur_mail(onderwerp, tekst, naar=BACKUP_MAIL_NAAR)


def voer_herstelcontrole_uit(pad):
    resultaat = controleer_herstel(pad)
    schrijf_herstelcontrole(resultaat)
    print(f"Herstelcontrole {pad.name}: {'gelukt' if resultaat['ok'] else 'MISLUKT'} -- {resultaat['melding']}")
    if not resultaat["ok"]:
        meld_mislukte_herstelcontrole(resultaat)
    return resultaat


def ruim_gegevens_op():
    """Bewaartermijnen toepassen op voorraad.db (zie onderhoud.py). Mislukt dit,
    dan mag dat de rest van de taak niet tegenhouden."""
    try:
        conn = sqlite3.connect(BRON, timeout=30)
        try:
            verwijderd = onderhoud.ruim_oude_gegevens(conn)
        finally:
            conn.close()
    except sqlite3.Error as fout:
        print(f"Opruimen overgeslagen: {fout}")
        return
    totaal = sum(verwijderd.values())
    print(f"Oude gegevens opgeruimd: {totaal} regels" + (f" ({verwijderd})" if totaal else ""))


def dagelijkse_taak(argv=()):
    """Wat de PythonAnywhere-taak elke dag doet. Geeft de exitcode terug (0 = goed)."""
    if "--herstelcontrole" in argv:
        # Los een herstelcontrole draaien op de nieuwste back-up, bijv. na een wijziging.
        bestanden = sorted(BACKUP_MAP.glob("voorraad-????-??-??.db"))
        if not bestanden:
            print("Geen back-ups gevonden.")
            return 1
        return 0 if voer_herstelcontrole_uit(bestanden[-1])["ok"] else 1

    pad = maak_backup()
    if pad is None:
        meld_mislukte_backup("voorraad.db is niet gevonden.")
        return 1
    ok, melding = controleer_backup(pad)
    if not ok:
        # Een kapotte back-up weggooien: anders telt hij mee als "de back-up
        # van vandaag" en wordt hij straks gemaild/als herstelpunt gebruikt.
        pad.unlink()
        print(f"Back-up afgekeurd en verwijderd: {melding}")
        meld_mislukte_backup(melding)
        return 1
    ruim_oude_backups_op()
    mail_backup(pad)
    if herstelcontrole_is_aan_de_beurt():
        voer_herstelcontrole_uit(pad)
    # Pas opruimen als de back-up van vandaag veilig staat.
    ruim_gegevens_op()
    return 0


if __name__ == "__main__":
    raise SystemExit(dagelijkse_taak(sys.argv[1:]))
