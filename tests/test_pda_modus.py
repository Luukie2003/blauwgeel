"""Regressietests voor de PDA-modus (compacte vloer-weergave op de
telefoon): de automatische herkenning op basis van de User-Agent, het
weergave-cookie dat daarna wint, de handmatige omschakelknoppen, en de
inhoud die per pagina wordt in-/uitgeschakeld."""

from conftest import stel_csrf_token_in as _csrf

TELEFOON_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _cookies_bevatten(resp, tekst):
    return any(tekst in c for c in resp.headers.getlist("Set-Cookie"))


def _inloggen_met_useragent(client, user_agent):
    """Zoals de ingelogde_client-fixture, maar met een zelfgekozen
    User-Agent op de allereerste request -- nodig om het 'eerste bezoek
    op dit toestel'-gedrag te testen, want dat wordt anders al bepaald
    door de (niet-telefoon) User-Agent van de inlog-POST zelf."""
    token = _csrf(client)
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": token},
        headers={"User-Agent": user_agent},
    )
    assert resp.status_code == 302, "seed-login voor tests is mislukt"
    return resp


def test_inlogpagina_heeft_geen_aparte_handterminal_knop_meer(client):
    resp = client.get("/login")
    assert b"Aanmelden in handterminal-weergave" not in resp.data


def test_cookie_wint_van_useragent_zodra_gezet(client):
    _inloggen_met_useragent(client, DESKTOP_UA)
    resp = client.get("/", headers={"User-Agent": TELEFOON_UA})
    assert b"pda-menu" not in resp.data


def test_desktop_modus_toont_gewoon_de_volledige_tellen_pagina(ingelogde_client):
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/tellen")
    body = resp.data.decode()
    assert 'class="app-zijbalk"' in body
    assert "Eerdere tellingen en omzet" in body


def test_desktop_modus_toont_wel_voorgesteld_om_te_bestellen(ingelogde_client):
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/bestellijst")
    body = resp.data.decode()
    assert "Voorgesteld om te bestellen" in body
    assert "Al besteld? Bestelling klaarzetten" in body
    assert 'id="suggesties-tabel"' in body


def test_desktop_tellen_lopen_controleren_toont_tabel(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    with ingelogde_client.session_transaction() as sess:
        sess["loop_review"] = {str(product["id"]): 5}
        sess["loop_bar"] = {str(product["id"]): "3"}
        sess["loop_hok"] = {str(product["id"]): "2"}

    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/tellen/lopen/controleren")
    body = resp.data.decode()
    assert "<table>" in body
    assert 'id="loop-controleren-kaarten"' not in body


def test_bestelling_nieuw_blijft_altijd_desktop_ongeacht_weergave(ingelogde_client):
    """Een nieuwe bestelling klaarzetten gebeurt altijd op desktop, ook als
    het toestel toevallig in handterminal-weergave staat."""
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/bestellijst/nieuw")
    body = resp.data.decode()
    assert 'id="bestelling-tabel"' in body
    assert 'class="app-zijbalk"' in body
    assert "pda-kop-menuknop" not in body


def test_desktop_bestelling_nieuw_toont_tabel(ingelogde_client):
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/bestellijst/nieuw")
    body = resp.data.decode()
    assert 'id="bestelling-tabel"' in body
    assert 'class="app-zijbalk"' in body


def test_desktop_kassa_geschiedenis_toont_tabel(ingelogde_client, db):
    db.execute(
        "INSERT INTO kassa_mutaties (type, bedrag, datum, naam, opmerking) "
        "VALUES ('toevoeging', 25.0, '2026-01-01 10:00', 'admin', 'test')"
    )
    db.commit()

    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/kassa/geschiedenis")
    body = resp.data.decode()
    assert "<table>" in body
    assert 'id="kassa-tijdlijn-kaarten"' not in body
    assert 'class="app-zijbalk"' in body


def test_desktop_product_bewerken_toont_gewone_schil(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get(f"/producten/{product['id']}/bewerken")
    body = resp.data.decode()
    assert 'class="app-zijbalk"' in body


def test_desktop_modus_toont_levering_inboeken_knop(ingelogde_client):
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/boeken")
    body = resp.data.decode()
    assert "Levering inboeken" in body
