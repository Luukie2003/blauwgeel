"""Wie er op het kantine scherm staat, de aankondiging met aftelklok en het bouwen van de dia's."""

import re
from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from helpers import vandaag_amsterdam
from club_van_20.administratie import bijdrage_status, financien, is_nieuw_lid, leden_met_bijdragen
from club_van_20.seizoenen import huidig_seizoen, verschuif_seizoen


# Een naambordje op het scherm is glanzend metaalgoud vanaf zoveel STERREN (zie
# zichtbare_leden); instelbaar via club_van_20_glans_vanaf_sterren.
STANDAARD_GLANS_VANAF_STERREN = 2


STANDAARD_SEIZOENEN_PER_STER = 3


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


ONBETAALD_KOLOMMEN = 4
ONBETAALD_RIJEN_RUIM = 3  # tot 12 namen (3 rijen) is er plek voor de grote kop en de grote letter

# Vanaf 4 rijen past het alleen met een compactere kop/onderkant en rijen met een vaste hoogte (anders groeit
# een rij met een lange, 2-regelige naam de dia uit het scherm). Per aantal rijen: (letter, rijhoogte, schaal van
# kop en onderkant), de eerste twee in --u. Zo blijft er met 3 regels kleine tekst nog ruim 4% rand boven en onder.
_ONBETAALD_MAAT = {4: (42, 118, 0.7), 5: (37, 94, 0.66), 6: (32, 78, 0.62)}


KLEINE_TEKSTEN_MAX = 3
KLEINE_TEKST_TEKENS = 140


def kleine_teksten(tekst):
    """De regels van de kleine tekst onder de "Steun de club"-dia: elke niet-lege regel is een eigen tekst
    (max. 3, zoveel past er onder de namen). Ook gebruikt om de ingevoerde tekst schoon te maken."""
    regels = [regel.strip()[:KLEINE_TEKST_TEKENS] for regel in (tekst or "").splitlines()]
    return [regel for regel in regels if regel][:KLEINE_TEKSTEN_MAX]


def onbetaald_raster(aantal):
    """Opmaak van een "Steun de club"-dia met zoveel namen. Altijd 4 kolommen: smaller kapt de namen af."""
    rijen = -(-aantal // ONBETAALD_KOLOMMEN)
    if rijen <= ONBETAALD_RIJEN_RUIM:
        return {"kolommen": ONBETAALD_KOLOMMEN, "letter": 46, "rij": None, "schaal": 1}
    letter, rij, schaal = _ONBETAALD_MAAT[min(rijen, 6)]
    return {"kolommen": ONBETAALD_KOLOMMEN, "letter": letter, "rij": rij, "schaal": schaal}


def onbetaalde_leden(zichtbaar):
    """De leden voor de "Leden? Steun de club!"-dia: wie op het scherm hoort maar dit seizoen nog niet
    betaald heeft, en eerder wel (een lid dat nog nooit betaald heeft is geen "trouw lid dat ontbreekt").
    Dat zijn precies de bordjes die tijdens de tijdelijke herinnering lichtrood op de naammuur staan. Op
    alfabet, zodat niemand zich uitgelicht voelt."""
    namen = [lid for lid in zichtbaar if not lid["betaald"] and lid["seizoenen"] >= 1]
    return sorted(namen, key=lambda lid: lid["naam"].lower())


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
    teamstrijd, welkom nieuwe leden, "Leden? Steun de club!" (wie nog niet
    betaald heeft), werving. Een onderdeel zonder inhoud
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

    if instellingen["club_van_20_toon_onbetaald"]:
        ontbrekend = onbetaalde_leden(zichtbaar)
        per_dia = max(ONBETAALD_KOLOMMEN, min(24, instellingen["club_van_20_onbetaald_per_slide"] or 24))
        # Vol of bijna vol: de dia's krijgen even veel namen (13 namen = 7 + 6, niet 12 + 1).
        aantal_dias = -(-len(ontbrekend) // per_dia)
        if aantal_dias:
            per_dia_gelijk = -(-len(ontbrekend) // aantal_dias)
            for idx in range(aantal_dias):
                groep = ontbrekend[idx * per_dia_gelijk : (idx + 1) * per_dia_gelijk]
                raster = onbetaald_raster(len(groep))
                slides.append(
                    {
                        "type": "club_van_20_onbetaald",
                        "duur": duur,
                        "achtergrond": None,  # eigen, donkerrode opmaak
                        "namen": [{"naam": lid["naam"], "lang": lid["lang"]} for lid in groep],
                        "totaal": len(ontbrekend),
                        "seizoen": seizoen,
                        "raster": raster,
                        "kleintjes": kleine_teksten(instellingen["club_van_20_onbetaald_tekst"]),
                        "bedrag": bedrag,
                        "qr_svg": qr_svg,
                        "pagina": f"{idx + 1}/{aantal_dias}" if aantal_dias > 1 else None,
                    }
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
