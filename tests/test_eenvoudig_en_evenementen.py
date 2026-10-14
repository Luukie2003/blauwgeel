"""De eenvoudige weergave (favorieten in het menu en als grote knoppen) en evenementen in de prognose."""

from datetime import date, datetime, timedelta

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

import voorspelling
from navigatie import STANDAARD_FAVORIETEN, favoriete_items


# ---------- Eenvoudige weergave ----------


def test_favorieten_in_volgorde_en_alleen_wat_je_mag_zien():
    items = [{"url_endpoint": e, "label": e} for e in ("dashboard", "tellen", "boeken", "bestellijst", "bijzonderheden")]
    assert [i["url_endpoint"] for i in favoriete_items(items, None)] == STANDAARD_FAVORIETEN
    assert [i["url_endpoint"] for i in favoriete_items(items, "boeken,kluis_tellen,tellen")] == ["boeken", "tellen"]


def test_eenvoudige_weergave_aanzetten(client, db):
    _maak_vrijwilliger(db, "vrijwilliger", "voorraad")
    _login(client, "vrijwilliger")
    normaal = client.get("/").data.decode()
    assert "zijbalk-favorieten" not in normaal and "grote-knoppen" not in normaal

    tekst = client.get("/account/voorkeuren").data.decode()
    assert "Eenvoudige weergave" in tekst and 'name="favoriet" value="tellen"' in tekst
    assert "Uitloggen op alle andere toestellen" in tekst.split("<main>")[-1]  # staat nu echt op de pagina
    assert "Uitloggen" not in tekst.split("<title>")[1].split("</title>")[0]  # en niet meer in de titel

    client.post("/account/weergave", data={"csrf_token": _csrf(client), "eenvoudig": "on",
                                           "favoriet": ["boeken", "tellen", "kluis_tellen"]})
    rij = db.execute("SELECT eenvoudig, favorieten FROM gebruikers WHERE naam = 'vrijwilliger'").fetchone()
    assert rij["eenvoudig"] == 1 and rij["favorieten"] == "boeken,tellen"  # de kluis mag deze vrijwilliger niet zien

    overzicht = client.get("/").data.decode()
    assert 'class="app-zijbalk eenvoudig"' in overzicht and "Alle onderdelen" in overzicht
    knoppen = overzicht.split('class="grote-knoppen"')[1].split("</div>")[0]
    assert knoppen.index('href="/boeken"') < knoppen.index('href="/tellen"')


# ---------- Evenementen ----------


def test_een_evenement_maakt_de_dag_open_en_drukker(db):
    zondag = date(2026, 10, 18)  # standaard dicht
    kalender = voorspelling.lees_kalender(db, zondag, zondag)
    assert not kalender[zondag]["open"]
    db.execute("INSERT INTO evenementen (datum, naam, aangemaakt_op) VALUES (?, 'Jeugdtoernooi', '2026-10-13 10:00')", (zondag.isoformat(),))
    db.commit()
    kalender = voorspelling.lees_kalender(db, zondag, zondag)
    assert kalender[zondag]["open"] and kalender[zondag]["evenementen"] == 1

    b = voorspelling.blootstelling(datetime(2026, 10, 18, 12), datetime(2026, 10, 19, 12), kalender)
    assert b["E"] == 1.0 and b["D"] == 1.0
    assert voorspelling.drukte(b, dict(voorspelling.PRIOR)) == 2.0  # aanname: dubbel zo druk


def test_het_model_leert_het_evenement_effect_bij():
    # Twee producten, gewone dagen verkopen 10, evenementdagen 40: het effect moet ruim boven de aanname uitkomen.
    rijen = []
    for pid in (1, 2):
        for i in range(12):
            evenement = i % 4 == 0
            start = datetime(2026, 6, 1, 12) + timedelta(days=i)
            rijen.append({"pid": pid, "tid": i, "start": start, "einde": start + timedelta(days=1), "V": 40 if evenement else 10,
                          "afgekapt": False, "w": 1.0, "prijs": 2.0,
                          "b": {"D": 1.0, "M": 0.0, "T": 0.0, "S": 0.0, "W": 0.0, "E": 1.0 if evenement else 0.0}})
    effecten, _, informatie = voorspelling.pas_model_aan(rijen)
    assert informatie["evenement"] > 0.3 and effecten["evenement"] > 2.0


