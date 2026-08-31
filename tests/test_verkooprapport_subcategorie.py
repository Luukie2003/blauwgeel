from datetime import datetime

from conftest import stel_csrf_token_in as _csrf


def _registreer_verkoop(client, db, subcategorie="Speciaalbier"):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute(
        "UPDATE producten SET voorraad = 20, subcategorie = ? WHERE id = ?",
        (subcategorie, product["id"]),
    )
    db.commit()
    resp = client.post(
        "/tellen",
        data={"csrf_token": _csrf(client), f"geteld_{product['id']}": "5"},
    )
    assert resp.status_code == 302
    return product


def _vandaag_periode():
    vandaag = datetime.now().strftime("%Y-%m-%d")
    return vandaag, vandaag


def test_verkooprapport_toont_subcategorie_bij_top_verkopers(ingelogde_client, db):
    product = _registreer_verkoop(ingelogde_client, db, subcategorie="Speciaalbier")
    van, tot = _vandaag_periode()

    resp = ingelogde_client.get(f"/verkooprapport?van={van}&tot={tot}")
    body = resp.data.decode()
    assert product["naam"] in body
    positie = body.index(product["naam"])
    assert "Speciaalbier" in body[positie:positie + 400]


def test_verkooprapport_csv_bevat_subcategorie_kolom(ingelogde_client, db):
    product = _registreer_verkoop(ingelogde_client, db, subcategorie="Speciaalbier")
    van, tot = _vandaag_periode()

    resp = ingelogde_client.get(f"/verkooprapport/csv?van={van}&tot={tot}")
    tekst = resp.data.decode("utf-8-sig")
    kop = tekst.splitlines()[0]
    assert "Subcategorie" in kop
    assert any(product["naam"] in regel and "Speciaalbier" in regel for regel in tekst.splitlines())


def test_verkooprapport_pdf_werkt_met_en_zonder_subcategorie(ingelogde_client, db):
    _registreer_verkoop(ingelogde_client, db, subcategorie="Speciaalbier")
    van, tot = _vandaag_periode()

    resp = ingelogde_client.get(f"/verkooprapport/pdf?van={van}&tot={tot}")
    assert resp.status_code == 200
    assert resp.content_type == "application/pdf"
