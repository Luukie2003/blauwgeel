"""Voorgedrukte kaartjes op A4, om uit te knippen: Naam, Team, hardlopers en lege regels.

Vijf ontwerpen (zie OPTIES): twee brede, twee vierkante en een smal staand ontwerp. De hardlopers (de dranken die hard lopen, met een vak om bij te turven) en of het
in kleur of zwart-wit moet, bepaalt de aanroeper (zie routes/kaartjes.py). Alle maten zijn in mm; de kaartjes
sluiten op elkaar aan, met stippellijntjes om langs te knippen."""

from collections import namedtuple

from fpdf import FPDF

from pdf.basis import KLEUR_BLAUW, KLEUR_GEEL, LOGO_PAD

# Meer hardlopers past niet: de ontwerpen hebben ruimte voor 2 kolommen van 2 (of 1 kolom van 4). Bewust weinig:
# hoe minder artikelen, hoe meer vrije regels er overblijven om op te schrijven.
MAX_HARDLOPERS = 4
MAX_TEKENS_HARDLOPER = 24

GRIJS = (150, 150, 150)
LIJN = (120, 120, 120)
ZWART = (30, 30, 30)
ZWARTWIT_ACCENT = (40, 40, 40)

Optie = namedtuple("Optie", "sleutel naam breedte hoogte kolommen rijen omschrijving")

# In deze volgorde getoond. Het eerste ontwerp is de standaard.
OPTIES = [
    Optie("D", "Breed", 97, 52, 2, 5, "Twee kolommen met een lang, leeg turfvak achter elke hardloper, 4 lege regels."),
    Optie("D2", "Breed, hoog turfvak", 97, 60, 2, 4, "Een hardloper per rij met een extra hoog turfvak over de hele breedte, 3 lege regels."),
    Optie("A", "Vierkant", 65, 65, 3, 4, "Een hardloper per rij met een lang turfvak, ruim opgezet, 4 lege regels."),
    Optie("B", "Vierkant, met logo", 55, 55, 3, 5, "Met het clublogo in een slanke balk, een hardloper per rij met turfvak, 3 lege regels."),
    Optie("C", "Staand, smal", 46, 82, 4, 3, "Smal en hoog: de naam boven een breed turfvak, Naam en Team onder elkaar, 4 lege regels."),
]
OPTIE_PER_SLEUTEL = {o.sleutel: o for o in OPTIES}
STANDAARD_OPTIE = OPTIES[0].sleutel


def _alle_namen(tekst):
    namen = []
    for regel in (tekst or "").splitlines():
        naam = " ".join(regel.split())[:MAX_TEKENS_HARDLOPER]
        if naam and naam.lower() not in [n.lower() for n in namen]:
            namen.append(naam)
    return namen


def schoon_hardlopers(tekst):
    """Een lijst namen uit een tekst met een naam per regel: lege regels weg, hooguit MAX_HARDLOPERS namen van
    hooguit MAX_TEKENS_HARDLOPER tekens. Geeft (namen, aantal_weggelaten)."""
    namen = _alle_namen(tekst)
    return namen[:MAX_HARDLOPERS], max(0, len(namen) - MAX_HARDLOPERS)


def hardlopers_over(tekst):
    """De namen uit de tekst die niet meer op het kaartje passen (na de eerste MAX_HARDLOPERS)."""
    return _alle_namen(tekst)[MAX_HARDLOPERS:]


def _veilig(tekst):
    """De standaardlettertypes van een pdf kennen alleen Latijn-1: iets anders (bijv. een emoji) wordt een ?."""
    return tekst.encode("latin-1", "replace").decode("latin-1")


