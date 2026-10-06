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
    mail_club_aanmelding INTEGER NOT NULL DEFAULT 0,
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
    privacy_contact TEXT,
    kassalade_stand REAL NOT NULL DEFAULT 0,
    kluis_stand REAL NOT NULL DEFAULT 0
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

-- Brute-force-bescherming voor /api/tablet-code/controleren (zie
-- routes/auth.py) -- die JSON-API heeft geen gebruikersnaam om op te
-- blokkeren zoals login_pogingen hierboven, dus per IP-adres i.p.v. naam.
CREATE TABLE IF NOT EXISTS tablet_code_pogingen (
    ip_adres TEXT PRIMARY KEY,
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

-- Fysieke telling van de kluis -- zelfde vorm als kassa_tellingen, maar
-- zonder contante_omzet: de kluis heeft geen eigen omzet, het verwachte
-- bedrag is gewoon de op dat moment bekende kluis_stand.
CREATE TABLE IF NOT EXISTS kluis_tellingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    naam TEXT,
    gebruiker_id INTEGER REFERENCES gebruikers(id),
    verwacht_bedrag REAL NOT NULL DEFAULT 0,
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
    goedkeuring_opmerking TEXT,
    geteld_bedrag_voor_correctie REAL,
    geteld_bedrag_gecorrigeerd_door_id INTEGER REFERENCES gebruikers(id),
    geteld_bedrag_gecorrigeerd_door TEXT,
    geteld_bedrag_gecorrigeerd_op TEXT,
    geteld_bedrag_correctie_opmerking TEXT
);

-- Geld dat de kluis in-/uit gaat van/naar buiten de club-boekhouding (bank,
-- penningmeester) -- i.t.t. kassa_mutaties (afdracht/toevoeging), dat de
-- interne overboeking tussen kassalade en kluis is.
CREATE TABLE IF NOT EXISTS kluis_mutaties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('storting', 'opname')),
    bedrag REAL NOT NULL,
    datum TEXT NOT NULL,
    naam TEXT,
    gebruiker_id INTEGER REFERENCES gebruikers(id),
    ontvanger TEXT,
    opmerking TEXT,
    bedrag_voor_correctie REAL,
    gecorrigeerd_door_id INTEGER REFERENCES gebruikers(id),
    gecorrigeerd_door TEXT,
    gecorrigeerd_op TEXT,
    correctie_opmerking TEXT
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

