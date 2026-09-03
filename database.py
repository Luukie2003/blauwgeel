import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

STANDAARD_GEBRUIKER = "admin"
STANDAARD_WACHTWOORD = "kantine123"

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

SEED_PRODUCTEN = [
    # (artikelcode, naam, categorie, eenheid, voorraad, min_voorraad, bestel_hoeveelheid, verkoopprijs, actief)
    ("KAN", "Grote kan", "Bier", "Pitcher", 0, 0, 0, 12.00, 1),
    ("BIER", "Tap Bier", "Bier", "Glas", 0, 0, 0, 2.00, 1),
    ("HERTOG", "Hertog Jan Fles", "Bier", "Fles", 0, 0, 0, 2.20, 1),
    ("HERTOG0.0", "Hertog Jan 0.0 Fles", "Bier", "Fles", 0, 0, 0, 2.20, 1),
    ("GUINNESS", "Guinness Export", "Bier", "Fles", 0, 0, 0, 3.00, 1),
    ("LIEFMANS", "Liefmans Fruitesse", "Bier", "Fles", 0, 0, 0, 2.50, 1),
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
    ("DROGE", "Droge Worst", "Snoep", "Worst", 0, 3, 0, 1.80, 1),
    ("HARIBO", "Haribo Starmix", "Snoep", "Zakje", 0, 0, 0, 1.50, 1),
    ("SNICKER", "Snicker", "Snoep", "Reep", 0, 0, 0, 1.00, 1),
    ("MARS", "Mars", "Snoep", "Reep", 0, 0, 0, 1.00, 1),
    ("TWIX", "Twix", "Snoep", "Reep", 0, 0, 0, 1.00, 1),
    ("MM", "M&M Geel", "Snoep", "Zakje", 0, 0, 0, 1.00, 1),
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
    ("producten", "inkoopprijs", "REAL NOT NULL DEFAULT 0"),
    ("producten", "subcategorie", "TEXT"),
    ("gebruikers", "email", "TEXT"),
    ("gebruikers", "reset_token_hash", "TEXT"),
    ("gebruikers", "reset_token_verloopt", "TEXT"),
    ("gebruikers", "mail_factuur", "INTEGER NOT NULL DEFAULT 0"),
    ("gebruikers", "mail_week_overzicht", "INTEGER NOT NULL DEFAULT 0"),
    ("instellingen", "banner_tekst", "TEXT"),
    ("instellingen", "kassa_stand", "REAL NOT NULL DEFAULT 0"),
    ("mutaties", "gebruiker_id", "INTEGER REFERENCES gebruikers(id)"),
    ("tellingen", "gebruiker_id", "INTEGER REFERENCES gebruikers(id)"),
    ("bestellingen", "besteld_door_id", "INTEGER REFERENCES gebruikers(id)"),
    ("bestellingen", "referentie", "TEXT"),
    ("kassa_tellingen", "goedgekeurd_door_id", "INTEGER REFERENCES gebruikers(id)"),
    ("kassa_tellingen", "goedgekeurd_door", "TEXT"),
    ("kassa_tellingen", "goedgekeurd_op", "TEXT"),
    ("kassa_tellingen", "goedkeuring_opmerking", "TEXT"),
    ("mededelingen", "urgent", "INTEGER NOT NULL DEFAULT 0"),
    ("mededelingen", "afgehandeld", "INTEGER NOT NULL DEFAULT 0"),
    ("mededelingen", "afgehandeld_door", "TEXT"),
    ("mededelingen", "afgehandeld_op", "TEXT"),
    ("stemopties", "afbeelding", "TEXT"),
    ("stemmen", "naam", "TEXT"),
    ("stemmen", "afgekeurd", "INTEGER NOT NULL DEFAULT 0"),
    ("stemvragen", "sluit_op", "TEXT"),
    ("stemvragen", "toon_uitslag", "INTEGER NOT NULL DEFAULT 1"),
    ("stemvragen", "opmerking_toegestaan", "INTEGER NOT NULL DEFAULT 0"),
    ("stemmen", "opmerking", "TEXT"),
    ("stemvragen", "aantal_keuzes", "INTEGER NOT NULL DEFAULT 1"),
    ("producten", "afbeelding", "TEXT"),
    ("bestelregels", "manco", "INTEGER NOT NULL DEFAULT 0"),
    ("categorieen", "verkoopprijs_verplicht", "INTEGER NOT NULL DEFAULT 1"),
    ("producten", "glazen_per_fust", "INTEGER NOT NULL DEFAULT 0"),
    ("producten", "prijs_per_glas", "REAL NOT NULL DEFAULT 0"),
    ("kassa_tellingen", "contante_omzet_voor_correctie", "REAL"),
    ("kassa_tellingen", "contante_omzet_gecorrigeerd_door_id", "INTEGER REFERENCES gebruikers(id)"),
    ("kassa_tellingen", "contante_omzet_gecorrigeerd_door", "TEXT"),
    ("kassa_tellingen", "contante_omzet_gecorrigeerd_op", "TEXT"),
    ("kassa_tellingen", "contante_omzet_correctie_opmerking", "TEXT"),
    ("kassa_tellingen", "geteld_bedrag_voor_correctie", "REAL"),
    ("kassa_tellingen", "geteld_bedrag_gecorrigeerd_door_id", "INTEGER REFERENCES gebruikers(id)"),
    ("kassa_tellingen", "geteld_bedrag_gecorrigeerd_door", "TEXT"),
    ("kassa_tellingen", "geteld_bedrag_gecorrigeerd_op", "TEXT"),
    ("kassa_tellingen", "geteld_bedrag_correctie_opmerking", "TEXT"),
    ("kassa_mutaties", "bedrag_voor_correctie", "REAL"),
    ("kassa_mutaties", "gecorrigeerd_door_id", "INTEGER REFERENCES gebruikers(id)"),
    ("kassa_mutaties", "gecorrigeerd_door", "TEXT"),
    ("kassa_mutaties", "gecorrigeerd_op", "TEXT"),
    ("kassa_mutaties", "correctie_opmerking", "TEXT"),
]


