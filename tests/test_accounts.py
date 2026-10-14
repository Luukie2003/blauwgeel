from werkzeug.security import generate_password_hash

from database import WACHTWOORD_HASH_METHODE

from conftest import stel_csrf_token_in as _csrf


def _maak_tweede_beheerder(db):
    db.execute(
        """INSERT INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op)
           VALUES ('tweede', 'onbruikbaar', 'beheerder', '2026-01-01 10:00')"""
    )
    db.commit()
    return db.execute("SELECT id FROM gebruikers WHERE naam = 'tweede'").fetchone()["id"]


def _maak_vrijwilliger(db, naam="vrijwilliger", wachtwoord="test1234"):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op) "
        "VALUES (?, ?, 'vrijwilliger', '2026-01-01 10:00')",
        (naam, generate_password_hash(wachtwoord, method=WACHTWOORD_HASH_METHODE)),
    )
    db.commit()
    return db.execute("SELECT id FROM gebruikers WHERE naam = ?", (naam,)).fetchone()["id"]


def test_verwijderen_van_account_met_boekingsgeschiedenis_geeft_nette_foutmelding(
    ingelogde_client, db
):
    """mutaties.gebruiker_id heeft bewust geen ON DELETE CASCADE (die
    geschiedenis mag nooit stilzwijgend verdwijnen) -- verwijderen van zo'n
    account moet dus netjes geweigerd worden i.p.v. een 500
    (sqlite3.IntegrityError)."""
    gebruiker_id = _maak_tweede_beheerder(db)
    product = db.execute("SELECT id FROM producten LIMIT 1").fetchone()
    db.execute(
        "INSERT INTO mutaties (product_id, type, aantal, datum, gebruiker_id) "
        "VALUES (?, 'in', 1, '2026-01-01', ?)",
        (product["id"], gebruiker_id),
    )
    db.commit()

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    nog_aanwezig = db.execute(
        "SELECT id FROM gebruikers WHERE id = ?", (gebruiker_id,)
    ).fetchone()
    assert nog_aanwezig is not None

    vervolg = ingelogde_client.get(resp.headers["Location"])
    assert "kan niet verwijderd worden" in vervolg.data.decode()


def test_verwijderen_van_account_met_bestelgeschiedenis_geeft_nette_foutmelding(
    ingelogde_client, db
):
    gebruiker_id = _maak_tweede_beheerder(db)
    db.execute(
        "INSERT INTO bestellingen (status, aangemaakt_op, besteld_door_id) "
        "VALUES ('besteld', '2026-01-01 10:00', ?)",
        (gebruiker_id,),
    )
    db.commit()

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    nog_aanwezig = db.execute(
        "SELECT id FROM gebruikers WHERE id = ?", (gebruiker_id,)
    ).fetchone()
    assert nog_aanwezig is not None


def test_verwijderen_van_account_zonder_geschiedenis_werkt_nog_gewoon(ingelogde_client, db):
    gebruiker_id = _maak_tweede_beheerder(db)

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    weg = db.execute("SELECT id FROM gebruikers WHERE id = ?", (gebruiker_id,)).fetchone()
    assert weg is None


# ---------- Account blokkeren/deblokkeren ----------


def test_beheerder_kan_account_blokkeren_en_deblokkeren(ingelogde_client, db):
    gebruiker_id = _maak_vrijwilliger(db, "blokkeerbaar")

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/actief", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert db.execute(
        "SELECT actief FROM gebruikers WHERE id = ?", (gebruiker_id,)
    ).fetchone()["actief"] == 0

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/actief", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert db.execute(
        "SELECT actief FROM gebruikers WHERE id = ?", (gebruiker_id,)
    ).fetchone()["actief"] == 1


