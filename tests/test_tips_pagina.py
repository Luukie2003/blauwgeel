def test_tips_pagina_geeft_200(ingelogde_client):
    resp = ingelogde_client.get("/tips")
    assert resp.status_code == 200
    assert "Tips".encode() in resp.data
    assert "Kiosk-sjabloonbouwer".encode() in resp.data


def test_tips_pagina_vereist_login(client):
    resp = client.get("/tips")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_footer_bevat_link_naar_tips_pagina(ingelogde_client):
    resp = ingelogde_client.get("/")
    assert resp.status_code == 200
    assert 'href="/tips"'.encode() in resp.data
