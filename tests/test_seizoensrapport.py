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


# ---------- Met de hand ingevulde maandtotalen ----------

from routes.seizoensrapport import lees_bedrag  # noqa: E402
from conftest import stel_csrf_token_in as _csrf  # noqa: E402


def _historie(db, seizoen, **per_maand):
    for maand, bedrag in per_maand.items():
        db.execute(
            "INSERT INTO omzet_historie (seizoen, maand, omzet, ingevoerd_op) VALUES (?, ?, ?, '2026-10-09 10:00')",
            (seizoen, int(maand[1:]), bedrag),
        )
    db.commit()


def test_bedragen_lezen_zoals_mensen_ze_typen():
    assert lees_bedrag("1.234,56") == 1234.56
    assert lees_bedrag("1234,5") == 1234.5
    assert lees_bedrag("1234.56") == 1234.56
    assert lees_bedrag("€ 900") == 900
    assert lees_bedrag("  ") is None and lees_bedrag("") is None and lees_bedrag(None) is None
    for fout in ("abc", "12,345,6", "-5", "2000000", "1e5"):
        with pytest.raises(ValueError):
            lees_bedrag(fout)


def test_ingevulde_maanden_vullen_een_seizoen_zonder_tellingen(db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 8, 21), tot=date(2026, 10, 3))
    _historie(db, "2025-2026", m7=1000, m8=1500, m9=2000)

    rapport = bereken_seizoensrapport(db, NU)

    vorig = next(s for s in rapport["seizoenen"] if s["seizoen"] == "2025-2026")
    assert vorig["omzet"] == 4500
    assert vorig["maanden"][8] == 1500 and vorig["handmatige_maanden"] == {7, 8, 9}
    assert vorig["alleen_ingevuld"] and vorig["verkoopdagen"] == 0
    assert vorig["volledig"]  # de tellingen beginnen pas in een later seizoen: er ontbreekt niets "vóór" de eerste telling
    assert rapport["heeft_ingevulde_maanden"]


def test_tellingen_gaan_voor_op_ingevulde_maanden(db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 6, 27), tot=date(2026, 10, 3))
    rapport_zonder = bereken_seizoensrapport(db, NU)
    september = next(s for s in rapport_zonder["seizoenen"] if s["seizoen"] == "2026-2027")["maanden"][9]
    assert september > 0

    _historie(db, "2026-2027", m9=99999)  # september is volledig door tellingen gedekt
    rapport = bereken_seizoensrapport(db, NU)

    huidig = next(s for s in rapport["seizoenen"] if s["seizoen"] == "2026-2027")
    assert huidig["maanden"][9] == pytest.approx(september)
    assert 9 not in huidig["handmatige_maanden"]


def test_een_gedeeltelijk_gedekte_eerste_maand_wordt_aangevuld(db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 8, 21), tot=date(2026, 10, 3))
    zonder = bereken_seizoensrapport(db, NU)
    augustus = next(s for s in zonder["seizoenen"] if s["seizoen"] == "2026-2027")["maanden"][8]
    assert 0 < augustus < 800

    _historie(db, "2026-2027", m7=700, m8=800)
    huidig = next(s for s in bereken_seizoensrapport(db, NU)["seizoenen"] if s["seizoen"] == "2026-2027")

    assert huidig["maanden"][7] == 700 and huidig["maanden"][8] == 800
    assert huidig["handmatige_maanden"] == {7, 8}
    assert huidig["gegevens_vanaf"] is None  # juli en augustus zijn nu ingevuld


def test_zonder_invullen_blijft_een_late_start_gemarkeerd(db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 8, 21), tot=date(2026, 10, 3))
    huidig = next(s for s in bereken_seizoensrapport(db, NU)["seizoenen"] if s["seizoen"] == "2026-2027")
    assert huidig["gegevens_vanaf"] == date(2026, 8, 21) and not huidig["volledig"]


def test_tot_dezelfde_datum_rekent_een_lopende_maand_naar_rato(db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 8, 21), tot=date(2026, 10, 3))
    _historie(db, "2025-2026", m10=3100, m11=9999)  # peildatum 8 oktober: oktober telt voor 8/31, november niet

    vorig = next(s for s in bereken_seizoensrapport(db, NU)["seizoenen"] if s["seizoen"] == "2025-2026")

    assert vorig["tot_nu"] == pytest.approx(3100 * 8 / 31)
    assert vorig["omzet"] == 3100 + 9999


