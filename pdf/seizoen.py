"""PDF van de omzet per seizoen, en de vergelijkingstabel die de uitdraai ook gebruikt."""

from pdf.basis import KLEUR_GRIJS, Rapport, _euro, _kort


SEIZOEN_PDF_MAX_SEIZOENEN = 5


def _procent(waarde):
    if waarde is None:
        return "-"
    return f"{waarde:+.1f}%".replace(".", ",")


def _seizoen_tabel_kop(pdf, seizoenen, label_breedte=52):
    breedte = (190 - label_breedte) / max(len(seizoenen), 1)
    pdf.kop_rij([("", label_breedte, "L")] + [(s["seizoen"], breedte, "R") for s in seizoenen])
    return breedte


def seizoen_samenvatting_tabel(pdf, rapport, max_seizoenen=SEIZOEN_PDF_MAX_SEIZOENEN):
    """De vergelijkingstabel per seizoen (omzet, vergelijking tot dezelfde datum,
    verkoopdagen...) -- gedeeld door het seizoensrapport en de compacte uitdraai."""
    seizoenen = rapport["seizoenen"][-max_seizoenen:]
    label_breedte = 52
    breedte = _seizoen_tabel_kop(pdf, seizoenen, label_breedte)
    peil = rapport["peildatum"].strftime("%d-%m")
    rijen = [
        ("Omzet", [_euro(s["omzet"]) for s in seizoenen]),
        ("Verschil met vorig seizoen", [_procent(s["verschil_vorig_seizoen"]) for s in seizoenen]),
        (f"Omzet t/m {peil}", [_euro(s["tot_nu"]) for s in seizoenen]),
        (
            f"Dit seizoen t.o.v. t/m {peil}",
            ["-" if s["is_huidig"] else _procent(s["tot_nu_verschil_met_huidig"]) for s in seizoenen],
        ),
        ("Verkoopdagen", [str(s["verkoopdagen"]) for s in seizoenen]),
        ("Gemiddeld per verkoopdag", [_euro(s["per_verkoopdag"]) for s in seizoenen]),
        ("Thuiswedstrijden", [str(s["thuiswedstrijden"]) for s in seizoenen]),
    ]
    for i, (label, waarden) in enumerate(rijen):
        pdf.data_rij(
            [(label, label_breedte, "L")] + [(w, breedte, "R") for w in waarden],
            zebra=i % 2 == 1,
        )
    onvolledig = [s for s in seizoenen if not s["volledig"]]
    if onvolledig:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*KLEUR_GRIJS)
        for s in onvolledig:
            if s["gegevens_vanaf"]:
                tekst = f"{s['seizoen']}: tellingen pas vanaf {s['gegevens_vanaf'].strftime('%d-%m-%Y')}, dus niet het hele seizoen."
            else:
                tekst = f"{s['seizoen']}: tellingen tot {s['gegevens_tot'].strftime('%d-%m-%Y')}."
            pdf.cell(0, 4.5, tekst, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)


def seizoensrapport_pdf(rapport):
    seizoenen = rapport["seizoenen"][-SEIZOEN_PDF_MAX_SEIZOENEN:]
    pdf = Rapport(
        "Omzet per seizoen",
        f"Peildatum {rapport['peildatum'].strftime('%d-%m-%Y')}  -  seizoen = 1 juli t/m 30 juni",
    )

    pdf.sectie("Vergelijking")
    seizoen_samenvatting_tabel(pdf, rapport)

    pdf.sectie("Omzet per maand")
    label_breedte = 52
    breedte = _seizoen_tabel_kop(pdf, seizoenen, label_breedte)
    for i, (maand, naam) in enumerate(rapport["maanden"]):
        pdf.data_rij(
            [(naam.capitalize(), label_breedte, "L")]
            + [(_euro(s["maanden"][maand]) if s["maanden"][maand] else "-", breedte, "R") for s in seizoenen],
            zebra=i % 2 == 1,
        )

    pdf.sectie("Meest verkochte producten per seizoen")
    for s in reversed(seizoenen):
        if not s["top_producten"]:
            continue
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, s["seizoen"], new_x="LMARGIN", new_y="NEXT")
        for i, p in enumerate(s["top_producten"], start=1):
            pdf.data_rij(
                [
                    (f"{i}. {_kort(pdf, p['naam'], 100)}", 110, "L"),
                    (f"{p['aantal']} stuks", 35, "R"),
                    (_euro(p["omzet"]), 45, "R"),
                ],
                zebra=i % 2 == 0,
            )
        pdf.ln(2)

    return bytes(pdf.output())
