"""De feestdia op de kantine-tv (2.12.0): het sjabloon 'feest', in de clubkleuren, met vlaggetjes, stralen en (met het
effect feest) confetti en vuurwerk. Zie templates/_kiosk_sponsor_inhoud.html en static/kiosk_effecten.css.

Wat er op staat, komt uit het gewone dia-formulier:
- het label op een geel lint bovenaan ("Bij winst");
- de titel, zo groot als hij past, over hooguit drie regels; de laatste regel in het geel;
- de tekst: de laatste regel is de knaller, op een gele sticker ("op 2 pitchers!"), waarin een getal extra groot staat;
  de regels ervoor staan onder de titel;
- eventueel een tekening (twee pitchers, een beker of een bal): die staat dan linksonder en de sticker rechts.

De lettergroottes rekent de server uit met de breedte van de letters (Barlow Condensed Bold, de koppenletter van de
site): zo past elke tekst die je intikt, zonder dat de tv iets hoeft op te meten. De maten zijn in vw, op een scherm van
16 bij 9 (zoals de tv's)."""

import math
import re
from itertools import combinations

# Het geel en het blauw van de club (zie ook kiosk_scherm_stijl.css).
GEEL = "#fcd42f"

TEKENINGEN = {
    "pitchers": "Twee pitchers bier die proosten",
    "beker": "Kampioensbeker",
    "bal": "Stuiterende voetbal",
}

# De breedte van de hoofdletters en tekens in Barlow Condensed Bold, in em (gemeten uit de letter zelf, zie
# pdf/letters/BarlowCondensed-Bold.ttf). Wat er niet in staat, telt als een gemiddelde letter.
_BREEDTE = {
    "A": 0.482, "B": 0.47, "C": 0.464, "D": 0.476, "E": 0.438, "F": 0.421, "G": 0.467, "H": 0.48, "I": 0.23,
    "J": 0.452, "K": 0.491, "L": 0.426, "M": 0.548, "N": 0.514, "O": 0.473, "P": 0.465, "Q": 0.461, "R": 0.471,
    "S": 0.444, "T": 0.468, "U": 0.479, "V": 0.488, "W": 0.689, "X": 0.475, "Y": 0.474, "Z": 0.412,
    "0": 0.453, "1": 0.284, "2": 0.438, "3": 0.436, "4": 0.484, "5": 0.439, "6": 0.44, "7": 0.407, "8": 0.44,
    "9": 0.435, " ": 0.2, "!": 0.279, "?": 0.437, ".": 0.223, ",": 0.211, ":": 0.275, ";": 0.232, "-": 0.331,
    "–": 0.38, "'": 0.17, '"': 0.346, "€": 0.5, "&": 0.603, "+": 0.438, "%": 0.766, "/": 0.415, "(": 0.311,
    ")": 0.311,
}
_GEMIDDELD = 0.47
_LETTERAFSTAND = 0.01  # em, zoals .fs-titel en .fs-knal in kiosk_effecten.css

# Een getal in de knaller (ook een prijs als "€ 2,50" of "5,-") staat zo veel keer groter, en een regel met zo'n getal
# is zo veel em hoog; de aanloop (de woorden voor het getal, zoals "op") staat er klein boven.
GETAL = re.compile(r"(?:€\s*)?\d+(?:[.,]\d+)*(?:,-)?")
GETAL_FACTOR = 1.9
_REGEL_TITEL = 0.92
_REGEL_KNAL = 1.0
_REGEL_GETAL = 0.84 * GETAL_FACTOR
AANLOOP_FACTOR = 0.5
_REGEL_AANLOOP = AANLOOP_FACTOR * 1.1

# De ruimte (breedte, hoogte in vw) voor de titel en voor de tekst op de sticker, met een tekening (poster) en zonder
# (midden), en de grootste letter. Een regel onder de titel kost zo veel hoogte; zonder label komt de titel hoger.
_RUIMTE = {
    "poster": {"titel": (90, 18.6), "knal": (34, 14.6)},
    "midden": {"titel": (88, 19.5), "knal": (62, 12.6)},
}
_ZONDER_KNALLER = 13.0
_ZONDER_LABEL = 4.5
_PER_REGEL = 5.4
_MAX_TITEL = (14.0, 12.0)  # op één regel, op meer regels
_MAX_KNAL = 7.6
_MAX_REGEL = 4.6
_MAX_LABEL = 4.4


def _maat(tekst):
    """De breedte van tekst in hoofdletters, in em."""
    tekst = str(tekst).upper()
    return sum(_BREEDTE.get(c, _GEMIDDELD) for c in tekst) + _LETTERAFSTAND * max(0, len(tekst) - 1)


def delen_van(tekst):
    """De knaller in stukken, met de getallen apart: 'op 2 pitchers!' -> [('op ', False), ('2', True), (' pitchers!',
    False)]."""
    delen, plek = [], 0
    for gevonden in GETAL.finditer(tekst):
        if gevonden.start() > plek:
            delen.append((tekst[plek:gevonden.start()], False))
        delen.append((gevonden.group(), True))
        plek = gevonden.end()
    if plek < len(tekst):
        delen.append((tekst[plek:], False))
    return delen


def _knal_maat(tekst):
    return sum(_maat(deel) * (GETAL_FACTOR if getal else 1) for deel, getal in delen_van(tekst))


