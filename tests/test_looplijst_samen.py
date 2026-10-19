"""Tellen op de site en in de handterminal-app tegelijk (zie routes/tellen/looplijst_opslag.py): wat je in de app telt,
komt op de site binnen; afbreken of opslaan op het ene toestel stopt de telling ook op het andere, in plaats van dat
die hem bij de volgende stap weer terugzet."""

from conftest import stel_csrf_token_in as _csrf
from test_app_api import _post, _tel_producten, app_client  # noqa: F401 (fixture)

from routes.tellen.looplijst_opslag import AFGEBROKEN, VERVANGEN


def _stap(site, product_id, fase, geteld, actie="volgende"):
    """Eén stap op de looplijst van de site, zoals het formulier hem verstuurt."""
    return site.post("/tellen/lopen", data={"csrf_token": _csrf(site), "product_id": product_id, "fase": fase,
                                            "geteld": geteld, "actie": actie})


def _stand(app_client):  # noqa: F811
    return app_client.get("/api/app/tellen").get_json()["stand"]


def test_wat_de_app_telt_komt_op_de_site_binnen(app_client, ingelogde_client, db):  # noqa: F811
    producten = _tel_producten(app_client)
    eerste, derde = producten[0], producten[2]
    bar = {str(eerste["id"]): "5"}
    assert _post(app_client, "/api/app/tellen/stand", fase="bar", index=2, bar=bar, hok={}, loop_id="L1",
                 nieuw=True).status_code == 200

    # Op de site staat de telling als onderbroken, bij het derde product, en verder tellen kan daar.
    overzicht = ingelogde_client.get("/tellen").data.decode()
    assert "Looplijst onderbroken" in overzicht and "product 3 van" in overzicht
    assert derde["naam"] in ingelogde_client.get("/tellen/lopen").data.decode()
    _stap(ingelogde_client, derde["id"], "bar", "8")
    stand = _stand(app_client)
    assert stand["loop_id"] == "L1" and stand["index"] == 3 and stand["bar"] == {**bar, str(derde["id"]): "8"}

    # En de app gaat weer verder met wat er op de site bij kwam.
    assert _post(app_client, "/api/app/tellen/stand", fase="bar", index=4, bar=stand["bar"], hok={},
                 loop_id="L1").status_code == 200


def test_een_aantal_hoort_bij_het_product_dat_op_het_scherm_stond(app_client, ingelogde_client, db):  # noqa: F811
    """De site toonde product 1; intussen is de app verder (product 6). Het ingevulde aantal hoort bij product 1."""
    producten = _tel_producten(app_client)
    ingelogde_client.get("/tellen/lopen/starten")
    _stap(ingelogde_client, producten[0]["id"], "bar", "2")
    loop_id = _stand(app_client)["loop_id"]
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=5, bar={str(producten[0]["id"]): "2"}, hok={},
          loop_id=loop_id)
    _stap(ingelogde_client, producten[1]["id"], "bar", "9")
    assert _stand(app_client)["bar"] == {str(producten[0]["id"]): "2", str(producten[1]["id"]): "9"}


def test_afbreken_op_de_site_stopt_de_app(app_client, ingelogde_client, db):  # noqa: F811
    producten = _tel_producten(app_client)
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=1, bar={str(producten[0]["id"]): "3"}, hok={},
          loop_id="L1", nieuw=True)
    overzicht = ingelogde_client.get("/tellen").data.decode()
    assert "/tellen/lopen/afbreken" in overzicht and "Ja, afbreken" in overzicht
    resp = ingelogde_client.post("/tellen/lopen/afbreken", data={"csrf_token": _csrf(ingelogde_client)})
    assert resp.headers["Location"].endswith("/tellen") and _stand(app_client) is None
    assert "Looplijst onderbroken" not in ingelogde_client.get("/tellen").data.decode()

    # De app geeft zijn stand door: niet terugzetten, maar laten weten dat hij is afgebroken.
    resp = _post(app_client, "/api/app/tellen/stand", fase="bar", index=2, bar={str(producten[0]["id"]): "3"}, hok={},
                 loop_id="L1")
    assert resp.status_code == 409 and resp.get_json() == {"fout": "afgebroken", "melding": AFGEBROKEN}
    assert _stand(app_client) is None
    assert _post(app_client, "/api/app/tellen/controleren", bar={"1": "2"}, hok={}, loop_id="L1").status_code == 409
    resp = _post(app_client, "/api/app/tellen/bevestigen", waarden={"1": 2}, loop_id="L1", verzoek_id="b1")
    assert resp.status_code == 409 and db.execute("SELECT COUNT(*) FROM tellingen").fetchone()[0] == 0


