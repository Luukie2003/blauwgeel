#!/usr/bin/env python3
"""Zet de nieuwste code live op www.kantineblauwgeel.nl, in 1 commando.

    venv/bin/python scripts/zet_live.py

Wat het doet:
  1. controleert dat alles gecommit is en je op main staat;
  2. draait de code-controle (ruff) en alle tests -- faalt er iets, dan stopt het;
  3. pusht naar GitHub;
  4. vraagt de server (POST /uitrollen, ondertekend) de nieuwste code op te halen, zo nodig de
     vastgezette pakketten te installeren, alle pagina's met de nieuwe code op een kopie van de echte
     database te openen (de rooktest; lukt iets daarvan niet, dan zet de server de vorige versie terug)
     en de web-app te herstarten;
  5. wacht tot /status laat zien dat de nieuwe versie echt draait.

Valt de verbinding met de server weg voordat er een antwoord is (dat gebeurt soms als de server na een gelukte uitrol
al herstart), dan kijkt het script via /status of de nieuwe versie draait, in plaats van te stoppen met een fout.

Eenmalig instellen (zie ook uitrollen.py):
    venv/bin/python scripts/zet_live.py --maak-geheim
Dat maakt een geheim aan op jouw computer en toont de ene regel die je daarna in een Bash-console
op PythonAnywhere plakt. Zonder dat geheim op de server is live zetten uitgeschakeld.

Opties:
  --zonder-tests   sla ruff en de tests over (alleen als je weet wat je doet)
  --zonder-push    push niet; alleen de server bijwerken met wat al op GitHub staat
  --maak-geheim    maak een nieuw geheim aan (vervangt een bestaand: daarna op de server opnieuw instellen)
"""

import argparse
import http.client
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from uitrollen import maak_handtekening  # noqa: E402

BASIS_URL = os.environ.get("KANTINE_URL", "https://www.kantineblauwgeel.nl").rstrip("/")
GEHEIM_PAD = Path.home() / ".config" / "kantine" / "uitrol_geheim"
WACHT_OP_STATUS_SECONDEN = 90


def fout(tekst):
    print(f"FOUT: {tekst}", file=sys.stderr)
    return 1


def git(*argumenten, check=True):
    return subprocess.run(["git", *argumenten], cwd=REPO, capture_output=True, text=True, check=check)


def lees_geheim():
    geheim = os.environ.get("KANTINE_UITROL_GEHEIM", "").strip()
    if geheim:
        return geheim
    try:
        return GEHEIM_PAD.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def maak_geheim():
    geheim = secrets.token_urlsafe(48)
    GEHEIM_PAD.parent.mkdir(parents=True, exist_ok=True)
    GEHEIM_PAD.write_text(geheim + "\n", encoding="utf-8")
    GEHEIM_PAD.chmod(0o600)
    print(f"Geheim opgeslagen in {GEHEIM_PAD} (alleen leesbaar voor jou).")
    print("\nZet het nu eenmalig op de server: open op PythonAnywhere een Bash-console en plak deze regel:\n")
    print(f"  echo '{geheim}' > ~/Voorraadbeheer/uitrol_geheim.txt && chmod 600 ~/Voorraadbeheer/uitrol_geheim.txt\n")
    print("Daarna werkt `venv/bin/python scripts/zet_live.py`. Deel het geheim met niemand.")
    return 0


def controleer_git_status():
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        return f"je staat op '{branch}', live zetten kan alleen vanaf main"
    gewijzigd = [r for r in git("status", "--porcelain").stdout.splitlines() if not r.startswith("??")]
    if gewijzigd:
        return "er zijn wijzigingen die nog niet gecommit zijn:\n  " + "\n  ".join(gewijzigd[:10])
    return None


def draai(naam, *commando):
    print(f"→ {naam} ...", flush=True)
    start = time.time()
    uitkomst = subprocess.run(commando, cwd=REPO)
    if uitkomst.returncode != 0:
        print(f"✗ {naam} mislukt: niet live gezet.")
        return False
    print(f"✓ {naam} ({time.time() - start:.0f} s)")
    return True


