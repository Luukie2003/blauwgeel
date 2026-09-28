"""Tests voor de Man of the Match-dia op het kantine scherm -- zie
kiosk_motm in schema.sql en de sleeplijst op kiosk_sponsoren_leden.html.
Geen live koppeling met voetbal.nl: de speler wordt handmatig elke week
ingevuld, leeg = geen MOTM die week voor dat team."""
import json

from conftest import stel_csrf_token_in as _csrf


def _voeg_team_toe(db, team, speler=None, volgorde=None):
    if volgorde is None:
        volgorde = db.execute(
            "SELECT COALESCE(MAX(volgorde), -1) + 1 AS v FROM kiosk_motm"
        ).fetchone()["v"]
    cur = db.execute(
        "INSERT INTO kiosk_motm (team, speler, volgorde) VALUES (?, ?, ?)",
        (team, speler, volgorde),
    )
    db.commit()
    return cur.lastrowid


def test_zonder_teams_geen_motm_dia(client, db):
    resp = client.get("/kiosk/scherm")
    assert resp.status_code == 200
    # "Man of the Match" en "slide-motm" zitten ook in de <style>-block
    # (CSS-comment/selector) ongeacht of er een dia is -- check daarom op de
    # daadwerkelijke dia-inhoud, niet de tekst/klassenaam op zich.
    assert b'class="motmdia-lijst"' not in resp.data


def test_team_zonder_speler_slaat_dia_over(client, db):
    _voeg_team_toe(db, "Eigen Team Alpha")

    resp = client.get("/kiosk/scherm")
    assert b'class="motmdia-lijst"' not in resp.data


def test_team_met_speler_toont_dia(client, db):
    _voeg_team_toe(db, "Eigen Team Alpha", speler="Jan Jansen")

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()
    assert 'class="motmdia-lijst"' in tekst
    assert "Eigen Team Alpha" in tekst
    assert "Jan Jansen" in tekst


def test_alleen_teams_met_speler_komen_op_de_dia(client, db):
    _voeg_team_toe(db, "Eigen Team Alpha", speler="Jan Jansen")
    _voeg_team_toe(db, "Eigen Team Beta")

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()
    assert "Jan Jansen" in tekst
    assert "Eigen Team Beta" not in tekst


def test_toon_motm_uit_slaat_dia_over_ondanks_ingevulde_speler(client, ingelogde_client, db):
    _voeg_team_toe(db, "Eigen Team Alpha", speler="Jan Jansen")
    ingelogde_client.post(
        "/kiosk/scherm/instellingen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )

    resp = client.get("/kiosk/scherm")
    assert b'class="motmdia-lijst"' not in resp.data


def test_team_toevoegen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/motm/team-nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "team": "ZA 1"},
    )
    assert resp.status_code in (302, 303)
    rij = db.execute("SELECT * FROM kiosk_motm WHERE team = 'ZA 1'").fetchone()
    assert rij is not None
    assert rij["speler"] is None


def test_team_toevoegen_zonder_naam_geeft_fout(ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/scherm/motm/team-nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "team": "   "},
    )
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_motm").fetchone()["n"] == 0


def test_team_verwijderen(ingelogde_client, db):
    team_id = _voeg_team_toe(db, "ZA 1")
    ingelogde_client.post(
        f"/kiosk/scherm/motm/team/{team_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert db.execute("SELECT * FROM kiosk_motm WHERE id = ?", (team_id,)).fetchone() is None


def test_volgorde_en_spelers_opslaan(ingelogde_client, db):
    id_a = _voeg_team_toe(db, "ZA 1")
    id_b = _voeg_team_toe(db, "ZA 2")

    ingelogde_client.post(
        "/kiosk/scherm/motm/volgorde",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "volgorde": json.dumps([id_b, id_a]),
            "spelers": json.dumps({id_a: "Jan Jansen", id_b: "  "}),
        },
    )

    rij_a = db.execute("SELECT * FROM kiosk_motm WHERE id = ?", (id_a,)).fetchone()
    rij_b = db.execute("SELECT * FROM kiosk_motm WHERE id = ?", (id_b,)).fetchone()
    assert rij_a["speler"] == "Jan Jansen"
    assert rij_b["volgorde"] == 0
    assert rij_a["volgorde"] == 1
    # Enkel spaties wordt leeggemaakt (None), niet letterlijk opgeslagen.
    assert rij_b["speler"] is None


def test_volgorde_opslaan_past_teamnaam_aan(ingelogde_client, db):
    team_id = _voeg_team_toe(db, "Oude Naam")
    ingelogde_client.post(
        "/kiosk/scherm/motm/volgorde",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "volgorde": json.dumps([team_id]),
            "teamnamen": json.dumps({team_id: "Nieuwe Naam"}),
        },
    )
    rij = db.execute("SELECT team FROM kiosk_motm WHERE id = ?", (team_id,)).fetchone()
    assert rij["team"] == "Nieuwe Naam"


def test_volgorde_opslaan_lege_teamnaam_wordt_genegeerd(ingelogde_client, db):
    team_id = _voeg_team_toe(db, "Blijft Gelijk")
    ingelogde_client.post(
        "/kiosk/scherm/motm/volgorde",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "volgorde": json.dumps([team_id]),
            "teamnamen": json.dumps({team_id: "   "}),
        },
    )
    rij = db.execute("SELECT team FROM kiosk_motm WHERE id = ?", (team_id,)).fetchone()
    assert rij["team"] == "Blijft Gelijk"


def test_meerdere_namen_komma_gescheiden_worden_samengevoegd_met_en(client, db):
    _voeg_team_toe(db, "Eigen Team Alpha", speler="Jan Jansen, Piet Pietersen")

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()
    assert "Jan Jansen &amp; Piet Pietersen" in tekst or "Jan Jansen & Piet Pietersen" in tekst


def test_drie_namen_komma_gescheiden_toont_komma_en_en(client, db):
    _voeg_team_toe(db, "Eigen Team Alpha", speler="Jan Jansen, Piet Pietersen, Klaas Klaassen")

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()
    assert "Jan Jansen, Piet Pietersen" in tekst
    assert "Klaassen" in tekst


def test_motm_instellingen_opslaan(ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/scherm/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "toon_motm": "1",
            "motm_volgorde": "7",
            "motm_duur_seconden": "15",
        },
    )
    instellingen = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert instellingen["toon_motm"] == 1
    assert instellingen["motm_volgorde"] == 7
    assert instellingen["motm_duur_seconden"] == 15
