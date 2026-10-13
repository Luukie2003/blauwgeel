"""Fase B: tijdelijke actieprijzen, prijsadvies bij een lage marge, niet-lopers en leveranciers."""

from datetime import date, timedelta

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from helpers.tijd import vandaag_amsterdam
from leveranciers import per_leverancier, vandaag_bestellen
from marge import prijsadvies
from niet_lopers import bereken_niet_lopers
from prijzen import pas_geplande_prijzen_toe


def _product(db, naam, **velden):
    standaard = {
        "categorie": "Fris", "eenheid": "Fles", "voorraad": 10, "min_voorraad": 5, "verkoopprijs": 2.0,
        "inkoopprijs": 14.64, "actief": 1, "besteleenheid": "Krat", "besteleenheid_factor": 24,
    }
    standaard.update(velden)
    cur = db.execute(
        f"INSERT INTO producten (naam, {', '.join(standaard)}) VALUES ({', '.join('?' * (len(standaard) + 1))})",
        (naam, *standaard.values()),
    )
    db.commit()
    return cur.lastrowid


def _prijs(db, pid):
    return db.execute("SELECT verkoopprijs FROM producten WHERE id = ?", (pid,)).fetchone()[0]


# ---------- Tijdelijke actieprijzen ----------


def test_een_actieprijs_gaat_nu_in_en_springt_na_de_einddatum_terug(ingelogde_client, db):
    pid = _product(db, "Actie Cola")
    eind = vandaag_amsterdam() + timedelta(days=3)
    resp = ingelogde_client.post(
        "/producten/prijzen",
        data={"csrf_token": _csrf(ingelogde_client), f"prijs_{pid}": "1,50", "einddatum": eind.isoformat()},
        follow_redirects=True,
    )
    assert "komt de oude prijs vanzelf terug" in resp.data.decode()
    assert _prijs(db, pid) == 1.5
    gepland = db.execute("SELECT * FROM prijs_wijzigingen_gepland WHERE product_id = ?", (pid,)).fetchall()
    assert [(g["nieuwe_prijs"], g["ingangsdatum"], g["opmerking"]) for g in gepland] == [
        (2.0, (eind + timedelta(days=1)).isoformat(), "einde actie")
    ]
    assert "einde actie" in ingelogde_client.get("/producten/prijzen").data.decode()

    pas_geplande_prijzen_toe(db, eind)  # op de laatste actiedag nog de actieprijs
    assert _prijs(db, pid) == 1.5
    pas_geplande_prijzen_toe(db, eind + timedelta(days=1))
    assert _prijs(db, pid) == 2.0


def test_een_actie_in_de_toekomst_plant_begin_en_einde(ingelogde_client, db):
    pid = _product(db, "Later Cola")
    begin, eind = vandaag_amsterdam() + timedelta(days=5), vandaag_amsterdam() + timedelta(days=7)
    ingelogde_client.post(
        "/producten/prijzen",
        data={"csrf_token": _csrf(ingelogde_client), f"prijs_{pid}": "1,00", "ingangsdatum": begin.isoformat(),
              "einddatum": eind.isoformat()},
    )
    assert _prijs(db, pid) == 2.0
    gepland = db.execute(
        "SELECT nieuwe_prijs, ingangsdatum FROM prijs_wijzigingen_gepland WHERE product_id = ? ORDER BY ingangsdatum", (pid,)
    ).fetchall()
    assert [tuple(g) for g in gepland] == [(1.0, begin.isoformat()), (2.0, (eind + timedelta(days=1)).isoformat())]


def test_een_einde_voor_het_begin_wordt_geweigerd(ingelogde_client, db):
    pid = _product(db, "Fout Cola")
    resp = ingelogde_client.post(
        "/producten/prijzen",
        data={"csrf_token": _csrf(ingelogde_client), f"prijs_{pid}": "1,00",
              "ingangsdatum": (vandaag_amsterdam() + timedelta(days=5)).isoformat(),
              "einddatum": (vandaag_amsterdam() + timedelta(days=2)).isoformat()},
    )
    assert "kan niet eindigen voordat hij begint" in resp.data.decode()
    assert _prijs(db, pid) == 2.0 and not db.execute("SELECT 1 FROM prijs_wijzigingen_gepland").fetchone()


# ---------- Prijsadvies ----------


def _marge_regel(**velden):
    regel = {"id": 7, "heeft_inkoop": True, "inkoop_stuk": 1.50, "verkoopprijs": 2.0, "marge_pct": 25.0}
    regel.update(velden)
    return regel


def test_het_advies_haalt_de_doelmarge_naar_boven_afgerond():
    assert prijsadvies(_marge_regel(), 30) == ("prijs_7", 2.2)  # 1,50 / 0,70 = 2,14 -> 2,20
    assert prijsadvies(_marge_regel(marge_pct=35.0), 30) is None  # al boven de doelmarge
    assert prijsadvies(_marge_regel(heeft_inkoop=False, marge_pct=None), 30) is None


