from conftest import stel_csrf_token_in as _csrf


def _maak_stemvraag(client, titel="Welk fust voor het weizen?", opties=("Fust A", "Fust B", "Fust C")):
    resp = client.post(
        "/stemmen/nieuw",
        data={"csrf_token": _csrf(client), "titel": titel, "optie": list(opties)},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return resp.headers["Location"].rsplit("/", 1)[-1]  # stemvraag_id


def test_stemvraag_aanmaken(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["titel"] == "Welk fust voor het weizen?"
    assert vraag["actief"] == 1
    opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    assert [o["tekst"] for o in opties] == ["Fust A", "Fust B", "Fust C"]


def test_stemvraag_met_minder_dan_2_opties_wordt_geweigerd(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/stemmen/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "titel": "Test", "optie": ["Enige optie"]},
    )
    assert resp.status_code == 302
    aantal = db.execute("SELECT COUNT(*) AS n FROM stemvragen").fetchone()["n"]
    assert aantal == 0


def test_lege_opties_worden_genegeerd(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, opties=("Fust A", "", "Fust B", "  "))
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemopties WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 2


def test_publieke_pagina_bereikbaar_zonder_extra_login(ingelogde_client, db):
    """De publieke stempagina staat in OPEN_ENDPOINTS -- geen redirect naar
    /login, ongeacht of de bezoeker al ingelogd is."""
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.get(f"/stem/{stemvraag_id}")
    assert resp.status_code == 200
    assert b"Welk fust voor het weizen?" in resp.data


def test_niet_bestaande_stemvraag_geeft_404(client):
    resp = client.get("/stem/99999")
    assert resp.status_code == 404


def test_stemmen_zet_een_stem_weg_en_cookie(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()

    # Eerst GET om het stem_kiezer-cookie te krijgen (net als een echte bezoeker).
    ingelogde_client.get(f"/stem/{stemvraag_id}")
    resp = ingelogde_client.post(
        f"/stem/{stemvraag_id}",
        data={"csrf_token": _csrf(ingelogde_client), "optie_id": optie["id"]},
    )
    assert resp.status_code == 200
    assert b"Bedankt voor je stem" in resp.data

    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 1


def test_dubbel_stemmen_wordt_geweerd(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    ingelogde_client.get(f"/stem/{stemvraag_id}")
    token = _csrf(ingelogde_client)
    ingelogde_client.post(f"/stem/{stemvraag_id}", data={"csrf_token": token, "optie_id": optie["id"]})

    # Tweede poging, zelfde browser/cookie.
    resp = ingelogde_client.post(
        f"/stem/{stemvraag_id}", data={"csrf_token": token, "optie_id": optie["id"]}
    )
    assert b"al gestemd" in resp.data

    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 1  # niet dubbel geteld


def test_gesloten_stemming_accepteert_geen_nieuwe_stem(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/sluiten", data={"csrf_token": _csrf(ingelogde_client)}
    )

    ingelogde_client.get(f"/stem/{stemvraag_id}")
    resp = ingelogde_client.post(
        f"/stem/{stemvraag_id}", data={"csrf_token": _csrf(ingelogde_client), "optie_id": optie["id"]}
    )
    assert b"is gesloten" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 0


def test_verwijderen_verwijdert_ook_opties_en_stemmen(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone() is None
    assert (
        db.execute(
            "SELECT COUNT(*) AS n FROM stemopties WHERE stemvraag_id = ?", (stemvraag_id,)
        ).fetchone()["n"]
        == 0
    )


def test_detailpagina_toont_qr_code(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.get(f"/stemmen/{stemvraag_id}")
    assert resp.status_code == 200
    assert b"<svg" in resp.data
    assert f"/stem/{stemvraag_id}".encode() in resp.data
