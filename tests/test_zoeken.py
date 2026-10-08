from werkzeug.security import generate_password_hash

from conftest import stel_csrf_token_in as _csrf
from database import WACHTWOORD_HASH_METHODE
from routes.zoeken import _datum_patroon, _like


def _titels(antwoord):
    return {g["titel"]: [r["titel"] for r in g["resultaten"]] for g in antwoord["groepen"]}


def _zoek(client, term):
    resp = client.get("/zoeken/live", query_string={"q": term})
    assert resp.status_code == 200
    return resp.get_json()


def _vrijwilliger(client, db, secties):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) "
        "VALUES ('vrijwilliger', ?, 'vrijwilliger', ?, '2026-01-01 10:00')",
        (generate_password_hash("geheim123", method=WACHTWOORD_HASH_METHODE), secties),
    )
    db.commit()
    resp = client.post(
        "/login", data={"naam": "vrijwilliger", "wachtwoord": "geheim123", "csrf_token": _csrf(client)}
    )
    assert resp.status_code == 302


def test_zoekpatronen():
    assert _like("50%_x") == "%50\\%\\_x%"
    assert _datum_patroon("03-10-2026") == "2026-10-03%"
    assert _datum_patroon("3-10") == "%-10-03%"
    assert _datum_patroon("pils") is None


def test_te_korte_term_geeft_niets(ingelogde_client):
    assert _zoek(ingelogde_client, "p")["groepen"] == []


def test_zoekt_in_producten_tellingen_prikbord_en_paginas(ingelogde_client, db):
    db.execute(
        "INSERT INTO producten (naam, categorie, voorraad, min_voorraad) VALUES ('Zeldzame Pils', 'Bier', 3, 1)"
    )
    db.execute("INSERT INTO tellingen (datum, naam, opmerking) VALUES ('2026-10-03 23:00', 'Karin', 'pils bijna op')")
    db.execute(
        "INSERT INTO mededelingen (tekst, naam, datum) VALUES ('Pils bestellen niet vergeten', 'Piet', '2026-10-01 10:00')"
    )
    db.commit()

    titels = _titels(_zoek(ingelogde_client, "pils"))

    assert titels["Producten"] == ["Zeldzame Pils"]
    assert titels["Tellingen"] == ["Telling 03-10-2026 23:00"]
    assert titels["Prikbord"] == ["Pils bestellen niet vergeten"]

    pagina = _titels(_zoek(ingelogde_client, "kassa tellen"))
    assert "Kassa tellen" in pagina["Pagina's"]


def test_datum_zoeken_in_nederlandse_notatie(ingelogde_client, db):
    db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-10-03 23:00', 'Karin')")
    db.commit()
    assert "Tellingen" in _titels(_zoek(ingelogde_client, "03-10-2026"))
    assert "Tellingen" in _titels(_zoek(ingelogde_client, "03-10"))
    assert "Tellingen" not in _titels(_zoek(ingelogde_client, "04-10-2026"))


def test_procent_en_underscore_zijn_gewone_tekens(ingelogde_client, db):
    db.execute("INSERT INTO producten (naam, categorie) VALUES ('Korting 50% actie', 'Overig')")
    db.execute("INSERT INTO producten (naam, categorie) VALUES ('Korting 500 actie', 'Overig')")
    db.commit()
    assert _titels(_zoek(ingelogde_client, "50%"))["Producten"] == ["Korting 50% actie"]


def test_resultaten_volgen_de_rechten_van_het_account(client, db):
    db.execute("INSERT INTO producten (naam, categorie) VALUES ('Geheim Product', 'Overig')")
    db.execute("INSERT INTO kassa_tellingen (datum, naam, opmerking) VALUES ('2026-10-03 22:00', 'Piet', 'geheim')")
    db.execute("INSERT INTO kluis_tellingen (datum, naam, opmerking) VALUES ('2026-10-03 22:00', 'Piet', 'geheim')")
    db.execute("INSERT INTO club_van_20_leden (naam, aangemaakt_op) VALUES ('Geheim Lid', '2026-01-01 10:00')")
    db.execute("INSERT INTO mededelingen (tekst, naam, datum) VALUES ('geheim prikbord', 'Piet', '2026-10-01 10:00')")
    db.commit()
    _vrijwilliger(client, db, "kassa")

    titels = _titels(_zoek(client, "geheim"))

    assert "Kassatellingen" in titels      # eigen sectie
    assert "Prikbord" in titels            # voor iedereen
    assert "Producten" not in titels       # geen voorraad-sectie
    assert "Kluistellingen" not in titels  # alleen beheerders
    assert "Club van 20" not in titels     # geen Club van 20-sectie
    assert "Accounts" not in titels


def test_paginas_zijn_alleen_wat_het_account_in_de_zijbalk_ziet(client, db):
    _vrijwilliger(client, db, "voorraad")
    titels = _titels(_zoek(client, "back-ups"))
    assert "Pagina's" not in titels