def test_bij_een_fust_gaat_het_advies_over_de_glasprijs():
    fust = _marge_regel(inkoop_stuk=90.0, verkoopprijs=120.0, marge_pct=25.0, glazen_per_fust=60, prijs_per_glas=2.0)
    assert prijsadvies(fust, 30) == ("glas_7", 2.2)  # € 1,50 per glas / 0,70 -> € 2,20


def test_het_rapport_toont_het_advies_en_zet_het_klaar(ingelogde_client, db):
    pid = _product(db, "Te Goedkoop", inkoopprijs=36.0, verkoopprijs=1.8)  # € 1,50 per fles, 17% marge
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'T')", (vandaag_amsterdam().isoformat() + " 10:00",)).lastrowid
    db.execute("INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs) VALUES (?, ?, 10, 5, 5, 1.8)", (t, pid))
    db.commit()

    tekst = ingelogde_client.get("/rapporten/marge").data.decode()
    assert f"voorstel=prijs_{pid}:2.20" in tekst.replace("%3A", ":")

    klaar = ingelogde_client.get(f"/producten/prijzen?voorstel=prijs_{pid}:2.20").data.decode()
    assert "voorgestelde prijs is" in klaar and 'value="2,20"' in klaar
    assert _prijs(db, pid) == 1.8  # nog niets opgeslagen


def test_de_doelmarge_is_instelbaar(ingelogde_client, db):
    ingelogde_client.post("/rapporten/marge/doelmarge", data={"csrf_token": _csrf(ingelogde_client), "doelmarge": "45"})
    assert db.execute("SELECT doelmarge_pct FROM instellingen WHERE id = 1").fetchone()[0] == 45
    assert 'value="45"' in ingelogde_client.get("/rapporten/marge").data.decode()


# ---------- Niet-lopers ----------


def _telling(db, datum, regels):
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'T')", (datum,)).lastrowid
    for pid, verkocht in regels:
        db.execute(
            "INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs) VALUES (?, ?, 10, ?, ?, 2)",
            (t, pid, 10 - verkocht, verkocht),
        )
    db.commit()


def test_niet_lopers_met_de_waarde_die_erin_vastzit(db):
    staat = _product(db, "Staat Stil", voorraad=48, inkoopprijs=24.0)  # € 1 per fles
    loopt = _product(db, "Loopt Wel")
    nooit = _product(db, "Niet Geteld")
    keuken = _product(db, "Keuken Ding", categorie="Keuken")
    _telling(db, "2026-09-20 10:00", [(staat, 0), (loopt, 3), (keuken, 0)])
    _telling(db, "2026-10-04 10:00", [(staat, 0), (loopt, 0)])

    uitkomst = bereken_niet_lopers(db, 8, date(2026, 10, 13))

    namen = [r["naam"] for r in uitkomst["niet_lopers"]]
    assert "Staat Stil" in namen and "Loopt Wel" not in namen and "Keuken Ding" not in namen
    assert next(r for r in uitkomst["niet_lopers"] if r["naam"] == "Staat Stil")["waarde"] == 48.0
    assert "Niet Geteld" in [r["naam"] for r in uitkomst["niet_geteld"]]
    assert nooit and keuken


def test_de_niet_lopers_pagina_alleen_voor_beheerders(ingelogde_client, client, db):
    assert "Niet verkocht" in ingelogde_client.get("/rapporten/niet-lopers").data.decode()
    _maak_vrijwilliger(db, "vrijwilliger", "voorraad")
    ander = client.application.test_client()
    _login(ander, "vrijwilliger")
    assert "alleen voor beheerders" in ander.get("/rapporten/niet-lopers", follow_redirects=True).data.decode()


# ---------- Leveranciers ----------


def _leverancier(client, naam="Robertus", **velden):
    data = {"csrf_token": _csrf(client), "naam": naam, "actief": "on", "minimum_bedrag": "250", "bestellen_voor": "12:00",
            "telefoon": "0475-123456", "levertijd_dagen": "2"}
    data.update(velden)
    return client.post("/leveranciers/nieuw", data=data, follow_redirects=True)


