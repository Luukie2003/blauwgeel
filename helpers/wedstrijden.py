"""Wedstrijden en Man of the Match."""

import re
from datetime import date, datetime, timedelta

import weer
from agenda import CLUBNAAM


def bepaal_tegenstander(omschrijving):
    """Haalt de tegenstander uit een wedstrijd-omschrijving zoals
    "Blauw Geel'15 2-Potetos 4" (zie agenda.py, dezelfde tabel/kolom als
    wedstrijden.omschrijving). Splitst net als agenda.py op het eerste kale
    streepje en bepaalt met CLUBNAAM welke kant de tegenstander is -- een
    teamnaam die zelf een streepje bevat (bijv. "O23-1") kan dit net als
    daar in de war sturen, maar dat is dezelfde al geaccepteerde beperking
    als bij de thuis/uit-bepaling in agenda.py, niet een nieuwe.
    Geeft None terug als geen van beide kanten CLUBNAAM bevat (bijv. een
    kale/onverwachte tekst)."""
    delen = omschrijving.split("-", 1)
    if len(delen) < 2:
        return None
    kant_a, kant_b = delen[0].strip(), delen[1].strip()
    if CLUBNAAM in kant_a.lower():
        return kant_b or None
    if CLUBNAAM in kant_b.lower():
        return kant_a or None
    return None


def club_van_team_naam(naam):
    """Haalt de clubnaam uit een teamnaam zoals "Oranje Nassau 5" of
    "Blauw Geel'15 O23-1" (zie kiosk_stand_teams/kiosk_stand_poules in
    routes/kiosk.py) door alleen het LAATSTE team-volgnummer te strippen --
    bijv. "5"/"6" of een jeugdcode als "O23-1" of "18+1". Zo blijft een jaartal dat
    toevallig in de clubnaam zelf zit (bijv. "Velocitas 1897", "Be Quick
    1887") intact, want dat wordt nooit als laatste woord nogmaals herhaald.
    Meerdere teams van dezelfde club (bijv. "Oranje Nassau 5" en "Oranje
    Nassau 6") leveren zo dezelfde clubnaam op, en delen dus 1 logo (zie
    kiosk_club_logos)."""
    return re.sub(r"\s+(?:O\d+-\d+|\d+\+\d+|\d+)$", "", naam).strip()


MOTM_RESULTATEN = {"gewonnen": "Gewonnen", "gelijk": "Gelijkspel", "verloren": "Verloren"}


_MOTM_SCORE = re.compile(r"^\s*(\d+)\s*[-\u2013:]\s*(\d+)\s*$")


def motm_score_weergave(uitslag, resultaat):
    """De uitslag zoals 'ie op de Man of the Match-dia komt: het eigen team links.
    Met een gekozen resultaat (gewonnen/gelijk/verloren) maakt dit uit welk
    getal van het eigen team is: bij "gewonnen" het hoogste, bij "verloren" het
    laagste. Zo maakt het niet uit of je "1-2" of "2-1" intikt, of de uitslag
    overneemt van voetbal.nl (thuisploeg eerst, ook als je zelf uit speelde).
    Zonder resultaat, een tegenstrijdige combinatie (bijv. "2-2" bij gewonnen)
    of een uitslag die geen twee getallen is, blijft de tekst zoals getypt."""
    tekst = (uitslag or "").strip()
    gevonden = _MOTM_SCORE.match(tekst)
    if not gevonden or resultaat not in MOTM_RESULTATEN:
        return tekst
    a, b = int(gevonden.group(1)), int(gevonden.group(2))
    if resultaat == "gelijk":
        return f"{a}-{b}" if a == b else tekst
    if a == b:
        return tekst
    hoog, laag = max(a, b), min(a, b)
    return f"{hoog}-{laag}" if resultaat == "gewonnen" else f"{laag}-{hoog}"


