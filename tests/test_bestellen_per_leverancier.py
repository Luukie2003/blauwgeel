"""Bestellen per leverancier, "Op de bestellijst" en de herinnering om te bestellen (1.70.0), plus de telling corrigeren
en naam en prijs aanpassen vanaf de handterminal."""

from datetime import datetime

from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_bestelvoorstel import _product, prognose  # noqa: F401 (fixture)

import bestelvoorstel
import facturen
from bestellen import bestel_tekst, bestelling_gegevens, maak_bestellingen


def _leverancier(db, naam, besteldagen="1,3", voor="16:00", levertijd=1, klantnummer=None):
    lid = db.execute(
        """INSERT INTO leveranciers (naam, besteldagen, bestellen_voor, levertijd_dagen, klantnummer, aangemaakt_op)
           VALUES (?, ?, ?, ?, ?, '2026-10-01')""",
        (naam, besteldagen, voor, levertijd, klantnummer),
    ).lastrowid
    db.commit()
    return lid


def _bij(db, pid, lid):
    db.execute("UPDATE producten SET leverancier_id = ?, artikelcode = ? WHERE id = ?", (lid, f"A{pid}", pid))
    db.commit()


# ---------- Een bestelling per leverancier ----------


def test_klaarzetten_maakt_een_bestelling_per_leverancier(ingelogde_client, db):
    sligro = _leverancier(db, "Sligro", klantnummer="123456")
    makro = _leverancier(db, "Makro")
    cola = _product(db, "Cola Lev", voorraad=0, factor=24, besteleenheid="tray")
    bier = _product(db, "Bier Lev", voorraad=0)
    chips = _product(db, "Chips Lev", voorraad=0)
    los = _product(db, "Los Lev", voorraad=0)
    _bij(db, cola, sligro)
    _bij(db, chips, sligro)
    _bij(db, bier, makro)

    resp = ingelogde_client.post("/bestellijst/aanmaken", data={
        "csrf_token": _csrf(ingelogde_client), "product_id": [cola, bier, chips, los],
        f"aantal_{cola}": "2", f"aantal_{bier}": "5", f"aantal_{chips}": "1", f"aantal_{los}": "3",
    }, follow_redirects=True)
    pagina = resp.data.decode()
    assert "3 bestellingen klaargezet, een per leverancier" in pagina

    rijen = db.execute(
        """SELECT b.id, l.naam, COUNT(br.id) AS regels FROM bestellingen b LEFT JOIN leveranciers l ON l.id = b.leverancier_id
           JOIN bestelregels br ON br.bestelling_id = b.id GROUP BY b.id ORDER BY b.id"""
    ).fetchall()
    assert [(r["naam"], r["regels"]) for r in rijen] == [("Makro", 1), ("Sligro", 2), (None, 1)]
    sligro_bestelling = rijen[1]["id"]
    assert f"Bestelling #{sligro_bestelling}</strong> bij <strong>Sligro" in pagina and "PDF voor de leverancier" in pagina

    # De tekst om door te sturen, en de pdf.
    tekst = bestel_tekst(bestelling_gegevens(db, sligro_bestelling))
    assert "klantnummer 123456" in tekst and f"- 2 tray Cola Lev (48 stuks), art.nr. A{cola}" in tekst
    pdf = ingelogde_client.get(f"/bestellingen/{sligro_bestelling}/pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"
    assert f"bestelling-{sligro_bestelling}-sligro.pdf" in pdf.headers["Content-Disposition"]

    # Inboeken: de factuur krijgt de leverancier van de bestelling.
    ronde = facturen.ronde_voor_bestelling(db, rijen[0]["id"])
    assert db.execute("SELECT leverancier_id FROM inboekrondes WHERE id = ?", (ronde,)).fetchone()[0] == makro
    assert [b["leverancier"] for b in facturen.open_bestellingen(db)] == [None, "Sligro", "Makro"]


def test_app_zet_ook_per_leverancier_klaar(app_client, db):  # noqa: F811
    sligro = _leverancier(db, "Sligro App")
    cola = _product(db, "Cola App Lev", voorraad=0)
    bier = _product(db, "Bier App Lev", voorraad=0)
    _bij(db, cola, sligro)
    antwoord = _post(app_client, "/api/app/bestellijst/bestellen", aantallen={str(cola): 1, str(bier): 2}, verzoek_id="lev-1").get_json()
    assert [(b["leverancier"], b["regels"]) for b in antwoord["bestellingen"]] == [("Sligro App", 1), (None, 1)]
    assert antwoord["melding"].startswith("2 bestellingen klaargezet")
    producten = app_client.get("/api/app/producten").get_json()["producten"]
    assert next(p for p in producten if p["id"] == cola)["leverancier"] == "Sligro App"


def test_een_leverancier_geeft_een_bestelling(db):
    lid = _leverancier(db, "Alleen")
    pid = _product(db, "Een Lev", voorraad=0)
    _bij(db, pid, lid)
    assert [(b["leverancier"], b["regels"]) for b in maak_bestellingen(db, {pid: 1})] == [("Alleen", 1)]
    assert maak_bestellingen(db, {pid: 0}) == []


# ---------- "Op de bestellijst" ----------


def test_op_de_bestellijst_volgt_het_advies(db, prognose):  # noqa: F811
    pid = _product(db, "Ranja Advies Lijst", voorraad=0, minimum=0, factor=6, besteleenheid="doos")
    prognose[pid] = (10, 15)
    product = db.execute("SELECT * FROM producten WHERE id = ?", (pid,)).fetchone()
    blok, melding = bestelvoorstel.zet_op_bestellijst(db, product, "Luuk")
    assert blok["gekozen"] == 3 and melding == "Ranja Advies Lijst staat bij Voorgesteld om te bestellen: 3 doos."


# ---------- De herinnering om te bestellen ----------


def test_herinnering_een_paar_uur_van_tevoren_maar_niet_s_nachts():
    assert bestelvoorstel.herinner_moment(datetime(2026, 10, 27, 16, 0)) == datetime(2026, 10, 27, 13, 0)
    assert bestelvoorstel.herinner_moment(datetime(2026, 10, 27, 9, 0)) == datetime(2026, 10, 26, 20, 0)
    assert bestelvoorstel.herinner_moment(datetime(2026, 10, 28, 0, 30)) == datetime(2026, 10, 27, 21, 30)
    assert bestelvoorstel.herinner_moment(datetime(2026, 10, 28, 1, 30)) == datetime(2026, 10, 27, 20, 0)


def test_bestelmomenten_voor_de_app(app_client, db):  # noqa: F811
    lid = _leverancier(db, "Sligro Moment")  # dinsdag en donderdag vóór 16.00 uur
    _leverancier(db, "Zonder Dagen", besteldagen="")
    laag = _product(db, "Laag Moment", voorraad=0, minimum=5)
    gekozen = _product(db, "Gekozen Moment", voorraad=50)
    _bij(db, laag, lid)
    _bij(db, gekozen, lid)
    bestelvoorstel.zet_bestelaantal(db, gekozen, 2)

    nu = datetime(2026, 10, 26, 10, 0)  # maandag; 8 dagen vooruit is tot dinsdag 3 november 10.00 uur, dus zonder die van 16.00 uur
    momenten = bestelvoorstel.bestelmomenten(db, nu)
    assert [(m["leverancier"], m["uiterst"], m["herinnering"]) for m in momenten] == [
        ("Sligro Moment", "2026-10-27 16:00", "2026-10-27 13:00"),
        ("Sligro Moment", "2026-10-29 16:00", "2026-10-29 13:00"),
    ]
    assert momenten[0]["aantal"] == 2 and momenten[0]["al_besteld"] is False
    assert momenten[0]["tijd"] == "16:00" and momenten[0]["levering_tekst"] == "wo 28-10"

    # Na het klaarzetten bij die leverancier is het eerstvolgende moment al besteld.
    db.execute("INSERT INTO bestellingen (status, aangemaakt_op, leverancier_id) VALUES ('besteld', '2026-10-26 09:00', ?)", (lid,))
    db.commit()
    assert bestelvoorstel.bestelmomenten(db, nu)[0]["al_besteld"] is True

    start = app_client.get("/api/app/start").get_json()
    assert all(m["leverancier"] == "Sligro Moment" for m in start["bestelmomenten"])


# ---------- In de app: de telling corrigeren, naam en prijs aanpassen ----------


def _telling(db, pid, voor, geteld, datum):
    tid = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (datum,)).lastrowid
    rid = db.execute(
        """INSERT INTO telling_regels (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, correctie, verkoopprijs)
           VALUES (?, ?, ?, ?, ?, 0, 2.0)""",
        (tid, pid, voor, geteld, max(0, voor - geteld)),
    ).lastrowid
    db.commit()
    return tid, rid


