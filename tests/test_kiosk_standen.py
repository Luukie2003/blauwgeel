"""Tests voor de standen-dia's op het kantine scherm (ZA 2/ZA 3/O23) -- zie
kiosk_stand_teams in schema.sql, STAND_POULES in routes/kiosk.py en de
sleeplijst op kiosk_sponsoren_leden.html. Geen live koppeling met
voetbal.nl: de volgorde wordt handmatig gesleept en hier dus ook
handmatig als rijen ingevoerd."""
import io
import json

from conftest import stel_csrf_token_in as _csrf
from helpers import CLUB_LOGO_MAP, club_van_team_naam
from test_kiosk import _KLEINE_PNG


def _voeg_team_toe(db, poule, naam, eigen_team=0, volgorde=None, club=None, gewonnen=0, gelijk=0, verloren=0):
    if volgorde is None:
        volgorde = db.execute(
            "SELECT COALESCE(MAX(volgorde), -1) + 1 AS v FROM kiosk_stand_teams WHERE poule = ?", (poule,)
        ).fetchone()["v"]
    cur = db.execute(
        """INSERT INTO kiosk_stand_teams (poule, naam, eigen_team, volgorde, club, gewonnen, gelijk, verloren)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (poule, naam, eigen_team, volgorde, club or club_van_team_naam(naam), gewonnen, gelijk, verloren),
    )
    db.commit()
    return cur.lastrowid


def test_zonder_teams_geen_stand_dia(client, db):
    resp = client.get("/kiosk/scherm")
    assert resp.status_code == 200
    # "slide-stand" zit ook in de <style>-block (CSS-selector) ongeacht of er
    # een dia is -- check daarom op de zichtbare titel, niet de klassenaam.
    assert b"Stand ZA" not in resp.data


def test_stand_dia_toont_teams_op_volgorde_met_eigen_team_gemarkeerd(client, db):
    _voeg_team_toe(db, "za2", "Concurrent A")
    eigen_id = _voeg_team_toe(db, "za2", "Eigen Team", eigen_team=1)
    _voeg_team_toe(db, "za2", "Concurrent B")

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()

    assert "Stand ZA 2" in tekst
    # Op volgorde: Concurrent A (1e), Eigen Team (2e), Concurrent B (3e).
    positie_a = tekst.find("Concurrent A")
    positie_eigen = tekst.find("Eigen Team")
    positie_b = tekst.find("Concurrent B")
    assert positie_a < positie_eigen < positie_b
    assert "standdia-rij--eigen" in tekst
    assert eigen_id  # sanity: rij is echt aangemaakt


def test_andere_poule_zonder_teams_slaat_die_dia_over(client, db):
    _voeg_team_toe(db, "za2", "Concurrent A")

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()

    assert "Stand ZA 2" in tekst
    assert "Stand ZA 3" not in tekst
    assert "Stand O23" not in tekst


def test_team_toevoegen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/standen/team-nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "poule": "za3", "naam": "Nieuwe Tegenstander"},
    )
    assert resp.status_code == 302

    rij = db.execute(
        "SELECT * FROM kiosk_stand_teams WHERE poule = 'za3' AND naam = 'Nieuwe Tegenstander'"
    ).fetchone()
    assert rij is not None
    assert rij["eigen_team"] == 0


def test_team_toevoegen_onbekende_poule_geeft_fout(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/standen/team-nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "poule": "za99", "naam": "Iets"},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.get_json()["ok"] is False
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_stand_teams").fetchone()["n"] == 0


def test_team_verwijderen(ingelogde_client, db):
    team_id = _voeg_team_toe(db, "o23", "Weg ermee")
    resp = ingelogde_client.post(
        f"/kiosk/scherm/standen/team/{team_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM kiosk_stand_teams WHERE id = ?", (team_id,)).fetchone() is None


def test_eigen_team_wisselen_is_uniek_per_poule(ingelogde_client, db):
    team_a = _voeg_team_toe(db, "za2", "Team A", eigen_team=1)
    team_b = _voeg_team_toe(db, "za2", "Team B")

    resp = ingelogde_client.post(
        f"/kiosk/scherm/standen/team/{team_b}/eigen-team",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    rij_a = db.execute("SELECT eigen_team FROM kiosk_stand_teams WHERE id = ?", (team_a,)).fetchone()
    rij_b = db.execute("SELECT eigen_team FROM kiosk_stand_teams WHERE id = ?", (team_b,)).fetchone()
    assert rij_a["eigen_team"] == 0
    assert rij_b["eigen_team"] == 1


def test_eigen_team_nogmaals_wisselen_zet_uit(ingelogde_client, db):
    team_id = _voeg_team_toe(db, "za2", "Team A", eigen_team=1)
    ingelogde_client.post(
        f"/kiosk/scherm/standen/team/{team_id}/eigen-team",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    rij = db.execute("SELECT eigen_team FROM kiosk_stand_teams WHERE id = ?", (team_id,)).fetchone()
    assert rij["eigen_team"] == 0


def test_volgorde_opslaan_herschikt_de_poule(ingelogde_client, db):
    a = _voeg_team_toe(db, "za3", "A")
    b = _voeg_team_toe(db, "za3", "B")
    c = _voeg_team_toe(db, "za3", "C")

    resp = ingelogde_client.post(
        "/kiosk/scherm/standen/za3/volgorde",
        data={"csrf_token": _csrf(ingelogde_client), "volgorde": json.dumps([c, a, b])},
    )
    assert resp.status_code == 302

    volgorde = [
        r["naam"]
        for r in db.execute(
            "SELECT naam FROM kiosk_stand_teams WHERE poule = 'za3' ORDER BY volgorde"
        ).fetchall()
    ]
    assert volgorde == ["C", "A", "B"]


def test_volgorde_opslaan_raakt_andere_poule_niet(ingelogde_client, db):
    """De UPDATE filtert ook op poule (naast id) -- een team-id dat toevallig
    ook in een andere poule bestaat mag daar niet per ongeluk meeveranderen."""
    za2_team = _voeg_team_toe(db, "za2", "ZA2 team")
    za3_a = _voeg_team_toe(db, "za3", "A")
    za3_b = _voeg_team_toe(db, "za3", "B")

    ingelogde_client.post(
        "/kiosk/scherm/standen/za3/volgorde",
        data={"csrf_token": _csrf(ingelogde_client), "volgorde": json.dumps([za3_b, za3_a])},
    )

    za2_volgorde_voor = db.execute(
        "SELECT volgorde FROM kiosk_stand_teams WHERE id = ?", (za2_team,)
    ).fetchone()["volgorde"]
    assert za2_volgorde_voor == 0


def test_scherm_instellingen_slaat_standen_velden_op(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "standen_volgorde": "5",
            "standen_duur_seconden": "15",
        },
    )
    assert resp.status_code == 302

    instellingen = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    # toon_standen bewust niet meegestuurd -> uit
    assert instellingen["toon_standen"] == 0
    assert instellingen["standen_volgorde"] == 5
    assert instellingen["standen_duur_seconden"] == 15


def test_standen_duur_is_instelbaar_op_de_dia(client, ingelogde_client, db):
    _voeg_team_toe(db, "za2", "Concurrent A")
    ingelogde_client.post(
        "/kiosk/scherm/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "toon_standen": "on",
            "standen_volgorde": "4",
            "standen_duur_seconden": "18",
        },
    )

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()
    # 'class="slide slide-stand' i.p.v. kaal "slide-stand" -- dat laatste
    # matcht ook de CSS-selector in de <style>-block, die altijd aanwezig is.
    idx = tekst.find('class="slide slide-stand')
    assert idx != -1
    stukje = tekst[idx : idx + 200]
    assert 'data-duur="18"' in stukje


# ---------- club_van_team_naam ----------


def test_club_van_team_naam_strip_teamvolgnummer():
    assert club_van_team_naam("Oranje Nassau 5") == "Oranje Nassau"
    assert club_van_team_naam("Oranje Nassau 6") == "Oranje Nassau"
    assert club_van_team_naam("HFC '15 6") == "HFC '15"


def test_club_van_team_naam_laat_jaartal_in_clubnaam_intact():
    """Een jaartal dat bij de clubnaam zelf hoort (bijv. "Velocitas 1897")
    mag niet verward worden met een team-volgnummer -- alleen het
    ALLERLAATSTE woord wordt gestript."""
    assert club_van_team_naam("Velocitas 1897 7") == "Velocitas 1897"
    assert club_van_team_naam("Be Quick 1887 3") == "Be Quick 1887"
    assert club_van_team_naam("LSC 1890 O23-1") == "LSC 1890"


def test_club_van_team_naam_zonder_volgnummer_blijft_gelijk():
    assert club_van_team_naam("Marum") == "Marum"


# ---------- club/logo-register ----------


def test_team_toevoegen_leidt_club_af(ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/scherm/standen/team-nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "poule": "za2", "naam": "Oranje Nassau 5"},
    )
    rij = db.execute(
        "SELECT club FROM kiosk_stand_teams WHERE naam = 'Oranje Nassau 5'"
    ).fetchone()
    assert rij["club"] == "Oranje Nassau"


def test_team_toevoegen_met_logo_registreert_die_voor_de_club(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/standen/team-nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "poule": "za2",
            "naam": "Oranje Nassau 5",
            "logo": (io.BytesIO(_KLEINE_PNG), "logo.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302

    logo = db.execute(
        "SELECT afbeelding FROM kiosk_club_logos WHERE club = 'Oranje Nassau'"
    ).fetchone()
    assert logo is not None
    assert logo["afbeelding"].endswith(".png")
    (CLUB_LOGO_MAP / logo["afbeelding"]).unlink()


def test_tweede_team_van_zelfde_club_hergebruikt_geregistreerd_logo(ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/scherm/standen/team-nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "poule": "za2",
            "naam": "Oranje Nassau 5",
            "logo": (io.BytesIO(_KLEINE_PNG), "logo.png"),
        },
        content_type="multipart/form-data",
    )
    # 2e team van dezelfde club, GEEN nieuwe logo-upload deze keer.
    ingelogde_client.post(
        "/kiosk/scherm/standen/team-nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "poule": "za2", "naam": "Oranje Nassau 6"},
    )

    rijen = db.execute(
        "SELECT naam, club FROM kiosk_stand_teams ORDER BY naam"
    ).fetchall()
    assert {r["naam"]: r["club"] for r in rijen} == {
        "Oranje Nassau 5": "Oranje Nassau",
        "Oranje Nassau 6": "Oranje Nassau",
    }
    # Nog steeds maar 1 rij in het register (niet overschreven/gedupliceerd).
    logo = db.execute("SELECT afbeelding FROM kiosk_club_logos").fetchone()
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_club_logos").fetchone()["n"] == 1
    (CLUB_LOGO_MAP / logo["afbeelding"]).unlink()


def test_club_logo_opslaan_werkt_ook_los_van_team_toevoegen(ingelogde_client, db):
    _voeg_team_toe(db, "za3", "Helpman 4")
    resp = ingelogde_client.post(
        "/kiosk/scherm/standen/club-logo",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "club": "Helpman",
            "logo": (io.BytesIO(_KLEINE_PNG), "helpman.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    logo = db.execute("SELECT afbeelding FROM kiosk_club_logos WHERE club = 'Helpman'").fetchone()
    assert logo is not None
    (CLUB_LOGO_MAP / logo["afbeelding"]).unlink()


def test_club_logo_opslaan_zonder_bestand_geeft_fout(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/standen/club-logo",
        data={"csrf_token": _csrf(ingelogde_client), "club": "Helpman"},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.get_json()["ok"] is False


def test_stand_dia_toont_logo_als_geregistreerd(client, ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/scherm/standen/team-nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "poule": "za2",
            "naam": "Oranje Nassau 5",
            "logo": (io.BytesIO(_KLEINE_PNG), "logo.png"),
        },
        content_type="multipart/form-data",
    )
    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()
    assert 'class="standdia-logo"' in tekst
    assert "/static/club_logos/" in tekst

    logo = db.execute("SELECT afbeelding FROM kiosk_club_logos WHERE club = 'Oranje Nassau'").fetchone()
    (CLUB_LOGO_MAP / logo["afbeelding"]).unlink()


def test_stand_dia_zonder_logo_toont_geen_logo_img(client, db):
    _voeg_team_toe(db, "za2", "Onbekende Club")
    resp = client.get("/kiosk/scherm")
    assert b'class="standdia-logo"' not in resp.data


# ---------- W/GL/V + afgeleide Gespeeld/Punten ----------


def test_volgorde_opslaan_slaat_ook_w_gl_v_op(ingelogde_client, db):
    team_id = _voeg_team_toe(db, "za2", "Test Club")
    resp = ingelogde_client.post(
        "/kiosk/scherm/standen/za2/volgorde",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "volgorde": json.dumps([team_id]),
            "statistieken": json.dumps({str(team_id): {"w": 4, "gl": 1, "v": 2}}),
        },
    )
    assert resp.status_code == 302
    rij = db.execute(
        "SELECT gewonnen, gelijk, verloren FROM kiosk_stand_teams WHERE id = ?", (team_id,)
    ).fetchone()
    assert (rij["gewonnen"], rij["gelijk"], rij["verloren"]) == (4, 1, 2)


def test_volgorde_opslaan_negatieve_statistiek_wordt_naar_0_geklemd(ingelogde_client, db):
    team_id = _voeg_team_toe(db, "za2", "Test Club")
    ingelogde_client.post(
        "/kiosk/scherm/standen/za2/volgorde",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "volgorde": json.dumps([team_id]),
            "statistieken": json.dumps({str(team_id): {"w": -3, "gl": "onzin", "v": 2}}),
        },
    )
    rij = db.execute(
        "SELECT gewonnen, gelijk, verloren FROM kiosk_stand_teams WHERE id = ?", (team_id,)
    ).fetchone()
    assert (rij["gewonnen"], rij["gelijk"], rij["verloren"]) == (0, 0, 2)


def test_stand_dia_toont_afgeleide_gespeeld_en_punten(client, db):
    """Gespeeld en Punten staan nergens los opgeslagen -- G = W+GL+V en
    P = 3*W + GL (hetzelfde 3-1-0-systeem als voetbal.nl), berekend in
    _stand_team_weergave (routes/kiosk.py)."""
    _voeg_team_toe(db, "za2", "Test Club", gewonnen=4, gelijk=1, verloren=2)

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()

    assert "W 4" in tekst and "GL 1" in tekst and "V 2" in tekst
    # 3*4 + 1 = 13 punten.
    assert ">13<" in tekst
