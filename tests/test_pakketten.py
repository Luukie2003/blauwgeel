import os
from importlib import metadata
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

MAP = Path(__file__).resolve().parent.parent


def _regels(bestand):
    return [
        r.strip()
        for r in (MAP / bestand).read_text().splitlines()
        if r.strip() and not r.strip().startswith(("#", "-r"))
    ]


def _vastgezet():
    pins = {}
    for regel in _regels("requirements-vast.txt"):
        assert "==" in regel and ">" not in regel, f"alleen exacte versies in requirements-vast.txt: {regel}"
        naam, versie = regel.split("==")
        pins[canonicalize_name(naam)] = versie
    return pins


def test_vastgezette_versies_voldoen_aan_de_minimumversies():
    """Dependabot of een mens verhoogt een minimum in requirements.txt: dan moet requirements-vast.txt
    (bash scripts/leg_pakketten_vast.sh) mee."""
    pins = _vastgezet()
    for regel in _regels("requirements.txt"):
        eis = Requirement(regel)
        naam = canonicalize_name(eis.name)
        assert naam in pins, f"{eis.name} ontbreekt in requirements-vast.txt"
        assert eis.specifier.contains(pins[naam]), f"{eis.name}: vastgezet {pins[naam]} voldoet niet aan {eis.specifier}"


def test_dev_omgeving_bouwt_voort_op_de_vastgezette_versies():
    assert "-r requirements-vast.txt" in (MAP / "requirements-dev.txt").read_text()


@pytest.mark.skipif(not os.environ.get("CI"), reason="alleen in de CI: lokaal mag je een andere versie hebben")
def test_in_de_ci_draaien_de_tests_op_precies_de_vastgezette_versies():
    """Zo testen we wat er ook echt op de server komt."""
    for naam, versie in _vastgezet().items():
        assert metadata.version(naam) == versie, f"{naam}: geïnstalleerd {metadata.version(naam)}, vastgezet {versie}"
