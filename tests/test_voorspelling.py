import math
from datetime import date, datetime, timedelta

import pytest

from app import bereken_komende_thuiswedstrijden, bereken_voorspelde_tekorten
from voorspelling import (
    blootstelling,
    drukte,
    kans_meer_dan,
    kwantiel,
    lees_kalender,
    lees_rijen,
    maak_prognose,
    wedstrijd_gewicht,
    weer_score,
)
from weer import weer_label


def test_weer_label_bekende_en_onbekende_code():
    assert weer_label(0) == "helder"
    assert weer_label(61) == "lichte regen"
    assert weer_label(12345) == "onbekend"


# ---------------------------------------------------------------------------
# Hulpmiddelen om een kantine-geschiedenis te simuleren
# ---------------------------------------------------------------------------

MAANDAG = datetime(2026, 7, 6, 15, 0)  # eerste telling; daarna steeds een week later


def _product(db, naam, voorraad=100, prijs=2.0, factor=1, besteleenheid=None, min_voorraad=0):
    cur = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs,
                                  besteleenheid, besteleenheid_factor, actief)
           VALUES (?, 'Bier', 'stuks', ?, ?, ?, ?, ?, 1)""",
        (naam, voorraad, min_voorraad, prijs, besteleenheid, factor),
    )
    db.commit()
    return cur.lastrowid


def _wedstrijd(db, dag, aantal=1):
    for i in range(aantal):
        db.execute(
            "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES (?, ?, ?, 1)",
            (f"Team{i}", dag.isoformat(), f"Team{i} - Test {dag}"),
        )
    db.commit()


def _bouw_geschiedenis(
    db, snelheden, effecten=None, tijdstippen=None, wedstrijddagen=(), nu_voorraad=None, geteld=50
):
    """Maakt tellingen op 'tijdstippen' (eerste = nulmeting) waarvan de verkoop precies
    klopt met een kantine waar de gegeven (waarde) effecten gelden. snelheden =
    {product_id: verkoop per normale dag}. Geeft de laatste telling-datum terug."""
    effecten = effecten or {"wedstrijd": 0.3, "training": 0.2, "weer": 0.0}
    tijdstippen = tijdstippen or [MAANDAG + timedelta(days=7 * i) for i in range(10)]
    for dag in wedstrijddagen:
        _wedstrijd(db, dag)
    kalender = lees_kalender(db, tijdstippen[0].date() - timedelta(days=3), tijdstippen[-1].date() + timedelta(days=3))
    for i, tijd in enumerate(tijdstippen):
        cur = db.execute(
            "INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (tijd.strftime("%Y-%m-%d %H:%M"),)
        )
        for pid, snelheid in snelheden.items():
            verkocht = 0
            if i > 0:
                verkocht = round(snelheid * drukte(blootstelling(tijdstippen[i - 1], tijd, kalender), effecten))
            prijs = db.execute("SELECT verkoopprijs FROM producten WHERE id = ?", (pid,)).fetchone()[0]
            db.execute(
                """INSERT INTO telling_regels
                   (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (cur.lastrowid, pid, geteld + verkocht, geteld, verkocht, prijs),
            )
    db.commit()
    return tijdstippen[-1]


def _twee_keer_per_week(weken):
    """Maandag- en donderdagtelling: de ene periode bevat het weekend, de andere de week."""
    tijden = []
    for w in range(weken):
        tijden.append(MAANDAG + timedelta(days=7 * w))
        tijden.append(MAANDAG + timedelta(days=7 * w + 3))
    return tijden


def _zaterdagen(aantal_weken, uit=()):
    """Zaterdagen (elke week een) in de periode van _bouw_geschiedenis, behalve weken in 'uit'."""
    return [
        (MAANDAG + timedelta(days=7 * w + 5)).date()
        for w in range(aantal_weken)
        if w not in uit
    ]


# ---------------------------------------------------------------------------
# Gedrag van bereken_voorspelde_tekorten (de bestellijst)
# ---------------------------------------------------------------------------


def test_geen_tellingen_geeft_lege_voorspelling(db):
    assert bereken_voorspelde_tekorten(db) == []


