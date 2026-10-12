"""Het modulenoverzicht met vermoedelijke versienummers bovenaan het versielogboek (Help-pagina)."""

import re

from navigatie import NAV_GROEP_VOLGORDE
from wijzigingen import HUIDIGE_VERSIE, MODULES, WIJZIGINGEN


def _versie(tekst):
    return tuple(int(deel) for deel in tekst.split("."))


def test_de_huidige_versie_is_de_nieuwste_in_het_logboek():
    versies = [r["versie"] for r in WIJZIGINGEN]
    assert versies[0] == HUIDIGE_VERSIE
    assert versies == sorted(versies, key=_versie, reverse=True) and len(set(versies)) == len(versies)


def test_elke_module_heeft_een_geldig_versienummer_en_bestaande_versies_erbij():
    versies = {r["versie"] for r in WIJZIGINGEN}
    namen = [m["naam"] for m in MODULES]
    assert len(set(namen)) == len(namen)
    for m in MODULES:
        assert re.fullmatch(r"\d+\.\d+\.\d+", m["versie"]), m
        assert m["inhoud"], m
        for veld in ("sinds", "laatst"):
            assert m[veld] == "" or m[veld] in versies, f"{m['naam']}: {veld} {m[veld]!r} staat niet in het logboek"
        if m["sinds"] and m["laatst"]:
            assert _versie(m["sinds"]) <= _versie(m["laatst"]) <= _versie(HUIDIGE_VERSIE), m


def test_een_nieuwe_module_heeft_hoofdnummer_0():
    taken = next(m for m in MODULES if m["naam"] == "Taken")
    assert taken["versie"].startswith("0.") and taken["sinds"] == "1.43.0"


def test_elke_menugroep_komt_in_het_overzicht_voor():
    """Komt er een nieuwe groep in het menu, dan hoort die ook een module te krijgen (zie CLAUDE.md)."""
    sleutel = {"Start": "Overzicht", "Beheer": "beheer"}
    namen = " | ".join(m["naam"] for m in MODULES).lower()
    for groep in NAV_GROEP_VOLGORDE:
        assert sleutel.get(groep, groep).lower() in namen, f"geen module voor menugroep {groep!r}"


def test_de_helppagina_toont_het_overzicht_boven_de_versies(ingelogde_client):
    tekst = ingelogde_client.get("/help").data.decode()
    assert "Modules en hun vermoedelijke versie" in tekst and "schatting op basis van dit logboek" in tekst
    for m in MODULES:
        assert m["naam"].replace("&", "&amp;") in tekst and m["versie"] in tekst
    assert tekst.index("Modules en hun vermoedelijke versie") < tekst.index(f"Versie {HUIDIGE_VERSIE}")
    assert "Wat er per versie is veranderd" in tekst