def test_evenementen_beheren_op_de_prognosepagina(ingelogde_client, db):
    resp = ingelogde_client.post("/prognose/evenement", data={"csrf_token": _csrf(ingelogde_client), "datum": "2026-11-01",
                                                               "naam": "  Kampioens   feest "}, follow_redirects=True)
    assert "Kampioens feest op zondag 1-11-2026 telt mee" in resp.data.decode()
    e = db.execute("SELECT * FROM evenementen").fetchone()
    assert (e["datum"], e["naam"]) == ("2026-11-01", "Kampioens feest")
    assert "Kampioens feest" in ingelogde_client.get("/prognose").data.decode()
    assert "Geef het evenement een naam" in ingelogde_client.post(
        "/prognose/evenement", data={"csrf_token": _csrf(ingelogde_client), "datum": "2026-11-02", "naam": ""}, follow_redirects=True
    ).data.decode()
    ingelogde_client.post(f"/prognose/evenement/{e['id']}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT COUNT(*) FROM evenementen").fetchone()[0] == 0


def test_een_nieuw_evenement_verandert_de_vingerafdruk(db):
    voor = voorspelling.historie_vingerafdruk(db)
    db.execute("INSERT INTO evenementen (datum, naam, aangemaakt_op) VALUES ('2026-11-01', 'Feest', '2026-10-13 10:00')")
    db.commit()
    assert voorspelling.historie_vingerafdruk(db) != voor


def test_een_rustige_activiteit_telt_als_een_klein_deel_van_een_dag(db):
    zondag, woensdag = date(2026, 10, 18), date(2026, 10, 14)  # zondag dicht, woensdag een gewone verkoopdag
    for dag in (zondag, woensdag):
        db.execute("INSERT INTO evenementen (datum, naam, soort, aangemaakt_op) VALUES (?, 'Lunch JO17', 'rustig', '2026-10-13 10:00')",
                   (dag.isoformat(),))
    db.commit()
    kalender = voorspelling.lees_kalender(db, woensdag, zondag)
    assert kalender[zondag]["open"] and kalender[zondag]["rustig"] and kalender[zondag]["evenementen"] == 0
    assert not kalender[woensdag]["rustig"]  # op een gewone verkoopdag verandert een lunch niets

    b = voorspelling.blootstelling(datetime(2026, 10, 18, 12), datetime(2026, 10, 19, 12), kalender)
    assert b["R"] == 1.0
    assert abs(voorspelling.drukte(b, dict(voorspelling.PRIOR)) - 0.3) < 1e-9  # aanname: 30% van een gewone dag


def test_een_rustige_activiteit_toevoegen_op_de_prognosepagina(ingelogde_client, db):
    resp = ingelogde_client.post("/prognose/evenement", data={"csrf_token": _csrf(ingelogde_client), "datum": "2026-11-01",
                                                               "naam": "Lunch JO17", "soort": "rustig"}, follow_redirects=True)
    assert "telt mee in de prognose als rustige dag" in resp.data.decode()
    assert db.execute("SELECT soort FROM evenementen").fetchone()[0] == "rustig"
    tekst = ingelogde_client.get("/prognose").data.decode()
    assert "Lunch JO17" in tekst and ">rustig</span>" in tekst


# ---------- Groepen (bijv. 'UC') ----------


def test_de_groep_volgt_uit_de_naam_als_hij_al_bekend_is(db):
    from routes.prognose import groep_voor

    assert groep_voor(db, "UC Lunch", "") is None  # nog niet bekend
    db.execute("INSERT INTO evenementen (datum, naam, soort, groep, aangemaakt_op) VALUES ('2026-10-01', 'UC Lunch', 'rustig', 'UC', 'x')")
    db.execute("INSERT INTO evenementen (datum, naam, soort, groep, aangemaakt_op) VALUES ('2026-10-02', 'UC JO17 lunch', 'rustig', 'UC JO17', 'x')")
    db.commit()
    assert groep_voor(db, "UC Activiteit", "") == "UC"
    assert groep_voor(db, "uc jo17 training", "") == "UC JO17"  # de langste bekende groep wint
    assert groep_voor(db, "Bestuursvergadering", "") is None
    assert groep_voor(db, "Iets", " uc ") == "UC"  # zelf ingevuld: dezelfde schrijfwijze als eerder


