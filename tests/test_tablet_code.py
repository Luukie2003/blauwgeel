"""Tests voor de verplichte 6-cijferige tablet-code (zie tablet_code_instellen
in routes/auth.py en de gate in vereis_login, app.py) -- bedoeld om straks
zonder gebruikersnaam aan te melden op de kiosk-tablet/tv-app.

Let op: de conftest.py-fixture vult tablet_code_hash standaard alvast in
(anders zou vrijwel elke andere test hier stuklopen) -- deze tests zetten 'm
voor hun eigen testgebruiker expliciet terug op NULL om het "nog niet
ingesteld"-scenario echt na te bootsen."""
from werkzeug.security import generate_password_hash

from database import WACHTWOORD_HASH_METHODE

from conftest import stel_csrf_token_in as _csrf


def _maak_gebruiker_zonder_code(db, naam="verse_gebruiker", wachtwoord="test1234"):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op) "
        "VALUES (?, ?, 'vrijwilliger', '2026-01-01 10:00')",
        (naam, generate_password_hash(wachtwoord, method=WACHTWOORD_HASH_METHODE)),
    )
    # De conftest-trigger vult tablet_code_hash meteen na de INSERT hierboven
    # (zie conftest.py) -- voor deze tests draait het nu net om het "nog geen
    # code"-scenario, dus die auto-vulling hier expliciet weer ongedaan maken.
    db.execute("UPDATE gebruikers SET tablet_code_hash = NULL WHERE naam = ?", (naam,))
    db.commit()
    return db.execute("SELECT id FROM gebruikers WHERE naam = ?", (naam,)).fetchone()["id"]


def _login(client, naam, wachtwoord="test1234"):
    csrf = _csrf(client)
    resp = client.post(
        "/login", data={"naam": naam, "wachtwoord": wachtwoord, "csrf_token": csrf}
    )
    assert resp.status_code == 302
    return resp


def test_zonder_code_wordt_elke_pagina_omgeleid_naar_instelpagina(client, db):
    _maak_gebruiker_zonder_code(db, "geen_code")
    _login(client, "geen_code")

    resp = client.get("/", follow_redirects=True)
    assert resp.request.path == "/tablet-code/instellen"
    assert b"Tablet-code" in resp.data


def test_uitloggen_blijft_bereikbaar_zonder_code(client, db):
    _maak_gebruiker_zonder_code(db, "geen_code_logout")
    _login(client, "geen_code_logout")

    resp = client.get("/logout", follow_redirects=True)
    assert resp.request.path == "/login"


def test_code_instellen_met_geldige_6_cijfers_werkt(client, db):
    gebruiker_id = _maak_gebruiker_zonder_code(db, "stelt_code_in")
    _login(client, "stelt_code_in")
    csrf = _csrf(client)

    resp = client.post(
        "/tablet-code/instellen",
        data={"code": "123456", "code_herhaald": "123456", "csrf_token": csrf},
    )
    assert resp.status_code == 302
    bijgewerkt = db.execute(
        "SELECT tablet_code_hash FROM gebruikers WHERE id = ?", (gebruiker_id,)
    ).fetchone()
    assert bijgewerkt["tablet_code_hash"] is not None

    # Nu niet meer omgeleid naar de instelpagina.
    resp = client.get("/", follow_redirects=True)
    assert resp.request.path == "/"


def test_code_moet_precies_6_cijfers_zijn(client, db):
    _maak_gebruiker_zonder_code(db, "korte_code")
    _login(client, "korte_code")
    csrf = _csrf(client)

    for ongeldig in ("12345", "1234567", "abcdef", "12 345"):
        resp = client.post(
            "/tablet-code/instellen",
            data={"code": ongeldig, "code_herhaald": ongeldig, "csrf_token": csrf},
            follow_redirects=True,
        )
        assert b"precies 6 cijfers" in resp.data
        csrf = _csrf(client)

    ongewijzigd = db.execute(
        "SELECT tablet_code_hash FROM gebruikers WHERE naam = 'korte_code'"
    ).fetchone()
    assert ongewijzigd["tablet_code_hash"] is None


def test_codes_moeten_overeenkomen(client, db):
    _maak_gebruiker_zonder_code(db, "typefout")
    _login(client, "typefout")
    csrf = _csrf(client)

    resp = client.post(
        "/tablet-code/instellen",
        data={"code": "111111", "code_herhaald": "222222", "csrf_token": csrf},
        follow_redirects=True,
    )
    assert b"komen niet overeen" in resp.data
    ongewijzigd = db.execute(
        "SELECT tablet_code_hash FROM gebruikers WHERE naam = 'typefout'"
    ).fetchone()
    assert ongewijzigd["tablet_code_hash"] is None


def test_code_moet_uniek_zijn_over_accounts_heen(client, db):
    _maak_gebruiker_zonder_code(db, "eerste_gebruiker")
    _login(client, "eerste_gebruiker")
    csrf = _csrf(client)
    resp = client.post(
        "/tablet-code/instellen",
        data={"code": "555555", "code_herhaald": "555555", "csrf_token": csrf},
    )
    assert resp.status_code == 302
    client.get("/logout")

    _maak_gebruiker_zonder_code(db, "tweede_gebruiker")
    _login(client, "tweede_gebruiker")
    csrf = _csrf(client)
    resp = client.post(
        "/tablet-code/instellen",
        data={"code": "555555", "code_herhaald": "555555", "csrf_token": csrf},
        follow_redirects=True,
    )
    assert b"al in gebruik" in resp.data
    ongewijzigd = db.execute(
        "SELECT tablet_code_hash FROM gebruikers WHERE naam = 'tweede_gebruiker'"
    ).fetchone()
    assert ongewijzigd["tablet_code_hash"] is None


