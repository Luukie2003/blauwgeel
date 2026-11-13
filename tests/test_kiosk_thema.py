"""Het Halloween-thema op de kantine-tv (1.74.0): met één klik aan of uit op de Kiosk-hub of in de handterminal-app, en
de schermen nemen het over omdat het in hun versie meetelt."""

from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, app_client  # noqa: F401 (fixture)


def _zet(client, thema):
    return client.post("/kiosk/thema", data={"csrf_token": _csrf(client), "thema": thema})


def _thema(db):
    return db.execute("SELECT thema FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()[0]


def test_halloween_met_een_klik_aan_en_uit(ingelogde_client, client, db):
    versie_prijzen = client.get("/kiosk/prijzen/versie").get_json()["versie"]
    versie_dias = client.get("/kiosk/scherm/versie").get_json()["versie"]
    assert "hw-vleermuis" not in client.get("/kiosk/prijzen").get_data(as_text=True)

    assert _zet(ingelogde_client, "halloween").status_code == 302
    assert _thema(db) == "halloween"
    prijzen = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert "hw-vleermuis" in prijzen and "hw--prijzen" in prijzen
    assert "hw--dias" in client.get("/kiosk/scherm").get_data(as_text=True)
    # De schermen vragen elke 10 seconden hun versie: die is anders, dus ze laden het thema vanzelf.
    assert client.get("/kiosk/prijzen/versie").get_json()["versie"] != versie_prijzen
    assert client.get("/kiosk/scherm/versie").get_json()["versie"] != versie_dias
    hub = ingelogde_client.get("/kiosk").get_data(as_text=True)
    assert 'aria-label="Halloween-thema uitzetten"' in hub

    _zet(ingelogde_client, "")
    assert _thema(db) is None
    assert "hw-vleermuis" not in client.get("/kiosk/prijzen").get_data(as_text=True)
    assert client.get("/kiosk/prijzen/versie").get_json()["versie"] == versie_prijzen
    assert 'aria-label="Halloween-thema aanzetten"' in ingelogde_client.get("/kiosk").get_data(as_text=True)


def test_alleen_met_rechten_voor_de_kantine_tv(client, db):
    assert client.post("/kiosk/thema", data={"csrf_token": _csrf(client), "thema": "halloween"}).status_code == 302
    assert _thema(db) is None  # niet ingelogd: naar het inlogscherm, en het thema blijft uit


def test_halloween_in_de_app(app_client, db):  # noqa: F811
    overzicht = app_client.get("/api/app/kantine-tv").get_json()
    assert overzicht["thema"] is None and overzicht["themas"][0] == {"sleutel": "halloween", "naam": "Halloween"}
    aan = _post(app_client, "/api/app/kantine-tv/thema", thema="halloween").get_json()
    assert aan["thema"] == "halloween" and "staat aan" in aan["melding"] and _thema(db) == "halloween"
    uit = _post(app_client, "/api/app/kantine-tv/thema", thema=None).get_json()
    assert uit["thema"] is None and "Thema uit" in uit["melding"]
    # Een thema dat niet bestaat, zet het gewoon uit.
    assert _post(app_client, "/api/app/kantine-tv/thema", thema="onbekend").get_json()["thema"] is None


def test_kerst_en_een_thema_tegelijk(ingelogde_client, client, db):
    _zet(ingelogde_client, "halloween")
    _zet(ingelogde_client, "kerst")  # een ander thema zet het vorige uit
    assert _thema(db) == "kerst"
    dias = client.get("/kiosk/scherm").get_data(as_text=True)
    assert "ks ks--dias" in dias and "<div class=\"ks-boom\">" in dias and "hw-vleermuis" not in dias
    prijzen = client.get("/kiosk/prijzen").get_data(as_text=True)
    assert "ks ks--prijzen" in prijzen and "<div class=\"ks-boom\">" not in prijzen
    hub = ingelogde_client.get("/kiosk").get_data(as_text=True)
    assert 'aria-label="Kerst-thema uitzetten"' in hub and 'aria-label="Halloween-thema aanzetten"' in hub


def test_de_clubstijl_met_een_klik_aan_en_uit(ingelogde_client, client, db):
    versie_dias = client.get("/kiosk/scherm/versie").get_json()["versie"]
    versie_prijzen = client.get("/kiosk/prijzen/versie").get_json()["versie"]
    assert "kiosk_clubstijl.css" not in client.get("/kiosk/scherm").get_data(as_text=True)

    ingelogde_client.post("/kiosk/stijl", data={"csrf_token": _csrf(ingelogde_client), "stijl": "club"})
    assert db.execute("SELECT stijl FROM kiosk_scherm_instellingen").fetchone()[0] == "club"
    assert "kiosk_clubstijl.css" in client.get("/kiosk/scherm").get_data(as_text=True)
    assert "kiosk_clubstijl.css" in client.get("/kiosk/prijzen").get_data(as_text=True)
    assert client.get("/kiosk/scherm/versie").get_json()["versie"] != versie_dias
    assert client.get("/kiosk/prijzen/versie").get_json()["versie"] != versie_prijzen
    assert 'aria-label="Clubstijl uitzetten"' in ingelogde_client.get("/kiosk").get_data(as_text=True)

    ingelogde_client.post("/kiosk/stijl", data={"csrf_token": _csrf(ingelogde_client), "stijl": ""})
    assert db.execute("SELECT stijl FROM kiosk_scherm_instellingen").fetchone()[0] is None
    assert "kiosk_clubstijl.css" not in client.get("/kiosk/scherm").get_data(as_text=True)


def test_de_clubstijl_alleen_met_rechten(client, db):
    client.post("/kiosk/stijl", data={"csrf_token": _csrf(client), "stijl": "club"})
    assert db.execute("SELECT stijl FROM kiosk_scherm_instellingen").fetchone()[0] is None
