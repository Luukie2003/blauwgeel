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


def test_welkom_popup_verschijnt_eenmalig_na_inloggen(client):
    """Meteen na het inloggen moet de welkom-pop-up (begroeting + keuze
    tussen desktop/handterminal) verschijnen -- op de eerstvolgende
    pagina, en daarna niet meer."""
    token = _csrf(client)
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": token},
        headers={"User-Agent": DESKTOP_UA},
        follow_redirects=True,
    )
    body = resp.data.decode()
    assert 'id="welkom-modal"' in body
    assert "admin" in body
    assert any(g in body for g in ["Goedemorgen", "Goedemiddag", "Goedenavond"])
    assert "/weergave/desktop" in body
    assert "/weergave/pda" in body

    resp = client.get("/")
    assert 'id="welkom-modal"' not in resp.data.decode()


def test_inlogpagina_heeft_geen_aparte_handterminal_knop_meer(client):
    resp = client.get("/login")
    assert b"Aanmelden in handterminal-weergave" not in resp.data


def test_telefoon_useragent_krijgt_pda_start_op_eerste_bezoek(client):
    resp = _inloggen_met_useragent(client, TELEFOON_UA)
    assert _cookies_bevatten(resp, "weergave=pda")

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"pda-menu" in resp.data


def test_niet_ingelogd_bezoek_op_telefoon_zet_pda_al_vast_voor_het_inloggen(client):
    """Regressietest: het allereerste verzoek van een nog niet ingelogde
    telefoon is meestal een GET op een beveiligde pagina (bijv. '/'), die
    vereis_login() meteen ombuigt naar /login -- dat gebeurt vóór de eigen
    view draait. Als zet_weergave_modus() dan nog niet is geweest, zet die
    ombuiging het cookie stiekem op 'desktop' vast (de fallback), en wint
    dat cookie daarna altijd van de User-Agent, ook na het echte inloggen.
    Moet dus al bij déze allereerste, nog niet ingelogde omleiding kloppen."""
    resp = client.get("/", headers={"User-Agent": TELEFOON_UA})
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("/login")
    assert _cookies_bevatten(resp, "weergave=pda")

    token = _csrf(client)
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": token},
    )
    assert resp.status_code == 302

    resp = client.get("/")
    assert b"pda-menu" in resp.data


def test_desktop_useragent_krijgt_gewoon_dashboard_op_eerste_bezoek(client):
    resp = _inloggen_met_useragent(client, DESKTOP_UA)
    assert _cookies_bevatten(resp, "weergave=desktop")

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"pda-menu" not in resp.data


def test_cookie_wint_van_useragent_zodra_gezet(client):
    _inloggen_met_useragent(client, DESKTOP_UA)
    resp = client.get("/", headers={"User-Agent": TELEFOON_UA})
    assert b"pda-menu" not in resp.data


def test_weergave_pda_knop_zet_cookie_en_toont_pda_daarna(ingelogde_client):
    resp = ingelogde_client.get("/weergave/pda")
    assert resp.status_code == 302
    assert _cookies_bevatten(resp, "weergave=pda")

    resp = ingelogde_client.get("/", headers={"User-Agent": DESKTOP_UA})
    assert b"pda-menu" in resp.data


def test_weergave_desktop_knop_zet_cookie_en_toont_desktop_daarna(ingelogde_client):
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/weergave/desktop")
    assert resp.status_code == 302
    assert _cookies_bevatten(resp, "weergave=desktop")

    resp = ingelogde_client.get("/", headers={"User-Agent": TELEFOON_UA})
    assert b"pda-menu" not in resp.data


def test_pda_modus_toont_compacte_shell_op_tellen(ingelogde_client):
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/tellen")
    body = resp.data.decode()
    assert "pda-kop-menuknop" in body
    assert 'class="pda-kop-titel">Tellen<' in body
    assert 'class="app-zijbalk"' not in body
    assert "Looplijst starten" in body
    # De grote losse-productenlijst hoort in PDA-modus niet te verschijnen.
    assert "Eerdere tellingen en omzet" not in body


def test_desktop_modus_toont_gewoon_de_volledige_tellen_pagina(ingelogde_client):
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/tellen")
    body = resp.data.decode()
    assert 'class="app-zijbalk"' in body
    assert "Eerdere tellingen en omzet" in body


