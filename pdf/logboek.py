"""PDF van het logboek."""

from pdf.basis import KLEUR_RAND, KLEUR_WIT, KLEUR_ZEBRA, Rapport, _kort


def _logboek_kop(pdf):
    pdf.kop_rij([("Moment", 33, "L"), ("Wie", 27, "L"), ("Actie", 48, "L"), ("Details", 82, "L")])


def logboek_pdf(regels, periode):
    """Het logboek als PDF: regels = [{"moment", "wie", "actie", "details"}]."""
    pdf = Rapport("Logboek", f"{periode}  -  {len(regels)} regels")
    if not regels:
        pdf.leeg_bericht("Niets gelogd in deze periode.")
        return bytes(pdf.output())
    _logboek_kop(pdf)
    pdf.set_font("Helvetica", "", 8)
    for i, r in enumerate(regels):
        pdf.set_font("Helvetica", "", 8)
        # Details kunnen lang zijn: laat ze over meerdere regels lopen, en maak de
        # rij zo hoog als dat nodig is.
        regels_details = pdf.multi_cell(81, 4.2, r["details"] or " ", align="L", dry_run=True, output="LINES")
        hoogte = max(5.5, len(regels_details) * 4.2 + 1.3)
        if pdf.get_y() + hoogte > pdf.page_break_trigger:
            pdf.add_page()
            _logboek_kop(pdf)
            pdf.set_font("Helvetica", "", 8)
        x, y = pdf.get_x(), pdf.get_y()
        pdf.set_fill_color(*(KLEUR_ZEBRA if i % 2 == 1 else KLEUR_WIT))
        pdf.set_draw_color(*KLEUR_RAND)
        for tekst, breedte in ((r["moment"], 33), (r["wie"], 27), (r["actie"], 48)):
            pdf.set_xy(x, y)
            pdf.cell(breedte, hoogte, _kort(pdf, tekst, breedte), border=1, fill=True)
            x += breedte
        pdf.set_xy(x, y)
        pdf.rect(x, y, 82, hoogte, style="DF")
        pdf.set_xy(x + 0.5, y + 0.65)
        pdf.multi_cell(81, 4.2, r["details"], align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.set_xy(10, y + hoogte)
    return bytes(pdf.output())
