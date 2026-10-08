"""Opmaak die alle PDF's delen: kleuren, kop en voet met logo, en de tabelregels."""

from datetime import datetime
from pathlib import Path

from fpdf import FPDF


NAAM_APP = "Kantine Beheer"


NAAM_CLUB = "s.v. Blauw-Geel 1915"


LOGO_PAD = Path(__file__).resolve().parent.parent / "static" / "logo.png"


KLEUR_BLAUW = (30, 58, 138)


KLEUR_BLAUW_DONKER = (15, 31, 77)


KLEUR_ACCENT = (64, 97, 175)


KLEUR_GEEL = (252, 212, 47)


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
        if LOGO_PAD.exists():
            self.image(str(LOGO_PAD), x=180, y=9, h=16)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*KLEUR_BLAUW)
        self.cell(0, 9, NAAM_APP, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*KLEUR_ACCENT)
        self.cell(0, 5, NAAM_CLUB, new_x="LMARGIN", new_y="NEXT")
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

    def sectie(self, titel):
        self.ln(6)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*KLEUR_BLAUW)
        self.cell(0, 8, titel, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def statregel(self, label, waarde):
        self.set_font("Helvetica", "", 10)
        self.cell(90, 6.5, label, new_x="RIGHT")
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 6.5, str(waarde), new_x="LMARGIN", new_y="NEXT")


def _kort(pdf, tekst, breedte_mm):
    max_breedte = breedte_mm - 2
    if pdf.get_string_width(tekst) <= max_breedte:
        return tekst
    while tekst and pdf.get_string_width(tekst + "...") > max_breedte:
        tekst = tekst[:-1]
    return tekst + "..."


def _euro(bedrag):
    return f"€ {bedrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _datum_nl(tekst):
    """'2026-10-07 14:30' -> '07-10-2026 14:30'; laat andere invoer ongemoeid."""
    try:
        return datetime.strptime(tekst, "%Y-%m-%d %H:%M").strftime("%d-%m-%Y %H:%M")
    except (TypeError, ValueError):
        return tekst or ""
