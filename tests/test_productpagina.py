"""De productpagina (/producten/<id>): kerncijfers, prijzen, inkoop en bestellen, barcodes, tellingen, en het blok
'Verkoop en verwachting' dat apart wordt opgehaald."""

from datetime import date, datetime, timedelta

import pytest

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger
from test_voorspelling import _bouw_geschiedenis, _product

import productinfo


def _weken_terug(aantal, uur=22):
    """Tellingen op woensdagavond, de laatste van deze of vorige week."""
    vandaag = date.today()
    woensdag = vandaag - timedelta(days=(vandaag.weekday() - 2) % 7 or 7)
    return [datetime.combine(woensdag - timedelta(weeks=i), datetime.min.time()).replace(hour=uur)
            for i in range(aantal - 1, -1, -1)]


def _hertog(db, **velden):
    pid = _product(db, "Hertog Jan Fles", voorraad=18, prijs=2.5, factor=24, besteleenheid="krat", min_voorraad=24)
    db.execute("UPDATE producten SET inkoopprijs = 19.20 WHERE id = ?", (pid,))
    for veld, waarde in velden.items():
        db.execute(f"UPDATE producten SET {veld} = ? WHERE id = ?", (waarde, pid))
    db.commit()
    return pid


# ---------- Wat er zonder het voorspelmodel op staat ----------


def test_kerncijfers_marge_en_voorraadwaarde(db):
    pid = _hertog(db)
    product = db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()
    info = productinfo.productinfo(db, product)
    assert info["inkoop_stuk"] == pytest.approx(0.80)
    assert info["marge"]["pct"] == pytest.approx(68.0) and info["marge"]["stuk"] == pytest.approx(1.70)
    assert not info["marge"]["onder_doel"]
    assert info["voorraadwaarde"] == pytest.approx(14.40)
    assert info["in_besteleenheden"] == pytest.approx(0.75)


def test_onderweg_laatst_binnen_derving_en_meldingen(db):
    pid = _hertog(db)
    b = db.execute("INSERT INTO bestellingen (status, aangemaakt_op, referentie) VALUES ('besteld', '2026-10-15 11:00', 'N-1')").lastrowid
    db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld) VALUES (?, ?, 48)", (b, pid))
    vandaag = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute("INSERT INTO mutaties (product_id, type, aantal, datum, naam) VALUES (?, 'in', 24, ?, 'Luuk')", (pid, vandaag))
    db.execute("INSERT INTO mutaties (product_id, type, aantal, datum, naam, reden) VALUES (?, 'uit', 2, ?, 'Koen', 'breuk')", (pid, vandaag))
    db.execute("INSERT INTO bestellijst_meldingen (product_id, aangemaakt_op) VALUES (?, ?)", (pid, vandaag))
    db.commit()
    info = productinfo.productinfo(db, db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone())
    assert [(r["id"], r["aantal_besteld"]) for r in info["open_bestellingen"]] == [(b, 48)]
    assert info["laatste_levering"]["aantal"] == 24
    assert (info["derving"]["aantal"], info["derving"]["keer"]) == (2, 1)
    assert info["meldingen"] == 1


def test_productpagina_toont_alles(ingelogde_client, db):
    pid = _hertog(db, merk="Hertog Jan", opmerking="Staat achter in de koelcel.")
    _bouw_geschiedenis(db, {pid: 3}, tijdstippen=_weken_terug(4), open_dagen="2,5")
    tekst = ingelogde_client.get(f"/producten/{pid}").data.decode()
    for stuk in ("Hertog Jan Fles", "Staat achter in de koelcel.", "Onder het minimum", "68%", "Laatst geteld",
                 "Verkoop en verwachting", f"/producten/{pid}/verkoop", "Prijzen", "Inkoop en bestellen",
                 "krat", "Artikelen en barcodes", "Laatste tellingen", "Op de bestellijst"):
        assert stuk in tekst, stuk


