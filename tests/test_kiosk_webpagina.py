"""Een webpagina als dia (1.81.0), zoals de tussenstand van Shout-out!: alleen van een site uit KIOSK_WEBPAGINA_SITES,
schermvullend in een afgeschermd frame, via deze site zonder het blok met de QR-code -- zie _webpagina_url in
routes/kiosk/sponsoren_sjablonen.py, kiosk_webpagina.py en de Content-Security-Policy in app.py."""
import io

from conftest import stel_csrf_token_in as _csrf

import kiosk_webpagina

STATS = "https://coach.epremium.nl/blauwgeel/stats/"
PAGINA = "<!doctype html><html><head><title>Klassement</title></head><body><section class=\"panel qr\">Scan</section></body></html>"


def _nieuwe_dia(client, **velden):
    data = {"csrf_token": _csrf(client), "sjabloon": "webpagina", "titel": "Tussenstand Shout-out!",
            "weergave_duur_seconden": "20", "actief": "on", **velden}
    return client.post("/kiosk/sponsoren-leden/sponsoren/nieuw", data=data, follow_redirects=True)


def test_de_tussenstand_van_shout_out_als_dia(ingelogde_client, db):
    formulier = ingelogde_client.get("/kiosk/sponsoren-leden/sponsoren/nieuw").get_data(as_text=True)
    assert 'value="webpagina"' in formulier and 'id="webpagina-veld"' in formulier
    assert _nieuwe_dia(ingelogde_client, webpagina_url=STATS).status_code == 200
    rij = db.execute("SELECT id, sjabloon, webpagina_url, weergave_duur_seconden FROM kiosk_sponsoren").fetchone()
    assert tuple(rij)[1:] == ("webpagina", STATS, 20)
    scherm = ingelogde_client.get("/kiosk/scherm")
    tekst = scherm.get_data(as_text=True)
    assert "sjabloon-webpagina" in tekst and f'class="dia-webpagina" src="/kiosk/webpagina/{rij["id"]}"' in tekst
    assert 'sandbox="allow-scripts"' in tekst
    assert "frame-src 'self' https://coach.epremium.nl" in scherm.headers["Content-Security-Policy"]
    bewerken = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{rij['id']}/bewerken").get_data(as_text=True)
    assert f'value="{STATS}"' in bewerken


def test_alleen_een_https_pagina_van_een_bekende_site(ingelogde_client, db):
    for adres in ("https://example.com/klassement", "http://coach.epremium.nl/blauwgeel/stats/", ""):
        resp = _nieuwe_dia(ingelogde_client, webpagina_url=adres)
        assert "coach.epremium.nl (met https://)" in resp.get_data(as_text=True) or not adres
    assert [r[0] for r in db.execute("SELECT webpagina_url FROM kiosk_sponsoren")] == [None, None, None]
    # Zonder goedgekeurd adres komt de dia niet op het scherm.
    assert 'class="dia-webpagina"' not in ingelogde_client.get("/kiosk/scherm").get_data(as_text=True)


def test_de_tv_krijgt_de_pagina_zonder_de_scan(app, ingelogde_client, db, monkeypatch):
    """Openbaar (de tv logt niet in), afgeschermd met sandbox, en met de stijl die de QR-code verbergt."""
    _nieuwe_dia(ingelogde_client, webpagina_url=STATS)
    dia = db.execute("SELECT id FROM kiosk_sponsoren").fetchone()["id"]
    monkeypatch.setattr(kiosk_webpagina, "opgehaald", lambda adres: kiosk_webpagina.zonder_extra(PAGINA, adres))
    tv = app.test_client()
    resp = tv.get(f"/kiosk/webpagina/{dia}")
    tekst = resp.get_data(as_text=True)
    assert resp.status_code == 200 and tekst.index("<head>") < tekst.index(f'<base href="{STATS}">')
    assert ".panel.qr{display:none!important}" in tekst
    assert resp.headers["Content-Security-Policy"].startswith("sandbox allow-scripts;")
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    # Lukt het ophalen niet, dan de pagina zoals hij is; een dia zonder webpagina geeft niets.
    monkeypatch.setattr(kiosk_webpagina, "opgehaald", lambda adres: None)
    terug = tv.get(f"/kiosk/webpagina/{dia}")
    assert terug.status_code == 302 and terug.headers["Location"] == STATS
    assert tv.get("/kiosk/webpagina/999999").status_code == 404
    assert tv.get("/kiosk/webpagina/voorbeeld?adres=" + STATS).status_code in (302, 401, 403)  # het voorbeeld: inloggen


def test_ophalen_bewaart_de_pagina_en_valt_terug_op_de_vorige(monkeypatch):
    kiosk_webpagina._BEWAARD.clear()
    keren = []

    class Antwoord(io.BytesIO):
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *fout):
            return False

    class Opener:
        def open(self, verzoek, timeout):
            keren.append(verzoek.full_url)
            if len(keren) > 1:
                raise OSError("geen verbinding")
            return Antwoord(PAGINA.encode())

    monkeypatch.setattr(kiosk_webpagina.urllib.request, "build_opener", lambda *handlers: Opener())
    eerst = kiosk_webpagina.opgehaald(STATS, nu=0)
    assert ".panel.qr{display:none!important}" in eerst
    assert kiosk_webpagina.opgehaald(STATS, nu=10) == eerst and len(keren) == 1  # bewaard
    assert kiosk_webpagina.opgehaald(STATS, nu=10_000) == eerst and len(keren) == 2  # mislukt: de vorige
    assert kiosk_webpagina.opgehaald("https://example.com/", nu=0) is None
    kiosk_webpagina._BEWAARD.clear()
