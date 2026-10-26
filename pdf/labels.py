"""Schaplabels met QR-code en de stemposter."""

import io

from fpdf import FPDF

from pdf.basis import KLEUR_BLAUW, KLEUR_GEEL, KLEUR_GRIJS, KLEUR_RAND, KLEUR_WIT, LOGO_PAD, _euro, _kort


def stemming_poster_pdf(titel, qr_png_bytes):
    """Een A4-poster om op te hangen/neer te leggen bij de bar: groot de
    vraag, groot de QR-code. Bewust geen Rapport (dat is de kleine,
    zakelijke koptekst-stijl) -- dit mag een blikvanger zijn."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()

    pdf.set_fill_color(*KLEUR_BLAUW)
    pdf.rect(0, 0, 210, 297, style="F")

    if LOGO_PAD.exists():
        pdf.image(str(LOGO_PAD), x=85, y=18, w=40)

    pdf.set_xy(15, 66)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*KLEUR_GEEL)
    pdf.cell(180, 7, "S.V. BLAUW-GEEL 1915 - STEMMEN!", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_xy(15, 78)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(*KLEUR_WIT)
    pdf.multi_cell(180, 13, titel, align="C")

    kaart_breedte = 125
    kaart_x = (210 - kaart_breedte) / 2
    kaart_y = 128
    kaart_hoogte = 118
    pdf.set_fill_color(*KLEUR_WIT)
    pdf.rect(kaart_x, kaart_y, kaart_breedte, kaart_hoogte, style="F")

    qr_grootte = 95
    pdf.image(
        io.BytesIO(qr_png_bytes),
        x=(210 - qr_grootte) / 2,
        y=kaart_y + (kaart_hoogte - qr_grootte) / 2,
        w=qr_grootte,
    )

    pdf.set_xy(15, kaart_y + kaart_hoogte + 10)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*KLEUR_GEEL)
    pdf.cell(180, 10, "Scan en stem mee!", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_xy(15, 283)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*KLEUR_WIT)
    pdf.cell(180, 6, "Kantine Beheer - s.v. Blauw-Geel 1915", align="C")

    return bytes(pdf.output())


# Schaplabels: A4 om na het printen los te knippen. Groot: 6 brede stroken per vel, met het logo en (als die er is)
# de productfoto. Klein: 16 per vel (2 kolommen van 8), voor een smal schap of de koeling.
LABEL_FORMATEN = ("groot", "klein")


LABEL_STROKEN_PER_PAGINA = 6


LABEL_BREEDTE = 190


LABEL_HOOGTE = 44


LABEL_MARGE_LINKS = 10


LABEL_MARGE_BOVEN = 8


LABEL_GAP = 2.4


LABEL_KLEIN = {"kolommen": 2, "rijen": 8, "breedte": 95, "hoogte": 33, "marge_links": 8, "kolom_gap": 4}


def label_opties(args):
    """Het formaat en of de verkoopprijs erop moet, uit de querystring van een label-PDF (?formaat=klein&prijs=1)."""
    formaat = args.get("formaat", "groot")
    return {"formaat": formaat if formaat in LABEL_FORMATEN else "groot", "met_prijs": args.get("prijs") == "1"}


def schaplabels_pdf(producten, formaat="groot", met_prijs=False):
    """Printbare schaplabels om na het printen los te knippen en aan het schap te hangen. Elk label toont de naam en de
    categorie, het minimum, hoe en bij wie je het bestelt, en een QR-code: de handterminal opent daarmee het product
    (met de bestelknoppen), een telefooncamera de publieke landingspagina. De routes leveren de QR-bytes en het
    foto-pad aan; dit bestand kent qr.py bewust niet, net als stemming_poster_pdf hierboven.

    formaat: "groot" (6 stroken per vel, met logo en foto) of "klein" (16 per vel, alleen tekst en QR-code).
    met_prijs: de verkoopprijs groot naast de naam, voor een label in de koeling of aan de bar.

    producten: lijst van dicts met naam, categorie en verder allemaal optionele velden (ontbrekend of leeg wordt gewoon
    overgeslagen): subcategorie, artikelcode, leverancier, min_voorraad, eenheid, besteleenheid, besteleenheid_factor,
    verkoopprijs, qr_png (kant-en-klare PNG-bytes), qr_hint (de regel onder de QR-code) en foto_pad. Zonder foto of
    QR-code krijgt de tekst die ruimte erbij."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.core_fonts_encoding = "cp1252"  # voor het euroteken, zie Rapport in pdf/basis.py
    pdf.set_auto_page_break(False)

    klein = formaat == "klein"
    if klein:
        kolommen, rijen = LABEL_KLEIN["kolommen"], LABEL_KLEIN["rijen"]
        breedte, hoogte = LABEL_KLEIN["breedte"], LABEL_KLEIN["hoogte"]
        marge_links, kolom_gap = LABEL_KLEIN["marge_links"], LABEL_KLEIN["kolom_gap"]
    else:
        kolommen, rijen = 1, LABEL_STROKEN_PER_PAGINA
        breedte, hoogte = LABEL_BREEDTE, LABEL_HOOGTE
        marge_links, kolom_gap = LABEL_MARGE_LINKS, 0

    for i, product in enumerate(producten):
        plek = i % (kolommen * rijen)
        if plek == 0:
            pdf.add_page()
        rij, kolom = divmod(plek, kolommen)
        x0 = marge_links + kolom * (breedte + kolom_gap)
        y0 = LABEL_MARGE_BOVEN + rij * (hoogte + LABEL_GAP)

        # Stippellijnen om langs te knippen.
        pdf.set_draw_color(*KLEUR_RAND)
        pdf.set_dash_pattern(dash=2, gap=1.5)
        if rij > 0:
            pdf.line(x0, y0 - LABEL_GAP / 2, x0 + breedte, y0 - LABEL_GAP / 2)
        if kolom > 0:
            pdf.line(x0 - kolom_gap / 2, y0, x0 - kolom_gap / 2, y0 + hoogte)
        pdf.set_dash_pattern()

        pdf.set_fill_color(*KLEUR_GEEL)
        pdf.rect(x0, y0, 2 if klein else 2.5, hoogte, style="F")

        if klein:
            rechts = x0 + breedte - 1.5
            if product.get("qr_png"):
                rechts = _label_qr(pdf, product, rechts, y0, hoogte, grootte=23, hint_grootte=5.5) - 3
            _label_tekst(pdf, product, x0 + 5, y0 + 2.5, rechts - x0 - 5, met_prijs, klein=True)
            continue

        if LOGO_PAD.exists():
            pdf.image(str(LOGO_PAD), x=x0 + 6, y=y0 + (hoogte - 14) / 2, h=14)
        rechts = x0 + breedte - 2
        if product.get("qr_png"):
            rechts = _label_qr(pdf, product, rechts, y0, hoogte, grootte=30, hint_grootte=6.5) - 4
        if product.get("foto_pad"):
            rechts = _label_foto(pdf, product["foto_pad"], rechts, y0, hoogte, grootte=32)
        _label_tekst(pdf, product, x0 + 24, y0 + 4, rechts - x0 - 24, met_prijs, klein=False)

    return bytes(pdf.output())