def motm_resultaat_klopt(uitslag, resultaat):
    """False als de uitslag een score is die niet bij het gekozen resultaat past
    (gelijkspel met ongelijke cijfers, of winst/verlies met gelijke cijfers)."""
    gevonden = _MOTM_SCORE.match((uitslag or "").strip())
    if not gevonden or resultaat not in MOTM_RESULTATEN:
        return True
    gelijk = int(gevonden.group(1)) == int(gevonden.group(2))
    return gelijk if resultaat == "gelijk" else not gelijk


def bereken_wedstrijd_geschiedenis(db, limiet=25, inclusief_afgelast=False):
    """De laatst gespeelde wedstrijden (alle teams, thuis en uit) --
    gedeeld tussen de Wedstrijden-pagina en Club instellingen. Afgelaste
    wedstrijden zijn niet gespeeld en doen niet mee, behalve met
    inclusief_afgelast=True (de Wedstrijden-pagina, waar je een afgelasting
    ook achteraf kunt zetten of terugdraaien)."""
    return [
        {
            "id": w["id"],
            "datum_weergave": datetime.strptime(w["datum"], "%Y-%m-%d").strftime("%d-%m-%Y"),
            "team": w["team"],
            "omschrijving": w["omschrijving"],
            "thuis": w["thuis"],
            "afgelast": w["afgelast"],
        }
        for w in db.execute(
            f"""SELECT * FROM wedstrijden WHERE datum < ? {"" if inclusief_afgelast else "AND afgelast = 0"}
                ORDER BY datum DESC, team LIMIT ?""",
            (date.today().isoformat(), limiet),
        ).fetchall()
    ]


_WEEKDAG_KORT = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]


_MAAND_KORT = [
    "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
]


def bereken_komende_thuiswedstrijden(db, dagen=14, inclusief_afgelast=False):
    """Groepeert de komende thuiswedstrijden per datum -- gevuld door
    agenda.py (de gekoppelde teamagenda's) -- samen met de weersverwachting
    van diezelfde dag (gevuld door weer.py), als indicatie hoe druk het kan
    worden: een thuiswedstrijd bij mooi weer trekt meer mensen dan bij
    regen. Rekent nog niets automatisch door in de omzetverwachting -- zie
    bereken_voorspelde_tekorten() voor waar dat wel gebeurt. Een afgelaste
    wedstrijd doet niet mee, behalve met inclusief_afgelast=True (de pagina's
    waar je een wedstrijd als afgelast markeert of weer terugzet)."""
    vandaag = date.today().isoformat()
    grens = (date.today() + timedelta(days=dagen)).isoformat()
    rijen = db.execute(
        f"""SELECT id, datum, team, omschrijving, afgelast FROM wedstrijden
           WHERE thuis = 1 AND datum >= ? AND datum <= ?
           {"" if inclusief_afgelast else "AND afgelast = 0"}
           ORDER BY datum, team""",
        (vandaag, grens),
    ).fetchall()
    per_datum = {}
    for r in rijen:
        per_datum.setdefault(r["datum"], []).append(r)

    weer_per_datum = {
        w["datum"]: w
        for w in db.execute(
            "SELECT * FROM weer_voorspelling WHERE datum >= ? AND datum <= ?",
            (vandaag, grens),
        ).fetchall()
    }

    resultaat = []
    for datum, lijst in sorted(per_datum.items()):
        w = weer_per_datum.get(datum)
        dt = datetime.strptime(datum, "%Y-%m-%d")
        resultaat.append(
            {
                "datum": datum,
                "datum_weergave": dt.strftime("%d-%m-%Y"),
                # Losse velden voor de datumbadge op het kantine scherm (zie
                # kiosk_scherm.html) -- puur presentatie, datum/datum_weergave
                # hierboven blijven de brontijd voor de rest van de app.
                "dag_kort": _WEEKDAG_KORT[dt.weekday()],
                "dag_nummer": dt.day,
                "maand_kort": _MAAND_KORT[dt.month - 1],
                "wedstrijden": lijst,
                "weer": (
                    {
                        "label": weer.weer_label(w["weercode"]),
                        "icoon": weer.weer_icoon(w["weercode"]),
                        "max_temp": w["max_temp"],
                        "neerslag_kans": w["neerslag_kans"],
                    }
                    if w
                    else None
                ),
            }
        )
    return resultaat