def test_pda_modus_toont_voorgesteld_om_te_bestellen_als_kaarten(ingelogde_client):
    """De handterminal mag de bestel-suggesties niet meer verbergen (was
    vroeger zo), maar toont ze als aanraakvriendelijke kaarten i.p.v. de
    brede tabel die de volledige site gebruikt."""
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/bestellijst")
    body = resp.data.decode()
    assert "Openstaande bestellingen" in body
    assert "Voorgesteld om te bestellen" in body
    assert "Al besteld? Factuur klaarzetten" in body
    assert "Bestellijst (PDF)" not in body
    assert 'id="suggesties-kaarten"' in body
    assert 'id="suggesties-tabel"' not in body


def test_desktop_modus_toont_wel_voorgesteld_om_te_bestellen(ingelogde_client):
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/bestellijst")
    body = resp.data.decode()
    assert "Voorgesteld om te bestellen" in body
    assert 'id="suggesties-tabel"' in body
    assert 'id="suggesties-kaarten"' not in body


def test_pda_start_bevat_alle_zes_secties(ingelogde_client):
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/")
    body = resp.data.decode()
    for label in ["Tellen", "Boeken", "Prikbord", "Kassa", "Bestellijst", "Geschiedenis"]:
        assert label in body


def test_pda_shell_bevat_link_naar_volledige_site(ingelogde_client):
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/")
    assert b"/weergave/desktop" in resp.data


def test_pda_kop_toont_actieve_sectie_als_titel(ingelogde_client):
    """Zonder de vaste navigatiebalk (geeft ruimte terug op een klein
    scherm) is de koptitel de enige aanwijzing welke sectie je open hebt
    staan -- moet dus meeveranderen per pagina."""
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/bijzonderheden")
    body = resp.data.decode()
    assert 'class="pda-kop-titel">Prikbord<' in body


def test_pda_kop_toont_merknaam_op_startscherm(ingelogde_client):
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/")
    body = resp.data.decode()
    assert 'class="pda-kop-titel">BG 1915<' in body


def test_kassa_telling_detail_werkt_ook_in_pda_modus(ingelogde_client, db):
    ingelogde_client.get("/weergave/pda")
    data = {"csrf_token": _csrf(ingelogde_client), "contante_omzet": "0"}
    data.update({k: "0" for k in [
        "aantal_50", "aantal_20", "aantal_10", "aantal_5", "aantal_2",
        "aantal_1", "aantal_050", "aantal_020", "aantal_010", "aantal_005",
    ]})
    resp = ingelogde_client.post("/kassa/tellen", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert "pda-kop-menuknop" in resp.data.decode()


def test_pda_tellen_lopen_controleren_toont_kaarten(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    with ingelogde_client.session_transaction() as sess:
        sess["loop_review"] = {str(product["id"]): 5}
        sess["loop_bar"] = {str(product["id"]): "3"}
        sess["loop_hok"] = {str(product["id"]): "2"}

    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/tellen/lopen/controleren")
    body = resp.data.decode()
    assert 'id="loop-controleren-kaarten"' in body
    assert "<table>" not in body


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


def test_pda_bestelling_nieuw_toont_kaarten_en_pda_schil(ingelogde_client):
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/bestellijst/nieuw")
    body = resp.data.decode()
    assert 'id="bestelling-kaarten"' in body
    assert 'id="bestelling-tabel"' not in body
    assert "pda-kop-menuknop" in body


def test_desktop_bestelling_nieuw_toont_tabel(ingelogde_client):
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get("/bestellijst/nieuw")
    body = resp.data.decode()
    assert 'id="bestelling-tabel"' in body
    assert 'id="bestelling-kaarten"' not in body
    assert 'class="app-zijbalk"' in body


def test_pda_kassa_geschiedenis_toont_kaarten_en_verbergt_grafiek(ingelogde_client, db):
    db.execute(
        "INSERT INTO kassa_mutaties (type, bedrag, datum, naam, opmerking) "
        "VALUES ('afdracht', 50.0, '2026-01-01 10:00', 'admin', 'test')"
    )
    db.commit()

    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get("/kassa/geschiedenis")
    body = resp.data.decode()
    assert 'id="kassa-tijdlijn-kaarten"' in body
    assert "<table>" not in body
    assert "omzet-trend-grafiek" not in body
    assert "pda-kop-menuknop" in body


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


def test_pda_product_bewerken_blijft_in_handterminal_schil(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    ingelogde_client.get("/weergave/pda")
    resp = ingelogde_client.get(f"/producten/{product['id']}/bewerken")
    body = resp.data.decode()
    assert "pda-kop-menuknop" in body
    assert 'class="app-zijbalk"' not in body


def test_desktop_product_bewerken_toont_gewone_schil(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    ingelogde_client.get("/weergave/desktop")
    resp = ingelogde_client.get(f"/producten/{product['id']}/bewerken")
    body = resp.data.decode()
    assert 'class="app-zijbalk"' in body