def test_de_groep_doet_mee_op_de_dagen_waar_het_evenement_telt(db):
    zondag, woensdag = date(2026, 10, 18), date(2026, 10, 14)
    for dag, soort in ((zondag, "rustig"), (woensdag, "rustig")):
        db.execute("INSERT INTO evenementen (datum, naam, soort, groep, aangemaakt_op) VALUES (?, 'UC Lunch', ?, 'UC', 'x')",
                   (dag.isoformat(), soort))
    db.commit()
    kalender = voorspelling.lees_kalender(db, woensdag, zondag)
    assert kalender[zondag]["groepen"] == ("groep:uc",) and kalender[woensdag]["groepen"] == ()
    b = voorspelling.blootstelling(datetime(2026, 10, 18, 12), datetime(2026, 10, 19, 12), kalender)
    assert b["G"] == {"groep:uc": 1.0}
    effecten = dict(voorspelling.PRIOR, **{"groep:uc": 0.5})
    assert abs(voorspelling.drukte(b, effecten) - 0.8) < 1e-9  # 30% van een dag plus de bijstelling voor UC


def test_het_model_leert_dat_uc_drukker_is_dan_een_gewone_rustige_dag():
    rijen = []
    for pid in (1, 2):
        for i in range(16):
            soort = ("uc" if i % 4 == 0 else "ander") if i % 2 == 0 else None
            start = datetime(2026, 6, 1, 12) + timedelta(days=i)
            b = {"D": 1.0, "M": 0.0, "T": 0.0, "S": 0.0, "W": 0.0, "E": 0.0, "R": 1.0 if soort else 0.0,
                 "G": {"groep:uc": 1.0} if soort == "uc" else {}}
            verkocht = 10 if soort is None else 9 if soort == "uc" else 3  # een UC-dag bijna zo druk als een gewone dag
            rijen.append({"pid": pid, "tid": i, "start": start, "einde": start + timedelta(days=1), "V": verkocht,
                          "afgekapt": False, "w": 1.0, "prijs": 2.0, "b": b})
    effecten, _, informatie = voorspelling.pas_model_aan(rijen)
    assert informatie["groep:uc"] > 0.3
    assert effecten["groep:uc"] > 0.3 and -0.9 < effecten["rustig"] < -0.5


def test_een_evenement_met_groep_toevoegen(ingelogde_client, db):
    resp = ingelogde_client.post("/prognose/evenement", data={"csrf_token": _csrf(ingelogde_client), "datum": "2026-11-01",
                                                               "naam": "UC Lunch", "soort": "rustig", "groep": "UC"}, follow_redirects=True)
    assert "als rustige dag, bij UC" in resp.data.decode()
    ingelogde_client.post("/prognose/evenement", data={"csrf_token": _csrf(ingelogde_client), "datum": "2026-11-08",
                                                        "naam": "UC Activiteit", "soort": "druk", "groep": ""})
    assert [r[0] for r in db.execute("SELECT groep FROM evenementen ORDER BY id")] == ["UC", "UC"]
    tekst = ingelogde_client.get("/prognose").data.decode()
    assert '<option value="UC">' in tekst and "&middot; UC" in tekst


def test_evenementen_in_de_komende_7_dagen_staan_op_het_overzicht(ingelogde_client, db):
    from helpers.tijd import vandaag_amsterdam

    vandaag = vandaag_amsterdam()
    for delta, naam in ((1, "UC Lunch"), (3, "Jeugdtoernooi"), (9, "Te ver weg")):
        db.execute("INSERT INTO evenementen (datum, naam, soort, groep, aangemaakt_op) VALUES (?, ?, ?, ?, 'x')",
                   ((vandaag + timedelta(days=delta)).isoformat(), naam, "rustig" if "Lunch" in naam else "druk",
                    "UC" if "UC" in naam else None))
    db.commit()
    tekst = ingelogde_client.get("/").data.decode()
    assert "UC Lunch morgen" in tekst and "Rustige activiteit: telt mee" in tekst
    assert "Jeugdtoernooi" in tekst and "Te ver weg" not in tekst