-- Laatst bekende verwachting per dag, ook voor dagen die voorbij zijn (de
-- tabel hierboven wordt elke keer leeggemaakt). Zo kan het voorspelmodel
-- (voorspelling.py) leren hoeveel het weer uitmaakt voor de verkoop.
CREATE TABLE IF NOT EXISTS weer_historie (
    datum TEXT PRIMARY KEY,
    max_temp REAL,
    neerslag_kans INTEGER,
    bijgewerkt_op TEXT
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

-- Losse naam+prijs-varianten die uit 1 product getapt/geschonken worden,
-- bijv. een pitcher (12,00) en een glas (2,00) uit een fust dat zelf niet in
-- zijn geheel verkocht wordt. Heeft een product 1 of meer van deze opties,
-- dan toont het prijzenscherm die losse regels i.p.v. de eigen verkoopprijs
-- van het product (zie _prijzen_categorieen in routes/kiosk.py) -- het
-- product zelf blijft gewoon meetellen/bestellen zoals altijd.
CREATE TABLE IF NOT EXISTS product_prijsopties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES producten(id) ON DELETE CASCADE,
    naam TEXT NOT NULL,
    prijs REAL NOT NULL DEFAULT 0,
    volgorde INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_product_prijsopties_product ON product_prijsopties(product_id);
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
-- signaleer_afwijkende_telling (routes/tellen.py) filtert bij elke
-- tellingopslag op product_id, en deze tabel groeit voor altijd (1 rij per
-- product per telling) -- zonder index wordt die check langzaam trager.
CREATE INDEX IF NOT EXISTS idx_telling_regels_product ON telling_regels(product_id);
CREATE INDEX IF NOT EXISTS idx_kassa_tellingen_datum ON kassa_tellingen(datum);
CREATE INDEX IF NOT EXISTS idx_kassa_mutaties_datum ON kassa_mutaties(datum);
CREATE INDEX IF NOT EXISTS idx_kluis_tellingen_datum ON kluis_tellingen(datum);
CREATE INDEX IF NOT EXISTS idx_kluis_mutaties_datum ON kluis_mutaties(datum);

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

-- Zelfgebouwde sjablonen (drag-and-drop bouwer, zie kiosk_sjabloon_bouwer.html)
-- naast de vaste lay-outs hierboven. elementen is een JSON-array van vrij
-- gepositioneerde onderdelen (titel/tekst/foto/vrije_tekst), zie
-- routes/kiosk.py (_sjabloon_elementen_uit_formulier / _bouw_slides).
CREATE TABLE IF NOT EXISTS kiosk_sjablonen_custom (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL,
    achtergrond_kleur TEXT NOT NULL DEFAULT '#0f1f4d',
    achtergrond_afbeelding TEXT,
    overlay_donker INTEGER NOT NULL DEFAULT 1,
    elementen TEXT NOT NULL DEFAULT '[]',
    aangemaakt_op TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS club_van_20_leden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL,
    aangemaakt_op TEXT NOT NULL
);

-- Club van 20-administratie: 1 rij per lid per seizoen ("2026-2027", loopt
-- van 1 juli t/m 30 juni, zie club_van_20.py). Geen rij voor een seizoen =
-- "niet gevraagd". club_van_20_leden.naam is het naambordje (wat op het
-- scherm staat); voornaam/achternaam/team staan er los naast, zie
-- _migreer_club_van_20_administratie in database.py.
CREATE TABLE IF NOT EXISTS club_van_20_bijdragen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lid_id INTEGER NOT NULL REFERENCES club_van_20_leden(id) ON DELETE CASCADE,
    seizoen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'niet_gevraagd',
    bedrag REAL NOT NULL DEFAULT 0,
    betaald_door TEXT,
    betaalwijze TEXT,
    betaald_op TEXT,
    notitie TEXT,
    bijgewerkt_door TEXT,
    bijgewerkt_op TEXT,
    UNIQUE(lid_id, seizoen)
);
CREATE INDEX IF NOT EXISTS idx_club_van_20_bijdragen_seizoen ON club_van_20_bijdragen(seizoen);

-- Aanmeldingen via de publieke pagina (/club-van-20/aanmelden): een concept
-- dat pas een lid + betaling wordt als een beheerder de betaling heeft
-- gecontroleerd en goedkeurt (zie aanmeldingen.py). naam = wie de aanmelder
-- is (ter controle van de betaling), bordje = wat er op het scherm moet
-- staan, bardienst = bij contant: wie er toen achter de bar stond.
-- verlengt_lid_id = bij een verlenging het bestaande lid (bordje) dat de
-- aanmelder koos; leeg bij een nieuw bordje.
CREATE TABLE IF NOT EXISTS club_van_20_aanmeldingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seizoen TEXT NOT NULL,
    naam TEXT NOT NULL,
    bordje TEXT NOT NULL,
    betaalwijze TEXT NOT NULL,
    bardienst TEXT,
    bedrag REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'nieuw',
    datum TEXT NOT NULL,
    aangemaakt_op TEXT NOT NULL,
    ip_hash TEXT,
    behandeld_door TEXT,
    behandeld_op TEXT,
    opmerking TEXT,
    lid_id INTEGER REFERENCES club_van_20_leden(id) ON DELETE SET NULL,
    verlengt_lid_id INTEGER REFERENCES club_van_20_leden(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_club_van_20_aanmeldingen_status ON club_van_20_aanmeldingen(status);

-- Mislukte pogingen om de voorbeeldcode van het aanmeldformulier in te voeren
-- (geheime knop), per afgeleide IP-code, zodat een korte code niet te raden
-- is door veel te proberen. Rijen ouder dan een dag worden opgeruimd.
CREATE TABLE IF NOT EXISTS club_van_20_voorbeeld_pogingen (
    ip_hash TEXT PRIMARY KEY,
    mislukt INTEGER NOT NULL DEFAULT 0,
    sinds TEXT NOT NULL
);

-- Waar het Club van 20-geld aan besteed wordt (bartafels, sfeerverlichting,
-- ...) -- voor de administratie én de "waar gaat jouw €20 heen"-dia.
-- kosten = werkelijk uitgegeven (NULL = nog niet bekend, dan telt de raming).
CREATE TABLE IF NOT EXISTS club_van_20_projecten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL,
    omschrijving TEXT,
    raming REAL NOT NULL DEFAULT 0,
    kosten REAL,
    status TEXT NOT NULL DEFAULT 'gepland',
    afbeelding TEXT,
    volgorde INTEGER NOT NULL DEFAULT 0,
    toon_op_scherm INTEGER NOT NULL DEFAULT 1,
    afgerond_op TEXT,
    aangemaakt_op TEXT NOT NULL
);

