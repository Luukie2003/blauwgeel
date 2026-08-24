def test_post_zonder_csrf_token_wordt_geweigerd(client):
    resp = client.post("/login", data={"naam": "admin", "wachtwoord": "kantine123"})
    assert resp.status_code == 400


def test_post_met_verkeerd_csrf_token_wordt_geweigerd(client, csrf):
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": "onzin-token"},
    )
    assert resp.status_code == 400


def test_login_met_juiste_gegevens_werkt(client, csrf):
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": csrf},
    )
    assert resp.status_code == 302


def test_login_met_verkeerd_wachtwoord_faalt_zonder_lockout(client, csrf):
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "fout", "csrf_token": csrf},
    )
    assert resp.status_code == 200
    assert "Onjuiste naam of wachtwoord".encode() in resp.data


def test_login_wordt_geblokkeerd_na_vijf_mislukte_pogingen(client, csrf):
    for _ in range(5):
        client.post(
            "/login", data={"naam": "admin", "wachtwoord": "fout", "csrf_token": csrf}
        )
    # Zelfs met het juiste wachtwoord blijft de 6e poging geblokkeerd.
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": csrf},
    )
    assert resp.status_code == 200
    assert "Te veel mislukte inlogpogingen".encode() in resp.data


def test_succesvolle_login_reset_de_teller(client, csrf):
    for _ in range(3):
        client.post(
            "/login", data={"naam": "admin", "wachtwoord": "fout", "csrf_token": csrf}
        )
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": csrf},
    )
    assert resp.status_code == 302  # nog niet geblokkeerd, dus login lukt gewoon


def test_niet_ingelogd_wordt_naar_login_gestuurd(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