def test_rapport_bestaat_ook_met_alleen_ingevulde_maanden(db):
    assert bereken_seizoensrapport(db, NU) is None
    _historie(db, "2025-2026", m7=1000)

    rapport = bereken_seizoensrapport(db, NU)

    assert rapport is not None
    assert [s["seizoen"] for s in rapport["seizoenen"]] == ["2025-2026", "2026-2027"]


# ---------- De invulpagina ----------


def _post(client, seizoen="2024-2025", **velden):
    data = {"csrf_token": _csrf(client), "seizoen": seizoen}
    data.update({f"maand_{m[1:]}": waarde for m, waarde in velden.items()})
    return client.post("/rapporten/seizoenen/invullen", data=data)


def test_invulpagina_toont_het_formulier(ingelogde_client):
    pagina = ingelogde_client.get("/rapporten/seizoenen/invullen?seizoen=2024-2025")
    assert pagina.status_code == 200
    assert b"Seizoen 2024-2025" in pagina.data and b'name="maand_7"' in pagina.data and b'name="maand_6"' in pagina.data


def test_bedragen_opslaan_overschrijven_en_wissen(ingelogde_client, db):
    resp = _post(ingelogde_client, m7="1.000,50", m8="750", m9="")
    assert resp.status_code == 302
    rijen = {r["maand"]: r["omzet"] for r in db.execute("SELECT * FROM omzet_historie WHERE seizoen = '2024-2025'")}
    assert rijen == {7: 1000.5, 8: 750.0}

    _post(ingelogde_client, m7="2000", m8="")  # m7 overschrijven, m8 wissen
    rijen = {r["maand"]: r["omzet"] for r in db.execute("SELECT * FROM omzet_historie WHERE seizoen = '2024-2025'")}
    assert rijen == {7: 2000.0}

    pagina = ingelogde_client.get("/rapporten/seizoenen/invullen?seizoen=2024-2025").data.decode()
    assert 'value="2000,00"' in pagina


def test_een_ongeldig_bedrag_slaat_niets_op(ingelogde_client, db):
    resp = _post(ingelogde_client, m7="1000", m8="veel")
    assert resp.status_code == 302
    assert db.execute("SELECT COUNT(*) AS n FROM omzet_historie").fetchone()["n"] == 0
    assert "geen geldig bedrag" in ingelogde_client.get(resp.headers["Location"]).data.decode()


def test_invullen_staat_in_het_logboek(ingelogde_client, db):
    _post(ingelogde_client, m7="1000")
    assert db.execute("SELECT COUNT(*) AS n FROM logboek WHERE endpoint = 'seizoensrapport_historie'").fetchone()["n"] == 1


def test_invullen_is_alleen_voor_beheerders(client, db):
    from werkzeug.security import generate_password_hash
    from database import WACHTWOORD_HASH_METHODE

    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) "
        "VALUES ('vrijwilliger', ?, 'vrijwilliger', 'voorraad', '2026-01-01 10:00')",
        (generate_password_hash("geheim123", method=WACHTWOORD_HASH_METHODE),),
    )
    db.commit()
    client.post("/login", data={"naam": "vrijwilliger", "wachtwoord": "geheim123", "csrf_token": _csrf(client)})
    assert client.get("/rapporten/seizoenen/invullen").status_code == 302
    assert _post(client, m7="1000").status_code == 302
    assert db.execute("SELECT COUNT(*) AS n FROM omzet_historie").fetchone()["n"] == 0
    assert b"Eerdere seizoenen invullen" not in client.get("/rapporten/seizoenen").data


def test_rapportpagina_en_pdf_met_ingevulde_maanden(ingelogde_client, db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 8, 21), tot=date(2026, 10, 3))
    _historie(db, "2025-2026", m7=1000, m8=1500)

    pagina = ingelogde_client.get("/rapporten/seizoenen").data.decode()
    assert "met de hand ingevuld" in pagina.lower() and "Eerdere seizoenen invullen" in pagina
    assert ingelogde_client.get("/rapporten/seizoenen/pdf").data.startswith(b"%PDF")
    assert ingelogde_client.get("/rapporten/seizoenen/csv").status_code == 200
