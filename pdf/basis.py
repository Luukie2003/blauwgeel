"""Opmaak die alle PDF's delen. Sinds 2.9.0 in de clubstijl, zoals de site: de Barlow-letter, de kleuren van
clubstijl.css, een donkerblauwe kop met het logo en een gele streep eronder, rustige tabellen (alleen lijnen tussen de
regels, de kop in kleine grijze hoofdletters) en een voet met 'pagina 1 van 3'.

De letters staan als TTF in pdf/letters: omgezet uit de woff2 van de site (static/fonts, zie Barlow-OFL.txt), want fpdf2
leest geen woff2. ClubPDF laadt een letter pas als hij gebruikt wordt. Een set_font met 'Helvetica' (zoals overal van
vóór 2.9.0) krijgt gewoon Barlow; cursief bestaat hier niet en wordt rechtop. Tekens die niet in de letter zitten (zoals
een pijl of een emoji in een productnaam) worden vervangen (_vervang), zodat er nooit een leeg vakje of een fout uit komt;
met de standaardletters van vroeger gaf zo'n teken een fout."""

import unicodedata
from datetime import datetime
from pathlib import Path

from fpdf import FPDF


NAAM_APP = "Kantine Beheer"


NAAM_CLUB = "s.v. Blauw-Geel 1915"


LOGO_PAD = Path(__file__).resolve().parent.parent / "static" / "logo.png"


LETTERS_MAP = Path(__file__).resolve().parent / "letters"


# De letters (zoals fpdf2 ze noemt) en hun bestanden: gewoon en vet (Barlow SemiBold, zoals vet op de site), en de smalle
# Barlow Condensed voor koppen en grote getallen.
LETTER = "barlow"


KOPLETTER = "barlowcondensed"


_LETTER_BESTANDEN = {
    LETTER: "Barlow-Regular.ttf",
    LETTER + "B": "Barlow-SemiBold.ttf",
    KOPLETTER: "BarlowCondensed-SemiBold.ttf",
    KOPLETTER + "B": "BarlowCondensed-Bold.ttf",
}


# De kleuren van clubstijl.css.
KLEUR_BLAUW = (30, 58, 138)  # --blauw


KLEUR_BLAUW_DONKER = (20, 39, 94)  # --blauw-donker, de kop


KLEUR_ACCENT = (196, 205, 230)  # lichtblauw op donkerblauw, zoals de tekst in de verzendbalk


KLEUR_GEEL = (252, 212, 47)  # --geel


KLEUR_TEKST = (26, 32, 51)  # --tekst


KLEUR_GRIJS = (95, 101, 117)  # --tekst-zacht


KLEUR_KOPRIJ = (246, 244, 239)  # --achtergrond: een vlak achter een kop of een totaal


KLEUR_ZEBRA = (250, 248, 243)  # om en om een regel, net iets warmer dan wit


KLEUR_WIT = (255, 255, 255)


KLEUR_RAND = (221, 215, 202)  # --rand


KLEUR_RAND_LICHT = (235, 230, 219)  # --rand-licht, tussen de regels van een tabel


KLEUR_ROOD = (184, 50, 31)  # --rood


KLEUR_GROEN = (31, 122, 69)  # --groen


# Tekens die niet in de Barlow van de site zitten, met wat ervoor in de plaats komt (de rest: zie _vervang).
_VERVANGINGEN = {
    "→": "->", "←": "<-", "⇒": "=>", "↑": "^", "↓": "v", "✓": "v", "✔": "v", "✗": "x", "✘": "x",
    "≥": ">=", "≤": "<=", "≈": "~", "ƒ": "f",
}


def _vervang(teken, tekens):
    """Een teken dat niet in de letter zit: uit _VERVANGINGEN, anders de letter zonder accent (ś wordt s), en anders
    niets (een emoji of een ander plaatje) of een vraagteken."""
    if teken in _VERVANGINGEN:
        return _VERVANGINGEN[teken]
    basis = "".join(t for t in unicodedata.normalize("NFKD", teken) if ord(t) in tekens)
    if basis:
        return basis
    soort = unicodedata.category(teken)
    return "" if soort[0] in "SMC" or soort in ("Zl", "Zp") else "?"


class ClubPDF(FPDF):
    """FPDF met de letters van de site (zie het begin van dit bestand)."""

    def set_font(self, family=None, style="", size=0):
        familie = (family or self.font_family or LETTER).lower().replace(" ", "").replace("-", "")
        if familie in ("helvetica", "arial", "times", "courier", "symbol", "zapfdingbats", "barlow"):
            familie = LETTER
        # fpdf2 geeft de stijl soms zelf door als TextEmphasis (bijvoorbeeld B|U); die kent .style ("BU").
        stijl = (style if isinstance(style, str) else getattr(style, "style", "") or "").upper()
        if familie in (LETTER, KOPLETTER):
            vet = "B" if "B" in stijl else ""
            if familie + vet not in self.fonts:
                self.add_font(familie, vet, str(LETTERS_MAP / _LETTER_BESTANDEN[familie + vet]))
            stijl = vet + ("U" if "U" in stijl else "")
        super().set_font(familie, stijl, size)

    def normalize_text(self, text):
        if self.is_ttf_font and self.current_font is not None:
            tekens = self.current_font.cmap
            if any(ord(t) not in tekens and t not in "\n\r\t" for t in text):
                text = "".join(t if ord(t) in tekens or t in "\n\r\t" else _vervang(t, tekens) for t in text)
        return super().normalize_text(text)


