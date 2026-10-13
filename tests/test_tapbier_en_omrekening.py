"""Tapbier telt mee in de omzet (een leeg fust = glazen maal de glasprijs), de inkoopprijs per stuk op één plek, en de
genummerde migraties die dat voor de bestaande gegevens één keer regelen."""

from conftest import stel_csrf_token_in as _csrf

from database.migraties import GENUMMERDE_MIGRATIES, migreer_genummerd
from helpers import inkoop_per_stuk, omzet_per_eenheid
from marge import bereken_marge, bereken_tap


def _fust(db, naam="Fust Proef", voorraad=10, glazen=60, prijs_glas=2.0, inkoop=63.28):
    cur = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, inkoopprijs, actief,
                                  glazen_per_fust, prijs_per_glas, besteleenheid_factor)
           VALUES (?, 'Telling', 'Fust', ?, 2, 0, ?, 1, ?, ?, 1)""",
        (naam, voorraad, inkoop, glazen, prijs_glas),
    )
    db.commit()
    return cur.lastrowid


def _krat(db, naam="Pils Proef", inkoop=19.78, factor=24, verkoop=2.20):
    cur = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, inkoopprijs, actief,
                                  besteleenheid, besteleenheid_factor)
           VALUES (?, 'Bier', 'Fles', 48, 24, ?, ?, 1, 'Krat', ?)""",
        (naam, verkoop, inkoop, factor),
    )
    db.commit()
    return cur.lastrowid


def _rij(db, product_id):
    return db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()


# ---------- Eén plek voor de omrekening ----------


def test_de_inkoopprijs_per_krat_wordt_per_stuk_omgerekend(db):
    krat = _rij(db, _krat(db))
    assert abs(inkoop_per_stuk(krat) - 19.78 / 24) < 1e-9
    assert inkoop_per_stuk({"inkoopprijs": 5.0, "besteleenheid_factor": 0}) == 5.0  # 0 of leeg telt als 1
    assert inkoop_per_stuk({"inkoopprijs": None, "besteleenheid_factor": None}) == 0
    assert inkoop_per_stuk({}) == 0


def test_een_fust_levert_glazen_maal_de_glasprijs_op(db):
    fust = _rij(db, _fust(db))
    assert omzet_per_eenheid(fust) == 120.0
    assert omzet_per_eenheid({"verkoopprijs": 2.2}) == 2.2  # een gewoon product: de verkoopprijs


def test_marge_en_derving_rekenen_per_stuk_via_dezelfde_functie(db):
    import derving
    import marge

    assert marge.inkoop_per_stuk is inkoop_per_stuk and derving.inkoop_per_stuk is inkoop_per_stuk


# ---------- Tapbier in de omzet ----------


def test_een_weggeteld_fust_telt_als_120_euro_omzet(ingelogde_client, db):
    fust_id = _fust(db)
    ingelogde_client.post("/tellen", data={"csrf_token": _csrf(ingelogde_client), f"geteld_{fust_id}": "8"})

    regel = db.execute("SELECT verkocht, verkoopprijs FROM telling_regels WHERE product_id = ?", (fust_id,)).fetchone()
    assert regel["verkocht"] == 2 and regel["verkoopprijs"] == 120.0  # 2 lege fusten = € 240

    tekst = ingelogde_client.get("/tellingen").data.decode()
    assert "€ 240.00" in tekst


def test_het_tapbier_staat_in_de_marge(db):
    from datetime import date

    fust_id = _fust(db)
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-10-10 12:00', 'Test')").lastrowid
    db.execute(
        """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
           VALUES (?, ?, 10, 8, 2, 120)""",
        (t, fust_id),
    )
    db.commit()
    rapport = bereken_marge(db, 4, date(2026, 10, 13))
    fust = next(p for p in rapport["producten"] if p["id"] == fust_id)
    assert fust["verkoopprijs"] == 120 and fust["omzet"] == 240
    assert abs(fust["winst"] - (240 - 2 * 63.28)) < 0.01


