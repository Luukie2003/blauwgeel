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
    aantal_ontvangen INTEGER,
    manco INTEGER NOT NULL DEFAULT 0
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
    mail_week_overzicht INTEGER NOT NULL DEFAULT 0,
    secties TEXT NOT NULL DEFAULT 'voorraad,kassa,keuken,stemmen'
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
    naam TEXT NOT NULL UNIQUE,
    verkoopprijs_verplicht INTEGER NOT NULL DEFAULT 1
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
    datum TEXT NOT NULL,
    urgent INTEGER NOT NULL DEFAULT 0,
    afgehandeld INTEGER NOT NULL DEFAULT 0,
    afgehandeld_door TEXT,
    afgehandeld_op TEXT
);

-- Losse inkopen buiten de vaste voorraad om (bijv. schoonmaakspullen),
-- niet gekoppeld aan een product uit de producten-tabel.
CREATE TABLE IF NOT EXISTS boodschappen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tekst TEXT NOT NULL,
    aangemaakt_door TEXT,
    aangemaakt_op TEXT NOT NULL,
    afgevinkt INTEGER NOT NULL DEFAULT 0,
    afgevinkt_door TEXT,
    afgevinkt_op TEXT
);

-- Log van frituurvet-vervangingen, voor de herinnering op het dashboard.
CREATE TABLE IF NOT EXISTS frituurvet_vervangingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    naam TEXT,
    gebruiker_id INTEGER REFERENCES gebruikers(id),
    opmerking TEXT
);

CREATE TABLE IF NOT EXISTS mededeling_opmerkingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mededeling_id INTEGER NOT NULL REFERENCES mededelingen(id) ON DELETE CASCADE,
    tekst TEXT NOT NULL,
    naam TEXT,
    gebruiker_id INTEGER REFERENCES gebruikers(id),
    datum TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mededeling_opmerkingen_mededeling ON mededeling_opmerkingen(mededeling_id);

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
    afgesloten INTEGER NOT NULL DEFAULT 0,
    goedgekeurd_door_id INTEGER REFERENCES gebruikers(id),
    goedgekeurd_door TEXT,
    goedgekeurd_op TEXT,
    goedkeuring_opmerking TEXT
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

CREATE TABLE IF NOT EXISTS prijs_geschiedenis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES producten(id) ON DELETE CASCADE,
    veld TEXT NOT NULL CHECK (veld IN ('verkoopprijs', 'inkoopprijs')),
    oude_prijs REAL NOT NULL,
    nieuwe_prijs REAL NOT NULL,
    datum TEXT NOT NULL,
    naam TEXT,
    gebruiker_id INTEGER REFERENCES gebruikers(id)
);

CREATE INDEX IF NOT EXISTS idx_prijs_geschiedenis_product ON prijs_geschiedenis(product_id);
CREATE INDEX IF NOT EXISTS idx_wedstrijden_datum ON wedstrijden(datum);
-- Voorkomt dubbele rijen als dezelfde wedstrijd bij een volgende ververs-
-- ronde opnieuw uit de feed komt (agenda.py gebruikt hierdoor veilig
-- INSERT OR IGNORE, zodat gespeelde wedstrijden als geschiedenis blijven
-- staan in plaats van verwijderd te worden).
CREATE UNIQUE INDEX IF NOT EXISTS idx_wedstrijden_uniek ON wedstrijden(team, datum, omschrijving);
CREATE INDEX IF NOT EXISTS idx_mutaties_product ON mutaties(product_id);
CREATE INDEX IF NOT EXISTS idx_mutaties_datum ON mutaties(datum);
CREATE INDEX IF NOT EXISTS idx_bestelregels_bestelling ON bestelregels(bestelling_id);
CREATE INDEX IF NOT EXISTS idx_telling_regels_telling ON telling_regels(telling_id);
CREATE INDEX IF NOT EXISTS idx_kassa_tellingen_datum ON kassa_tellingen(datum);
CREATE INDEX IF NOT EXISTS idx_kassa_mutaties_datum ON kassa_mutaties(datum);

-- ---------- Stemmen ----------

CREATE TABLE IF NOT EXISTS stemvragen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titel TEXT NOT NULL,
    omschrijving TEXT,
    aangemaakt_op TEXT NOT NULL,
    aangemaakt_door TEXT,
    actief INTEGER NOT NULL DEFAULT 1,
    sluit_op TEXT,
    toon_uitslag INTEGER NOT NULL DEFAULT 1,
    opmerking_toegestaan INTEGER NOT NULL DEFAULT 0,
    aantal_keuzes INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stemopties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stemvraag_id INTEGER NOT NULL REFERENCES stemvragen(id) ON DELETE CASCADE,
    tekst TEXT NOT NULL,
    volgorde INTEGER NOT NULL DEFAULT 0,
    afbeelding TEXT
);

CREATE TABLE IF NOT EXISTS stemmen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stemvraag_id INTEGER NOT NULL REFERENCES stemvragen(id) ON DELETE CASCADE,
    stemoptie_id INTEGER NOT NULL REFERENCES stemopties(id) ON DELETE CASCADE,
    kiezer_sleutel TEXT NOT NULL,
    naam TEXT,
    opmerking TEXT,
    afgekeurd INTEGER NOT NULL DEFAULT 0,
    datum TEXT NOT NULL,
    UNIQUE(stemvraag_id, kiezer_sleutel, stemoptie_id)
);

