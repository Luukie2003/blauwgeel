import shutil
import sys
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Het echte aantal hash-rondes (200.000, zie database.py) kost ~0,1 s per hash
# en elke test maakt er meerdere (seed-account, tablet-code, inloggen): dat was
# ruim de helft van de totale testtijd. De tests gaan over gedrag, niet over de
# sterkte van de hash, dus hier een lichte variant. Moet vóór de import van app
# gebeuren: de routes binden de waarde bij het importeren.
import database  # noqa: E402

database.WACHTWOORD_HASH_METHODE = "pbkdf2:sha256:1000"

from app import create_app  # noqa: E402
from database import WACHTWOORD_HASH_METHODE, get_db  # noqa: E402


def _maak_sjabloon_db(pad):
    """Bouwt de schone testdatabase: schema + seed-producten + seed-account."""
    # Vast wachtwoord i.p.v. het willekeurig gegenereerde standaardwachtwoord
    # (zie database.init_db) -- de hele testsuite logt in met dit account en
    # moet dus weten wat het wachtwoord is.
    flask_app = create_app(database_path=str(pad), admin_wachtwoord="kantine123")
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


@pytest.fixture(scope="session")
def sjabloon_db(tmp_path_factory):
    """De schone database wordt 1x per testrun opgebouwd (schema, migraties en
    seed-data kosten per keer tientallen ms) en daarna per test gekopieerd."""
    pad = tmp_path_factory.mktemp("sjabloon") / "sjabloon.db"
    _maak_sjabloon_db(pad)
    return pad


@pytest.fixture
def app(tmp_path, sjabloon_db):
    pad = tmp_path / "test.db"
    shutil.copyfile(sjabloon_db, pad)
    # Het schema zit al in de kopie: laat get_db() het niet opnieuw toepassen.
    database._SCHEMA_TOEGEPAST_VOOR.add(str(pad))
    flask_app = create_app(database_path=str(pad), admin_wachtwoord="kantine123")
    flask_app.config["TESTING"] = True
    # In productie staat dit standaard aan (de site draait altijd over https),
    # maar de testclient praat over http -- anders verstuurt de browser het
    # sessiecookie nooit terug en blijft elke request "uitgelogd".
    flask_app.config["SESSION_COOKIE_SECURE"] = False
    yield flask_app


@pytest.fixture(autouse=True)
def _voorspelling_zonder_bewaren(monkeypatch):
    """Elke test rekent de voorspelling echt uit (veel tests passen de gegevens aan en vragen daarna
    opnieuw). Het bewaren zelf wordt getest in tests/test_voorspelling_bewaren.py."""
    import voorspelling

    monkeypatch.setattr(voorspelling, "CACHE_AAN", False)
    voorspelling.wis_bewaarde_resultaten()


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
