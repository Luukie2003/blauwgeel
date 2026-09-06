from conftest import stel_csrf_token_in as _csrf


def _voeg_toe(client, tekst="Vuilniszakken"):
    resp = client.post(
        "/boodschappenlijst",
        data={"csrf_token": _csrf(client), "tekst": tekst},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return resp


def test_item_toevoegen(ingelogde_client, db):
    _voeg_toe(ingelogde_client, tekst="Schoonmaakmiddel")
    item = db.execute("SELECT * FROM boodschappen ORDER BY id DESC LIMIT 1").fetchone()
    assert item["tekst"] == "Schoonmaakmiddel"
    assert item["aangemaakt_door"] == "admin"
    assert item["afgevinkt"] == 0


def test_leeg_item_wordt_niet_toegevoegd(ingelogde_client, db):
    ingelogde_client.post(
        "/boodschappenlijst", data={"csrf_token": _csrf(ingelogde_client), "tekst": "   "}
    )
    aantal = db.execute("SELECT COUNT(*) AS n FROM boodschappen").fetchone()["n"]
    assert aantal == 0


def test_item_afvinken_bewaart_wie_en_wanneer(ingelogde_client, db):
    _voeg_toe(ingelogde_client)
    item = db.execute("SELECT * FROM boodschappen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.post(
        f"/boodschappenlijst/{item['id']}/afvinken", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302

    item_na = db.execute("SELECT * FROM boodschappen WHERE id = ?", (item["id"],)).fetchone()
    assert item_na["afgevinkt"] == 1
    assert item_na["afgevinkt_door"] == "admin"
    assert item_na["afgevinkt_op"] is not None


def test_afgevinkt_item_kan_terugezet_worden(ingelogde_client, db):
    _voeg_toe(ingelogde_client)
    item = db.execute("SELECT * FROM boodschappen ORDER BY id DESC LIMIT 1").fetchone()
    token = _csrf(ingelogde_client)
    ingelogde_client.post(f"/boodschappenlijst/{item['id']}/afvinken", data={"csrf_token": token})

    ingelogde_client.post(f"/boodschappenlijst/{item['id']}/afvinken", data={"csrf_token": token})
    item_na = db.execute("SELECT * FROM boodschappen WHERE id = ?", (item["id"],)).fetchone()
    assert item_na["afgevinkt"] == 0
    assert item_na["afgevinkt_door"] is None
    assert item_na["afgevinkt_op"] is None


def test_item_verwijderen(ingelogde_client, db):
    _voeg_toe(ingelogde_client, tekst="Koffiemelk")
    item = db.execute("SELECT * FROM boodschappen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.post(
        f"/boodschappenlijst/{item['id']}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM boodschappen WHERE id = ?", (item["id"],)).fetchone() is None


def test_open_en_afgevinkte_items_apart_getoond(ingelogde_client, db):
    _voeg_toe(ingelogde_client, tekst="Nog te kopen item")
    _voeg_toe(ingelogde_client, tekst="Al gekocht item")
    afgevinkt = db.execute(
        "SELECT * FROM boodschappen WHERE tekst = 'Al gekocht item'"
    ).fetchone()
    ingelogde_client.post(
        f"/boodschappenlijst/{afgevinkt['id']}/afvinken", data={"csrf_token": _csrf(ingelogde_client)}
    )

    body = ingelogde_client.get("/boodschappenlijst").data.decode()
    recent_idx = body.index("Recent gekocht")
    # het open item hoort vóór het "Recent gekocht"-blok te staan...
    assert body.index("Nog te kopen item") < recent_idx
    # ...en het afgevinkte item hoort er ná te staan (niet alleen in de
    # flash-melding bovenaan de pagina, die ook de itemtekst bevat).
    assert "Al gekocht item" in body[recent_idx:]