def _passend(pdf, tekst, breedte, stijl, grootte, kleinste):
    """Zet het lettertype op de grootste maat (van grootte tot kleinste) waarin de tekst in de breedte past. Past hij
    ook in de kleinste maat niet, dan wordt hij ingekort (_kort)."""
    while True:
        pdf.set_font("Helvetica", stijl, grootte)
        if pdf.get_string_width(tekst) <= breedte - 2 or grootte <= kleinste:
            return _kort(pdf, tekst, breedte)
        grootte -= 0.5


def label_regels(product):
    """De regels onder de naam en de categorie: het minimum (ook in colli als dat precies uitkomt), hoe je het bestelt
    en bij wie. Wat onbekend is, valt weg. Geeft (soort, tekst)-paren."""
    regels = []
    minimum = product.get("min_voorraad") or 0
    besteleenheid = product.get("besteleenheid")
    factor = product.get("besteleenheid_factor") or 1
    if minimum > 0:
        tekst = f"Min. voorraad: {minimum} {product.get('eenheid') or ''}".rstrip()
        if besteleenheid and factor > 1 and minimum % factor == 0:
            tekst += f" ({minimum // factor} {besteleenheid})"
        regels.append(("minimum", tekst))
    if besteleenheid:
        regels.append(("bestellen", f"Bestellen per {besteleenheid}" + (f" van {factor}" if factor > 1 else "")))
    delen = [product.get("leverancier"), f"art.nr. {product['artikelcode']}" if product.get("artikelcode") else None]
    herkomst = " · ".join(d for d in delen if d)
    if herkomst:
        regels.append(("herkomst", herkomst[0].upper() + herkomst[1:]))
    return regels


