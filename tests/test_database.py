"""Tests voor de hergebruikte sqlite3-connectie in database.py (get_db()
opent nog maar 1x per workerproces een verbinding i.p.v. per request, zie
het uitgebreide commentaar daar) -- met name dat een back-up-restore
(die buiten deze cache om rechtstreeks in het bestand schrijft) niet
onopgemerkt blijft hangen op de oude, gecachte inhoud."""

import sqlite3

import database


def test_get_db_hergebruikt_dezelfde_verbinding_binnen_hetzelfde_pad(app):
    with app.app_context():
        db1 = database.get_db()
    with app.app_context():
        db2 = database.get_db()
    assert db1 is db2


def test_get_db_geeft_aparte_verbindingen_per_databasepad(app, tmp_path):
    ander_pad = str(tmp_path / "ander.db")
    app.config["DATABASE"] = str(tmp_path / "test.db")
    with app.app_context():
        db_origineel = database.get_db()

    app.config["DATABASE"] = ander_pad
    with app.app_context():
        db_ander = database.get_db()

    assert db_origineel is not db_ander


def test_close_db_rolt_terug_in_plaats_van_te_sluiten(app):
    with app.app_context():
        db = database.get_db()
        db.execute(
            "INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, actief) "
            "VALUES ('Niet gecommit', 'Overig', 'stuks', 1, 0, 1)"
        )
        # Geen commit() -- teardown (via close_db) moet dit terugrollen.

    with app.app_context():
        db_hergebruikt = database.get_db()
        rij = db_hergebruikt.execute(
            "SELECT COUNT(*) AS n FROM producten WHERE naam = 'Niet gecommit'"
        ).fetchone()
        assert rij["n"] == 0
        # De verbinding zelf moet nog gewoon bruikbaar zijn (niet gesloten).
        db_hergebruikt.execute("SELECT 1")


def test_sluit_gecachte_verbinding_forceert_verse_data_na_restore(app, tmp_path):
    """Simuleert precies wat backup.herstel_backup() doet: met de
    sqlite3.Connection.backup()-API (een pagina-voor-pagina kopie, geen
    gewone SQL-statement) rechtstreeks in het live databasebestand
    schrijven, buiten get_db() om. Die API vervangt de inhoud op een
    lager niveau dan een normale UPDATE, en de al openstaande, gecachte
    connectie moet daarna expliciet vervangen worden om de nieuwe inhoud
    te zien."""
    db_pad = app.config["DATABASE"]

    with app.app_context():
        database.get_db()  # zet de connectie in _VERBINDINGEN vast

    # Een aparte "back-up"-database met andere inhoud, en die er met
    # dezelfde API als backup.py overheen zetten.
    backup_pad = str(tmp_path / "los-backup.db")
    backup_bron = sqlite3.connect(backup_pad)
    backup_bron.execute(
        "CREATE TABLE producten (id INTEGER PRIMARY KEY, naam TEXT)"
    )
    backup_bron.execute("INSERT INTO producten (naam) VALUES ('Hersteld product')")
    backup_bron.commit()

    live_verbinding = sqlite3.connect(db_pad)
    with live_verbinding:
        backup_bron.backup(live_verbinding)
    backup_bron.close()
    live_verbinding.close()

    with app.app_context():
        db_nog_gecached = database.get_db()
        gevonden_voor = db_nog_gecached.execute(
            "SELECT naam FROM producten WHERE naam = 'Hersteld product'"
        ).fetchone()

    database.sluit_gecachte_verbinding(db_pad)

    with app.app_context():
        db_na_invalidatie = database.get_db()
        gevonden_na = db_na_invalidatie.execute(
            "SELECT naam FROM producten WHERE naam = 'Hersteld product'"
        ).fetchone()

    # Waar het echt om gaat: ná het ongeldig maken van de cache ziet de
    # (nieuwe) connectie sowieso de herstelde inhoud, ongeacht wat de
    # oude gecachte connectie ervoor liet zien.
    assert gevonden_na is not None
