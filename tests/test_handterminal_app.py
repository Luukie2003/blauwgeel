"""Wat de site doet voor de handterminal-app op de Zebra (android-apps/handterminal)."""

from test_tablet_code import _zet_tablet_code

APP = "Mozilla/5.0 (Linux; Android 6.0.1; TC51 Build/MMB29K; wv) Chrome/106.0 Mobile Safari/537.36 KantineHandterminal/1.0.0"
TELEFOON = "Mozilla/5.0 (Linux; Android 6.0.1; TC51 Build/MMB29K) Chrome/106.0 Mobile Safari/537.36"


def _inloggen(client, code, ua=APP):
    return client.post("/api/tablet-code/inloggen", json={"code": code}, headers={"User-Agent": ua})


def test_foute_code_zegt_hoeveel_pogingen_er_nog_zijn(client, db):
    _zet_tablet_code(db, "admin", "246813")
    over = [_inloggen(client, "000000").get_json()["pogingen_over"] for _ in range(5)]
    assert over == [4, 3, 2, 1, 0]


def test_op_slot_zegt_hoe_lang_nog(client, db):
    _zet_tablet_code(db, "admin", "246813")
    for _ in range(5):
        _inloggen(client, "000000")
    resp = _inloggen(client, "246813")
    assert resp.status_code == 429
    assert 1 <= resp.get_json()["wacht_minuten"] <= 30


def test_in_de_app_geen_weergavekeuze_na_inloggen(app, db):
    _zet_tablet_code(db, "admin", "246813")
    in_app = app.test_client()
    assert _inloggen(in_app, "246813").get_json()["geldig"]
    in_app.set_cookie("weergave", "pda")
    assert 'id="welkom-modal"' not in in_app.get("/", headers={"User-Agent": APP}).data.decode()

    # In een gewone browser blijft de vraag welke weergave je wilt.
    browser = app.test_client()
    assert _inloggen(browser, "246813", ua=TELEFOON).get_json()["geldig"]
    assert 'id="welkom-modal"' in browser.get("/", headers={"User-Agent": TELEFOON}).data.decode()


def test_scan_van_een_bekende_barcode_gaat_meteen_naar_het_product(ingelogde_client, db):
    product_id = db.execute("SELECT id FROM producten ORDER BY id LIMIT 1").fetchone()["id"]
    db.execute(
        "INSERT INTO artikelen (product_id, naam, ean, aantal_per_verpakking, inkoopprijs, aangemaakt_op)"
        " VALUES (?, 'Testartikel', '8710200001234', 1, 1.0, '2026-10-18 12:00')",
        (product_id,),
    )
    db.commit()
    resp = ingelogde_client.get("/barcodes/zoek?direct=1&code=8710200001234")
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/producten/{product_id}")
    # Zonder direct=1 (zelf opzoeken op de barcodepagina) blijf je op de barcodepagina.
    assert ingelogde_client.get("/barcodes/zoek?code=8710200001234").status_code == 200
    # Een onbekende barcode: de barcodepagina, om hem toe te voegen.
    assert ingelogde_client.get("/barcodes/zoek?direct=1&code=8710200001241").status_code == 200


def test_in_de_app_geen_kop_en_tabbalk_van_de_site(ingelogde_client):
    ingelogde_client.set_cookie("weergave", "pda")
    in_app = ingelogde_client.get("/bijzonderheden", headers={"User-Agent": APP}).data.decode()
    assert 'class="pda-tabbalk"' not in in_app and 'id="pda-zoek-invoer"' not in in_app and "pda-in-app" in in_app
    browser = ingelogde_client.get("/bijzonderheden", headers={"User-Agent": TELEFOON}).data.decode()
    assert 'class="pda-tabbalk"' in browser and 'id="pda-zoek-invoer"' in browser
