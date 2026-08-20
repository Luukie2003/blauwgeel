from datetime import datetime

from fpdf import FPDF

NAAM_APP = "Kantine Voorraadbeheer"

KLEUR_BLAUW = (30, 58, 138)
KLEUR_GRIJS = (90, 90, 90)
KLEUR_KOPRIJ = (228, 228, 228)
KLEUR_ZEBRA = (246, 246, 246)
KLEUR_WIT = (255, 255, 255)
KLEUR_RAND = (160, 160, 160)


class Rapport(FPDF):
    def __init__(self, titel, subtitel=""):
        super().__init__(orientation="P", unit="mm", format="A4")
        # The core Helvetica font has no glyph for "€" under the default
        # latin-1 mapping. cp1252 (Windows-1252) maps 0x80 to the euro sign,
        # which the standard font's built-in encoding does support.
        self.core_fonts_encoding = "cp1252"
        self._titel = titel
        self._subtitel = subtitel
        self.set_auto_page_break(auto=True, margin=20)
        self.add_page()

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*KLEUR_BLAUW)
        self.cell(0, 9, NAAM_APP, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(0, 0, 0)
        self.cell(0, 7, self._titel, new_x="LMARGIN", new_y="NEXT")
        if self._subtitel:
            self.set_font("Helvetica", "", 10)
            self.set_text_color(*KLEUR_GRIJS)
            self.cell(0, 6, self._subtitel, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*KLEUR_RAND)
        self.set_line_width(0.3)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(7)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*KLEUR_GRIJS)
        gegenereerd = datetime.now().strftime("%d-%m-%Y %H:%M")
        self.cell(
            0,
            10,
            f"Gegenereerd op {gegenereerd}  -  pagina {self.page_no()}",
            align="C",
        )

    def kop_rij(self, kolommen):
        """kolommen: list of (label, breedte_mm, align)"""
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(*KLEUR_KOPRIJ)
        self.set_draw_color(*KLEUR_RAND)
        for label, breedte, align in kolommen:
            self.cell(breedte, 7, label, border=1, align=align, fill=True)
        self.ln()

    def data_rij(self, waarden, zebra=False):
        """waarden: list of (tekst, breedte, align)"""
        self.set_font("Helvetica", "", 9)
        self.set_fill_color(*(KLEUR_ZEBRA if zebra else KLEUR_WIT))
        for tekst, breedte, align in waarden:
            self.cell(breedte, 6.5, str(tekst), border=1, align=align, fill=True)
        self.ln()

    def leeg_bericht(self, tekst):
        self.ln(3)
        self.set_font("Helvetica", "I", 10)
        self.set_text_color(*KLEUR_GRIJS)
        self.cell(0, 8, tekst, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)


def _kort(pdf, tekst, breedte_mm):
    max_breedte = breedte_mm - 2
    if pdf.get_string_width(tekst) <= max_breedte:
        return tekst
    while tekst and pdf.get_string_width(tekst + "...") > max_breedte:
        tekst = tekst[:-1]
    return tekst + "..."


def _euro(bedrag):
    return f"€ {bedrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def bestellijst_pdf(suggesties):
    pdf = Rapport("Bestellijst", "Producten onder de minimumvoorraad")
    kolommen = [
        ("Product", 68, "L"),
        ("Categorie", 32, "L"),
        ("Voorraad", 28, "R"),
        ("Minimum", 28, "R"),
        ("Aantal bestellen", 34, "R"),
    ]
    pdf.kop_rij(kolommen)
    for i, p in enumerate(suggesties):
        aantal = p["bestel_hoeveelheid"] if p["bestel_hoeveelheid"] > 0 else max(
            0, p["min_voorraad"] - p["voorraad"]
        )
        pdf.data_rij(
            [
                (_kort(pdf, p["naam"], 68), 68, "L"),
                (p["categorie"], 32, "L"),
                (f"{p['voorraad']} {p['eenheid']}", 28, "R"),
                (f"{p['min_voorraad']} {p['eenheid']}", 28, "R"),
                (f"{aantal} {p['eenheid']}", 34, "R"),
            ],
            zebra=i % 2 == 1,
        )
    if not suggesties:
        pdf.leeg_bericht("Niets te bestellen - alle voorraad zit boven het minimum.")
    return bytes(pdf.output())


def verkoop_pdf(telling_id, periode_tekst, regels):
    pdf = Rapport(f"Verkooprapport - telling #{telling_id}", periode_tekst)

    kolommen = [
        ("Product", 58, "L"),
        ("Verkocht", 26, "R"),
        ("Verkoopprijs", 32, "R"),
        ("Omzet", 32, "R"),
    ]
    pdf.kop_rij(kolommen)

    totaal_omzet = 0.0
    verkocht_regels = [r for r in regels if r["verkocht"] > 0]
    for i, r in enumerate(verkocht_regels):
        omzet = r["verkocht"] * r["verkoopprijs"]
        totaal_omzet += omzet
        pdf.data_rij(
            [
                (_kort(pdf, r["product_naam"], 58), 58, "L"),
                (f"{r['verkocht']} {r['eenheid']}", 26, "R"),
                (_euro(r["verkoopprijs"]), 32, "R"),
                (_euro(omzet), 32, "R"),
            ],
            zebra=i % 2 == 1,
        )

    if not verkocht_regels:
        pdf.leeg_bericht("Geen verkoop geregistreerd in deze periode.")
    else:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(116, 8, "", border=0)
        pdf.cell(32, 8, "Totaal", align="R")
        pdf.cell(32, 8, _euro(totaal_omzet), align="R", new_x="LMARGIN", new_y="NEXT")

    correcties = [r for r in regels if r["correctie"] > 0]
    if correcties:
        pdf.ln(8)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*KLEUR_BLAUW)
        pdf.cell(0, 8, "Correcties (extra gevonden voorraad)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.kop_rij([("Product", 100, "L"), ("Extra geteld", 40, "R")])
        for i, r in enumerate(correcties):
            pdf.data_rij(
                [
                    (_kort(pdf, r["product_naam"], 100), 100, "L"),
                    (f"+{r['correctie']} {r['eenheid']}", 40, "R"),
                ],
                zebra=i % 2 == 1,
            )

    return bytes(pdf.output())
