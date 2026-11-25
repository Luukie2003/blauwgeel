"""PDF van de merkanalyse (merkanalyse.py): intern (met inkoop, marge en gesprekspunten), of om te laten zien: alleen wat er
van dit merk verkocht wordt en hoe de leveringen liepen. Daar staat bewust niet in hoe groot het merk bij ons is en wat andere
merken doen: dat verzwakt een onderhandeling."""

from pdf.basis import KLEUR_GRIJS, KLEUR_TEKST, LETTER, Rapport, _datum_nl, _euro, _kort

MAANDEN = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def _dag(datum):
    return f"{datum[8:10]}-{datum[5:7]}-{datum[:4]}"


def maand_naam(sleutel):
    return f"{MAANDEN[int(sleutel[5:7]) - 1]} {sleutel[:4]}"


def _g(x, d=0, achter=""):
    return "-" if x is None else f"{x:.{d}f}".replace(".", ",") + achter


def _tekst(pdf, tekst, vet=False, grijs=False):
    pdf.set_font(LETTER, "B" if vet else "", 10 if not grijs else 8.5)
    pdf.set_text_color(*(KLEUR_GRIJS if grijs else KLEUR_TEKST))
    pdf.multi_cell(0, 5 if not grijs else 4.4, tekst, align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*KLEUR_TEKST)


def _tabel(pdf, kolommen, rijen):
    pdf.kop_rij(kolommen)
    for i, rij in enumerate(rijen):
        pdf.data_rij([(_kort(pdf, str(w), b), b, u) for w, (_, b, u) in zip(rij, kolommen)], zebra=i % 2 == 1)


def merkanalyse_pdf(a, deelbaar=False, vragen=()):
    t = a["totaal"]
    laatste = f", laatste telling {_datum_nl(a['laatste_telling'])}" if a["laatste_telling"] else ""
    pdf = Rapport(f"Merkanalyse {a['merk']}", f"De laatste {a['weken']} weken{laatste}" + ("" if deelbaar else ". Intern: met inkoop en marge."))
    pdf.statregel("Verkocht", f"{t['verkocht']} stuks" + (f" ({_g(t['per_week'])} per week)" if t["per_week"] else ""))
    if t["aandeel_categorie"] and not deelbaar:
        pdf.statregel(f"Aandeel in de omzet van {' en '.join(a['categorieen'])}", _g(t["aandeel_categorie"], 0, "%"))
    if not deelbaar:
        pdf.statregel("Omzet", _euro(t["omzet"]) + (f" ({_g(t['aandeel'])}% van alles, nummer {t['plek']} van de merken)" if t["aandeel"] and t["plek"] else ""))
        if t["winst"] is not None:
            pdf.statregel("Brutowinst", f"{_euro(t['winst'])} ({_g(t['marge_pct'])}% marge)")
        pdf.statregel("Ingekocht", f"{_euro(t['inkoop'])} ({t['inkoop_stuks']} stuks)")
        pdf.statregel("Voorraad nu", f"{t['voorraad']} stuks ({_euro(t['voorraad_waarde'])})" + (f", {t['onderweg']} onderweg" if t["onderweg"] else ""))

    if a["punten"] and not deelbaar:
        pdf.sectie("Gesprekspunten")
        for p in a["punten"]:
            _tekst(pdf, p["titel"], vet=True)
            _tekst(pdf, p["tekst"])
            pdf.ln(1.5)

    if vragen and not deelbaar:
        pdf.sectie("Vragen om te stellen")
        for vraag in vragen:
            _tekst(pdf, f"- {vraag}")
    if not deelbaar:
        pdf.add_page()  # op de eerste pagina het gesprek, daarna de cijfers

    pdf.sectie("Per product")
    if deelbaar:
        _tabel(pdf, [("Product", 62, "L"), ("Verkocht", 26, "R"), ("Per week", 24, "R"), ("Aandeel", 24, "R"), ("Eerst /wk", 27, "R"), ("Nu /wk", 27, "R")],
               [(p["kort"], p["verkocht"], _g(p["per_week"], 1), _g(p["aandeel"], 0, "%"), _g(p["voor"], 1), _g(p["na"], 1)) for p in a["producten"]])
    else:
        _tabel(pdf, [("Product", 40, "L"), ("Verkocht", 21, "R"), ("Per week", 21, "R"), ("Eerst/nu", 25, "R"), ("Omzet", 25, "R"), ("Marge", 17, "R"), ("Ligt er", 19, "R"), ("Weken", 22, "R")],
               [(p["kort"], p["verkocht"], _g(p["per_week"], 1), f"{_g(p['voor'])} / {_g(p['na'])}", _euro(p["omzet"]), _g(p["marge_pct"], 0, "%"), p["voorraad"], _g(p["weken_voorraad"] if p["voorraad"] else None, 1)) for p in a["producten"]])
    pdf.ln(1)
    uitleg = "Verkocht volgens de tellingen, zonder telfouten. Eerst / nu: per week in de eerste en de tweede helft van de periode."
    _tekst(pdf, uitleg if deelbaar else uitleg + " Btw en statiegeld zijn in de marge niet meegenomen.", grijs=True)

    if a["per_maand"] and not deelbaar:
        _tekst(pdf, "Per maand: " + ", ".join(f"{maand_naam(m['maand'])} {m['totaal']}" for m in a["per_maand"]) + ".", grijs=True)
    elif a["per_maand"]:
        pdf.sectie("Per maand")
        _tabel(pdf, [("Maand", 60, "L"), ("Verkocht", 40, "R")], [(maand_naam(m["maand"]), m["totaal"]) for m in a["per_maand"]])
    if not deelbaar:
        v = a["volume"]
        if v["scenario"]:
            pdf.sectie("Wat een betere afspraak scheelt")
            _tekst(pdf, f"In dit tempo ongeveer {_g(v['dozen'])} dozen van {v['doos']} per seizoen van {a['seizoen_weken']} weken, voor {_euro(v['doosprijs'])} per doos: {_euro(v['inkoop'])}.")
            pdf.ln(1)
            _tabel(pdf, [("Afspraak", 110, "L"), ("Scheelt per seizoen", 50, "R")], [(s["wat"], _euro(s["scheelt"])) for s in v["scenario"]])

    if a["andere"] and not deelbaar:
        pdf.sectie(f"De rest van {' en '.join(a['categorieen'])}")
        _tabel(pdf, [("Product", 70, "L"), ("Verkocht", 30, "R"), ("Per week", 30, "R"), ("Omzet", 30, "R"), ("Marge", 30, "R")],
               [(r["naam"], r["verkocht"], _g(r["per_week"], 1), _euro(r["omzet"]), _g(r["marge_pct"], 0, "%")) for r in a["andere"]])
    if a["afwijkend"]:
        pdf.sectie(f"Leveringen die afweken ({len(a['leveringen']) - len(a['afwijkend'])} van de {len(a['leveringen'])} klopten)")
        _tabel(pdf, [("Datum", 25, "L"), ("Product", 55, "L"), ("Besteld", 25, "R"), ("Geleverd", 25, "R"), ("Verschil", 25, "R"), ("Alsnog", 35, "R")],
               [(_dag(f["datum"]), f["naam"], f["besteld"], f["geleverd"], f"{f['verschil']:+d}", f"{f['nagekomen']['aantal']} los" if f["nagekomen"] else "") for f in a["afwijkend"]])

    return bytes(pdf.output())
