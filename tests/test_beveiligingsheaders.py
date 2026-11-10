"""De beveiligingsheaders die op elke pagina staan (zie beveiligingsheaders in app.py)."""


def test_de_browser_onthoudt_dat_de_site_alleen_via_https_bestaat(client):
    # Zonder includeSubDomains: kantineblauwgeel.nl zonder www staat bij STRATO, niet bij deze site.
    assert client.get("/login").headers["Strict-Transport-Security"] == "max-age=31536000"


def test_ook_op_de_openbare_schermen(client):
    assert client.get("/status").headers["Strict-Transport-Security"] == "max-age=31536000"
