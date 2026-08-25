from conftest import stel_csrf_token_in as _csrf


def _plaats_mededeling(client, tekst="Tapkraan lekt", urgent=False):
    data = {"csrf_token": _csrf(client), "tekst": tekst}
    if urgent:
        data["urgent"] = "on"
    resp = client.post("/bijzonderheden", data=data, follow_redirects=False)
    assert resp.status_code == 302


def test_mededeling_plaatsen_en_urgent_vlag(ingelogde_client, db):
    _plaats_mededeling(ingelogde_client, tekst="Bierfust bijna leeg", urgent=True)
    m = db.execute("SELECT * FROM mededelingen ORDER BY id DESC LIMIT 1").fetchone()
    assert m["tekst"] == "Bierfust bijna leeg"
    assert m["urgent"] == 1
    assert m["afgehandeld"] == 0


def test_afhandelen_bewaart_wie_en_wanneer(ingelogde_client, db):
    _plaats_mededeling(ingelogde_client)
    m = db.execute("SELECT * FROM mededelingen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.post(
        f"/bijzonderheden/{m['id']}/afhandelen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302

    m = db.execute("SELECT * FROM mededelingen WHERE id = ?", (m["id"],)).fetchone()
    assert m["afgehandeld"] == 1
    assert m["afgehandeld_door"] == "admin"
    assert m["afgehandeld_op"] is not None


def test_heropenen_maakt_afgehandelde_mededeling_weer_open(ingelogde_client, db):
    _plaats_mededeling(ingelogde_client)
    m = db.execute("SELECT * FROM mededelingen ORDER BY id DESC LIMIT 1").fetchone()
    token = _csrf(ingelogde_client)
    ingelogde_client.post(f"/bijzonderheden/{m['id']}/afhandelen", data={"csrf_token": token})

    ingelogde_client.post(f"/bijzonderheden/{m['id']}/heropenen", data={"csrf_token": token})
    m = db.execute("SELECT * FROM mededelingen WHERE id = ?", (m["id"],)).fetchone()
    assert m["afgehandeld"] == 0
    assert m["afgehandeld_door"] is None
    assert m["afgehandeld_op"] is None


def test_afgehandelde_mededelingen_staan_onderaan(ingelogde_client, db):
    _plaats_mededeling(ingelogde_client, tekst="Eerst geplaatst")
    eerste = db.execute("SELECT * FROM mededelingen ORDER BY id DESC LIMIT 1").fetchone()
    token = _csrf(ingelogde_client)
    ingelogde_client.post(f"/bijzonderheden/{eerste['id']}/afhandelen", data={"csrf_token": token})

    _plaats_mededeling(ingelogde_client, tekst="Later geplaatst, nog open")

    resp = ingelogde_client.get("/bijzonderheden")
    tekst = resp.data.decode()
    assert tekst.index("Later geplaatst, nog open") < tekst.index("Eerst geplaatst")


def test_pin_als_banner_zet_instellingen_banner(ingelogde_client, db):
    _plaats_mededeling(ingelogde_client, tekst="Kantine dit weekend dicht")
    m = db.execute("SELECT * FROM mededelingen ORDER BY id DESC LIMIT 1").fetchone()

    resp = ingelogde_client.post(
        f"/bijzonderheden/{m['id']}/pin-als-banner", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302

    instelling = db.execute("SELECT banner_tekst FROM instellingen WHERE id = 1").fetchone()
    assert instelling["banner_tekst"] == "Kantine dit weekend dicht"


def test_vrijwilliger_mag_niet_pinnen_als_banner(client, db, csrf):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op) "
        "VALUES ('vrijwilliger1', 'x', 'vrijwilliger', '2026-01-01 10:00')"
    )
    db.execute(
        "INSERT INTO mededelingen (tekst, naam, datum) VALUES ('Test', 'vrijwilliger1', '2026-01-01 10:00')"
    )
    db.commit()
    gebruiker = db.execute("SELECT * FROM gebruikers WHERE naam = 'vrijwilliger1'").fetchone()
    mededeling = db.execute("SELECT * FROM mededelingen ORDER BY id DESC LIMIT 1").fetchone()
    with client.session_transaction() as sess:
        sess["gebruiker_id"] = gebruiker["id"]
        sess["gebruiker_naam"] = "vrijwilliger1"
        sess["gebruiker_rol"] = "vrijwilliger"
        sess["csrf_token"] = csrf

    resp = client.post(
        f"/bijzonderheden/{mededeling['id']}/pin-als-banner", data={"csrf_token": csrf}
    )
    assert resp.status_code == 302  # geweerd, terug naar dashboard
    instelling = db.execute("SELECT banner_tekst FROM instellingen WHERE id = 1").fetchone()
    assert instelling["banner_tekst"] is None
