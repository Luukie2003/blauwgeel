"""Club van 20: de administratie (leden, betalingen per seizoen, projecten)
en alles wat daaruit volgt voor het kantine scherm en de publieke pagina.

Los van routes/club_van_20.py (de beheerpagina's) en routes/kiosk.py (het
kantine scherm), zodat allebei dezelfde regels gebruiken voor "wie staat er
op het scherm", "hoeveel is er opgehaald" en "wat is het volgende doel".

Een seizoen loopt van 1 juli t/m 30 juni, net als het voetbalseizoen, en
wordt opgeslagen als "2026-2027". Geen bijdrage-rij voor een lid in een
seizoen betekent simpelweg "niet gevraagd" -- een nieuw seizoen hoeft dus
nergens "gestart" te worden, het staat vanzelf klaar zodra 1 juli voorbij is.
"""

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from helpers import now_str, vandaag_amsterdam

SEIZOEN_STARTMAAND = 7

BIJDRAGE_STATUS_LABELS = {
    "niet_gevraagd": "Niet gevraagd",
    "gevraagd": "Gevraagd",
    "toegezegd": "Toegezegd",
    "betaald": "Betaald",
    "afgezegd": "Stopt",
}
BIJDRAGE_STATUSSEN = list(BIJDRAGE_STATUS_LABELS)

BETAALWIJZEN = {
    "contant": "Contant",
    "mollie": "Mollie (online)",
    "tikkie": "Tikkie / betaalverzoek",
    "bank": "Overschrijving",
    "anders": "Anders",
}

PROJECT_STATUS_LABELS = {
    "gepland": "Gepland",
    "bezig": "Mee bezig",
    "klaar": "Klaar",
}

# Een naambordje op het scherm is glanzend metaalgoud vanaf zoveel STERREN (zie
# zichtbare_leden); instelbaar via club_van_20_glans_vanaf_sterren.
STANDAARD_GLANS_VANAF_STERREN = 2

STANDAARD_SEIZOENEN_PER_STER = 3

SEIZOEN_PATROON = re.compile(r"^\s*(\d{4})\s*[-/]\s*(\d{2}|\d{4})\s*$")


# ---------- Seizoenen ----------


def seizoen_van_datum(datum=None):
    """"2026-2027" voor elke datum van 1 juli 2026 t/m 30 juni 2027. datum
    mag een date, een ISO-tekst (YYYY-MM-DD...) of None (= vandaag) zijn."""
    if datum is None:
        datum = vandaag_amsterdam()
    elif isinstance(datum, str):
        datum = date.fromisoformat(datum[:10])
    begin = datum.year if datum.month >= SEIZOEN_STARTMAAND else datum.year - 1
    return f"{begin}-{begin + 1}"


def huidig_seizoen():
    return seizoen_van_datum(None)


def verschuif_seizoen(seizoen, stappen):
    """verschuif_seizoen("2026-2027", -1) == "2025-2026"."""
    begin = int(seizoen[:4]) + stappen
    return f"{begin}-{begin + 1}"


def normaliseer_seizoen(tekst):
    """Accepteert "2023-2024", "2023/2024" en "2023-24"; geeft "2023-2024"
    terug, of None als het geen (aaneensluitend) seizoen is."""
    m = SEIZOEN_PATROON.match(tekst or "")
    if not m:
        return None
    begin = int(m.group(1))
    eind = m.group(2)
    eind = int(eind) if len(eind) == 4 else int(str(begin)[:2] + eind)
    if eind != begin + 1:
        return None
    return f"{begin}-{eind}"


def seizoen_kort(seizoen):
    """"2026-2027" -> "26/27", voor smalle tabelkoppen."""
    return f"{seizoen[2:4]}/{seizoen[7:9]}"


def alle_seizoenen(db):
    """Alle seizoenen waarin iets is vastgelegd, plus het huidige -- oudste
    eerst, zodat de overzichtstabel dezelfde volgorde heeft als de oude
    spreadsheet (2023-2024, 2024-2025, ...)."""
    seizoenen = {
        r["seizoen"]
        for r in db.execute("SELECT DISTINCT seizoen FROM club_van_20_bijdragen").fetchall()
    }
    seizoenen.add(huidig_seizoen())
    return sorted(seizoenen)


# ---------- Leden + bijdragen ----------


def leden_met_bijdragen(db, alleen_actief=False):
    """Alle leden als dicts, elk met 'bijdragen' ({seizoen: dict}) en een
    paar afgeleide velden. 2 queries i.p.v. 1 per lid (het scherm pollt dit
    elke 10s)."""
    waar = "WHERE status != 'inactief'" if alleen_actief else ""
    leden = [
        dict(r)
        for r in db.execute(
            f"SELECT * FROM club_van_20_leden {waar} ORDER BY naam COLLATE NOCASE"
        ).fetchall()
    ]
    bijdragen_per_lid = {}
    for b in db.execute("SELECT * FROM club_van_20_bijdragen").fetchall():
        bijdragen_per_lid.setdefault(b["lid_id"], {})[b["seizoen"]] = dict(b)
    for lid in leden:
        bijdragen = bijdragen_per_lid.get(lid["id"], {})
        lid["bijdragen"] = bijdragen
        betaald = sorted(s for s, b in bijdragen.items() if b["status"] == "betaald")
        lid["betaalde_seizoenen"] = betaald
        lid["aantal_seizoenen"] = len(betaald) + (lid.get("eerdere_seizoenen") or 0)
        lid["eerste_seizoen"] = betaald[0] if betaald else None
        lid["totaal_betaald"] = sum(
            b["bedrag"] or 0 for b in bijdragen.values() if b["status"] == "betaald"
        )
        lid["volledige_naam"] = " ".join(
            deel for deel in (lid.get("voornaam"), lid.get("achternaam")) if deel
        )
    return leden


def bijdrage_status(lid, seizoen):
    b = lid["bijdragen"].get(seizoen)
    return b["status"] if b else "niet_gevraagd"


