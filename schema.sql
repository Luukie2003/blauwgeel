-- Voorraadbeheer database schema

CREATE TABLE IF NOT EXISTS producten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artikelcode TEXT,
    naam TEXT NOT NULL,
    categorie TEXT NOT NULL DEFAULT 'Overig',
    subcategorie TEXT,
    eenheid TEXT NOT NULL DEFAULT 'stuks',
    voorraad INTEGER NOT NULL DEFAULT 0,
    min_voorraad INTEGER NOT NULL DEFAULT 0,
    bestel_hoeveelheid INTEGER NOT NULL DEFAULT 0,
    verkoopprijs REAL NOT NULL DEFAULT 0,
    inkoopprijs REAL NOT NULL DEFAULT 0,
    actief INTEGER NOT NULL DEFAULT 1,
    besteleenheid TEXT,
    besteleenheid_factor INTEGER NOT NULL DEFAULT 1,
    opmerking TEXT
);

CREATE TABLE IF NOT EXISTS bestellingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'besteld' CHECK (status IN ('besteld', 'ontvangen')),
    aangemaakt_op TEXT NOT NULL,
    besteld_door TEXT,
    ontvangen_op TEXT
);

CREATE TABLE IF NOT EXISTS bestelregels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bestelling_id INTEGER NOT NULL REFERENCES bestellingen(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES producten(id),
    aantal_besteld INTEGER NOT NULL,
    aantal_ontvangen INTEGER
);

CREATE TABLE IF NOT EXISTS gebruikers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL UNIQUE,
    wachtwoord_hash TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'beheerder' CHECK (rol IN ('beheerder', 'vrijwilliger')),
    aangemaakt_op TEXT NOT NULL,
    laatste_login TEXT
);

CREATE TABLE IF NOT EXISTS tellingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    naam TEXT,
    opmerking TEXT
);

CREATE TABLE IF NOT EXISTS telling_regels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telling_id INTEGER NOT NULL REFERENCES tellingen(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES producten(id),
    voorraad_voor INTEGER NOT NULL,
    geteld_aantal INTEGER NOT NULL,
    verkocht INTEGER NOT NULL DEFAULT 0,
    correctie INTEGER NOT NULL DEFAULT 0,
    verkoopprijs REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mutaties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES producten(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('in', 'uit')),
    aantal INTEGER NOT NULL,
    datum TEXT NOT NULL,
    naam TEXT,
    opmerking TEXT,
    bestelling_id INTEGER REFERENCES bestellingen(id),
    telling_id INTEGER REFERENCES tellingen(id)
);

CREATE TABLE IF NOT EXISTS categorieen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS subcategorieen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categorie TEXT NOT NULL,
    naam TEXT NOT NULL,
    UNIQUE(categorie, naam)
);

CREATE TABLE IF NOT EXISTS mededelingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tekst TEXT NOT NULL,
    naam TEXT,
    datum TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mutaties_product ON mutaties(product_id);
CREATE INDEX IF NOT EXISTS idx_mutaties_datum ON mutaties(datum);
CREATE INDEX IF NOT EXISTS idx_bestelregels_bestelling ON bestelregels(bestelling_id);
CREATE INDEX IF NOT EXISTS idx_telling_regels_telling ON telling_regels(telling_id);