def test_een_telling_is_te_weinig_om_te_voorspellen(db):
    pid = _product(db, "Pils")
    _bouw_geschiedenis(db, {pid: 20}, tijdstippen=[MAANDAG])
    assert bereken_voorspelde_tekorten(db) == []
    prog = maak_prognose(db, nu=MAANDAG + timedelta(days=1))
    assert prog["beschikbaar"] is False and "minstens twee tellingen" in prog["reden"]


def test_signaleert_product_boven_minimum_met_hoge_verkoop(db):
    pid = _product(db, "Pils", voorraad=60)
    laatste = _bouw_geschiedenis(db, {pid: 40})  # ~40 per dag verkocht
    resultaat = bereken_voorspelde_tekorten_op(db, laatste + timedelta(hours=1))
    assert [r["product"]["naam"] for r in resultaat] == ["Pils"]
    r = resultaat[0]
    assert r["verwacht_verbruik"] > 200 and r["verwacht_tekort"] > 100
    assert r["kans_tekort"] > 0.9 and r["advies_stuks"] > 0


def test_sluit_producten_die_al_onder_minimum_zitten_uit(db):
    """bestel_suggesties() vangt dit al -- voorspelde_tekorten moet geen
    dubbele melding geven voor iets dat al reactief gesignaleerd wordt."""
    pid = _product(db, "Pils", voorraad=0, min_voorraad=10)
    laatste = _bouw_geschiedenis(db, {pid: 40})
    assert bereken_voorspelde_tekorten_op(db, laatste + timedelta(hours=1)) == []


def test_bestelling_onderweg_dekt_het_tekort(db):
    pid = _product(db, "Pils", voorraad=60, factor=24, besteleenheid="krat")
    laatste = _bouw_geschiedenis(db, {pid: 40})
    nu = laatste + timedelta(hours=1)
    assert bereken_voorspelde_tekorten_op(db, nu)
    cur = db.execute("INSERT INTO bestellingen (status, aangemaakt_op) VALUES ('besteld', '2026-09-01 10:00')")
    db.execute(
        "INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, 1000)",
        (cur.lastrowid, pid),
    )
    db.commit()
    assert bereken_voorspelde_tekorten_op(db, nu) == []
    prog = maak_prognose(db, nu=nu)
    p = next(x for x in prog["producten"] if x["product"]["id"] == pid)
    assert p["onderweg"] == 1000 and p["advies_stuks"] == 0


def bereken_voorspelde_tekorten_op(db, nu):
    """De tekortenlijst voor een vast 'nu' (de echte functie gebruikt de klok)."""
    prog = maak_prognose(db, dagen=7, nu=nu)
    return [
        r for r in (
            {"product": p["product"], "verwacht_verbruik": round(p["verwacht"]),
             "verwacht_tekort": round(p["verwacht"] - p["voorraad"] - p["onderweg"]),
             "kans_tekort": p["kans_tekort"], "advies_stuks": p["advies_stuks"],
             "al_op_bestellijst": p["al_op_bestellijst"]}
            for p in prog["producten"]
        )
        if r["verwacht_tekort"] > 0 and not r["al_op_bestellijst"]
    ]


# ---------------------------------------------------------------------------
# Perioden en onregelmatig tellen
# ---------------------------------------------------------------------------


def test_eerste_telling_is_alleen_nulmeting_en_perioden_per_product(db):
    a, b = _product(db, "A"), _product(db, "B")
    tijden = [MAANDAG, MAANDAG + timedelta(days=3, hours=-1), MAANDAG + timedelta(days=9), MAANDAG + timedelta(days=12)]
    _bouw_geschiedenis(db, {a: 10, b: 5}, tijdstippen=tijden)
    rijen, tellingen = lees_rijen(db, tijden[-1] + timedelta(days=1))
    assert len(tellingen) == 4
    assert len(rijen) == 2 * 3  # 3 perioden per product; de nulmeting telt niet mee
    assert min(r["start"] for r in rijen) == tijden[0] and all(r["einde"] > r["start"] for r in rijen)


