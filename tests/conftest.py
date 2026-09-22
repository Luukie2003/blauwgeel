import sys
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from database import WACHTWOORD_HASH_METHODE, get_db  # noqa: E402


@pytest.fixture
def app(tmp_path):
    flask_app = create_app(database_path=str(tmp_path / "test.db"))
    flask_app.config["TESTING"] = True
    # In productie staat dit standaard aan (de site draait altijd over https),
    # maar de testclient praat over http -- anders verstuurt de browser het
    # sessiecookie nooit terug en blijft elke request "uitgelogd".
    flask_app.config["SESSION_COOKIE_SECURE"] = False
    with flask_app.app_context():
        # tablet_code_hash IS NULL dwingt (zie vereis_login in app.py) elk
        # account naar de instelpagina voor de tablet-code -- zonder dit zou
        # vrijwel elke test die een account aanmaakt/inlogt daarop vastlopen,
        # terwijl geen van die tests over deze functie gaat. Vult 'm hier
        # 1x voor het seed-account, en met een trigger voor elk account dat
        # een test hierna zelf aanmaakt. Een test die de instelpagina zelf
        # wil testen, zet 'm voor zijn eigen testgebruiker expliciet terug op
        # NULL.
        db = get_db()
        test_hash = generate_password_hash("999999", method=WACHTWOORD_HASH_METHODE)
        db.execute(
            "UPDATE gebruikers SET tablet_code_hash = ? WHERE tablet_code_hash IS NULL",
            (test_hash,),
        )
        db.execute(
            f"""CREATE TRIGGER IF NOT EXISTS test_auto_tablet_code
                AFTER INSERT ON gebruikers
                WHEN NEW.tablet_code_hash IS NULL
                BEGIN
                    UPDATE gebruikers SET tablet_code_hash = '{test_hash}' WHERE id = NEW.id;
                END"""
        )
        db.commit()
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    with app.app_context():
        yield get_db()


FIXED_CSRF_TOKEN = "test-csrf-token"


def stel_csrf_token_in(client):
    """Zet het csrf_token direct in de sessie i.p.v. te wachten tot een
    template 'm via de context_processor aanmaakt -- niet elke pagina
    rendert een formulier, en inloggen wist de sessie (dus ook een eerder
    gezet token) weer. Werkt omdat csrf_beschermen() alleen vergelijkt of
    het formulierveld overeenkomt met wat er in de sessie staat."""
    with client.session_transaction() as sess:
        sess["csrf_token"] = FIXED_CSRF_TOKEN
    return FIXED_CSRF_TOKEN


@pytest.fixture
def csrf(client):
    return stel_csrf_token_in(client)


@pytest.fixture
def ingelogde_client(client, csrf):
    resp = client.post(
        "/login",
        data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": csrf},
    )
    assert resp.status_code == 302, "seed-login voor tests is mislukt"
    return client