class _Tekenaar:
    def __init__(self, pdf, hardlopers, zwartwit=False):
        self.pdf = pdf
        self.hardlopers = [_veilig(naam) for naam in hardlopers[:MAX_HARDLOPERS]]
        self.blauw = ZWARTWIT_ACCENT if zwartwit else KLEUR_BLAUW
        self.geel = (255, 255, 255) if zwartwit else KLEUR_GEEL

    # ---------- bouwstenen ----------

    def lijn(self, x1, x2, y, kleur=LIJN, dikte=0.2):
        self.pdf.set_draw_color(*kleur)
        self.pdf.set_line_width(dikte)
        self.pdf.line(x1, y, x2, y)

    def stippel(self, x1, x2, y):
        """Een gestippelde lege regel (voor eigen notities)."""
        self.pdf.set_draw_color(*GRIJS)
        self.pdf.set_line_width(0.2)
        self.pdf.set_dash_pattern(dash=0.6, gap=0.8)
        self.pdf.line(x1, y, x2, y)
        self.pdf.set_dash_pattern()

    def dubbele_lijn(self, x1, x2, y):
        """De dubbele blauwe scheiding tussen Naam/Team en de hardlopers."""
        self.pdf.set_draw_color(*self.blauw)
        self.pdf.set_line_width(0.35)
        self.pdf.line(x1, y, x2, y)
        self.pdf.line(x1, y + 1.0, x2, y + 1.0)

    def label(self, tekst, x, y, maat=6.5, stijl="", kleur=GRIJS):
        self.pdf.set_font("Helvetica", stijl, maat)
        self.pdf.set_text_color(*kleur)
        self.pdf.text(x, y, tekst)
        return self.pdf.get_string_width(tekst)

    def veld(self, tekst, x, x_eind, y_lijn, maat=6.5):
        """Een label met een schrijflijn erachter, op de hoogte van y_lijn."""
        b = self.label(tekst, x, y_lijn - 0.6, maat)
        self.lijn(x + b + 1.2, x_eind, y_lijn)

    def _maten(self, maat, ruimte):
        """Per naam een lettergrootte waarbij hij binnen 'ruimte' past (anders iets kleiner)."""
        maten = []
        for naam in self.hardlopers:
            m = maat
            self.pdf.set_font("Helvetica", "", m)
            while self.pdf.get_string_width(naam) > ruimte and m > 4.2:
                m -= 0.2
                self.pdf.set_font("Helvetica", "", m)
            maten.append(m)
        return maten

    def _langste(self, maten):
        langste = 0
        for naam, m in zip(self.hardlopers, maten):
            self.pdf.set_font("Helvetica", "", m)
            langste = max(langste, self.pdf.get_string_width(naam))
        return langste

    def hardlopers_gestapeld(self, x, y_eerste, breedte, stap, hoogte=5.2, maat=6.4):
        """De hardlopers onder elkaar, elk met de naam boven een turfvak over de hele breedte (voor smalle kaartjes,
        waar naast de naam te weinig plek voor een vak overblijft)."""
        maten = self._maten(maat, breedte)
        for i, (naam, m) in enumerate(zip(self.hardlopers, maten)):
            cy = y_eerste + i * stap
            self.pdf.set_font("Helvetica", "", m)
            self.pdf.set_text_color(*ZWART)
            self.pdf.text(x, cy, naam)
            self.pdf.set_draw_color(*LIJN)
            self.pdf.set_line_width(0.25)
            self.pdf.rect(x, cy + 0.9, breedte, hoogte)

    def hardlopers_turf(self, x, y_eerste, breedte, rij_h, kolommen, maat=6.2, hoogte=4.0, cel_min=6.0, tussen=4.0):
        """De hardlopers met een lang turfvak achter de naam: een leeg vak dat doorloopt tot de rand van de kolom. Er
        staan geen streepjes in: je turft zelf zoals je dat gewend bent."""
        per_kol = MAX_HARDLOPERS // kolommen
        kol_b = (breedte - tussen * (kolommen - 1)) / kolommen
        maten = self._maten(maat, kol_b - 2 * cel_min - 2.0)  # het vak houdt minstens 2 x cel_min over
        vak_b = kol_b - self._langste(maten) - 2.0  # het vak vult de ruimte tot de kolomrand
        for i, (naam, m) in enumerate(zip(self.hardlopers, maten)):
            cx = x + (i // per_kol) * (kol_b + tussen)
            cy = y_eerste + (i % per_kol) * rij_h
            self.pdf.set_font("Helvetica", "", m)
            self.pdf.set_text_color(*ZWART)
            self.pdf.text(cx, cy, naam)
            bx, by = cx + kol_b - vak_b, cy + 0.7 - hoogte
            self.pdf.set_draw_color(*LIJN)
            self.pdf.set_line_width(0.25)
            self.pdf.rect(bx, by, vak_b, hoogte)

    # ---------- de ontwerpen ----------

    def kaart_a(self, x, y, w, h):
        p = 4.5
        b = w - 2 * p
        self.veld("Naam", x + p, x + p + b * 0.58, y + 8.0)
        self.veld("Team", x + p + b * 0.63, x + w - p, y + 8.0)
        self.dubbele_lijn(x + p, x + w - p, y + 10.4)
        self.hardlopers_turf(x + p, y + 17.8, b, 6.2, 1, 6.4, 5.0)
        for k in range(4):
            self.stippel(x + p, x + w - p, y + 43.4 + k * 5.6)

    def kaart_b(self, x, y, w, h):
        pdf = self.pdf
        pdf.set_fill_color(*self.blauw)
        pdf.rect(x + 0.6, y, w - 1.2, 6.0, style="F")  # smaller dan het kaartje: de snijlijn blijft zichtbaar
        if LOGO_PAD.exists():
            pdf.image(str(LOGO_PAD), x=x + 2.0, y=y + 0.7, h=4.6)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*self.geel)
        pdf.text(x + 7.4, y + 4.1, "BLAUW-GEEL")
        pdf.set_font("Helvetica", "", 5.6)
        pdf.set_text_color(255, 255, 255)
        pdf.text(x + w - 2.0 - pdf.get_string_width("kantine"), y + 4.0, "kantine")
        p = 3.5
        b = w - 2 * p
        self.veld("Naam", x + p, x + p + b * 0.56, y + 11.8, 6)
        self.veld("Team", x + p + b * 0.61, x + w - p, y + 11.8, 6)
        self.dubbele_lijn(x + p, x + w - p, y + 13.8)
        self.hardlopers_turf(x + p, y + 19.8, b, 5.3, 1, 5.8, 4.3)
        for k in range(3):
            self.stippel(x + p, x + w - p, y + 41.4 + k * 4.8)

    def kaart_c(self, x, y, w, h):
        p = 3.2
        b = w - 2 * p
        self.veld("Naam", x + p, x + w - p, y + 7.0)
        self.veld("Team", x + p, x + w - p, y + 13.4)
        self.dubbele_lijn(x + p, x + w - p, y + 16.0)
        self.hardlopers_gestapeld(x + p, y + 23.2, b, 9.6, 5.2, 6.4)
        for k in range(4):
            self.stippel(x + p, x + w - p, y + 63.4 + k * 5.0)

    def kaart_d(self, x, y, w, h):
        p = 3.6
        b = w - 2 * p
        self.veld("Naam", x + p, x + p + b * 0.58, y + 6.6)
        self.veld("Team", x + p + b * 0.63, x + w - p, y + 6.6)
        self.dubbele_lijn(x + p, x + w - p, y + 8.6)
        self.hardlopers_turf(x + p, y + 17.0, b, 6.0, 2, 6.0, 5.2)
        for k in range(4):
            self.stippel(x + p, x + w - p, y + 30.6 + k * 5.8)

    def kaart_d2(self, x, y, w, h):
        p = 3.6
        b = w - 2 * p
        self.veld("Naam", x + p, x + p + b * 0.58, y + 6.4)
        self.veld("Team", x + p + b * 0.63, x + w - p, y + 6.4)
        self.dubbele_lijn(x + p, x + w - p, y + 8.4)
        self.hardlopers_turf(x + p, y + 16.5, b, 7.2, 1, 6.8, 5.6)
        for k in range(3):
            self.stippel(x + p, x + w - p, y + 45.4 + k * 5.4)

    # ---------- een vel ----------

    def vel(self, optie):
        """Een A4 vol kaartjes van dit ontwerp, met snijlijntjes."""
        pdf = self.pdf
        pdf.add_page()
        w, h, kol, rij = optie.breedte, optie.hoogte, optie.kolommen, optie.rijen
        x0, y0 = (210 - kol * w) / 2, (297 - rij * h) / 2
        pdf.set_draw_color(*GRIJS)
        pdf.set_line_width(0.15)
        pdf.set_dash_pattern(dash=1.0, gap=1.2)
        for i in range(kol + 1):
            pdf.line(x0 + i * w, y0 - 3, x0 + i * w, y0 + rij * h + 3)
        for j in range(rij + 1):
            pdf.line(x0 - 3, y0 + j * h, x0 + kol * w + 3, y0 + j * h)
        pdf.set_dash_pattern()
        teken = getattr(self, "kaart_" + optie.sleutel.lower())
        for r in range(rij):
            for c in range(kol):
                teken(x0 + c * w, y0 + r * h, w, h)
        pdf.set_font("Helvetica", "", 6)
        pdf.set_text_color(*GRIJS)
        pdf.text(
            10, 293.5,
            f"Optie {optie.sleutel}: {kol * rij} kaartjes van {w} x {h} mm - print op 100% (niet 'passend maken'), "
            "knip langs de stippellijnen",
        )


def _nieuw():
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margin(0)
    return pdf


def kaartjes_pdf(optie, hardlopers, vellen=1, zwartwit=False):
    """De kaartjes van 1 ontwerp (sleutel uit OPTIES), 'vellen' keer dezelfde A4, als pdf-bytes."""
    optie = OPTIE_PER_SLEUTEL.get(optie) or OPTIE_PER_SLEUTEL[STANDAARD_OPTIE]
    pdf = _nieuw()
    tekenaar = _Tekenaar(pdf, hardlopers, zwartwit)
    for _ in range(max(1, int(vellen))):
        tekenaar.vel(optie)
    return bytes(pdf.output())


def kaartjes_overzicht_pdf(hardlopers, zwartwit=False):
    """Een pdf met 1 pagina per ontwerp, om ze naast elkaar te kunnen vergelijken."""
    pdf = _nieuw()
    tekenaar = _Tekenaar(pdf, hardlopers, zwartwit)
    for optie in OPTIES:
        tekenaar.vel(optie)
    return bytes(pdf.output())