def test_vrijwilliger_ziet_geen_marge(client, db):
    pid = _hertog(db)
    _maak_vrijwilliger(db, "voorraadhulp", "voorraad")
    _login(client, "voorraadhulp")
    tekst = client.get(f"/producten/{pid}").data.decode()
    assert "Hertog Jan Fles" in tekst and "Marge" not in tekst and "Bewerken" not in tekst


# ---------- Verkoop en verwachting ----------


def test_verkoop_per_week_en_verwachting(ingelogde_client, db):
    pid = _hertog(db)
    _bouw_geschiedenis(db, {pid: 4}, tijdstippen=_weken_terug(8), open_dagen="2,5")
    verkoop = productinfo.verkoopinfo(db, pid)
    assert verkoop["weken"] and verkoop["per_week"] > 0
    assert verkoop["verwachting"] is not None and verkoop["verwachting"]["verwacht"] > 0
    assert sum(w["aantal"] for w in verkoop["weken"]) <= db.execute(
        "SELECT SUM(verkocht) FROM telling_regels WHERE product_id = ?", (pid,)
    ).fetchone()[0] + 1e-6

    tekst = ingelogde_client.get(f"/producten/{pid}/verkoop").data.decode()
    assert "Gemiddeld per week" in tekst and "Verkocht per week" in tekst and "Verwacht de komende 7 dagen" in tekst


def test_zonder_tellingen(ingelogde_client, db):
    pid = _hertog(db)
    assert productinfo.verkoopinfo(db, pid) is None
    assert "Nog geen tellingen" in ingelogde_client.get(f"/producten/{pid}/verkoop").data.decode()
    assert ingelogde_client.get("/producten/999999/verkoop").data.decode() == ""


def test_al_weken_niets_verkocht(db):
    pid = _hertog(db)
    ander = _product(db, "Cola")
    tijden = _weken_terug(8)
    _bouw_geschiedenis(db, {pid: 3, ander: 5}, tijdstippen=tijden[:4], open_dagen="2,5")
    # Daarna nog vier tellingen waarin alleen de cola verkocht wordt.
    for tijd in tijden[4:]:
        t = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (tijd.strftime("%Y-%m-%d %H:%M"),)).lastrowid
        db.execute("INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs) VALUES (?, ?, 18, 18, 0, 2.5)", (t, pid))
        db.execute("INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs) VALUES (?, ?, 50, 40, 10, 2.0)", (t, ander))
    db.commit()
    assert productinfo.verkoopinfo(db, pid)["zonder_verkoop"] >= productinfo.WEKEN_NIET_VERKOCHT
    assert productinfo.verkoopinfo(db, ander)["zonder_verkoop"] == 0


# ---------- Op de bestellijst ----------


def test_op_de_bestellijst_zetten(ingelogde_client, db):
    pid = _hertog(db)
    resp = ingelogde_client.post(f"/producten/{pid}/melden", data={"csrf_token": _csrf(ingelogde_client)})
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/producten/{pid}")
    rij = db.execute("SELECT bron, afgehandeld FROM bestellijst_meldingen WHERE product_id = ?", (pid,)).fetchone()
    assert (rij["bron"], rij["afgehandeld"]) == ("productpagina", 0)
    assert "Hertog Jan Fles" in ingelogde_client.get("/bestellijst").data.decode()


def test_melden_hoort_bij_de_voorraad_sectie(client, db):
    pid = _hertog(db)
    _maak_vrijwilliger(db, "kassahulp", "kassa")
    _login(client, "kassahulp")
    client.post(f"/producten/{pid}/melden", data={"csrf_token": _csrf(client)})
    assert client.get(f"/producten/{pid}/verkoop").status_code == 302
    assert db.execute("SELECT COUNT(*) FROM bestellijst_meldingen").fetchone()[0] == 0


def test_leeftijd():
    vandaag = date(2026, 10, 16)
    assert productinfo.leeftijd("2026-10-16 09:00", vandaag) == "vandaag"
    assert productinfo.leeftijd("2026-10-15 22:00", vandaag) == "gisteren"
    assert productinfo.leeftijd("2026-10-10 22:00", vandaag) == "6 dagen geleden"
    assert productinfo.leeftijd("2026-09-01 22:00", vandaag) == "6 weken geleden"
