"""PDF's over verkoop: verkooprapport per telling of per periode."""

from pdf.basis import KLEUR_BLAUW, Rapport, _euro, _kort


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
        categorie_tekst = r["categorie"]
        if r["subcategorie"]:
            categorie_tekst = f"{categorie_tekst} / {r['subcategorie']}"
        pdf.data_rij(
            [
                (_kort(pdf, r["product_naam"], 50), 50, "L"),
                (_kort(pdf, categorie_tekst, 32), 32, "L"),
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
