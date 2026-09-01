"""Regressietests voor de AJAX-laag (base.html: .js-ajax-form + is_ajax_verzoek()
in app.py): routes die met de fetch-header JSON teruggeven i.p.v. een
redirect, zodat de pagina niet hoeft te herladen. De gewone (niet-AJAX)
paden van deze routes blijven ongewijzigd en staan al elders getest."""

from conftest import stel_csrf_token_in as _csrf

AJAX_HEADERS = {"X-Requested-With": "fetch"}


def test_product_actief_wisselen_geeft_json_terug(ingelogde_client, db):
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    resp = ingelogde_client.post(
        f"/producten/{product['id']}/actief",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers=AJAX_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["actief"] == 0
    assert "melding" in data

    bijgewerkt = db.execute("SELECT actief FROM producten WHERE id = ?", (product["id"],)).fetchone()
    assert bijgewerkt["actief"] == 0


def test_product_actief_wisselen_onbekend_product_geeft_json_fout(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/producten/999999/actief",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers=AJAX_HEADERS,
    )
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_categorie_verkoopprijs_verplicht_geeft_json_terug(ingelogde_client, db):
    db.execute("INSERT INTO categorieen (naam, verkoopprijs_verplicht) VALUES ('AjaxTest', 1)")
    db.commit()
    categorie = db.execute("SELECT * FROM categorieen WHERE naam = 'AjaxTest'").fetchone()

    resp = ingelogde_client.post(
        f"/categorieen/{categorie['id']}/verkoopprijs-verplicht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers=AJAX_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["verkoopprijs_verplicht"] == 0

    bijgewerkt = db.execute(
        "SELECT verkoopprijs_verplicht FROM categorieen WHERE id = ?", (categorie["id"],)
    ).fetchone()
    assert bijgewerkt["verkoopprijs_verplicht"] == 0


def test_mededeling_afhandelen_en_heropenen_geven_json_terug(ingelogde_client, db):
    ingelogde_client.post(
        "/bijzonderheden",
        data={"csrf_token": _csrf(ingelogde_client), "tekst": "Ajax-test mededeling"},
    )
    mededeling = db.execute("SELECT * FROM mededelingen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.post(
        f"/bijzonderheden/{mededeling['id']}/afhandelen",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers=AJAX_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["afgehandeld"] == 1

    resp = ingelogde_client.post(
        f"/bijzonderheden/{mededeling['id']}/heropenen",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers=AJAX_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["afgehandeld"] == 0

    bijgewerkt = db.execute(
        "SELECT afgehandeld FROM mededelingen WHERE id = ?", (mededeling["id"],)
    ).fetchone()
    assert bijgewerkt["afgehandeld"] == 0


def test_stem_afkeuren_en_goedkeuren_geven_json_terug(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/stemmen/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "titel": "Ajax-test stemming",
            "optie1": "A",
            "optie2": "B",
        },
        follow_redirects=False,
    )
    stemvraag_id = int(resp.headers["Location"].rsplit("/", 1)[-1])
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()

    ingelogde_client.get(f"/stem/{stemvraag_id}")
    ingelogde_client.post(
        f"/stem/{stemvraag_id}",
        data={"csrf_token": _csrf(ingelogde_client), "optie_id": optie["id"], "naam": "Ajax Stemmer"},
    )
    stem = db.execute(
        "SELECT * FROM stemmen WHERE stemvraag_id = ? ORDER BY id DESC LIMIT 1", (stemvraag_id,)
    ).fetchone()

    resp = ingelogde_client.post(
        f"/stemmen/stem/{stem['id']}/afkeuren",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers=AJAX_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["afgekeurd"] == 1

    resp = ingelogde_client.post(
        f"/stemmen/stem/{stem['id']}/goedkeuren",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers=AJAX_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["afgekeurd"] == 0

    bijgewerkt = db.execute("SELECT afgekeurd FROM stemmen WHERE id = ?", (stem["id"],)).fetchone()
    assert bijgewerkt["afgekeurd"] == 0


def test_gewone_formulier_submit_blijft_gewoon_een_redirect(ingelogde_client, db):
    """Zonder de fetch-header (dus een gewone <form>-submit, of JS
    uitgeschakeld) moet het gedrag exact hetzelfde blijven als voorheen."""
    product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    resp = ingelogde_client.post(
        f"/producten/{product['id']}/actief",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert resp.content_type != "application/json"
