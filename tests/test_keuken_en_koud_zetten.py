"""De keuken als eigen module (tellen, inboeken, prijzen, apart van de gewone telling) en het koud-zet-advies."""

from datetime import datetime

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

import voorspelling
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


# ---------- Koud zetten ----------


def _nep_prognose(monkeypatch, dagen, producten):
    uitkomst = {"beschikbaar": True, "dagen_overzicht": dagen, "producten": producten}
    monkeypatch.setattr(voorspelling, "maak_prognose", lambda db, **kwargs: uitkomst)


def _product(naam, categorie="Bier", eenheid="Fles", voorraad=100, factor=24, besteleenheid="Krat"):
    return {"naam": naam, "categorie": categorie, "eenheid": eenheid, "voorraad": voorraad,
            "besteleenheid_factor": factor, "besteleenheid": besteleenheid}


def test_koud_zetten_voor_de_volgende_verkoopdag(db, monkeypatch):
    nu = datetime(2026, 10, 9, 18, 0)  # vrijdagavond
    zaterdag = {"datum": datetime(2026, 10, 10).date(), "open": True, "drukte": 1.5, "weekdag": "zaterdag",
                "wedstrijden": 1, "training": False}
    _nep_prognose(monkeypatch, [{"datum": nu.date(), "open": False, "drukte": 0.0}, zaterdag], [
        {"product": _product("Hertog Jan"), "snelheid": 40.0},           # 60 verwacht -> 75 koud = 3 krat + 3
        {"product": _product("Cola", "Fris", voorraad=10), "snelheid": 10.0},  # 15 verwacht, maar 10 op voorraad
        {"product": _product("Fust HJ", eenheid="Fust", factor=1, besteleenheid=None), "snelheid": 1.0},
        {"product": _product("Chips", "Chips"), "snelheid": 10.0},
        {"product": _product("Zelden", "Fris"), "snelheid": 0.2},
    ])

    advies = voorspelling.koud_zetten(db, nu)

    assert not advies["vandaag"] and advies["dag"]["weekdag"] == "zaterdag"
    regels = {r["product"]["naam"]: r for r in advies["regels"]}
    assert set(regels) == {"Hertog Jan", "Cola"}  # geen fust, geen chips, niet wat bijna niet verkoopt
    assert (regels["Hertog Jan"]["koud"], regels["Hertog Jan"]["hele"], regels["Hertog Jan"]["los"]) == (75, 3, 3)
    assert regels["Cola"]["koud"] == 10 and regels["Cola"]["te_weinig"]


def test_geen_koud_zetten_zonder_verkoopdag_vandaag_of_morgen(db, monkeypatch):
    nu = datetime(2026, 10, 12, 18, 0)  # maandag; woensdag is te ver weg
    _nep_prognose(monkeypatch, [{"datum": datetime(2026, 10, 14).date(), "open": True, "drukte": 1.0}],
                  [{"product": _product("Hertog Jan"), "snelheid": 40.0}])
    assert voorspelling.koud_zetten(db, nu) is None


def test_de_kaart_op_het_overzicht(ingelogde_client, monkeypatch):
    monkeypatch.setattr("routes.dashboard.koud_zetten", lambda db: {
        "dag": {"weekdag": "zaterdag", "wedstrijden": 2, "training": False}, "vandaag": False,
        "regels": [{"product": {"naam": "Hertog Jan", "eenheid": "Fles"}, "verwacht": 60.0, "koud": 75, "te_weinig": False,
                    "hele": 3, "los": 3, "besteleenheid": "Krat"}],
    })
    tekst = ingelogde_client.get("/dashboard/koud-zetten").data.decode()
    assert "Koud zetten voor morgen (zaterdag)" in tekst and "3 krat + 3" in tekst
    assert 'data-lazy-bron="/dashboard/koud-zetten"' in ingelogde_client.get("/").data.decode()
    monkeypatch.setattr("routes.dashboard.koud_zetten", lambda db: None)
    assert ingelogde_client.get("/dashboard/koud-zetten").data.decode() == ""
