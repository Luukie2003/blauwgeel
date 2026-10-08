from datetime import date, datetime, timedelta

import pytest

from seizoensrapport import bereken_seizoensrapport, seizoen_einde, seizoen_start

NU = datetime(2026, 10, 8, 12, 0)


def _product(db, naam, prijs):
    cur = db.execute(
        "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs) "
        "VALUES (?, 'Bier', 'stuks', 100, 0, ?)",
        (naam, prijs),
    )
    db.commit()
    return cur.lastrowid


def _weekelijkse_tellingen(db, producten, van=date(2025, 8, 2), tot=date(2026, 10, 3)):
    """Elke zaterdag om 23:00 een telling; elke periode wordt per product 'verkocht'
    verkocht. Geeft de totale verkoop in euro's terug (de eerste telling is de nulmeting)."""
    db.execute("UPDATE instellingen SET verkoopdagen = '0,1,2,3,4,5,6' WHERE id = 1")
    totaal = 0.0
    dag = van
    eerste = True
    while dag <= tot:
        cur = db.execute(
            "INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (f"{dag.isoformat()} 23:00",)
        )
        for pid, (verkocht, prijs) in producten.items():
            v = 0 if eerste else verkocht
            totaal += v * prijs
            db.execute(
                """INSERT INTO telling_regels
                   (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
                   VALUES (?, ?, ?, 50, ?, ?)""",
                (cur.lastrowid, pid, 50 + v, v, prijs),
            )
        eerste = False
        dag += timedelta(days=7)
    db.commit()
    return totaal


def test_seizoensgrenzen():
    assert seizoen_start("2025-2026") == date(2025, 7, 1)
    assert seizoen_einde("2025-2026") == date(2026, 6, 30)


def test_zonder_tellingen_geen_rapport(db):
    assert bereken_seizoensrapport(db, NU) is None


def test_omzet_per_seizoen_klopt_met_de_tellingen(db):
    pils = _product(db, "Pils", 2.0)
    cola = _product(db, "Cola", 1.5)
    totaal = _weekelijkse_tellingen(db, {pils: (70, 2.0), cola: (30, 1.5)})

    rapport = bereken_seizoensrapport(db, NU)

    assert [s["seizoen"] for s in rapport["seizoenen"]] == ["2025-2026", "2026-2027"]
    assert rapport["huidig"] == "2026-2027"
    assert sum(s["omzet"] for s in rapport["seizoenen"]) == pytest.approx(totaal)
    for s in rapport["seizoenen"]:
        assert sum(s["maanden"].values()) == pytest.approx(s["omzet"])
        assert s["verkoopdagen"] > 0
        assert s["per_verkoopdag"] == pytest.approx(s["omzet"] / s["verkoopdagen"])


def test_tot_dezelfde_datum_vergelijkt_eerlijk(db):
    pils = _product(db, "Pils", 2.0)
    # Begin vóór 1 juli, zodat beide seizoenen vanaf het begin gedekt zijn.
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2025, 6, 28), tot=date(2026, 10, 3))

    rapport = bereken_seizoensrapport(db, NU)
    vorig, huidig = rapport["seizoenen"][-2:]

    # Het huidige seizoen is pas 99 dagen oud: zijn omzet tot nu is zijn hele omzet,
    # en het vorige seizoen moet tot dezelfde dag worden afgekapt.
    assert huidig["tot_nu"] == pytest.approx(huidig["omzet"])
    assert 0 < vorig["tot_nu"] < vorig["omzet"]
    # Zelfde verkoop per week -> ongeveer even veel omzet tot dezelfde datum.
    assert abs(vorig["tot_nu_verschil_met_huidig"]) < 10
    assert huidig["tot_nu_verschil_met_huidig"] is None


def test_top_producten_gesorteerd_op_omzet(db):
    pils = _product(db, "Pils", 2.0)
    chips = _product(db, "Chips", 1.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0), chips: (10, 1.0)})

    top = bereken_seizoensrapport(db, NU)["seizoenen"][-1]["top_producten"]

    assert [p["naam"] for p in top] == ["Pils", "Chips"]
    assert top[0]["omzet"] > top[1]["omzet"]


def test_seizoen_met_late_start_is_niet_volledig(db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2025, 10, 4))

    eerste = bereken_seizoensrapport(db, NU)["seizoenen"][0]

    assert eerste["gegevens_vanaf"] == date(2025, 10, 4)
    assert not eerste["volledig"]


def test_thuiswedstrijden_worden_per_seizoen_geteld(db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)})
    for datum, afgelast in [("2025-09-06", 0), ("2025-09-13", 0), ("2026-09-05", 0), ("2026-09-12", 1)]:
        db.execute(
            "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, afgelast) VALUES ('ZA 1', ?, 'x', 1, ?)",
            (datum, afgelast),
        )
    db.commit()

    vorig, huidig = bereken_seizoensrapport(db, NU)["seizoenen"]

    assert vorig["thuiswedstrijden"] == 2
    assert huidig["thuiswedstrijden"] == 1  # de afgelaste telt niet mee


# ---------- Pagina's ----------


def test_pagina_zonder_tellingen_legt_uit_dat_er_niets_is(ingelogde_client):
    resp = ingelogde_client.get("/rapporten/seizoenen")
    assert resp.status_code == 200
    assert b"nog geen tellingen" in resp.data


def test_pagina_csv_en_pdf_met_tellingen(ingelogde_client, db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2025, 6, 28), tot=date(2026, 10, 3))

    pagina = ingelogde_client.get("/rapporten/seizoenen")
    assert pagina.status_code == 200
    assert b"2025-2026" in pagina.data and b"Omzet per maand" in pagina.data

    csv = ingelogde_client.get("/rapporten/seizoenen/csv")
    assert csv.status_code == 200
    tekst = csv.data.decode("utf-8-sig")
    assert tekst.startswith("Seizoen;Maand;Omzet")
    assert "2025-2026;Totaal;" in tekst

    pdf = ingelogde_client.get("/rapporten/seizoenen/pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_pdf_zonder_tellingen_toont_de_pagina(ingelogde_client):
    resp = ingelogde_client.get("/rapporten/seizoenen/pdf")
    assert resp.status_code == 200
    assert not resp.data.startswith(b"%PDF")
