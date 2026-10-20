"""Gekoppelde tv's: elke tv in de kantine een eigen naam, en op de site per tv kiezen wat hij toont.

Zo werkt het:
1. De tv (de tv-app, of een browser op de tv) opent /kiosk/koppelen. Die pagina geeft de tv een eigen, willekeurig
   token (bewaard in de tv zelf) en gaat naar /kiosk/t/<token>.
2. Is die tv nog niet gekoppeld, dan staat daar een koppelcode van 6 cijfers (een half uur geldig).
3. Op Kantine-tv vul je die code in, met een naam ("Bar", "Kantine links"). Binnen een paar seconden toont de tv
   wat je kiest: de prijzenlijst, de dia's of het wisselscherm (dat volgt de bestaande wisselknop).
4. Daarna stel je per tv in wat hij toont en hoe groot (zoom), en laad je hem op afstand opnieuw. De tv geeft bij het
   verversen door dat hij aan staat, wat hij toont en hoe groot zijn beeld is; staat een tv uit terwijl er bardienst
   is, dan staat dat bij "Wat moet er nu?" op het overzicht (zie helpers/status.py).

De oude vaste adressen (/kiosk/prijzen, /kiosk/scherm, /kiosk/tv) blijven gewoon werken voor een tv die (nog) niet is
gekoppeld."""

import hashlib
import re
import secrets
from datetime import date, datetime, timedelta

SCHERMEN = {
    "prijzen": "Prijzenlijst",
    "dias": "Dia's",
    "wissel": "Wisselscherm (volgt de wisselknop)",
}
ZOOMS = (70, 80, 90, 100, 110, 120, 130, 150)
TOKEN_PATROON = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
CODE_GELDIG_MINUTEN = 30
# Iedereen kan /kiosk/t/<token> openen; meer open koppelcodes dan dit tegelijk geeft geen nieuwe meer.
MAX_OPEN_CODES = 40
# De tv vraagt elke 10 seconden of er iets veranderd is; dat hij aan staat, schrijft de site hooguit eens per minuut
# weg (elke schrijfactie maakt de bewaarde uitkomsten van alle schermen ongeldig, zie routes/kiosk/gedeeld.py).
HARTSLAG_ELKE_SECONDEN = 60
# Zo lang na het laatste teken van leven telt een tv nog als "aan".
AAN_BINNEN_SECONDEN = 180
FORMAAT = "%Y-%m-%d %H:%M:%S"


def _tekst(moment):
    return moment.strftime(FORMAAT)


def geldig_token(token):
    return bool(TOKEN_PATROON.match(token or ""))


def tv_voor_token(db, token):
    return db.execute("SELECT * FROM kiosk_tvs WHERE token = ?", (token,)).fetchone()


def alle_tvs(db):
    return db.execute("SELECT * FROM kiosk_tvs ORDER BY naam COLLATE NOCASE, id").fetchall()


def koppelcode_voor(db, token, nu=None):
    """De geldige koppelcode van deze (nog niet gekoppelde) tv, of een nieuwe. None als er al te veel tv's tegelijk
    aan het koppelen zijn."""
    nu = nu or datetime.now()
    grens = _tekst(nu - timedelta(minutes=CODE_GELDIG_MINUTEN))
    rij = db.execute("SELECT code, aangemaakt_op FROM kiosk_tv_koppelcodes WHERE token = ?", (token,)).fetchone()
    if rij is not None and rij["aangemaakt_op"] >= grens:
        return rij["code"]
    db.execute("DELETE FROM kiosk_tv_koppelcodes WHERE aangemaakt_op < ? OR token = ?", (grens, token))
    if db.execute("SELECT COUNT(*) FROM kiosk_tv_koppelcodes").fetchone()[0] >= MAX_OPEN_CODES:
        db.commit()
        return None
    while True:
        code = f"{secrets.randbelow(10 ** 6):06d}"
        if db.execute("SELECT 1 FROM kiosk_tv_koppelcodes WHERE code = ?", (code,)).fetchone() is None:
            break
    db.execute("INSERT INTO kiosk_tv_koppelcodes (code, token, aangemaakt_op) VALUES (?, ?, ?)", (code, token, _tekst(nu)))
    db.commit()
    return code


