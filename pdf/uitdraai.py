"""De compacte uitdraai: kas, kluis, voorraad, bestellijst, prognose en seizoenen."""

from pdf.basis import KLEUR_BLAUW, KLEUR_GRIJS, KLEUR_KOPRIJ, Rapport, _datum_nl, _euro, _kort
from pdf.seizoen import seizoen_samenvatting_tabel


UITDRAAI_KOLOM_BREEDTE = 92


UITDRAAI_KOLOM_X = (10, 108)


UITDRAAI_RIJ_HOOGTE = 4.6


def _uitdraai_geldblok(pdf, x, y, titel, gegevens):
    """Een compact kas- of kluisverslag in een kolom van 92 mm breed:
    de huidige stand, de laatste telling en de laatste geldbewegingen.
    Geeft de y-positie onder het blok terug."""
    breedte = UITDRAAI_KOLOM_BREEDTE
    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*KLEUR_BLAUW)
    pdf.cell(breedte, 6, titel, new_x="LEFT", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    def regel(label, waarde, vet=False, kleur=None):
        pdf.set_x(x)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(48, 5, label)
        pdf.set_font("Helvetica", "B" if vet else "", 9)
        if kleur:
            pdf.set_text_color(*kleur)
        pdf.cell(breedte - 48, 5, _kort(pdf, str(waarde), breedte - 48), align="R", new_x="LEFT", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    pdf.set_x(x)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(breedte, 8, f"Stand: {_euro(gegevens['stand'])}", new_x="LEFT", new_y="NEXT")

    telling = gegevens["laatste_telling"]
    if telling:
        pdf.set_x(x)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*KLEUR_GRIJS)
        pdf.cell(breedte, 5, f"Laatste telling - {_datum_nl(telling['datum'])}", new_x="LEFT", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        regel("Geteld door:", telling["naam"] or "-")
        regel("Verwacht:", _euro(telling["verwacht"]))
        regel("Geteld:", _euro(telling["geteld"]))
        verschil = telling["verschil"]
        if verschil > 0:
            regel("Overschot:", _euro(verschil), vet=True)
        elif verschil < 0:
            regel("Tekort:", _euro(-verschil), vet=True, kleur=(180, 30, 30))
        else:
            regel("Verschil:", _euro(0), vet=True)
        regel("Goedgekeurd door:", telling["goedgekeurd_door"] or "-")
    else:
        pdf.set_x(x)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(breedte, 5, "Nog geen afgesloten telling.", new_x="LEFT", new_y="NEXT")

    if gegevens["open_tellingen"]:
        pdf.set_x(x)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(180, 30, 30)
        n = gegevens["open_tellingen"]
        pdf.cell(breedte, 5, f"Let op: {n} telling{'en' if n != 1 else ''} nog niet goedgekeurd.", new_x="LEFT", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    pdf.ln(1)
    pdf.set_x(x)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*KLEUR_GRIJS)
    pdf.cell(breedte, 5, "Laatste geldbewegingen", new_x="LEFT", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    if gegevens["mutaties"]:
        for m in gegevens["mutaties"]:
            pdf.set_x(x)
            pdf.set_font("Helvetica", "", 8)
            bedrag = m["bedrag"]
            teken = "+" if bedrag >= 0 else "-"
            pdf.cell(22, 4.6, _datum_nl(m["datum"])[:10])
            pdf.cell(44, 4.6, _kort(pdf, m["omschrijving"], 44))
            pdf.cell(breedte - 66, 4.6, f"{teken} {_euro(abs(bedrag))}", align="R", new_x="LEFT", new_y="NEXT")
    else:
        pdf.set_x(x)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(breedte, 4.6, "Geen bewegingen.", new_x="LEFT", new_y="NEXT")
    return pdf.get_y()


def _uitdraai_voorraadrijen(voorraad):
    rijen = []
    for categorie in voorraad["categorieen"]:
        rijen.append(("kop", categorie["naam"]))
        rijen.extend(("product", p) for p in categorie["producten"])
    return rijen


def _ruimte_voor(pdf, mm):
    """Begin een onderdeel op een nieuwe pagina als er niet genoeg plek meer is
    voor zijn kop en de eerste regels (anders blijft de kop alleen achter)."""
    if pdf.get_y() + mm > pdf.page_break_trigger:
        pdf.add_page()


def _uitdraai_bestellijst(pdf, bestellijst):
    _ruimte_voor(pdf, 40)
    pdf.set_x(10)
    pdf.sectie("Bestellijst")
    if not bestellijst["nu"] and not bestellijst["tekorten"]:
        pdf.leeg_bericht("Niets te bestellen - alle voorraad zit boven het minimum.")
        return
    if bestellijst["nu"]:
        pdf.kop_rij([("Nu bestellen (onder het minimum)", 75, "L"), ("Voorraad", 30, "R"), ("Minimum", 30, "R"), ("Bestellen", 55, "R")])
        for i, p in enumerate(bestellijst["nu"]):
            pdf.data_rij(
                [
                    (_kort(pdf, p["naam"], 75), 75, "L"),
                    (p["voorraad"], 30, "R"),
                    (p["minimum"], 30, "R"),
                    (_kort(pdf, p["bestel"], 55), 55, "R"),
                ],
                zebra=i % 2 == 1,
            )
    if bestellijst["tekorten"]:
        pdf.ln(3)
        pdf.kop_rij(
            [(f"Verwacht tekort binnen {bestellijst['dagen']} dagen", 75, "L"), ("Voorraad", 30, "R"), ("Kans", 30, "R"), ("Bestellen", 55, "R")]
        )
        for i, p in enumerate(bestellijst["tekorten"]):
            pdf.data_rij(
                [
                    (_kort(pdf, p["naam"], 75), 75, "L"),
                    (p["voorraad"], 30, "R"),
                    (p["kans"], 30, "R"),
                    (_kort(pdf, p["bestel"], 55), 55, "R"),
                ],
                zebra=i % 2 == 1,
            )


def _uitdraai_prognose(pdf, prognose):
    _ruimte_voor(pdf, 95 if prognose["beschikbaar"] else 25)
    pdf.set_x(10)
    pdf.sectie("Prognose komende dagen")
    if not prognose["beschikbaar"]:
        pdf.leeg_bericht(prognose["reden"])
        return
    pdf.statregel(
        f"Verwachte omzet ({prognose['dagen_aantal']} dagen):",
        f"{_euro(prognose['omzet'])}  (waarschijnlijk {_euro(prognose['laag'])} - {_euro(prognose['hoog'])})",
    )
    pdf.statregel("Betrouwbaarheid van de voorspelling:", prognose["betrouwbaarheid"])
    pdf.ln(1)
    pdf.kop_rij([("Dag", 55, "L"), ("Verwachte omzet", 45, "R"), ("Bijzonderheden", 90, "L")])
    for i, d in enumerate(prognose["dagen"]):
        pdf.data_rij(
            [
                (d["dag"], 55, "L"),
                (_euro(d["omzet"]) if d["open"] else "dicht", 45, "R"),
                (d["opmerking"], 90, "L"),
            ],
            zebra=i % 2 == 1,
        )
    if prognose["risico"]:
        pdf.ln(3)
        pdf.kop_rij([("Kans dat het opraakt", 100, "L"), ("Voorraad nu", 45, "R"), ("Kans", 45, "R")])
        for i, p in enumerate(prognose["risico"]):
            pdf.data_rij(
                [
                    (_kort(pdf, p["naam"], 100), 100, "L"),
                    (p["voorraad"], 45, "R"),
                    (p["kans"], 45, "R"),
                ],
                zebra=i % 2 == 1,
            )


def compacte_uitdraai_pdf(
    kas=None, kluis=None, voorraad=None, moment=None, bestellijst=None, prognose=None, seizoenen=None
):
    """Compacte A4-uitdraai met (naar keuze) het kasverslag, het kluisverslag
    en de huidige voorraadstand. Kas en kluis staan naast elkaar, de voorraad
    loopt in twee kolommen daaronder, zodat het bij een normale kantine op
    één pagina past. Daarna, als gekozen, de bestellijst, de prognose voor de
    komende dagen en de omzet per seizoen (die vullen de rest van de pagina's)."""
    pdf = Rapport("Compacte uitdraai", f"Stand per {_datum_nl(moment)}" if moment else "")

    geldblokken = [(titel, g) for titel, g in (("Kasverslag", kas), ("Kluisverslag", kluis)) if g]
    if geldblokken:
        y0 = pdf.get_y()
        onderkant = y0
        for (titel, gegevens), x in zip(geldblokken, UITDRAAI_KOLOM_X):
            onderkant = max(onderkant, _uitdraai_geldblok(pdf, x, y0, titel, gegevens))
        pdf.set_xy(10, onderkant + 3)

    if voorraad:
        pdf.set_x(10)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*KLEUR_BLAUW)
        pdf.cell(
            0,
            6,
            f"Voorraad: {voorraad['aantal_producten']} producten, {voorraad['aantal_laag']} te laag (rood), "
            f"waarde {_euro(voorraad['totale_waarde'])}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_text_color(0, 0, 0)

        rijen = _uitdraai_voorraadrijen(voorraad)
        hoogte = UITDRAAI_RIJ_HOOGTE
        index = 0
        while index < len(rijen):
            y_start = pdf.get_y() + 1
            per_kolom = max(1, int((pdf.page_break_trigger - y_start) // hoogte))
            if per_kolom < 6 and index:
                pdf.add_page()
                continue
            # Past de rest op deze pagina, verdeel dan gelijk over de twee kolommen
            # in plaats van de eerste helemaal vol te zetten: dat laat ruimte voor
            # wat eronder komt (bestellijst, prognose...).
            per_kolom = min(per_kolom, -(-(len(rijen) - index) // 2) + 1)
            stuk = rijen[index : index + 2 * per_kolom]
            # Een categoriekop mag niet als laatste regel van een kolom
            # blijven hangen: schuif 'm dan mee naar de volgende kolom.
            if len(stuk) > per_kolom:
                knip = per_kolom
                if stuk[knip - 1][0] == "kop":
                    knip -= 1
                kolommen = [stuk[:knip], stuk[knip:]]
                verbruikt = knip + len(kolommen[1])
            else:
                kolommen = [stuk, []]
                verbruikt = len(stuk)
            for kolom_rijen, x in zip(kolommen, UITDRAAI_KOLOM_X):
                y = y_start
                for soort, inhoud in kolom_rijen:
                    pdf.set_xy(x, y)
                    if soort == "kop":
                        pdf.set_font("Helvetica", "B", 8.5)
                        pdf.set_fill_color(*KLEUR_KOPRIJ)
                        pdf.cell(UITDRAAI_KOLOM_BREEDTE, hoogte, inhoud, fill=True)
                    else:
                        if inhoud["laag"]:
                            pdf.set_font("Helvetica", "B", 8)
                            pdf.set_text_color(180, 30, 30)
                        else:
                            pdf.set_font("Helvetica", "", 8)
                        pdf.cell(60, hoogte, _kort(pdf, inhoud["naam"], 60))
                        pdf.cell(
                            UITDRAAI_KOLOM_BREEDTE - 60,
                            hoogte,
                            f"{inhoud['voorraad']} / min {inhoud['minimum']}",
                            align="R",
                        )
                        pdf.set_text_color(0, 0, 0)
                    y += hoogte
            index += verbruikt
            pdf.set_y(y_start + max(len(k) for k in kolommen) * hoogte)
            if index < len(rijen):
                pdf.add_page()

    if bestellijst:
        _uitdraai_bestellijst(pdf, bestellijst)
    if prognose:
        _uitdraai_prognose(pdf, prognose)
    if seizoenen:
        _ruimte_voor(pdf, 80)
        pdf.set_x(10)
        pdf.sectie("Omzet per seizoen")
        if seizoenen["rapport"] is None:
            pdf.leeg_bericht("Er zijn nog geen tellingen, dus er is nog niets te vergelijken.")
        else:
            seizoen_samenvatting_tabel(pdf, seizoenen["rapport"], max_seizoenen=4)

    return bytes(pdf.output())