def is_nieuw_lid(lid, seizoen):
    """Eerste betaalde seizoen is dit seizoen (en geen eerdere seizoenen van
    vóór de administratie ingevuld)."""
    return lid["eerste_seizoen"] == seizoen and not (lid.get("eerdere_seizoenen") or 0)


def sla_bijdrage_op(db, lid_id, seizoen, status, bedrag=None, betaald_door=None,
                    betaalwijze=None, notitie=None, standaard_bedrag=20, gebruiker=None,
                    betaald_op=None):
    """Upsert van 1 bijdrage. Bij 'betaald' zonder bedrag geldt het
    standaardbedrag, en zonder datum vandaag. 'niet_gevraagd' zonder verdere
    gegevens verwijdert de rij gewoon (= geen rij, zie de moduledocstring)."""
    if status not in BIJDRAGE_STATUS_LABELS:
        raise ValueError(f"Onbekende status: {status}")
    if status == "betaald":
        if not bedrag:
            bedrag = standaard_bedrag
        betaald_op = betaald_op or vandaag_amsterdam().isoformat()
    else:
        bedrag = bedrag or 0
        betaald_op = None
    if status == "niet_gevraagd" and not (betaald_door or notitie):
        db.execute(
            "DELETE FROM club_van_20_bijdragen WHERE lid_id = ? AND seizoen = ?", (lid_id, seizoen)
        )
        return
    db.execute(
        """INSERT INTO club_van_20_bijdragen
               (lid_id, seizoen, status, bedrag, betaald_door, betaalwijze, betaald_op,
                notitie, bijgewerkt_door, bijgewerkt_op)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(lid_id, seizoen) DO UPDATE SET
               status = excluded.status,
               bedrag = excluded.bedrag,
               betaald_door = excluded.betaald_door,
               betaalwijze = excluded.betaalwijze,
               betaald_op = COALESCE(club_van_20_bijdragen.betaald_op, excluded.betaald_op),
               notitie = excluded.notitie,
               bijgewerkt_door = excluded.bijgewerkt_door,
               bijgewerkt_op = excluded.bijgewerkt_op""",
        (
            lid_id,
            seizoen,
            status,
            bedrag,
            (betaald_door or "").strip() or None,
            betaalwijze if betaalwijze in BETAALWIJZEN else None,
            betaald_op,
            (notitie or "").strip() or None,
            gebruiker,
            now_str(),
        ),
    )
    if status != "betaald":
        # COALESCE hierboven bewaart de oorspronkelijke betaaldatum bij het
        # opnieuw opslaan van een betaalde bijdrage -- maar een bijdrage die
        # níet (meer) betaald is, hoort ook geen betaaldatum te hebben.
        db.execute(
            "UPDATE club_van_20_bijdragen SET betaald_op = NULL WHERE lid_id = ? AND seizoen = ?",
            (lid_id, seizoen),
        )


def seizoen_totalen(db):
    """{seizoen: {bedrag, betaald, gevraagd, toegezegd, afgezegd}} over alle
    (ook inactieve) leden -- geld dat binnen is, blijft binnen."""
    totalen = {}
    for r in db.execute(
        """SELECT seizoen, status, COUNT(*) AS n, COALESCE(SUM(bedrag), 0) AS som
           FROM club_van_20_bijdragen GROUP BY seizoen, status"""
    ).fetchall():
        t = totalen.setdefault(
            r["seizoen"], {"bedrag": 0, "betaald": 0, "gevraagd": 0, "toegezegd": 0, "afgezegd": 0}
        )
        if r["status"] == "betaald":
            t["bedrag"] += r["som"]
        if r["status"] in t:
            t[r["status"]] += r["n"]
    return totalen


# ---------- Wie staat er op het scherm ----------


def is_zichtbaar(lid, seizoen, zichtbaar_seizoenen):
    """(zichtbaar, onbetaald) voor 1 lid in het gegeven seizoen. Een lid dat
    dit seizoen betaald heeft, staat er altijd op; wie stopt (afgezegd) of
    gearchiveerd is (status 'inactief') nooit. Daartussen bepaalt zichtbaar_seizoenen hoe lang een
    oudere betaling nog meetelt (0 = elk actief lid)."""
    if lid["status"] == "inactief":
        return False, False
    status = bijdrage_status(lid, seizoen)
    if status == "betaald":
        return True, False
    if status == "afgezegd":
        return False, False
    if zichtbaar_seizoenen <= 0:
        return True, True
    eerdere = {verschuif_seizoen(seizoen, -i) for i in range(1, zichtbaar_seizoenen)}
    if eerdere & set(lid["betaalde_seizoenen"]):
        return True, True
    return False, False


def sterren_voor(aantal_seizoenen, per_ster=STANDAARD_SEIZOENEN_PER_STER):
    """Aantal sterren bij een bordje: 1 per 'per_ster' betaalde seizoenen
    (standaard 3: bij 3 seizoenen lid de eerste ster, bij 6 de tweede, ...).
    Onder de drempel geen ster. per_ster=1 geeft het oude gedrag (1 ster per
    seizoen)."""
    per = max(1, int(per_ster or STANDAARD_SEIZOENEN_PER_STER))
    return max(0, int(aantal_seizoenen or 0)) // per


def _ruimste_bereik(a, b):
    """Het ruimste van twee 'aantal seizoenen terug'-bereiken (0 = elk lid)."""
    return 0 if a <= 0 or b <= 0 else max(a, b)


def onbetaald_actie(instellingen, vandaag=None):
    """De tijdelijke herinnering ("de komende 2 weken staat iedereen die nog
    niet betaald heeft lichtrood op het scherm"): {'tot': date, 'seizoenen': n}
    zolang die loopt (t/m de ingestelde dag), anders None."""
    try:
        tot = date.fromisoformat((instellingen["club_van_20_onbetaald_tot"] or "").strip())
    except ValueError:
        return None
    if (vandaag or vandaag_amsterdam()) > tot:
        return None
    return {"tot": tot, "seizoenen": max(0, instellingen["club_van_20_onbetaald_seizoenen"])}


