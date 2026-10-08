"""Nieuwe code veilig op de server zetten ("live zetten").

Hoe het werkt: het script scripts/zet_live.py (op je eigen computer) stuurt een
ondertekend verzoek naar POST /uitrollen. De server controleert de handtekening, haalt
de nieuwste code op (`git pull --ff-only`) en laat de web-app daarna herstarten.
Het endpoint doet alléén dat: de eigen repository bijwerken. Er kan geen andere code
mee worden meegestuurd, alleen wat al in de repository staat.

Staat er op de server geen `uitrol_geheim.txt`, dan is het endpoint uitgeschakeld
(404). Het geheim zet je met `python3 scripts/zet_live.py --maak-geheim`."""

import hashlib
import hmac
import os
import subprocess
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


def werk_code_bij(repo=BASE_DIR):
    """Haalt de nieuwste code op met `git pull --ff-only` (dus nooit een merge of
    overschrijven). Geeft {"ok", "oud", "nieuw", "gewijzigd", "requirements_gewijzigd",
    "uitvoer"} terug."""
    resultaat = {
        "ok": False,
        "oud": huidige_commit(repo),
        "nieuw": None,
        "gewijzigd": False,
        "requirements_gewijzigd": False,
        "uitvoer": "",
    }
    try:
        pull = _git(repo, "pull", "--ff-only")
    except (OSError, subprocess.SubprocessError) as fout:
        resultaat["uitvoer"] = f"git pull kon niet draaien: {fout}"
        return resultaat
    resultaat["uitvoer"] = (pull.stdout + pull.stderr).strip()[-1500:]
    if pull.returncode != 0:
        return resultaat
    resultaat["ok"] = True
    resultaat["nieuw"] = huidige_commit(repo)
    resultaat["gewijzigd"] = resultaat["oud"] != resultaat["nieuw"]
    if resultaat["gewijzigd"] and resultaat["oud"]:
        verschil = _git(repo, "diff", "--name-only", resultaat["oud"], resultaat["nieuw"])
        resultaat["requirements_gewijzigd"] = "requirements.txt" in verschil.stdout.split()
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
