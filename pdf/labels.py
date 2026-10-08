"""Schaplabels met QR-code en de stemposter."""

import io

from fpdf import FPDF

from pdf.basis import KLEUR_BLAUW, KLEUR_GEEL, KLEUR_GRIJS, KLEUR_RAND, KLEUR_WIT, LOGO_PAD, _kort


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


# Schaplabels: A4 in horizontale stroken om na het printen los te knippen.
LABEL_STROKEN_PER_PAGINA = 6


LABEL_BREEDTE = 190


LABEL_HOOGTE = 44


LABEL_MARGE_LINKS = 10


LABEL_MARGE_BOVEN = 8


LABEL_GAP = 2.4


def schaplabels_pdf(producten):
    """Printbare schaplabels: A4 in horizontale stroken (6 per vel), bedoeld
    om na het printen los te knippen en aan het schap te hangen. Elk label
    toont het logo, naam + categorie + (indien bekend) artikelcode en
    minimumvoorraad, een productfoto (indien aanwezig) en een QR-code die
    naar de productpagina linkt -- met elke telefooncamera te scannen, ook
    zonder de app open te hebben (zie routes/producten.py, dat 'm samen met
    de qr-bytes en het foto-pad aanlevert -- dit bestand kent qr.py bewust
    niet, net als stemming_poster_pdf hierboven al met de stem-QR doet).

    producten: lijst van dicts met naam, categorie en verder allemaal
    optionele velden (ontbrekend of None wordt gewoon overgeslagen):
    subcategorie, artikelcode, min_voorraad, eenheid, qr_png (kant-en-klare
    PNG-bytes), foto_pad en heeft_foto_kolom (standaard True). Zonder qr_png
    (bijv. een verbruiksvoorwerp zonder eigen productpagina om naartoe te
    scannen) vervalt ook de foto-kolom en krijgt de tekst de volle breedte
    van het label. heeft_foto_kolom=False laat het lege foto-kadertje
    achterwege voor iets dat sowieso nooit een foto heeft (verbruiksvoorwerpen
    hebben geen eigen afbeeldingsveld, in tegenstelling tot producten die er
    later nog een kunnen krijgen) -- de tekst gebruikt dan de ruimte ernaast."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)

    qr_grootte = 32
    foto_grootte = 32
    tekst_x = LABEL_MARGE_LINKS + 34
    qr_x = LABEL_MARGE_LINKS + LABEL_BREEDTE - qr_grootte - 2
    foto_x = qr_x - foto_grootte - 4
    tekst_breedte_met_foto_en_qr = foto_x - tekst_x - 4
    tekst_breedte_met_qr_zonder_foto = qr_x - tekst_x - 4
    tekst_breedte_zonder_qr = LABEL_MARGE_LINKS + LABEL_BREEDTE - 4 - tekst_x

    for i, product in enumerate(producten):
        heeft_qr = bool(product.get("qr_png"))
        heeft_foto_kolom = heeft_qr and product.get("heeft_foto_kolom", True)
        if not heeft_qr:
            tekst_breedte = tekst_breedte_zonder_qr
        elif heeft_foto_kolom:
            tekst_breedte = tekst_breedte_met_foto_en_qr
        else:
            tekst_breedte = tekst_breedte_met_qr_zonder_foto

        strook_index = i % LABEL_STROKEN_PER_PAGINA
        if strook_index == 0:
            pdf.add_page()
        y0 = LABEL_MARGE_BOVEN + strook_index * (LABEL_HOOGTE + LABEL_GAP)

        if strook_index > 0:
            pdf.set_draw_color(*KLEUR_RAND)
            pdf.set_dash_pattern(dash=2, gap=1.5)
            pdf.line(
                LABEL_MARGE_LINKS,
                y0 - LABEL_GAP / 2,
                LABEL_MARGE_LINKS + LABEL_BREEDTE,
                y0 - LABEL_GAP / 2,
            )
            pdf.set_dash_pattern()

        pdf.set_fill_color(*KLEUR_GEEL)
        pdf.rect(LABEL_MARGE_LINKS, y0, 2.5, LABEL_HOOGTE, style="F")

        if LOGO_PAD.exists():
            pdf.image(str(LOGO_PAD), x=LABEL_MARGE_LINKS + 6, y=y0 + (LABEL_HOOGTE - 14) / 2, h=14)

        pdf.set_xy(tekst_x, y0 + 5)
        pdf.set_font("Helvetica", "B", 17)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(tekst_breedte, 8, _kort(pdf, product["naam"], tekst_breedte), new_x="LMARGIN", new_y="NEXT")

        subtekst = product["categorie"]
        if product.get("subcategorie"):
            subtekst += f" · {product['subcategorie']}"
        pdf.set_xy(tekst_x, y0 + 18)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*KLEUR_GRIJS)
        pdf.cell(tekst_breedte, 5, _kort(pdf, subtekst, tekst_breedte), new_x="LMARGIN", new_y="NEXT")

        if product.get("artikelcode"):
            pdf.set_xy(tekst_x, y0 + 24)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*KLEUR_GRIJS)
            pdf.cell(
                tekst_breedte,
                4.5,
                _kort(pdf, f"Artikelcode: {product['artikelcode']}", tekst_breedte),
                new_x="LMARGIN",
                new_y="NEXT",
            )

        if product.get("min_voorraad") is not None:
            pdf.set_xy(tekst_x, y0 + 31)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*KLEUR_BLAUW)
            pdf.cell(
                tekst_breedte,
                6,
                f"Min. voorraad: {product['min_voorraad']} {product.get('eenheid', '')}",
                new_x="LMARGIN",
                new_y="NEXT",
            )

        if not heeft_qr:
            continue

        if heeft_foto_kolom:
            foto_y = y0 + (LABEL_HOOGTE - foto_grootte) / 2
            foto_getekend = False
            if product.get("foto_pad"):
                try:
                    pdf.image(
                        str(product["foto_pad"]),
                        x=foto_x,
                        y=foto_y,
                        w=foto_grootte,
                        h=foto_grootte,
                        keep_aspect_ratio=True,
                    )
                    foto_getekend = True
                except Exception:
                    # Bijv. een verwijderd of beschadigd bestand -- de rest van
                    # het label (en de andere labels op het vel) mag daar niet
                    # om mislukken, dan valt dit ene vakje terug op het lege
                    # kader hieronder.
                    foto_getekend = False
            if not foto_getekend:
                pdf.set_draw_color(*KLEUR_RAND)
                pdf.rect(foto_x, foto_y, foto_grootte, foto_grootte, style="D")

        pdf.image(
            io.BytesIO(product["qr_png"]),
            x=qr_x,
            y=y0 + (LABEL_HOOGTE - qr_grootte) / 2,
            w=qr_grootte,
        )

    return bytes(pdf.output())
