"""De keuken als eigen module (tellen, inboeken, prijzen, apart van de gewone telling)."""

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from helpers import bereken_omzet_en_kassa
from keukenbeheer import boek_keuken_in, verwerk_keuken_telling
from marge import bereken_marge


def _keuken(db, naam="Frikandel Proef", voorraad=40, verkoop=1.75, inkoop=12.0, factor=40):
    cur = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, inkoopprijs, actief,
                                  besteleenheid, besteleenheid_factor)
           VALUES (?, 'Keuken', 'Stuks', ?, 20, ?, ?, 1, 'Doos', ?)""",
        (naam, voorraad, verkoop, inkoop, factor),
    )
    db.commit()
    return cur.lastrowid


def _voorraad(db, pid):
    return db.execute("SELECT voorraad FROM producten WHERE id = ?", (pid,)).fetchone()[0]


# ---------- Keuken ----------


def test_inboeken_per_doos_en_tellen_geeft_de_verkoop(db):
    pid = _keuken(db)
    assert boek_keuken_in(db, {pid: 2}, "Kok", "2026-10-10 10:00", inkoopprijzen={pid: 13.0}) == 1
    assert _voorraad(db, pid) == 120  # 40 + 2 dozen van 40
    assert db.execute("SELECT inkoopprijs FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 13.0

    telling = verwerk_keuken_telling(db, {pid: 70}, "Kok", "2026-10-11 20:00")

    regel = db.execute("SELECT * FROM keuken_telling_regels WHERE telling_id = ?", (telling,)).fetchone()
    assert (regel["verkocht"], regel["verkoopprijs"]) == (50, 1.75)
    assert _voorraad(db, pid) == 70
    assert db.execute("SELECT COUNT(*) FROM telling_regels WHERE product_id = ?", (pid,)).fetchone()[0] == 0  # niet in de gewone telling
    mutaties = [m["opmerking"] for m in db.execute("SELECT opmerking FROM mutaties WHERE product_id = ? ORDER BY id", (pid,))]
    assert mutaties == ["Ingeboekt (keuken): 2 doos", f"Verkocht (keukentelling #{telling})"]


def test_de_keukenpaginas_werken(ingelogde_client, db):
    pid = _keuken(db)
    ingelogde_client.post("/keuken/inboeken", data={"csrf_token": _csrf(ingelogde_client), f"aantal_{pid}": "1", f"inkoop_{pid}": "12,00"})
    assert _voorraad(db, pid) == 80
    resp = ingelogde_client.post("/keuken/tellen", data={"csrf_token": _csrf(ingelogde_client), f"geteld_{pid}": "60"}, follow_redirects=True)
    tekst = resp.data.decode()
    assert "Keukentelling #" in tekst and "&euro; 35,00" in tekst  # 20 frikandellen van € 1,75
    ingelogde_client.post("/keuken/prijzen", data={"csrf_token": _csrf(ingelogde_client), f"prijs_{pid}": "2,00"})
    assert db.execute("SELECT verkoopprijs FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 2.0
    assert db.execute("SELECT COUNT(*) FROM prijs_geschiedenis WHERE product_id = ? AND veld = 'verkoopprijs'", (pid,)).fetchone()[0] == 1
    for url in ("/keuken", "/keuken/tellen", "/keuken/inboeken", "/keuken/prijzen", "/keuken/tellingen"):
        assert 'href="/keuken/tellen"' in ingelogde_client.get(url).data.decode(), url


def test_keukenomzet_telt_mee_in_marge_en_kassa(db):
    from datetime import date

    pid = _keuken(db, inkoop=40.0)  # € 1 per frikandel
    verwerk_keuken_telling(db, {pid: 30}, "Kok", "2026-10-10 20:00")  # 10 verkocht = € 17,50
    rapport = bereken_marge(db, 4, date(2026, 10, 13))
    frikandel = next(p for p in rapport["producten"] if p["id"] == pid)
    assert frikandel["omzet"] == 17.5 and abs(frikandel["winst"] - 7.5) < 0.001

    for datum in ("2026-10-09 12:00", "2026-10-12 12:00"):
        db.execute("INSERT INTO kassa_tellingen (datum, contante_omzet, afgesloten) VALUES (?, 10, 1)", (datum,))
    db.commit()
    assert bereken_omzet_en_kassa(db)["periodes"][0]["voorraad"] == 17.5


def test_vrijwilliger_met_keuken_mag_tellen_maar_geen_prijzen(client, db):
    _keuken(db)
    _maak_vrijwilliger(db, "kok", "keuken")
    _login(client, "kok")
    assert client.get("/keuken/tellen").status_code == 200
    assert client.get("/keuken/inboeken").status_code == 200
    assert "alleen voor beheerders" in client.get("/keuken/prijzen", follow_redirects=True).data.decode()
    assert 'href="/keuken/prijzen"' not in client.get("/keuken/tellen").data.decode()


def test_koud_zetten_is_weg(ingelogde_client):
    """Er is geen koelcel: het koud-zet-advies staat niet meer op het overzicht en de handterminal."""
    assert "koud-zetten" not in ingelogde_client.get("/").data.decode()
    assert ingelogde_client.get("/dashboard/koud-zetten").status_code == 404


# ---------- Begintelling, looplijst en scannen (1.64.0) ----------


def test_begintelling_zet_alleen_de_voorraad_goed(db):
    """De eerste keukentelling: wat er minder ligt dan op de site stond, is geen verkoop en geeft geen omzet."""
    pid = _keuken(db, voorraad=40)
    meer = _keuken(db, naam="Kroket Proef", voorraad=5)
    telling = verwerk_keuken_telling(db, {pid: 25, meer: 12}, "Kok", "2026-10-11 20:00", begintelling=True)

    rij = db.execute("SELECT begintelling FROM keuken_tellingen WHERE id = ?", (telling,)).fetchone()
    assert rij["begintelling"] == 1
    regels = {r["product_id"]: r for r in db.execute("SELECT * FROM keuken_telling_regels WHERE telling_id = ?", (telling,))}
    assert (regels[pid]["verkocht"], regels[pid]["correctie"]) == (0, -15)
    assert (regels[meer]["verkocht"], regels[meer]["correctie"]) == (0, 7)
    assert (_voorraad(db, pid), _voorraad(db, meer)) == (25, 12)
    mutaties = {m["product_id"]: (m["type"], m["aantal"], m["opmerking"]) for m in db.execute("SELECT * FROM mutaties")}
    assert mutaties[pid] == ("uit", 15, f"Begintelling (keukentelling #{telling})")
    assert mutaties[meer] == ("in", 7, f"Begintelling (keukentelling #{telling})")
    # De volgende (gewone) telling rekent vanaf de begintelling
    volgende = verwerk_keuken_telling(db, {pid: 20}, "Kok", "2026-10-18 20:00")
    assert db.execute("SELECT verkocht FROM keuken_telling_regels WHERE telling_id = ?", (volgende,)).fetchone()[0] == 5


def test_keuken_barcodes_tellen_per_supermarkt_anders(db):
    from test_barcodes import AH_DOOS, AH_ZAK, PLUS_ZAK, _artikel

    from keukenbeheer import keuken_barcodes

    pid = _keuken(db)
    _artikel(db, pid, "AH frikandellen", ean=AH_ZAK, aantal=20, prijs=10, doos=AH_DOOS, per_doos=2)
    _artikel(db, pid, "Plus frikandellen", ean=PLUS_ZAK, aantal=15, prijs=8)
    codes = keuken_barcodes(db)
    assert {c: codes[c]["aantal"] for c in codes} == {AH_ZAK: 20, AH_DOOS: 40, PLUS_ZAK: 15}
    assert all(c["product_id"] == pid for c in codes.values())


def test_gescand_inboeken_telt_stuks(db):
    pid = _keuken(db, voorraad=10, factor=40)
    assert boek_keuken_in(db, {pid: 1}, "Kok", "2026-10-10 10:00", gescand={pid: 55}) == 1  # één product, twee boekingen
    assert _voorraad(db, pid) == 10 + 40 + 55
    opmerkingen = [m[0] for m in db.execute("SELECT opmerking FROM mutaties WHERE product_id = ? ORDER BY id", (pid,))]
    assert opmerkingen == ["Ingeboekt (keuken, gescand): 55 stuks", "Ingeboekt (keuken): 1 doos"]


def test_looplijst_koppelen_en_opslaan_via_de_site(ingelogde_client, db):
    from test_barcodes import _ean

    pid = _keuken(db, voorraad=0)
    pagina = ingelogde_client.get("/keuken/tellen/lopen").data.decode()
    assert "Frikandel Proef" in pagina and "Begintelling" in pagina
    code = _ean("871000000009")
    resp = ingelogde_client.post("/keuken/barcode-koppelen", json={"code": code, "product_id": pid, "aantal": "40",
                                                                    "naam": "AH doos", "inkoopprijs": "12,50"},
                                 headers={"X-CSRF-Token": _csrf(ingelogde_client)})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["aantal"] == 40 and resp.get_json()["product_id"] == pid
    assert ingelogde_client.post("/keuken/barcode-koppelen", json={"code": code, "product_id": pid, "aantal": "40"},
                                 headers={"X-CSRF-Token": _csrf(ingelogde_client)}).status_code == 400  # al gekoppeld
    assert ingelogde_client.post("/keuken/barcode-koppelen", json={"code": _ean("871000000010"), "product_id": pid},
                                 headers={"X-CSRF-Token": _csrf(ingelogde_client)}).status_code == 400  # aantal ontbreekt
    assert code in ingelogde_client.get("/keuken/tellen/lopen").data.decode()

    resp = ingelogde_client.post("/keuken/tellen", data={"csrf_token": _csrf(ingelogde_client), f"geteld_{pid}": "80",
                                                         "begintelling": "1", "bron": "looplijst"})
    assert resp.status_code == 302 and "opgeslagen=1" in resp.headers["Location"]
    assert _voorraad(db, pid) == 80
    assert "Begintelling" in ingelogde_client.get("/keuken/tellingen").data.decode()


def test_keuken_scannen_alleen_met_keukenrechten(client, db):
    pid = _keuken(db)
    _maak_vrijwilliger(db, "tapper", "voorraad")
    _login(client, "tapper")
    assert client.get("/keuken/tellen/lopen").status_code == 302
    resp = client.post("/keuken/barcode-koppelen", json={"code": "8710000000093", "product_id": pid, "aantal": 1},
                       headers={"X-CSRF-Token": _csrf(client)})
    assert resp.status_code == 302


def test_app_begintelling_en_gescand_inboeken(app, db):
    from test_app_api_meer import _vrijwilliger

    pid = _keuken(db, voorraad=30)
    client = _vrijwilliger(app, db, "keukenapp", "keuken")
    assert client.get("/api/app/keuken").get_json()["eerste_telling"] is True
    resp = client.post("/api/app/keuken/tellen", json={"waarden": {str(pid): 20}, "begintelling": True, "verzoek_id": "b1"},
                       headers=client.kop)
    assert resp.status_code == 200 and resp.get_json()["melding"].startswith("Begintelling")
    assert db.execute("SELECT SUM(verkocht) FROM keuken_telling_regels").fetchone()[0] == 0
    assert client.get("/api/app/keuken").get_json()["eerste_telling"] is False
    client.post("/api/app/keuken/inboeken", json={"gescand": {str(pid): 55}, "verzoek_id": "b2"}, headers=client.kop)
    assert _voorraad(db, pid) == 75


def test_tellingen_pagina_laadt_de_regels_pas_bij_openen(ingelogde_client, db):
    from routes.tellen.verwerken import verwerk_telling

    pid = db.execute("INSERT INTO producten (naam, categorie, voorraad, verkoopprijs) VALUES ('Cola Proef', 'Fris', 10, 2.5)").lastrowid
    db.commit()
    telling = verwerk_telling(db, {pid: 6}, "Teller", "", "2026-10-10 20:00")
    overzicht = ingelogde_client.get("/tellingen").data.decode()
    assert "Cola Proef" not in overzicht  # niet meer alle regels in de pagina
    regels = ingelogde_client.get(f"/tellingen/{telling}/regels").data.decode()
    assert "Cola Proef" in regels and "€ 10.00" in regels


# ---------- De keuken in de handterminal-app (1.66.0) ----------


def test_app_keuken_dozen_prijs_telling_bekijken_en_boodschappenlijst(app, db):
    from test_app_api_meer import _vrijwilliger
    from test_barcodes import AH_DOOS, AH_ZAK, _artikel

    pid = _keuken(db, voorraad=50, verkoop=1.75)
    _artikel(db, pid, "AH frikandellen", ean=AH_ZAK, aantal=20, prijs=10, doos=AH_DOOS, per_doos=2)
    client = _vrijwilliger(app, db, "keukenapp2", "keuken")

    keuken = client.get("/api/app/keuken").get_json()
    p = next(x for x in keuken["producten"] if x["id"] == pid)
    assert p["verkoopprijs"] == 1.75 and p["op_boodschappenlijst"] is False
    assert [(d["code"], d["aantal"]) for d in p["dozen"]] == [(AH_ZAK, 20), (AH_DOOS, 40)]

    telling = client.post("/api/app/keuken/tellen", json={"waarden": {str(pid): 30}, "verzoek_id": "kt1"},
                          headers=client.kop).get_json()["telling_id"]
    detail = client.get(f"/api/app/keuken/tellingen/{telling}").get_json()
    assert detail["begintelling"] is False and detail["omzet"] == 35.0
    assert detail["regels"] == [{"product_id": pid, "naam": "Frikandel Proef", "eenheid": "Stuks", "was": 50, "geteld": 30,
                                 "verkocht": 20, "correctie": 0, "omzet": 35.0}]
    assert client.get("/api/app/keuken/tellingen/9999").status_code == 404
    assert client.get("/api/app/keuken").get_json()["tellingen"][0]["begintelling"] is False

    # Op de boodschappenlijst, ook zonder voorraadrechten, en maar één keer.
    for verzoek in ("b1", "b2"):
        resp = client.post("/api/app/keuken/boodschap", json={"product_id": pid, "verzoek_id": verzoek}, headers=client.kop)
        assert resp.status_code == 200
    assert [r[0] for r in db.execute("SELECT tekst FROM boodschappen WHERE afgevinkt = 0")] == ["Frikandel Proef (keuken)"]
    assert next(x for x in client.get("/api/app/keuken").get_json()["producten"] if x["id"] == pid)["op_boodschappenlijst"]
    gewoon = db.execute("INSERT INTO producten (naam, categorie, voorraad) VALUES ('Cola', 'Fris', 1)").lastrowid
    db.commit()
    assert client.post("/api/app/keuken/boodschap", json={"product_id": gewoon}, headers=client.kop).status_code == 404
