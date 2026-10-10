"""Gegevens voor de dia's: standen, Man of the Match, clublogo's en het samenstellen van de slides."""

import json
import re

from flask import url_for

import qr
from club_van_20 import bouw_slides as club_van_20_slides
from helpers import (
    video_info,
    KIOSK_SPONSOR_SJABLOON_AANGEPAST,
    MOTM_RESULTATEN,
    bereken_komende_thuiswedstrijden,
    club_van_team_naam,
    motm_score_weergave,
)
from sponsoren import bouw_sponsor_dias
from routes.kiosk.gedeeld import _scherm_instellingen


def _poule_slug(titel):
    """Maakt van een titel (bijv. "Zaterdag 4") een url-vriendelijke, interne
    poule-sleutel ("zaterdag-4") -- alleen de titel is zichtbaar voor de
    gebruiker, de sleutel blijft achter de schermen (zie kiosk_stand_teams.poule)."""
    sleutel = re.sub(r"[^a-z0-9]+", "-", titel.strip().lower()).strip("-")
    return sleutel or "poule"


def _sponsor_slide(s, eigen_sjablonen, producten_bij_id=None):
    """Bouwt de slide-dict voor 1 sponsor-/mededelingrij. Bij
    sjabloon == 'aangepast' wordt het gekoppelde zelfgebouwde sjabloon
    (kiosk_sjablonen_custom) verrijkt met de eigen titel/tekst/foto van
    deze sponsor; is dat sjabloon inmiddels verwijderd, dan levert deze
    sponsor gewoon geen slide op (zelfde 'leeg blok'-filosofie als de
    rest van _bouw_slides). Een 'prijs'-element krijgt hier zijn inhoud
    vers uit producten_bij_id -- dat gebeurt bij elke opbouw opnieuw
    (elke paginalaad/versiepoll), dus een latere prijswijziging van het
    gekoppelde product komt vanzelf door, net als de rest van het scherm."""
    duur = s["weergave_duur_seconden"]
    if s["sjabloon"] == "video_volledig":
        if not s["video"]:
            return None  # een videodia zonder video heeft niets te tonen
        if s["video_hele_duur"] and s["video_duur"]:
            duur = max(2, round(s["video_duur"], 1))  # de dia blijft staan zolang de video duurt
    slide = {
        "type": "sponsor",
        "duur": duur,
        "video": s["video"],
        "video_bytes": (video_info(s["video"], s["video_duur"]) or {}).get("bytes", 0),
        "video_geluid": bool(s["video_geluid"]),
        "sjabloon": s["sjabloon"],
        "titel": s["titel"],
        "tekst": s["tekst"],
        "afbeelding": s["afbeelding"],
        "overgang": s["overgang"],
        "tekst_grootte": s["tekst_grootte"],
        "achtergrond_afbeelding": s["achtergrond_afbeelding"],
    }
    if s["sjabloon"] != KIOSK_SPONSOR_SJABLOON_AANGEPAST:
        return slide
    sjabloon = eigen_sjablonen.get(s["custom_sjabloon_id"])
    if sjabloon is None:
        return None
    producten_bij_id = producten_bij_id or {}
    elementen = []
    for element in json.loads(sjabloon["elementen"]):
        element = dict(element)
        if element.get("type") == "foto":
            element["inhoud"] = s["afbeelding"]
        elif element.get("type") == "titel":
            element["inhoud"] = s["titel"]
        elif element.get("type") == "tekst":
            element["inhoud"] = s["tekst"]
        elif element.get("type") == "prijs":
            product = producten_bij_id.get(element.get("product_id"))
            element["inhoud"] = (
                ("€ " + f"{product['verkoopprijs']:.2f}".replace(".", ",")) if product else None
            )
        elementen.append(element)
    slide.update(
        {
            "custom_achtergrond_kleur": sjabloon["achtergrond_kleur"],
            "custom_achtergrond_afbeelding": sjabloon["achtergrond_afbeelding"],
            "custom_overlay_donker": bool(sjabloon["overlay_donker"]),
            "elementen": elementen,
        }
    )
    return slide


