from test_secties_rechten import _login, _maak_vrijwilliger


def test_gewone_paginabezoeken_worden_gelogd(ingelogde_client, db):
    ingelogde_client.get("/bijzonderheden")

    rij = db.execute(
        "SELECT endpoint, weergave_modus FROM paginabezoeken ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert rij["endpoint"] == "bijzonderheden"
    assert rij["weergave_modus"] == "desktop"


def test_gebruiker_id_wordt_meegelogd_voor_ingelogde_bezoeker(ingelogde_client, db):
    ingelogde_client.get("/bijzonderheden")

    admin_id = db.execute("SELECT id FROM gebruikers WHERE naam = 'admin'").fetchone()["id"]
    rij = db.execute(
        "SELECT gebruiker_id FROM paginabezoeken WHERE endpoint = 'bijzonderheden' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert rij["gebruiker_id"] == admin_id


def test_anonieme_publieke_pagina_wordt_gelogd_zonder_gebruiker(client, db):
    client.get("/offline")  # opwarmen, telt niet mee (zie hieronder)
    aantal_voor = db.execute(
        "SELECT COUNT(*) AS n FROM paginabezoeken WHERE endpoint = 'kiosk_prijzen_scherm'"
    ).fetchone()["n"]

    client.get("/kiosk/prijzen")

    rij = db.execute(
        "SELECT gebruiker_id FROM paginabezoeken WHERE endpoint = 'kiosk_prijzen_scherm' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    aantal_na = db.execute(
        "SELECT COUNT(*) AS n FROM paginabezoeken WHERE endpoint = 'kiosk_prijzen_scherm'"
    ).fetchone()["n"]
    assert aantal_na == aantal_voor + 1
    assert rij["gebruiker_id"] is None


def test_statische_bestanden_en_polling_endpoints_worden_niet_gelogd(client, db):
    client.get("/offline")
    client.get("/kiosk/prijzen/versie")
    client.get("/kiosk/scherm/versie")

    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM paginabezoeken "
        "WHERE endpoint IN ('offline_pagina', 'kiosk_prijzen_versie', 'kiosk_scherm_versie')"
    ).fetchone()["n"]
    assert aantal == 0


def test_post_verzoeken_worden_niet_apart_gelogd(ingelogde_client, db):
    from conftest import stel_csrf_token_in as _csrf

    ingelogde_client.post(
        "/bijzonderheden",
        data={"tekst": "test", "csrf_token": _csrf(ingelogde_client)},
        follow_redirects=True,
    )

    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM paginabezoeken WHERE endpoint = 'bijzonderheden'"
    ).fetchone()["n"]
    # De POST zelf telt niet mee, wel de GET van de resulterende redirect
    # (die de browser altijd meteen volgt) -- dus precies 1, niet 2.
    assert aantal == 1


def test_foutpagina_wordt_niet_gelogd(ingelogde_client, db):
    ingelogde_client.get("/deze-pagina-bestaat-niet")

    aantal = db.execute("SELECT COUNT(*) AS n FROM paginabezoeken").fetchone()["n"]
    assert aantal == 0


def test_gebruiksstatistieken_pagina_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "gewone_vrijwilliger", "voorraad,kassa,keuken,stemmen")
    _login(client, "gewone_vrijwilliger")

    resp = client.get("/gebruiksstatistieken", follow_redirects=True)
    assert b"alleen voor beheerders" in resp.data


def test_gebruiksstatistieken_pagina_toont_meest_gebruikte_functies(ingelogde_client, db):
    for _ in range(3):
        ingelogde_client.get("/bijzonderheden")
    ingelogde_client.get("/voorraadoverzicht")

    resp = ingelogde_client.get("/gebruiksstatistieken")

    assert resp.status_code == 200
    tekst = resp.data.decode()
    assert "Bijzonderheden" in tekst
    assert "admin" in tekst


def test_gebruiksstatistieken_periode_filter_beperkt_tot_geldige_opties(ingelogde_client):
    resp = ingelogde_client.get("/gebruiksstatistieken?dagen=999")
    assert resp.status_code == 200
    assert b"Laatste 30 dagen" in resp.data