def test_geblokkeerd_account_kan_niet_inloggen(client, db):
    gebruiker_id = _maak_vrijwilliger(db, "wordt_geblokkeerd")
    db.execute("UPDATE gebruikers SET actief = 0 WHERE id = ?", (gebruiker_id,))
    db.commit()

    csrf = _csrf(client)
    resp = client.post(
        "/login",
        data={"naam": "wordt_geblokkeerd", "wachtwoord": "test1234", "csrf_token": csrf},
    )
    assert resp.status_code == 200
    assert b"geblokkeerd" in resp.data
    # Niet daadwerkelijk ingelogd: een pagina die login vereist stuurt terug
    # naar /login i.p.v. 'm te tonen.
    vervolg = client.get("/", follow_redirects=True)
    assert vervolg.request.path == "/login"


def test_lopende_sessie_van_geblokkeerd_account_wordt_meteen_geweerd(client, db):
    """actief wordt elke request opnieuw gecheckt (zie vereis_login) --
    blokkeren tijdens een lopende sessie moet dus direct effect hebben,
    zonder dat diegene eerst moet uitloggen."""
    gebruiker_id = _maak_vrijwilliger(db, "actieve_sessie")
    csrf = _csrf(client)
    resp = client.post(
        "/login", data={"naam": "actieve_sessie", "wachtwoord": "test1234", "csrf_token": csrf}
    )
    assert resp.status_code == 302

    resp = client.get("/")
    assert resp.status_code == 200

    db.execute("UPDATE gebruikers SET actief = 0 WHERE id = ?", (gebruiker_id,))
    db.commit()

    resp = client.get("/", follow_redirects=True)
    assert resp.request.path == "/login"
    assert b"geblokkeerd" in resp.data


def test_kan_eigen_account_niet_blokkeren(ingelogde_client, db):
    admin = db.execute("SELECT id FROM gebruikers WHERE naam = 'admin'").fetchone()
    resp = ingelogde_client.post(
        f"/accounts/{admin['id']}/actief",
        data={"csrf_token": _csrf(ingelogde_client)},
        follow_redirects=True,
    )
    assert b"niet blokkeren" in resp.data
    assert db.execute(
        "SELECT actief FROM gebruikers WHERE id = ?", (admin["id"],)
    ).fetchone()["actief"] == 1