CREATE INDEX IF NOT EXISTS idx_stemopties_vraag ON stemopties(stemvraag_id);
CREATE INDEX IF NOT EXISTS idx_stemmen_vraag ON stemmen(stemvraag_id);

-- Bibliotheek van eerder gebruikte stemopties (bijv. biertjes met foto), zodat
-- ze bij een volgende stemming hergebruikt kunnen worden zonder opnieuw te
-- moeten uploaden.
CREATE TABLE IF NOT EXISTS bieren (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL COLLATE NOCASE,
    afbeelding TEXT,
    aangemaakt_op TEXT NOT NULL,
    UNIQUE(naam)
);

-- Verbruiksvoorwerpen: dingen als bakjes/servetten die wel een schaplabel
-- nodig hebben, maar geen echte voorraadproducten zijn (geen voorraad, geen
-- bestellijst-regel) -- puur om te kunnen printen en om ze desgewenst als
-- losse tekstmelding op de bestellijst te zetten (zie bestellijst_meldingen).
CREATE TABLE IF NOT EXISTS verbruiksvoorwerpen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL,
    categorie TEXT,
    aangemaakt_op TEXT NOT NULL
);

-- Meldingen voor de bestellijst die niet uit de gewone voorraadberekening
-- komen: een bezoeker die zonder account de QR-code van een product scant
-- en op "Melden voor bestellijst" drukt (product_id gezet, bron 'qr_scan'),
-- of een verbruiksvoorwerp dat een beheerder handmatig op de bestellijst
-- zet (product_id leeg, tekst gezet, bron 'verbruiksvoorwerp'). Blijft
-- staan tot een beheerder 'm afhandelt (zelfde patroon als mededelingen).
CREATE TABLE IF NOT EXISTS bestellijst_meldingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES producten(id) ON DELETE CASCADE,
    tekst TEXT,
    bron TEXT NOT NULL DEFAULT 'qr_scan',
    aangemaakt_op TEXT NOT NULL,
    afgehandeld INTEGER NOT NULL DEFAULT 0,
    afgehandeld_door TEXT,
    afgehandeld_op TEXT
);

-- ---------- Kantine Kiosk ----------
-- Losstaande TV-schermen (Chromecast) zonder login: prijzenscherm (welke
-- producten getoond worden staat op producten.toon_op_kiosk, zie
-- KOLOM_MIGRATIES in database.py) en het kantine scherm (diashow van
-- sponsoren + Club van 20-leden + wedstrijden).

-- Sponsor-/reclame-slides. sjabloon bepaalt de layout op het kantine scherm
-- (zie de vaste sjabloon-sleutels in routes/kiosk.py).
CREATE TABLE IF NOT EXISTS kiosk_sponsoren (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sjabloon TEXT NOT NULL DEFAULT 'afbeelding_volledig',
    titel TEXT,
    tekst TEXT,
    afbeelding TEXT,
    weergave_duur_seconden INTEGER NOT NULL DEFAULT 8,
    volgorde INTEGER NOT NULL DEFAULT 0,
    actief INTEGER NOT NULL DEFAULT 1,
    aangemaakt_op TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kiosk_sponsoren_volgorde ON kiosk_sponsoren(volgorde);

CREATE TABLE IF NOT EXISTS club_van_20_leden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL,
    aangemaakt_op TEXT NOT NULL
);

-- Losse product-acties voor het prijzenscherm (bijv. "happy hour"): een
-- korte, opvallende pop-up die af en toe over de prijslijst heen verschijnt.
-- Gebruikt de naam/foto/prijs van het gekoppelde product zelf, geen eigen
-- afbeelding nodig -- zie routes/kiosk.py (kiosk_prijzen_scherm).
CREATE TABLE IF NOT EXISTS kiosk_acties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES producten(id) ON DELETE CASCADE,
    tekst TEXT,
    actief INTEGER NOT NULL DEFAULT 1,
    aangemaakt_op TEXT NOT NULL
);

-- Instellingen (1 rij) voor hoe het kantine scherm is opgebouwd: welke
-- blokken meedraaien in de diashow, in welke volgorde, en hoe het Club van
-- 20-blok wordt weergegeven. Zelfde opzet als de instellingen-tabel hierboven.
CREATE TABLE IF NOT EXISTS kiosk_scherm_instellingen (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    toon_sponsoren INTEGER NOT NULL DEFAULT 1,
    sponsoren_volgorde INTEGER NOT NULL DEFAULT 1,
    toon_club_van_20 INTEGER NOT NULL DEFAULT 1,
    club_van_20_volgorde INTEGER NOT NULL DEFAULT 2,
    club_van_20_titel TEXT NOT NULL DEFAULT 'Club van 20',
    club_van_20_namen_per_slide INTEGER NOT NULL DEFAULT 40,
    toon_wedstrijden INTEGER NOT NULL DEFAULT 1,
    wedstrijden_volgorde INTEGER NOT NULL DEFAULT 3
);
INSERT OR IGNORE INTO kiosk_scherm_instellingen (id) VALUES (1);

-- Livestream op het prijzenscherm (bijv. een thuiswedstrijd). Reactief: het
-- prijzenscherm zelf valt terug op de prijslijst zodra de stream een fout
-- geeft, stopt, of vastloopt (zie kiosk_prijzen_scherm.html en
-- kiosk_stream_uitschakelen in routes/kiosk.py) -- geen planning nodig, en
-- een vergeten "weer uitzetten" trekt zichzelf recht.
CREATE TABLE IF NOT EXISTS kiosk_stream (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    stream_url TEXT,
    actief INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO kiosk_stream (id) VALUES (1);
