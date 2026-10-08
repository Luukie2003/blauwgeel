"""PDF's over voorraad: bestellijst en voorraadoverzicht."""

from pdf.basis import Rapport, _euro, _kort


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
    i = 0
    for c in gegevens["categorie_lijst"]:
        pdf.data_rij(
            [
                (_kort(pdf, c["naam"], 70), 70, "L"),
                (c["aantal"], 30, "R"),
                (_euro(c["waarde"]), 40, "R"),
                (f"{c['percentage']:.1f}%", 30, "R"),
            ],
            zebra=i % 2 == 1,
        )
        i += 1
        for s in c["subcategorieen"]:
            pdf.data_rij(
                [
                    (_kort(pdf, f"   {s['naam']}", 70), 70, "L"),
                    (s["aantal"], 30, "R"),
                    (_euro(s["waarde"]), 40, "R"),
                    (f"{s['percentage']:.1f}%", 30, "R"),
                ],
                zebra=i % 2 == 1,
            )
            i += 1

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
