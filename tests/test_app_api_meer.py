"""De JSON-API voor de handterminal-app, deel 2 (routes/app_api_meer.py): productinfo, kassa en kluis, keuken,
boodschappen, Club van 20-aanmeldingen, agenda, prognose, barcodes en taken."""

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_barcodes import _artikel, _ean
from test_eigen_taken import _taak
from test_pda_uitbreiding import _aanmelding
from test_productpagina import _hertog, _weken_terug
from test_secties_rechten import _login, _maak_vrijwilliger
from test_voorspelling import _bouw_geschiedenis


def _vrijwilliger(app, db, naam, secties):
    """Een vrijwilliger met alleen deze secties, ingelogd (zelfde sessie als de app na het inloggen met de code)."""
    _maak_vrijwilliger(db, naam, secties)
    client = app.test_client()
    _login(client, naam)
    client.kop = {"X-CSRF-Token": _csrf(client)}  # na het inloggen is er een nieuwe sessie
    return client


# ---------- Productinformatie ----------


def test_product_met_alle_info(app_client, db):  # noqa: F811
    pid = _hertog(db, merk="Hertog Jan", opmerking="Achter in de koelcel")
    _artikel(db, pid, "Hertog Jan 30cl", _ean("871200000011"), prijs=0.8, doos=_ean("871200000012"), per_doos=24)
    b = db.execute("INSERT INTO bestellingen (status, aangemaakt_op, referentie) VALUES ('besteld', '2026-10-15 11:00', 'N-1')").lastrowid
    db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, 48)", (b, pid))
    db.commit()
    _bouw_geschiedenis(db, {pid: 3}, tijdstippen=_weken_terug(4), open_dagen="2,5")
    info = app_client.get(f"/api/app/producten/{pid}").get_json()["info"]
    assert info["opmerking"] == "Achter in de koelcel" and info["besteleenheid_naam"] == "krat"
    assert info["inkoop_stuk"] == pytest.approx(0.80) and info["marge"]["pct"] == pytest.approx(68.0)
    assert info["onderweg"][0]["aantal"] == 48 and info["onderweg"][0]["in_besteleenheden"] == 2
    assert info["artikelen"][0]["naam"] == "Hertog Jan 30cl" and info["artikelen"][0]["per_doos"] == 24
    assert info["tellingen"] and info["laatst_geteld"]


def test_vrijwilliger_ziet_geen_marge(app, db):
    pid = _hertog(db)
    client = _vrijwilliger(app, db, "voorraadhulp", "voorraad")
    info = client.get(f"/api/app/producten/{pid}").get_json()["info"]
    assert info["marge"] is None and info["inkoop_stuk"] == pytest.approx(0.80)


def test_verkoop_en_verwachting(app_client, db):  # noqa: F811
    pid = _hertog(db)
    # Nog geen tellingen: geen verkoop, maar het bestelblok wel (zelf het aantal colli kiezen kan al).
    verkoop = app_client.get(f"/api/app/producten/{pid}/verkoop").get_json()
    assert verkoop["beschikbaar"] is False and verkoop["bestellen"]["bestellen_eenheden"] == 1
    _bouw_geschiedenis(db, {pid: 4}, tijdstippen=_weken_terug(8), open_dagen="2,5")
    verkoop = app_client.get(f"/api/app/producten/{pid}/verkoop").get_json()
    assert verkoop["beschikbaar"] and verkoop["weken"] and verkoop["per_week"] > 0
    assert verkoop["verwachting"]["verwacht"] > 0 and verkoop["prognose_dagen"] == 7
    assert app_client.get("/api/app/producten/999999/verkoop").status_code == 404


def test_op_de_bestellijst_maar_een_keer_per_verzoek(app_client, db):  # noqa: F811
    pid = _hertog(db)
    for _ in range(2):
        resp = _post(app_client, f"/api/app/producten/{pid}/melden", verzoek_id="melden-1")
        assert resp.status_code == 200 and resp.get_json()["meldingen"] == 1
    assert db.execute("SELECT COUNT(*) FROM bestellijst_meldingen WHERE product_id = ?", (pid,)).fetchone()[0] == 1
    assert app_client.get(f"/api/app/producten/{pid}").get_json()["info"]["meldingen"] == 1


