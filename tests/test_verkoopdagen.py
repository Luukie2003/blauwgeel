"""Verkoopdagen: de kantine verkoopt standaard alleen op woensdag en zaterdag, met
uitzonderingen per datum. De prognose en de weekomzet rekenen alleen met open dagen."""

from datetime import date, datetime, timedelta

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger
from test_voorspelling import _bouw_geschiedenis, _product, _wedstrijd

from voorspelling import (
    blootstelling,
    dag_is_open,
    lees_kalender,
    lees_verkoopdagen,
    maak_prognose,
    omzet_per_dag,
    wedstrijden_op_gesloten_dagen,
)

MAANDAG = datetime(2026, 9, 7, 12, 0)  # een maandag
WEEK_TOT = MAANDAG + timedelta(days=7)


def _uitzondering(db, dag, open_, opmerking=None):
    db.execute(
        "INSERT OR REPLACE INTO verkoop_uitzonderingen (datum, open, opmerking) VALUES (?, ?, ?)",
        (dag.isoformat(), 1 if open_ else 0, opmerking),
    )
    db.commit()


def _open_dagen(db, tekst):
    db.execute("UPDATE instellingen SET verkoopdagen = ? WHERE id = 1", (tekst,))
    db.commit()


# ---------- De vaste dagen en de uitzonderingen ----------


def test_standaard_wordt_er_op_woensdag_en_zaterdag_verkocht(db):
    weekdagen, uitzonderingen = lees_verkoopdagen(db)
    assert weekdagen == {2, 5} and uitzonderingen == {}
    assert dag_is_open(date(2026, 9, 9), weekdagen, uitzonderingen)  # woensdag
    assert dag_is_open(date(2026, 9, 12), weekdagen, uitzonderingen)  # zaterdag
    assert not dag_is_open(date(2026, 9, 11), weekdagen, uitzonderingen)  # vrijdag
    assert not dag_is_open(date(2026, 9, 13), weekdagen, uitzonderingen)  # zondag


def test_uitzonderingen_wijken_af_van_de_vaste_dagen(db):
    _uitzondering(db, date(2026, 9, 13), True)  # zondag toch open
    _uitzondering(db, date(2026, 9, 9), False)  # woensdag dicht
    weekdagen, uitzonderingen = lees_verkoopdagen(db)
    assert dag_is_open(date(2026, 9, 13), weekdagen, uitzonderingen)
    assert not dag_is_open(date(2026, 9, 9), weekdagen, uitzonderingen)


def test_onleesbare_instelling_valt_terug_op_woensdag_en_zaterdag(db):
    _open_dagen(db, "onzin,,9")
    assert lees_verkoopdagen(db)[0] == {2, 5}


def test_blootstelling_telt_alleen_open_dagen_mee(db):
    kalender = lees_kalender(db, date(2026, 9, 5), date(2026, 9, 20))
    assert blootstelling(MAANDAG, WEEK_TOT, kalender)["D"] == 2.0  # woensdag en zaterdag

    _uitzondering(db, date(2026, 9, 13), True)
    kalender = lees_kalender(db, date(2026, 9, 5), date(2026, 9, 20))
    assert blootstelling(MAANDAG, WEEK_TOT, kalender)["D"] == 3.0

    _uitzondering(db, date(2026, 9, 9), False)
    kalender = lees_kalender(db, date(2026, 9, 5), date(2026, 9, 20))
    b = blootstelling(MAANDAG, WEEK_TOT, kalender)
    assert b["D"] == 2.0 and b["T"] == 0.0  # de woensdag (training) telt niet meer mee


# ---------- Prognose ----------


