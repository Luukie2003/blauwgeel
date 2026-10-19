"""De noodstop: met één knop de hele site en de tv-schermen afsluiten, bijvoorbeeld bij een vermoeden van een hack.

Alleen de eigenaar (gebruikers.eigenaar, één account) kan afsluiten en weer openen, en afsluiten kan pas als er een
noodcode is. Afsluiten logt iedereen overal uit, ook de beheerders en de eigenaar zelf. Daarna komt alleen een
beheerder er nog in, met zijn wachtwoord én de noodcode (mag_inloggen), zodat een gestolen wachtwoord alleen niet
genoeg is. Publieke pagina's, de apps en het wachtwoord-vergeten-formulier gaan dicht en de tv-schermen tonen een
vergrendel-scherm (zie app.py, noodstop_bewaken). Weer openen vraagt het wachtwoord van de eigenaar en de noodcode.

Kwijt of buitengesloten? Op de server (een Bash-console op PythonAnywhere) kan het altijd:

    cd ~/Voorraadbeheer && python3 noodstop.py status
    python3 noodstop.py open            # de site weer openen
    python3 noodstop.py dicht           # de site afsluiten
    python3 noodstop.py code-wissen     # de noodcode wissen (daarna opnieuw instellen op de site)
    python3 noodstop.py eigenaar NAAM   # een ander account eigenaar maken
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

MIN_CODE_LENGTE = 6
MAX_POGINGEN = 5  # zoveel foute pogingen om te openen, dan eerst even wachten
WACHTTIJD_MINUTEN = 15
DB_PAD = Path(__file__).resolve().parent / "voorraad.db"


def _nu():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def toestand(db):
    """{"actief", "sinds", "door", "reden", "code_ingesteld", "geblokkeerd_tot"}; op een oude database zonder de
    kolommen: niet actief."""
    try:
        rij = db.execute(
            """SELECT noodstop_actief, noodstop_sinds, noodstop_door, noodstop_reden, noodstop_code_hash,
                      noodstop_geblokkeerd_tot FROM instellingen WHERE id = 1"""
        ).fetchone()
    except sqlite3.OperationalError:
        rij = None
    if rij is None:
        return {"actief": False, "sinds": None, "door": None, "reden": None, "code_ingesteld": False,
                "geblokkeerd_tot": None}
    return {
        "actief": bool(rij[0]),
        "sinds": rij[1],
        "door": rij[2],
        "reden": rij[3],
        "code_ingesteld": bool(rij[4]),
        "geblokkeerd_tot": rij[5],
    }


def is_actief(db):
    return toestand(db)["actief"]


def eigenaar(db):
    """Het account van de eigenaar (id, naam), of None. Is er (nog) geen, bijvoorbeeld bij een nieuwe installatie, dan
    wordt het volgens dezelfde vaste regel als database/migraties.py (_m3_eigenaar_aanwijzen) aangewezen."""
    try:
        rij = db.execute("SELECT id, naam FROM gebruikers WHERE eigenaar = 1 AND actief = 1 ORDER BY id LIMIT 1").fetchone()
        if rij is None and not db.execute("SELECT 1 FROM gebruikers WHERE eigenaar = 1").fetchone():
            from database.migraties import _m3_eigenaar_aanwijzen

            _m3_eigenaar_aanwijzen(db)
            db.commit()
            rij = db.execute("SELECT id, naam FROM gebruikers WHERE eigenaar = 1 AND actief = 1 LIMIT 1").fetchone()
        return rij
    except sqlite3.OperationalError:
        return None


def is_eigenaar(db, gebruiker_id):
    e = eigenaar(db)
    return e is not None and gebruiker_id is not None and e[0] == gebruiker_id


def vergrendel(db, door, reden=None):
    """Sluit alles af en logt iedereen overal uit (sessie_versie omhoog, zie vereis_login in app.py)."""
    db.execute(
        """UPDATE instellingen SET noodstop_actief = 1, noodstop_sinds = ?, noodstop_door = ?, noodstop_reden = ?
           WHERE id = 1""",
        (_nu(), door, (reden or "").strip()[:200] or None),
    )
    db.execute("UPDATE gebruikers SET sessie_versie = COALESCE(sessie_versie, 0) + 1")
    db.commit()


def ontgrendel(db):
    db.execute(
        """UPDATE instellingen SET noodstop_actief = 0, noodstop_pogingen = 0, noodstop_geblokkeerd_tot = NULL
           WHERE id = 1"""
    )
    db.commit()


def zet_code(db, code):
    """Stelt de noodcode in; geeft een foutmelding of None terug."""
    code = (code or "").strip()
    if len(code) < MIN_CODE_LENGTE:
        return f"Kies een noodcode van minstens {MIN_CODE_LENGTE} tekens."
    db.execute("UPDATE instellingen SET noodstop_code_hash = ? WHERE id = 1",
               (generate_password_hash(code, method="pbkdf2:sha256:200000"),))
    db.commit()
    return None


def wis_code(db):
    db.execute("UPDATE instellingen SET noodstop_code_hash = NULL WHERE id = 1")
    db.commit()


def code_klopt(db, code):
    rij = db.execute("SELECT noodstop_code_hash FROM instellingen WHERE id = 1").fetchone()
    return bool(rij and rij[0] and code and check_password_hash(rij[0], code.strip()))


def mag_inloggen(db, gebruiker, code):
    """Inloggen tijdens een noodstop (het wachtwoord klopt al): alleen een beheerder, en alleen met de noodcode. Geeft
    een foutmelding, of None als het mag. Een foute noodcode telt als foute poging (zie foute_poging). Is er (nog) geen
    noodcode, bijvoorbeeld na 'python3 noodstop.py dicht' op de server, dan komt alleen de eigenaar erin."""
    if gebruiker["rol"] != "beheerder":
        return "De site is tijdelijk afgesloten. Probeer het later opnieuw."
    if (minuten := wachten(db)):
        return f"Te veel foute pogingen. Probeer het over {minuten} minuut/minuten opnieuw."
    if not toestand(db)["code_ingesteld"]:
        return None if is_eigenaar(db, gebruiker["id"]) else "De site is tijdelijk afgesloten. Probeer het later opnieuw."
    if not code_klopt(db, code):
        foute_poging(db)
        return "De site is afgesloten met de noodstop: vul ook de noodcode in. Wachtwoord of noodcode klopt niet."
    return None


def wachten(db):
    """Hoeveel minuten er nog gewacht moet worden na te veel foute pogingen (0 = niet)."""
    tot = toestand(db)["geblokkeerd_tot"]
    if not tot:
        return 0
    over = datetime.strptime(tot, "%Y-%m-%d %H:%M") - datetime.now()
    return max(0, int(over.total_seconds() // 60) + 1) if over.total_seconds() > 0 else 0


def foute_poging(db):
    """Telt een foute poging om te openen; na MAX_POGINGEN eerst WACHTTIJD_MINUTEN wachten."""
    rij = db.execute("SELECT COALESCE(noodstop_pogingen, 0) FROM instellingen WHERE id = 1").fetchone()
    pogingen = (rij[0] if rij else 0) + 1
    blokkade = None
    if pogingen >= MAX_POGINGEN:
        blokkade = (datetime.now() + timedelta(minutes=WACHTTIJD_MINUTEN)).strftime("%Y-%m-%d %H:%M")
        pogingen = 0
    db.execute("UPDATE instellingen SET noodstop_pogingen = ?, noodstop_geblokkeerd_tot = ? WHERE id = 1",
               (pogingen, blokkade))
    db.commit()


def maak_eigenaar(db, naam):
    """Maakt het (actieve) beheerdersaccount met deze naam eigenaar, en alle anderen niet. Geeft een foutmelding of
    None terug."""
    rij = db.execute(
        "SELECT id FROM gebruikers WHERE naam = ? COLLATE NOCASE AND rol = 'beheerder' AND actief = 1", (naam,)
    ).fetchone()
    if rij is None:
        return f"Geen actief beheerdersaccount met de naam '{naam}'."
    db.execute("UPDATE gebruikers SET eigenaar = CASE WHEN id = ? THEN 1 ELSE 0 END", (rij[0],))
    db.commit()
    return None


def _console(argumenten):
    """De noodstop vanaf de server zelf (zie de uitleg bovenaan dit bestand)."""
    db = sqlite3.connect(DB_PAD)
    opdracht = argumenten[0] if argumenten else "status"
    if opdracht == "open":
        ontgrendel(db)
        print("De site is weer open. Iedereen moet opnieuw inloggen.")
    elif opdracht == "dicht":
        vergrendel(db, "console op de server", "Afgesloten vanaf de server")
        print("De site is afgesloten; alleen de eigenaar kan nog inloggen.")
    elif opdracht == "code-wissen":
        wis_code(db)
        print("De noodcode is gewist. Stel een nieuwe in op de site (Beheer > Noodstop).")
    elif opdracht == "eigenaar" and len(argumenten) > 1:
        fout = maak_eigenaar(db, argumenten[1])
        print(fout or f"{argumenten[1]} is nu de eigenaar.")
    else:
        t = toestand(db)
        e = eigenaar(db)
        print(f"Noodstop: {'AFGESLOTEN sinds ' + t['sinds'] if t['actief'] else 'niet actief'}")
        print(f"Eigenaar: {e[1] if e else 'geen'} | noodcode ingesteld: {'ja' if t['code_ingesteld'] else 'nee'}")
    db.close()


if __name__ == "__main__":
    _console(sys.argv[1:])
