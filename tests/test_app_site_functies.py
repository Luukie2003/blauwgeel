"""Functies van de site in de app (2.10.0, eerst voor de tablet): geld afdragen of toevoegen bij de kassa, storten of
opnemen bij de kluis, de verkoopdagen van de prognose, en de rest van een product bewerken. Dezelfde boekingen en
controles als de formulieren op de site."""

from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_secties_rechten import _login, _maak_vrijwilliger


def _standen(db):
    rij = db.execute("SELECT kassalade_stand, kluis_stand FROM instellingen WHERE id = 1").fetchone()
    return round(rij[0], 2), round(rij[1], 2)


def test_afdragen_uit_de_kassalade_naar_de_kluis(app_client, db):  # noqa: F811
    kassa, kluis = _standen(db)
    antwoord = _post(app_client, "/api/app/kassa/mutatie", type="afdracht", bedrag="50,25", ontvanger="Penningmeester",
                     opmerking="Na de wedstrijd", verzoek_id="geld-1")
    assert antwoord.status_code == 200 and antwoord.get_json()["melding"] == "Afdracht van € 50,25 geboekt."
    assert _standen(db) == (round(kassa - 50.25, 2), round(kluis + 50.25, 2))
    # Hetzelfde verzoek nog eens (de verbinding haperde): niet dubbel.
    _post(app_client, "/api/app/kassa/mutatie", type="afdracht", bedrag="50,25", verzoek_id="geld-1")
    assert db.execute("SELECT COUNT(*) FROM kassa_mutaties").fetchone()[0] == 1

    # Het overzicht van de kassa toont hem bij de laatste geldbewegingen.
    m = app_client.get("/api/app/kassa").get_json()["mutaties"][0]
    assert (m["type"], m["bedrag"], m["ontvanger"], m["opmerking"]) == ("afdracht", 50.25, "Penningmeester", "Na de wedstrijd")


def test_een_toevoeging_en_wat_niet_mag(app_client, db):  # noqa: F811
    kassa, kluis = _standen(db)
    assert _post(app_client, "/api/app/kassa/mutatie", type="toevoeging", bedrag=20, verzoek_id="geld-2").status_code == 200
    assert _standen(db) == (round(kassa + 20, 2), round(kluis - 20, 2))
    for fout in ({"type": "storting", "bedrag": 5}, {"type": "afdracht", "bedrag": 0}, {"type": "afdracht", "bedrag": "x"},
                 {"type": "afdracht", "bedrag": -3}):
        assert _post(app_client, "/api/app/kassa/mutatie", verzoek_id=f"fout-{fout}", **fout).status_code == 400, fout


def test_storten_en_opnemen_bij_de_kluis(app_client, db):  # noqa: F811
    kassa, kluis = _standen(db)
    _post(app_client, "/api/app/kluis/mutatie", type="storting", bedrag=100, verzoek_id="kluis-1")
    _post(app_client, "/api/app/kluis/mutatie", type="opname", bedrag="30,50", ontvanger="Bank", verzoek_id="kluis-2")
    assert _standen(db) == (kassa, round(kluis + 69.5, 2))
    assert [m["type"] for m in app_client.get("/api/app/kluis").get_json()["mutaties"]] == ["opname", "storting"]


def test_de_kluis_alleen_voor_beheerders_de_kassa_voor_wie_de_kassa_doet(client, db):
    _maak_vrijwilliger(db, "kassa_vrijwilliger", "kassa")
    _login(client, "kassa_vrijwilliger")
    kop = {"X-CSRF-Token": _csrf(client)}
    assert client.post("/api/app/kassa/mutatie", json={"type": "afdracht", "bedrag": 5, "verzoek_id": "v-1"},
                       headers=kop).status_code == 200
    assert client.post("/api/app/kluis/mutatie", json={"type": "storting", "bedrag": 5, "verzoek_id": "v-2"},
                       headers=kop).status_code in (302, 403)
    assert db.execute("SELECT COUNT(*) FROM kluis_mutaties").fetchone()[0] == 0


def test_de_verkoopdagen_in_de_app(app_client, db):  # noqa: F811
    dagen = app_client.get("/api/app/verkoopdagen").get_json()["dagen"]
    assert [d["naam"] for d in dagen][:2] == ["maandag", "dinsdag"] and len(dagen) == 7

    antwoord = _post(app_client, "/api/app/verkoopdagen", dagen={"2": "altijd", "4": "wedstrijd", "5": "altijd"})
    assert antwoord.status_code == 200 and antwoord.get_json()["melding"]
    assert [d["keuze"] for d in antwoord.get_json()["dagen"]] == ["dicht", "dicht", "altijd", "dicht", "wedstrijd", "altijd", "dicht"]
    rij = db.execute("SELECT verkoopdagen, verkoopdagen_wedstrijd FROM instellingen WHERE id = 1").fetchone()
    assert (rij[0], rij[1]) == ("2,5", "4")

    # Zonder één vaste dag kan niet, net als op de site.
    assert _post(app_client, "/api/app/verkoopdagen", dagen={"4": "wedstrijd"}).status_code == 400