def test_code_kan_later_gewijzigd_worden(ingelogde_client, db):
    """ingelogde_client (admin) heeft via de conftest-fixture al een code --
    dit is dus het 'vrijwillig wijzigen'-pad, niet de verplichte eerste keer."""
    admin = db.execute("SELECT id, tablet_code_hash FROM gebruikers WHERE naam = 'admin'").fetchone()
    oude_hash = admin["tablet_code_hash"]

    resp = ingelogde_client.get("/tablet-code/instellen")
    assert resp.status_code == 200
    assert b"nieuwe 6-cijferige code" in resp.data

    resp = ingelogde_client.post(
        "/tablet-code/instellen",
        data={"code": "246810", "code_herhaald": "246810", "csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    nieuw = db.execute("SELECT tablet_code_hash FROM gebruikers WHERE id = ?", (admin["id"],)).fetchone()
    assert nieuw["tablet_code_hash"] != oude_hash


def test_next_parameter_stuurt_terug_naar_bedoelde_pagina(client, db):
    _maak_gebruiker_zonder_code(db, "met_bestemming")
    _login(client, "met_bestemming")

    resp = client.get("/bijzonderheden", follow_redirects=True)
    assert resp.request.path == "/tablet-code/instellen"

    csrf = _csrf(client)
    resp = client.post(
        "/tablet-code/instellen",
        data={
            "code": "135791",
            "code_herhaald": "135791",
            "next": "/bijzonderheden",
            "csrf_token": csrf,
        },
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/bijzonderheden"


# ---------- JSON-API voor de kiosk-tablet-app (tablet_code_controleren) ----------


def _zet_tablet_code(db, naam, code, actief=1):
    db.execute(
        "UPDATE gebruikers SET tablet_code_hash = ?, actief = ? WHERE naam = ?",
        (generate_password_hash(code, method=WACHTWOORD_HASH_METHODE), actief, naam),
    )
    db.commit()


def test_controleren_werkt_zonder_sessie_of_csrf_token(client, db):
    """De app heeft geen cookies/sessie -- dit moet dus lukken met een kale
    POST, zonder in te loggen en zonder csrf_token (zie de uitzondering in
    csrf_beschermen, app.py)."""
    _zet_tablet_code(db, "admin", "246813")
    resp = client.post("/api/tablet-code/controleren", json={"code": "246813"})
    assert resp.status_code == 200
    assert resp.get_json() == {"geldig": True}


def test_controleren_met_onjuiste_code(client, db):
    _zet_tablet_code(db, "admin", "246813")
    resp = client.post("/api/tablet-code/controleren", json={"code": "999999"})
    assert resp.status_code == 200
    assert resp.get_json()["geldig"] is False


def test_controleren_met_ongeldig_formaat_crasht_niet(client, db):
    for code in ("12345", "1234567", "abcdef", ""):
        resp = client.post("/api/tablet-code/controleren", json={"code": code})
        assert resp.status_code == 200
        assert resp.get_json()["geldig"] is False


def test_controleren_zonder_body_crasht_niet(client, db):
    resp = client.post("/api/tablet-code/controleren")
    assert resp.status_code == 200
    assert resp.get_json()["geldig"] is False


def test_geblokkeerd_account_zijn_code_werkt_niet_meer(client, db):
    _zet_tablet_code(db, "admin", "246813", actief=0)
    resp = client.post("/api/tablet-code/controleren", json={"code": "246813"})
    assert resp.get_json()["geldig"] is False


def test_te_veel_mislukte_pogingen_blokkeert_tijdelijk(client, db):
    _zet_tablet_code(db, "admin", "246813")
    for _ in range(10):
        client.post("/api/tablet-code/controleren", json={"code": "000000"})

    # Zelfs de juiste code wordt nu geweigerd -- de blokkade geldt voor het
    # IP-adres, niet voor een specifieke code.
    resp = client.post("/api/tablet-code/controleren", json={"code": "246813"})
    assert resp.status_code == 429
    data = resp.get_json()
    assert data["geldig"] is False
    assert data["fout"] == "te_veel_pogingen"


def test_geldige_code_ruimt_eigen_mislukte_pogingen_op(client, db):
    _zet_tablet_code(db, "admin", "246813")
    for _ in range(5):
        client.post("/api/tablet-code/controleren", json={"code": "000000"})

    resp = client.post("/api/tablet-code/controleren", json={"code": "246813"})
    assert resp.get_json() == {"geldig": True}

    # Na een geslaagde poging is de teller voor dit IP-adres helemaal weg --
    # geen enkele rij meer, dus een volgende mislukte poging begint weer bij 0
    # (dus zeker niet meteen geblokkeerd door de 5 pogingen van hierboven).
    assert db.execute("SELECT COUNT(*) AS n FROM tablet_code_pogingen").fetchone()["n"] == 0
    resp = client.post("/api/tablet-code/controleren", json={"code": "000000"})
    assert resp.status_code == 200
    assert resp.get_json()["geldig"] is False