def scherm_bereik(instellingen, vandaag=None):
    """(zichtbaar_seizoenen, markeer_onbetaald) zoals het scherm ze nu gebruikt:
    de gewone instellingen, of tijdens de tijdelijke herinnering een ruimer
    bereik met alle onbetaalden lichtrood."""
    bereik = instellingen["club_van_20_zichtbaar_seizoenen"]
    markeer = bool(instellingen["club_van_20_markeer_onbetaald"])
    actie = onbetaald_actie(instellingen, vandaag)
    if actie:
        return _ruimste_bereik(bereik, actie["seizoenen"]), True
    return bereik, markeer


def zichtbare_leden(db, instellingen, seizoen=None, leden=None, zichtbaar_seizoenen=None):
    """De leden die (volgens 'Wie staat er op het scherm?', zie scherm_bereik)
    zichtbaar zijn. zichtbaar_seizoenen overschrijft dat bereik, voor wie een
    ruimer bereik nodig heeft (bijvoorbeeld de verleng-lijst, zie
    aanmeldingen.py)."""
    seizoen = seizoen or huidig_seizoen()
    bereik, markeer = scherm_bereik(instellingen)
    if zichtbaar_seizoenen is None:
        zichtbaar_seizoenen = bereik
    leden = leden if leden is not None else leden_met_bijdragen(db, alleen_actief=True)
    per_ster = instellingen["club_van_20_seizoenen_per_ster"]
    glans_vanaf = max(1, instellingen["club_van_20_glans_vanaf_sterren"] or STANDAARD_GLANS_VANAF_STERREN)
    resultaat = []
    for lid in leden:
        zichtbaar, onbetaald = is_zichtbaar(lid, seizoen, zichtbaar_seizoenen)
        if not zichtbaar:
            continue
        n = lid["aantal_seizoenen"]
        sterren = sterren_voor(n, per_ster)
        resultaat.append(
            {
                "id": lid["id"],
                "betaald": not onbetaald,
                "naam": lid["naam"],
                "team": (lid.get("team") or "").strip(),
                "sterren": sterren,
                "seizoenen": n,
                "niveau": "glans" if sterren >= glans_vanaf else "",
                "nieuw": is_nieuw_lid(lid, seizoen),
                "niet_betaald": onbetaald and markeer,
                "extra_groot": bool(lid.get("extra_groot")),
                "lang": len(lid["naam"]) > 16,
            }
        )
    return resultaat