# Per soort regel: (stijl, lettergrootte groot, lettergrootte klein, kleur).
_REGEL_OPMAAK = {
    "minimum": ("B", 10, 8.5, KLEUR_BLAUW),
    "bestellen": ("", 9, 7.5, (40, 40, 40)),
    "herkomst": ("", 8, 7, KLEUR_GRIJS),
}


def _label_tekst(pdf, product, x, y, breedte, met_prijs, klein):
    """De naam (met de prijs ernaast als die erop moet), de categorie en de regels van label_regels, van boven naar
    beneden."""
    naam_grootte, naam_kleinste, naam_hoogte = (13, 9, 6) if klein else (17, 11, 8)
    naam_breedte = breedte
    prijs = product.get("verkoopprijs") if met_prijs else None
    if prijs:
        tekst = _euro(prijs)
        pdf.set_font("Helvetica", "B", naam_grootte)
        prijs_breedte = pdf.get_string_width(tekst) + 2
        pdf.set_text_color(*KLEUR_BLAUW)
        pdf.set_xy(x + breedte - prijs_breedte, y)
        pdf.cell(prijs_breedte, naam_hoogte, tekst, align="R")
        naam_breedte -= prijs_breedte + 2
    pdf.set_text_color(0, 0, 0)
    naam = _passend(pdf, product["naam"], naam_breedte, "B", naam_grootte, naam_kleinste)
    pdf.set_xy(x, y)
    pdf.cell(naam_breedte, naam_hoogte, naam)
    y += naam_hoogte + (0.3 if klein else 1)

    subtekst = product["categorie"] or ""
    if product.get("subcategorie"):
        subtekst += f" · {product['subcategorie']}"
    if subtekst:
        pdf.set_font("Helvetica", "", 7.5 if klein else 9)
        pdf.set_text_color(*KLEUR_GRIJS)
        pdf.set_xy(x, y)
        pdf.cell(breedte, 4 if klein else 5, _kort(pdf, subtekst, breedte))
        y += 4.6 if klein else 6.5

    for soort, tekst in label_regels(product):
        stijl, groot, kleiner, kleur = _REGEL_OPMAAK[soort]
        pdf.set_font("Helvetica", stijl, kleiner if klein else groot)
        pdf.set_text_color(*kleur)
        pdf.set_xy(x, y)
        pdf.cell(breedte, 4 if klein else 5, _kort(pdf, tekst, breedte))
        y += 4.2 if klein else 5.5


def _label_qr(pdf, product, rechts, y0, hoogte, grootte, hint_grootte):
    """De QR-code rechts op het label, met eronder wat je ermee doet. Geeft de linkerkant ervan terug."""
    x = rechts - grootte
    hint_hoogte = hint_grootte * 0.45
    y = y0 + (hoogte - grootte - hint_hoogte) / 2
    pdf.image(io.BytesIO(product["qr_png"]), x=x, y=y, w=grootte)
    hint = product.get("qr_hint") or "Scan met de handterminal"
    pdf.set_text_color(*KLEUR_GRIJS)
    hint = _passend(pdf, hint, grootte + 4, "", hint_grootte, 4.5)
    pdf.set_xy(x - 2, y + grootte - 0.5)
    pdf.cell(grootte + 4, hint_hoogte, hint, align="C")
    return x


def _label_foto(pdf, foto_pad, rechts, y0, hoogte, grootte):
    """De productfoto links van de QR-code. Geeft de nieuwe rechterkant voor de tekst terug: links van de foto, of
    ongewijzigd als de foto niet te tekenen is (verwijderd of beschadigd -- de rest van het label, en de andere labels
    op het vel, mogen daar niet om mislukken)."""
    x = rechts - grootte
    try:
        pdf.image(str(foto_pad), x=x, y=y0 + (hoogte - grootte) / 2, w=grootte, h=grootte, keep_aspect_ratio=True)
    except Exception:
        return rechts
    return x - 4
