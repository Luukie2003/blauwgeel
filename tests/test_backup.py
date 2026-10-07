import os
import sqlite3
import time
from datetime import datetime, timedelta

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