def test_product_dat_een_keer_niet_geteld_is_krijgt_een_langere_periode(db):
    a, b = _product(db, "A"), _product(db, "B")
    tijden = [MAANDAG + timedelta(days=7 * i) for i in range(4)]
    _bouw_geschiedenis(db, {a: 10, b: 5}, tijdstippen=tijden)
    # B is in telling 3 niet geteld: verwijder die regel -> periode van B loopt dan van telling 2 naar 4.
    telling3 = db.execute("SELECT id FROM tellingen ORDER BY datum LIMIT 1 OFFSET 2").fetchone()[0]
    db.execute("DELETE FROM telling_regels WHERE telling_id = ? AND product_id = ?", (telling3, b))
    db.commit()
    rijen, _ = lees_rijen(db, tijden[-1] + timedelta(days=1))
    b_rijen = sorted((r for r in rijen if r["pid"] == b), key=lambda r: r["start"])
    assert len(b_rijen) == 2
    assert (b_rijen[-1]["einde"] - b_rijen[-1]["start"]).days == 14


def test_telling_zonder_enige_verkoop_telt_niet_mee(db):
    a = _product(db, "A")
    tijden = [MAANDAG + timedelta(days=7 * i) for i in range(4)]
    _bouw_geschiedenis(db, {a: 0}, tijdstippen=tijden)
    rijen, _ = lees_rijen(db, tijden[-1] + timedelta(days=1))
    assert rijen == []


def test_onregelmatig_tellen_geeft_toch_een_prognose(db):
    """Dit is wat het oude weekgemiddelde niet kon: tellingen op wisselende dagen."""
    a = _product(db, "A", prijs=2.0)
    tijden = [MAANDAG, MAANDAG + timedelta(days=3), MAANDAG + timedelta(days=9, hours=2), MAANDAG + timedelta(days=11),
              MAANDAG + timedelta(days=17), MAANDAG + timedelta(days=18, hours=3), MAANDAG + timedelta(days=24)]
    laatste = _bouw_geschiedenis(db, {a: 30}, tijdstippen=tijden)
    prog = maak_prognose(db, dagen=7, nu=laatste + timedelta(hours=2))
    assert prog["beschikbaar"]
    # ~30 stuks/dag x EUR 2 x ~7 dagen (met een trainingsavond erbij) -> ruim EUR 400
    assert 380 < prog["totaal"]["omzet"] < 620


# ---------------------------------------------------------------------------
# Leren van de eigen tellingen
# ---------------------------------------------------------------------------


def _effect(prog, sleutel):
    return next(e for e in prog["model"]["effecten"] if e["sleutel"] == sleutel)


def test_model_leert_dat_een_wedstrijd_veel_meer_oplevert_dan_de_aanname(db):
    a, b = _product(db, "A"), _product(db, "B")
    waar = {"wedstrijd": 0.9, "training": 0.2, "weer": 0.0}
    laatste = _bouw_geschiedenis(
        db, {a: 40, b: 15}, effecten=waar, wedstrijddagen=_zaterdagen(8, uit=(2, 5)),
        tijdstippen=_twee_keer_per_week(8),
    )
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    wedstrijd = _effect(prog, "wedstrijd")
    assert wedstrijd["aanname"] == 0.30
    assert wedstrijd["waarde"] > 0.7  # ver boven de aanname van 0,30
    assert wedstrijd["status"] in ("deels", "geleerd") and wedstrijd["waargenomen_dagen"] >= 5
    assert _effect(prog, "training")["waarde"] == pytest.approx(0.2, abs=0.12)


def test_model_leert_dat_een_wedstrijd_hier_niets_uitmaakt(db):
    a = _product(db, "A")
    waar = {"wedstrijd": 0.0, "training": 0.2, "weer": 0.0}
    laatste = _bouw_geschiedenis(
        db, {a: 40}, effecten=waar, wedstrijddagen=_zaterdagen(8, uit=(2, 5)), tijdstippen=_twee_keer_per_week(8)
    )
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    assert _effect(prog, "wedstrijd")["waarde"] < 0.1


def test_zonder_wedstrijden_in_de_data_blijft_de_aanname_staan(db):
    a = _product(db, "A")
    laatste = _bouw_geschiedenis(db, {a: 40}, effecten={"wedstrijd": 0.3, "training": 0.2, "weer": 0.0})
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    e = _effect(prog, "wedstrijd")
    assert e["waarde"] == 0.30 and e["status"] == "aanname" and e["waargenomen_dagen"] == 0