def vraag_server(geheim):
    body = json.dumps({"actie": "bijwerken"}).encode()
    tijdstip = int(time.time())
    verzoek = urllib.request.Request(
        BASIS_URL + "/uitrollen",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Uitrol-Tijd": str(tijdstip),
            "X-Uitrol-Handtekening": maak_handtekening(geheim, tijdstip, body),
        },
    )
    try:
        # Ruim: bij nieuwe pakketten installeert de server die eerst (kan een minuut duren).
        with urllib.request.urlopen(verzoek, timeout=300) as antwoord:
            return antwoord.status, json.loads(antwoord.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except ValueError:
            return e.code, {}
    except (OSError, http.client.HTTPException, ValueError) as e:
        # Geen (bruikbaar) antwoord: de verbinding viel weg of het duurde te lang. De server kan dan toch klaar zijn,
        # want na een gelukte uitrol herstart hij en dat breekt dit verzoek soms af. Wat er draait, zegt /status (main).
        return None, {"verbinding": str(getattr(e, "reason", None) or e) or type(e).__name__}


def lees_status():
    try:
        with urllib.request.urlopen(BASIS_URL + "/status", timeout=15) as antwoord:
            return json.loads(antwoord.read().decode())
    except (urllib.error.URLError, ValueError, OSError):
        return None  # de web-app is net aan het herstarten


def wacht_tot_actief(verwachte_commit):
    einde = time.time() + WACHT_OP_STATUS_SECONDEN
    while time.time() < einde:
        status = lees_status()
        if status and status.get("commit") == verwachte_commit:
            return status
        time.sleep(3)
    return None


def main():
    parser = argparse.ArgumentParser(description="Zet de nieuwste code live.")
    parser.add_argument("--zonder-tests", action="store_true")
    parser.add_argument("--zonder-push", action="store_true")
    parser.add_argument("--maak-geheim", action="store_true")
    args = parser.parse_args()

    if args.maak_geheim:
        return maak_geheim()

    geheim = lees_geheim()
    if not geheim:
        return fout("nog geen geheim ingesteld. Draai eerst: venv/bin/python scripts/zet_live.py --maak-geheim")

    probleem = controleer_git_status()
    if probleem:
        return fout(probleem)

    if not args.zonder_tests:
        if not draai("Code-controle (ruff)", sys.executable, "-m", "ruff", "check", "."):
            return 1
        if not draai("Tests", sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"):
            return 1

    if not args.zonder_push:
        if not draai("Pushen naar GitHub", "git", "push"):
            return 1

    lokaal = git("rev-parse", "--short", "HEAD").stdout.strip()
    print(f"→ Server bijwerken naar {lokaal} ...", flush=True)
    code, antwoord = vraag_server(geheim)
    if code is None:
        print(f"! Geen antwoord van de server ({antwoord['verbinding']}). Kijken via /status of {lokaal} draait ...",
              flush=True)
        status = wacht_tot_actief(lokaal)
        if not status:
            return fout(
                f"de server antwoordde niet en na {WACHT_OP_STATUS_SECONDEN} s draait {lokaal} nog niet. Misschien is "
                "hij nog bezig, of heeft de rooktest de vorige versie teruggezet. Kijk over een paar minuten op /status; "
                "draait hij dan nog niet, start dit script opnieuw met --zonder-tests: dan zegt de server wat er misging."
            )
        print(f"✓ Live: versie {status['versie']} ({status['commit']}) op {BASIS_URL}. Hoe de rooktest op de server "
              "uitkwam, is niet bekend (er kwam geen antwoord); was er een fout, dan had de server de vorige versie "
              "teruggezet.")
        return 0
    if code == 404:
        return fout("live zetten staat nog niet aan op de server (uitrol_geheim.txt ontbreekt daar). Zie --maak-geheim.")
    if code == 403:
        return fout("de server weigert de handtekening: staat hetzelfde geheim op de server? (ook de klok van je computer moet kloppen)")
    if code != 200 or not antwoord.get("ok"):
        extra = "\nDe server heeft de vorige versie teruggezet; er is niets veranderd." if antwoord.get("teruggedraaid") else ""
        return fout(f"de server kon de code niet bijwerken (HTTP {code}):\n{antwoord.get('uitvoer', '')}{extra}")

    rooktest = antwoord.get("rooktest")
    if rooktest and rooktest.get("afgerond"):
        print(f"✓ Rooktest op de server: {rooktest['paginas']} pagina's met de echte gegevens geopend, zonder fouten "
              f"({rooktest.get('duur', '?')} s).")
    elif rooktest:
        print(f"! Rooktest op de server niet afgerond ({'; '.join(rooktest.get('fouten', []))}); de nieuwe versie gaat wel live.")

    if antwoord.get("pakketten") == "geinstalleerd":
        print("✓ Pakketten op de server bijgewerkt (requirements-vast.txt).")
    if not antwoord["gewijzigd"] and antwoord["nieuw"] == lokaal:
        status = lees_status()
        if status and status.get("commit") == lokaal:
            print(f"✓ Server draait al {lokaal} (versie {status['versie']}): niets te doen.")
            return 0

    print("→ Wachten tot de nieuwe versie draait ...", flush=True)
    status = wacht_tot_actief(lokaal)
    if not status:
        return fout(f"na {WACHT_OP_STATUS_SECONDEN} s draait {lokaal} nog niet. Kijk op PythonAnywhere (Web-tab → Reload) en /status.")
    print(f"✓ Live: versie {status['versie']} ({status['commit']}) op {BASIS_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
