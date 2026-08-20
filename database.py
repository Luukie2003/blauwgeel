import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

STANDAARD_GEBRUIKER = "admin"
STANDAARD_WACHTWOORD = "kantine123"

SEED_PRODUCTEN = [
    # (naam, categorie, eenheid, voorraad, min_voorraad, bestel_hoeveelheid, verkoopprijs)
    ("Pilsbier (krat 24 flesjes)", "Drank", "krat", 8, 3, 5, 45.00),
    ("Cola 33cl (blikje)", "Drank", "blikje", 48, 24, 48, 1.50),
    ("Sinas 33cl (blikje)", "Drank", "blikje", 24, 12, 24, 1.50),
    ("Koffie (pak 250g)", "Drank", "pak", 4, 2, 4, 0.00),
    ("Chips (zak)", "Snacks", "zak", 15, 10, 20, 1.00),
    ("Frikandel", "Snacks", "stuks", 30, 20, 50, 2.00),
    ("Frietsaus (bak)", "Snacks", "bak", 3, 2, 4, 0.00),
    ("Toiletpapier", "Non-food", "rol", 12, 6, 12, 0.00),
    ("Afwasmiddel", "Non-food", "fles", 2, 1, 2, 0.00),
]


# Columns added after the initial release. CREATE TABLE IF NOT EXISTS won't
# retrofit these onto a database file that was created before the column
# existed, so they're added by hand on every connection (cheap PRAGMA check).
KOLOM_MIGRATIES = [
    ("producten", "verkoopprijs", "REAL NOT NULL DEFAULT 0"),
    ("mutaties", "telling_id", "INTEGER REFERENCES tellingen(id)"),
]


def _migreer_kolommen(db):
    for tabel, kolom, definitie in KOLOM_MIGRATIES:
        bestaande = {row["name"] for row in db.execute(f"PRAGMA table_info({tabel})")}
        if kolom not in bestaande:
            db.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {definitie}")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        # Always (re)apply the schema on a fresh connection. This is cheap
        # (CREATE ... IF NOT EXISTS) and makes the app self-healing if the
        # database file is ever replaced or wiped out from under a running
        # process -- e.g. by iCloud Drive syncing/evicting the .db file,
        # which is where this project lives.
        with open(SCHEMA_PATH) as f:
            g.db.executescript(f.read())
        _migreer_kolommen(g.db)
        g.db.commit()
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = get_db()
        count = db.execute("SELECT COUNT(*) AS n FROM producten").fetchone()["n"]
        if count == 0:
            db.executemany(
                """INSERT INTO producten
                   (naam, categorie, eenheid, voorraad, min_voorraad, bestel_hoeveelheid, verkoopprijs)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                SEED_PRODUCTEN,
            )
            db.commit()

        gebruikers_count = db.execute("SELECT COUNT(*) AS n FROM gebruikers").fetchone()["n"]
        if gebruikers_count == 0:
            db.execute(
                "INSERT INTO gebruikers (naam, wachtwoord_hash, aangemaakt_op) VALUES (?, ?, ?)",
                (
                    STANDAARD_GEBRUIKER,
                    generate_password_hash(STANDAARD_WACHTWOORD, method="pbkdf2:sha256"),
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            db.commit()


def register_db(app):
    app.teardown_appcontext(close_db)