def test_afbreken_in_de_app_stopt_de_site(app_client, ingelogde_client, db):  # noqa: F811
    producten = _tel_producten(app_client)
    ingelogde_client.get("/tellen/lopen/starten")
    _stap(ingelogde_client, producten[0]["id"], "bar", "4")
    loop_id = _stand(app_client)["loop_id"]
    _post(app_client, "/api/app/tellen/stoppen", loop_id=loop_id)
    assert _stand(app_client) is None

    # De volgende stap op de site zet hem niet terug, maar meldt dat hij is afgebroken.
    resp = _stap(ingelogde_client, producten[1]["id"], "bar", "6")
    assert resp.headers["Location"].endswith("/tellen") and _stand(app_client) is None
    assert AFGEBROKEN in ingelogde_client.get("/tellen").data.decode()
    assert ingelogde_client.get("/tellen/lopen").status_code == 200  # gewoon een nieuwe looplijst


def test_een_late_stop_gooit_een_nieuwere_telling_niet_weg(app_client, db):  # noqa: F811
    """De app brak telling L1 af zonder verbinding en geeft dat later door; intussen loopt telling L2."""
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=3, bar={"1": "2"}, hok={}, loop_id="L2", nieuw=True)
    _post(app_client, "/api/app/tellen/stoppen", loop_id="L1")
    assert _stand(app_client)["loop_id"] == "L2"


def test_opnieuw_begonnen_op_een_ander_toestel(app_client, db):  # noqa: F811
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=3, bar={"1": "2"}, hok={}, loop_id="L1", nieuw=True)
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=0, bar={}, hok={}, loop_id="L2", nieuw=True)
    resp = _post(app_client, "/api/app/tellen/stand", fase="bar", index=4, bar={"1": "2"}, hok={}, loop_id="L1")
    assert resp.status_code == 409 and resp.get_json()["melding"] == VERVANGEN


def test_niet_twee_keer_opslaan(app_client, ingelogde_client, db):  # noqa: F811
    """In de app en op de site dezelfde telling bij het controleren: wie het eerst bevestigt, slaat op."""
    producten = _tel_producten(app_client)
    bar = {str(producten[0]["id"]): "3"}
    _post(app_client, "/api/app/tellen/controleren", bar=bar, hok={}, loop_id="L1", nieuw=True)
    assert "Telling controleren" in ingelogde_client.get("/tellen/lopen/hervatten", follow_redirects=True).data.decode()
    ingelogde_client.post("/tellen/lopen/controleren", data={"csrf_token": _csrf(ingelogde_client),
                                                              f"totaal_{producten[0]['id']}": "3"})
    assert db.execute("SELECT COUNT(*) FROM tellingen").fetchone()[0] == 1
    resp = _post(app_client, "/api/app/tellen/bevestigen", waarden={str(producten[0]["id"]): 3}, loop_id="L1",
                 verzoek_id="b1")
    assert resp.status_code == 409 and db.execute("SELECT COUNT(*) FROM tellingen").fetchone()[0] == 1


def test_een_oudere_app_zonder_loop_id_werkt_nog(app_client, db):  # noqa: F811
    producten = _tel_producten(app_client)
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=1, bar={str(producten[0]["id"]): "1"}, hok={})
    _post(app_client, "/api/app/tellen/stoppen")
    assert _stand(app_client) is None
    _post(app_client, "/api/app/tellen/stand", fase="bar", index=1, bar={}, hok={})
    assert _stand(app_client)["index"] == 1