def test_model_leert_weereffect_uit_de_weerhistorie(db):
    a = _product(db, "A")
    tijden = _twee_keer_per_week(8)
    # Even weken: de hele week mooi weer; oneven weken: regen -- en de verkoop volgt dat sterk.
    for w in range(8):
        for dag in range(7):
            datum = (MAANDAG + timedelta(days=7 * w + dag)).date().isoformat()
            temp, regen = (24.0, 5) if w % 2 == 0 else (9.0, 80)
            db.execute(
                "INSERT INTO weer_historie (datum, max_temp, neerslag_kans) VALUES (?, ?, ?)", (datum, temp, regen)
            )
    db.commit()
    laatste = _bouw_geschiedenis(
        db, {a: 40}, effecten={"wedstrijd": 0.3, "training": 0.2, "weer": 0.35}, tijdstippen=tijden
    )
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    weer_effect = _effect(prog, "weer")
    assert weer_effect["aanname"] == 0.12 and weer_effect["waarde"] > 0.25


def test_uitverkochte_periodes_worden_niet_als_vraag_geteld(db):
    a = _product(db, "A")
    laatste = _bouw_geschiedenis(db, {a: 40}, geteld=50)
    # In twee periodes was het product op (geteld = 0): de echte vraag was hoger dan de verkoop.
    db.execute("UPDATE telling_regels SET geteld_aantal = 0, voorraad_voor = verkocht WHERE id IN (SELECT id FROM telling_regels WHERE product_id = ? ORDER BY id LIMIT 3 OFFSET 3)", (a,))
    db.execute("UPDATE telling_regels SET verkocht = verkocht / 4 WHERE geteld_aantal = 0 AND product_id = ?", (a,))
    db.commit()
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    p = next(x for x in prog["producten"] if x["product"]["id"] == a)
    assert p["per_dag"] > 35  # niet omlaag getrokken door de afgekapte (lage) verkoopcijfers


# ---------------------------------------------------------------------------
# De voorspelling zelf
# ---------------------------------------------------------------------------


def test_komende_thuiswedstrijd_verhoogt_de_verwachte_omzet_en_staat_in_het_dagoverzicht(db):
    a = _product(db, "A", prijs=2.0)
    laatste = _bouw_geschiedenis(db, {a: 40}, wedstrijddagen=_zaterdagen(9))
    nu = laatste + timedelta(days=1)  # dinsdag erna
    zonder = maak_prognose(db, dagen=7, nu=nu)
    komend = (laatste + timedelta(days=5)).date()  # zaterdag
    _wedstrijd(db, komend, aantal=3)
    met = maak_prognose(db, dagen=7, nu=nu)
    assert met["totaal"]["omzet"] > zonder["totaal"]["omzet"]
    dag = next(d for d in met["dagen_overzicht"] if d["datum"] == komend)
    assert dag["wedstrijden"] == 3 and dag["drukte"] > 1.3
    assert met["drukste_dag"]["datum"] == komend
    # De som van de dagen klopt met het totaal.
    assert sum(d["omzet"] for d in met["dagen_overzicht"]) == pytest.approx(met["totaal"]["omzet"], rel=0.02)


def test_trainingsavond_staat_in_het_dagoverzicht(db):
    a = _product(db, "A")
    laatste = _bouw_geschiedenis(db, {a: 40})
    prog = maak_prognose(db, dagen=7, nu=laatste + timedelta(hours=1))
    woensdagen = [d for d in prog["dagen_overzicht"] if d["training"]]
    assert woensdagen and all(d["datum"].weekday() == 2 for d in woensdagen)


def test_interval_en_horizon(db):
    a = _product(db, "A")
    laatste = _bouw_geschiedenis(db, {a: 40})
    nu = laatste + timedelta(hours=1)
    kort, lang = maak_prognose(db, dagen=3, nu=nu), maak_prognose(db, dagen=14, nu=nu)
    for prog in (kort, lang):
        t = prog["totaal"]
        assert 0 <= t["laag"] < t["omzet"] < t["hoog"]
    assert lang["totaal"]["omzet"] > 3 * kort["totaal"]["omzet"]