def test_een_leverancier_aanmaken_met_besteldagen_en_producten(ingelogde_client, db):
    cola, fanta = _product(db, "Lev Cola"), _product(db, "Lev Fanta")
    resp = _leverancier(ingelogde_client, dag_1="on", dag_4="on", product_id=[str(cola), str(fanta)])
    assert "Leverancier toegevoegd" in resp.data.decode()
    lev = db.execute("SELECT * FROM leveranciers WHERE naam = 'Robertus'").fetchone()
    assert lev["besteldagen"] == "1,4" and lev["minimum_bedrag"] == 250
    assert {r[0] for r in db.execute("SELECT id FROM producten WHERE leverancier_id = ?", (lev["id"],))} == {cola, fanta}

    tekst = ingelogde_client.get("/leveranciers").data.decode()
    assert "dinsdag, vrijdag vóór 12:00" in tekst and "0475-123456" in tekst

    # Bewerken: Fanta uitvinken koppelt hem los.
    ingelogde_client.post(f"/leveranciers/{lev['id']}", data={"csrf_token": _csrf(ingelogde_client), "naam": "Robertus",
                                                             "actief": "on", "product_id": [str(cola)]})
    assert db.execute("SELECT leverancier_id FROM producten WHERE id = ?", (fanta,)).fetchone()[0] is None
    # Alles uitvinken koppelt ook alles los.
    ingelogde_client.post(f"/leveranciers/{lev['id']}", data={"csrf_token": _csrf(ingelogde_client), "naam": "Robertus", "actief": "on"})
    assert db.execute("SELECT COUNT(*) FROM producten WHERE leverancier_id = ?", (lev["id"],)).fetchone()[0] == 0


def test_twee_leveranciers_met_dezelfde_naam_kan_niet(ingelogde_client, db):
    _leverancier(ingelogde_client)
    assert "Er is al een leverancier" in _leverancier(ingelogde_client, naam="robertus").data.decode()


def test_de_productkaart_kiest_een_leverancier(ingelogde_client, db):
    _leverancier(ingelogde_client)
    lev_id = db.execute("SELECT id FROM leveranciers").fetchone()[0]
    pid = _product(db, "Kaart Cola")
    assert f'<option value="{lev_id}"' in ingelogde_client.get(f"/producten/{pid}/bewerken").data.decode()
    p = db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()
    ingelogde_client.post(f"/producten/{pid}/bewerken", data={
        "csrf_token": _csrf(ingelogde_client), "naam": p["naam"], "categorie": "Fris", "eenheid": "Fles", "voorraad": "10",
        "min_voorraad": "5", "bestel_hoeveelheid": "0", "verkoopprijs": "2", "inkoopprijs": "14.64", "actief": "on",
        "besteleenheid": "Krat", "besteleenheid_factor": "24", "leverancier_id": str(lev_id),
    }, content_type="multipart/form-data")
    assert db.execute("SELECT leverancier_id FROM producten WHERE id = ?", (pid,)).fetchone()[0] == lev_id


def test_de_bestellijst_per_leverancier_met_minimum_en_pdf(ingelogde_client, db):
    _leverancier(ingelogde_client, product_id=[str(_product(db, "Krap Cola", voorraad=2, min_voorraad=24))])
    _product(db, "Krap Zonder", voorraad=0, min_voorraad=6)
    lev_id = db.execute("SELECT id FROM leveranciers").fetchone()[0]

    groepen = per_leverancier(db, db.execute("SELECT * FROM producten WHERE actief = 1 AND voorraad < min_voorraad").fetchall())
    robertus = next(g for g in groepen if g["naam"] == "Robertus")
    assert robertus["waarde"] == 14.64 and robertus["onder_minimum"]  # 1 krat, minimum € 250
    assert groepen[-1]["naam"] == "Geen leverancier"

    tekst = ingelogde_client.get("/bestellijst").data.decode()
    assert "Bestellen per leverancier" in tekst and "onder minimum van" in tekst and "bij Robertus" in tekst
    pdf = ingelogde_client.get(f"/bestellijst/pdf?leverancier={lev_id}")
    assert pdf.status_code == 200 and "bestellijst-robertus.pdf" in pdf.headers["Content-Disposition"]
    assert ingelogde_client.get("/bestellijst/pdf?leverancier=geen").status_code == 200


def test_op_de_besteldag_staat_het_op_het_overzicht(ingelogde_client, db):
    vandaag = vandaag_amsterdam()
    _leverancier(ingelogde_client, **{f"dag_{vandaag.weekday()}": "on"},
                 product_id=[str(_product(db, "Krap Bier", voorraad=1, min_voorraad=24))])
    assert [(lev["naam"], n) for lev, n in vandaag_bestellen(db, vandaag)] == [("Robertus", 1)]
    assert vandaag_bestellen(db, vandaag + timedelta(days=1)) == []
    assert "Vandaag bestellen bij Robertus" in ingelogde_client.get("/").data.decode()


def test_vrijwilligers_zien_de_leveranciers_maar_beheren_ze_niet(client, db):
    _maak_vrijwilliger(db, "besteller", "voorraad")
    _login(client, "besteller")
    assert client.get("/leveranciers").status_code == 200
    assert "alleen voor beheerders" in client.get("/leveranciers/nieuw", follow_redirects=True).data.decode()