def test_prognose_rekent_alleen_met_open_dagen(db):
    pid = _product(db, "Pils", voorraad=500)
    laatste = _bouw_geschiedenis(db, {pid: 10}, open_dagen="2,5")
    prognose = maak_prognose(db, dagen=7, nu=laatste + timedelta(hours=1))

    assert prognose["beschikbaar"]
    dagen = prognose["dagen_overzicht"]
    gesloten = [d for d in dagen if not d["open"]]
    open_ = [d for d in dagen if d["open"]]
    assert all(d["omzet"] == 0 and d["drukte"] == 0 for d in gesloten)
    assert {d["datum"].weekday() for d in open_} <= {2, 5} and open_
    # Zo'n 2 open dagen van ~10 per dag, niet 7 dagen: ruim onder de 40.
    verwacht = prognose["producten"][0]["verwacht"]
    assert 12 < verwacht < 40


def test_prognose_met_alleen_gesloten_dagen_geeft_niets_verwachts(db):
    pid = _product(db, "Pils", voorraad=500)
    laatste = _bouw_geschiedenis(db, {pid: 10}, open_dagen="2,5")
    # Zondagavond: de komende 2 dagen (maandag en dinsdag) zijn dicht.
    zondag = datetime.combine(laatste.date() + timedelta(days=(6 - laatste.weekday()) % 7 or 7), datetime.min.time())
    zondag = zondag.replace(hour=20)
    prognose = maak_prognose(db, dagen=3, nu=zondag)
    assert prognose["beschikbaar"]
    assert prognose["totaal"]["omzet"] == 0 or all(d["omzet"] == 0 for d in prognose["dagen_overzicht"] if not d["open"])


def test_het_model_leert_per_open_dag_en_niet_per_kalenderdag(db):
    pid = _product(db, "Pils", voorraad=500)
    laatste = _bouw_geschiedenis(db, {pid: 10}, open_dagen="2,5")
    open_model = maak_prognose(db, dagen=7, nu=laatste + timedelta(hours=1))["producten"][0]["verwacht"]

    _open_dagen(db, "0,1,2,3,4,5,6")  # dezelfde tellingen, maar nu "elke dag open"
    alle_dagen = maak_prognose(db, dagen=7, nu=laatste + timedelta(hours=1))["producten"][0]["verwacht"]
    # Met 2 open dagen per week verkoopt een open dag veel meer dan een van 7: de snelheid per dag
    # is dan zo'n 3,5x hoger, maar de verwachting voor de week blijft in dezelfde orde.
    assert 0.5 < open_model / alle_dagen < 2.0


# ---------- Weekomzet ----------


def test_omzet_wordt_alleen_over_open_dagen_verdeeld(db):
    pid = _product(db, "Pils", voorraad=500, prijs=2.0)
    _bouw_geschiedenis(db, {pid: 10}, open_dagen="2,5")
    omzet, eerste, laatste = omzet_per_dag(db, nu=datetime(2026, 12, 1))
    assert omzet and all(dag.weekday() in (2, 5) for dag in omzet)
    verkocht = db.execute("SELECT SUM(verkocht * verkoopprijs) FROM telling_regels").fetchone()[0]
    assert abs(sum(omzet.values()) - verkocht) < 1e-6


def test_verkoop_op_alleen_gesloten_dagen_verdwijnt_niet_uit_de_omzet(db):
    pid = _product(db, "Pils", prijs=2.0)
    for datum, geteld, verkocht in (("2026-09-14 14:00", 100, 0), ("2026-09-15 14:00", 70, 30)):
        cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (datum,))
        db.execute(
            """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
               VALUES (?, ?, ?, ?, ?, 2.0)""",
            (cur.lastrowid, pid, geteld + verkocht, geteld, verkocht),
        )
    db.commit()  # maandag 14.00 uur tot dinsdag 14.00 uur: allebei gesloten
    omzet, _, _ = omzet_per_dag(db, nu=datetime(2026, 9, 20))
    assert abs(sum(omzet.values()) - 60.0) < 1e-6


# ---------- Wedstrijden op een gesloten dag ----------