def test_kostprijs_per_glas_pitcher_en_verlies_per_fust(db):
    fust_id = _fust(db, inkoop=60.0)
    db.execute("INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde, glazen) VALUES (?, 'Pitcher', 8, 0, 4)", (fust_id,))
    db.commit()

    fust = next(f for f in bereken_tap(db) if f["id"] == fust_id)

    assert fust["kostprijs_glas"] == 1.0 and fust["marge_glas_pct"] == 50
    assert fust["terugverdiend_na"] == 30  # € 60 / € 2 per glas
    assert [v["winst"] for v in fust["verlies"]] == [60.0, 54.0, 48.0]  # 0, 3 en 6 glazen weg
    assert fust["opties"][0]["kostprijs"] == 4.0 and fust["opties"][0]["marge_pct"] == 50


def test_de_marge_pagina_toont_het_tapbier(ingelogde_client, db):
    _fust(db, naam="Fust Zichtbaar")
    tekst = ingelogde_client.get("/rapporten/marge").data.decode()
    assert "Tapbier: per glas en per fust" in tekst and "Fust Zichtbaar" in tekst


def test_glazen_per_prijsoptie_worden_bewaard(ingelogde_client, db):
    fust_id = _fust(db)
    p = _rij(db, fust_id)
    ingelogde_client.post(
        f"/producten/{fust_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client), "naam": p["naam"], "categorie": p["categorie"], "eenheid": "Fust",
            "voorraad": "10", "min_voorraad": "2", "bestel_hoeveelheid": "0", "verkoopprijs": "0", "inkoopprijs": "63.28",
            "besteleenheid_factor": "1", "actief": "on", "glazen_per_fust": "60", "prijs_per_glas": "2",
            "optie_naam": ["Pitcher", "Glas"], "optie_prijs": ["8", "2"], "optie_glazen": ["4,5", ""],
        },
        content_type="multipart/form-data",
    )
    opties = db.execute("SELECT naam, glazen FROM product_prijsopties WHERE product_id = ? ORDER BY volgorde", (fust_id,)).fetchall()
    assert [(o["naam"], o["glazen"]) for o in opties] == [("Pitcher", 4.5), ("Glas", 0)]


# ---------- Genummerde migraties ----------


def test_de_tapbier_migratie_vult_fusten_en_oude_tellingen_een_keer(db):
    fust_id = _fust(db, glazen=0, prijs_glas=0)
    t = db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-09-01 12:00', 'Oud')").lastrowid
    db.execute(
        """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
           VALUES (?, ?, 5, 4, 1, 0)""",
        (t, fust_id),
    )
    db.execute("PRAGMA user_version = 0")
    db.commit()

    migreer_genummerd(db)

    p = _rij(db, fust_id)
    assert (p["glazen_per_fust"], p["prijs_per_glas"]) == (60, 2.0)
    assert db.execute("SELECT verkoopprijs FROM telling_regels WHERE product_id = ?", (fust_id,)).fetchone()[0] == 120
    assert db.execute("PRAGMA user_version").fetchone()[0] == GENUMMERDE_MIGRATIES[-1][0]

    # Zet iemand het daarna zelf anders, dan blijft dat zo: de stap draait geen tweede keer.
    db.execute("UPDATE producten SET glazen_per_fust = 0 WHERE id = ?", (fust_id,))
    db.commit()
    migreer_genummerd(db)
    assert _rij(db, fust_id)["glazen_per_fust"] == 0


def test_een_ingevulde_glasprijs_blijft_staan(db):
    fust_id = _fust(db, glazen=0, prijs_glas=2.5)
    db.execute("PRAGMA user_version = 0")
    db.commit()
    migreer_genummerd(db)
    assert _rij(db, fust_id)["prijs_per_glas"] == 2.5


def test_de_nummers_lopen_op_zonder_gaten():
    nummers = [n for n, _ in GENUMMERDE_MIGRATIES]
    assert nummers == list(range(1, len(nummers) + 1))