-- Sponsoren met logo voor het kantine scherm en de prijzenlijst ("Mede
-- mogelijk gemaakt door"), los van de algemene dia's in kiosk_sponsoren.
-- Sponsoren met dezelfde groep (bijv. "Zaterdag 1") komen samen op 1 dia;
-- zie sponsoren.py (bouw_sponsor_dias) en routes/sponsoren.py.
CREATE TABLE IF NOT EXISTS kiosk_sponsorlogos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naam TEXT NOT NULL,
    logo TEXT,
    groep TEXT,
    witte_achtergrond INTEGER NOT NULL DEFAULT 1,
    actief INTEGER NOT NULL DEFAULT 1,
    volgorde INTEGER NOT NULL DEFAULT 0,
    aangemaakt_op TEXT NOT NULL
);

-- Vooraf ingeplande bardiensten per specifieke dag (geen wekelijks
-- terugkerend rooster -- de bezetting wisselt elke week). Het prijzenscherm
-- toont de bijpassende rij vanzelf in een gele balk zodra de klok tussen
-- start_tijd en eind_tijd valt, zie kiosk_prijzen_scherm.html.
CREATE TABLE IF NOT EXISTS kiosk_bardiensten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    start_tijd TEXT NOT NULL,
    eind_tijd TEXT NOT NULL,
    namen TEXT NOT NULL,
    aangemaakt_op TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kiosk_bardiensten_datum ON kiosk_bardiensten(datum);

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

-- Standen-dia's op het kantine scherm: per eigen team (poule 'za2'/'za3'/
-- 'o23') een handmatig bijgehouden, gesleepte volgorde van alle clubs in die
-- poule -- geen live koppeling met voetbal.nl, gewoon 1x per week zelf
-- bijwerken (zie kiosk_stand_volgorde_opslaan in routes/kiosk.py).
-- eigen_team markeert welke rij de vereniging zelf is (voor de uitlichting
-- op de dia) -- ten hoogste 1 per poule.
CREATE TABLE IF NOT EXISTS kiosk_stand_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poule TEXT NOT NULL,
    naam TEXT NOT NULL,
    eigen_team INTEGER NOT NULL DEFAULT 0,
    volgorde INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_kiosk_stand_teams_poule ON kiosk_stand_teams(poule, volgorde);

-- Zelf toe te voegen/verwijderen poules voor de standen-dia's (was een
-- hardcoded lijst van precies 3: za2/za3/o23) -- sleutel is de interne,
-- url-vriendelijke verwijzing waar kiosk_stand_teams.poule hierboven naar
-- verwijst (zie club_van_team_naam/_poule_slug in routes/kiosk.py), titel is
-- wat er op de dia/beheerpagina te zien is en vrij aan te passen. Zie
-- _migreer_stand_poules_backfill in database.py voor het eenmalig vullen
-- van de 3 vaste poules die er hiervoor al waren.
CREATE TABLE IF NOT EXISTS kiosk_stand_poules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sleutel TEXT NOT NULL UNIQUE,
    titel TEXT NOT NULL,
    volgorde INTEGER NOT NULL DEFAULT 0
);

-- Herbruikbaar clublogo-register, zelfde opzet als de bieren-bibliotheek
-- hierboven (zie bewaar_bier/bewaar_club_logo in helpers.py): 1 keer een
-- logo uploaden voor bijv. "Oranje Nassau", en elk team van die club (in
-- welke poule dan ook, dit of een volgend seizoen) gebruikt 'm automatisch
-- -- de clubnaam volgt uit de teamnaam via club_van_team_naam() in
-- helpers.py (bijv. "Oranje Nassau 5" en "Oranje Nassau 6" -> "Oranje
-- Nassau"). Gespeeld/Punten staan bewust niet in kiosk_stand_teams: die
-- volgen rechtstreeks uit W/GL/V (3-1-0-systeem), dus geen apart veld dat
-- uit de pas kan gaan lopen.
CREATE TABLE IF NOT EXISTS kiosk_club_logos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    club TEXT NOT NULL COLLATE NOCASE,
    afbeelding TEXT,
    aangemaakt_op TEXT NOT NULL,
    UNIQUE(club)
);

