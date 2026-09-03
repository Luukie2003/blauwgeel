"""Regressietest: de database mag niet in WAL-modus staan.

WAL vereist dat alle connecties een -shm-bestand via mmap delen. Dat bleek
op deze hosting niet betrouwbaar zodra de webapp (meerdere workers) en een
los proces (de dagelijkse back-up-taak, of een handmatig scriptje) tegelijk
een eigen connectie naar hetzelfde bestand hadden open staan: dat gaf 1x
een "database disk image is malformed"-fout in productie (geen echte
corruptie -- PRAGMA integrity_check kwam daarna weer "ok" terug -- maar het
risico is te groot om te laten staan). Zie het commentaar bij get_db() in
database.py."""

import database


def test_get_db_gebruikt_geen_wal_modus(app):
    with app.app_context():
        db = database.get_db()
        modus = db.execute("PRAGMA journal_mode").fetchone()[0]
    assert modus.lower() != "wal"