def _migreer_kolommen(db):
    for tabel, kolom, definitie in KOLOM_MIGRATIES:
        bestaande = {row["name"] for row in db.execute(f"PRAGMA table_info({tabel})")}
        if kolom not in bestaande:
            db.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {definitie}")


def _migreer_telling_verkoopprijs(db):
    """telling_regels.verkoopprijs bestaat pas sinds de prijs-per-telling
    functie. Dit is bewust GEEN gewone kolom-migratie: die zou de kolom
    steeds op 0 laten staan voor bestaande tellingen, waardoor oude
    omzetcijfers ineens op nul zouden komen. In plaats daarvan vullen we 'm,
    precies op het moment dat de kolom voor het eerst wordt aangemaakt,
    eenmalig met de dan geldende (huidige) verkoopprijs -- zodat bestaande
    rapportages ongewijzigd blijven. Bestaat de kolom al, dan raken we niets
    meer aan: nieuwe tellingen zetten hun eigen prijs vast bij verwerking,
    en die mag nooit meer worden overschreven."""
    bestaande = {row["name"] for row in db.execute("PRAGMA table_info(telling_regels)")}
    if "verkoopprijs" in bestaande:
        return
    db.execute("ALTER TABLE telling_regels ADD COLUMN verkoopprijs REAL NOT NULL DEFAULT 0")
    db.execute(
        """UPDATE telling_regels
           SET verkoopprijs = (
               SELECT verkoopprijs FROM producten WHERE producten.id = telling_regels.product_id
           )"""
    )


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