-- Man of the Match-dia (kantine scherm), in de stijl van voetbal.nl maar dan
-- zonder foto's -- elk eigen team staat hier 1x, speler wordt handmatig elke
-- week bijgewerkt (geen live koppeling). Een lege speler betekent "geen MOTM
-- deze week"; dat team slaat de dia dan over, en heeft geen enkel team een
-- speler, dan slaat de hele diashow deze dia over. Zie _bouw_slides en
-- kiosk_sponsoren_leden.html.
CREATE TABLE IF NOT EXISTS kiosk_motm (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team TEXT NOT NULL,
    speler TEXT,
    volgorde INTEGER NOT NULL DEFAULT 0
);

-- 1 rij per paginabezoek, voor Club > Gebruiksstatistieken -- puur intern
-- inzicht in welke onderdelen daadwerkelijk gebruikt worden (en door wie),
-- geen externe trackingdienst. gebruiker_id is bewust ON DELETE SET NULL
-- (i.t.t. de meeste andere gebruiker_id-kolommen hierboven, die geen
-- ON DELETE hebben): een verwijderd account mag deze historie niet blokkeren
-- zoals dat wel gebeurde bij producten/accounts met echte boekingsgeschiedenis
-- (zie routes/producten.py en routes/accounts.py) -- hier is de naam sowieso
-- al niet meer te herleiden na verwijdering, dus NULL is geen verlies.
CREATE TABLE IF NOT EXISTS paginabezoeken (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    gebruiker_id INTEGER REFERENCES gebruikers(id) ON DELETE SET NULL,
    weergave_modus TEXT NOT NULL,
    datum TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paginabezoeken_datum ON paginabezoeken(datum);
CREATE INDEX IF NOT EXISTS idx_paginabezoeken_endpoint ON paginabezoeken(endpoint);

-- Instellingen (1 rij) voor het prijzenscherm zelf -- los van
-- kiosk_scherm_instellingen hierboven, dat gaat over het andere scherm
-- (de dia's). Nu alleen de wedstrijddag-welkomstbanner, zie
-- routes/kiosk.py (_wedstrijddag_welkom).
CREATE TABLE IF NOT EXISTS kiosk_prijzen_instellingen (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    wedstrijddag_welkom_actief INTEGER NOT NULL DEFAULT 1,
    wedstrijddag_welkom_tekst TEXT NOT NULL DEFAULT 'Welkom {tegenstander}!'
);
INSERT OR IGNORE INTO kiosk_prijzen_instellingen (id) VALUES (1);

-- Waar iemand is met de looplijst voor tellen (zie routes/tellen.py), zodat je
-- 'm kunt pauzeren en later (ook na uitloggen, een vergrendelde telefoon of op
-- een ander toestel) weer oppakt. 1 rij per gebruiker; bar en hok zijn
-- JSON-objecten {product_id: aantal} en review is het totaal zodra beide
-- rondes klaar zijn en alleen nog gecontroleerd hoeft te worden. Verdwijnt
-- bij bevestigen, stoppen, opnieuw beginnen of na een paar dagen.
CREATE TABLE IF NOT EXISTS loop_voortgang (
    gebruiker_id INTEGER PRIMARY KEY REFERENCES gebruikers(id) ON DELETE CASCADE,
    fase TEXT NOT NULL DEFAULT 'bar',
    indx INTEGER NOT NULL DEFAULT 0,
    bar TEXT NOT NULL DEFAULT '{}',
    hok TEXT NOT NULL DEFAULT '{}',
    review TEXT,
    bijgewerkt_op TEXT NOT NULL
);

-- Dagen waarop de kantine afwijkt van de vaste verkoopdagen (instellingen.verkoopdagen,
-- standaard woensdag en zaterdag): open=1 is "toch open" (bijv. een wedstrijd op zondag),
-- open=0 is "dicht" (bijv. een vrije zaterdag). Het voorspellen en de weekomzet
-- (zie voorspelling.py) tellen alleen open dagen mee. Ook voor datums in het verleden.
CREATE TABLE IF NOT EXISTS verkoop_uitzonderingen (
    datum TEXT PRIMARY KEY,
    open INTEGER NOT NULL,
    opmerking TEXT
);