# ---------- Kassa en kluis ----------


def test_kassa_tellen_en_goedkeuren(app_client, db):  # noqa: F811
    db.execute("UPDATE instellingen SET kassalade_stand = 100 WHERE id = 1")
    db.commit()
    kassa = app_client.get("/api/app/kassa").get_json()
    assert kassa["stand"] == 100 and [c["veld"] for c in kassa["coupures"]][0] == "aantal_50"

    body = dict(aantallen={"aantal_50": 2, "aantal_10": 3, "aantal_005": 1}, contante_omzet="30,00", kaart_omzet="12,5",
                opmerking="Na de wedstrijd", verzoek_id="kassa-1")
    eerste = _post(app_client, "/api/app/kassa/tellen", **body).get_json()
    assert _post(app_client, "/api/app/kassa/tellen", **body).get_json() == eerste  # niet dubbel
    telling = eerste["telling"]
    assert telling["geteld"] == pytest.approx(130.05) and telling["verwacht"] == pytest.approx(130.0)
    assert telling["kaart_omzet"] == pytest.approx(12.5) and not telling["afgesloten"] and telling["van_mij"]
    assert "te veel" in eerste["melding"]
    assert db.execute("SELECT COUNT(*) FROM kassa_tellingen").fetchone()[0] == 1
    assert app_client.get("/api/app/kassa").get_json()["concepten"][0]["id"] == telling["id"]

    goed = _post(app_client, f"/api/app/kassa/{telling['id']}/goedkeuren", opmerking="ok")
    assert goed.status_code == 200 and goed.get_json()["stand"] == pytest.approx(130.05)
    assert _post(app_client, f"/api/app/kassa/{telling['id']}/goedkeuren").status_code == 409
    assert app_client.get("/api/app/kassa").get_json()["recent"][0]["afgesloten"]


def test_kassa_tellen_vraagt_of_de_taak_klaar_is(app_client, db):  # noqa: F811
    taak_id = _taak(db, titel="Kassa tellen", soort="preset:kassa_tellen")
    antwoord = _post(app_client, "/api/app/kassa/tellen", aantallen={"aantal_5": 1}).get_json()
    assert antwoord["taak_vragen"] == [{"id": taak_id, "titel": "Kassa tellen"}]


def test_kluis_alleen_voor_beheerders(app, app_client, db):  # noqa: F811
    antwoord = _post(app_client, "/api/app/kluis/tellen", aantallen={"aantal_20": 5}).get_json()
    assert antwoord["telling"]["geteld"] == 100 and "contante_omzet" not in antwoord["telling"]
    assert _post(app_client, f"/api/app/kluis/{antwoord['telling']['id']}/goedkeuren").get_json()["stand"] == 100

    client = _vrijwilliger(app, db, "kassahulp", "kassa")
    assert client.get("/api/app/kassa").status_code == 200
    assert client.get("/api/app/kluis").status_code == 403
    assert client.post("/api/app/kluis/tellen", json={}, headers=client.kop).status_code == 403


# ---------- Keuken ----------


