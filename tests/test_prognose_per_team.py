"""De prognose leert per team hoeveel drukker (of rustiger) een thuiswedstrijd van dat team is dan een gemiddelde
thuiswedstrijd (zie voorspelling/basis.py, TEAM_PREFIX)."""

from datetime import timedelta

from test_voorspelling import MAANDAG, _bouw_geschiedenis, _effect, _product, _twee_keer_per_week, _zaterdagen

from voorspelling import blootstelling, lees_kalender, maak_prognose, team_sleutel

HEREN, JEUGD = "Blauw Geel'15 1", "Blauw Geel'15 JO19-1"


def _thuis(db, dag, team):
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES (?, ?, ?, 1)",
        (team, dag.isoformat(), f"{team} - Tegenstander {dag}"),
    )
    db.commit()


def test_kalender_en_blootstelling_kennen_de_teams(db):
    zaterdag = (MAANDAG + timedelta(days=5)).date()
    _thuis(db, zaterdag, HEREN)
    _thuis(db, zaterdag, JEUGD)
    db.execute("UPDATE instellingen SET verkoopdagen = '0,1,2,3,4,5,6' WHERE id = 1")
    db.commit()
    kalender = lees_kalender(db, zaterdag, zaterdag)
    assert set(kalender[zaterdag]["teams"]) == {team_sleutel(HEREN), team_sleutel(JEUGD)}
    b = blootstelling(MAANDAG, MAANDAG + timedelta(days=7), kalender)
    assert b["MD"] == 1.0 and b["G"][team_sleutel(HEREN)] == 1.0


def test_het_model_leert_welk_team_publiek_trekt(db):
    """Om de week speelt het eerste elftal thuis (veel drukker), de andere weken de jeugd (een gewone wedstrijd)."""
    a, b = _product(db, "A"), _product(db, "B")
    zaterdagen = _zaterdagen(12)
    for i, dag in enumerate(zaterdagen):
        _thuis(db, dag, HEREN if i % 2 == 0 else JEUGD)
    waar = {"wedstrijd": 0.3, "training": 0.2, "weer": 0.0, team_sleutel(HEREN): 0.9, team_sleutel(JEUGD): 0.0}
    laatste = _bouw_geschiedenis(db, {a: 40, b: 15}, effecten=waar, tijdstippen=_twee_keer_per_week(12))

    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    heren = _effect(prog, team_sleutel(HEREN))
    jeugd = _effect(prog, team_sleutel(JEUGD))
    assert heren["waarde"] > jeugd["waarde"] + 0.3
    assert heren["naam"] == f"Thuiswedstrijd van {HEREN} (bovenop een thuiswedstrijd)"


def test_met_een_team_leert_alleen_de_thuiswedstrijd(db):
    """Speelt er maar één team thuis, dan is dat niet van 'een thuiswedstrijd' te onderscheiden: geen team-effect."""
    a = _product(db, "A")
    for dag in _zaterdagen(8):
        _thuis(db, dag, HEREN)
    laatste = _bouw_geschiedenis(db, {a: 40}, effecten={"wedstrijd": 0.6, "training": 0.2, "weer": 0.0},
                                 tijdstippen=_twee_keer_per_week(8))
    prog = maak_prognose(db, nu=laatste + timedelta(hours=1))
    assert not any(e["sleutel"].startswith("team:") for e in prog["model"]["effecten"])