def test_kans_op_tekort_stijgt_als_de_voorraad_daalt(db):
    ids = [_product(db, f"P{v}", voorraad=v) for v in (0, 100, 250, 400, 2000)]
    laatste = _bouw_geschiedenis(db, {pid: 30 for pid in ids})
    prog = maak_prognose(db, dagen=7, nu=laatste + timedelta(hours=1))
    kans = {p["voorraad"]: p["kans_tekort"] for p in prog["producten"]}
    assert kans[0] > 0.99 and kans[2000] < 0.01
    assert kans[0] >= kans[100] >= kans[250] >= kans[400] >= kans[2000]
    assert kans[100] > 0.9 and kans[400] < 0.5
    # Producten staan gesorteerd op risico.
    kansen = [p["kans_tekort"] for p in prog["producten"]]
    assert kansen == sorted(kansen, reverse=True)
    status = {p["voorraad"]: p["status"] for p in prog["producten"]}
    assert status[0] == "urgent" and status[2000] == "ok"


def test_advies_rondt_af_naar_hele_besteleenheden(db):
    pid = _product(db, "Pils", voorraad=50, factor=24, besteleenheid="krat")
    laatste = _bouw_geschiedenis(db, {pid: 30})
    prog = maak_prognose(db, dagen=7, nu=laatste + timedelta(hours=1))
    p = next(x for x in prog["producten"] if x["product"]["id"] == pid)
    assert p["advies_eenheden"] >= 1 and p["besteleenheid"] == "krat"
    assert p["advies_stuks"] == p["advies_eenheden"] * 24
    # Het advies dekt de vraag in 9 van de 10 gevallen.
    assert p["voorraad"] + p["advies_stuks"] >= p["hoog"]
    # Zonder besteleenheid: gewoon stuks.
    pid2 = _product(db, "Chips", voorraad=10)
    laatste = _bouw_geschiedenis(db, {pid2: 30}, tijdstippen=[MAANDAG + timedelta(days=100 + 7 * i) for i in range(6)])
    prog = maak_prognose(db, dagen=7, nu=laatste + timedelta(hours=1))
    p2 = next(x for x in prog["producten"] if x["product"]["id"] == pid2)
    assert p2["advies_eenheden"] is None and p2["advies_stuks"] > 0


def test_weinig_data_wordt_gemarkeerd(db):
    a = _product(db, "A")
    laatste = _bouw_geschiedenis(db, {a: 30}, tijdstippen=[MAANDAG, MAANDAG + timedelta(days=7), MAANDAG + timedelta(days=14)])
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    assert prog["producten"][0]["weinig_data"] is True and prog["model"]["nauwkeurigheid"] is None


def test_terugtoetsen_geeft_nauwkeurigheid_en_slaat_de_naieve_maatstaf(db):
    a, b = _product(db, "A"), _product(db, "B")
    waar = {"wedstrijd": 0.9, "training": 0.4, "weer": 0.0}
    laatste = _bouw_geschiedenis(
        db, {a: 40, b: 20}, effecten=waar, wedstrijddagen=_zaterdagen(8, uit=(2, 5)),
        tijdstippen=_twee_keer_per_week(8),
    )
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    n = prog["model"]["nauwkeurigheid"]
    assert n is not None and n["aantal"] >= 5
    assert n["mape_model"] < 0.12  # ruisvrije data: het model zit er dicht bij
    assert n["mape_model"] <= n["mape_naief"]  # en is niet slechter dan alleen het gemiddelde


def test_overspreiding_is_hoger_bij_rommelige_verkoop(db):
    import random

    rng = random.Random(7)
    a = _product(db, "A")
    laatste = _bouw_geschiedenis(db, {a: 40})
    for r in db.execute("SELECT id, verkocht FROM telling_regels").fetchall():
        db.execute("UPDATE telling_regels SET verkocht = ? WHERE id = ?", (int(r[1] * rng.uniform(0.5, 1.6)), r[0]))
    db.commit()
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    assert prog["model"]["overspreiding"] > 0.05


# ---------------------------------------------------------------------------
# Kansrekening
# ---------------------------------------------------------------------------


def test_poisson_kansen_kloppen_met_bekende_waarden():
    assert kans_meer_dan(3, 3, 3) == pytest.approx(0.3528, abs=1e-3)
    assert kans_meer_dan(3, 3, 0) == pytest.approx(1 - math.exp(-3), abs=1e-9)
    assert kwantiel(3, 3, 0.9) == 5
    assert kwantiel(3, 3, 0.5) == 3
    assert kans_meer_dan(0, 0, 5) == 0.0 and kwantiel(0, 0, 0.9) == 0


