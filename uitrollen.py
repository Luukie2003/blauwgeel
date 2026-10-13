"""Nieuwe code veilig op de server zetten ("live zetten").

Hoe het werkt: het script scripts/zet_live.py (op je eigen computer) stuurt een
ondertekend verzoek naar POST /uitrollen. De server controleert de handtekening, haalt
de nieuwste code op (`git pull --ff-only`) en laat de web-app daarna herstarten.
Het endpoint doet alléén dat: de eigen repository bijwerken en, als de vastgezette pakketten
(requirements-vast.txt) zijn gewijzigd, precies die installeren. Er kan geen andere code mee worden
meegestuurd, alleen wat al in de repository staat. Mislukt het installeren, dan wordt de code
teruggezet naar de vorige versie, zodat code en pakketten nooit uit de pas lopen.

Staat er op de server geen `uitrol_geheim.txt`, dan is het endpoint uitgeschakeld
(404). Het geheim zet je met `python3 scripts/zet_live.py --maak-geheim`."""

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GEHEIM_BESTAND = BASE_DIR / "uitrol_geheim.txt"
# Het WSGI-bestand van de web-app op PythonAnywhere; het "aanraken" daarvan laat de
# app herstarten (zelfde als de Reload-knop). Elders (lokaal, testen) bestaat het niet.
STANDAARD_WSGI_BESTAND = "/var/www/www_kantineblauwgeel_nl_wsgi.py"
# Hoe oud een ondertekend verzoek mag zijn: een onderschept verzoek is daarna waardeloos.
MAX_LEEFTIJD_SECONDEN = 300
GIT_TIMEOUT_SECONDEN = 60
PIP_TIMEOUT_SECONDEN = 240
# De rooktest (rooktest.py) opent na het ophalen alle pagina's met de nieuwe code en een kopie van de echte database.
ROOKTEST_TIMEOUT_SECONDEN = 150
PAKKETTENBESTAND = "requirements-vast.txt"
# Wijzigt een van deze bestanden, dan moeten de pakketten op de server worden bijgewerkt.
PAKKETBESTANDEN = ("requirements.txt", PAKKETTENBESTAND)


def lees_geheim(pad=None):
    """Het gedeelde geheim, of None als het endpoint is uitgeschakeld."""
    try:
        geheim = Path(pad or GEHEIM_BESTAND).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return geheim if len(geheim) >= 32 else None  # een te kort geheim is geen geheim


def maak_handtekening(geheim, tijdstip, body):
    bericht = f"{int(tijdstip)}.".encode() + body
    return "sha256=" + hmac.new(geheim.encode(), bericht, hashlib.sha256).hexdigest()


def controleer_handtekening(geheim, tijdstip, handtekening, body, nu=None):
    """True als de handtekening klopt én het verzoek vers is."""
    try:
        tijdstip = int(tijdstip)
    except (TypeError, ValueError):
        return False
    if abs((nu if nu is not None else time.time()) - tijdstip) > MAX_LEEFTIJD_SECONDEN:
        return False
    verwacht = maak_handtekening(geheim, tijdstip, body)
    return hmac.compare_digest(verwacht, handtekening or "")


def _git(repo, *argumenten):
    return subprocess.run(
        ["git", *argumenten],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDEN,
        check=False,
    )


