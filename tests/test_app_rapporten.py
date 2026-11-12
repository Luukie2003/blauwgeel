"""De rapporten in de app (2.11.0, routes/app_api_rapporten.py): elk rapport in dezelfde vorm voor het rapportscherm van de
app, met de periodekeuze, en met dezelfde rechten als de pagina op de site."""

import pytest
from test_app_api import app_client  # noqa: F401 (fixture)
from test_secties_rechten import _login, _maak_vrijwilliger

ALLE = ("verkoop", "week", "seizoenen", "seizoen-in-cijfers", "marge", "derving", "niet-lopers", "bardiensten")
BEHEERDER = ("marge", "derving", "niet-lopers", "bardiensten")


def _controleer_vorm(rapport):
    assert rapport["titel"] and isinstance(rapport["keuzes"], list) and rapport["delen"]
    for deel in rapport["delen"]:
        assert deel["soort"] in ("cijfers", "lijst", "tekst"), deel
        if deel["soort"] == "cijfers":
            assert all({"waarde", "label"} <= set(c) for c in deel["cijfers"])
        if deel["soort"] == "lijst":
            assert deel["leeg"] and all(r["titel"] is not None for r in deel["regels"])


@pytest.mark.parametrize("rapport", ALLE)
def test_elk_rapport_in_de_vorm_van_de_app(app_client, rapport):  # noqa: F811
    resp = app_client.get(f"/api/app/rapporten/{rapport}")
    assert resp.status_code == 200, resp.data[:200]
    _controleer_vorm(resp.get_json())


def test_de_periode_kiezen(app_client, db):  # noqa: F811
    keuzes = app_client.get("/api/app/rapporten/verkoop?keuze=90").get_json()["keuzes"]
    assert [k["sleutel"] for k in keuzes if k["actief"]] == ["90"]
    assert [k["sleutel"] for k in app_client.get("/api/app/rapporten/verkoop?keuze=onzin").get_json()["keuzes"] if k["actief"]] == ["30"]
    marge = app_client.get("/api/app/rapporten/marge?keuze=26").get_json()
    assert [k["sleutel"] for k in marge["keuzes"] if k["actief"]] == ["26"]


def test_verkoop_met_een_telling(app_client, db):  # noqa: F811
    from test_bestelvoorstel import _product

    _product(db, "Cola Rapport", voorraad=10)
    rapport = app_client.get("/api/app/rapporten/verkoop?keuze=365").get_json()
    kop = rapport["delen"][0]
    assert kop["soort"] == "cijfers" and kop["cijfers"][0]["label"] == "omzet" and kop["cijfers"][0]["waarde"].startswith("€")


def test_de_beheerderrapporten_alleen_voor_beheerders(client, db):
    _maak_vrijwilliger(db, "rapport_vrijwilliger", "voorraad")
    _login(client, "rapport_vrijwilliger")
    assert client.get("/api/app/rapporten/verkoop").status_code == 200
    assert client.get("/api/app/rapporten/seizoen-in-cijfers").status_code == 200
    for rapport in BEHEERDER:
        assert client.get(f"/api/app/rapporten/{rapport}").status_code in (302, 403), rapport