def test_wedstrijd_op_zondag_wordt_voorgelegd_tot_je_kiest(db):
    nu = datetime(2026, 9, 16, 12, 0)
    _wedstrijd(db, date(2026, 9, 13))  # zondag, geweest
    _wedstrijd(db, date(2026, 9, 19))  # zaterdag: gewoon open
    _wedstrijd(db, date(2026, 9, 20))  # zondag, komend

    gesloten = wedstrijden_op_gesloten_dagen(db, nu=nu)
    assert [(g["datum"], g["toekomst"]) for g in gesloten] == [(date(2026, 9, 13), False), (date(2026, 9, 20), True)]

    _uitzondering(db, date(2026, 9, 13), True, "Thuiswedstrijd")
    assert [g["datum"] for g in wedstrijden_op_gesloten_dagen(db, nu=nu)] == [date(2026, 9, 20)]


def test_open_gezette_wedstrijddag_telt_mee_als_wedstrijd_en_open(db):
    _wedstrijd(db, date(2026, 9, 13))  # zondag
    _uitzondering(db, date(2026, 9, 13), True)
    kalender = lees_kalender(db, date(2026, 9, 5), date(2026, 9, 20))
    b = blootstelling(MAANDAG, WEEK_TOT, kalender)
    assert b["D"] == 3.0 and b["M"] == 1.0


# ---------- Instellen op de Prognose-pagina ----------


def test_prognosepagina_toont_de_verkoopdagen(ingelogde_client, db):
    _wedstrijd(db, date.today() + timedelta(days=(6 - date.today().weekday()) or 7))  # eerstvolgende zondag
    tekst = ingelogde_client.get("/prognose").data.decode()
    assert "Verkoopdagen:" in tekst and "woensdag, zaterdag" in tekst
    assert "Thuiswedstrijd op een dag waarop je normaal niet verkoopt" in tekst and "Ja, open" in tekst


def test_vaste_dagen_opslaan_en_minstens_een_dag_verplicht(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/prognose/verkoopdagen",
        data={"csrf_token": _csrf(ingelogde_client), "dag_2": "on", "dag_4": "on", "dag_5": "on"},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT verkoopdagen FROM instellingen").fetchone()["verkoopdagen"] == "2,4,5"

    ingelogde_client.post("/prognose/verkoopdagen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT verkoopdagen FROM instellingen").fetchone()["verkoopdagen"] == "2,4,5"


def test_uitzondering_toevoegen_aanpassen_en_verwijderen(ingelogde_client, db):
    data = {"csrf_token": _csrf(ingelogde_client), "datum": "2026-10-11", "status": "open", "opmerking": "Zondagwedstrijd"}
    ingelogde_client.post("/prognose/uitzondering", data=data)
    rij = db.execute("SELECT * FROM verkoop_uitzonderingen").fetchone()
    assert rij["datum"] == "2026-10-11" and rij["open"] == 1 and rij["opmerking"] == "Zondagwedstrijd"

    ingelogde_client.post("/prognose/uitzondering", data={**data, "status": "dicht", "opmerking": ""})
    rij = db.execute("SELECT * FROM verkoop_uitzonderingen").fetchone()
    assert rij["open"] == 0 and rij["opmerking"] is None

    ingelogde_client.post("/prognose/uitzondering", data={**data, "datum": "geen datum"})
    assert db.execute("SELECT COUNT(*) AS n FROM verkoop_uitzonderingen").fetchone()["n"] == 1

    ingelogde_client.post("/prognose/uitzondering/2026-10-11/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT COUNT(*) AS n FROM verkoop_uitzonderingen").fetchone()["n"] == 0


def test_verkoopdagen_instellen_hoort_bij_de_voorraad_sectie(client, db):
    _maak_vrijwilliger(db, "kassahulp", "kassa")
    _login(client, "kassahulp")
    resp = client.post("/prognose/verkoopdagen", data={"csrf_token": _csrf(client), "dag_0": "on"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
    assert db.execute("SELECT verkoopdagen FROM instellingen").fetchone()["verkoopdagen"] == "2,5"
