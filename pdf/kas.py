"""PDF van een kassatelling."""

from pdf.basis import Rapport, _euro


def kassa_pdf(telling, coupures):
    status = "Goedgekeurd" if telling["afgesloten"] else "Nog open (concept)"
    subtitel = f"{telling['datum']}  -  {status}"
    pdf = Rapport(f"Kassatelling #{telling['id']}", subtitel)

    pdf.sectie("Coupures")
    pdf.kop_rij([("Coupure", 60, "L"), ("Aantal", 40, "R"), ("Subtotaal", 40, "R")])
    for i, (kolom, waarde, label) in enumerate(coupures):
        aantal = telling[kolom]
        pdf.data_rij(
            [
                (label, 60, "L"),
                (aantal, 40, "R"),
                (_euro(aantal * waarde), 40, "R"),
            ],
            zebra=i % 2 == 1,
        )
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 8, "", border=0)
    pdf.cell(40, 8, "Totaal geteld", align="R")
    pdf.cell(40, 8, _euro(telling["geteld_bedrag"]), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.sectie("Berekening")
    pdf.statregel("Contante omzet (volgens PayPal):", _euro(telling["contante_omzet"]))
    pdf.statregel("Verwacht bedrag:", _euro(telling["verwacht_bedrag"]))
    pdf.statregel("Geteld bedrag:", _euro(telling["geteld_bedrag"]))
    if telling["verschil"] > 0:
        verschil_label = "Overschot:"
    elif telling["verschil"] < 0:
        verschil_label = "Tekort:"
    else:
        verschil_label = "Verschil:"
    pdf.statregel(verschil_label, _euro(abs(telling["verschil"])))

    if telling["naam"] or telling["opmerking"] or telling["goedgekeurd_door"]:
        pdf.sectie("Details")
        if telling["naam"]:
            pdf.statregel("Geteld door:", telling["naam"])
        if telling["opmerking"]:
            pdf.statregel("Opmerking (teller):", telling["opmerking"])
        if telling["goedgekeurd_door"]:
            zelf_goedgekeurd = (
                telling["gebruiker_id"] is not None
                and telling["gebruiker_id"] == telling["goedgekeurd_door_id"]
            )
            waarde = telling["goedgekeurd_door"] + (" (zelf goedgekeurd)" if zelf_goedgekeurd else "")
            pdf.statregel("Goedgekeurd door:", waarde)
        if telling["goedgekeurd_op"]:
            pdf.statregel("Goedgekeurd op:", telling["goedgekeurd_op"])
        if telling["goedkeuring_opmerking"]:
            pdf.statregel("Opmerking (goedkeurder):", telling["goedkeuring_opmerking"])

    return bytes(pdf.output())