def _verdeel(woorden, aantal, maat):
    """De woorden over aantal regels, zo dat de breedste regel zo smal mogelijk is. Geeft (breedste, regels)."""
    beste = None
    for knips in combinations(range(1, len(woorden)), aantal - 1):
        grenzen = (0, *knips, len(woorden))
        regels = [" ".join(woorden[a:b]) for a, b in zip(grenzen, grenzen[1:], strict=False)]
        breedste = max(maat(r) for r in regels)
        if beste is None or breedste < beste[0]:
            beste = (breedste, regels)
    return beste


def _passend(tekst, breedte, hoogte, max_regels, maat, regelhoogte, grens, extra_hoogte=0.0):
    """tekst over 1 tot en met max_regels regels, zo groot als hij past in breedte bij hoogte (vw). Meer regels alleen
    als dat duidelijk groter wordt. extra_hoogte: wat er per em nog bij komt (de aanloop). Geeft (regels, grootte)."""
    woorden = tekst.split()[:40]
    beste = ([], 0.0)
    for aantal in range(1, min(max_regels, len(woorden)) + 1):
        breedste, regels = _verdeel(woorden, aantal, maat)
        hoog = sum(regelhoogte(r) for r in regels) + extra_hoogte
        grootte = min(grens(aantal), breedte / breedste if breedste else grens(aantal), hoogte / hoog)
        if grootte > beste[1] * 1.04:
            beste = (regels, grootte)
    return beste[0], round(beste[1], 2)


def _aanloop(regel):
    """De knaller in aanloop en knal: 'op 2 pitchers!' -> ('op', '2 pitchers!'). Alleen een korte aanloop voor een getal
    (hooguit drie woorden); anders is de hele regel de knal."""
    gevonden = GETAL.search(regel)
    if not gevonden or gevonden.start() == 0:
        return None, regel
    voor = regel[:gevonden.start()].strip()
    if not voor or len(voor.split()) > 3 or len(voor) > 18:
        return None, regel
    return voor, regel[gevonden.start():].strip()


def delen(titel, regels, met_tekening, label=None):
    """Wat er op een feestdia staat, met de lettergroottes die passen (zie de uitleg bovenaan).

    regels: de regels van de tekst (de laatste is de knaller); label: de tekst op het lint (of None). Geeft een dict voor
    _kiosk_sponsor_inhoud.html."""
    vorm = "poster" if met_tekening else "midden"
    ruimte = _RUIMTE[vorm]
    regels = [r for r in regels if r]
    knaller = regels[-1] if regels else None
    onder = [(r, round(min(_MAX_REGEL, ruimte["titel"][0] / max(_maat(r), 0.1)), 2)) for r in regels[:-1][:3]]

    hoogte = ruimte["titel"][1] - _PER_REGEL * len(onder)
    if not knaller:
        hoogte += _ZONDER_KNALLER
    if not label:
        hoogte += _ZONDER_LABEL
    titel_regels, titel_vw = _passend(
        str(titel or ""), ruimte["titel"][0], max(hoogte, 6.0), 3, _maat, lambda r: _REGEL_TITEL,
        lambda aantal: _MAX_TITEL[0] if aantal == 1 else _MAX_TITEL[1],
    )

    aanloop, knal, knal_vw = None, [], 0.0
    if knaller:
        aanloop, rest = _aanloop(knaller)
        knal_regels, knal_vw = _passend(
            rest, ruimte["knal"][0], ruimte["knal"][1], 2, _knal_maat,
            lambda r: _REGEL_GETAL if GETAL.search(r) else _REGEL_KNAL, lambda aantal: _MAX_KNAL,
            _REGEL_AANLOOP if aanloop else 0.0,
        )
        knal = [delen_van(r) for r in knal_regels]
    return {
        "vorm": vorm,
        "titel_regels": titel_regels,
        "titel_vw": titel_vw,
        "regels": onder,
        "aanloop": aanloop,
        "aanloop_vw": round(max(2.6, knal_vw * AANLOOP_FACTOR), 2) if aanloop else 0,
        "knal": knal,
        "knal_vw": knal_vw,
        # Het lint: zo groot als past (een lang label wordt kleiner).
        "label_vw": round(min(_MAX_LABEL, 54 / max(_maat(label), 0.1)), 2) if label else 0,
    }


def _vlaggen():
    """De vlaggetjes aan twee slingers over de bovenkant: (links, boven in %, draaiing, kleur, vertraging). Ze hangen aan
    een boog (dezelfde als de lijn in _kiosk_sponsor_inhoud.html, op een vlak van 1920 bij 1080)."""
    kleuren = (GEEL, "#ffffff", "#4f7dff")
    bogen = (((-40, 26), (470, 236), (980, 44)), ((940, 44), (1450, 236), (1960, 26)))
    uit = []
    for b, (p0, p1, p2) in enumerate(bogen):
        for i in range(9):
            t = 0.07 + i * 0.86 / 8
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
            dx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
            dy = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
            hoek = math.degrees(math.atan2(dy, dx))
            uit.append((round(x / 19.2, 2), round(y / 10.8, 2), round(hoek, 1), kleuren[(i + b) % 3],
                        round((i * 0.37 + b * 0.6) % 2.4, 2)))
    return uit


VLAGGEN = _vlaggen()