def test_zoekpagina_toont_resultaten_en_lege_toestand(ingelogde_client, db):
    db.execute("INSERT INTO producten (naam, categorie) VALUES ('Zeldzame Pils', 'Bier')")
    db.commit()
    assert b"Zeldzame Pils" in ingelogde_client.get("/zoeken?q=zeldzame").data
    assert b"Niets gevonden" in ingelogde_client.get("/zoeken?q=bestaatniet").data
    assert b"minstens 2 tekens" in ingelogde_client.get("/zoeken?q=p").data


def test_zoekbalk_staat_in_de_titelbalk(ingelogde_client):
    assert b'id="zoekbalk-invoer"' in ingelogde_client.get("/").data


def test_live_zoeken_telt_niet_mee_als_paginabezoek(ingelogde_client, db):
    _zoek(ingelogde_client, "pils")
    assert db.execute("SELECT COUNT(*) AS n FROM paginabezoeken WHERE endpoint = 'zoeken_live'").fetchone()["n"] == 0


# ---------- Uitgebreid zoeken ----------


def test_zoekt_ook_in_bestellingen_boodschappen_en_verbruiksvoorwerpen(ingelogde_client, db):
    pid = db.execute("INSERT INTO producten (naam, categorie) VALUES ('Radler Citroen', 'Bier')").lastrowid
    cur = db.execute(
        "INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, referentie) VALUES ('besteld', '2026-10-01 10:00', 'Piet', 'Jumbo-4521')"
    )
    db.execute(
        "INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, 2)", (cur.lastrowid, pid)
    )
    db.execute("INSERT INTO boodschappen (tekst, aangemaakt_op) VALUES ('Schoonmaakdoekjes kopen', '2026-10-01 10:00')")
    db.execute("INSERT INTO verbruiksvoorwerpen (naam, aangemaakt_op) VALUES ('Schoonmaakspray', '2026-10-01 10:00')")
    db.commit()

    assert "Bestelling #" in _titels(_zoek(ingelogde_client, "jumbo"))["Bestellingen"][0]
    # Ook via een product in de bestelling
    assert "Bestellingen" in _titels(_zoek(ingelogde_client, "citroen"))
    titels = _titels(_zoek(ingelogde_client, "schoonmaak"))
    assert titels["Boodschappenlijst"] == ["Schoonmaakdoekjes kopen"]
    assert titels["Verbruiksvoorwerpen"] == ["Schoonmaakspray"]


def test_zoekt_in_geldbewegingen_wedstrijden_en_sponsoren(ingelogde_client, db):
    db.execute(
        "INSERT INTO kassa_mutaties (type, bedrag, datum, naam, ontvanger, opmerking) "
        "VALUES ('afdracht', 80, '2026-10-03 22:30', 'Piet', 'Penningmeester', 'sponsorgeld')"
    )
    db.execute(
        "INSERT INTO kluis_mutaties (type, bedrag, datum, naam, opmerking) VALUES ('storting', 150, '2026-10-04 10:00', 'Karin', 'sponsorgeld naar bank')"
    )
    db.execute("INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('ZA 1', '2026-10-10', 'Blauw-Geel - Sponsorteam', 1)")
    db.execute("INSERT INTO kiosk_sponsoren (titel, aangemaakt_op) VALUES ('Sponsor Bakkerij Jansen', '2026-10-01 10:00')")
    db.commit()

    titels = _titels(_zoek(ingelogde_client, "sponsor"))

    assert any("Afdracht" in t for t in titels["Kassa-afdrachten en -toevoegingen"])
    assert any("Storting" in t for t in titels["Kluis-stortingen en -opnames"])
    assert titels["Wedstrijden"] == ["ZA 1 · 2026-10-10"] or titels["Wedstrijden"][0].startswith("ZA 1")
    assert titels["Sponsoren (Kantine-tv)"] == ["Sponsor Bakkerij Jansen"]


def test_uitgebreide_resultaten_volgen_de_rechten(client, db):
    db.execute("INSERT INTO kluis_mutaties (type, bedrag, datum, naam, opmerking) VALUES ('storting', 1, '2026-10-04 10:00', 'K', 'geheimtekst')")
    db.execute("INSERT INTO kassa_mutaties (type, bedrag, datum, naam, opmerking) VALUES ('afdracht', 1, '2026-10-04 10:00', 'K', 'geheimtekst')")
    db.execute("INSERT INTO kiosk_sponsoren (titel, aangemaakt_op) VALUES ('geheimtekst sponsor', '2026-10-01 10:00')")
    db.execute("INSERT INTO boodschappen (tekst, aangemaakt_op) VALUES ('geheimtekst', '2026-10-01 10:00')")
    db.commit()
    _vrijwilliger(client, db, "kassa")

    titels = _titels(_zoek(client, "geheimtekst"))

    assert "Kassa-afdrachten en -toevoegingen" in titels
    assert "Kluis-stortingen en -opnames" not in titels
    assert "Sponsoren (Kantine-tv)" not in titels
    assert "Boodschappenlijst" not in titels  # voorraad-sectie
