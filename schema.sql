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
    besteld_door_id INTEGER REFERENCES gebruikers(id),
    ontvangen_op TEXT,
    referentie TEXT
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
    laatste_login TEXT,
    email TEXT,
    reset_token_hash TEXT,
    reset_token_verloopt TEXT,
    mail_factuur INTEGER NOT NULL DEFAULT 0,
    mail_week_overzicht INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tellingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    naam TEXT,
    gebruiker_id INTEGER REFERENCES gebruikers(id),
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
    gebruiker_id INTEGER REFERENCES gebruikers(id),
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

CREATE TABLE IF NOT EXISTS instellingen (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    notificatie_email TEXT,
    banner_tekst TEXT,
    kassa_stand REAL NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO instellingen (id, notificatie_email) VALUES (1, NULL);

CREATE TABLE IF NOT EXISTS kassa_tellingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    naam TEXT,
    gebruiker_id INTEGER REFERENCES gebruikers(id),
    verwacht_bedrag REAL NOT NULL DEFAULT 0,
    contante_omzet REAL NOT NULL DEFAULT 0,
    geteld_bedrag REAL NOT NULL DEFAULT 0,
    verschil REAL NOT NULL DEFAULT 0,
    aantal_50 INTEGER NOT NULL DEFAULT 0,
    aantal_20 INTEGER NOT NULL DEFAULT 0,
    aantal_10 INTEGER NOT NULL DEFAULT 0,
    aantal_5 INTEGER NOT NULL DEFAULT 0,
    aantal_2 INTEGER NOT NULL DEFAULT 0,
    aantal_1 INTEGER NOT NULL DEFAULT 0,
    aantal_050 INTEGER NOT NULL DEFAULT 0,
    aantal_020 INTEGER NOT NULL DEFAULT 0,
    aantal_010 INTEGER NOT NULL DEFAULT 0,
    aantal_005 INTEGER NOT NULL DEFAULT 0,
    opmerking TEXT,
    afgesloten INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_pogingen (
    naam TEXT PRIMARY KEY,
    mislukte_pogingen INTEGER NOT NULL DEFAULT 0,
    laatste_poging TEXT,
    geblokkeerd_tot TEXT
);

CREATE TABLE IF NOT EXISTS kassa_mutaties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('afdracht', 'toevoeging')),
    bedrag REAL NOT NULL,
    datum TEXT NOT NULL,
    naam TEXT,
    gebruiker_id INTEGER REFERENCES gebruikers(id),
    ontvanger TEXT,
    opmerking TEXT
);

CREATE TABLE IF NOT EXISTS wedstrijden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team TEXT NOT NULL,
    datum TEXT NOT NULL,
    omschrijving TEXT NOT NULL,
    thuis INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS agenda_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    team TEXT
);

CREATE TABLE IF NOT EXISTS weer_voorspelling (
    datum TEXT PRIMARY KEY,
    max_temp REAL,
    neerslag_kans INTEGER,
    weercode INTEGER
);

CREATE INDEX IF NOT EXISTS idx_wedstrijden_datum ON wedstrijden(datum);
CREATE INDEX IF NOT EXISTS idx_mutaties_product ON mutaties(product_id);
CREATE INDEX IF NOT EXISTS idx_mutaties_datum ON mutaties(datum);
CREATE INDEX IF NOT EXISTS idx_bestelregels_bestelling ON bestelregels(bestelling_id);
CREATE INDEX IF NOT EXISTS idx_telling_regels_telling ON telling_regels(telling_id);
CREATE INDEX IF NOT EXISTS idx_kassa_tellingen_datum ON kassa_tellingen(datum);
CREATE INDEX IF NOT EXISTS idx_kassa_mutaties_datum ON kassa_mutaties(datum);
