import io
import sqlite3
import zipfile
from datetime import date

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from club_van_20 import (
    bereken_club_van_20_status,
    rijen_naar_csv,
    rijen_uit_xlsx,
    sterren_voor,
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
HUIDIG_JAAR = int(HUIDIG[:4])
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
    _zet(db, club_van_20_toon_onbetaald=0)  # deze test gaat over de naammuur, niet over de Steun-de-club-dia
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
    _zet(db, club_van_20_toon_onbetaald=0)  # deze test gaat over de naammuur, niet over de Steun-de-club-dia
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


def test_scherm_glans_vanaf_twee_sterren_nieuw_en_oude_seizoenen(client, db):
    _alleen_club_van_20(db)
    # 1 ster (3 seizoenen): nog een gewoon wit bordje, wel met het sterlabel.
    een_ster = _lid(db, "Een Ster")
    for s in (TWEE_TERUG, VORIG, HUIDIG):
        _bijdrage(db, een_ster, s)
    # 2 sterren (6 seizoenen): glanzend metaalgoud.
    twee_sterren = _lid(db, "Twee Sterren")
    for jaar in range(HUIDIG_JAAR - 5, HUIDIG_JAAR + 1):
        _bijdrage(db, twee_sterren, f"{jaar}-{jaar + 1}")
    # Geen ster (2 seizoenen): wit, geen label -- het oude zilver bestaat niet meer.
    twee_jaar = _lid(db, "Twee Jaar")
    _bijdrage(db, twee_jaar, VORIG)
    _bijdrage(db, twee_jaar, HUIDIG)
    _bijdrage(db, _lid(db, "Nieuwkomer"), HUIDIG)
    # Eerdere seizoenen (van vóór de administratie) tellen mee voor de sterren,
    # en maken iemand geen "nieuw" lid.
    _bijdrage(db, _lid(db, "Oud Lid Zonder Historie", eerdere_seizoenen=9), HUIDIG)

    tekst = client.get("/kiosk/scherm").data.decode()

    def klassen(naam):
        positie = tekst.index(f'<span class="c20-naam">{naam}</span>')
        begin = tekst.rindex('<div class="c20-bordje', 0, positie)
        return tekst[begin:positie]

    assert 'class="c20-sterren">★</span>' in klassen("Een Ster") and "c20-bordje--glans" not in klassen("Een Ster")
    assert "c20-bordje--glans" in klassen("Twee Sterren") and "c20-glans" in klassen("Twee Sterren")
    assert 'class="c20-sterren">★★</span>' in klassen("Twee Sterren")
    assert "c20-sterren" not in klassen("Twee Jaar") and "c20-bordje--glans" not in klassen("Twee Jaar")
    assert "c20-bordje--nieuw" in klassen("Nieuwkomer")
    assert "c20-bordje--glans" in klassen("Oud Lid Zonder Historie")  # 10 seizoenen = 3 sterren
    assert "c20-bordje--nieuw" not in klassen("Oud Lid Zonder Historie")
    assert "glanzend vanaf 6 seizoenen" in tekst

    # Instelbaar: glans al vanaf 1 ster.
    _zet(db, club_van_20_glans_vanaf_sterren=1)
    tekst = client.get("/kiosk/scherm").data.decode()
    assert "c20-bordje--glans" in klassen("Een Ster") and "glanzend vanaf 3 seizoenen" in tekst


def test_glans_instelling_opslaan(ingelogde_client, db):
    ingelogde_client.post(
        "/club-van-20/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "club_van_20_glans_vanaf_sterren": "3"},
    )
    assert db.execute("SELECT club_van_20_glans_vanaf_sterren AS n FROM kiosk_scherm_instellingen").fetchone()["n"] == 3
    pagina = ingelogde_client.get("/club-van-20/instellingen").data.decode()
    assert 'name="club_van_20_glans_vanaf_sterren"' in pagina and 'value="3"' in pagina


def test_scherm_verdeelt_namen_en_vult_laatste_dia_met_lege_vakjes(client, db):
    _alleen_club_van_20(db)
    _zet(db, club_van_20_namen_per_slide=4, club_van_20_kolommen=2)
    for naam in ["Aad", "Bram", "Cor", "Dirk", "Evert"]:
        _bijdrage(db, _lid(db, naam), HUIDIG)

    tekst = client.get("/kiosk/scherm").data.decode()

    assert "1/2" in tekst and "2/2" in tekst
    assert tekst.count("c20-bordje--leeg") == 3
    assert "Jouw naam hier?" in tekst


def test_laatste_dia_houdt_even_grote_bordjes(client, db):
    """Zonder lege vakjes heeft de laatste dia minder namen; standaard houdt
    die toch het raster van een volle dia (dus even grote bordjes). Alleen
    met "laatste dia vullen" worden de bordjes daar groter."""
    _alleen_club_van_20(db)
    _zet(db, club_van_20_namen_per_slide=8, club_van_20_kolommen=4, club_van_20_lege_vakjes=0)
    for i in range(10):
        _bijdrage(db, _lid(db, f"Lid {i:02d}"), HUIDIG)

    tekst = client.get("/kiosk/scherm").data.decode()
    assert tekst.count("--kolommen: 4; --rijen: 2;") == 2
    assert "c20-bordje--leeg" not in tekst

    _zet(db, club_van_20_laatste_dia_vullen=1)
    tekst = client.get("/kiosk/scherm").data.decode()
    assert "--kolommen: 4; --rijen: 2;" in tekst and "--kolommen: 4; --rijen: 1;" in tekst


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
    # Aantal teams voor de schaal op kleine tv-viewports (zie .c20-teams in de css).
    assert '<div class="c20-teams" style="--n: 2">' in tekst
    assert "Welkom in de Club van 20!" in tekst
    assert "Ook bij de Club van 20?" in tekst
    assert "<svg" in tekst  # QR-code naar de publieke pagina


def test_teamstrijd_toont_ook_teams_zonder_betalers(client, db):
    """Een team waarvan nog niemand (recent) betaald heeft, staat er toch
    op met 0 -- anders verschijnt een nieuw team (zoals O23) nooit."""
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Za1 Betaler", team="Za1"), HUIDIG)
    _bijdrage(db, _lid(db, "Za2 Betaler", team="Za2"), HUIDIG)
    _lid(db, "Nieuw O23 Lid", team="O23")
    _bijdrage(db, _lid(db, "Oud O23 Lid", team="O23"), TWEE_TERUG)
    _lid(db, "Gearchiveerd", team="Za5", status="inactief")

    tekst = client.get("/kiosk/scherm").data.decode()
    teams = tekst[tekst.index("slide-club_van_20_teams") :]
    assert '<span class="c20-team-naam">O23</span>' in teams
    assert "Za5" not in teams
    assert "Gelijk op tussen Za1 en Za2!" in teams


def test_scherm_meldt_nieuwe_versie_na_wijziging(client, db):
    """Het kantine scherm pollt /kiosk/scherm/versie en herlaadt zichzelf
    zodra die verandert -- een wijziging die op een dia zichtbaar is, moet
    dus altijd een andere versie opleveren."""
    _alleen_club_van_20(db)
    lid_id = _lid(db, "Teamwissel", team="Za1")
    _bijdrage(db, lid_id, HUIDIG)
    _bijdrage(db, _lid(db, "Ander", team="Za2"), HUIDIG)

    versie = client.get("/kiosk/scherm/versie").get_json()["versie"]
    assert client.get("/kiosk/scherm/versie").get_json()["versie"] == versie

    db.execute("UPDATE club_van_20_leden SET team = 'O23' WHERE id = ?", (lid_id,))
    db.commit()
    na_team = client.get("/kiosk/scherm/versie").get_json()["versie"]
    assert na_team != versie

    _bijdrage(db, _lid(db, "Nieuwe Betaler"), HUIDIG)
    assert client.get("/kiosk/scherm/versie").get_json()["versie"] != na_team


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
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Bonkie", "voornaam": "Mark", "team": "Za1"},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT team FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()["team"] == "Za1"


def test_archiveren_haalt_lid_van_scherm_en_bewaart_historie(ingelogde_client, client, db):
    _alleen_club_van_20(db)
    lid_id = _lid(db, "Stopper")
    _bijdrage(db, lid_id, HUIDIG)
    _bijdrage(db, _lid(db, "Blijver"), HUIDIG)

    resp = ingelogde_client.post(
        f"/club-van-20/leden/{lid_id}/archiveren",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.get_json()["gearchiveerd"] is True
    lid = db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
    assert lid["status"] == "inactief" and lid["gearchiveerd_op"]
    # Historie blijft, maar het lid staat niet meer op het scherm of in de actieve lijst.
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_bijdragen WHERE lid_id = ?", (lid_id,)).fetchone()["n"] == 1
    scherm = client.get("/kiosk/scherm").data.decode()
    assert "Stopper" not in scherm and "Blijver" in scherm
    assert "Stopper" not in ingelogde_client.get("/club-van-20").data.decode()
    archief = ingelogde_client.get("/club-van-20?weergave=gearchiveerd").data.decode()
    assert "Stopper" in archief and "Gearchiveerd" in archief and "Blijver" not in archief

    # Gegevens bewerken zet een gearchiveerd lid niet stilletjes terug.
    ingelogde_client.post(
        f"/club-van-20/leden/{lid_id}",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Stopper", "notitie": "wil van het bord"},
    )
    assert db.execute("SELECT status FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()["status"] == "inactief"

    ingelogde_client.post(
        f"/club-van-20/leden/{lid_id}/archiveren",
        data={"csrf_token": _csrf(ingelogde_client), "actie": "terugzetten"},
    )
    lid = db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
    assert lid["status"] == "actief" and lid["gearchiveerd_op"] is None
    assert "Stopper" in client.get("/kiosk/scherm").data.decode()


def test_bulk_archiveren_en_terugzetten(ingelogde_client, db):
    ids = [_lid(db, "Een"), _lid(db, "Twee"), _lid(db, "Drie")]
    ingelogde_client.post(
        "/club-van-20/bulk",
        data={"csrf_token": _csrf(ingelogde_client), "seizoen": HUIDIG, "status": "gevraagd",
              "actie": "archiveren", "lid_ids": [str(i) for i in ids[:2]]},
    )
    statussen = {r["naam"]: r["status"] for r in db.execute("SELECT naam, status FROM club_van_20_leden")}
    assert statussen == {"Een": "inactief", "Twee": "inactief", "Drie": "actief"}
    # Archiveren raakt de seizoensstatus niet.
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_bijdragen").fetchone()["n"] == 0

    ingelogde_client.post(
        "/club-van-20/bulk",
        data={"csrf_token": _csrf(ingelogde_client), "seizoen": HUIDIG, "status": "gevraagd",
              "actie": "terugzetten", "lid_ids": [str(ids[0])]},
    )
    assert db.execute("SELECT status FROM club_van_20_leden WHERE id = ?", (ids[0],)).fetchone()["status"] == "actief"


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


def test_namen_op_de_publieke_pagina_kunnen_uit_maar_het_scherm_houdt_ze(client, db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Publiek Lid", team="ZA2"), HUIDIG)
    _bijdrage(db, _lid(db, "Tweede Lid", team="ZA3"), HUIDIG)
    assert db.execute("SELECT club_van_20_publiek_namen FROM kiosk_scherm_instellingen").fetchone()[0] == 1  # standaard aan
    aan = client.get("/club-van-20/doe-mee").data.decode()
    assert "Publiek Lid" in aan and "Tweede Lid" in aan

    _zet(db, club_van_20_publiek_namen=0)
    uit = client.get("/club-van-20/doe-mee").data.decode()

    assert "Publiek Lid" not in uit and "Tweede Lid" not in uit
    assert "De Club van 20 &middot; seizoen" not in uit  # ook het kopje van de naamlijst is weg
    assert "naambordjes dit seizoen" in uit and ">2<" in uit  # het aantal blijft staan: dat is geen naam
    assert "Welk team steunt het meest?" in uit  # teamstand (alleen aantallen) ook
    # Op het scherm in de kantine blijven de namen staan.
    assert "Publiek Lid" in client.get("/kiosk/scherm").data.decode()


def test_namen_op_de_publieke_pagina_opslaan_via_de_instellingen(ingelogde_client, db):
    _alleen_club_van_20(db)
    pagina = ingelogde_client.get("/club-van-20/instellingen").data.decode()
    assert 'name="club_van_20_publiek_namen"' in pagina and "Leden op de publieke pagina" in pagina

    def bewaar(**velden):
        ingelogde_client.post("/club-van-20/instellingen", data={"csrf_token": _csrf(ingelogde_client), **velden})
        return db.execute("SELECT club_van_20_publiek_namen FROM kiosk_scherm_instellingen").fetchone()[0]

    assert bewaar(club_van_20_titel="Club van 20") == 0  # vinkje niet meegestuurd = uit
    assert bewaar(club_van_20_titel="Club van 20", club_van_20_publiek_namen="1") == 1


def test_aankondiging_telt_af_en_wisselt_na_afloop():
    from datetime import datetime, timezone

    from club_van_20 import AMSTERDAM, aankondiging

    instellingen = {
        "club_van_20_aankondiging_tekst": "Vanaf maandag kun jij verlengen!",
        "club_van_20_aankondiging_aftellen_tot": "2026-10-05T00:00",
        "club_van_20_aankondiging_na_tekst": "",
    }
    voor = aankondiging(instellingen, nu=datetime(2026, 9, 30, 21, 30, 15, tzinfo=AMSTERDAM))
    assert voor["aftellen"] is True
    assert (voor["dagen"], voor["uren"], voor["minuten"], voor["seconden"]) == (4, 2, 29, 45)
    assert voor["doel_label"] == "maandag 5 oktober, 00:00"
    # Amsterdamse tijd (zomertijd, UTC+2) -> 4 okt 22:00 UTC.
    assert voor["doel_ms"] == int(datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc).timestamp() * 1000)

    na = datetime(2026, 10, 5, 0, 0, 1, tzinfo=AMSTERDAM)
    assert aankondiging(instellingen, nu=na) is None
    instellingen["club_van_20_aankondiging_na_tekst"] = "Het is zover!"
    assert aankondiging(instellingen, nu=na) == {"tekst": "Het is zover!", "aftellen": False}

    zonder_tekst = dict(instellingen, club_van_20_aankondiging_tekst="", club_van_20_aankondiging_aftellen_tot=None)
    assert aankondiging(zonder_tekst) is None
    alleen_tekst = dict(instellingen, club_van_20_aankondiging_aftellen_tot=None)
    assert aankondiging(alleen_tekst)["aftellen"] is False


def test_aankondiging_opslaan_en_op_publieke_pagina(ingelogde_client, client, db):
    resp = ingelogde_client.post(
        "/club-van-20/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "toon_club_van_20": "on",
            "club_van_20_titel": "Club van 20",
            "club_van_20_zichtbaar_seizoenen": "2",
            "club_van_20_aankondiging_tekst": "Vanaf maandag kun jij verlengen of je opgeven!",
            "club_van_20_aankondiging_aftellen_tot": "2099-10-05T00:00",
            "club_van_20_aankondiging_na_tekst": "Het is zover!",
        },
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert rij["club_van_20_aankondiging_aftellen_tot"] == "2099-10-05T00:00"

    tekst = client.get("/club-van-20/doe-mee").data.decode()
    assert "Vanaf maandag kun jij verlengen of je opgeven!" in tekst
    assert 'class="aftelklok' in tekst and 'data-na-tekst="Het is zover!"' in tekst
    # De aankondiging staat bovenaan, vóór het "Ook bij de Club van 20?"-blok.
    assert tekst.index("aankondiging-in") < tekst.index('id="aankondiging"') < tekst.index("Ook bij de Club van 20?")

    # Een onleesbaar moment wordt gewoon leeg (dan alleen de tekst, zonder klok).
    ingelogde_client.post(
        "/club-van-20/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "club_van_20_aankondiging_tekst": "Hallo",
              "club_van_20_aankondiging_aftellen_tot": "morgen"},
    )
    assert db.execute("SELECT club_van_20_aankondiging_aftellen_tot AS t FROM kiosk_scherm_instellingen").fetchone()["t"] is None
    tekst = client.get("/club-van-20/doe-mee").data.decode()
    assert "Hallo" in tekst and 'class="aftelklok' not in tekst


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


# ---------- Sterren: 1 per 3 seizoenen ----------


def test_sterren_voor_per_drie_seizoenen():
    assert [sterren_voor(n) for n in range(0, 10)] == [0, 0, 0, 1, 1, 1, 2, 2, 2, 3]
    assert sterren_voor(5, per_ster=1) == 5  # oud gedrag: 1 ster per seizoen
    assert sterren_voor(7, per_ster=0) == 2  # onzinnige waarde valt terug op 3


def test_scherm_toont_ster_per_drie_seizoenen_en_legenda(client, db):
    _alleen_club_van_20(db)
    zes = _lid(db, "Zes Jaar")
    for jaar in range(HUIDIG_JAAR - 5, HUIDIG_JAAR + 1):
        _bijdrage(db, zes, f"{jaar}-{jaar + 1}")
    twee = _lid(db, "Twee Jaar")
    _bijdrage(db, twee, VORIG)
    _bijdrage(db, twee, HUIDIG)

    tekst = client.get("/kiosk/scherm").data.decode()

    def sterren(naam):
        positie = tekst.index(f'<span class="c20-naam">{naam}</span>')
        begin = tekst.rindex('<div class="c20-bordje', 0, positie)
        stuk = tekst[begin:positie]
        return stuk.count("★") if "c20-sterren" in stuk else 0

    assert sterren("Zes Jaar") == 2
    assert sterren("Twee Jaar") == 0
    assert "elke 3 seizoenen lid" in tekst

    _zet(db, club_van_20_seizoenen_per_ster=1)
    tekst = client.get("/kiosk/scherm").data.decode()
    # Meer dan 5 sterren worden compact als "6★" getoond i.p.v. zes losse sterren.
    assert 'class="c20-sterren">6★</span>' in tekst
    assert "elke 1 seizoenen lid" in tekst


def test_seizoenen_per_ster_instelbaar(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/club-van-20/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "club_van_20_seizoenen_per_ster": "4"},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT club_van_20_seizoenen_per_ster AS n FROM kiosk_scherm_instellingen").fetchone()["n"] == 4
    ingelogde_client.post(
        "/club-van-20/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "club_van_20_seizoenen_per_ster": "0"},
    )
    # Een onzinnige waarde (0) wordt 1: nooit een deling door nul of "geen enkele ster".
    assert db.execute("SELECT club_van_20_seizoenen_per_ster AS n FROM kiosk_scherm_instellingen").fetchone()["n"] == 1


def test_overzicht_en_publiek_gebruiken_dezelfde_sterrenregel(ingelogde_client, client, db):
    zes = _lid(db, "Zes Jaar")
    for jaar in range(HUIDIG_JAAR - 5, HUIDIG_JAAR + 1):
        _bijdrage(db, zes, f"{jaar}-{jaar + 1}")
    overzicht = ingelogde_client.get("/club-van-20").data.decode()
    assert 'title="6 seizoenen lid">★★</span>' in overzicht
    publiek = client.get("/club-van-20/doe-mee").data.decode()
    assert '<span class="sterren">★★</span>' in publiek


# ---------- Importeren: Excel ----------


def _maak_xlsx(bladen):
    """Bouwt een minimaal .xlsx-bestand. bladen: lijst van (naam, rijen, verborgen)."""
    gedeeld, index = [], {}

    def s_idx(tekst):
        if tekst not in index:
            index[tekst] = len(gedeeld)
            gedeeld.append(tekst)
        return index[tekst]

    sheet_xml = []
    for _, rijen, _ in bladen:
        regels = []
        for r, rij in enumerate(rijen, start=1):
            cellen = []
            for c, waarde in enumerate(rij):
                if waarde in ("", None):
                    continue
                ref = f"{chr(65 + c)}{r}"
                if isinstance(waarde, (int, float)):
                    cellen.append(f'<c r="{ref}"><v>{waarde}</v></c>')
                else:
                    cellen.append(f'<c r="{ref}" t="s"><v>{s_idx(waarde)}</v></c>')
            regels.append(f'<row r="{r}">{"".join(cellen)}</row>')
        sheet_xml.append(
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(regels)}</sheetData></worksheet>'
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        verborgen_attr = {True: ' state="hidden"', False: ""}
        sheets = "".join(
            f'<sheet name="{naam}" sheetId="{i}" r:id="rId{i}"{verborgen_attr[verborgen]}/>'
            for i, (naam, _, verborgen) in enumerate(bladen, start=1)
        )
        z.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheets}</sheets></workbook>',
        )
        rels = "".join(
            f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(bladen) + 1)
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>',
        )
        z.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{t}</t></si>" for t in gedeeld)
            + "</sst>",
        )
        for i, xml in enumerate(sheet_xml, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    return buffer.getvalue()


KOP = ["Voornaam", "Achternaam", "Team", "Naambordje", "2018-2019", "2025-2026", "2026-2027", "Status 2026-2027"]


def test_xlsx_kiest_het_ledenblad_en_slaat_verborgen_bladen_over():
    data = _maak_xlsx(
        [
            ("Oude lijst", [["Voornaam", "Naambordje"], ["Oud", "Verouderd Lid"]], True),
            ("Projecten", [["Project", "Raming"], ["Bartafels", 1000]], False),
            ("Ledenlijst", [["Totale opbrengst", "", "", "", 20], KOP, ["Jan", "Jansen", "Za1", "Jantje", 20, "", "", "Niet gevraagd"]], False),
        ]
    )
    rijen = rijen_uit_xlsx(data)
    assert rijen[1] == KOP and rijen[2][3] == "Jantje" and rijen[2][4] == "20"
    resultaat = parse_import(rijen_naar_csv(rijen))
    assert [r["naam"] for r in resultaat["rijen"]] == ["Jantje"]
    assert resultaat["rijen"][0]["bijdragen"]["2018-2019"] == {"status": "betaald", "bedrag": 20.0}


def test_xlsx_weigert_onzin_en_gevaarlijke_bestanden():
    import pytest

    with pytest.raises(ValueError, match="geldig Excel"):
        rijen_uit_xlsx(b"dit is geen zipbestand")
    with pytest.raises(ValueError, match="Naambordje"):
        rijen_uit_xlsx(_maak_xlsx([("Blad1", [["Iets", "Anders"], ["a", "b"]], False)]))
    kwaad = io.BytesIO()
    with zipfile.ZipFile(kwaad, "w") as z:
        z.writestr("xl/workbook.xml", '<!DOCTYPE x [<!ENTITY a "aaaa">]><workbook/>')
        z.writestr("xl/_rels/workbook.xml.rels", "<Relationships/>")
    with pytest.raises(ValueError, match="niet-ondersteunde"):
        rijen_uit_xlsx(kwaad.getvalue())


def test_import_xlsx_via_pagina_vult_alleen_gaten_en_laat_bestaande_details_staan(ingelogde_client, db):
    # Bestaand lid: team inmiddels in de app aangepast naar O23, betaling met details.
    lid = _lid(db, "Jantje", team="O23")
    db.execute(
        "INSERT INTO club_van_20_bijdragen (lid_id, seizoen, status, bedrag, betaalwijze, notitie) "
        "VALUES (?, '2025-2026', 'betaald', 20, 'contant', 'bij de bar')",
        (lid,),
    )
    db.commit()
    data = _maak_xlsx(
        [
            (
                "Ledenlijst",
                [
                    KOP,
                    ["Jan", "Jansen", "Za1", "Jantje", 20, 20, 20, "Betaald"],
                    ["Piet", "Pieters", "Za2", "Pietje", 20, "", "", "Niet gevraagd"],
                ],
                False,
            )
        ]
    )

    voorbeeld = ingelogde_client.post(
        "/club-van-20/importeren",
        data={"csrf_token": _csrf(ingelogde_client), "bestand": (io.BytesIO(data), "Club van 20.xlsx")},
        content_type="multipart/form-data",
    )
    tekst = voorbeeld.data.decode()
    assert voorbeeld.status_code == 200
    assert "1 bestaan al" in tekst and "1 zijn nieuw" in tekst
    # 2018-19 nieuw (Jantje), 2026-27 nieuw, 2025-26 ongewijzigd, Pietje 2018-19 nieuw.
    assert "3 nieuw" in tekst and "0 gewijzigd" in tekst and "1 ongewijzigd" in tekst
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 1  # nog niets opgeslagen

    csv_tekst = rijen_naar_csv(rijen_uit_xlsx(data))
    resp = ingelogde_client.post(
        "/club-van-20/importeren", data={"csrf_token": _csrf(ingelogde_client), "tekst": csv_tekst, "bevestig": "1"}
    )
    assert resp.status_code == 302

    jantje = db.execute("SELECT * FROM club_van_20_leden WHERE naam = 'Jantje'").fetchone()
    assert jantje["team"] == "O23"  # niet teruggezet naar Za1
    assert jantje["voornaam"] == "Jan" and jantje["achternaam"] == "Jansen"  # lege velden wel aangevuld
    behouden = db.execute(
        "SELECT * FROM club_van_20_bijdragen WHERE lid_id = ? AND seizoen = '2025-2026'", (lid,)
    ).fetchone()
    assert behouden["betaalwijze"] == "contant" and behouden["notitie"] == "bij de bar"
    seizoenen = {
        r["seizoen"] for r in db.execute("SELECT seizoen FROM club_van_20_bijdragen WHERE lid_id = ?", (lid,))
    }
    assert seizoenen == {"2018-2019", "2025-2026", "2026-2027"}
    assert db.execute("SELECT team FROM club_van_20_leden WHERE naam = 'Pietje'").fetchone()["team"] == "Za2"


def test_import_toont_welke_bestaande_betalingen_wijzigen(ingelogde_client, db):
    lid = _lid(db, "Jantje")
    _bijdrage(db, lid, "2025-2026", bedrag=10)
    data = _maak_xlsx([("Ledenlijst", [KOP, ["Jan", "Jansen", "", "Jantje", "", 20, "", ""]], False)])
    tekst = ingelogde_client.post(
        "/club-van-20/importeren",
        data={"csrf_token": _csrf(ingelogde_client), "bestand": (io.BytesIO(data), "x.xlsx")},
        content_type="multipart/form-data",
    ).data.decode()
    assert "1 gewijzigd" in tekst and "Jantje 2025-2026: betaald €10 → betaald €20" in tekst


def test_import_met_kapot_excelbestand_geeft_melding(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/club-van-20/importeren",
        data={"csrf_token": _csrf(ingelogde_client), "bestand": (io.BytesIO(b"geen excel"), "kapot.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200 and b"geldig Excel" in resp.data


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
    # "Betaald" in de statuskolom maar expliciet 0 in de bedragkolom: verlengd, met bedrag 0
    # (het geld stond al in een eerder seizoen).
    assert rijen["Mv. Subaeswaren"]["bijdragen"]["2026-2027"] == {
        "status": "betaald", "bedrag": 0, "nul_betaald": True
    }
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


def test_publieke_pagina_heeft_geen_streepjes_als_leesteken(client, db):
    import html
    import re

    def zichtbare_tekst():
        pagina = client.get("/club-van-20/doe-mee").data.decode()
        pagina = re.sub(r"<style.*?</style>", "", pagina, flags=re.S)
        pagina = re.sub(r"<script.*?</script>", "", pagina, flags=re.S)
        return html.unescape(re.sub(r"<[^>]+>", " ", pagina))

    # Er moet een naam op de pagina staan, anders ontbreekt de seizoenskop.
    lid_id = _lid(db, "Test")
    _bijdrage(db, lid_id, HUIDIG)
    tekst = zichtbare_tekst()
    assert "\u2014" not in tekst and "\u2013" not in tekst and " - " not in tekst
    # Het seizoen staat als 2026/2027; de clubnaam houdt zijn streepje.
    assert f"seizoen {HUIDIG.replace('-', '/')}" in tekst and f"seizoen {HUIDIG}" not in tekst


# ---------- Extra groot bordje ----------


def test_extra_groot_vinkje_wordt_opgeslagen_en_weer_uitgezet(ingelogde_client, db):
    basis = {"csrf_token": _csrf(ingelogde_client), "naam": "Ten Boer On Tour", "status_seizoen": "betaald"}
    ingelogde_client.post("/club-van-20/leden/nieuw", data={**basis, "extra_groot": "on"})
    lid = db.execute("SELECT * FROM club_van_20_leden WHERE naam = 'Ten Boer On Tour'").fetchone()
    assert lid["extra_groot"] == 1
    assert "checked" in ingelogde_client.get(f"/club-van-20/leden/{lid['id']}").data.decode().split('name="extra_groot"')[1][:80]

    ingelogde_client.post(f"/club-van-20/leden/{lid['id']}", data=basis)  # vinkje niet meegestuurd = uit
    assert db.execute("SELECT extra_groot FROM club_van_20_leden WHERE id = ?", (lid["id"],)).fetchone()[0] == 0


def test_extra_groot_bordje_is_breed_op_het_scherm(client, db):
    _alleen_club_van_20(db)
    _zet(db, club_van_20_kolommen=4, club_van_20_namen_per_slide=8)
    _bijdrage(db, _lid(db, "Gewoon Lid"), HUIDIG)
    _bijdrage(db, _lid(db, "Ten Boer On Tour", extra_groot=1), HUIDIG)

    tekst = client.get("/kiosk/scherm").data.decode()
    assert tekst.count("c20-bordje--groot") == 1
    groot = tekst[tekst.index("c20-bordje--groot") :][:400]
    assert "Ten Boer On Tour" in groot and "Gewoon Lid" not in groot
    # Een gat naast een breed bordje wordt opgevuld door het volgende bordje.
    assert "grid-auto-flow: row dense" in open("static/kiosk_scherm_stijl.css").read()


def test_extra_groot_met_een_kolom_wordt_niet_breed(client, db):
    _alleen_club_van_20(db)
    _zet(db, club_van_20_kolommen=1, club_van_20_namen_per_slide=4)
    _bijdrage(db, _lid(db, "Ten Boer On Tour", extra_groot=1), HUIDIG)
    assert "c20-bordje--groot" not in client.get("/kiosk/scherm").data.decode()


def test_raster_rijen_plaatst_zoals_css_grid_dense():
    from club_van_20 import raster_rijen

    assert raster_rijen([], 4) == 0
    assert raster_rijen([1] * 8, 4) == 2
    assert raster_rijen([2, 2, 2], 3) == 3  # elk breed bordje houdt een rij voor zich
    assert raster_rijen([1, 1, 1, 2], 4) == 2  # past niet op rij 1 (nog 1 kolom vrij)
    assert raster_rijen([1, 1, 2, 1], 3) == 2  # het gat op rij 1 wordt door het laatste bordje gevuld
    assert raster_rijen([2, 1, 1, 2, 1, 1, 2], 4) == 3
    assert raster_rijen([2], 1) == 1  # nooit breder dan het raster


def test_extra_groot_telt_dubbel_voor_het_aantal_namen_per_dia(client, db):
    from club_van_20 import verdeel_over_dias

    leden = [{"naam": "A", "extra_groot": True}] + [{"naam": n, "extra_groot": False} for n in "BCDE"]
    assert [[l["naam"] for l in g] for g in verdeel_over_dias(leden, 4, 4)] == [["A", "B", "C"], ["D", "E"]]
    # Zonder extra groot: gewoon 4 per dia.
    gewoon = [{"naam": n, "extra_groot": False} for n in "ABCDE"]
    assert [len(g) for g in verdeel_over_dias(gewoon, 4, 4)] == [4, 1]

    _alleen_club_van_20(db)
    _zet(db, club_van_20_kolommen=4, club_van_20_namen_per_slide=8, club_van_20_lege_vakjes=0)
    for i in range(7):
        _bijdrage(db, _lid(db, f"Lid {i}", extra_groot=1 if i < 3 else 0), HUIDIG)
    tekst = client.get("/kiosk/scherm").data.decode()
    # 3 brede (6 vakjes) + 5 gewone = 11 vakjes: 2 dia's, elk met precies 2 rijen
    # of meer, nooit minder rijen dan het echte raster nodig heeft.
    assert tekst.count("c20-bordje--groot") == 3
    assert "1/2" in tekst and "2/2" in tekst
