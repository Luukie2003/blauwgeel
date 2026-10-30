"""De kantine-tv vanaf de handterminal (routes/app_api_tv.py): tv's, specials, bardienst en dia's."""

from datetime import timedelta

from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_app_api_meer import _vrijwilliger
from test_kiosk_tvs import TOKEN, _code, _gekoppeld, _rij, _versie

from helpers import vandaag_amsterdam


def test_overzicht(app_client):  # noqa: F811
    data = app_client.get("/api/app/kantine-tv").get_json()
    assert data["tvs"] == [] and data["wissel"] in ("prijzen", "dias")
    assert {s["sleutel"] for s in data["schermen"]} == {"prijzen", "dias", "wissel"}
    assert data["vandaag"] == vandaag_amsterdam().isoformat()
    assert "acties" in data and "uitgelicht" in data and data["uitverkocht"] == 0


def test_tv_wisselen_en_herladen(app, app_client, ingelogde_client, db):  # noqa: F811
    tv = _gekoppeld(app, ingelogde_client, scherm="prijzen")
    tv_id = _rij(db)["id"]
    oud = _versie(tv)
    data = app_client.get("/api/app/kantine-tv").get_json()
    assert data["tvs"][0]["naam"] == "Bar" and data["tvs"][0]["scherm"] == "prijzen"

    resp = _post(app_client, f"/api/app/kantine-tv/tvs/{tv_id}/scherm", scherm="dias")
    assert resp.status_code == 200 and "toont nu: dia's" in resp.get_json()["melding"]
    assert _rij(db)["scherm"] == "dias" and _rij(db)["naam"] == "Bar"
    assert _versie(tv) != oud
    assert _post(app_client, f"/api/app/kantine-tv/tvs/{tv_id}/scherm", scherm="onzin").status_code == 400

    teller = _rij(db)["herlaad_teller"]
    assert _post(app_client, f"/api/app/kantine-tv/tvs/{tv_id}/herladen").status_code == 200
    assert _rij(db)["herlaad_teller"] == teller + 1
    assert _post(app_client, "/api/app/kantine-tv/tvs/9999/herladen").status_code == 404


def test_wisselknop(app_client, db):  # noqa: F811
    assert _post(app_client, "/api/app/kantine-tv/wissel", toont="dias").get_json()["wissel"] == "dias"
    assert db.execute("SELECT actief_tv_scherm FROM kiosk_scherm_instellingen").fetchone()[0] == "dias"
    assert _post(app_client, "/api/app/kantine-tv/wissel", toont="prijzen").get_json()["wissel"] == "prijzen"


def test_actie_en_uitgelicht(app_client, db):  # noqa: F811
    pid = db.execute("SELECT id FROM producten WHERE actief = 1 ORDER BY id LIMIT 1").fetchone()[0]
    actie_id = db.execute(
        "INSERT INTO kiosk_acties (product_id, tekst, actief, aangemaakt_op) VALUES (?, 'Nu 2 voor 3', 0, '2026-10-20')",
        (pid,),
    ).lastrowid
    db.commit()
    data = _post(app_client, f"/api/app/kantine-tv/acties/{actie_id}", actief=True).get_json()
    assert data["acties"][0]["actief"] is True and "staat nu aan" in data["melding"]
    assert _post(app_client, "/api/app/kantine-tv/acties/9999", actief=True).status_code == 404

    data = _post(app_client, "/api/app/kantine-tv/uitgelicht", product_id=pid, titel="Luuk's special").get_json()
    assert data["uitgelicht"]["product_id"] == pid and data["uitgelicht"]["titel"] == "Luuk's special"
    # Zonder titel blijft de vorige titel staan.
    data = _post(app_client, "/api/app/kantine-tv/uitgelicht", product_id=pid).get_json()
    assert data["uitgelicht"]["titel"] == "Luuk's special"
    data = _post(app_client, "/api/app/kantine-tv/uitgelicht", product_id=None).get_json()
    assert data["uitgelicht"] is None and data["uitgelicht_titel"] == "Luuk's special"
    assert _post(app_client, "/api/app/kantine-tv/uitgelicht", product_id=999999).status_code == 400
    producten = app_client.get("/api/app/kantine-tv/producten").get_json()["producten"]
    assert any(p["id"] == pid for p in producten)


def test_bardienst_toevoegen_aanpassen_en_verwijderen(app_client, db):  # noqa: F811
    vandaag = vandaag_amsterdam()
    resp = _post(app_client, "/api/app/kantine-tv/bardiensten", datum=vandaag.isoformat(), start_tijd="14:00",
                 eind_tijd="18:00", namen="  Piet   en Klaas ", verzoek_id="bd-1")
    data = resp.get_json()
    assert resp.status_code == 200 and data["bardiensten"][0]["namen"] == "Piet en Klaas"
    # Nog een keer hetzelfde verzoek: niet dubbel.
    _post(app_client, "/api/app/kantine-tv/bardiensten", datum=vandaag.isoformat(), namen="Piet", verzoek_id="bd-1")
    assert db.execute("SELECT COUNT(*) FROM kiosk_bardiensten").fetchone()[0] == 1
    bd = data["bardiensten"][0]["id"]

    data = _post(app_client, f"/api/app/kantine-tv/bardiensten/{bd}", namen="Jan en Klaas").get_json()
    rij = db.execute("SELECT * FROM kiosk_bardiensten WHERE id = ?", (bd,)).fetchone()
    assert rij["namen"] == "Jan en Klaas" and rij["start_tijd"] == "14:00" and rij["eind_tijd"] == "18:00"
    assert _post(app_client, f"/api/app/kantine-tv/bardiensten/{bd}", namen=" ").status_code == 400
    assert _post(app_client, f"/api/app/kantine-tv/bardiensten/{bd}", eind_tijd="19:30").get_json()["bardiensten"][0]["eind_tijd"] == "19:30"

    over_een_week = (vandaag + timedelta(days=7)).isoformat()
    assert _post(app_client, "/api/app/kantine-tv/bardiensten", datum=over_een_week, namen="Piet").status_code == 400

    _post(app_client, f"/api/app/kantine-tv/bardiensten/{bd}/verwijderen")
    assert db.execute("SELECT COUNT(*) FROM kiosk_bardiensten").fetchone()[0] == 0


