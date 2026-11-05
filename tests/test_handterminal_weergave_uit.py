"""De handterminal-weergave van de site staat tijdelijk uit (HANDTERMINAL_WEERGAVE, zie create_app): op de Zebra werkt
de app, en een telefoon krijgt de gewone site. De andere tests zetten hem aan (conftest) zodat de code blijft werken."""

import pytest

from app import create_app

TELEFOON_UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"


def test_staat_standaard_uit(tmp_path):
    app = create_app(database_path=str(tmp_path / "x.db"), admin_wachtwoord="x")
    assert app.config["HANDTERMINAL_WEERGAVE"] is False


@pytest.fixture
def uit(app):
    app.config["HANDTERMINAL_WEERGAVE"] = False


def test_telefoon_krijgt_de_gewone_site(uit, ingelogde_client):
    tekst = ingelogde_client.get("/", headers={"User-Agent": TELEFOON_UA}).data.decode()
    assert 'class="app-zijbalk' in tekst and "pda-kop-menuknop" not in tekst
    assert "Naar handterminal-weergave" not in tekst


def test_oud_cookie_en_de_knop_doen_niets(uit, ingelogde_client):
    ingelogde_client.set_cookie("weergave", "pda")  # een telefoon die eerder de handterminal-weergave koos
    assert "pda-kop-menuknop" not in ingelogde_client.get("/").data.decode()

    resp = ingelogde_client.get("/weergave/pda", follow_redirects=True)
    tekst = resp.data.decode()
    assert "staat tijdelijk uit" in tekst and "pda-kop-menuknop" not in tekst
    assert not any(c.startswith("weergave=pda") for c in resp.headers.getlist("Set-Cookie"))


def test_geen_weergave_cookie_meer_bij_een_eerste_bezoek(uit, client):
    """Zo wordt een telefoon nog herkend als de handterminal-weergave weer aangaat."""
    resp = client.get("/login", headers={"User-Agent": TELEFOON_UA})
    assert not any(c.startswith("weergave=") for c in resp.headers.getlist("Set-Cookie"))
