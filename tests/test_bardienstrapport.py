from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from bardienstrapport import _uren, bereken_bardienstrapport, splits_namen
from conftest import stel_csrf_token_in as _csrf
from database import WACHTWOORD_HASH_METHODE
from test_seizoensrapport import _product, _weekelijkse_tellingen

VANAF, TOT = date(2026, 8, 1), date(2026, 10, 8)


def _dienst(db, datum, namen, start="19:00", eind="23:00"):
    db.execute(
        "INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op) VALUES (?, ?, ?, ?, '2026-08-01 10:00')",
        (datum, start, eind, namen),
    )
    db.commit()


@pytest.fixture
def geschiedenis(db):
    pils = _product(db, "Pils", 2.0)
    _weekelijkse_tellingen(db, {pils: (70, 2.0)}, van=date(2026, 6, 27), tot=date(2026, 10, 3))


def test_namen_splitsen():
    assert splits_namen("Luuk & Femke") == ["Luuk", "Femke"]
    assert splits_namen("Piet, Karin en Jan") == ["Piet", "Karin", "Jan"]
    assert splits_namen("Piet/Karin + Jan") == ["Piet", "Karin", "Jan"]
    assert splits_namen("  ") == []


def test_duur_van_een_dienst_ook_over_middernacht():
    assert _uren("19:00", "23:00") == 4
    assert _uren("22:00", "01:00") == 3


def test_zonder_tellingen_geen_rapport(db):
    assert bereken_bardienstrapport(db, VANAF, TOT) is None


def test_omzet_per_persoon_en_dienst(db, geschiedenis):
    _dienst(db, "2026-09-05", "Luuk & Femke")
    _dienst(db, "2026-09-12", "luuk")

    rapport = bereken_bardienstrapport(db, VANAF, TOT)

    assert rapport["aantal_diensten"] == 2
    namen = {p["naam"].casefold(): p for p in rapport["personen"]}
    assert set(namen) == {"luuk", "femke"}
    assert namen["luuk"]["diensten"] == 2 and namen["femke"]["diensten"] == 1
    assert namen["luuk"]["uren"] == 8
    assert namen["luuk"]["per_dienst"] > 0
    assert namen["luuk"]["per_uur"] == pytest.approx(namen["luuk"]["omzet"] / 8)


def test_meerdere_diensten_op_een_dag_verdelen_de_omzet_naar_duur(db, geschiedenis):
    _dienst(db, "2026-09-05", "Piet", "12:00", "16:00")  # 4 uur
    _dienst(db, "2026-09-05", "Karin", "16:00", "22:00")  # 6 uur

    rapport = bereken_bardienstrapport(db, VANAF, TOT)

    piet = next(p for p in rapport["personen"] if p["naam"] == "Piet")
    karin = next(p for p in rapport["personen"] if p["naam"] == "Karin")
    assert piet["omzet"] / karin["omzet"] == pytest.approx(4 / 6)


def test_diensten_buiten_de_tellingen_tellen_niet_mee(db, geschiedenis):
    _dienst(db, "2026-10-20", "Piet")  # na de laatste telling
    _dienst(db, "2026-09-05", "Karin")

    rapport = bereken_bardienstrapport(db, VANAF, date(2026, 12, 31))

    assert [p["naam"] for p in rapport["personen"]] == ["Karin"]
    assert rapport["zonder_gegevens"] == 1


def test_gecorrigeerde_omzet_haalt_een_drukke_dag_naar_een_gewone_dag(db, geschiedenis):
    # 5 september 2026 is een zaterdag; met een thuiswedstrijd is die drukker.
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, afgelast) VALUES ('ZA 1', '2026-09-05', 'x', 1, 0)"
    )
    db.commit()
    _dienst(db, "2026-09-05", "Piet")

    p = bereken_bardienstrapport(db, VANAF, TOT)["personen"][0]

    assert p["gecorrigeerd"] <= p["omzet"]


# ---------- Pagina ----------


def test_pagina_voor_beheerder(ingelogde_client, db, geschiedenis):
    _dienst(db, "2026-09-05", "Luuk & Femke")
    pagina = ingelogde_client.get("/rapporten/bardiensten")
    assert pagina.status_code == 200
    assert b"Luuk" in pagina.data and b"Femke" in pagina.data
    assert ingelogde_client.get("/rapporten/bardiensten?periode=90").status_code == 200
    assert ingelogde_client.get("/rapporten/bardiensten?periode=onzin").status_code == 200


def test_pagina_zonder_tellingen(ingelogde_client):
    assert b"nog geen tellingen" in ingelogde_client.get("/rapporten/bardiensten").data


def test_pagina_en_menu_zijn_niet_voor_vrijwilligers(client, db):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) "
        "VALUES ('vrijwilliger', ?, 'vrijwilliger', 'voorraad,kassa', '2026-01-01 10:00')",
        (generate_password_hash("geheim123", method=WACHTWOORD_HASH_METHODE),),
    )
    db.commit()
    client.post("/login", data={"naam": "vrijwilliger", "wachtwoord": "geheim123", "csrf_token": _csrf(client)})

    assert client.get("/rapporten/bardiensten").status_code == 302
    assert b"Omzet per bardienst" not in client.get("/rapporten/seizoenen").data  # niet in de zijbalk