def test_dias_en_blokken(app_client, db):  # noqa: F811
    morgen = (vandaag_amsterdam() + timedelta(days=1)).isoformat()
    dia = db.execute(
        """INSERT INTO kiosk_sponsoren (sjabloon, titel, actief, zichtbaar_vanaf, aangemaakt_op)
           VALUES ('mededeling_groot', 'Feestavond', 1, ?, '2026-10-20')""", (morgen,)
    ).lastrowid
    db.commit()
    data = app_client.get("/api/app/kantine-tv/dias").get_json()
    rij = next(d for d in data["dias"] if d["id"] == dia)
    assert rij["periode"] == "later" and rij["soort"].startswith("Mededeling")
    assert {b["sleutel"] for b in data["blokken"]} >= {"toon_sponsoren", "toon_standen", "toon_motm"}

    data = _post(app_client, f"/api/app/kantine-tv/dias/{dia}", actief=False).get_json()
    assert db.execute("SELECT actief FROM kiosk_sponsoren WHERE id = ?", (dia,)).fetchone()[0] == 0
    assert "'Feestavond' staat nu uit" in data["melding"]
    sjabloon = db.execute(
        "INSERT INTO kiosk_sjablonen_custom (naam, aangemaakt_op) VALUES ('Wilner Vleeswaren', '2026-10-20')").lastrowid
    db.execute("""INSERT INTO kiosk_sponsoren (sjabloon, custom_sjabloon_id, actief, aangemaakt_op)
                  VALUES ('aangepast', ?, 1, '2026-10-20')""", (sjabloon,))
    db.commit()
    assert any(d["titel"] == "Wilner Vleeswaren" for d in app_client.get("/api/app/kantine-tv/dias").get_json()["dias"])

    data = _post(app_client, "/api/app/kantine-tv/dia-blokken/toon_standen", aan=False).get_json()
    assert db.execute("SELECT toon_standen FROM kiosk_scherm_instellingen").fetchone()[0] == 0
    assert next(b for b in data["blokken"] if b["sleutel"] == "toon_standen")["aan"] is False
    assert _post(app_client, "/api/app/kantine-tv/dia-blokken/actief_tv_scherm", aan=True).status_code == 404


def test_alleen_met_kantine_tv_rechten(app, db):
    client = _vrijwilliger(app, db, "barhulp", "voorraad")
    assert client.get("/api/app/kantine-tv").status_code == 403
    assert client.post("/api/app/kantine-tv/wissel", json={"toont": "dias"}, headers=client.kop).status_code == 403
    tv_client = _vrijwilliger(app, db, "tvhulp", "kantine_tv")
    assert tv_client.get("/api/app/kantine-tv").status_code == 200
    assert tv_client.get("/api/app/start").get_json()["toegang"]["kantine_tv"] is True


def test_token_van_de_tv_blijft_geheim(app, app_client, ingelogde_client, db):  # noqa: F811
    _gekoppeld(app, ingelogde_client)
    assert TOKEN not in app_client.get("/api/app/kantine-tv").get_data(as_text=True)


def test_koppelen_vanuit_de_app(app, app_client, db):  # noqa: F811
    tv = app.test_client()
    code = "".join(_code(tv))
    resp = _post(app_client, "/api/app/kantine-tv/tvs/koppelen", code=code, naam="Zaal", scherm="dias", verzoek_id="tv1")
    data = resp.get_json()
    assert resp.status_code == 200 and "is gekoppeld" in data["melding"]
    assert data["tvs"][0]["naam"] == "Zaal" and _rij(db)["scherm"] == "dias"
    # Dezelfde code nog een keer (bijvoorbeeld opnieuw verstuurd): niet dubbel.
    _post(app_client, "/api/app/kantine-tv/tvs/koppelen", code=code, naam="Zaal", scherm="dias", verzoek_id="tv1")
    assert db.execute("SELECT COUNT(*) FROM kiosk_tvs").fetchone()[0] == 1
    resp = _post(app_client, "/api/app/kantine-tv/tvs/koppelen", code="000000", naam="X", scherm="prijzen")
    assert resp.status_code == 400 and "staat niet" in resp.get_json()["melding"]


def test_qr_code_op_de_tv_en_het_koppel_adres(app, ingelogde_client):
    tv = app.test_client()
    pagina = tv.get(f"/kiosk/t/{TOKEN}").get_data(as_text=True)
    code = "".join(_code(tv))
    assert "<svg" in pagina and "handterminal-app" in pagina
    resp = ingelogde_client.get(f"/kiosk/koppel/{code}")
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/kiosk/tvs?code={code}")
    hub = ingelogde_client.get(f"/kiosk/tvs?code={code}").get_data(as_text=True)
    assert f'value="{code}"' in hub
    # Zonder inloggen: eerst naar de inlogpagina.
    assert "/login" in app.test_client().get(f"/kiosk/koppel/{code}").headers["Location"]
