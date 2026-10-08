import re

from werkzeug.security import generate_password_hash

from conftest import stel_csrf_token_in as _csrf
from database import WACHTWOORD_HASH_METHODE
from navigatie import NAV_GROEP_ICOON, NAV_GROEP_VOLGORDE, NAV_ITEMS


def _menu(html):
    """{groepsnaam: [labels]} uit de zijbalk van een pagina."""
    zijbalk = html.split('id="app-zijbalk"')[1].split("</nav>")[0]
    uit = {}
    for groep in re.split(r'<div class="zijbalk-groep"', zijbalk)[1:]:
        naam = re.search(r'data-groep="([^"]+)"', groep).group(1)
        uit[naam] = [re.sub(r"<[^>]+>|\s+", " ", l).strip() for l in re.findall(r"<a [^>]*>(.*?)</a>", groep, flags=re.S)]
    return uit


def _inloggen(client, db, secties, rol="vrijwilliger"):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) VALUES ('tester', ?, ?, ?, '2026-01-01 10:00')",
        (generate_password_hash("geheim123", method=WACHTWOORD_HASH_METHODE), rol, secties),
    )
    db.commit()
    client.post("/login", data={"naam": "tester", "wachtwoord": "geheim123", "csrf_token": _csrf(client)})


def test_elke_groep_heeft_een_pictogram_en_een_plek_in_de_volgorde():
    for item in NAV_ITEMS:
        assert item["groep"] in NAV_GROEP_VOLGORDE and item["groep"] in NAV_GROEP_ICOON, item["groep"]


def test_menu_heeft_elf_onderdelen_in_de_afgesproken_volgorde(ingelogde_client):
    menu = _menu(ingelogde_client.get("/").data.decode())
    assert list(menu) == NAV_GROEP_VOLGORDE
    assert len(menu) == 11


def test_kassa_en_kluis_zitten_samen_onder_geld(ingelogde_client):
    geld = _menu(ingelogde_client.get("/").data.decode())["Geld"]
    assert geld == [
        "Kassa tellen", "Kassa geschiedenis", "Afdracht / toevoeging",
        "Kluis tellen", "Kluis geschiedenis", "Storting / opname",
    ]


def test_vrijwilliger_met_kassa_ziet_de_kassa_maar_niet_de_kluis(client, db):
    _inloggen(client, db, "kassa")
    menu = _menu(client.get("/").data.decode())
    assert menu["Geld"] == ["Kassa tellen", "Kassa geschiedenis", "Afdracht / toevoeging"]
    assert "Voorraad" not in menu and "Beheer" not in menu and "Keuken" not in menu
    assert "Start" in menu and "Rapporten" in menu  # voor iedereen


def test_vrijwilliger_met_alleen_voorraad_heeft_geen_geld_en_geen_bardienstrapport(client, db):
    _inloggen(client, db, "voorraad")
    menu = _menu(client.get("/").data.decode())
    assert "Geld" not in menu
    assert menu["Voorraad"] == ["Voorraadoverzicht", "In/uit boeken", "Mutatieoverzicht", "Voorraad tellen", "Tellingen"]
    assert "Omzet per bardienst" not in menu["Rapporten"]


def test_club_instellingen_is_delegeerbaar_zonder_de_rest_van_beheer(client, db):
    _inloggen(client, db, "club")
    assert _menu(client.get("/").data.decode())["Beheer"] == ["Club instellingen"]


def test_menu_klapt_in_als_accordeon_via_javascript():
    js = open("static/gedeeld.js").read()
    assert "één groep tegelijk open" in js
    assert 'andere === groep && openen' in js  # alle andere groepen dicht, deze open
    assert "zijbalk-open-groepen" in js  # de oude opgeslagen voorkeur wordt opgeruimd