def test_het_formulier_op_de_site_boekt_nog_net_zo(ingelogde_client, db):
    kassa, kluis = _standen(db)
    ingelogde_client.post("/kassa/mutatie/nieuw", data={"csrf_token": _csrf(ingelogde_client), "type": "afdracht",
                                                        "bedrag": "12,50", "ontvanger": "", "opmerking": ""})
    ingelogde_client.post("/kluis/mutatie/nieuw", data={"csrf_token": _csrf(ingelogde_client), "type": "opname",
                                                        "bedrag": "2", "ontvanger": "", "opmerking": ""})
    assert _standen(db) == (round(kassa - 12.5, 2), round(kluis + 12.5 - 2, 2))


# ---------- De rest van een product bewerken (beheerders) ----------


def _product(db, naam, artikelcode=None):
    pid = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, inkoopprijs, actief, artikelcode)
           VALUES (?, 'Fris', 'stuks', 10, 5, 2.0, 1.0, 1, ?)""",
        (naam, artikelcode),
    ).lastrowid
    db.execute("INSERT OR IGNORE INTO categorieen (naam) VALUES ('Fris')")
    db.execute("INSERT OR IGNORE INTO categorieen (naam) VALUES ('Bier')")
    db.commit()
    return pid


def test_de_rest_van_een_product_bewerken(app_client, db):  # noqa: F811
    pid = _product(db, "Cola Bewerken")
    lid = db.execute("INSERT INTO leveranciers (naam, aangemaakt_op) VALUES ('Robertus', '2026-11-01')").lastrowid
    db.commit()
    stand = app_client.get(f"/api/app/producten/{pid}/bewerken").get_json()
    assert stand["categorie"] == "Fris" and "Bier" in stand["categorieen"] and {"id": lid, "naam": "Robertus"} in stand["leveranciers"]

    antwoord = _post(app_client, f"/api/app/producten/{pid}/bewerken", categorie="Bier", leverancier_id=lid, artikelcode=" cb-1 ",
                     inkoopprijs="0,85", bestel_hoeveelheid=24, toon_op_kiosk=True, actief=True, opmerking="Alleen in blik")
    assert antwoord.status_code == 200 and antwoord.get_json()["melding"] == "Opgeslagen."
    rij = db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()
    assert (rij["categorie"], rij["leverancier_id"], rij["artikelcode"], rij["inkoopprijs"], rij["bestel_hoeveelheid"],
            rij["toon_op_kiosk"], rij["opmerking"]) == ("Bier", lid, "cb-1", 0.85, 24, 1, "Alleen in blik")
    # Een andere inkoopprijs staat in de prijsgeschiedenis, en het staat in het logboek.
    assert db.execute("SELECT nieuwe_prijs FROM prijs_geschiedenis WHERE product_id = ? AND veld = 'inkoopprijs'", (pid,)).fetchone()[0] == 0.85
    assert db.execute("SELECT COUNT(*) FROM logboek WHERE actie = 'api_app_product_bewerken'").fetchone()[0] == 1


def test_product_bewerken_weigert_wat_niet_klopt(app_client, db):  # noqa: F811
    pid = _product(db, "Sinas Bewerken")
    _product(db, "Ander Product", artikelcode="DUBBEL")
    goed = {"categorie": "Fris", "leverancier_id": None, "artikelcode": "", "bestel_hoeveelheid": 0, "actief": True}
    for fout in ({"categorie": "Bestaat niet"}, {"leverancier_id": 999999}, {"artikelcode": "dubbel"}, {"inkoopprijs": "x"},
                 {"bestel_hoeveelheid": -1}):
        assert _post(app_client, f"/api/app/producten/{pid}/bewerken", **{**goed, **fout}).status_code == 400, fout
    assert app_client.get("/api/app/producten/999999/bewerken").status_code == 404


def test_product_bewerken_alleen_voor_beheerders(client, db):
    pid = _product(db, "Bier Bewerken")
    _maak_vrijwilliger(db, "voorraad_vrijwilliger", "voorraad")
    _login(client, "voorraad_vrijwilliger")
    resp = client.post(f"/api/app/producten/{pid}/bewerken", json={"categorie": "Bier"}, headers={"X-CSRF-Token": _csrf(client)})
    assert resp.status_code in (302, 403)
    assert db.execute("SELECT categorie FROM producten WHERE id = ?", (pid,)).fetchone()[0] == "Fris"
