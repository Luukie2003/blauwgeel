"""Database: verbinding, schema, migraties en het eerste beheerdersaccount.

Vroeger 1 bestand; de migraties en de voorbeeldproducten staan nu in
database/migraties.py en database/seed.py. Alles blijft hier beschikbaar,
dus `from database import get_db, ...` werkt ongewijzigd."""

import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash

from database.migraties import (  # noqa: F401
    KOLOM_MIGRATIES,
    _migreer_bieren_backfill,
    _migreer_categorieen,
    _migreer_club_van_20_administratie,
    _migreer_club_van_20_datums,
    _migreer_kassa_afgesloten,
    _migreer_keuken_categorie,
    _migreer_kluis_kassalade,
    _migreer_kolommen,
    _migreer_stand_club_backfill,
    _migreer_stand_poules_backfill,
    _migreer_stemmen_meerdere_keuzes,
    _migreer_telling_verkoopprijs,
    migreer_alles,
)
from database.seed import SEED_PRODUCTEN  # noqa: F401

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"

STANDAARD_GEBRUIKER = "admin"

# Waar het willekeurig gegenereerde wachtwoord van het allereerste
# beheerdersaccount komt te staan (zie init_db) -- zelfde opzet als
# SECRET_KEY_PATH in app.py: een vast wachtwoord in de broncode ("kantine123")
# zou voor elke nieuwe installatie hetzelfde en publiek bekend zijn.
ADMIN_WACHTWOORD_PAD = Path(__file__).resolve().parent.parent / "admin_wachtwoord_initieel.txt"

# Expliciet gekozen i.p.v. werkzeug's eigen standaard: die is "scrypt" sinds
# werkzeug 2.3, wat hashlib.scrypt vereist -- niet overal beschikbaar
# (bijv. deze lokale ontwikkelomgeving mist het, afhankelijk van de
# OpenSSL/LibreSSL-build van Python). pbkdf2_hmac zit altijd in de
# standaardbibliotheek. Het aantal iteraties is ook bewust lager dan
# werkzeug's eigen pbkdf2-standaard (600.000): dat duurde op de hosting van
# deze site ruim 0,6s per inlogpoging. 200.000 is nog steeds een serieuze
# drempel voor offline brute-force, en ruim voldoende voor dit interne
# kantine-beheersysteem (geen betaalgegevens, geen hoogwaardig doelwit).
WACHTWOORD_HASH_METHODE = "pbkdf2:sha256:200000"


# Databasepaden waarvoor het schema al is toegepast in dit proces -- zie
# get_db() hieronder.
_SCHEMA_TOEGEPAST_VOOR = set()


def get_db():
    if "db" not in g:
        db_pad = current_app.config["DATABASE"]
        g.db = sqlite3.connect(db_pad)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        # Bewust GEEN WAL-modus (was dat eerder wel): WAL vereist dat alle
        # connecties het bijbehorende -shm-bestand via mmap delen, en dat
        # bleek op deze hosting niet betrouwbaar zodra zowel de webapp
        # (meerdere workers) als een los proces (de dagelijkse back-up-taak,
        # of een handmatig console-scriptje) tegelijk een eigen connectie
        # naar hetzelfde bestand open hadden -- dat gaf 1x een "database
        # disk image is malformed"-fout (bleek gelukkig geen echte
        # corruptie: PRAGMA integrity_check kwam daarna weer "ok" terug,
        # maar het risico is te groot om te laten staan). De standaard
        # journal-mode (DELETE) gebruikt alleen gewone bestandsloks i.p.v.
        # gedeeld geheugen, en is de reden dat dit weer per request een
        # nieuwe connectie opent i.p.v. er 1 te hergebruiken: zonder WAL is
        # er geen -wal-bestand meer dat bij elke request op- en afgebroken
        # hoeft te worden, dus dat kostte toch al geen tientallen ms meer.
        g.db.execute("PRAGMA journal_mode = DELETE")
        # Schema + migraties toepassen is zelfhelend (CREATE ... IF NOT
        # EXISTS) en hoeft dus maar 1x per proces, niet op elke request --
        # het db-pad wordt hierboven al bijgehouden zodat een volgende
        # request in hetzelfde proces dit overslaat. Wordt de database ooit
        # vervangen of leeggehaald onder een lopend proces (bijv. door
        # iCloud Drive dat het .db-bestand synchroniseert/evict, waar dit
        # project staat), dan herstelt de eerstvolgende procesherstart dit
        # weer vanzelf.
        if db_pad not in _SCHEMA_TOEGEPAST_VOOR:
            with open(SCHEMA_PATH) as f:
                g.db.executescript(f.read())
            migreer_alles(g.db)
            g.db.commit()
            _SCHEMA_TOEGEPAST_VOOR.add(db_pad)
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app, admin_wachtwoord=None):
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
            # admin_wachtwoord is alleen bedoeld voor de testsuite (zie
            # tests/conftest.py), die een vast wachtwoord nodig heeft om
            # voorspelbaar te kunnen inloggen. Bij een echte (nieuwe)
            # installatie wordt er willekeurig een gegenereerd, zodat er geen
            # voor iedereen gelijk en publiek bekend standaardwachtwoord
            # bestaat -- eenmalig weggeschreven zodat degene die de
            # installatie doet het kan opzoeken.
            if admin_wachtwoord is None:
                if ADMIN_WACHTWOORD_PAD.exists():
                    admin_wachtwoord = ADMIN_WACHTWOORD_PAD.read_text().strip()
                else:
                    admin_wachtwoord = secrets.token_urlsafe(9)
                    ADMIN_WACHTWOORD_PAD.write_text(admin_wachtwoord)
                print(
                    f"[setup] Beheerdersaccount '{STANDAARD_GEBRUIKER}' aangemaakt. "
                    f"Wachtwoord: {admin_wachtwoord} (ook opgeslagen in {ADMIN_WACHTWOORD_PAD.name})"
                )
            db.execute(
                "INSERT INTO gebruikers (naam, wachtwoord_hash, aangemaakt_op) VALUES (?, ?, ?)",
                (
                    STANDAARD_GEBRUIKER,
                    generate_password_hash(admin_wachtwoord, method=WACHTWOORD_HASH_METHODE),
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            db.commit()


def register_db(app):
    app.teardown_appcontext(close_db)