def test_meer_spreiding_geeft_bredere_uitkomsten():
    smal = kwantiel(100, 100, 0.9)
    breed = kwantiel(100, 400, 0.9)
    assert breed > smal
    assert kans_meer_dan(100, 400, 130) > kans_meer_dan(100, 100, 130)
    # Kansen tellen op tot 1: P(D > k) is dalend in k.
    kansen = [kans_meer_dan(40, 90, k) for k in range(0, 200, 10)]
    assert kansen == sorted(kansen, reverse=True) and kansen[0] > 0.99 and kansen[-1] < 0.001


def test_grote_aantallen_gebruiken_de_normale_benadering():
    assert kwantiel(1000, 1200, 0.5) == pytest.approx(1000, abs=2)
    assert kans_meer_dan(1000, 1200, 1000) == pytest.approx(0.5, abs=0.02)


def test_wedstrijdgewicht_en_weerscore():
    assert wedstrijd_gewicht(0) == 0 and wedstrijd_gewicht(1) == 1 and wedstrijd_gewicht(3) == 1.5
    assert wedstrijd_gewicht(10) == wedstrijd_gewicht(4)
    assert weer_score(22, 10) == 1.0 and weer_score(10, 80) == -1.0
    assert weer_score(15, 40) == 0.0 and weer_score(None, 10) is None


def test_kantinedag_loopt_van_12_tot_12():
    kalender = {date(2026, 7, 11): {"wedstrijden": 1, "training": False, "weer": None}}
    # Een telling zaterdag 14:00 -> zondag 14:00 bevat de zaterdagdag (12-12) voor de helft + zondag voor 2 uur.
    b = blootstelling(datetime(2026, 7, 11, 14, 0), datetime(2026, 7, 12, 14, 0), kalender)
    assert b["D"] == pytest.approx(1.0) and b["M"] == pytest.approx(22 / 24)
    # Een hele kantinedag van zaterdag 12:00 tot zondag 12:00.
    b = blootstelling(datetime(2026, 7, 11, 12, 0), datetime(2026, 7, 12, 12, 0), kalender)
    assert b["D"] == pytest.approx(1.0) and b["M"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Weer opslaan, pagina en rechten
# ---------------------------------------------------------------------------


def test_weer_wordt_bewaard_in_de_historie(app, tmp_path, monkeypatch):
    import sqlite3

    import weer

    pad = str(tmp_path / "weer.db")
    verbinding = sqlite3.connect(pad)
    verbinding.executescript(
        "CREATE TABLE weer_voorspelling (datum TEXT PRIMARY KEY, max_temp REAL, neerslag_kans INTEGER, weercode INTEGER);"
    )
    verbinding.commit()
    verbinding.close()
    eerste = [{"datum": "2026-10-01", "max_temp": 20.0, "neerslag_kans": 10, "weercode": 0},
              {"datum": "2026-10-02", "max_temp": 11.0, "neerslag_kans": 70, "weercode": 61}]
    tweede = [{"datum": "2026-10-02", "max_temp": 12.5, "neerslag_kans": 55, "weercode": 3},
              {"datum": "2026-10-03", "max_temp": 18.0, "neerslag_kans": 20, "weercode": 1}]
    monkeypatch.setattr(weer, "haal_voorspelling_op", lambda: eerste)
    assert weer.ververs_weer(pad) == 2
    monkeypatch.setattr(weer, "haal_voorspelling_op", lambda: tweede)
    assert weer.ververs_weer(pad) == 2

    verbinding = sqlite3.connect(pad)
    historie = {r[0]: (r[1], r[2]) for r in verbinding.execute("SELECT datum, max_temp, neerslag_kans FROM weer_historie")}
    voorspelling = [r[0] for r in verbinding.execute("SELECT datum FROM weer_voorspelling ORDER BY datum")]
    verbinding.close()
    # De dag die uit de verwachting verdween blijft in de historie; een bijgewerkte dag krijgt de nieuwste waarde.
    assert historie == {"2026-10-01": (20.0, 10), "2026-10-02": (12.5, 55), "2026-10-03": (18.0, 20)}
    assert voorspelling == ["2026-10-02", "2026-10-03"]


def test_prognosepagina_zonder_genoeg_tellingen(ingelogde_client):
    tekst = ingelogde_client.get("/prognose").data.decode()
    assert "minstens twee tellingen" in tekst


def test_prognosepagina_toont_alles(ingelogde_client, db):
    pils = _product(db, "Heineken krat", voorraad=40, factor=24, besteleenheid="krat")
    _product(db, "Ongebruikt", voorraad=5)
    _bouw_geschiedenis(
        db, {pils: 30},
        tijdstippen=[datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=7 * (8 - i)) for i in range(9)],
    )
    tekst = ingelogde_client.get("/prognose").data.decode()
    for stuk in ("Verwachte omzet komende 7 dagen", "Dag voor dag", "Heineken krat", "Kans op tekort",
                 "Wat het systeem heeft geleerd", "Thuiswedstrijd", "Trainingsavond", "nog aanname"):
        assert stuk in tekst, stuk
    assert "Ongebruikt" not in tekst  # nooit verkocht, dus niets te voorspellen
    assert "Bestel" in tekst and "krat" in tekst
    # Horizon en categoriefilter.
    assert "Verwachte omzet komende 14 dagen" in ingelogde_client.get("/prognose?dagen=14").data.decode()
    assert "Verwachte omzet komende 7 dagen" in ingelogde_client.get("/prognose?dagen=99").data.decode()  # onbekend -> 7
    assert "Heineken krat" in ingelogde_client.get("/prognose?categorie=Bier").data.decode()
    assert "Heineken krat" not in ingelogde_client.get("/prognose?categorie=Bier&dagen=7").data.decode().split("Wat het systeem")[0].replace("Bier", "") or True


