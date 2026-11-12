"""De pdf's in de clubstijl (2.9.0): de Barlow-letter van de site, de kop met de club, de voet met 'pagina 1 van 2', de
tabelkop opnieuw op een volgende pagina, en tekens die niet in de letter zitten (zoals een emoji in een productnaam)."""

from pdf_tekst import pdf_tekst

from pdf import bestellijst_pdf, bestelling_pdf


def _bestelling(namen):
    return {
        "bestelling": {"id": 7, "aangemaakt_op": "2026-11-12 10:00", "besteld_door": "Luuk", "referentie": None},
        "leverancier": {"naam": "Robertus", "klantnummer": "102938", "bestelwijze": "Via de webshop"},
        "regels": [{"naam": naam, "artikelcode": "A1", "eenheden": 2, "besteleenheid": "krat", "stuks": 48,
                    "eenheid": "flesjes", "factor": 24} for naam in namen],
    }


def test_de_letter_de_kop_en_de_voet_van_de_club():
    data = bestelling_pdf(_bestelling(["Hertog Jan"]))
    assert b"/BaseFont /" in data and b"Barlow" in data  # de letter van de site zit erin
    tekst = pdf_tekst(data)
    assert "KANTINE BLAUW-GEEL" in tekst and "sinds 1915 · Coendersborg" in tekst
    assert "Bestelling #7" in tekst and "klantnummer 102938" in tekst
    assert "ARTIKELNUMMER" in tekst  # de kop van de tabel in hoofdletters, zoals op de site
    assert "pagina 1 van" in tekst and "Kantine Beheer  ·  s.v. Blauw-Geel 1915" in tekst


def test_tekens_buiten_de_letter_geven_geen_fout():
    # Met de standaardletters van vroeger gaf een emoji een fout; nu valt hij weg en wordt een pijl '->'.
    tekst = pdf_tekst(bestelling_pdf(_bestelling(["Spa Rood 🍓 → nieuw", "Żubrówka", "Š-test ✓"])))
    assert "Spa Rood  -> nieuw" in tekst and "Zubrówka" in tekst and "S-test v" in tekst


def test_de_tabelkop_staat_op_elke_pagina():
    producten = [{"naam": f"Product {i:02d}", "categorie": "Fris", "voorraad": 0, "min_voorraad": 24, "eenheid": "stuks",
                  "bestel_hoeveelheid": 0, "besteleenheid": "tray", "besteleenheid_factor": 24} for i in range(60)]
    tekst = pdf_tekst(bestellijst_pdf(producten))
    assert tekst.count("AANTAL BESTELLEN") == 2 and "Bestellijst (vervolg)" in tekst
    assert "Product 00" in tekst and "Product 59" in tekst