def _migreer_kassa_afgesloten(db):
    """De kolom afgesloten is nieuw: kassa-tellingen werden voorheen meteen
    definitief verwerkt (direct verrekend in instellingen.kassa_stand).
    Bij het toevoegen van deze kolom markeren we alle op dat moment
    bestaande tellingen daarom in één keer als afgesloten, zodat hun invloed
    op de kassa-stand niet per ongeluk dubbel telt (of verdwijnt) doordat ze
    er ineens als 'nog open' uitzien. Tellingen die hierna worden
    aangemaakt starten gewoon standaard op open (0)."""
    bestaande = {row["name"] for row in db.execute("PRAGMA table_info(kassa_tellingen)")}
    if "afgesloten" in bestaande:
        return
    db.execute("ALTER TABLE kassa_tellingen ADD COLUMN afgesloten INTEGER NOT NULL DEFAULT 0")
    db.execute("UPDATE kassa_tellingen SET afgesloten = 1")


def _migreer_stemmen_meerdere_keuzes(db):
    """De UNIQUE-constraint op stemmen stond oorspronkelijk op
    (stemvraag_id, kiezer_sleutel): goed voor precies 1 keuze per stemmer.
    Met stemvragen.aantal_keuzes kan een stemmer nu meerdere opties
    tegelijk aanvinken, dus moet stemoptie_id in de constraint mee -- anders
    blokkeert de 2e keuze van dezelfde stemmer zichzelf. SQLite kent geen
    ALTER TABLE voor constraints, dus de tabel wordt eenmalig herbouwd."""
    ddl = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'stemmen'"
    ).fetchone()
    if ddl is None or "kiezer_sleutel, stemoptie_id" in ddl["sql"]:
        return
    db.execute("ALTER TABLE stemmen RENAME TO stemmen_oud")
    db.execute(
        """CREATE TABLE stemmen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stemvraag_id INTEGER NOT NULL REFERENCES stemvragen(id) ON DELETE CASCADE,
            stemoptie_id INTEGER NOT NULL REFERENCES stemopties(id) ON DELETE CASCADE,
            kiezer_sleutel TEXT NOT NULL,
            naam TEXT,
            opmerking TEXT,
            afgekeurd INTEGER NOT NULL DEFAULT 0,
            datum TEXT NOT NULL,
            UNIQUE(stemvraag_id, kiezer_sleutel, stemoptie_id)
        )"""
    )
    db.execute(
        """INSERT INTO stemmen
               (id, stemvraag_id, stemoptie_id, kiezer_sleutel, naam, opmerking, afgekeurd, datum)
           SELECT id, stemvraag_id, stemoptie_id, kiezer_sleutel, naam, opmerking, afgekeurd, datum
           FROM stemmen_oud"""
    )
    db.execute("DROP TABLE stemmen_oud")
    db.execute("CREATE INDEX IF NOT EXISTS idx_stemmen_vraag ON stemmen(stemvraag_id)")


def _migreer_bieren_backfill(db):
    """De bieren-bibliotheek is nieuw: vul 'm eenmalig met de stemopties die
    al een foto hadden (uit stemmingen die al bestonden voordat deze
    bibliotheek er was), zodat dat werk niet verloren gaat."""
    aantal = db.execute("SELECT COUNT(*) AS n FROM bieren").fetchone()["n"]
    if aantal > 0:
        return
    regels = db.execute(
        """SELECT tekst, afbeelding FROM stemopties
           WHERE afbeelding IS NOT NULL AND afbeelding != ''
           ORDER BY id"""
    ).fetchall()
    for regel in regels:
        db.execute(
            "INSERT OR IGNORE INTO bieren (naam, afbeelding, aangemaakt_op) VALUES (?, ?, ?)",
            (regel["tekst"], regel["afbeelding"], datetime.now().strftime("%Y-%m-%d %H:%M")),
        )


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
            _migreer_kolommen(g.db)
            _migreer_stemmen_meerdere_keuzes(g.db)
            _migreer_categorieen(g.db)
            _migreer_telling_verkoopprijs(g.db)
            _migreer_kassa_afgesloten(g.db)
            _migreer_bieren_backfill(g.db)
            g.db.commit()
            _SCHEMA_TOEGEPAST_VOOR.add(db_pad)
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
                    generate_password_hash(STANDAARD_WACHTWOORD, method=WACHTWOORD_HASH_METHODE),
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            db.commit()


def register_db(app):
    app.teardown_appcontext(close_db)