def team_stand(zichtbaar, leden=()):
    """Aantal naambordjes op het scherm per team, meeste eerst -- voor de
    'welk team steunt het meest'-dia. Elk team dat bij een (niet
    gearchiveerd) lid in de administratie staat doet mee, ook als daar nog
    niemand van betaald heeft (dan met 0): zo verschijnt een nieuw team
    meteen op de dia, en werkt die 0 juist als aansporing."""
    tellers = {
        (lid.get("team") or "").strip(): 0
        for lid in leden
        if lid["status"] != "inactief" and (lid.get("team") or "").strip()
    }
    for lid in zichtbaar:
        if lid["team"]:
            tellers[lid["team"]] = tellers.get(lid["team"], 0) + 1
    if not tellers:
        return []
    hoogste = max(tellers.values()) or 1
    return [
        {"team": team, "aantal": n, "procent": round(n / hoogste * 100)}
        for team, n in sorted(tellers.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    ]


def nieuwe_leden(leden, seizoen, dagen=30):
    """Leden die dit seizoen voor het eerst betaald hebben, in de afgelopen
    'dagen' dagen -- voor de welkomstdia."""
    grens = (vandaag_amsterdam() - timedelta(days=dagen)).isoformat()
    namen = []
    for lid in leden:
        if lid["status"] == "inactief" or not is_nieuw_lid(lid, seizoen):
            continue
        b = lid["bijdragen"].get(seizoen)
        datum = (b.get("betaald_op") or (b.get("bijgewerkt_op") or "")[:10]) if b else ""
        if datum and datum >= grens:
            namen.append(lid["naam"])
    return namen


# ---------- Geld en projecten ----------


def project_kosten(project):
    return project["kosten"] if project["kosten"] is not None else (project["raming"] or 0)


def financien(db, bedrag_per_bordje=20, seizoen=None):
    """Opgehaald (totaal en dit seizoen), besteed, beschikbaar en het
    eerstvolgende doel. Besteed = kosten van projecten die klaar zijn of
    waar al aan gewerkt wordt (werkelijke kosten, of anders de raming);
    het eerstvolgende geplande project is het 'doel' waar het beschikbare
    geld naartoe spaart."""
    seizoen = seizoen or huidig_seizoen()
    totalen = seizoen_totalen(db)
    opgehaald = sum(t["bedrag"] for t in totalen.values())
    dit = totalen.get(seizoen, {"bedrag": 0, "betaald": 0})
    projecten = [
        dict(p)
        for p in db.execute(
            "SELECT * FROM club_van_20_projecten ORDER BY volgorde, id"
        ).fetchall()
    ]
    besteed = sum(project_kosten(p) for p in projecten if p["status"] in ("klaar", "bezig"))
    beschikbaar = opgehaald - besteed
    # Het beschikbare geld wordt in volgorde over de geplande projecten
    # "verdeeld": wat al helemaal bij elkaar is gespaard, telt als gespaard,
    # en het doel is het eerste project waar nog geld voor nodig is (of het
    # laatste, als alles al gespaard is).
    doel = None
    gepland = [p for p in projecten if p["status"] == "gepland"]
    rest = max(0, beschikbaar)
    for p in gepland:
        p["gespaard"] = min(rest, p["raming"] or 0) >= (p["raming"] or 0)
        if p["gespaard"]:
            rest -= p["raming"] or 0
    if gepland:
        p = next((p for p in gepland if not p["gespaard"]), gepland[-1])
        raming = p["raming"] or 0
        gespaard = raming if p["gespaard"] else max(0, min(rest, raming))
        nog_nodig = max(0, raming - gespaard)
        doel = {
            "naam": p["naam"],
            "raming": raming,
            "gespaard": gespaard,
            "procent": round(gespaard / raming * 100) if raming else 100,
            "nog_nodig": nog_nodig,
            "nog_bordjes": -(-int(nog_nodig) // int(bedrag_per_bordje)) if bedrag_per_bordje else 0,
        }
    return {
        "opgehaald": opgehaald,
        "opgehaald_seizoen": dit["bedrag"],
        "betaald_seizoen": dit["betaald"],
        "besteed": besteed,
        "beschikbaar": beschikbaar,
        "doel": doel,
        "projecten": projecten,
        "gerealiseerd": [
            p for p in projecten if p["status"] in ("klaar", "bezig") and p["toon_op_scherm"]
        ],
        "gepland": [p for p in projecten if p["status"] == "gepland" and p["toon_op_scherm"]],
    }


def euro(bedrag, decimalen=False):
    """€ 1.840 (of € 1.840,00) -- Nederlandse notatie."""
    tekst = f"{bedrag:,.2f}" if decimalen else f"{round(bedrag):,}"
    return "€ " + tekst.replace(",", "X").replace(".", ",").replace("X", ".")


# ---------- Dashboard ----------


def bereken_club_van_20_status(db):
    """Statusblokje op het dashboard: hoeveel leden die dit seizoen
    'verwacht' worden (actief, niet gestopt, en betaald in een van de 2
    vorige seizoenen of al gevraagd/toegezegd) nog niet betaald hebben. Groen
    zodra iedereen binnen is; oranje zolang er nog iemand openstaat."""
    seizoen = huidig_seizoen()
    vorige = {verschuif_seizoen(seizoen, -1), verschuif_seizoen(seizoen, -2)}
    open_leden = []
    niet_gevraagd = 0
    betaald = 0
    for lid in leden_met_bijdragen(db, alleen_actief=True):
        status = bijdrage_status(lid, seizoen)
        if status == "betaald":
            betaald += 1
            continue
        if status == "afgezegd":
            continue
        if status in ("gevraagd", "toegezegd") or vorige & set(lid["betaalde_seizoenen"]):
            open_leden.append({"naam": lid["naam"], "status": status})
            if status == "niet_gevraagd":
                niet_gevraagd += 1
    return {
        "seizoen": seizoen,
        "leden": open_leden,
        "aantal": len(open_leden),
        "niet_gevraagd": niet_gevraagd,
        "betaald": betaald,
        "ok": not open_leden,
    }


# ---------- Aankondiging op de publieke pagina ----------

AMSTERDAM = ZoneInfo("Europe/Amsterdam")
AFTEL_FORMAAT = "%Y-%m-%dT%H:%M"
DAGNAMEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MAANDNAMEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
              "september", "oktober", "november", "december"]


def aftelmoment(instellingen):
    """Het ingestelde aftelmoment (Amsterdamse tijd), of None als dat leeg of
    onleesbaar is. Ook het moment waarop aanmelden via de site opengaat."""
    try:
        return datetime.strptime(
            instellingen["club_van_20_aankondiging_aftellen_tot"] or "", AFTEL_FORMAAT
        ).replace(tzinfo=AMSTERDAM)
    except ValueError:
        return None


def aankondiging(instellingen, nu=None):
    """De aankondiging bovenaan de publieke pagina, of None als er niets te
    tonen is. Vóór het aftelmoment: de tekst + een aftelklok (doel_ms voor de
    JS, plus de resterende tijd voor wie geen JS heeft); daarna de "na
    afloop"-tekst, of niets als die leeg is. Zonder aftelmoment gewoon
    alleen de tekst."""
    tekst = (instellingen["club_van_20_aankondiging_tekst"] or "").strip()
    na_tekst = (instellingen["club_van_20_aankondiging_na_tekst"] or "").strip()
    moment = aftelmoment(instellingen)
    nu = nu or datetime.now(AMSTERDAM)
    if moment is None:
        return {"tekst": tekst, "aftellen": False} if tekst else None
    if nu >= moment:
        return {"tekst": na_tekst, "aftellen": False} if na_tekst else None
    if not tekst:
        return None
    rest = int((moment - nu).total_seconds())
    return {
        "tekst": tekst,
        "na_tekst": na_tekst,
        "aftellen": True,
        "doel_ms": int(moment.timestamp() * 1000),
        "doel_label": f"{DAGNAMEN[moment.weekday()]} {moment.day} {MAANDNAMEN[moment.month - 1]}, {moment:%H:%M}",
        "dagen": rest // 86400,
        "uren": rest % 86400 // 3600,
        "minuten": rest % 3600 // 60,
        "seconden": rest % 60,
    }


def _aankondiging_voor_dia(instellingen):
    """De aankondiging voor op de wervingsdia: alleen tekst + doelmoment,
    bewust NIET de resterende dagen/uren/seconden -- die veranderen elke
    seconde, en alles in een dia telt mee voor de versie waarop het scherm
    zichzelf herlaadt (dat zou dan elke 10s gebeuren). Het aftellen zelf
    doet de JS op het scherm."""
    if not instellingen["club_van_20_aankondiging_op_dia"]:
        return None
    a = aankondiging(instellingen)
    if not a:
        return None
    return {"tekst": a["tekst"], "doel_ms": a.get("doel_ms")}


# ---------- Betaalverzoek ----------


def verzoek_tekst(sjabloon, lid, seizoen, bedrag, betaallink):
    """Vult het instelbare verzoek-sjabloon in. Onbekende {velden} blijven
    gewoon staan i.p.v. een fout te geven."""

    class _Veilig(dict):
        def __missing__(self, sleutel):
            return "{" + sleutel + "}"

    waarden = _Veilig(
        voornaam=lid.get("voornaam") or lid["naam"],
        naambordje=lid["naam"],
        seizoen=seizoen,
        bedrag=f"{bedrag:g}",
        betaallink=betaallink or "",
    )
    return (sjabloon or "").format_map(waarden).strip()


def whatsapp_link(telefoon, tekst):
    """wa.me-link met vooraf ingevulde tekst. Nederlandse 06-nummers worden
    omgezet naar het internationale 316-formaat dat wa.me verwacht."""
    cijfers = re.sub(r"\D", "", telefoon or "")
    if not cijfers:
        return None
    if cijfers.startswith("00"):
        cijfers = cijfers[2:]
    elif cijfers.startswith("0"):
        cijfers = "31" + cijfers[1:]
    return f"https://wa.me/{cijfers}?text={quote(tekst)}"


# ---------- Kantine scherm ----------


def vakjes_breedte(lid, kolommen):
    """Hoeveel kolommen een bordje breed is: een extra groot bordje neemt er
    2 in, maar alleen als de dia minstens 2 kolommen heeft (anders zou het
    raster een extra kolom erbij maken)."""
    return 2 if lid["extra_groot"] and kolommen >= 2 else 1


def raster_rijen(breedtes, kolommen):
    """Aantal rijen dat nodig is voor bordjes met deze breedtes in een raster
    met 'kolommen' kolommen, geplaatst zoals CSS grid met 'row dense' dat
    doet (elk bordje op de eerste plek vanaf linksboven waar het past, dus
    een gat naast een breed bordje wordt door een later bordje opgevuld)."""
    rijen = []
    for breedte in breedtes:
        breedte = max(1, min(breedte, kolommen))
        rij = 0
        while True:
            if rij == len(rijen):
                rijen.append([False] * kolommen)
            plek = next(
                (c for c in range(kolommen - breedte + 1) if not any(rijen[rij][c : c + breedte])),
                None,
            )
            if plek is not None:
                for c in range(plek, plek + breedte):
                    rijen[rij][c] = True
                break
            rij += 1
    return len(rijen)


def verdeel_over_dias(zichtbaar, per_slide, kolommen):
    """Verdeelt de namen over dia's van hooguit 'per_slide' vakjes; een extra
    groot bordje telt voor 2 vakjes."""
    groepen, huidig, bezet = [], [], 0
    for lid in zichtbaar:
        breedte = vakjes_breedte(lid, kolommen)
        if huidig and bezet + breedte > per_slide:
            groepen.append(huidig)
            huidig, bezet = [], 0
        huidig.append(lid)
        bezet += breedte
    if huidig:
        groepen.append(huidig)
    return groepen


def bouw_slides(db, instellingen, qr_svg=None):
    """Alle Club van 20-dia's voor het kantine scherm, in vaste volgorde:
    naammuur (verdeeld over meerdere dia's bij veel namen), opbrengst/doel,
    teamstrijd, welkom nieuwe leden, werving. Een onderdeel zonder inhoud
    levert gewoon geen dia op."""
    seizoen = huidig_seizoen()
    leden = leden_met_bijdragen(db, alleen_actief=True)
    zichtbaar = zichtbare_leden(db, instellingen, seizoen, leden)
    # Op het scherm kunnen ook onbetaalde (lichtrode) bordjes staan; tellers en
    # de teamstrijd gaan alleen over wie dit seizoen echt meedoet.
    betaald = [lid for lid in zichtbaar if lid["betaald"]]
    duur = max(3, instellingen["club_van_20_duur_seconden"])
    kolommen = max(1, instellingen["club_van_20_kolommen"])
    per_slide = max(1, instellingen["club_van_20_namen_per_slide"])
    # Zoveel rijen heeft een volle dia; de laatste dia houdt standaard
    # hetzelfde raster (dus even grote bordjes), tenzij "laatste dia vullen"
    # aan staat.
    vaste_rijen = -(-per_slide // kolommen)
    achtergrond = instellingen["club_van_20_achtergrond"]
    bedrag = instellingen["club_van_20_bedrag"] or 20
    slides = []

    # Een extra groot bordje neemt 2 vakjes in en telt dus dubbel mee voor het
    # aantal namen dat op een dia past.
    groepen = verdeel_over_dias(zichtbaar, per_slide, kolommen)
    for idx, groep in enumerate(groepen):
        # Net als de oude Canva-dia's wordt de laatste dia aangevuld met lege
        # vakjes ("hier kan jouw naam staan") tot de dia vol is.
        breedtes = [vakjes_breedte(lid, kolommen) for lid in groep]
        bezet = sum(breedtes)
        lege = 0
        if instellingen["club_van_20_lege_vakjes"] and idx == len(groepen) - 1:
            lege = max(0, per_slide - bezet)
        # Aantal rijen volgens de echte plaatsing, dus ook als een breed bordje
        # een gat laat dat niet helemaal gevuld wordt.
        rijen = raster_rijen(breedtes + [1] * lege, kolommen)
        if not instellingen["club_van_20_laatste_dia_vullen"]:
            rijen = max(rijen, vaste_rijen)
        slides.append(
            {
                "type": "club_van_20",
                "duur": duur,
                "seizoenen_per_ster": max(1, instellingen["club_van_20_seizoenen_per_ster"]),
                "glans_vanaf_seizoenen": max(1, instellingen["club_van_20_glans_vanaf_sterren"])
                * max(1, instellingen["club_van_20_seizoenen_per_ster"]),
                "titel": instellingen["club_van_20_titel"],
                "seizoen": seizoen,
                "namen": groep,
                "lege_vakjes": lege,
                "kolommen": kolommen,
                "rijen": max(1, rijen),
                "achtergrond": achtergrond,
                "pagina": f"{idx + 1}/{len(groepen)}" if len(groepen) > 1 else None,
            }
        )

    if instellingen["club_van_20_toon_teller"]:
        geld = financien(db, bedrag, seizoen)
        if geld["opgehaald"] > 0 or geld["gerealiseerd"] or geld["doel"]:
            slides.append(
                {
                    "type": "club_van_20_teller",
                    "duur": duur,
                    "achtergrond": achtergrond,
                    "opgehaald": round(geld["opgehaald"]),
                    "aantal_leden": len(betaald),
                    "bedrag": bedrag,
                    "doel": geld["doel"],
                    "gerealiseerd": [
                        {"naam": p["naam"], "klaar": p["status"] == "klaar"}
                        for p in geld["gerealiseerd"][:7]
                    ],
                }
            )

    if instellingen["club_van_20_toon_teams"]:
        stand = team_stand(betaald, leden)
        if len(stand) >= 2 and stand[0]["aantal"] > 0:
            slides.append(
                {
                    "type": "club_van_20_teams",
                    "duur": duur,
                    "achtergrond": achtergrond,
                    "teams": stand[:8],
                    "verschil": stand[0]["aantal"] - stand[1]["aantal"],
                }
            )

    if instellingen["club_van_20_toon_nieuw"]:
        nieuw = nieuwe_leden(leden, seizoen)
        if nieuw:
            slides.append(
                {"type": "club_van_20_nieuw", "duur": duur, "achtergrond": achtergrond, "namen": nieuw[:12]}
            )

    # Werving alleen als de Club van 20 ook echt in gebruik is (er staan
    # leden in de administratie) -- anders verschijnt er op een verse
    # installatie ineens een wervingsdia voor iets dat nog niet bestaat.
    if instellingen["club_van_20_toon_werving"] and leden:
        slides.append(
            {
                "type": "club_van_20_werving",
                "duur": duur,
                "achtergrond": achtergrond,
                "aankondiging": _aankondiging_voor_dia(instellingen),
                "tekst": instellingen["club_van_20_werving_tekst"],
                "bedrag": bedrag,
                "aantal_leden": len(betaald),
                "qr_svg": qr_svg,
            }
        )
    return slides


# ---------- Importeren uit de spreadsheet ----------

_KOLOM_NAMEN = {
    "voornaam": "voornaam",
    "achternaam": "achternaam",
    "team": "team",
    "naambordje": "naam",
    "naam": "naam",
    "telefoon": "telefoon",
    "tel": "telefoon",
    "telefoonnummer": "telefoon",
    "e-mail": "email",
    "email": "email",
    "betaald door": "betaald_door",
    "notitie": "notitie",
    "opmerking": "notitie",
}
_STATUS_KOLOM = re.compile(r"^\s*status\s+(.+)$", re.IGNORECASE)
_STATUS_UIT_TEKST = {
    "niet gevraagd": "niet_gevraagd",
    "gevraagd": "gevraagd",
    "toegezegd": "toegezegd",
    "betaald": "betaald",
    "stopt": "afgezegd",
    "afgezegd": "afgezegd",
    "gestopt": "afgezegd",
}


def _schoon(waarde):
    waarde = (waarde or "").strip()
    return "" if waarde in ("?", "-", "–") else waarde


def _bedrag(waarde):
    """'20', '€20,00', '1.840' -> float; None bij leeg/'-'/onleesbaar."""
    tekst = (waarde or "").replace("€", "").replace(" ", "").strip()
    if not tekst or tekst in ("-", "–", "?"):
        return None
    if "," in tekst and "." in tekst:
        tekst = tekst.replace(".", "").replace(",", ".")
    elif "," in tekst:
        tekst = tekst.replace(",", ".")
    try:
        return float(tekst)
    except ValueError:
        return None


def _lees_csv(tekst):
    regels = [r for r in tekst.splitlines() if r.strip()]
    if not regels:
        return []
    proef = "\n".join(regels[:10])
    try:
        dialect = csv.Sniffer().sniff(proef, delimiters=",;\t")
        scheiding = dialect.delimiter
    except csv.Error:
        scheiding = max(",;\t", key=proef.count)
    return list(csv.reader(io.StringIO(tekst.lstrip("﻿")), delimiter=scheiding))


MAX_XLSX_XML_BYTES = 30 * 1024 * 1024
_XLSX_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _xlsx_xml(z, pad):
    """Een XML-onderdeel uit het xlsx-zipbestand, met een grens aan de
    uitgepakte grootte (zipbom) en zonder DTD/entiteiten (een bewust
    kwaadaardig bestand kan met geneste entiteiten de server vastzetten)."""
    if z.getinfo(pad).file_size > MAX_XLSX_XML_BYTES:
        raise ValueError("Het Excel-bestand is te groot.")
    data = z.read(pad)
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("Dit Excel-bestand bevat niet-ondersteunde onderdelen.")
    return ET.fromstring(data)


def rijen_uit_xlsx(data):
    """Leest het ledenblad uit een .xlsx (zonder extra bibliotheek, een xlsx is
    een zipbestand met XML). Kiest het blad "Ledenlijst" als dat er is, anders
    het eerste zichtbare blad met een kolom "Naambordje" of "Voornaam"; een
    verborgen blad (bijv. een oude versie van de lijst) telt nooit mee. Geeft
    de rijen als lijst van lijsten tekst, net als de CSV-lezer. ValueError met
    een leesbare melding als het geen bruikbaar Excel-bestand is."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        wb = _xlsx_xml(z, "xl/workbook.xml")
        rels = _xlsx_xml(z, "xl/_rels/workbook.xml.rels")
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ValueError("Dit lijkt geen geldig Excel-bestand (.xlsx).")
    doel = {r.get("Id"): r.get("Target") for r in rels}
    gedeeld = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in _xlsx_xml(z, "xl/sharedStrings.xml").findall("m:si", _XLSX_NS):
            gedeeld.append("".join(t.text or "" for t in si.iter("{%s}t" % _XLSX_NS["m"])))

    def kolom(ref):
        n = 0
        for ch in re.match(r"[A-Z]+", ref).group(0):
            n = n * 26 + ord(ch) - 64
        return n - 1

    def blad_rijen(pad):
        rijen = []
        for row in _xlsx_xml(z, pad).iter("{%s}row" % _XLSX_NS["m"]):
            cellen = {}
            for c in row.findall("m:c", _XLSX_NS):
                v = c.find("m:v", _XLSX_NS)
                soort = c.get("t")
                if soort == "s" and v is not None:
                    waarde = gedeeld[int(v.text)]
                elif soort == "inlineStr":
                    waarde = "".join(x.text or "" for x in c.iter("{%s}t" % _XLSX_NS["m"]))
                elif v is not None and v.text is not None:
                    waarde = v.text
                else:
                    continue
                cellen[kolom(c.get("r"))] = waarde
            rijen.append([cellen.get(i, "") for i in range(max(cellen) + 1)] if cellen else [])
        return rijen

    kandidaten = []
    for sh in wb.find("m:sheets", _XLSX_NS):
        if sh.get("state") in ("hidden", "veryHidden"):
            continue
        doelpad = doel.get(sh.get("{%s}id" % _XLSX_NS["r"]), "")
        pad = "xl/" + doelpad.lstrip("/").replace("xl/", "", 1)
        if pad not in z.namelist():
            continue
        kandidaten.append((sh.get("name", ""), pad))
    # "Ledenlijst" eerst, daarna de rest in bladvolgorde.
    kandidaten.sort(key=lambda k: k[0].strip().lower() != "ledenlijst")
    for _, pad in kandidaten:
        rijen = blad_rijen(pad)
        for rij in rijen[:15]:
            cellen = {c.strip().lower() for c in rij}
            if "naambordje" in cellen or "voornaam" in cellen:
                return rijen
    raise ValueError("Geen blad met een kolom 'Naambordje' of 'Voornaam' gevonden in dit Excel-bestand.")


def rijen_naar_csv(rijen):
    """Zet rijen om naar puntkomma-gescheiden tekst -- zo gaat een Excel-
    bestand door dezelfde voorbeeld- en bevestigstappen als een plak- of
    CSV-import."""
    buffer = io.StringIO()
    schrijver = csv.writer(buffer, delimiter=";", lineterminator="\n")
    for rij in rijen:
        schrijver.writerow(rij)
    return buffer.getvalue()


def parse_import(tekst, standaard_bedrag=20):
    """Leest een export van de Club van 20-spreadsheet (CSV, of rechtstreeks
    geplakt uit Google Sheets/Excel = tab-gescheiden). Herkent de kolommen op
    hun kop: Voornaam, Achternaam, Team, Naambordje, een kolom per seizoen
    ("2023-2024") met het betaalde bedrag, "Status 2026-2027" en "Betaald
    door". Regels boven de kop (zoals "Totale opbrengst") worden
    overgeslagen. Geeft {'rijen', 'seizoenen', 'waarschuwingen', 'fout'}."""
    rijen_ruw = _lees_csv(tekst or "")
    kop_index = None
    for i, rij in enumerate(rijen_ruw):
        cellen = {c.strip().lower() for c in rij}
        if "naambordje" in cellen or "voornaam" in cellen:
            kop_index = i
            break
    if kop_index is None:
        return {
            "rijen": [],
            "seizoenen": [],
            "waarschuwingen": [],
            "fout": "Geen kopregel gevonden -- er moet een kolom 'Naambordje' of 'Voornaam' in staan.",
        }

    kop = [c.strip() for c in rijen_ruw[kop_index]]
    velden = {}
    seizoen_kolommen = {}
    status_kolommen = {}
    for idx, naam in enumerate(kop):
        sleutel = naam.lower()
        if sleutel in _KOLOM_NAMEN and _KOLOM_NAMEN[sleutel] not in velden:
            velden[_KOLOM_NAMEN[sleutel]] = idx
            continue
        seizoen = normaliseer_seizoen(naam)
        if seizoen:
            seizoen_kolommen[seizoen] = idx
            continue
        m = _STATUS_KOLOM.match(naam)
        if m and normaliseer_seizoen(m.group(1)):
            status_kolommen[normaliseer_seizoen(m.group(1))] = idx

    # "Betaald door" hoort bij het seizoen van de statuskolom (zo staat het
    # in de spreadsheet), of anders bij het laatste seizoen.
    alle = sorted(set(seizoen_kolommen) | set(status_kolommen))
    betaald_door_seizoen = max(status_kolommen) if status_kolommen else (alle[-1] if alle else None)

    def cel(rij, idx):
        return rij[idx] if idx is not None and idx < len(rij) else ""

    rijen = []
    waarschuwingen = []
    gezien = {}
    for regelnr, rij in enumerate(rijen_ruw[kop_index + 1 :], start=kop_index + 2):
        if not any(c.strip() for c in rij):
            continue
        voornaam = _schoon(cel(rij, velden.get("voornaam")))
        achternaam = _schoon(cel(rij, velden.get("achternaam")))
        naam = _schoon(cel(rij, velden.get("naam")))
        if not naam:
            naam = " ".join(d for d in (voornaam, achternaam) if d)
            if naam:
                waarschuwingen.append(f"Regel {regelnr}: geen naambordje, '{naam}' gebruikt.")
        if not naam:
            waarschuwingen.append(f"Regel {regelnr}: geen naam of naambordje, overgeslagen.")
            continue
        sleutel = naam.lower()
        if sleutel in gezien:
            gezien[sleutel] += 1
            nieuwe_naam = f"{naam} ({gezien[sleutel]})"
            waarschuwingen.append(
                f"Regel {regelnr}: naambordje '{naam}' komt vaker voor, geïmporteerd als '{nieuwe_naam}'."
            )
            naam = nieuwe_naam
        else:
            gezien[sleutel] = 1

        bijdragen = {}
        for seizoen in alle:
            ruw = cel(rij, seizoen_kolommen.get(seizoen))
            bedrag = _bedrag(ruw)
            status_tekst = _schoon(cel(rij, status_kolommen.get(seizoen))).lower()
            status = _STATUS_UIT_TEKST.get(status_tekst)
            if bedrag and bedrag > 0:
                bijdragen[seizoen] = {"status": "betaald", "bedrag": bedrag}
            elif status in ("gevraagd", "toegezegd", "afgezegd"):
                bijdragen[seizoen] = {"status": status, "bedrag": 0}
            elif status == "betaald" and not ruw.strip():
                # Alleen "Betaald" zonder bedragkolom: standaardbedrag. Staat
                # er expliciet 0 in de bedragkolom, dan wint dat bedrag.
                bijdragen[seizoen] = {"status": "betaald", "bedrag": standaard_bedrag}
        betaald_door = _schoon(cel(rij, velden.get("betaald_door")))
        if betaald_door and betaald_door_seizoen:
            bijdragen.setdefault(betaald_door_seizoen, {"status": "niet_gevraagd", "bedrag": 0})
            bijdragen[betaald_door_seizoen]["betaald_door"] = betaald_door

        rijen.append(
            {
                "naam": naam,
                "voornaam": voornaam,
                "achternaam": achternaam,
                "team": _schoon(cel(rij, velden.get("team"))).rstrip("?").strip(),
                "telefoon": _schoon(cel(rij, velden.get("telefoon"))),
                "email": _schoon(cel(rij, velden.get("email"))),
                "notitie": _schoon(cel(rij, velden.get("notitie"))),
                "bijdragen": bijdragen,
            }
        )
    return {"rijen": rijen, "seizoenen": alle, "waarschuwingen": waarschuwingen, "fout": None}


def _bijdrage_ongewijzigd(bestaande, b):
    """True als de import voor dit seizoen niets verandert aan wat er al staat
    (zelfde status en bedrag) -- dan blijft de bestaande bijdrage met al haar
    details (betaalwijze, notitie) ongemoeid."""
    return (
        bestaande is not None
        and bestaande["status"] == b["status"]
        and (b["status"] != "betaald" or abs((bestaande["bedrag"] or 0) - (b.get("bedrag") or 0)) < 0.005)
        and not b.get("betaald_door")
    )


def import_samenvatting(db, rijen):
    """Wat de import zou doen, voor het voorbeeld: nieuwe leden, en per
    bijdrage of die nieuw, gewijzigd of ongewijzigd is -- zodat je vooraf ziet
    of een grote import (bijv. met jaren historie erbij) alleen aanvult of
    ook bestaande betalingen aanpast."""
    bestaand = {
        r["naam"].lower(): r["id"] for r in db.execute("SELECT id, naam FROM club_van_20_leden").fetchall()
    }
    huidige = {
        (r["lid_id"], r["seizoen"]): r for r in db.execute("SELECT * FROM club_van_20_bijdragen").fetchall()
    }
    samenvatting = {"nieuwe_leden": 0, "bestaande_leden": 0, "nieuw": 0, "gewijzigd": 0, "ongewijzigd": 0, "wijzigingen": []}
    for rij in rijen:
        lid_id = bestaand.get(rij["naam"].lower())
        samenvatting["bestaande_leden" if lid_id else "nieuwe_leden"] += 1
        for seizoen, b in rij["bijdragen"].items():
            if b["status"] == "niet_gevraagd" and not b.get("betaald_door"):
                continue
            huidig = huidige.get((lid_id, seizoen)) if lid_id else None
            if huidig is None:
                samenvatting["nieuw"] += 1
            elif _bijdrage_ongewijzigd(huidig, b):
                samenvatting["ongewijzigd"] += 1
            else:
                samenvatting["gewijzigd"] += 1
                samenvatting["wijzigingen"].append(
                    f"{rij['naam']} {seizoen}: {BIJDRAGE_STATUS_LABELS[huidig['status']].lower()}"
                    f"{' €%g' % huidig['bedrag'] if huidig['status'] == 'betaald' else ''} → "
                    f"{BIJDRAGE_STATUS_LABELS[b['status']].lower()}"
                    f"{' €%g' % b['bedrag'] if b['status'] == 'betaald' else ''}"
                )
    return samenvatting


def voer_import_uit(db, rijen, gebruiker=None, standaard_bedrag=20):
    """Zet geparste rijen (zie parse_import) in de database. Een lid met
    hetzelfde naambordje (hoofdletterongevoelig) wordt bijgewerkt i.p.v.
    dubbel aangemaakt. Bij zo'n bestaand lid worden alleen LEGE velden
    (team, telefoon, ...) aangevuld: wat in de app is aangepast (bijv. een
    team dat inmiddels O23 heet) blijft staan. De seizoenen uit de import
    overschrijven wat er voor die seizoenen stond, behalve een bijdrage die
    al dezelfde status en hetzelfde bedrag heeft (die blijft met al haar
    details -- betaalwijze, notitie -- ongemoeid); andere seizoenen blijven
    ongemoeid. Geeft (aantal nieuw, aantal bijgewerkt)."""
    bestaand = {
        r["naam"].lower(): r["id"]
        for r in db.execute("SELECT id, naam FROM club_van_20_leden").fetchall()
    }
    nieuw = bijgewerkt = 0
    vandaag = vandaag_amsterdam().isoformat()
    for rij in rijen:
        lid_id = bestaand.get(rij["naam"].lower())
        if lid_id is None:
            cursor = db.execute(
                """INSERT INTO club_van_20_leden
                       (naam, voornaam, achternaam, team, telefoon, email, notitie,
                        status, startdatum, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'actief', ?, ?)""",
                (
                    rij["naam"],
                    rij["voornaam"] or None,
                    rij["achternaam"] or None,
                    rij["team"] or None,
                    rij["telefoon"] or None,
                    rij["email"] or None,
                    rij["notitie"] or None,
                    vandaag,
                    now_str(),
                ),
            )
            lid_id = cursor.lastrowid
            bestaand[rij["naam"].lower()] = lid_id
            nieuw += 1
        else:
            # Alleen lege velden aanvullen: de app is leidend, de import
            # vult gaten.
            huidig = db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
            for veld in ("voornaam", "achternaam", "team", "telefoon", "email", "notitie"):
                if rij[veld] and not (huidig[veld] or "").strip():
                    db.execute(
                        f"UPDATE club_van_20_leden SET {veld} = ? WHERE id = ?", (rij[veld], lid_id)
                    )
            bijgewerkt += 1
        for seizoen, b in rij["bijdragen"].items():
            bestaande = db.execute(
                "SELECT status, bedrag FROM club_van_20_bijdragen WHERE lid_id = ? AND seizoen = ?",
                (lid_id, seizoen),
            ).fetchone()
            if _bijdrage_ongewijzigd(bestaande, b):
                continue
            sla_bijdrage_op(
                db,
                lid_id,
                seizoen,
                b["status"],
                bedrag=b.get("bedrag"),
                betaald_door=b.get("betaald_door"),
                standaard_bedrag=standaard_bedrag,
                gebruiker=gebruiker,
                # Historische seizoenen: geen "vandaag" als betaaldatum,
                # anders lijkt iedereen ineens een nieuw lid.
                betaald_op=f"{seizoen[:4]}-{SEIZOEN_STARTMAAND:02d}-01",
            )
    return nieuw, bijgewerkt
