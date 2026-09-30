import time

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from club_van_20 import huidig_seizoen
from sponsoren import bouw_sponsor_dias


def _sponsor(db, naam, groep=None, logo=None, actief=1, volgorde=0, wit=1):
    db.execute(
        """INSERT INTO kiosk_sponsorlogos (naam, logo, groep, witte_achtergrond, actief, volgorde, aangemaakt_op)
           VALUES (?, ?, ?, ?, ?, ?, '2026-01-01 10:00')""",
        (naam, logo, groep, wit, actief, volgorde),
    )
    db.commit()
    return db.execute("SELECT id FROM kiosk_sponsorlogos WHERE naam = ?", (naam,)).fetchone()["id"]


def _zet(db, **velden):
    for veld, waarde in velden.items():
        db.execute(f"UPDATE kiosk_scherm_instellingen SET {veld} = ? WHERE id = 1", (waarde,))
    db.commit()


def _instellingen(db):
    return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()


def test_dias_per_sponsor_en_per_groep(db):
    _sponsor(db, "Escape Hunt", volgorde=1)
    _sponsor(db, "Gelkinge9", groep="Zaterdag 1", volgorde=2)
    _sponsor(db, "Robertus", volgorde=3)
    _sponsor(db, "Frietwinkel", groep="zaterdag 1", volgorde=4)
    _sponsor(db, "Staat Uit", actief=0)

    dias = bouw_sponsor_dias(db, _instellingen(db))

    assert [(d["titel"], [l["naam"] for l in d["logos"]]) for d in dias] == [
        (None, ["Escape Hunt"]),
        ("Zaterdag 1", ["Gelkinge9", "Frietwinkel"]),
        (None, ["Robertus"]),
    ]
    assert dias[0]["kop"] == "Mede mogelijk gemaakt door"


def test_grote_groep_wordt_over_meerdere_dias_verdeeld(db):
    _zet(db, sponsors_logos_per_dia=2)
    for i in range(5):
        _sponsor(db, f"Sponsor {i}", groep="Zaterdag 2", volgorde=i)
    dias = bouw_sponsor_dias(db, _instellingen(db))
    assert [len(d["logos"]) for d in dias] == [2, 2, 1]


def test_kantine_scherm_zet_sponsoren_tussen_de_dias(client, db):
    _sponsor(db, "Escape Hunt", logo="escape.png")
    _zet(db, sponsors_elke_dias=3)

    tekst = client.get("/kiosk/scherm").data.decode()
    assert '<section class="slide slide-sponsorlogos c20' in tekst
    assert "Mede mogelijk gemaakt door" in tekst
    assert "kiosk_afbeeldingen/escape.png" in tekst
    assert "var sponsorsElke = Math.max(1, 3);" in tekst

    _zet(db, sponsors_toon_dias=0)
    assert '<section class="slide slide-sponsorlogos' not in client.get("/kiosk/scherm").data.decode()


def test_prijzenlijst_toont_sponsoren_als_overlay(client, db):
    versie_voor = client.get("/kiosk/prijzen/versie").get_json()["versie"]
    assert 'id="sponsor-overlay"' not in client.get("/kiosk/prijzen").data.decode()

    _sponsor(db, "Robertus", logo="robertus.png")
    _zet(db, sponsors_prijzen_interval=45, sponsors_prijzen_duur=6)

    tekst = client.get("/kiosk/prijzen").data.decode()
    assert 'id="sponsor-overlay"' in tekst
    assert "kiosk_afbeeldingen/robertus.png" in tekst
    assert "setInterval(toonSponsor, 45 * 1000)" in tekst
    assert "var duurMs = 6 * 1000;" in tekst
    # Een nieuwe sponsor moet het prijzenscherm laten herladen.
    assert client.get("/kiosk/prijzen/versie").get_json()["versie"] != versie_voor

    _zet(db, sponsors_toon_prijzen=0)
    assert 'id="sponsor-overlay"' not in client.get("/kiosk/prijzen").data.decode()


def test_wisselscherm_prijzenstand_toont_ook_sponsoren(client, db):
    _sponsor(db, "Robertus")
    _zet(db, actief_tv_scherm="prijzen")
    versie = client.get("/kiosk/tv/versie").get_json()["versie"]
    assert 'id="sponsor-overlay"' in client.get("/kiosk/tv").data.decode()
    _sponsor(db, "Tweede Sponsor")
    assert client.get("/kiosk/tv/versie").get_json()["versie"] != versie


