"""De prijslijst om op te hangen aan de bar: wat er op de prijzen-tv staat, op A4."""

from datetime import date

from pdf.basis import (
    KLEUR_BLAUW_DONKER, KLEUR_GEEL, KLEUR_RAND_LICHT, KLEUR_TEKST, KOPLETTER, LETTER, Rapport, _euro,
)


def prijslijst_pdf(categorieen, per_datum=None):
    """categorieen: [(naam, [ {naam, verkoopprijs}, ...])] zoals het prijzenscherm ze heeft (zie
    routes/kiosk/prijzen_gegevens.py, _prijzen_categorieen). Grote letters, zodat hij van een afstand te lezen is."""
    per_datum = per_datum or date.today()
    pdf = Rapport("Prijslijst", f"Prijzen per {per_datum.strftime('%d-%m-%Y')}")
    if not categorieen:
        pdf.leeg_bericht("Er staan geen producten op het prijzenscherm.")
        return bytes(pdf.output())
    for naam, items in categorieen:
        if pdf.get_y() > 245:
            pdf.add_page()
        # De categorie zoals een kop op de site: smal en donkerblauw, met een geel streepje eronder.
        pdf.ln(4)
        pdf.set_font(KOPLETTER, "B", 18)
        pdf.set_text_color(*KLEUR_BLAUW_DONKER)
        pdf.cell(0, 8.5, naam, new_x="LMARGIN", new_y="NEXT")
        pdf.set_fill_color(*KLEUR_GEEL)
        pdf.rect(pdf.l_margin, pdf.get_y() + 0.3, 12, 1, style="F")
        pdf.ln(2.5)
        pdf.set_text_color(*KLEUR_TEKST)
        pdf.set_draw_color(*KLEUR_RAND_LICHT)
        pdf.set_line_width(0.3)
        for item in items:
            pdf.set_font(LETTER, "", 13)
            pdf.cell(140, 9, item["naam"], border="B")
            pdf.set_font(KOPLETTER, "B", 16)
            pdf.cell(50, 9, _euro(item["verkoopprijs"]), border="B", align="R", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
