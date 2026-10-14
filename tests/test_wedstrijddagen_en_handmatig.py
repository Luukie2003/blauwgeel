"""Een weekdag die alleen open is bij een thuiswedstrijd (bijvoorbeeld zaterdag), en zelf een thuiswedstrijd toevoegen
die de teamagenda (nog) niet heeft."""

from datetime import date, timedelta

from conftest import stel_csrf_token_in as _csrf
from test_afgelaste_wedstrijden import _ics, _ververs, _wedstrijd
from test_secties_rechten import _login, _maak_vrijwilliger

from activiteiten import bouw_agenda
from voorspelling import dag_is_open, lees_kalender, lees_wedstrijddagen, wedstrijden_op_gesloten_dagen

ZATERDAG = date(2026, 10, 17)
TEAM = "Blauw Geel'15 3"


def _alleen_zaterdag_bij_wedstrijd(db):
    db.execute("UPDATE instellingen SET verkoopdagen = '2', verkoopdagen_wedstrijd = '5' WHERE id = 1")
    db.commit()


def _volgende_zaterdag(na=1):
    dag = date.today() + timedelta(days=na)
    return dag + timedelta(days=(5 - dag.weekday()) % 7)


# ---------- De instelling ----------


def test_standaard_is_er_geen_dag_alleen_bij_een_wedstrijd(db):
    assert lees_wedstrijddagen(db) == set()


def test_zaterdag_is_alleen_open_als_er_een_thuiswedstrijd_is():
    assert not dag_is_open(ZATERDAG, {2}, {}, {5}, thuiswedstrijd=False)
    assert dag_is_open(ZATERDAG, {2}, {}, {5}, thuiswedstrijd=True)
    assert not dag_is_open(ZATERDAG, {2}, {ZATERDAG.isoformat(): False}, {5}, thuiswedstrijd=True)  # toch dicht
    assert dag_is_open(ZATERDAG, {2}, {ZATERDAG.isoformat(): True}, {5}, thuiswedstrijd=False)  # toch open


def test_kalender_zet_een_zaterdag_zonder_wedstrijd_dicht(db):
    _alleen_zaterdag_bij_wedstrijd(db)
    kalender = lees_kalender(db, ZATERDAG, ZATERDAG + timedelta(days=7))
    assert kalender[ZATERDAG]["open"] is False
    assert kalender[ZATERDAG + timedelta(days=4)]["open"] is True  # woensdag blijft gewoon open

    _wedstrijd(db, ZATERDAG)
    assert lees_kalender(db, ZATERDAG, ZATERDAG)[ZATERDAG]["open"] is True


def test_een_afgelaste_wedstrijd_houdt_de_zaterdag_dicht(db):
    _alleen_zaterdag_bij_wedstrijd(db)
    _wedstrijd(db, ZATERDAG, afgelast=1, bron="handmatig")
    assert lees_kalender(db, ZATERDAG, ZATERDAG)[ZATERDAG]["open"] is False


def test_wedstrijd_op_een_wedstrijddag_hoeft_niet_voorgelegd(db):
    _alleen_zaterdag_bij_wedstrijd(db)
    zaterdag = _volgende_zaterdag()
    _wedstrijd(db, zaterdag)
    assert all(g["datum"] != zaterdag for g in wedstrijden_op_gesloten_dagen(db))


def test_agenda_toont_een_zaterdag_zonder_wedstrijd_niet_als_open(db):
    _alleen_zaterdag_bij_wedstrijd(db)
    vandaag = ZATERDAG - timedelta(days=5)  # maandag
    dagen = [d for w in bouw_agenda(db, vandaag, 14) for d in w["dagen"]]
    assert ZATERDAG.isoformat() not in [d["datum"] for d in dagen]

    _wedstrijd(db, ZATERDAG)
    dagen = {d["datum"]: d for w in bouw_agenda(db, vandaag, 14) for d in w["dagen"]}
    assert dagen[ZATERDAG.isoformat()]["open"] is True


# ---------- Instellen op de Prognose-pagina ----------


