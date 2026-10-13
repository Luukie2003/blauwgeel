"""Rooktest: opent alle pagina's van de site met de nieuwe code en een kopie van de echte database.

Bij het live zetten (uitrollen.py) start de server dit als los proces, nadat de nieuwe code is opgehaald maar voordat de
web-app herstart. Geeft een pagina een serverfout, dan zet de server de vorige versie terug: zo komt een fout die alleen
met de echte gegevens optreedt (zoals de inkoopprijs per krat in 1.44.1) niet meer live. De database zelf wordt niet
aangeraakt: alles gebeurt op een kopie in een tijdelijke map, en mail versturen staat uit.

    python3 rooktest.py /pad/naar/voorraad.db     -> één regel JSON: {"afgerond", "paginas", "doorverwezen", "fouten", "duur"}
"""

import json
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Pagina's die je niet zomaar opent: ze loggen uit, wisselen de weergave, starten een download of horen bij het uitrollen.
OVERSLAAN = {"logout", "uitloggen", "weergave_wisselen", "uitrollen_endpoint", "status_pagina", "service_worker", "favicon_ico", "static"}
OVERSLAAN_DELEN = ("pdf", "csv", "download", "export", "uitlog", "xlsx", "zip")
MAX_FOUTEN = 10


def te_openen(app):
    """(endpoint, url) van elke pagina zonder variabele delen in het adres die je met GET opent."""
    from flask import url_for

    paginas = []
    with app.test_request_context("/"):
        for regel in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
            if "GET" not in regel.methods or regel.arguments or regel.endpoint in OVERSLAAN:
                continue
            if any(deel in regel.endpoint for deel in OVERSLAAN_DELEN):
                continue
            paginas.append((regel.endpoint, url_for(regel.endpoint)))
    return paginas


def _kopieer(bron, map_):
    """Een volledige, consistente kopie van de database (ook als de site er net in schrijft)."""
    doel = Path(map_) / "rooktest.db"
    with sqlite3.connect(f"file:{bron}?mode=ro", uri=True) as van, sqlite3.connect(doel) as naar:
        van.backup(naar)
    return doel


def draai(bron_db):
    begin = time.monotonic()
    map_ = tempfile.mkdtemp(prefix="rooktest-")
    try:
        try:
            kopie = _kopieer(bron_db, map_)
        except sqlite3.Error as fout:  # geen database om mee te testen: dat zegt niets over de nieuwe code
            return {"afgerond": False, "paginas": 0, "doorverwezen": 0, "fouten": [f"database kopiëren mislukt: {fout}"]}
        try:
            sys.path.insert(0, str(BASE_DIR))
            import mail

            mail.MAIL_BESCHIKBAAR = False  # een rooktest stuurt nooit mail
            from app import create_app

            app = create_app(database_path=str(kopie))
            app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False, FOUTMELDING_MAIL=False)
        except Exception as fout:  # de nieuwe code start niet eens: dat moet terug
            return {"afgerond": True, "paginas": 0, "doorverwezen": 0, "fouten": [f"de site start niet: {type(fout).__name__}: {fout}"],
                    "duur": round(time.monotonic() - begin, 1)}
        with sqlite3.connect(kopie) as db:
            db.row_factory = sqlite3.Row
            beheerder = db.execute(
                "SELECT id, naam, rol, secties, sessie_versie FROM gebruikers WHERE rol = 'beheerder' AND actief = 1 ORDER BY id LIMIT 1"
            ).fetchone()
        if beheerder is None:
            return {"afgerond": False, "paginas": 0, "doorverwezen": 0, "fouten": ["geen actieve beheerder om mee te testen"]}
        client = app.test_client()
        with client.session_transaction() as sessie:
            sessie.update(
                gebruiker_id=beheerder["id"], gebruiker_naam=beheerder["naam"], gebruiker_rol=beheerder["rol"],
                gebruiker_secties=beheerder["secties"], sessie_versie=beheerder["sessie_versie"] or 0,
            )
        paginas, doorverwezen, fouten = 0, 0, []
        for endpoint, url in te_openen(app):
            try:
                antwoord = client.get(url)
                if antwoord.status_code >= 500:
                    fouten.append(f"{url}: HTTP {antwoord.status_code}")
                elif 300 <= antwoord.status_code < 400:
                    doorverwezen += 1
                antwoord.close()
            except Exception as fout:  # TESTING: een fout in een pagina komt hier als uitzondering binnen
                regels = traceback.format_exception(fout)
                fouten.append(f"{url}: {type(fout).__name__}: {fout} ({regels[-2].strip()[:160] if len(regels) > 1 else ''})")
            paginas += 1
            if len(fouten) >= MAX_FOUTEN:
                break
        return {
            "afgerond": True,
            "paginas": paginas,
            "doorverwezen": doorverwezen,
            "fouten": fouten,
            "duur": round(time.monotonic() - begin, 1),
        }
    finally:
        shutil.rmtree(map_, ignore_errors=True)


if __name__ == "__main__":
    try:
        uitkomst = draai(sys.argv[1])
    except Exception as fout:  # de rooktest zelf kon niet draaien: dat is iets anders dan een kapotte pagina
        uitkomst = {"afgerond": False, "paginas": 0, "doorverwezen": 0, "fouten": [f"rooktest kon niet draaien: {fout}"]}
    print(json.dumps(uitkomst))
