import sqlite3
from datetime import datetime, timedelta

import pytest

from onderhoud import BEWAARTERMIJNEN, ruim_oude_gegevens

NU = datetime(2026, 10, 8, 12, 0)


def _tekst(dagen_terug):
    return (NU - timedelta(days=dagen_terug)).strftime("%Y-%m-%d %H:%M")


@pytest.fixture
def conn(app):
    """De volledige testdatabase (met het echte schema), los van de app."""
    pad = app.config["DATABASE"]
    verbinding = sqlite3.connect(pad)
    verbinding.row_factory = sqlite3.Row
    yield verbinding
    verbinding.close()


def _aantal(conn, tabel):
    return conn.execute(f"SELECT COUNT(*) FROM {tabel}").fetchone()[0]


def test_bewaartermijnen_verwijzen_naar_bestaande_tabellen_en_kolommen(conn):
    """Een typfout zou stilletjes nooit iets opruimen."""
    for tabel, kolom, _dagen, _extra in BEWAARTERMIJNEN:
        kolommen = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabel})")}
        assert kolom in kolommen, f"{tabel}.{kolom} bestaat niet"


def test_paginabezoeken_en_logboek_worden_na_twee_jaar_opgeruimd(conn):
    for dagen in (10, 700, 760):
        conn.execute(
            "INSERT INTO paginabezoeken (endpoint, weergave_modus, datum) VALUES ('dashboard', 'desktop', ?)",
            (_tekst(dagen),),
        )
        conn.execute(
            "INSERT INTO logboek (datum, endpoint, actie) VALUES (?, 'login', 'Ingelogd')", (_tekst(dagen),)
        )
    conn.commit()

    verwijderd = ruim_oude_gegevens(conn, NU)

    assert verwijderd["paginabezoeken"] == 1 and verwijderd["logboek"] == 1
    assert _aantal(conn, "paginabezoeken") == 2 and _aantal(conn, "logboek") == 2


def test_een_lopende_inlogblokkade_blijft_staan(conn):
    conn.execute(
        "INSERT INTO login_pogingen (naam, mislukte_pogingen, laatste_poging, geblokkeerd_tot) VALUES "
        "('oud', 3, ?, NULL), ('geblokkeerd', 5, ?, ?), ('recent', 1, ?, NULL)",
        (_tekst(60), _tekst(60), (NU + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"), _tekst(2)),
    )
    conn.commit()

    ruim_oude_gegevens(conn, NU)

    namen = {r["naam"] for r in conn.execute("SELECT naam FROM login_pogingen")}
    assert namen == {"geblokkeerd", "recent"}


def test_ontbrekende_tabel_wordt_overgeslagen():
    conn = sqlite3.connect(":memory:")
    assert ruim_oude_gegevens(conn, NU) == {}
