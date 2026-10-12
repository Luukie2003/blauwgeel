"""De prijslijst om op te hangen aan de bar: wat er op de prijzen-tv staat, op A4."""

from datetime import date

from pdf.basis import KLEUR_BLAUW, KLEUR_RAND, Rapport, _euro


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
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*KLEUR_BLAUW)
        pdf.cell(0, 8, naam, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_draw_color(*KLEUR_RAND)
        for item in items:
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(140, 8, item["naam"], border="B")
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(50, 8, _euro(item["verkoopprijs"]), border="B", align="R", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