def _bouw_slides(db):
    """Bouwt de geordende lijst slides voor het kantine scherm, op basis
    van kiosk_scherm_instellingen: elke slide is een dict met minstens
    'type' en 'duur' (seconden weergavetijd), plus type-specifieke
    velden. Een blok (sponsoren/club van 20/wedstrijden) dat uitstaat of
    toevallig leeg is, levert gewoon geen slides op -- dan draait de
    diashow vanzelf zonder lege pagina."""
    instellingen = _scherm_instellingen(db)
    blokken = []

    if instellingen["toon_sponsoren"]:
        sponsoren = db.execute(
            "SELECT * FROM kiosk_sponsoren WHERE actief = 1 ORDER BY volgorde, id"
        ).fetchall()
        # Eigen sjablonen alvast allemaal ophalen (klein aantal, geen
        # N+1 nodig) zodat _sponsor_slide er per sponsor zo 1 uit kan
        # pakken zonder telkens een losse query.
        eigen_sjablonen = {
            r["id"]: r for r in db.execute("SELECT * FROM kiosk_sjablonen_custom").fetchall()
        }
        producten_bij_id = {
            r["id"]: r
            for r in db.execute("SELECT id, verkoopprijs FROM producten").fetchall()
        }
        slides = [
            slide
            for s in sponsoren
            if (slide := _sponsor_slide(s, eigen_sjablonen, producten_bij_id)) is not None
        ]
        if slides:
            blokken.append((instellingen["sponsoren_volgorde"], slides))

    if instellingen["toon_club_van_20"]:
        # Naammuur + opbrengst/doel + teamstrijd + welkom + werving, zie
        # club_van_20.bouw_slides voor wie er op het scherm staat. De
        # QR-code op de wervingsdia wijst naar de publieke Club van
        # 20-pagina.
        slides = club_van_20_slides(
            db,
            instellingen,
            qr_svg=(
                qr.qr_svg(url_for("club_van_20_publiek", _external=True))
                if instellingen["club_van_20_toon_werving"] or instellingen["club_van_20_toon_onbetaald"]
                else None
            ),
        )
        if slides:
            blokken.append((instellingen["club_van_20_volgorde"], slides))

    if instellingen["toon_wedstrijden"]:
        komende = bereken_komende_thuiswedstrijden(db)
        if komende:
            blokken.append(
                (
                    instellingen["wedstrijden_volgorde"],
                    [{
                        "type": "wedstrijden",
                        "duur": instellingen["wedstrijden_duur_seconden"],
                        "dagen": komende,
                    }],
                )
            )

    # 1 keer opgehaald i.p.v. per blok apart: standen EN Man of the
    # Match tonen allebei clublogo's via hetzelfde register.
    club_logos = (
        _club_logos(db) if instellingen["toon_standen"] or instellingen["toon_motm"] else {}
    )

    if instellingen["toon_standen"]:
        stand_slides = []
        for poule in _stand_poules(db):
            teams = _stand_teams(db, poule["sleutel"])
            if not teams:
                continue
            stand_slides.append(
                {
                    "type": "stand",
                    "duur": instellingen["standen_duur_seconden"],
                    "titel": poule["titel"],
                    "teams": [
                        _stand_team_weergave(i + 1, t, club_logos) for i, t in enumerate(teams)
                    ],
                }
            )
        if stand_slides:
            blokken.append((instellingen["standen_volgorde"], stand_slides))

    if instellingen["toon_motm"]:
        # Alleen teams met een ingevulde speler en/of uitslag komen op de
        # dia (zie kiosk_motm_volgorde_opslaan) -- allebei leeg betekent
        # dat het team niet heeft gespeeld, en heeft geen enkel team iets
        # ingevuld dan slaat de hele dia over, net als de andere blokken
        # hierboven bij lege data. Tegenstander-logo komt uit hetzelfde
        # register als de standen-dia's (club_van_team_naam), dus een
        # tegenstander die daar al een logo heeft staan (vaak het geval,
        # zelfde competities) toont 'm hier automatisch mee.
        motm_teams = [
            {
                "team": t["team"],
                "speler": _motm_namen_weergave(t["speler"]),
                "uitslag": motm_score_weergave(t["uitslag"], t["resultaat"]),
                "resultaat": t["resultaat"] if t["resultaat"] in MOTM_RESULTATEN else None,
                "resultaat_label": MOTM_RESULTATEN.get(t["resultaat"]),
                "tegenstander": (t["tegenstander"] or "").strip(),
                "tegenstander_logo": (
                    club_logos.get(club_van_team_naam(t["tegenstander"]))
                    if (t["tegenstander"] or "").strip()
                    else None
                ),
            }
            for t in _motm_teams(db)
            if (t["speler"] or "").strip() or (t["uitslag"] or "").strip() or t["resultaat"] in MOTM_RESULTATEN
        ]
        if motm_teams:
            blokken.append(
                (
                    instellingen["motm_volgorde"],
                    [{
                        "type": "motm",
                        "duur": instellingen["motm_duur_seconden"],
                        "titel": instellingen["motm_titel"],
                        "teams": motm_teams,
                    }],
                )
            )

    blokken.sort(key=lambda blok: blok[0])
    alle = [slide for _, slides in blokken for slide in slides]
    # Sponsordia's komen niet als blok, maar tussen de andere dia's door:
    # de JS in kiosk_scherm.html haalt ze uit de gewone volgorde en toont
    # na elke N dia's de volgende sponsor (zie sponsors_elke_dias).
    if instellingen["sponsors_toon_dias"]:
        alle.extend(bouw_sponsor_dias(db, instellingen))
    return alle