def test_per_weekdag_dicht_altijd_open_of_alleen_bij_een_wedstrijd(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/prognose/verkoopdagen",
        data={"csrf_token": _csrf(ingelogde_client), "dag_2": "altijd", "dag_5": "wedstrijd", "dag_6": ""},
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT verkoopdagen, verkoopdagen_wedstrijd FROM instellingen").fetchone()
    assert (rij["verkoopdagen"], rij["verkoopdagen_wedstrijd"]) == ("2", "5")

    tekst = ingelogde_client.get("/prognose").data.decode()
    assert "woensdag; zaterdag alleen bij een thuiswedstrijd" in tekst
    assert 'value="wedstrijd" selected' in tekst


def test_uitzondering_op_een_wedstrijddag_is_zoals_gewoonlijk_als_het_klopt_met_de_wedstrijd(ingelogde_client, db):
    _alleen_zaterdag_bij_wedstrijd(db)
    zaterdag = _volgende_zaterdag()
    db.execute("INSERT INTO verkoop_uitzonderingen (datum, open) VALUES (?, 0)", (zaterdag.isoformat(),))
    db.commit()
    assert "(zoals gewoonlijk)" in ingelogde_client.get("/prognose").data.decode()  # dicht zonder wedstrijd

    _wedstrijd(db, zaterdag)
    assert "(zoals gewoonlijk)" not in ingelogde_client.get("/prognose").data.decode()  # dicht ondanks de wedstrijd


def test_minstens_een_dag_altijd_open(ingelogde_client, db):
    ingelogde_client.post("/prognose/verkoopdagen", data={"csrf_token": _csrf(ingelogde_client), "dag_5": "wedstrijd"})
    rij = db.execute("SELECT verkoopdagen, verkoopdagen_wedstrijd FROM instellingen").fetchone()
    assert (rij["verkoopdagen"], rij["verkoopdagen_wedstrijd"]) == ("2,5", "")


# ---------- Zelf een thuiswedstrijd toevoegen ----------


def _toevoegen(client, **velden):
    return client.post("/wedstrijden/toevoegen", data={"csrf_token": _csrf(client), **velden})


def test_thuiswedstrijd_zelf_toevoegen(ingelogde_client, db):
    datum = (date.today() + timedelta(days=30)).isoformat()
    resp = _toevoegen(ingelogde_client, datum=datum, tijd="14:30", team=TEAM, omschrijving="Blauw Geel'15 3 - VV Test")
    assert resp.status_code == 302
    rij = db.execute("SELECT * FROM wedstrijden").fetchone()
    assert (rij["datum"], rij["tijd"], rij["team"], rij["thuis"], rij["handmatig"], rij["afgelast"]) == (
        datum, "14:30", TEAM, 1, 1, 0
    )
    # Ook een wedstrijd over een maand staat op de pagina, met de knop om 'm weer weg te halen.
    tekst = ingelogde_client.get("/wedstrijden").data.decode()
    assert "VV Test" in tekst and "zelf toegevoegd" in tekst and f"/wedstrijden/{rij['id']}/verwijderen" in tekst


def test_zonder_team_en_omschrijving_krijgt_hij_een_naam(ingelogde_client, db):
    _toevoegen(ingelogde_client, datum="2026-10-31")
    rij = db.execute("SELECT team, omschrijving, tijd FROM wedstrijden").fetchone()
    assert (rij["team"], rij["omschrijving"], rij["tijd"]) == ("Overig", "Thuiswedstrijd", None)


def test_foute_invoer_en_dubbel_worden_geweigerd(ingelogde_client, db):
    _toevoegen(ingelogde_client, datum="geen datum")
    _toevoegen(ingelogde_client, datum="2026-10-31", tijd="25:00")
    assert db.execute("SELECT COUNT(*) FROM wedstrijden").fetchone()[0] == 0
    _toevoegen(ingelogde_client, datum="2026-10-31")
    resp = _toevoegen(ingelogde_client, datum="2026-10-31")
    assert db.execute("SELECT COUNT(*) FROM wedstrijden").fetchone()[0] == 1
    assert resp.status_code == 302


def test_alleen_een_zelf_toegevoegde_wedstrijd_kan_weg(ingelogde_client, db):
    uit_agenda = _wedstrijd(db, ZATERDAG)
    _toevoegen(ingelogde_client, datum="2026-10-31")
    zelf = db.execute("SELECT id FROM wedstrijden WHERE handmatig = 1").fetchone()["id"]

    ingelogde_client.post(f"/wedstrijden/{uit_agenda}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    ingelogde_client.post(f"/wedstrijden/{zelf}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    assert [r["id"] for r in db.execute("SELECT id FROM wedstrijden")] == [uit_agenda]


def test_zelf_toegevoegde_wedstrijd_opent_de_zaterdag(ingelogde_client, db):
    _alleen_zaterdag_bij_wedstrijd(db)
    _toevoegen(ingelogde_client, datum=ZATERDAG.isoformat())
    assert lees_kalender(db, ZATERDAG, ZATERDAG)[ZATERDAG]["open"] is True


def test_toevoegen_hoort_bij_de_voorraad_sectie(client, db):
    _maak_vrijwilliger(db, "kassahulp", "kassa")
    _login(client, "kassahulp")
    _toevoegen(client, datum="2026-10-31")
    assert db.execute("SELECT COUNT(*) FROM wedstrijden").fetchone()[0] == 0
    assert "Thuiswedstrijd zelf toevoegen" not in client.get("/wedstrijden").data.decode()


# ---------- De koppeling met de teamagenda ----------


def test_agenda_vervangt_de_zelf_toegevoegde_wedstrijd_van_hetzelfde_team(app, ingelogde_client, db, monkeypatch):
    dag = date.today() + timedelta(days=5)
    _toevoegen(ingelogde_client, datum=dag.isoformat(), team=TEAM)
    _toevoegen(ingelogde_client, datum=dag.isoformat(), omschrijving="Jeugd thuis")  # ander team: blijft staan

    _ververs(app, db, monkeypatch, _ics((dag.strftime("%Y%m%d"), "Blauw Geel'15 3-Roden 4")))
    rijen = {(r["omschrijving"], r["handmatig"]) for r in db.execute("SELECT * FROM wedstrijden WHERE datum = ?", (dag.isoformat(),))}
    assert rijen == {("Blauw Geel'15 3-Roden 4", 0), ("Jeugd thuis", 1)}


def test_agenda_zet_een_zelf_toegevoegde_wedstrijd_niet_op_afgelast(app, ingelogde_client, db, monkeypatch):
    dag = date.today() + timedelta(days=5)
    _toevoegen(ingelogde_client, datum=dag.isoformat(), team=TEAM)
    later = (date.today() + timedelta(days=20)).strftime("%Y%m%d")  # de feed loopt verder, maar zonder deze dag
    _ververs(app, db, monkeypatch, _ics((later, "Blauw Geel'15 3-Roden 4")))
    rij = db.execute("SELECT afgelast FROM wedstrijden WHERE handmatig = 1").fetchone()
    assert rij is not None and rij["afgelast"] == 0
