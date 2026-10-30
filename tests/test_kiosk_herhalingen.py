"""Een dia vaker per ronde van de diashow laten zien: instelling, scherm en het verspreiden van de plekken."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import stel_csrf_token_in as _csrf

from helpers import KIOSK_MAX_HERHALINGEN

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "kiosk_scherm.html"


def _dia(db):
    return db.execute("SELECT * FROM kiosk_sponsoren ORDER BY id DESC").fetchone()


def _nieuw(client, **velden):
    data = {"csrf_token": _csrf(client), "sjabloon": "titel_tekst_groot", "titel": "Herhaald", "actief": "1", **velden}
    return client.post("/kiosk/sponsoren-leden/sponsoren/nieuw", data=data, follow_redirects=True)


# ---------- Instelling en scherm ----------


def test_standaard_komt_een_dia_een_keer_per_ronde(ingelogde_client, db):
    _nieuw(ingelogde_client)
    assert _dia(db)["herhalingen"] == 1


def test_herhalingen_opslaan_en_begrenzen(ingelogde_client, db):
    assert KIOSK_MAX_HERHALINGEN == 6
    for ingevuld, verwacht in (("3", 3), ("6", 6), ("99", 6), ("0", 1), ("-4", 1), ("", 1), ("abc", 1)):
        _nieuw(ingelogde_client, herhalingen=ingevuld)
        assert _dia(db)["herhalingen"] == verwacht, ingevuld

    dia = _dia(db)
    ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{dia['id']}/bewerken",
        data={"csrf_token": _csrf(ingelogde_client), "sjabloon": "titel_tekst_groot", "titel": "Herhaald", "herhalingen": "4"},
    )
    assert _dia(db)["herhalingen"] == 4


def test_het_formulier_en_de_lijst_tonen_het_aantal(ingelogde_client, db):
    assert 'name="herhalingen"' in ingelogde_client.get("/kiosk/sponsoren-leden/sponsoren/nieuw").data.decode()
    _nieuw(ingelogde_client, herhalingen="3")
    bewerken = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{_dia(db)['id']}/bewerken").data.decode()
    assert re.search(r'name="herhalingen"[^>]*value="3"', bewerken)
    assert "×3 per ronde" in ingelogde_client.get("/kiosk/sponsoren-leden").data.decode()


def test_het_scherm_krijgt_het_aantal_mee_alleen_als_het_meer_dan_een_is(ingelogde_client, client, db):
    _nieuw(ingelogde_client, titel="Een keer")
    _nieuw(ingelogde_client, titel="Drie keer", herhalingen="3")

    tekst = client.get("/kiosk/scherm").data.decode()

    assert tekst.count("data-herhaal=") == 1 and 'data-herhaal="3"' in tekst
    # Het blijft 1 dia in de pagina (dus bij een video 1x downloaden): de herhaling zit alleen in de volgorde.
    assert tekst.count("Drie keer") == 1


# ---------- Het verspreiden (het echte JavaScript, uitgevoerd met node) ----------


def _spreid(namen, herhaal):
    bron = re.search(r"function spreidDias\(basis, aantalVan\) \{.*?\n    \}\n", TEMPLATE.read_text(), re.S).group(0)
    script = bron + f"""
    var basis = {json.dumps(namen)}.map(function (n) {{ return {{ n: n }}; }});
    var herhaal = {json.dumps(herhaal)};
    console.log(JSON.stringify(spreidDias(basis, function (s) {{ return herhaal[s.n] || 1; }}).map(function (x) {{ return x.n; }})));
    """
    uit = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(uit.stdout)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node niet beschikbaar")


@needs_node
def test_zonder_herhalingen_blijft_de_volgorde_zoals_ze_was():
    namen = list("ABCDEFGHIJKLMN")
    assert _spreid(namen, {}) == namen


@needs_node
def test_een_dia_drie_keer_staat_gelijkmatig_verspreid_en_de_rest_blijft_in_volgorde():
    namen = list("ABCDEFGHIJKLMN")
    lijst = _spreid(namen, {"A": 3})

    assert len(lijst) == 16 and lijst[0] == "A"
    assert [n for n in lijst if n != "A"] == namen[1:]  # de andere dia's in dezelfde volgorde
    plekken = [i for i, n in enumerate(lijst) if n == "A"]
    afstanden = [(plekken[(i + 1) % 3] - p) % len(lijst) for i, p in enumerate(plekken)]
    assert sorted(afstanden) == [5, 5, 6]  # ongeveer elke 5-6 dia's


@needs_node
def test_meerdere_dia_s_met_herhaling_en_nooit_dezelfde_dia_achter_elkaar():
    namen = list("ABCDEFGHIJKLMN")
    lijst = _spreid(namen, {"A": 2, "H": 4, "C": 6})  # 6 past nog net binnen de grens: hooguit de helft van de dia's (7)

    assert lijst.count("A") == 2 and lijst.count("H") == 4 and lijst.count("C") == 6
    assert all(lijst[i] != lijst[(i + 1) % len(lijst)] for i in range(len(lijst)))


@needs_node
def test_met_weinig_dia_s_wordt_het_aantal_begrensd():
    assert _spreid(["A", "B"], {"A": 6}) == ["A", "B"]  # anders zou A direct na zichzelf komen
    assert _spreid(["A", "B", "C", "D"], {"A": 6}).count("A") == 2
    assert _spreid(["A"], {"A": 3}) == ["A"]