def test_blokkeren_van_andere_beheerder_mag_als_er_nog_een_actieve_overblijft(ingelogde_client, db):
    tweede_id = _maak_tweede_beheerder(db)
    resp = ingelogde_client.post(
        f"/accounts/{tweede_id}/actief", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert db.execute(
        "SELECT actief FROM gebruikers WHERE id = ?", (tweede_id,)
    ).fetchone()["actief"] == 0


def test_geblokkeerde_beheerder_telt_niet_mee_voor_rol_wijzigen_guard(ingelogde_client, db):
    tweede_id = _maak_tweede_beheerder(db)
    db.execute("UPDATE gebruikers SET actief = 0 WHERE id = ?", (tweede_id,))
    db.commit()

    # 'tweede' is beheerder maar geblokkeerd -- demoten mag altijd, dat raakt
    # de actieve-beheerdersteller niet (die stond al op 1: alleen admin).
    resp = ingelogde_client.post(
        f"/accounts/{tweede_id}/rol", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert db.execute(
        "SELECT rol FROM gebruikers WHERE id = ?", (tweede_id,)
    ).fetchone()["rol"] == "vrijwilliger"


def test_geblokkeerde_beheerder_kan_altijd_verwijderd_worden(ingelogde_client, db):
    tweede_id = _maak_tweede_beheerder(db)
    db.execute("UPDATE gebruikers SET actief = 0 WHERE id = ?", (tweede_id,))
    db.commit()

    resp = ingelogde_client.post(
        f"/accounts/{tweede_id}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert db.execute("SELECT id FROM gebruikers WHERE id = ?", (tweede_id,)).fetchone() is None


def test_geblokkeerd_account_kan_wachtwoord_link_niet_meer_gebruiken(client, db):
    from helpers import genereer_wachtwoord_token

    gebruiker_id = _maak_vrijwilliger(db, "link_geblokkeerd")
    token = genereer_wachtwoord_token(db, gebruiker_id, geldig_uren=24)
    db.execute("UPDATE gebruikers SET actief = 0 WHERE id = ?", (gebruiker_id,))
    db.commit()

    resp = client.get(f"/wachtwoord-instellen/{token}", follow_redirects=True)
    assert b"geblokkeerd" in resp.data
    assert resp.request.path == "/login"


# ---------- Wachtwoord-link (opnieuw) versturen ----------


def test_wachtwoord_link_versturen_genereert_geldig_token(ingelogde_client, db):
    gebruiker_id = _maak_vrijwilliger(db, "krijgt_link")
    db.execute("UPDATE gebruikers SET email = 'link@test.nl' WHERE id = ?", (gebruiker_id,))
    db.commit()

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/wachtwoord-link",
        data={"csrf_token": _csrf(ingelogde_client)},
        follow_redirects=True,
    )
    assert b"verstuurd" in resp.data
    bijgewerkt = db.execute(
        "SELECT reset_token_hash, reset_token_verloopt FROM gebruikers WHERE id = ?",
        (gebruiker_id,),
    ).fetchone()
    assert bijgewerkt["reset_token_hash"] is not None
    assert bijgewerkt["reset_token_verloopt"] is not None


def test_wachtwoord_link_versturen_zonder_email_geeft_foutmelding(ingelogde_client, db):
    gebruiker_id = _maak_vrijwilliger(db, "geen_email")

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/wachtwoord-link",
        data={"csrf_token": _csrf(ingelogde_client)},
        follow_redirects=True,
    )
    assert b"e-mailadres" in resp.data
    assert db.execute(
        "SELECT reset_token_hash FROM gebruikers WHERE id = ?", (gebruiker_id,)
    ).fetchone()["reset_token_hash"] is None


# ---------- Laatst actief ----------


def test_laatst_actief_leesbaar():
    from datetime import datetime

    from helpers import format_laatst_actief

    nu = datetime(2026, 10, 14, 15, 0)
    assert format_laatst_actief("2026-10-14 09:05", nu) == "vandaag 09:05"
    assert format_laatst_actief("2026-10-13 21:40", nu) == "gisteren 21:40"
    assert format_laatst_actief("2026-10-10 12:00", nu) == "4 dagen geleden"
    assert format_laatst_actief("2026-09-01 12:00", nu) == "01-09-2026"
    assert format_laatst_actief(None, nu) == ""


def test_accounts_toont_de_laatste_activiteit_in_plaats_van_de_laatste_inlog(ingelogde_client, db):
    """Wie ingelogd blijft, logt niet opnieuw in: het laatste paginabezoek zegt meer dan de laatste inlog."""
    gebruiker_id = _maak_vrijwilliger(db, "blijftingelogd")
    db.execute("UPDATE gebruikers SET laatste_login = '2026-08-01 10:00' WHERE id = ?", (gebruiker_id,))
    db.execute(
        "INSERT INTO paginabezoeken (endpoint, gebruiker_id, weergave_modus, datum) VALUES ('dashboard', ?, 'desktop', '2026-10-12 19:30')",
        (gebruiker_id,),
    )
    _maak_vrijwilliger(db, "nooitgeweest")
    db.commit()

    tekst = ingelogde_client.get("/accounts").data.decode()
    assert "laatst actief op 12-10-2026 19:30" in tekst
    assert "laatst ingelogd op 01-08-2026 10:00" in tekst
    assert "Nog nooit ingelogd" in tekst


def test_zonder_paginabezoek_telt_de_laatste_inlog(ingelogde_client, db):
    gebruiker_id = _maak_vrijwilliger(db, "alleeningelogd")
    db.execute("UPDATE gebruikers SET laatste_login = '2026-09-20 08:15' WHERE id = ?", (gebruiker_id,))
    db.commit()
    assert "laatst actief op 20-09-2026 08:15" in ingelogde_client.get("/accounts").data.decode()
