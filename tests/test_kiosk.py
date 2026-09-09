from conftest import stel_csrf_token_in as _csrf
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
    assert instellingen["toon_wedstrijden"] == 0


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