def huidige_commit(repo=BASE_DIR):
    """De korte hash van de code zoals die nu op schijf staat (of None)."""
    try:
        uitvoer = _git(repo, "rev-parse", "--short", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return None
    return uitvoer.stdout.strip() if uitvoer.returncode == 0 else None


def maak_pip_commando(repo=BASE_DIR, python=None):
    """Het commando om de vastgezette pakketten te installeren: in de virtualenv als de app daarin draait,
    anders met --user (PythonAnywhere zonder virtualenv). Python wordt gezocht op versienummer, want in de
    web-app is sys.executable de webserver en niet python zelf."""
    python = python or f"python{sys.version_info.major}.{sys.version_info.minor}"
    commando = [python, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(Path(repo) / PAKKETTENBESTAND)]
    if sys.prefix == sys.base_prefix:  # geen virtualenv
        commando.insert(4, "--user")
    return commando


def installeer_pakketten(repo=BASE_DIR):
    """Installeert requirements-vast.txt. Geeft (gelukt, uitvoer)."""
    try:
        uit = subprocess.run(
            maak_pip_commando(repo), cwd=repo, capture_output=True, text=True, timeout=PIP_TIMEOUT_SECONDEN, check=False
        )
    except (OSError, subprocess.SubprocessError) as fout:
        return False, f"pip kon niet draaien: {fout}"
    return uit.returncode == 0, (uit.stdout + uit.stderr).strip()[-1500:]


def draai_rooktest(repo, database):
    """Start rooktest.py met de nieuwe code als los proces (de draaiende web-app heeft nog de oude code in het geheugen).
    Geeft {"afgerond", "paginas", "doorverwezen", "fouten", "duur"}; "afgerond" is False als de test zelf niet kon
    draaien of te lang duurde: dat zegt niets over de nieuwe code en is dus geen reden om terug te draaien."""
    script = Path(repo) / "rooktest.py"
    if not script.exists():
        return {"afgerond": False, "paginas": 0, "doorverwezen": 0, "fouten": ["rooktest.py ontbreekt"]}
    # In de web-app is sys.executable de webserver en niet python zelf: zoek python op versienummer (zie maak_pip_commando).
    python = shutil.which(f"python{sys.version_info.major}.{sys.version_info.minor}") or sys.executable
    try:
        uit = subprocess.run(
            [python, str(script), str(database)],
            cwd=repo, capture_output=True, text=True, timeout=ROOKTEST_TIMEOUT_SECONDEN, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"afgerond": False, "paginas": 0, "doorverwezen": 0, "fouten": [f"duurde langer dan {ROOKTEST_TIMEOUT_SECONDEN} s"]}
    except (OSError, subprocess.SubprocessError) as fout:
        return {"afgerond": False, "paginas": 0, "doorverwezen": 0, "fouten": [f"kon niet starten: {fout}"]}
    regels = [r for r in uit.stdout.splitlines() if r.strip().startswith("{")]
    try:
        return json.loads(regels[-1])
    except (IndexError, ValueError):
        # Geen uitkomst: het proces is onderweg gecrasht (bijvoorbeeld bij het importeren van de nieuwe code).
        return {"afgerond": True, "paginas": 0, "doorverwezen": 0,
                "fouten": ["de rooktest crashte: " + (uit.stderr or uit.stdout).strip()[-600:]]}


def werk_code_bij(repo=BASE_DIR, rooktest_database=None):
    """Haalt de nieuwste code op met `git pull --ff-only` (dus nooit een merge of overschrijven) en
    installeert zo nodig de vastgezette pakketten. Mislukt dat laatste, dan wordt de code teruggezet.

    Met 'rooktest_database' opent de server daarna alle pagina's met de nieuwe code op een kopie van die database
    (rooktest.py). Geeft een pagina een serverfout, dan gaat de code (en zo nodig de pakketten) terug naar de vorige
    versie en wordt er niet herstart.

    Geeft {"ok", "oud", "nieuw", "gewijzigd", "pakketten", "teruggedraaid", "uitvoer", "rooktest"} terug; "pakketten"
    is None (niet nodig), "geinstalleerd" of "mislukt"; "rooktest" is None als die niet is gedraaid."""
    resultaat = {
        "ok": False,
        "oud": huidige_commit(repo),
        "nieuw": None,
        "gewijzigd": False,
        "pakketten": None,
        "teruggedraaid": False,
        "uitvoer": "",
        "rooktest": None,
    }
    try:
        pull = _git(repo, "pull", "--ff-only")
    except (OSError, subprocess.SubprocessError) as fout:
        resultaat["uitvoer"] = f"git pull kon niet draaien: {fout}"
        return resultaat
    resultaat["uitvoer"] = (pull.stdout + pull.stderr).strip()[-1500:]
    if pull.returncode != 0:
        return resultaat
    resultaat["nieuw"] = huidige_commit(repo)
    resultaat["gewijzigd"] = resultaat["oud"] != resultaat["nieuw"]

    if resultaat["gewijzigd"] and resultaat["oud"]:
        verschil = _git(repo, "diff", "--name-only", resultaat["oud"], resultaat["nieuw"]).stdout.split()
        if any(bestand in verschil for bestand in PAKKETBESTANDEN):
            gelukt, uitvoer = installeer_pakketten(repo)
            resultaat["pakketten"] = "geinstalleerd" if gelukt else "mislukt"
            if not gelukt:
                # Nieuwe code op oude pakketten kan stukgaan: terug naar wat werkte.
                terug = _git(repo, "reset", "--hard", resultaat["oud"])
                resultaat["teruggedraaid"] = terug.returncode == 0
                resultaat["gewijzigd"] = False
                resultaat["nieuw"] = huidige_commit(repo)
                resultaat["uitvoer"] = "Pakketten installeren mislukt:\n" + uitvoer
                return resultaat
            resultaat["uitvoer"] = (resultaat["uitvoer"] + "\n" + uitvoer).strip()[-1500:]
    if resultaat["gewijzigd"] and resultaat["oud"] and rooktest_database:
        rooktest = draai_rooktest(repo, rooktest_database)
        resultaat["rooktest"] = rooktest
        if rooktest.get("afgerond") and rooktest.get("fouten"):
            terug = _git(repo, "reset", "--hard", resultaat["oud"])
            resultaat["teruggedraaid"] = terug.returncode == 0
            if resultaat["pakketten"] == "geinstalleerd":
                installeer_pakketten(repo)  # de pakketten van de vorige versie weer terug
            resultaat["gewijzigd"] = False
            resultaat["nieuw"] = huidige_commit(repo)
            resultaat["uitvoer"] = "De rooktest vond fouten met de nieuwe code:\n" + "\n".join(rooktest["fouten"])
            return resultaat
    resultaat["ok"] = True
    return resultaat


def herstart_web_app(wsgi_bestand=None):
    """Laat de web-app herstarten door het WSGI-bestand "aan te raken". Geeft False als
    dat bestand er niet is (bijv. lokaal)."""
    pad = Path(wsgi_bestand or os.environ.get("WSGI_BESTAND") or STANDAARD_WSGI_BESTAND)
    try:
        os.utime(pad, None)
    except OSError:
        return False
    return True
