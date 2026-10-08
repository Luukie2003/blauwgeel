import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import backup


def _maak_db(pad, met_producten=True):
    conn = sqlite3.connect(pad)
    if met_producten:
        conn.execute("CREATE TABLE producten (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


def test_goede_backup_wordt_goedgekeurd(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    _maak_db(pad)
    assert backup.controleer_backup(pad) == (True, "ok")


def test_backup_zonder_producttabel_wordt_afgekeurd(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    _maak_db(pad, met_producten=False)
    ok, melding = backup.controleer_backup(pad)
    assert not ok
    assert "producten" in melding


def test_kapotte_backup_wordt_afgekeurd(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    pad.write_bytes(b"dit is geen sqlite-bestand" * 100)
    ok, _ = backup.controleer_backup(pad)
    assert not ok


def _zet_leeftijd(pad, dagen):
    tijd = time.time() - dagen * 86400
    os.utime(pad, (tijd, tijd))


def test_status_zonder_backups_is_niet_ok(tmp_path):
    status = backup.bereken_backup_status(backup_map=tmp_path)
    assert not status["ok"]
    assert status["laatste"] is None


def test_status_met_verse_backup_is_ok(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    _maak_db(pad)
    assert backup.bereken_backup_status(backup_map=tmp_path)["ok"]


def test_status_met_oude_backup_waarschuwt(tmp_path):
    pad = tmp_path / "voorraad-2026-10-01.db"
    _maak_db(pad)
    _zet_leeftijd(pad, 5)
    status = backup.bereken_backup_status(backup_map=tmp_path)
    assert not status["ok"]
    assert "5 dagen" in status["tekst"]


def test_veiligheidskopie_voor_herstel_telt_niet_mee_als_verse_backup(tmp_path):
    oud = tmp_path / "voorraad-2026-10-01.db"
    _maak_db(oud)
    _zet_leeftijd(oud, 5)
    _maak_db(tmp_path / "voorraad-voor-herstel-20261007-120000.db")
    assert not backup.bereken_backup_status(backup_map=tmp_path)["ok"]


def test_dashboard_en_backuppagina_tonen_waarschuwing(ingelogde_client, monkeypatch, tmp_path):
    monkeypatch.setattr(backup, "BACKUP_MAP", tmp_path)
    assert b"Er is nog geen back-up gemaakt" in ingelogde_client.get("/").data
    assert b"Er is nog geen back-up gemaakt" in ingelogde_client.get("/backups").data

    _maak_db(tmp_path / f"voorraad-{datetime.now().strftime('%Y-%m-%d')}.db")
    assert b"Er is nog geen back-up gemaakt" not in ingelogde_client.get("/").data


# ---------- Herstelcontrole ----------


def _volledige_db(pad, producten=3, gebruikers=1):
    conn = sqlite3.connect(pad)
    for tabel in backup.VERPLICHTE_TABELLEN:
        conn.execute(f"CREATE TABLE {tabel} (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO producten (id) VALUES (?)", [(i,) for i in range(producten)])
    conn.executemany("INSERT INTO gebruikers (id) VALUES (?)", [(i,) for i in range(gebruikers)])
    conn.commit()
    conn.close()


def test_herstelcontrole_van_een_goede_backup(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    _volledige_db(pad)

    resultaat = backup.controleer_herstel(pad, live_pad=tmp_path / "bestaat-niet.db")

    assert resultaat["ok"], resultaat["melding"]
    assert resultaat["tabellen"] == len(backup.VERPLICHTE_TABELLEN)
    assert resultaat["backup"] == pad.name


def test_herstelcontrole_raakt_de_backup_en_de_live_database_niet_aan(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    _volledige_db(pad)
    voor = pad.read_bytes()

    backup.controleer_herstel(pad, live_pad=tmp_path / "live.db")

    assert pad.read_bytes() == voor
    assert not (tmp_path / "live.db").exists()


def test_herstelcontrole_keurt_ontbrekende_tabellen_af(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    _maak_db(pad)  # alleen producten

    resultaat = backup.controleer_herstel(pad, live_pad=tmp_path / "x.db")

    assert not resultaat["ok"]
    assert "ontbreken" in resultaat["melding"]


def test_herstelcontrole_keurt_een_back_up_zonder_accounts_af(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    _volledige_db(pad, gebruikers=0)
    assert not backup.controleer_herstel(pad, live_pad=tmp_path / "x.db")["ok"]


def test_herstelcontrole_keurt_een_kapot_bestand_af(tmp_path):
    pad = tmp_path / "voorraad-2026-10-07.db"
    pad.write_bytes(b"geen database" * 200)
    assert not backup.controleer_herstel(pad, live_pad=tmp_path / "x.db")["ok"]


def test_herstelcontrole_vergelijkt_met_de_echte_database(tmp_path):
    live = tmp_path / "live.db"
    _volledige_db(live, producten=40)
    pad = tmp_path / "voorraad-2026-10-07.db"
    _volledige_db(pad, producten=0)

    resultaat = backup.controleer_herstel(pad, live_pad=live)

    assert not resultaat["ok"] and "geen producten" in resultaat["melding"]


def test_uitkomst_wordt_bewaard_en_teruggelezen(tmp_path):
    assert backup.lees_herstelcontrole(tmp_path) is None
    assert backup.herstelcontrole_is_aan_de_beurt(datetime(2026, 10, 8), tmp_path)  # nog nooit gedraaid

    backup.schrijf_herstelcontrole({"ok": True, "datum": "2026-10-01 03:00", "melding": "x", "backup": "b.db"}, tmp_path)

    assert backup.lees_herstelcontrole(tmp_path)["ok"] is True
    assert not backup.herstelcontrole_is_aan_de_beurt(datetime(2026, 10, 8), tmp_path)
    assert backup.herstelcontrole_is_aan_de_beurt(datetime(2026, 11, 1), tmp_path)  # 1e van de maand


def test_mislukte_herstelcontrole_geeft_een_waarschuwing_in_de_status(tmp_path):
    _maak_db(tmp_path / f"voorraad-{datetime.now().strftime('%Y-%m-%d')}.db")
    backup.schrijf_herstelcontrole({"ok": False, "datum": "2026-10-01 03:00", "melding": "tabellen ontbreken: x", "backup": "b.db"}, tmp_path)

    status = backup.bereken_backup_status(backup_map=tmp_path)

    assert not status["ok"]
    assert "herstelcontrole is mislukt" in status["tekst"]


def test_backuppagina_toont_de_herstelcontrole(ingelogde_client, monkeypatch, tmp_path):
    monkeypatch.setattr(backup, "BACKUP_MAP", tmp_path)
    assert b"nog niet gedraaid" in ingelogde_client.get("/backups").data

    backup.schrijf_herstelcontrole(
        {"ok": True, "datum": "2026-10-01 03:00", "melding": "terugzetten gelukt", "backup": "b.db"}, tmp_path
    )
    pagina = ingelogde_client.get("/backups").data
    assert b"Laatste herstelcontrole" in pagina and b"terugzetten gelukt" in pagina


def test_dagelijkse_taak_maakt_backup_controleert_herstel_en_ruimt_op(app, monkeypatch, tmp_path):
    live = app.config["DATABASE"]
    conn = sqlite3.connect(live)
    conn.execute("INSERT INTO paginabezoeken (endpoint, weergave_modus, datum) VALUES ('dashboard', 'desktop', '2020-01-01 10:00')")
    conn.execute("INSERT INTO paginabezoeken (endpoint, weergave_modus, datum) VALUES ('dashboard', 'desktop', ?)", (datetime.now().strftime("%Y-%m-%d %H:%M"),))
    conn.commit()
    conn.close()
    monkeypatch.setattr(backup, "BRON", Path(live))
    monkeypatch.setattr(backup, "BACKUP_MAP", tmp_path / "backups")
    gemaild = []
    monkeypatch.setattr(backup.mail, "stuur_mail", lambda *a, **k: gemaild.append((a, k)) or True)

    assert backup.dagelijkse_taak([]) == 0

    nieuwe = list((tmp_path / "backups").glob("voorraad-*.db"))
    assert len(nieuwe) == 1
    assert backup.lees_herstelcontrole(tmp_path / "backups")["ok"] is True  # nog nooit gedraaid -> nu wel
    assert len(gemaild) == 1  # de dagelijkse kopie
    conn = sqlite3.connect(live)
    assert conn.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0] == 1  # de oude is opgeruimd
    conn.close()
    # ... maar de back-up van vóór het opruimen bevat hem nog.
    kopie = sqlite3.connect(nieuwe[0])
    assert kopie.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0] == 2
    kopie.close()


def test_dagelijkse_taak_zonder_database_meldt_en_faalt(monkeypatch, tmp_path):
    monkeypatch.setattr(backup, "BRON", tmp_path / "bestaat-niet.db")
    monkeypatch.setattr(backup, "BACKUP_MAP", tmp_path / "backups")
    gemaild = []
    monkeypatch.setattr(backup.mail, "stuur_mail", lambda *a, **k: gemaild.append(a) or True)

    assert backup.dagelijkse_taak([]) == 1
    assert gemaild and "mislukt" in gemaild[0][0]
