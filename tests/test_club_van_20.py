import sqlite3
from datetime import date

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from club_van_20 import (
    bereken_club_van_20_status,
    financien,
    huidig_seizoen,
    normaliseer_seizoen,
    parse_import,
    seizoen_van_datum,
    verschuif_seizoen,
    verzoek_tekst,
    voer_import_uit,
    whatsapp_link,
)

HUIDIG = huidig_seizoen()
VORIG = verschuif_seizoen(HUIDIG, -1)
TWEE_TERUG = verschuif_seizoen(HUIDIG, -2)


def _lid(db, naam, team=None, status="actief", **extra):
    db.execute(
        """INSERT INTO club_van_20_leden (naam, team, status, extra_groot, eerdere_seizoenen, aangemaakt_op)
           VALUES (?, ?, ?, ?, ?, '2026-01-01 10:00')""",
        (naam, team, status, extra.get("extra_groot", 0), extra.get("eerdere_seizoenen", 0)),
    )
    db.commit()
    return db.execute("SELECT id FROM club_van_20_leden WHERE naam = ?", (naam,)).fetchone()["id"]


def _bijdrage(db, lid_id, seizoen, status="betaald", bedrag=20, betaald_op=None):
    db.execute(
        """INSERT INTO club_van_20_bijdragen (lid_id, seizoen, status, bedrag, betaald_op)
           VALUES (?, ?, ?, ?, ?)""",
        (lid_id, seizoen, status, bedrag, betaald_op),
    )
    db.commit()


def _zet(db, **velden):
    for veld, waarde in velden.items():
        db.execute(f"UPDATE kiosk_scherm_instellingen SET {veld} = ? WHERE id = 1", (waarde,))
    db.commit()


def _alleen_club_van_20(db):
    _zet(db, toon_sponsoren=0, toon_wedstrijden=0, toon_standen=0, toon_motm=0, toon_club_van_20=1)


# ---------- Seizoenen ----------


def test_seizoen_loopt_van_1_juli_tot_30_juni():
    assert seizoen_van_datum(date(2026, 6, 30)) == "2025-2026"
    assert seizoen_van_datum(date(2026, 7, 1)) == "2026-2027"
    assert seizoen_van_datum("2027-01-15") == "2026-2027"
    assert verschuif_seizoen("2026-2027", -3) == "2023-2024"


def test_normaliseer_seizoen():
    assert normaliseer_seizoen("2023-2024") == "2023-2024"
    assert normaliseer_seizoen("2023/2024") == "2023-2024"
    assert normaliseer_seizoen("2023-24") == "2023-2024"
    assert normaliseer_seizoen("2023-2025") is None
    assert normaliseer_seizoen("Voornaam") is None


# ---------- Kantine scherm ----------


