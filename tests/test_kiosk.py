from datetime import date

from conftest import stel_csrf_token_in as _csrf
from helpers import voeg_maanden_toe
from test_secties_rechten import _login, _maak_vrijwilliger


def _voeg_product_toe(db, naam, categorie="Bier", prijs=2.0, toon_op_kiosk=0, actief=1):
    db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad,
               bestel_hoeveelheid, verkoopprijs, actief, toon_op_kiosk)
           VALUES (?, ?, 'stuks', 0, 0, 0, ?, ?, ?)""",
        (naam, categorie, prijs, actief, toon_op_kiosk),
    )
    db.commit()
    return db.execute("SELECT id FROM producten WHERE naam = ?", (naam,)).fetchone()["id"]


def _voeg_sponsor_toe(db, titel, actief=1, sjabloon="titel_tekst_groot", volgorde=0, duur=8):
    db.execute(
        """INSERT INTO kiosk_sponsoren
               (sjabloon, titel, tekst, weergave_duur_seconden, volgorde, actief, aangemaakt_op)
           VALUES (?, ?, 'Bedankt voor de steun!', ?, ?, ?, '2026-01-01 10:00')""",
        (sjabloon, titel, duur, volgorde, actief),
    )
    db.commit()


def _voeg_wedstrijd_toe(db, datum, omschrijving="1e - Test", thuis=1):
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, ?, ?)",
        (datum, omschrijving, thuis),
    )
    db.commit()


def _voeg_actie_toe(db, product_id, tekst="Happy hour!", actief=1):
    db.execute(
        "INSERT INTO kiosk_acties (product_id, tekst, actief, aangemaakt_op) VALUES (?, ?, ?, '2026-01-01 10:00')",
        (product_id, tekst, actief),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM kiosk_acties WHERE product_id = ?", (product_id,)
    ).fetchone()["id"]


def _voeg_lid_toe(db, naam, status="actief", startdatum="2026-01-01", einddatum="2027-01-01", extra_groot=0):
    db.execute(
        """INSERT INTO club_van_20_leden
               (naam, status, startdatum, einddatum, extra_groot, aangemaakt_op)
           VALUES (?, ?, ?, ?, ?, '2026-01-01 10:00')""",
        (naam, status, startdatum, einddatum, extra_groot),
    )
    db.commit()
    return db.execute("SELECT id FROM club_van_20_leden WHERE naam = ?", (naam,)).fetchone()["id"]


# ---------- Onderdeel 1: Prijzenscherm ----------


def test_prijzenscherm_is_publiek_en_toont_alleen_gekozen_producten(client, db):
    _voeg_product_toe(db, "Getoond Biertje", toon_op_kiosk=1)
    _voeg_product_toe(db, "Verborgen Biertje", toon_op_kiosk=0)

    resp = client.get("/kiosk/prijzen")

    assert resp.status_code == 200
    assert b"Getoond Biertje" in resp.data
    assert b"Verborgen Biertje" not in resp.data


def test_prijzenscherm_instellingen_vereist_login(client, db):
    resp = client.get("/kiosk/prijzen/instellingen")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_prijzenscherm_instellingen_bulk_toggle_werkt(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Nieuw Op Kiosk", toon_op_kiosk=0)

    resp = ingelogde_client.post(
        "/kiosk/prijzen/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), f"toon_{product_id}": "on"},
    )
    assert resp.status_code == 302

    rij = db.execute("SELECT toon_op_kiosk FROM producten WHERE id = ?", (product_id,)).fetchone()
    assert rij["toon_op_kiosk"] == 1

    scherm = ingelogde_client.get("/kiosk/prijzen")
    assert b"Nieuw Op Kiosk" in scherm.data


def test_product_toon_op_kiosk_wisselen_via_ajax(ingelogde_client, db):
    """Het losse schuifje op de Kiosk-pagina in de PDA-weergave -- 1 tik,
    direct opgeslagen, geen 'Alles opslaan' nodig."""
    product_id = _voeg_product_toe(db, "Los Te Wisselen", toon_op_kiosk=0)

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/toon",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["toon_op_kiosk"] == 1
    assert "staat nu op het prijzenscherm" in data["melding"]

    rij = db.execute("SELECT toon_op_kiosk FROM producten WHERE id = ?", (product_id,)).fetchone()
    assert rij["toon_op_kiosk"] == 1

    # Nog een keer tikken zet 'm weer uit.
    resp2 = ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/toon",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp2.get_json()["toon_op_kiosk"] == 0


def test_product_toon_op_kiosk_wisselen_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_kiosk", "voorraad")
    _login(client, "vrijwilliger_kiosk")
    product_id = _voeg_product_toe(db, "Vrijwilliger Mag Niet", toon_op_kiosk=0)

    resp = client.post(
        f"/kiosk/prijzen/product/{product_id}/toon",
        data={"csrf_token": _csrf(client)},
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT toon_op_kiosk FROM producten WHERE id = ?", (product_id,)).fetchone()
    assert rij["toon_op_kiosk"] == 0


def test_kiosk_pagina_toont_kaartjes_in_pda_weergave(ingelogde_client, db):
    _voeg_product_toe(db, "PDA Kaartje Product", toon_op_kiosk=1)
    ingelogde_client.get("/weergave/pda")

    resp = ingelogde_client.get("/kiosk/prijzen/instellingen")

    assert resp.status_code == 200
    assert b"pda-kaartje" in resp.data
    assert b"PDA Kaartje Product" in resp.data
    assert b"Alles opslaan" not in resp.data


def test_kiosk_tegel_op_pda_start_alleen_voor_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_start", "voorraad")
    _login(client, "vrijwilliger_start")
    client.get("/weergave/pda")

    resp = client.get("/")
    assert b"Kiosk" not in resp.data


def test_product_uitverkocht_wisselen_via_ajax(ingelogde_client, db):
    """De UITVERKOCHT-knop op de Kiosk-pagina in de PDA-weergave."""
    product_id = _voeg_product_toe(db, "Op Is Op", toon_op_kiosk=1)

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["kiosk_uitverkocht"] == 1
    assert "uitverkocht" in data["melding"]

    rij = db.execute(
        "SELECT kiosk_uitverkocht FROM producten WHERE id = ?", (product_id,)
    ).fetchone()
    assert rij["kiosk_uitverkocht"] == 1

    # Nog een keer tikken maakt 'm weer beschikbaar.
    resp2 = ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp2.get_json()["kiosk_uitverkocht"] == 0


def test_product_uitverkocht_wisselen_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_uitverkocht", "voorraad")
    _login(client, "vrijwilliger_uitverkocht")
    product_id = _voeg_product_toe(db, "Vrijwilliger Mag Niet Uitverkopen", toon_op_kiosk=1)

    resp = client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(client)},
    )
    assert resp.status_code == 302
    rij = db.execute(
        "SELECT kiosk_uitverkocht FROM producten WHERE id = ?", (product_id,)
    ).fetchone()
    assert rij["kiosk_uitverkocht"] == 0


def test_prijzenscherm_toont_uitverkocht_duidelijk(client, db):
    product_id = _voeg_product_toe(db, "Bijna Op", toon_op_kiosk=1)
    db.execute("UPDATE producten SET kiosk_uitverkocht = 1 WHERE id = ?", (product_id,))
    db.commit()

    resp = client.get("/kiosk/prijzen")

    assert resp.status_code == 200
    assert b"Bijna Op" in resp.data
    assert b"Uitverkocht" in resp.data
    assert b"prijs-regel--uitverkocht" in resp.data


def test_prijzenscherm_versie_verandert_bij_uitverkocht_wisselen(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Versie Product", toon_op_kiosk=1)

    versie_voor = ingelogde_client.get("/kiosk/prijzen/versie").get_json()["versie"]
    ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    versie_na = ingelogde_client.get("/kiosk/prijzen/versie").get_json()["versie"]

    assert versie_voor != versie_na


def test_prijzen_versie_geeft_uitverkocht_namenlijst_voor_de_pop_up(ingelogde_client, db):
    """De grote UITVERKOCHT-pop-up op het prijzenscherm vergelijkt deze
    lijst tussen twee polls om een NIEUW uitverkocht product te detecteren."""
    product_id = _voeg_product_toe(db, "Pop-up Product", toon_op_kiosk=1)

    voor = ingelogde_client.get("/kiosk/prijzen/versie").get_json()
    assert voor["uitverkocht"] == []

    ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    na = ingelogde_client.get("/kiosk/prijzen/versie").get_json()
    assert na["uitverkocht"] == ["Pop-up Product"]


def test_kiosk_pda_pagina_toont_uitverkocht_knop(ingelogde_client, db):
    _voeg_product_toe(db, "Kaartje Met Knop", toon_op_kiosk=1)
    ingelogde_client.get("/weergave/pda")

    resp = ingelogde_client.get("/kiosk/prijzen/instellingen")

    assert resp.status_code == 200
    assert b"Uitverkocht" in resp.data
    assert b"btn-uitverkocht" in resp.data


# ---------- Acties (onderdeel van het prijzenscherm) ----------


def test_actie_aanmaken_bewerken_en_verwijderen(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Actieproduct", prijs=3.5)

    resp = ingelogde_client.post(
        "/kiosk/prijzen/acties/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": str(product_id),
            "tekst": "Happy hour: 1 euro korting!",
            "actief": "on",
        },
    )
    assert resp.status_code == 302
    actie = db.execute(
        "SELECT * FROM kiosk_acties WHERE product_id = ?", (product_id,)
    ).fetchone()
    assert actie is not None
    assert actie["tekst"] == "Happy hour: 1 euro korting!"
    assert actie["actief"] == 1

    lijst = ingelogde_client.get("/kiosk/prijzen/acties")
    assert b"Actieproduct" in lijst.data
    assert b"Happy hour" in lijst.data

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/acties/{actie['id']}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": str(product_id),
            "tekst": "Nu nog goedkoper!",
        },
    )
    assert resp.status_code == 302
    bijgewerkt = db.execute(
        "SELECT * FROM kiosk_acties WHERE id = ?", (actie["id"],)
    ).fetchone()
    assert bijgewerkt["tekst"] == "Nu nog goedkoper!"
    assert bijgewerkt["actief"] == 0  # checkbox niet meegestuurd -> uit

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/acties/{actie['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM kiosk_acties WHERE id = ?", (actie["id"],)).fetchone() is None


def test_actie_aanmaken_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_actie", "voorraad")
    _login(client, "vrijwilliger_actie")
    product_id = _voeg_product_toe(db, "Beschermd Actieproduct")

    resp = client.post(
        "/kiosk/prijzen/acties/nieuw",
        data={"csrf_token": _csrf(client), "product_id": str(product_id), "actief": "on"},
    )
    assert resp.status_code == 302
    assert db.execute(
        "SELECT * FROM kiosk_acties WHERE product_id = ?", (product_id,)
    ).fetchone() is None


def test_actie_toon_wisselen_via_ajax(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Toggle Actieproduct")
    actie_id = _voeg_actie_toe(db, product_id, actief=0)

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/acties/{actie_id}/toon",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["actief"] == 1
    rij = db.execute("SELECT actief FROM kiosk_acties WHERE id = ?", (actie_id,)).fetchone()
    assert rij["actief"] == 1


def test_actie_toon_wisselen_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_actietoggle", "voorraad")
    product_id = _voeg_product_toe(db, "Beschermd Toggle Product")
    actie_id = _voeg_actie_toe(db, product_id, actief=0)
    _login(client, "vrijwilliger_actietoggle")

    resp = client.post(
        f"/kiosk/prijzen/acties/{actie_id}/toon",
        data={"csrf_token": _csrf(client)},
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT actief FROM kiosk_acties WHERE id = ?", (actie_id,)).fetchone()
    assert rij["actief"] == 0


def test_prijzenscherm_bevat_actiegegevens_voor_de_pop_up(client, db):
    product_id = _voeg_product_toe(db, "Zichtbaar Actieproduct", prijs=4.25)
    _voeg_actie_toe(db, product_id, tekst="Nu in de aanbieding!", actief=1)
    _voeg_product_toe(db, "Verborgen Actieproduct")  # geen actie -> mag niet meekomen

    resp = client.get("/kiosk/prijzen")

    assert resp.status_code == 200
    assert b"Zichtbaar Actieproduct" in resp.data
    assert b"Nu in de aanbieding" in resp.data


def test_kiosk_pda_pagina_toont_acties_sectie(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "PDA Actieproduct")
    _voeg_actie_toe(db, product_id, tekst="PDA actietekst", actief=1)
    ingelogde_client.get("/weergave/pda")

    resp = ingelogde_client.get("/kiosk/prijzen/instellingen")

    assert resp.status_code == 200
    assert b"PDA Actieproduct" in resp.data
    assert b"PDA actietekst" in resp.data


# ---------- Onderdeel 2: Sponsoren/leden beheren ----------


def test_sponsor_aanmaken_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_kiosk", "voorraad")
    _login(client, "vrijwilliger_kiosk")

    resp = client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data={
            "csrf_token": _csrf(client),
            "sjabloon": "titel_tekst_groot",
            "titel": "Stiekeme Sponsor",
        },
    )
    assert resp.status_code == 302
    volg_resp = client.get(resp.headers["Location"])
    assert b"alleen voor beheerders" in volg_resp.data
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_sponsoren").fetchone()["n"] == 0


def test_sponsor_aanmaken_bewerken_en_verwijderen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "sjabloon": "titel_tekst_groot",
            "titel": "Testsponsor",
            "tekst": "Bedankt voor de steun",
            "weergave_duur_seconden": "6",
            "volgorde": "2",
            "actief": "on",
        },
    )
    assert resp.status_code == 302
    sponsor = db.execute("SELECT * FROM kiosk_sponsoren WHERE titel = 'Testsponsor'").fetchone()
    assert sponsor is not None
    assert sponsor["weergave_duur_seconden"] == 6

    bewerk_pagina = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{sponsor['id']}/bewerken")
    assert bewerk_pagina.status_code == 200
    assert b"Testsponsor" in bewerk_pagina.data

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{sponsor['id']}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "sjabloon": "titel_tekst_groot",
            "titel": "Testsponsor Bijgewerkt",
            "weergave_duur_seconden": "6",
            "volgorde": "2",
        },
    )
    assert resp.status_code == 302
    bijgewerkt = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (sponsor["id"],)).fetchone()
    assert bijgewerkt["titel"] == "Testsponsor Bijgewerkt"
    assert bijgewerkt["actief"] == 0  # checkbox niet meegestuurd -> uit

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{sponsor['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (sponsor["id"],)).fetchone() is None


def test_sponsor_formulier_toont_mededeling_sjabloon_en_voorbeeldtekst(ingelogde_client, db):
    resp = ingelogde_client.get("/kiosk/sponsoren-leden/sponsoren/nieuw")
    assert resp.status_code == 200
    assert b"Mededeling" in resp.data
    assert b"mededeling_groot" in resp.data
    # Voorbeeldtekst zit als JSON in de placeholder-script, voor alle sjablonen.
    assert b"Kantinedienst gezocht" in resp.data


def test_kantine_scherm_toont_mededeling_label(client, db):
    _voeg_sponsor_toe(db, "Kantinedienst gezocht!", sjabloon="mededeling_groot")

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"Kantinedienst gezocht!" in resp.data
    assert b"mededeling-label" in resp.data
    assert b">Mededeling<" in resp.data


def test_lid_toevoegen_en_verwijderen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Jan Jansen"},
    )
    assert resp.status_code == 302
    lid = db.execute("SELECT * FROM club_van_20_leden WHERE naam = 'Jan Jansen'").fetchone()
    assert lid is not None

    overzicht = ingelogde_client.get("/kiosk/sponsoren-leden")
    assert b"Jan Jansen" in overzicht.data

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/leden/{lid['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid["id"],)).fetchone() is None


def test_lid_nieuw_krijgt_automatisch_start_en_einddatum(ingelogde_client, db):
    """Startdatum = vandaag, einddatum = vandaag + de ingestelde standaard
    looptijd (12 maanden, zie kiosk_scherm_instellingen)."""
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Piet Pietersen"},
    )
    assert resp.status_code == 302

    lid = db.execute(
        "SELECT * FROM club_van_20_leden WHERE naam = 'Piet Pietersen'"
    ).fetchone()
    vandaag = date.today().isoformat()
    assert lid["status"] == "actief"
    assert lid["startdatum"] == vandaag
    assert lid["einddatum"] == voeg_maanden_toe(vandaag, 12)


def test_lid_status_wisselen_via_ajax(ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Nog Niet Betaald"},
    )
    lid = db.execute(
        "SELECT * FROM club_van_20_leden WHERE naam = 'Nog Niet Betaald'"
    ).fetchone()

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/leden/{lid['id']}/status",
        data={"csrf_token": _csrf(ingelogde_client), "status": "niet_betaald"},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["status"] == "niet_betaald"

    rij = db.execute(
        "SELECT status FROM club_van_20_leden WHERE id = ?", (lid["id"],)
    ).fetchone()
    assert rij["status"] == "niet_betaald"


def test_lid_status_wisselen_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_lidstatus", "voorraad")
    db.execute(
        "INSERT INTO club_van_20_leden (naam, status, startdatum, einddatum, aangemaakt_op) "
        "VALUES ('Test Lid', 'actief', '2026-01-01', '2027-01-01', '2026-01-01 10:00')"
    )
    db.commit()
    lid_id = db.execute(
        "SELECT id FROM club_van_20_leden WHERE naam = 'Test Lid'"
    ).fetchone()["id"]
    _login(client, "vrijwilliger_lidstatus")

    resp = client.post(
        f"/kiosk/sponsoren-leden/leden/{lid_id}/status",
        data={"csrf_token": _csrf(client), "status": "inactief"},
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT status FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
    assert rij["status"] == "actief"


def test_kantine_scherm_verbergt_inactieve_leden_maar_toont_niet_betaald(client, db):
    db.executemany(
        "INSERT INTO club_van_20_leden (naam, status, startdatum, einddatum, aangemaakt_op) "
        "VALUES (?, ?, '2026-01-01', '2027-01-01', '2026-01-01 10:00')",
        [
            ("Actief Lid", "actief"),
            ("Inactief Lid", "inactief"),
            ("Wanbetaler", "niet_betaald"),
        ],
    )
    db.commit()

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()

    assert resp.status_code == 200
    assert "Actief Lid" in tekst
    assert "Inactief Lid" not in tekst
    # Niet betaald blijft zichtbaar (als herinnering om te betalen), maar
    # dan met de lichtrode waarschuwingsklasse i.p.v. de gewone chip-stijl.
    assert "Wanbetaler" in tekst
    positie = tekst.find("Wanbetaler")
    fragment = tekst[max(0, positie - 200) : positie]
    assert "naam-chip--niet-betaald" in fragment


def test_sponsoren_leden_pagina_toont_status_en_looptijd(ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Weergave Test"},
    )

    resp = ingelogde_client.get("/kiosk/sponsoren-leden")

    assert resp.status_code == 200
    assert b"lid-status-select" in resp.data
    assert b"lid-naam" in resp.data
    assert b"Niet betaald" in resp.data


def test_lid_bewerken_wijzigt_naam_looptijd_en_extra_groot(ingelogde_client, db):
    lid_id = _voeg_lid_toe(db, "Oud Lid", startdatum="2020-01-01", einddatum="2021-01-01")

    formulier = ingelogde_client.get(f"/kiosk/sponsoren-leden/leden/{lid_id}/bewerken")
    assert formulier.status_code == 200
    assert b"Oud Lid" in formulier.data

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/leden/{lid_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Nieuwe Naam",
            "status": "inactief",
            "startdatum": "2022-06-15",
            "einddatum": "2028-06-15",
            "extra_groot": "on",
        },
    )
    assert resp.status_code == 302

    lid = db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
    assert lid["naam"] == "Nieuwe Naam"
    assert lid["status"] == "inactief"
    assert lid["startdatum"] == "2022-06-15"
    assert lid["einddatum"] == "2028-06-15"
    assert lid["extra_groot"] == 1


def test_lid_bewerken_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_lidbewerken", "voorraad")
    lid_id = _voeg_lid_toe(db, "Beschermd Lid")
    _login(client, "vrijwilliger_lidbewerken")

    resp = client.post(
        f"/kiosk/sponsoren-leden/leden/{lid_id}/bewerken",
        data={
            "csrf_token": _csrf(client),
            "naam": "Gehackte Naam",
            "status": "actief",
            "startdatum": "2026-01-01",
            "einddatum": "2027-01-01",
        },
    )
    assert resp.status_code == 302
    lid = db.execute("SELECT naam FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
    assert lid["naam"] == "Beschermd Lid"


def test_jaren_lid_berekent_volledige_jaren():
    from helpers import bereken_jaren_lid

    vaste_vandaag = date(2026, 6, 15)
    assert bereken_jaren_lid(None, vandaag=vaste_vandaag) == 0
    assert bereken_jaren_lid("2026-06-15", vandaag=vaste_vandaag) == 0
    # Verjaardag van de startdatum (10 juni) is dit jaar al geweest -> vol 10 jaar.
    assert bereken_jaren_lid("2016-06-10", vandaag=vaste_vandaag) == 10
    # Verjaardag (20 juni) moet dit jaar nog komen -> nog geen 5 volle jaren.
    assert bereken_jaren_lid("2021-06-20", vandaag=vaste_vandaag) == 4


def test_kantine_scherm_toont_sterren_per_jaar_lid(client, db):
    tien_jaar_geleden = date(date.today().year - 10, 1, 1).isoformat()
    _voeg_lid_toe(db, "Trouw Lid", startdatum=tien_jaar_geleden, einddatum="2099-01-01")

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert "★" * 10 in resp.data.decode("utf-8")
    assert b"Trouw Lid" in resp.data


def test_kantine_scherm_toont_extra_grote_naam(client, db):
    _voeg_lid_toe(db, "Grote Naam", extra_groot=1)
    _voeg_lid_toe(db, "Gewone Naam", extra_groot=0)

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # De extra-grote klasse hoort bij het kaartje van "Grote Naam", niet bij "Gewone Naam".
    groot_klasse = 'class="naam-chip naam-chip--groot"'
    assert groot_klasse in html
    groot_positie = html.index(groot_klasse)
    assert "Grote Naam" in html[groot_positie : groot_positie + 200]
    assert "Gewone Naam" not in html[groot_positie : groot_positie + 200]


# ---------- Onderdeel 3: Kantine scherm ----------


def test_scherm_instellingen_opslaan(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            # toon_sponsoren bewust niet meegestuurd -> uit
            "sponsoren_volgorde": "1",
            "toon_club_van_20": "on",
            "club_van_20_volgorde": "1",
            "club_van_20_titel": "Onze Club van 20",
            "club_van_20_namen_per_slide": "2",
            "club_van_20_looptijd_maanden": "6",
            # toon_wedstrijden bewust niet meegestuurd -> uit
            "wedstrijden_volgorde": "3",
        },
    )
    assert resp.status_code == 302

    instellingen = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert instellingen["toon_sponsoren"] == 0
    assert instellingen["toon_club_van_20"] == 1
    assert instellingen["club_van_20_titel"] == "Onze Club van 20"
    assert instellingen["club_van_20_namen_per_slide"] == 2
    assert instellingen["club_van_20_looptijd_maanden"] == 6
    assert instellingen["toon_wedstrijden"] == 0

    # Een nieuw lid gebruikt meteen de zojuist opgeslagen looptijd.
    ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Looptijd Test"},
    )
    lid = db.execute(
        "SELECT * FROM club_van_20_leden WHERE naam = 'Looptijd Test'"
    ).fetchone()
    vandaag = date.today().isoformat()
    assert lid["startdatum"] == vandaag
    assert lid["einddatum"] == voeg_maanden_toe(vandaag, 6)


def test_kantine_scherm_is_publiek_en_toont_alleen_actieve_sponsoren(client, db):
    _voeg_sponsor_toe(db, "Actieve Sponsor", actief=1)
    _voeg_sponsor_toe(db, "Inactieve Sponsor", actief=0)

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"Actieve Sponsor" in resp.data
    assert b"Inactieve Sponsor" not in resp.data


def test_kantine_scherm_verdeelt_leden_over_meerdere_slides(client, db):
    db.execute(
        "UPDATE kiosk_scherm_instellingen SET club_van_20_namen_per_slide = 2 WHERE id = 1"
    )
    for naam in ["Aad", "Bram", "Cor"]:
        db.execute(
            "INSERT INTO club_van_20_leden (naam, aangemaakt_op) VALUES (?, '2026-01-01 10:00')",
            (naam,),
        )
    db.commit()

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    for naam in ["Aad", "Bram", "Cor"]:
        assert naam.encode() in resp.data
    assert b"1/2" in resp.data
    assert b"2/2" in resp.data


def test_kantine_scherm_verbergt_wedstrijden_blok_zonder_wedstrijden(client, db):
    resp = client.get("/kiosk/scherm")
    assert resp.status_code == 200
    assert b"Komende thuiswedstrijden" not in resp.data


def test_kantine_scherm_toont_wedstrijden_blok_indien_aanwezig(client, db):
    from datetime import date, timedelta

    morgen = (date.today() + timedelta(days=1)).isoformat()
    _voeg_wedstrijd_toe(db, morgen, "1e - Kiosk tegenstander")

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"Komende thuiswedstrijden" in resp.data
    assert b"Kiosk tegenstander" in resp.data


def test_kantine_scherm_toont_lege_staat_als_alles_uit_staat(client, db):
    db.execute(
        """UPDATE kiosk_scherm_instellingen
           SET toon_sponsoren = 0, toon_club_van_20 = 0, toon_wedstrijden = 0
           WHERE id = 1"""
    )
    db.commit()

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert "nog niets ingesteld".encode() in resp.data


# ---------- Navigatie (zijbalk i.p.v. het accountmenu) ----------


def test_kiosk_zijbalk_groep_zichtbaar_voor_beheerder(ingelogde_client, db):
    resp = ingelogde_client.get("/")
    assert resp.status_code == 200
    assert b"Kiosk" in resp.data


def test_kiosk_zijbalk_groep_verborgen_voor_vrijwilliger(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_zijbalk", "voorraad")
    _login(client, "vrijwilliger_zijbalk")

    resp = client.get("/")

    assert resp.status_code == 200
    assert b"Kiosk" not in resp.data


def test_kiosk_route_blijft_beschermd_ook_al_staat_die_nu_in_de_zijbalk(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_kiosk_route", "voorraad")
    _login(client, "vrijwilliger_kiosk_route")

    resp = client.get("/kiosk", follow_redirects=True)

    assert resp.status_code == 200
    assert b"alleen voor beheerders" in resp.data
