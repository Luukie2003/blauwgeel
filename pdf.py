from datetime import datetime
from pathlib import Path

from fpdf import FPDF

NAAM_APP = "Kantine Beheer"
NAAM_CLUB = "s.v. Blauw-Geel 1915"
LOGO_PAD = Path(__file__).parent / "static" / "logo.png"

KLEUR_BLAUW = (30, 58, 138)
KLEUR_ACCENT = (64, 97, 175)
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


def bestellijst_pdf(suggesties):
    pdf = Rapport("Bestellijst", "Producten onder de minimumvoorraad")
    kolommen = [
        ("Product", 60, "L"),
        ("Categorie", 28, "L"),
        ("Voorraad", 26, "R"),
        ("Minimum", 26, "R"),
        ("Aantal bestellen", 46, "R"),
    ]
    pdf.kop_rij(kolommen)
    for i, p in enumerate(suggesties):
        tekort = p["bestel_hoeveelheid"] if p["bestel_hoeveelheid"] > 0 else max(
            0, p["min_voorraad"] - p["voorraad"]
        )
        factor = p["besteleenheid_factor"] or 1
        besteleenheid = p["besteleenheid"] or p["eenheid"]
        besteleenheden = -(-tekort // factor)
        aantal_tekst = f"{besteleenheden} {besteleenheid}"
        if factor > 1:
            aantal_tekst += f" ({besteleenheden * factor} {p['eenheid']})"
        pdf.data_rij(
            [
                (_kort(pdf, p["naam"], 60), 60, "L"),
                (p["categorie"], 28, "L"),
                (f"{p['voorraad']} {p['eenheid']}", 26, "R"),
                (f"{p['min_voorraad']} {p['eenheid']}", 26, "R"),
                (aantal_tekst, 46, "R"),
            ],
            zebra=i % 2 == 1,
        )
    if not suggesties:
        pdf.leeg_bericht("Niets te bestellen - alle voorraad zit boven het minimum.")
    return bytes(pdf.output())


def periode_verkoop_pdf(van_tekst, tot_tekst, regels):
    periode = f"Periode: {van_tekst}  t/m  {tot_tekst}"
    pdf = Rapport("Verkooprapport per periode", periode)

    kolommen = [
        ("Product", 50, "L"),
        ("Categorie", 32, "L"),
        ("Verkocht", 26, "R"),
        ("Gem. prijs", 32, "R"),
        ("Omzet", 30, "R"),
    ]
    pdf.kop_rij(kolommen)

    # Omzet komt al kant-en-klaar uit de database (verkocht * de destijds
    # vastgezette prijs, per telling gesommeerd) -- niet hier opnieuw
    # berekenen met de huidige prijs, want die kan intussen zijn gewijzigd.
    totaal_omzet = 0.0
    verkocht_regels = [r for r in regels if r["verkocht"] > 0]
    for i, r in enumerate(verkocht_regels):
        omzet = r["omzet"]
        totaal_omzet += omzet
        gem_prijs = omzet / r["verkocht"] if r["verkocht"] else 0
        pdf.data_rij(
            [
                (_kort(pdf, r["product_naam"], 50), 50, "L"),
                (_kort(pdf, r["categorie"], 32), 32, "L"),
                (f"{r['verkocht']} {r['eenheid']}", 26, "R"),
                (_euro(gem_prijs), 32, "R"),
                (_euro(omzet), 30, "R"),
            ],
            zebra=i % 2 == 1,
        )

    if not verkocht_regels:
        pdf.leeg_bericht("Geen verkoop geregistreerd in deze periode.")
    else:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(108, 8, "", border=0)
        pdf.cell(32, 8, "Totaal", align="R")
        pdf.cell(30, 8, _euro(totaal_omzet), align="R", new_x="LMARGIN", new_y="NEXT")

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


def voorraadoverzicht_pdf(gegevens):
    pdf = Rapport("Voorraadoverzicht", "Volledige stand van zaken van de kantinevoorraad")

    pdf.sectie("Samenvatting")
    pdf.statregel("Totale voorraadwaarde (verkoopprijs):", _euro(gegevens["totale_waarde"]))
    pdf.statregel("Aantal producten:", gegevens["aantal_producten"])
    pdf.statregel("Aantal categorieën:", gegevens["aantal_categorieen"])
    pdf.statregel("Producten zonder voorraad:", len(gegevens["zonder_voorraad"]))
    pdf.statregel("Producten onder minimum:", len(gegevens["onder_minimum"]))
    pdf.statregel("Nog nooit geteld:", len(gegevens["nooit_geteld"]))

    pdf.sectie("Voorraadwaarde per categorie")
    pdf.kop_rij(
        [
            ("Categorie", 70, "L"),
            ("Producten", 30, "R"),
            ("Waarde", 40, "R"),
            ("Aandeel", 30, "R"),
        ]
    )
    for i, c in enumerate(gegevens["categorie_lijst"]):
        pdf.data_rij(
            [
                (_kort(pdf, c["naam"], 70), 70, "L"),
                (c["aantal"], 30, "R"),
                (_euro(c["waarde"]), 40, "R"),
                (f"{c['percentage']:.1f}%", 30, "R"),
            ],
            zebra=i % 2 == 1,
        )

    pdf.sectie("Top 10 producten op voorraadwaarde")
    pdf.kop_rij(
        [
            ("Product", 66, "L"),
            ("Voorraad", 34, "R"),
            ("Verkoopprijs", 32, "R"),
            ("Waarde", 38, "R"),
        ]
    )
    for i, p in enumerate(gegevens["top_waarde"]):
        waarde = p["voorraad"] * p["verkoopprijs"]
        pdf.data_rij(
            [
                (_kort(pdf, p["naam"], 66), 66, "L"),
                (f"{p['voorraad']} {p['eenheid']}", 34, "R"),
                (_euro(p["verkoopprijs"]), 32, "R"),
                (_euro(waarde), 38, "R"),
            ],
            zebra=i % 2 == 1,
        )

    pdf.sectie("Opvallende zaken")
    if gegevens["inactief_met_voorraad"]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(
            0,
            7,
            f"Inactieve producten met nog voorraad ({len(gegevens['inactief_met_voorraad'])}):",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_font("Helvetica", "", 9)
        for p in gegevens["inactief_met_voorraad"]:
            pdf.cell(
                0,
                6,
                f"  -  {p['naam']}: {p['voorraad']} {p['eenheid']} nog op voorraad",
                new_x="LMARGIN",
                new_y="NEXT",
            )
        pdf.ln(2)

    if gegevens["zonder_prijs"]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(
            0,
            7,
            f"Actieve producten zonder verkoopprijs ({len(gegevens['zonder_prijs'])}):",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_font("Helvetica", "", 9)
        namen = ", ".join(p["naam"] for p in gegevens["zonder_prijs"])
        pdf.multi_cell(0, 6, f"  {namen}")
        pdf.ln(2)

    if gegevens["langst_niet_geteld"]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "Langst niet geteld:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for regel in gegevens["langst_niet_geteld"]:
            pdf.cell(
                0,
                6,
                f"  -  {regel['product']['naam']}: laatst geteld op {regel['laatste_datum']}",
                new_x="LMARGIN",
                new_y="NEXT",
            )
        pdf.ln(2)

    if (
        not gegevens["inactief_met_voorraad"]
        and not gegevens["zonder_prijs"]
        and not gegevens["langst_niet_geteld"]
    ):
        pdf.leeg_bericht("Niets opvallends gevonden.")

    pdf.sectie("Volledige productenlijst")
    pdf.kop_rij(
        [
            ("Code", 22, "L"),
            ("Product", 52, "L"),
            ("Categorie", 34, "L"),
            ("Voorraad", 26, "R"),
            ("Minimum", 24, "R"),
            ("Waarde", 32, "R"),
        ]
    )
    for i, p in enumerate(gegevens["producten"]):
        waarde = p["voorraad"] * p["verkoopprijs"]
        pdf.data_rij(
            [
                (p["artikelcode"] or "-", 22, "L"),
                (_kort(pdf, p["naam"], 52), 52, "L"),
                (_kort(pdf, p["categorie"], 34), 34, "L"),
                (f"{p['voorraad']} {p['eenheid']}", 26, "R"),
                (f"{p['min_voorraad']} {p['eenheid']}", 24, "R"),
                (_euro(waarde), 32, "R"),
            ],
            zebra=i % 2 == 1,
        )

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