def _stand_teams(db, poule):
    return db.execute(
        "SELECT * FROM kiosk_stand_teams WHERE poule = ? ORDER BY volgorde, id", (poule,)
    ).fetchall()


def _stand_poules(db):
    return db.execute("SELECT * FROM kiosk_stand_poules ORDER BY volgorde, id").fetchall()


def _stand_poule_sleutels(db):
    return {p["sleutel"] for p in _stand_poules(db)}


def _unieke_poule_sleutel(db, titel):
    """Voegt indien nodig -2, -3, ... toe zodat de sleutel uniek blijft,
    bijv. als er al een poule "Zaterdag 2" bestaat en je maakt 'm
    nogmaals aan (of een titel die toevallig tot dezelfde sleutel
    slugify't)."""
    basis = _poule_slug(titel)
    bestaande = _stand_poule_sleutels(db)
    sleutel = basis
    i = 2
    while sleutel in bestaande:
        sleutel = f"{basis}-{i}"
        i += 1
    return sleutel


def _motm_teams(db):
    return db.execute("SELECT * FROM kiosk_motm ORDER BY volgorde, id").fetchall()


def _motm_namen_weergave(speler):
    """speler mag meerdere, komma-gescheiden namen bevatten (bijv. een
    gedeelde Man of the Match) -- op de dia worden die netjes met "&"
    samengevoegd i.p.v. de kale komma's te tonen."""
    namen = [n.strip() for n in (speler or "").split(",") if n.strip()]
    if len(namen) <= 1:
        return namen[0] if namen else ""
    return ", ".join(namen[:-1]) + " & " + namen[-1]


def _club_logos(db):
    """Alle geregistreerde clublogo's in 1 keer, als {club: afbeelding} --
    zodat _stand_team_weergave hieronder niet per team een eigen query
    hoeft te doen (was een N+1: 1 query per team op elke paginalading
    EN elke 10s-poll van het kantine scherm)."""
    return {
        r["club"]: r["afbeelding"]
        for r in db.execute("SELECT club, afbeelding FROM kiosk_club_logos").fetchall()
    }


def _stand_team_weergave(positie, team, club_logos):
    """Bouwt 1 team-rij voor de standen-dia (zie kiosk_scherm.html) --
    Gespeeld en Punten worden hier berekend uit W/GL/V (3-1-0-systeem,
    zelfde als voetbal.nl) i.p.v. los opgeslagen, zodat ze nooit uit de
    pas kunnen gaan lopen met de ingevulde W/GL/V."""
    gewonnen, gelijk, verloren = team["gewonnen"], team["gelijk"], team["verloren"]
    return {
        "positie": positie,
        "naam": team["naam"],
        "eigen_team": bool(team["eigen_team"]),
        "logo": club_logos.get(team["club"]) if team["club"] else None,
        "gewonnen": gewonnen,
        "gelijk": gelijk,
        "verloren": verloren,
        "gespeeld": gewonnen + gelijk + verloren,
        "punten": gewonnen * 3 + gelijk,
    }