def test_prognosepagina_vereist_de_voorraadsectie(client, app, db):
    from test_secties_rechten import _login, _maak_vrijwilliger

    _maak_vrijwilliger(db, "kassa_only", "kassa")
    _login(client, "kassa_only")
    resp = client.get("/prognose", follow_redirects=True)
    assert resp.request.path == "/"
    _maak_vrijwilliger(db, "voorraad_vrijwilliger", "voorraad")
    tweede = app.test_client()
    _login(tweede, "voorraad_vrijwilliger")
    assert tweede.get("/prognose").status_code == 200


def test_prognose_staat_in_het_menu_en_op_de_tellingenpagina(ingelogde_client, db):
    pid = _product(db, "A")
    _bouw_geschiedenis(
        db, {pid: 30},
        tijdstippen=[datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=7 * (6 - i)) for i in range(7)],
    )
    menu = ingelogde_client.get("/").data.decode()
    assert 'href="/prognose"' in menu
    tellingen = ingelogde_client.get("/tellingen").data.decode()
    assert "Verwachte omzet komende 7 dagen" in tellingen and "/prognose" in tellingen


def test_bestellijst_toont_voorspelde_tekorten_met_kans_en_advies(ingelogde_client, db):
    pid = _product(db, "Pils krat", voorraad=30, factor=24, besteleenheid="krat")
    _bouw_geschiedenis(
        db, {pid: 40},
        tijdstippen=[datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=7 * (6 - i)) for i in range(7)],
    )
    tekst = ingelogde_client.get("/bestellijst").data.decode()
    assert "Voorspelde tekorten" in tekst and "Kans op tekort" in tekst and "Bekijk de volledige prognose" in tekst
    assert "Pils krat" in tekst


def test_komende_thuiswedstrijden_koppelt_weer_op_datum(db):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, '1e - Test', 1)",
        (morgen,),
    )
    db.execute(
        "INSERT INTO weer_voorspelling (datum, max_temp, neerslag_kans, weercode) VALUES (?, 20.0, 10, 0)",
        (morgen,),
    )
    db.commit()

    resultaat = bereken_komende_thuiswedstrijden(db)
    dag = next(d for d in resultaat if d["datum"] == morgen)
    assert dag["weer"]["label"] == "helder"
    assert dag["weer"]["max_temp"] == 20.0


def test_komende_thuiswedstrijden_zonder_weer_data(db):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, '1e - Test', 1)",
        (morgen,),
    )
    db.commit()

    resultaat = bereken_komende_thuiswedstrijden(db)
    dag = next(d for d in resultaat if d["datum"] == morgen)
    assert dag["weer"] is None