def test_scherm_toont_betalers_en_verbergt_gestopte_leden(client, db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Betaalt Nu"), HUIDIG)
    _bijdrage(db, _lid(db, "Betaalde Vorig Jaar"), VORIG)
    _bijdrage(db, _lid(db, "Lang Geleden"), TWEE_TERUG)
    _bijdrage(db, _lid(db, "Gestopt Lid", status="inactief"), HUIDIG)
    stopt = _lid(db, "Zegt Af")
    _bijdrage(db, stopt, VORIG)
    _bijdrage(db, stopt, HUIDIG, status="afgezegd", bedrag=0)
    _lid(db, "Nooit Betaald")

    tekst = client.get("/kiosk/scherm").data.decode()

    assert "Betaalt Nu" in tekst
    # Standaard telt een betaling van vorig seizoen nog mee.
    assert "Betaalde Vorig Jaar" in tekst
    assert "Lang Geleden" not in tekst
    assert "Gestopt Lid" not in tekst
    assert "Zegt Af" not in tekst
    assert "Nooit Betaald" not in tekst


def test_scherm_alleen_dit_seizoen_en_markeer_onbetaald(client, db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Betaalt Nu"), HUIDIG)
    _bijdrage(db, _lid(db, "Nog Niet Betaald"), VORIG)

    _zet(db, club_van_20_zichtbaar_seizoenen=1)
    tekst = client.get("/kiosk/scherm").data.decode()
    assert "Betaalt Nu" in tekst
    assert "Nog Niet Betaald" not in tekst

    _zet(db, club_van_20_zichtbaar_seizoenen=2, club_van_20_markeer_onbetaald=1)
    tekst = client.get("/kiosk/scherm").data.decode()
    positie = tekst.index("Nog Niet Betaald")
    assert "c20-bordje--niet-betaald" in tekst[max(0, positie - 400) : positie]
    positie = tekst.index("Betaalt Nu")
    assert "c20-bordje--niet-betaald" not in tekst[max(0, positie - 400) : positie]


def test_scherm_goud_zilver_nieuw_en_sterren(client, db):
    _alleen_club_van_20(db)
    trouw = _lid(db, "Trouw Lid")
    for s in (TWEE_TERUG, VORIG, HUIDIG):
        _bijdrage(db, trouw, s)
    zilver = _lid(db, "Tweede Jaar")
    _bijdrage(db, zilver, VORIG)
    _bijdrage(db, zilver, HUIDIG)
    _bijdrage(db, _lid(db, "Nieuwkomer"), HUIDIG)
    _bijdrage(db, _lid(db, "Oud Lid Zonder Historie", eerdere_seizoenen=4), HUIDIG)

    tekst = client.get("/kiosk/scherm").data.decode()

    def klassen(naam):
        positie = tekst.index(f'<span class="c20-naam">{naam}</span>')
        begin = tekst.rindex('<div class="c20-bordje', 0, positie)
        return tekst[begin:positie]

    assert "c20-bordje--goud" in klassen("Trouw Lid") and "★★★" in klassen("Trouw Lid")
    assert "c20-bordje--zilver" in klassen("Tweede Jaar")
    assert "c20-bordje--nieuw" in klassen("Nieuwkomer")
    # Eerdere seizoenen (van vóór de administratie) tellen mee voor goud,
    # en maken iemand geen "nieuw" lid.
    assert "c20-bordje--goud" in klassen("Oud Lid Zonder Historie")
    assert "c20-bordje--nieuw" not in klassen("Oud Lid Zonder Historie")


def test_scherm_verdeelt_namen_en_vult_laatste_dia_met_lege_vakjes(client, db):
    _alleen_club_van_20(db)
    _zet(db, club_van_20_namen_per_slide=4, club_van_20_kolommen=2)
    for naam in ["Aad", "Bram", "Cor", "Dirk", "Evert"]:
        _bijdrage(db, _lid(db, naam), HUIDIG)

    tekst = client.get("/kiosk/scherm").data.decode()

    assert "1/2" in tekst and "2/2" in tekst
    assert tekst.count("c20-bordje--leeg") == 3
    assert "Jouw naam hier?" in tekst


def test_scherm_teller_teams_nieuw_en_werving(client, db):
    _alleen_club_van_20(db)
    vandaag = date.today().isoformat()
    for i in range(3):
        _bijdrage(db, _lid(db, f"Za1 Speler {i}", team="Za1"), HUIDIG, betaald_op=vandaag)
    _bijdrage(db, _lid(db, "Za2 Speler", team="Za2"), HUIDIG, betaald_op=vandaag)
    db.execute(
        """INSERT INTO club_van_20_projecten (naam, raming, status, volgorde, aangemaakt_op)
           VALUES ('Bartafels', 50, 'klaar', 1, 'x'), ('Terrasdeuren', 100, 'gepland', 2, 'x')"""
    )
    db.commit()

    tekst = client.get("/kiosk/scherm").data.decode()

    assert "slide-club_van_20_teller" in tekst
    assert 'data-telop="80"' in tekst
    assert "Bartafels" in tekst
    # 80 opgehaald - 50 besteed = 30 van de 100 voor het volgende doel.
    assert "Terrasdeuren" in tekst and "--procent: 30%" in tekst
    assert "slide-club_van_20_teams" in tekst
    assert "Za1 leidt met 2 naambordjes voorsprong!" in tekst
    assert "Welkom in de Club van 20!" in tekst
    assert "Ook bij de Club van 20?" in tekst
    assert "<svg" in tekst  # QR-code naar de publieke pagina


def test_scherm_geen_werving_zonder_leden(client, db):
    _alleen_club_van_20(db)
    tekst = client.get("/kiosk/scherm").data.decode()
    assert "Ook bij de Club van 20?" not in tekst
    assert "nog niets ingesteld" in tekst


# ---------- Administratie ----------


def test_overzicht_en_bijdrage_opslaan_via_ajax(ingelogde_client, db):
    lid_id = _lid(db, "Jan Jansen", team="Za1")
    resp = ingelogde_client.get("/club-van-20")
    assert resp.status_code == 200
    assert b"Jan Jansen" in resp.data

    resp = ingelogde_client.post(
        f"/club-van-20/leden/{lid_id}/bijdrage",
        data={"csrf_token": _csrf(ingelogde_client), "seizoen": HUIDIG, "status": "betaald", "betaald_door": "Vader"},
        headers={"X-Requested-With": "fetch"},
    )
    data = resp.get_json()
    assert data["ok"] is True and data["status"] == "betaald" and data["bedrag"] == 20

    rij = db.execute("SELECT * FROM club_van_20_bijdragen WHERE lid_id = ?", (lid_id,)).fetchone()
    assert rij["status"] == "betaald"
    assert rij["betaald_door"] == "Vader"
    assert rij["betaald_op"] is not None
    assert rij["bijgewerkt_door"] == "admin"

    # Terug naar "niet gevraagd" zonder verdere gegevens = rij weg... maar
    # hier staat nog "betaald door", dus blijft de rij (zonder betaaldatum).
    ingelogde_client.post(
        f"/club-van-20/leden/{lid_id}/bijdrage",
        data={"csrf_token": _csrf(ingelogde_client), "seizoen": HUIDIG, "status": "gevraagd"},
        headers={"X-Requested-With": "fetch"},
    )
    rij = db.execute("SELECT * FROM club_van_20_bijdragen WHERE lid_id = ?", (lid_id,)).fetchone()
    assert rij["status"] == "gevraagd" and rij["betaald_op"] is None and rij["bedrag"] == 0
    assert rij["betaald_door"] == "Vader"


def test_bulk_zet_meerdere_leden_op_gevraagd(ingelogde_client, db):
    ids = [_lid(db, "Een"), _lid(db, "Twee")]
    resp = ingelogde_client.post(
        "/club-van-20/bulk",
        data={"csrf_token": _csrf(ingelogde_client), "seizoen": HUIDIG, "status": "gevraagd", "lid_ids": [str(i) for i in ids]},
    )
    assert resp.status_code == 302
    statussen = [r["status"] for r in db.execute("SELECT status FROM club_van_20_bijdragen").fetchall()]
    assert statussen == ["gevraagd", "gevraagd"]


def test_lid_nieuw_met_betaling_en_dubbel_naambordje(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/club-van-20/leden/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "voornaam": "Piet",
            "achternaam": "Pietersen",
            "naam": "",
            "team": "Za2",
            "status_seizoen": "betaald",
            "bedrag": "25",
            "betaalwijze": "contant",
        },
    )
    assert resp.status_code == 302
    lid = db.execute("SELECT * FROM club_van_20_leden WHERE naam = 'Piet Pietersen'").fetchone()
    assert lid["team"] == "Za2" and lid["status"] == "actief"
    b = db.execute("SELECT * FROM club_van_20_bijdragen WHERE lid_id = ?", (lid["id"],)).fetchone()
    assert (b["seizoen"], b["status"], b["bedrag"], b["betaalwijze"]) == (HUIDIG, "betaald", 25, "contant")

    ingelogde_client.post(
        "/club-van-20/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "piet pietersen"},
    )
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 1


def test_lid_bewerken_toont_verzoek_en_slaat_op(ingelogde_client, db):
    lid_id = _lid(db, "Bonkie")
    _bijdrage(db, lid_id, VORIG)
    db.execute("UPDATE club_van_20_leden SET voornaam = 'Mark', telefoon = '06-12345678' WHERE id = ?", (lid_id,))
    db.commit()

    resp = ingelogde_client.get(f"/club-van-20/leden/{lid_id}")
    tekst = resp.data.decode()
    assert "Hoi Mark!" in tekst
    assert "https://wa.me/31612345678?text=" in tekst

    resp = ingelogde_client.post(
        f"/club-van-20/leden/{lid_id}",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Bonkie", "voornaam": "Mark", "inactief": "on"},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT status FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()["status"] == "inactief"


def test_lid_verwijderen_verwijdert_ook_betalingen(ingelogde_client, db):
    lid_id = _lid(db, "Weg")
    _bijdrage(db, lid_id, HUIDIG)
    ingelogde_client.post(f"/club-van-20/leden/{lid_id}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_bijdragen").fetchone()["n"] == 0


def test_projecten_toevoegen_status_en_financien(ingelogde_client, db):
    _bijdrage(db, _lid(db, "Gever"), HUIDIG, bedrag=500)
    ingelogde_client.post(
        "/club-van-20/projecten",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Buitenspeakers", "raming": "300", "status": "bezig"},
    )
    ingelogde_client.post(
        "/club-van-20/projecten",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Terras", "raming": "1000", "status": "gepland"},
    )
    geld = financien(db)
    assert geld["opgehaald"] == 500 and geld["besteed"] == 300 and geld["beschikbaar"] == 200
    assert geld["doel"]["naam"] == "Terras" and geld["doel"]["procent"] == 20
    assert geld["doel"]["nog_bordjes"] == 40

    project_id = db.execute("SELECT id FROM club_van_20_projecten WHERE naam = 'Buitenspeakers'").fetchone()["id"]
    resp = ingelogde_client.post(
        f"/club-van-20/projecten/{project_id}/status",
        data={"csrf_token": _csrf(ingelogde_client), "status": "klaar"},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.get_json()["ok"] is True
    project = db.execute("SELECT * FROM club_van_20_projecten WHERE id = ?", (project_id,)).fetchone()
    assert project["status"] == "klaar" and project["afgerond_op"]

    assert b"Buitenspeakers" in ingelogde_client.get("/club-van-20/projecten").data


def test_instellingen_opslaan_en_onveilige_betaallink_weigeren(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/club-van-20/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "toon_club_van_20": "on",
            "club_van_20_titel": "Onze Club",
            "club_van_20_namen_per_slide": "24",
            "club_van_20_kolommen": "4",
            "club_van_20_duur_seconden": "15",
            "club_van_20_zichtbaar_seizoenen": "1",
            "club_van_20_bedrag": "25",
            "club_van_20_betaallink": "javascript:alert(1)",
            "club_van_20_werving_tekst": "Vraag het aan de bar",
            "club_van_20_verzoek_tekst": "Hoi {voornaam}",
        },
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert rij["club_van_20_titel"] == "Onze Club"
    assert rij["club_van_20_zichtbaar_seizoenen"] == 1
    assert rij["club_van_20_bedrag"] == 25
    assert rij["club_van_20_betaallink"] is None
    assert rij["club_van_20_toon_teams"] == 0
    assert ingelogde_client.get("/club-van-20/instellingen").status_code == 200


def test_vrijwilliger_heeft_club_van_20_sectie_nodig(client, db):
    _maak_vrijwilliger(db, "zonder_c20", "voorraad,kantine_tv")
    _login(client, "zonder_c20")
    assert client.get("/club-van-20").status_code == 302
    assert "Club van 20" not in client.get("/").data.decode().split("<main")[0]
    client.get("/logout")

    _maak_vrijwilliger(db, "met_c20", "club_van_20")
    _login(client, "met_c20")
    assert client.get("/club-van-20").status_code == 200
    assert client.get("/club-van-20/projecten").status_code == 200


def test_publieke_pagina_zonder_login(client, db):
    _bijdrage(db, _lid(db, "Publiek Lid"), HUIDIG)
    resp = client.get("/club-van-20/doe-mee")
    assert resp.status_code == 200
    assert b"Publiek Lid" in resp.data
    assert b"Ook bij de Club van 20?" in resp.data


def test_dashboard_status_telt_verwachte_leden(db):
    _bijdrage(db, _lid(db, "Al Betaald"), HUIDIG)
    _bijdrage(db, _lid(db, "Moet Nog"), VORIG)
    gevraagd = _lid(db, "Gevraagd Nieuw")
    _bijdrage(db, gevraagd, HUIDIG, status="gevraagd", bedrag=0)
    _lid(db, "Nooit Lid Geweest")
    stopt = _lid(db, "Stopt")
    _bijdrage(db, stopt, VORIG)
    _bijdrage(db, stopt, HUIDIG, status="afgezegd", bedrag=0)

    status = bereken_club_van_20_status(db)

    assert {l["naam"] for l in status["leden"]} == {"Moet Nog", "Gevraagd Nieuw"}
    assert status["niet_gevraagd"] == 1
    assert status["betaald"] == 1
    assert status["ok"] is False


def test_dashboard_tegel_alleen_met_sectie(client, db):
    _bijdrage(db, _lid(db, "Moet Nog"), VORIG)
    csrf = _csrf(client)
    client.post("/login", data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": csrf})
    tekst = client.get("/").data.decode()
    assert "Moet Nog" in tekst and "nog niet betaald" in tekst
    client.get("/logout")

    _maak_vrijwilliger(db, "vrijwilliger_dashboard", "voorraad")
    _login(client, "vrijwilliger_dashboard")
    assert b"Moet Nog" not in client.get("/").data


# ---------- Importeren / exporteren ----------

SPREADSHEET = """,,,Totale opbrengst,"€1,840","€1,100",€100,€0,,
Voornaam,Achternaam,Team,Naambordje,2023-2024,2024-2025,2025-2026,2026-2027,Status 2026-2027,Betaald door
Albert,Boer,,Albert,20,20,,,Niet gevraagd,
A.,Hamming,,?,20,,,,Niet gevraagd,
?,?,SJO?,Mv. Subaeswaren,,,20,0,Betaald,
Ten Boer,On Tour,,Ten Boer On Tour,160,,,,Niet gevraagd,
Jan,Bartelds,,Bartelds sr.,-,,,,Gevraagd,Zoon
,,,,,,,,,
"""


def test_parse_import_van_de_oude_spreadsheet():
    resultaat = parse_import(SPREADSHEET)
    assert resultaat["fout"] is None
    assert resultaat["seizoenen"] == ["2023-2024", "2024-2025", "2025-2026", "2026-2027"]
    rijen = {r["naam"]: r for r in resultaat["rijen"]}
    assert set(rijen) == {"Albert", "A. Hamming", "Mv. Subaeswaren", "Ten Boer On Tour", "Bartelds sr."}

    assert rijen["Albert"]["bijdragen"] == {
        "2023-2024": {"status": "betaald", "bedrag": 20},
        "2024-2025": {"status": "betaald", "bedrag": 20},
    }
    assert rijen["Ten Boer On Tour"]["bijdragen"]["2023-2024"]["bedrag"] == 160
    # "Betaald" in de statuskolom maar expliciet 0 in de bedragkolom: geen betaling.
    assert "2026-2027" not in rijen["Mv. Subaeswaren"]["bijdragen"]
    assert rijen["Mv. Subaeswaren"]["team"] == "SJO"
    assert rijen["Mv. Subaeswaren"]["voornaam"] == ""
    assert rijen["Bartelds sr."]["bijdragen"]["2026-2027"] == {
        "status": "gevraagd", "bedrag": 0, "betaald_door": "Zoon"
    }
    assert any("A. Hamming" in w for w in resultaat["waarschuwingen"])


def test_parse_import_tab_gescheiden_geplakt():
    tekst = "Naambordje\t2024-2025\nPlakker\t20\n"
    rijen = parse_import(tekst)["rijen"]
    assert rijen[0]["naam"] == "Plakker"
    assert rijen[0]["bijdragen"]["2024-2025"]["status"] == "betaald"


def test_parse_import_zonder_kopregel_geeft_fout():
    assert parse_import("a,b,c\n1,2,3\n")["fout"]


def test_import_via_pagina_voorbeeld_en_bevestigen(ingelogde_client, db):
    _lid(db, "Albert")  # bestaat al -> wordt bijgewerkt, niet dubbel
    resp = ingelogde_client.post(
        "/club-van-20/importeren", data={"csrf_token": _csrf(ingelogde_client), "tekst": SPREADSHEET}
    )
    assert resp.status_code == 200
    assert b"Voorbeeld: 5 leden" in resp.data
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 1

    resp = ingelogde_client.post(
        "/club-van-20/importeren",
        data={"csrf_token": _csrf(ingelogde_client), "tekst": SPREADSHEET, "bevestig": "1"},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 5
    albert = db.execute("SELECT * FROM club_van_20_leden WHERE naam = 'Albert'").fetchone()
    assert albert["achternaam"] == "Boer"
    totaal = db.execute(
        "SELECT SUM(bedrag) AS s FROM club_van_20_bijdragen WHERE seizoen = '2023-2024' AND status = 'betaald'"
    ).fetchone()["s"]
    assert totaal == 20 + 20 + 160
    # Historische betalingen krijgen de start van hun seizoen als datum,
    # zodat niet iedereen ineens als "nieuw" op de welkomstdia komt.
    assert db.execute(
        "SELECT betaald_op FROM club_van_20_bijdragen WHERE seizoen = '2023-2024' LIMIT 1"
    ).fetchone()["betaald_op"] == "2023-07-01"


def test_export_csv_is_weer_te_importeren(ingelogde_client, db):
    lid_id = _lid(db, "Export Lid", team="Za1")
    _bijdrage(db, lid_id, VORIG, bedrag=20)
    resp = ingelogde_client.get("/club-van-20/export.csv")
    assert resp.status_code == 200
    tekst = resp.data.decode("utf-8-sig")
    assert "Naambordje" in tekst and "Export Lid" in tekst and VORIG in tekst

    rijen = parse_import(tekst)["rijen"]
    assert rijen[0]["naam"] == "Export Lid"
    assert rijen[0]["bijdragen"][VORIG] == {"status": "betaald", "bedrag": 20}


def test_voer_import_uit_overschrijft_alleen_geimporteerde_seizoenen(db):
    lid_id = _lid(db, "Bestaand")
    _bijdrage(db, lid_id, "2020-2021", bedrag=15)
    voer_import_uit(db, parse_import("Naambordje,2023-2024\nBestaand,20\n")["rijen"])
    seizoenen = {
        r["seizoen"]: r["bedrag"]
        for r in db.execute("SELECT * FROM club_van_20_bijdragen WHERE lid_id = ?", (lid_id,)).fetchall()
    }
    assert seizoenen == {"2020-2021": 15, "2023-2024": 20}


# ---------- Hulpjes ----------


def test_verzoek_tekst_en_whatsapp_link():
    lid = {"naam": "Bonkie", "voornaam": "Mark"}
    tekst = verzoek_tekst("Hoi {voornaam}, {naambordje} voor €{bedrag} in {seizoen}. {betaallink} {onbekend}", lid, "2026-2027", 20.0, "https://x.nl")
    assert tekst == "Hoi Mark, Bonkie voor €20 in 2026-2027. https://x.nl {onbekend}"
    assert whatsapp_link("06 12 34 56 78", "hoi").startswith("https://wa.me/31612345678?text=hoi")
    assert whatsapp_link("+31 6 1234 5678", "x").startswith("https://wa.me/31612345678")
    assert whatsapp_link("", "x") is None


def test_omzetting_van_oude_leden_naar_seizoenen(tmp_path):
    """_migreer_club_van_20_administratie zet een database van vóór de
    administratie eenmalig om: actief -> betaald in het seizoen van de
    startdatum, niet betaald -> gevraagd voor dit seizoen (en weer actief)."""
    from database import _migreer_club_van_20_administratie

    db = sqlite3.connect(str(tmp_path / "oud.db"))
    db.row_factory = sqlite3.Row
    db.executescript(
        """CREATE TABLE club_van_20_leden (id INTEGER PRIMARY KEY, naam TEXT, aangemaakt_op TEXT,
               status TEXT, startdatum TEXT, einddatum TEXT, extra_groot INTEGER DEFAULT 0);
           CREATE TABLE club_van_20_bijdragen (id INTEGER PRIMARY KEY, lid_id INTEGER, seizoen TEXT,
               status TEXT, bedrag REAL, betaald_door TEXT, betaalwijze TEXT, betaald_op TEXT, notitie TEXT,
               bijgewerkt_door TEXT, bijgewerkt_op TEXT, UNIQUE(lid_id, seizoen));
           INSERT INTO club_van_20_leden VALUES (1, 'Actief', '2025-03-01 10:00', 'actief', '2025-03-01', '2026-03-01', 0);
           INSERT INTO club_van_20_leden VALUES (2, 'Wanbetaler', '2025-03-01 10:00', 'niet_betaald', '2025-03-01', '2026-03-01', 0);
           INSERT INTO club_van_20_leden VALUES (3, 'Gestopt', '2025-03-01 10:00', 'inactief', '2025-03-01', '2026-03-01', 0);"""
    )
    _migreer_club_van_20_administratie(db)
    _migreer_club_van_20_administratie(db)  # tweede keer doet niets meer

    rijen = {(r["lid_id"], r["seizoen"], r["status"]) for r in db.execute("SELECT * FROM club_van_20_bijdragen")}
    assert rijen == {(1, "2024-2025", "betaald"), (2, HUIDIG, "gevraagd")}
    assert db.execute("SELECT status FROM club_van_20_leden WHERE id = 2").fetchone()["status"] == "actief"
    kolommen = {r["name"] for r in db.execute("PRAGMA table_info(club_van_20_leden)")}
    assert {"voornaam", "achternaam", "team", "telefoon", "eerdere_seizoenen"} <= kolommen
