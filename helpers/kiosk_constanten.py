"""Vaste keuzelijsten en patronen voor de dia's en sjablonen op de Kantine-tv."""

import re


# De vaste layout-sjablonen voor een sponsor-slide op het kantine scherm --
# zie routes/kiosk.py (_bouw_slides) en templates/kiosk_scherm.html voor de
# bijbehorende CSS per sjabloon. "mededeling_groot" is bewust geen sponsor-
# layout maar een interne aankondiging (bijv. "kantinedienst gezocht") --
# krijgt daarom een duidelijk MEDEDELING-label op het scherm zelf, zodat
# niemand denkt dat het om een betaalde sponsor gaat.
KIOSK_SPONSOR_SJABLONEN = [
    ("afbeelding_volledig", "Afbeelding volledig scherm"),
    ("afbeelding_titel_tekst", "Afbeelding met titel en tekst"),
    ("titel_tekst_groot", "Alleen titel en tekst (geen afbeelding)"),
    ("titel_ondertitel_banner", "Compacte banner (titel + ondertitel)"),
    ("mededeling_groot", "Mededeling (met label, geen afbeelding)"),
    ("video_volledig", "Video (schermvullend, met optioneel onderschrift)"),
]


KIOSK_SPONSOR_SJABLOON_SLEUTELS = {sleutel for sleutel, _ in KIOSK_SPONSOR_SJABLONEN}


# Voorbeeldtekst per sjabloon (titel, tekst) -- puur als placeholder in het
# formulier (zie kiosk_sponsor_form.html), om te laten zien wat voor inhoud
# bij die layout past. Vult niets automatisch in.
KIOSK_SPONSOR_SJABLOON_VOORBEELDEN = {
    "afbeelding_volledig": ("Bijv. 'Bakkerij Jansen'", ""),
    "afbeelding_titel_tekst": (
        "Bijv. 'Slagerij De Vries'",
        "Bijv. 'Voor al uw vleeswaren -- vraag naar de weekaanbieding!'",
    ),
    "titel_tekst_groot": (
        "Bijv. 'Welkom bij s.v. Blauw-Geel 1915!'",
        "Bijv. 'Geniet van de wedstrijd en een lekker drankje aan de bar.'",
    ),
    "titel_ondertitel_banner": (
        "Bijv. 'Happy hour'",
        "Bijv. 'Elke vrijdag 17:00-18:00 alle drank 1 euro korting'",
    ),
    "mededeling_groot": (
        "Bijv. 'Kantinedienst gezocht!'",
        "Bijv. 'Meld je aan bij de bar of via het secretariaat.'",
    ),
    "video_volledig": ("Bijv. 'Sponsorfilm Bakkerij Jansen' (onderschrift, mag leeg)", ""),
}


# Sentinel-waarde voor de sjabloon-kolom van kiosk_sponsoren: een zelfgebouwd
# sjabloon (zie kiosk_sjablonen_custom) i.p.v. een van de vaste lay-outs
# hierboven. Losse constante (i.p.v. in KIOSK_SPONSOR_SJABLONEN zelf) zodat
# de vaste-sjablonen-lijst puur de vaste lay-outs blijft.
KIOSK_SPONSOR_SJABLOON_AANGEPAST = "aangepast"


KIOSK_OVERGANGEN = [
    ("fade", "Fade in/uit"),
    ("schuiven", "Schuiven"),
    ("inzoomen", "Inzoomen"),
]


KIOSK_OVERGANG_SLEUTELS = {sleutel for sleutel, _ in KIOSK_OVERGANGEN}


KIOSK_TEKST_GROOTTES = [
    ("klein", "Klein"),
    ("normaal", "Normaal"),
    ("groot", "Groot"),
    ("xl", "Extra groot"),
]


KIOSK_TEKST_GROOTTE_SLEUTELS = {sleutel for sleutel, _ in KIOSK_TEKST_GROOTTES}


# Elementtypes voor de eigen-sjabloon-bouwer (zie kiosk_sjabloon_bouwer.html):
# titel/tekst/foto halen hun inhoud van de sponsor die het sjabloon gebruikt,
# vrije_tekst heeft eigen vaste inhoud die bij elk gebruik gelijk blijft, en
# prijs toont de actuele verkoopprijs van een zelf gekozen product (element
# heeft dan ook een "product_id") -- wijzigt die prijs later, dan verandert
# de dia vanzelf mee, net als de rest van het scherm.
KIOSK_ELEMENT_TYPES = {"titel", "tekst", "foto", "vrije_tekst", "prijs"}


KIOSK_UITLIJNINGEN = {"links", "midden", "rechts"}


HEX_KLEUR_PATROON = re.compile(r"^#[0-9a-fA-F]{6}$")


# 24-uurs 'HH:MM', gebruikt voor bardienst-tijden (zie kiosk_bardienst in
# routes/kiosk.py) -- hetzelfde formaat als een <input type="time"> teruggeeft.
KIOSK_TIJD_PATROON = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# CSS kent alleen de Engelse text-align-waarden -- de opgeslagen/getoonde
# waarden (links/midden/rechts) zijn puur voor het formulier en mogen nooit
# rechtstreeks als CSS-waarde belanden (zie css_uitlijning-filter, gebruikt
# in kiosk_scherm.html en de gelijknamige JS-helper in kiosk_sponsor_form.html
# / kiosk_sjabloon_bouwer.html).
KIOSK_UITLIJNING_CSS = {"links": "left", "midden": "center", "rechts": "right"}


def css_uitlijning(waarde):
    return KIOSK_UITLIJNING_CSS.get(waarde, "left")