class Rapport(ClubPDF):
    """Een A4 met de kop van de club. Op de eerste pagina de titel groot met de ondertitel, daarna klein."""

    def __init__(self, titel, subtitel=""):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._titel = titel
        self._subtitel = subtitel
        self._tabel_kop = None
        self.set_auto_page_break(auto=True, margin=18)
        self.add_page()

    def header(self):
        # De balk zoals de titelbalk van de site: donkerblauw met het logo, en een gele streep eronder.
        self.set_fill_color(*KLEUR_BLAUW_DONKER)
        self.rect(0, 0, self.w, 17, style="F")
        self.set_fill_color(*KLEUR_GEEL)
        self.rect(0, 17, self.w, 1.3, style="F")
        if LOGO_PAD.exists():
            self.image(str(LOGO_PAD), x=self.l_margin, y=2.4, h=12.2)
        self.set_xy(self.l_margin + 14, 3.2)
        self.set_font(KOPLETTER, "B", 15)
        self.set_text_color(*KLEUR_WIT)
        self.set_char_spacing(0.5)
        self.cell(100, 6.4, "KANTINE BLAUW-GEEL")
        self.set_char_spacing(0)
        self.set_xy(self.l_margin + 14, 9.6)
        self.set_font(LETTER, "", 7.5)
        self.set_text_color(*KLEUR_ACCENT)
        self.cell(100, 4, "sinds 1915 · Coendersborg")
        self.set_xy(self.l_margin, 23)
        if self.page_no() == 1:
            self.set_font(KOPLETTER, "B", 22)
            self.set_text_color(*KLEUR_TEKST)
            self.cell(0, 9, self._titel, new_x="LMARGIN", new_y="NEXT")
            if self._subtitel:
                self.set_font(LETTER, "", 9.5)
                self.set_text_color(*KLEUR_GRIJS)
                self.multi_cell(0, 5, self._subtitel, new_x="LMARGIN", new_y="NEXT")
            self.ln(4)
        else:
            self.set_font(KOPLETTER, "B", 12)
            self.set_text_color(*KLEUR_GRIJS)
            self.cell(0, 6, f"{self._titel} (vervolg)", new_x="LMARGIN", new_y="NEXT")
            self.ln(2)
        self.set_text_color(*KLEUR_TEKST)

    def footer(self):
        self.set_draw_color(*KLEUR_RAND_LICHT)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.h - 13, self.w - self.r_margin, self.h - 13)
        self.set_font(LETTER, "", 7.5)
        self.set_text_color(*KLEUR_GRIJS)
        self.set_xy(self.l_margin, -12.5)
        self.cell(0, 6, f"{NAAM_APP}  ·  {NAAM_CLUB}", align="L")
        self.set_x(self.l_margin)
        gemaakt = datetime.now().strftime("%d-%m-%Y %H:%M")
        self.cell(0, 6, f"Gemaakt op {gemaakt}  ·  pagina {self.page_no()} van {self.str_alias_nb_pages}", align="R")

    def kop_rij(self, kolommen):
        """kolommen: list of (label, breedte_mm, align). De kop van een tabel, zoals op de site: kleine grijze
        hoofdletters met een lijn eronder. Komt de tabel op een volgende pagina, dan staat hij daar ook (data_rij)."""
        self._tabel_kop = kolommen
        self.set_font(LETTER, "B", 7.5)
        self.set_text_color(*KLEUR_GRIJS)
        self.set_draw_color(*KLEUR_RAND)
        self.set_line_width(0.35)
        self.set_char_spacing(0.3)
        for label, breedte, align in kolommen:
            self.cell(breedte, 7, str(label).upper(), border="B", align=align)
        self.set_char_spacing(0)
        self.ln()
        self.set_text_color(*KLEUR_TEKST)

    def data_rij(self, waarden, zebra=False):
        """waarden: list of (tekst, breedte, align)"""
        if self._tabel_kop and self.get_y() + 6.5 > self.page_break_trigger:
            self.add_page()
            self.kop_rij(self._tabel_kop)
        self.set_font(LETTER, "", 9)
        self.set_text_color(*KLEUR_TEKST)
        self.set_fill_color(*(KLEUR_ZEBRA if zebra else KLEUR_WIT))
        self.set_draw_color(*KLEUR_RAND_LICHT)
        self.set_line_width(0.2)
        for tekst, breedte, align in waarden:
            self.cell(breedte, 6.5, str(tekst), border="B", align=align, fill=True)
        self.ln()

    def leeg_bericht(self, tekst):
        self._tabel_kop = None
        self.ln(3)
        self.set_font(LETTER, "", 10)
        self.set_text_color(*KLEUR_GRIJS)
        self.cell(0, 8, tekst, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*KLEUR_TEKST)

    def sectie(self, titel):
        """Een kop boven een deel, zoals de kop van een paneel op de site, met een kort geel streepje eronder. Staat er
        onderaan de pagina geen plek meer voor iets eronder, dan begint hij op de volgende pagina."""
        self._tabel_kop = None
        self.ln(5)
        if self.get_y() > self.page_break_trigger - 22:
            self.add_page()
        self.set_font(KOPLETTER, "B", 14)
        self.set_text_color(*KLEUR_BLAUW_DONKER)
        self.cell(0, 7, titel, new_x="LMARGIN", new_y="NEXT")
        self.set_fill_color(*KLEUR_GEEL)
        self.rect(self.l_margin, self.get_y() + 0.3, 10, 0.9, style="F")
        self.ln(3.2)
        self.set_text_color(*KLEUR_TEKST)

    def statregel(self, label, waarde):
        self._tabel_kop = None
        self.set_font(LETTER, "", 10)
        self.set_text_color(*KLEUR_GRIJS)
        self.cell(90, 6.5, label, new_x="RIGHT")
        self.set_font(LETTER, "B", 10)
        self.set_text_color(*KLEUR_TEKST)
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
