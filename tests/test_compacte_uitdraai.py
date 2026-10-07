from werkzeug.security import generate_password_hash

from conftest import stel_csrf_token_in as _csrf
from database import WACHTWOORD_HASH_METHODE


def _voeg_data_toe(db):
    db.execute(
        "INSERT INTO producten (naam, categorie, voorraad, min_voorraad, verkoopprijs) "
        "VALUES ('Pils fles', 'Bier', 3, 12, 2.5), ('Cola', 'Fris', 40, 10, 1.5)"
    )
    db.execute(
        """INSERT INTO kassa_tellingen (datum, naam, verwacht_bedrag, contante_omzet,
           geteld_bedrag, verschil, afgesloten, goedgekeurd_door)
           VALUES ('2026-10-03 22:00', 'Piet', 100, 40, 135, -5, 1, 'Karin')"""
    )
    db.execute(
        "INSERT INTO kassa_mutaties (type, bedrag, datum, naam) VALUES ('afdracht', 80, '2026-10-03 22:30', 'Piet')"
    )
    db.execute(
        "INSERT INTO kluis_mutaties (type, bedrag, datum, naam) VALUES ('storting', 50, '2026-10-04 10:00', 'Karin')"
    )
    db.commit()


def test_pagina_en_pdf_voor_beheerder(ingelogde_client, db):
    _voeg_data_toe(db)
    pagina = ingelogde_client.get("/rapporten/uitdraai")
    assert pagina.status_code == 200
    assert b"Kasverslag" in pagina.data and b"Kluisverslag" in pagina.data

    resp = ingelogde_client.get("/rapporten/uitdraai/pdf?kas=1&kluis=1&voorraad=1")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF")


def test_pdf_zonder_keuze_stuurt_terug(ingelogde_client):
    resp = ingelogde_client.get("/rapporten/uitdraai/pdf")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/rapporten/uitdraai")


def test_pdf_ook_met_lege_database(ingelogde_client):
    resp = ingelogde_client.get("/rapporten/uitdraai/pdf?kas=1&kluis=1&voorraad=1")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")


def test_voorraad_lijst_loopt_door_over_meerdere_pagina_s(ingelogde_client, db):
    for i in range(300):
        db.execute(
            "INSERT INTO producten (naam, categorie, voorraad, min_voorraad) VALUES (?, ?, 5, 1)",
            (f"Product {i}", f"Categorie {i % 7}"),
        )
    db.commit()
    resp = ingelogde_client.get("/rapporten/uitdraai/pdf?voorraad=1")
    assert resp.status_code == 200
    assert resp.data.count(b"/Type /Page\n") >= 2 or resp.data.count(b"/Type /Page") >= 3


def test_vrijwilliger_zonder_rechten_krijgt_geen_kluis_of_kas(app, client, db):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) "
        "VALUES ('vrijwilliger', ?, 'vrijwilliger', 'voorraad', '2026-01-01 10:00')",
        (generate_password_hash("geheim123", method=WACHTWOORD_HASH_METHODE),),
    )
    db.commit()
    token = _csrf(client)
    resp = client.post("/login", data={"naam": "vrijwilliger", "wachtwoord": "geheim123", "csrf_token": token})
    assert resp.status_code == 302

    pagina = client.get("/rapporten/uitdraai")
    assert pagina.status_code == 200
    assert b"Kasverslag" not in pagina.data
    assert b"Kluisverslag" not in pagina.data
    assert b"Huidige voorraadstand" in pagina.data

    # Een handmatig toegevoegd kluis/kas-onderdeel wordt genegeerd.
    resp = client.get("/rapporten/uitdraai/pdf?kas=1&kluis=1")
    assert resp.status_code == 302
    resp = client.get("/rapporten/uitdraai/pdf?kas=1&kluis=1&voorraad=1")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")