def test_telling_corrigeren_in_de_app(app_client, db):  # noqa: F811
    pid = _product(db, "Pils Correctie", voorraad=10)
    tid, rid = _telling(db, pid, voor=30, geteld=10, datum="2026-10-24 22:00")
    regels = app_client.get(f"/api/app/tellingen/{tid}").get_json()["regels"]
    assert regels[0]["regel_id"] == rid and regels[0]["laatste"] is True

    antwoord = _post(app_client, f"/api/app/tellingen/regels/{rid}/corrigeren", geteld=14, verzoek_id="corr-1").get_json()
    assert "gecorrigeerd: 10 → 14 stuks geteld" in antwoord["melding"] and "van 10 naar 14" in antwoord["melding"]
    regel = db.execute("SELECT geteld_aantal, verkocht, gecorrigeerd_door FROM telling_regels WHERE id = ?", (rid,)).fetchone()
    assert (regel["geteld_aantal"], regel["verkocht"]) == (14, 16) and regel["gecorrigeerd_door"]
    assert db.execute("SELECT voorraad FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 14
    assert _post(app_client, f"/api/app/tellingen/regels/{rid}/corrigeren", geteld=-1, verzoek_id="corr-2").status_code == 400


def test_naam_en_prijs_aanpassen_in_de_app(app_client, db):  # noqa: F811
    pid = _product(db, "Fanta Oud", voorraad=10)
    antwoord = _post(app_client, f"/api/app/producten/{pid}/instellingen", min_voorraad=6, besteleenheid="tray",
                     besteleenheid_factor=24, naam="Fanta Orange", verkoopprijs="2,25")
    assert antwoord.status_code == 200
    p = db.execute("SELECT naam, verkoopprijs, min_voorraad FROM producten WHERE id = ?", (pid,)).fetchone()
    assert (p["naam"], p["verkoopprijs"], p["min_voorraad"]) == ("Fanta Orange", 2.25, 6)
    geschiedenis = db.execute("SELECT oude_prijs, nieuwe_prijs FROM prijs_geschiedenis WHERE product_id = ?", (pid,)).fetchone()
    assert (geschiedenis["oude_prijs"], geschiedenis["nieuwe_prijs"]) == (2.0, 2.25)
    fout = _post(app_client, f"/api/app/producten/{pid}/instellingen", min_voorraad=6, besteleenheid="", besteleenheid_factor=1,
                 verkoopprijs="veel")
    assert fout.status_code == 400 and "prijs" in fout.get_json()["melding"]
    # Zonder naam en prijs (een oudere app): die blijven zoals ze waren.
    _post(app_client, f"/api/app/producten/{pid}/instellingen", min_voorraad=8, besteleenheid="", besteleenheid_factor=1)
    p = db.execute("SELECT naam, verkoopprijs, min_voorraad FROM producten WHERE id = ?", (pid,)).fetchone()
    assert (p["naam"], p["verkoopprijs"], p["min_voorraad"]) == ("Fanta Orange", 2.25, 8)