def koppel(db, code, naam, scherm, door, nu=None):
    """Koppelt de tv met deze code. Geeft (tv_id, None) of (None, foutmelding)."""
    nu = nu or datetime.now()
    code = re.sub(r"\D", "", code or "")
    naam = " ".join((naam or "").split())[:40]
    if len(code) != 6:
        return None, "Vul de 6 cijfers in die op de tv staan."
    if not naam:
        return None, "Geef de tv een naam, bijvoorbeeld 'Bar' of 'Kantine links'."
    if scherm not in SCHERMEN:
        scherm = "dias"  # standaard de dia's; met de afstandsbediening wissel je naar de prijzenlijst
    rij = db.execute(
        "SELECT token FROM kiosk_tv_koppelcodes WHERE code = ? AND aangemaakt_op >= ?",
        (code, _tekst(nu - timedelta(minutes=CODE_GELDIG_MINUTEN))),
    ).fetchone()
    if rij is None:
        return None, "Deze code staat niet (meer) op een tv. Kijk op de tv welke code er nu staat."
    db.execute("DELETE FROM kiosk_tv_koppelcodes WHERE code = ?", (code,))
    bestaand = tv_voor_token(db, rij["token"])
    if bestaand is not None:
        db.commit()
        return bestaand["id"], None
    tv_id = db.execute(
        "INSERT INTO kiosk_tvs (token, naam, scherm, gekoppeld_op, gekoppeld_door) VALUES (?, ?, ?, ?, ?)",
        (rij["token"], naam, scherm, _tekst(nu), door),
    ).lastrowid
    db.commit()
    return tv_id, None


def bewaar_instellingen(db, tv_id, naam, scherm, zoom):
    """Naam, wat hij toont en hoe groot. Geeft een foutmelding of None."""
    naam = " ".join((naam or "").split())[:40]
    if not naam:
        return "Geef de tv een naam."
    if scherm not in SCHERMEN:
        return "Kies wat de tv moet tonen."
    try:
        zoom = int(zoom)
    except (TypeError, ValueError):
        zoom = 100
    zoom = min(ZOOMS, key=lambda z: abs(z - zoom))
    db.execute("UPDATE kiosk_tvs SET naam = ?, scherm = ?, zoom = ? WHERE id = ?", (naam, scherm, zoom, tv_id))
    db.commit()
    return None


def herlaad(db, tv_id):
    db.execute("UPDATE kiosk_tvs SET herlaad_teller = herlaad_teller + 1 WHERE id = ?", (tv_id,))
    db.commit()


def effectief_scherm(tv, scherm_instellingen):
    """'prijzen' of 'dias': het wisselscherm volgt de wisselknop van Kantine-tv."""
    if tv["scherm"] == "wissel":
        return "dias" if scherm_instellingen["actief_tv_scherm"] == "dias" else "prijzen"
    return "dias" if tv["scherm"] == "dias" else "prijzen"


def tv_versie(tv, effectief):
    """Het deel van de versie van het scherm dat bij deze tv hoort: verandert er iets aan wat hij toont, aan de zoom of
    druk je op 'Opnieuw laden', dan herlaadt de tv."""
    ruw = f"{effectief}|{tv['zoom']}|{tv['herlaad_teller']}"
    return hashlib.md5(ruw.encode()).hexdigest()[:8]


def _schoon(waarde, lengte):
    waarde = re.sub(r"[^\w .:/x()-]", "", str(waarde or ""))[:lengte].strip()
    return waarde or None


