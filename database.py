import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

STANDAARD_GEBRUIKER = "admin"
STANDAARD_WACHTWOORD = "kantine123"

SEED_PRODUCTEN = [
    # (artikelcode, naam, categorie, eenheid, voorraad, min_voorraad, bestel_hoeveelheid, verkoopprijs, actief)
    ("KAN", "Grote kan", "Bier", "Pitcher", 0, 0, 0, 12.00, 1),
    ("BIER", "Tap Bier", "Bier", "Glas", 0, 0, 0, 2.00, 1),
    ("HERTOG", "Hertog Jan Fles", "Bier", "Fles", 0, 0, 0, 2.20, 1),
    ("HERTOG0.0", "Hertog Jan 0.0 Fles", "Bier", "Fles", 0, 0, 0, 2.20, 1),
    ("GUINNESS", "Guinness Export", "Bier", "Fles", 0, 0, 0, 3.00, 1),
    ("LIEFMANS", "Liefmans Fruitesse", "Bier", "Fles", 0, 0, 0, 3.50, 1),
    ("SINASBB", "Sonnema Sinas", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
    ("BACARDI", "Bacardi Cola", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
    ("COLABB", "Sonnema Cola", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
    ("BOZUBLUE", "Bozu Blueberry", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
    ("BOZUGREEN", "Bozu Green", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
    ("WIJN", "Assorti Wijn", "Kassa knop", "Los", 0, 0, 0, 2.00, 1),
    ("PROSECCO", "Fles Prosecco", "Wijn", "Fles", 0, 0, 0, 8.00, 1),
    ("RADLER", "Amstel Radler", "Bier", "Fles", 0, 0, 0, 1.80, 1),
    ("SHOT", "Shot", "Kassa knop", "Los", 0, 0, 0, 1.50, 1),
    ("SNAKE", "Snakebite", "Shot", "Los", 0, 0, 0, 1.50, 1),
    ("MAGNERS", "Magners", "Bier", "Fles", 0, 0, 0, 5.00, 1),
    ("CAPTAIN", "Captain Morgan", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
    ("TRAYBB", "Tray Berenburg", "Tray", "Tray", 0, 0, 0, 42.00, 1),
    ("GUINNESSBLK", "Guinness Draugt Blik", "Bier", "Blik", 0, 0, 0, 5.00, 1),
    ("AA", "AA Drink", "Fris", "Fles", 0, 0, 0, 2.00, 1),
    ("POWERG", "Powerrade Geel", "Fris", "Fles", 0, 0, 0, 2.00, 1),
    ("POWERB", "Powerrade Blauw", "Fris", "Fles", 0, 0, 0, 2.00, 1),
    ("COCA", "Coca Cola", "Fris", "Fles", 0, 0, 0, 2.00, 1),
    ("COCAZERO", "Coca Cola Zero", "Fris", "Fles", 0, 0, 0, 2.00, 1),
    ("FANTA", "Fanta", "Fris", "Fles", 0, 0, 0, 2.00, 1),
    ("RIV", "Rivella", "Fris", "Fles", 0, 0, 0, 2.00, 1),
    ("WATER", "Water", "Fris", "Fles", 0, 0, 0, 1.85, 1),
    ("BOZUDARK", "Bozu Hard Icetea", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
    ("BOZUORANJE", "Bozu Peach", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
    ("HJFUST", "Fust Hertog Jan", "Telling", "Fust", 0, 0, 0, 0.00, 1),
    ("DORITOS", "Doritos", "Chips", "Zakje", 0, 0, 0, 1.20, 1),
    ("DORITOSZW", "Doritos Zwart", "Chips", "Zakje", 0, 0, 0, 1.20, 1),
    ("LAYS", "Lays Groen", "Chips", "Zakje", 0, 0, 0, 1.20, 1),
    ("LAYSBLW", "Lays Blauw", "Chips", "Zakje", 0, 0, 0, 1.20, 1),
    ("DROGE", "Droge Worst", "Snoep", "Worst", 0, 3, 0, 0.00, 1),
    ("HARIBO", "Haribo Starmix", "Snoep", "Zakje", 0, 0, 0, 1.50, 1),
    ("SNICKER", "Snicker", "Snoep", "Reep", 0, 0, 0, 1.00, 1),
    ("MARS", "Mars", "Snoep", "Reep", 0, 0, 0, 1.00, 1),
    ("TWIX", "Twix", "Snoep", "Reep", 0, 0, 0, 1.00, 1),
    ("MM", "M&M Geel", "Snoep", "Zakje", 0, 0, 0, 14.00, 1),
    ("CHOCO", "Chocolade melk", "Fris", "Flesje", 0, 0, 0, 1.20, 1),
    ("ABSO", "Absolute Sprite", "Voorgemixte Blik", "Blik", 0, 0, 0, 3.50, 1),
]


# Columns added after the initial release. CREATE TABLE IF NOT EXISTS won't
# retrofit these onto a database file that was created before the column
# existed, so they're added by hand on every connection (cheap PRAGMA check).
KOLOM_MIGRATIES = [
    ("producten", "verkoopprijs", "REAL NOT NULL DEFAULT 0"),
    ("producten", "artikelcode", "TEXT"),
    ("producten", "actief", "INTEGER NOT NULL DEFAULT 1"),
    ("mutaties", "telling_id", "INTEGER REFERENCES tellingen(id)"),
    ("gebruikers", "rol", "TEXT NOT NULL DEFAULT 'beheerder'"),
    ("gebruikers", "laatste_login", "TEXT"),
    ("producten", "besteleenheid", "TEXT"),
    ("producten", "besteleenheid_factor", "INTEGER NOT NULL DEFAULT 1"),
]


def _migreer_kolommen(db):
    for tabel, kolom, definitie in KOLOM_MIGRATIES:
        bestaande = {row["name"] for row in db.execute(f"PRAGMA table_info({tabel})")}
        if kolom not in bestaande:
            db.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {definitie}")


def _migreer_categorieen(db):
    """De categorieen-tabel is nieuw: als hij leeg is (nieuwe kolom op een
    bestaande database, of een gloednieuwe installatie), vullen we 'm met de
    categorieen die al in gebruik zijn bij bestaande producten, zodat er
    niets verandert aan wat er al stond. Bij een lege producten-tabel (verse
    installatie, vlak voordat SEED_PRODUCTEN is ingeladen) vallen we terug
    op de categorieen uit SEED_PRODUCTEN zelf, zodat de volgorde waarin
    init_db() dingen inlaadt er niet toe doet."""
    aantal = db.execute("SELECT COUNT(*) AS n FROM categorieen").fetchone()["n"]
    if aantal > 0:
        return
    bestaande = db.execute(
        "SELECT DISTINCT categorie FROM producten WHERE categorie IS NOT NULL AND categorie != ''"
    ).fetchall()
    namen = [row["categorie"] for row in bestaande]
    if not namen:
        namen = sorted({rij[2] for rij in SEED_PRODUCTEN})
    for naam in namen:
        db.execute("INSERT OR IGNORE INTO categorieen (naam) VALUES (?)", (naam,))


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
        _migreer_categorieen(g.db)
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
                   (artikelcode, naam, categorie, eenheid, voorraad, min_voorraad,
                    bestel_hoeveelheid, verkoopprijs, actief)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