def test_keuken_tellen_inboeken_en_frituurvet(app, db):
    pid = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, verkoopprijs, actief, besteleenheid, besteleenheid_factor)
           VALUES ('Frikandel', 'Keuken', 'stuks', 30, 2.0, 1, 'doos', 40)"""
    ).lastrowid
    db.commit()
    client = _vrijwilliger(app, db, "keukenhulp", "keuken")
    keuken = client.get("/api/app/keuken").get_json()
    frikandel = next(p for p in keuken["producten"] if p["id"] == pid)
    assert (frikandel["voorraad"], frikandel["verpakking"], frikandel["per_verpakking"]) == (30, "doos", 40)
    assert keuken["frituurvet"]["ok"] is False

    resp = client.post("/api/app/keuken/tellen", json={"waarden": {str(pid): 25}, "verzoek_id": "k1"}, headers=client.kop)
    assert resp.status_code == 200
    assert db.execute("SELECT voorraad FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 25
    assert client.post("/api/app/keuken/tellen", json={"waarden": {}}, headers=client.kop).status_code == 400

    client.post("/api/app/keuken/inboeken", json={"verpakkingen": {str(pid): 2}}, headers=client.kop)
    assert db.execute("SELECT voorraad FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 105

    vet = client.post("/api/app/frituurvet", json={}, headers=client.kop).get_json()
    assert vet["frituurvet"]["ok"] is True and vet["frituurvet"]["dagen_geleden"] == 0
    assert client.get("/api/app/boodschappen").status_code == 403  # geen voorraadrechten


# ---------- Boodschappen ----------


def test_boodschappen(app_client, db):  # noqa: F811
    lijst = _post(app_client, "/api/app/boodschappen", tekst="Wc-papier").get_json()
    item = lijst["open"][0]
    assert item["tekst"] == "Wc-papier" and item["door"] == "admin"
    assert _post(app_client, "/api/app/boodschappen", tekst="  ").status_code == 400
    lijst = _post(app_client, f"/api/app/boodschappen/{item['id']}/afvinken", af=True).get_json()
    assert not lijst["open"] and lijst["afgevinkt"][0]["afgevinkt_door"] == "admin"
    lijst = _post(app_client, f"/api/app/boodschappen/{item['id']}/afvinken", af=True).get_json()
    assert not lijst["open"]  # nog een keer "af" blijft af
    lijst = _post(app_client, f"/api/app/boodschappen/{item['id']}/afvinken").get_json()
    assert lijst["open"][0]["id"] == item["id"]
    assert _post(app_client, f"/api/app/boodschappen/{item['id']}/verwijderen").get_json() == {"open": [], "afgevinkt": []}


# ---------- Club van 20-aanmeldingen ----------


def test_aanmelding_goedkeuren_en_afwijzen(app_client, db):  # noqa: F811
    eerste = _aanmelding(db, naam="Jan Jansen", bordje="Jan & Co")
    tweede = _aanmelding(db, naam="Piet Pieters", bordje="Piet")
    lijst = app_client.get("/api/app/aanmeldingen").get_json()
    assert [a["bordje"] for a in lijst["openstaand"]] == ["Jan & Co", "Piet"]

    assert _post(app_client, f"/api/app/aanmeldingen/{eerste}/goedkeuren").status_code == 400
    resp = _post(app_client, f"/api/app/aanmeldingen/{eerste}/goedkeuren", betaling_gecontroleerd=True)
    assert resp.status_code == 200
    lid = db.execute("SELECT * FROM club_van_20_leden WHERE naam = 'Jan & Co'").fetchone()
    assert lid is not None and (lid["voornaam"], lid["achternaam"]) == ("Jan", "Jansen")
    assert _post(app_client, f"/api/app/aanmeldingen/{eerste}/goedkeuren", betaling_gecontroleerd=True).status_code == 409

    assert _post(app_client, f"/api/app/aanmeldingen/{tweede}/afwijzen", reden="Dubbel").status_code == 200
    rij = db.execute("SELECT status, opmerking FROM club_van_20_aanmeldingen WHERE id = ?", (tweede,)).fetchone()
    assert (rij["status"], rij["opmerking"]) == ("afgewezen", "Dubbel")
    lijst = app_client.get("/api/app/aanmeldingen").get_json()
    assert not lijst["openstaand"] and len(lijst["behandeld"]) == 2


def test_aanmeldingen_alleen_met_club_van_20(app, db):
    client = _vrijwilliger(app, db, "barhulp", "voorraad")
    assert client.get("/api/app/aanmeldingen").status_code == 403


# ---------- Agenda, prognose, barcodes ----------


def test_agenda(app_client, db):  # noqa: F811
    agenda = app_client.get("/api/app/agenda?dagen=14").get_json()
    assert agenda["dagen"] == 14 and isinstance(agenda["weken"], list)
    for week in agenda["weken"]:
        for dag in week["dagen"]:
            assert {"datum", "weekdag", "open", "wedstrijden", "bardiensten"} <= set(dag)


def test_prognose(app_client, db):  # noqa: F811
    assert app_client.get("/api/app/prognose").get_json()["beschikbaar"] is False
    pid = _hertog(db)
    _bouw_geschiedenis(db, {pid: 4}, tijdstippen=_weken_terug(8), open_dagen="2,5")
    prognose = app_client.get("/api/app/prognose?dagen=14").get_json()
    assert prognose["beschikbaar"] and prognose["dagen"] == 14
    assert prognose["totaal"]["omzet"] > 0 and prognose["per_dag"]
    assert any(p["id"] == pid for p in prognose["producten"])


def test_barcodes(app_client, db):  # noqa: F811
    pid = _hertog(db)
    _artikel(db, pid, "Hertog Jan 30cl", _ean("871200000021"))
    alles = app_client.get("/api/app/barcodes").get_json()
    assert any(p["product_id"] == pid for p in alles["producten"])
    gezocht = app_client.get("/api/app/barcodes?q=871200000021").get_json()
    assert [p["product_id"] for p in gezocht["producten"]] == [pid] and gezocht["aantal"] == 1


# ---------- Taken ----------


def test_taak_met_stappen_afronden(app_client, db):  # noqa: F811
    taak_id = _taak(db, titel="Koelcel schoonmaken", soort="eigen", omschrijving="Ook de deur")
    db.execute("UPDATE taken SET stappen = ? WHERE id = ?", ("Leeghalen\nSchoonmaken", taak_id))
    db.commit()
    start = app_client.get("/api/app/start").get_json()
    taak = next(t for t in start["taken"] if t["id"] == taak_id)
    assert taak["doel"] is None and taak["stappen"] == 2

    detail = app_client.get(f"/api/app/taken/{taak_id}").get_json()
    assert [s["tekst"] for s in detail["stappen"]] == ["Leeghalen", "Schoonmaken"] and detail["omschrijving"] == "Ook de deur"
    assert _post(app_client, f"/api/app/taken/{taak_id}/afronden").status_code == 409  # eerst de stappen
    for i in range(2):
        assert _post(app_client, f"/api/app/taken/{taak_id}/stap", stap=i, af=True).status_code == 200
    assert app_client.get(f"/api/app/taken/{taak_id}").get_json()["stappen"][1]["af"]
    assert _post(app_client, f"/api/app/taken/{taak_id}/afronden").status_code == 200
    assert app_client.get(f"/api/app/taken/{taak_id}").status_code == 404


def test_taak_met_een_pagina_geeft_het_doel(app_client, db):  # noqa: F811
    taak_id = _taak(db, titel="Kassa tellen", soort="preset:kassa_tellen")
    detail = app_client.get(f"/api/app/taken/{taak_id}").get_json()
    assert detail["doel"]["endpoint"] == "kassa_tellen"


def test_startscherm_met_kassa_keuken_en_club(app_client, db):  # noqa: F811
    db.execute("INSERT INTO kassa_tellingen (datum, naam, verwacht_bedrag, geteld_bedrag, verschil) VALUES ('2026-10-18 20:00', 'x', 0, 0, 0)")
    db.commit()
    _aanmelding(db)
    start = app_client.get("/api/app/start").get_json()
    assert start["kassa"]["concepten"] == 1 and start["kassa"]["status"] == "oranje"
    assert start["aanmeldingen_open"] == 1 and start["kluis_concepten"] == 0
    assert start["frituurvet"]["ok"] is False and start["toegang"]["kantine_tv"]


def test_tellen_start_meteen_en_de_verwachting_komt_apart(app_client, db):  # noqa: F811
    """De looplijst wacht niet op het voorspelmodel: dat haalt de app daarna apart op."""
    pid = _hertog(db)
    _bouw_geschiedenis(db, {pid: 4}, tijdstippen=_weken_terug(8), open_dagen="2,5")
    lijst = app_client.get("/api/app/tellen").get_json()["producten"]
    assert any(p["id"] == pid for p in lijst) and all(p["verwacht"] is None for p in lijst)
    verwacht = app_client.get("/api/app/tellen/verwachting").get_json()["verwacht"]
    assert verwacht[str(pid)]["verwacht"] >= 0