def hartslag(db, tv, toont=None, beeld=None, app_versie=None, geladen=False, nu=None):
    """De tv staat aan (en toont dit, met dit beeld, in deze app). Hooguit eens per minuut weggeschreven, tenzij er iets
    veranderd is of de tv net (opnieuw) is geladen."""
    nu = nu or datetime.now()
    toont = toont if toont in ("prijzen", "dias") else None
    beeld = _schoon(beeld, 20)
    app_versie = _schoon(app_versie, 20)
    recent = tv["laatst_gezien"] is not None and tv["laatst_gezien"] >= _tekst(nu - timedelta(seconds=HARTSLAG_ELKE_SECONDEN))
    hetzelfde = all(
        nieuw is None or nieuw == tv[kolom] for kolom, nieuw in (("toont", toont), ("beeld", beeld), ("app_versie", app_versie))
    )
    if recent and hetzelfde and not geladen:
        return
    db.execute(
        f"""UPDATE kiosk_tvs SET laatst_gezien = ?, toont = COALESCE(?, toont), beeld = COALESCE(?, beeld),
                   app_versie = COALESCE(?, app_versie){", geladen_op = ?" if geladen else ""}
            WHERE id = ?""",
        (_tekst(nu), toont, beeld, app_versie, *((_tekst(nu),) if geladen else ()), tv["id"]),
    )
    db.commit()


def staat_aan(tv, nu=None):
    nu = nu or datetime.now()
    return tv["laatst_gezien"] is not None and tv["laatst_gezien"] >= _tekst(nu - timedelta(seconds=AAN_BINNEN_SECONDEN))


def _wanneer(tekst, nu):
    moment = datetime.strptime(tekst, FORMAAT)
    if moment.date() == nu.date():
        return f"om {moment:%H:%M}"
    if moment.date() == nu.date() - timedelta(days=1):
        return f"gisteren om {moment:%H:%M}"
    return f"op {moment.day}-{moment.month} om {moment:%H:%M}"


def status(tv, nu=None):
    """Hoe het met de tv gaat, voor de site: {aan, tekst, toont, beeld, app}."""
    nu = nu or datetime.now()
    aan = staat_aan(tv, nu)
    if aan:
        tekst = "Aan"
    elif tv["laatst_gezien"] is None:
        tekst = "Nog niet gezien"
    else:
        tekst = f"Uit, laatst gezien {_wanneer(tv['laatst_gezien'], nu)}"
    app = tv["app_versie"]
    return {
        "aan": aan,
        "tekst": tekst,
        "toont": {"prijzen": "de prijzenlijst", "dias": "de dia's"}.get(tv["toont"]),
        "beeld": tv["beeld"],
        "app": None if not app else ("in een browser" if app == "browser" else f"tv-app {app}"),
        "geladen": _wanneer(tv["geladen_op"], nu) if tv["geladen_op"] else None,
    }


def bardienst_bezig(db, nu=None):
    """De bardienst die nu bezig is (ook een dienst over middernacht, zoals 22:00-01:00), of None. Zelfde regel als
    het prijzenscherm (kiosk_prijzen_scherm.html)."""
    nu = nu or datetime.now()
    vandaag = nu.date()
    gisteren = vandaag - timedelta(days=1)
    tijd = nu.strftime("%H:%M")
    for b in db.execute(
        "SELECT * FROM kiosk_bardiensten WHERE datum IN (?, ?) ORDER BY datum, start_tijd",
        (gisteren.isoformat(), vandaag.isoformat()),
    ).fetchall():
        over_nacht = b["eind_tijd"] <= b["start_tijd"]
        if b["datum"] == vandaag.isoformat():
            if (tijd >= b["start_tijd"]) if over_nacht else (b["start_tijd"] <= tijd < b["eind_tijd"]):
                return b
        elif over_nacht and date.fromisoformat(b["datum"]) == gisteren and tijd < b["eind_tijd"]:
            return b
    return None


def uit_tijdens_bardienst(db, nu=None):
    """De gekoppelde tv's die uit staan terwijl er nu bardienst is (leeg als er geen bardienst is)."""
    nu = nu or datetime.now()
    if bardienst_bezig(db, nu) is None:
        return []
    return [tv for tv in alle_tvs(db) if not staat_aan(tv, nu)]