def test_beheer_toevoegen_bewerken_aanuit_verwijderen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsorlogos",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "VisitAmerika", "groep": "Zaterdag 2", "witte_achtergrond": "on"},
    )
    assert resp.status_code == 302
    sponsor = db.execute("SELECT * FROM kiosk_sponsorlogos WHERE naam = 'VisitAmerika'").fetchone()
    assert sponsor["groep"] == "Zaterdag 2" and sponsor["witte_achtergrond"] == 1 and sponsor["actief"] == 1

    pagina = ingelogde_client.get("/kiosk/sponsorlogos").data.decode()
    assert "VisitAmerika" in pagina and "Zo ziet het eruit" in pagina and "slide-sponsorlogos" in pagina

    resp = ingelogde_client.post(
        f"/kiosk/sponsorlogos/{sponsor['id']}/actief",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.get_json()["actief"] is False

    ingelogde_client.post(
        f"/kiosk/sponsorlogos/{sponsor['id']}",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Visit Amerika", "groep": "", "volgorde": "7", "actief": "on"},
    )
    sponsor = db.execute("SELECT * FROM kiosk_sponsorlogos WHERE id = ?", (sponsor["id"],)).fetchone()
    assert (sponsor["naam"], sponsor["groep"], sponsor["volgorde"], sponsor["actief"], sponsor["witte_achtergrond"]) == (
        "Visit Amerika", None, 7, 1, 0
    )
    assert ingelogde_client.get(f"/kiosk/sponsorlogos/{sponsor['id']}").status_code == 200

    ingelogde_client.post(f"/kiosk/sponsorlogos/{sponsor['id']}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_sponsorlogos").fetchone()["n"] == 0


def test_instellingen_opslaan(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsorlogos/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "sponsors_toon_dias": "on",
            "sponsors_elke_dias": "4",
            "sponsors_duur_seconden": "10",
            "sponsors_prijzen_interval": "5",
            "sponsors_prijzen_duur": "7",
            "sponsors_kop": "Dankzij",
            "sponsors_logos_per_dia": "9",
        },
    )
    assert resp.status_code == 302
    i = _instellingen(db)
    assert (i["sponsors_toon_dias"], i["sponsors_elke_dias"], i["sponsors_duur_seconden"]) == (1, 4, 10)
    # Prijzenlijst bewust uitgevinkt; interval heeft een ondergrens van 10s, max 6 logo's per dia.
    assert (i["sponsors_toon_prijzen"], i["sponsors_prijzen_interval"], i["sponsors_prijzen_duur"]) == (0, 10, 7)
    assert i["sponsors_kop"] == "Dankzij" and i["sponsors_logos_per_dia"] == 6


def test_beheer_vereist_kantine_tv_sectie(client, db):
    _maak_vrijwilliger(db, "zonder_tv", "voorraad")
    _login(client, "zonder_tv")
    assert client.get("/kiosk/sponsorlogos").status_code == 302
    client.get("/logout")
    _maak_vrijwilliger(db, "met_tv", "kantine_tv")
    _login(client, "met_tv")
    assert client.get("/kiosk/sponsorlogos").status_code == 200


# ---------- Aftelklok op de wervingsdia ----------


def test_wervingsdia_toont_aftelklok_zonder_telkens_te_herladen(client, db):
    db.execute(
        "INSERT INTO club_van_20_leden (naam, status, aangemaakt_op) VALUES ('Lid', 'actief', '2026-01-01 10:00')"
    )
    db.execute(
        "INSERT INTO club_van_20_bijdragen (lid_id, seizoen, status, bedrag) VALUES (1, ?, 'betaald', 20)",
        (huidig_seizoen(),),
    )
    _zet(
        db,
        toon_sponsoren=0, toon_wedstrijden=0, toon_standen=0, toon_motm=0,
        club_van_20_aankondiging_tekst="Vanaf maandag kun jij verlengen!",
        club_van_20_aankondiging_aftellen_tot="2099-10-05T00:00",
    )

    tekst = client.get("/kiosk/scherm").data.decode()
    werving = tekst[tekst.index("slide-club_van_20_werving") :]
    assert "Vanaf maandag kun jij verlengen!" in werving and "data-aftel-doel=" in werving

    # De versie mag niet elke seconde veranderen (dan zou het scherm steeds herladen).
    v1 = client.get("/kiosk/scherm/versie").get_json()["versie"]
    time.sleep(1.1)
    assert client.get("/kiosk/scherm/versie").get_json()["versie"] == v1

    _zet(db, club_van_20_aankondiging_op_dia=0)
    assert "data-aftel-doel=" not in client.get("/kiosk/scherm").data.decode()
