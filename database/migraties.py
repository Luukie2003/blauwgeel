"""Migraties: kolommen en gegevens die zijn toegevoegd nadat de database van een
bestaande installatie al was aangemaakt. CREATE TABLE IF NOT EXISTS (schema.sql)
vult die niet aan, dus dat gebeurt hier, zelfhelend, bij elke start."""

from datetime import date, datetime

from database.seed import SEED_PRODUCTEN
from helpers import club_van_team_naam, voeg_maanden_toe


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
    # Hoeveel keer "overal uitloggen" is gebruikt: een sessie met een oudere versie is niet meer geldig.
    ("gebruikers", "sessie_versie", "INTEGER NOT NULL DEFAULT 0"),
    ("producten", "besteleenheid", "TEXT"),
    ("producten", "besteleenheid_factor", "INTEGER NOT NULL DEFAULT 1"),
    ("producten", "inkoopprijs", "REAL NOT NULL DEFAULT 0"),
    ("producten", "subcategorie", "TEXT"),
    ("gebruikers", "email", "TEXT"),
    ("gebruikers", "reset_token_hash", "TEXT"),
    ("gebruikers", "reset_token_verloopt", "TEXT"),
    ("gebruikers", "mail_factuur", "INTEGER NOT NULL DEFAULT 0"),
    ("gebruikers", "mail_week_overzicht", "INTEGER NOT NULL DEFAULT 0"),
    ("gebruikers", "mail_club_aanmelding", "INTEGER NOT NULL DEFAULT 0"),
    ("instellingen", "banner_tekst", "TEXT"),
    ("instellingen", "privacy_contact", "TEXT"),
    # Weekdagen waarop de kantine verkoopt, maandag = 0 ("2,5" = woensdag en
    # zaterdag), zie voorspelling.lees_verkoopdagen. Afwijkende datums staan in
    # verkoop_uitzonderingen.
    ("instellingen", "verkoopdagen", "TEXT NOT NULL DEFAULT '2,5'"),
    ("instellingen", "kassalade_stand", "REAL NOT NULL DEFAULT 0"),
    ("instellingen", "kluis_stand", "REAL NOT NULL DEFAULT 0"),
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
    ("telling_regels", "geteld_aantal_voor_correctie", "INTEGER"),
    ("telling_regels", "gecorrigeerd_door_id", "INTEGER REFERENCES gebruikers(id)"),
    ("telling_regels", "gecorrigeerd_door", "TEXT"),
    ("telling_regels", "gecorrigeerd_op", "TEXT"),
    ("telling_regels", "correctie_opmerking", "TEXT"),
    ("instellingen", "frituurvet_interval_dagen", "INTEGER NOT NULL DEFAULT 14"),
    # Default bewust "alles" i.p.v. leeg: bestaande vrijwilligers hadden tot nu
    # toe altijd volledige toegang tot Kassa/Keuken/Voorraad/Stemmen (er was
    # geen sectiebeperking), dus deze migratie mag niemand er bij de eerste
    # herstart na de update ineens uit gooien. Een beheerder kan het daarna
    # per account versmallen via Accounts.
    ("gebruikers", "secties", "TEXT NOT NULL DEFAULT 'voorraad,kassa,keuken,stemmen'"),
    ("producten", "auto_inactief_bij_nul", "INTEGER NOT NULL DEFAULT 0"),
    ("producten", "toon_op_kiosk", "INTEGER NOT NULL DEFAULT 0"),
    # Puur voor het prijzenscherm -- een snelle "even geen voorraad meer"
    # markering, los van de echte voorraad/actief-status (zie
    # kiosk_product_uitverkocht_wisselen). Staat de knop weer uit zodra er
    # bijvoorbeeld een nieuw fust is aangesloten.
    ("producten", "kiosk_uitverkocht", "INTEGER NOT NULL DEFAULT 0"),
    ("club_van_20_leden", "status", "TEXT NOT NULL DEFAULT 'actief'"),
    # Losse kolommen i.p.v. alleen een looptijd, zodat een gewijzigde
    # standaard-looptijd (zie kiosk_scherm_instellingen) nooit met
    # terugwerkende kracht de einddatum van bestaande leden verschuift --
    # zie _migreer_club_van_20_datums hieronder voor het eenmalig vullen
    # van bestaande leden.
    ("club_van_20_leden", "startdatum", "TEXT"),
    ("club_van_20_leden", "einddatum", "TEXT"),
    ("kiosk_scherm_instellingen", "club_van_20_looptijd_maanden", "INTEGER NOT NULL DEFAULT 12"),
    # Voor namen die net wat meer aandacht verdienen op het kantine scherm
    # (zie kiosk_lid_bewerken) -- los van de sterren, die volgen automatisch
    # uit de looptijd.
    ("club_van_20_leden", "extra_groot", "INTEGER NOT NULL DEFAULT 0"),
    # Extra weergave-opties per sponsor-/mededelingslide (zie
    # _sponsor_uit_formulier in routes/kiosk.py). custom_sjabloon_id verwijst
    # naar kiosk_sjablonen_custom zodra sjabloon = 'aangepast'; bewust geen
    # FK-constraint (zie kiosk_sjabloon_verwijderen, die referenties zelf
    # opruimt vóór het verwijderen).
    ("kiosk_sponsoren", "overgang", "TEXT NOT NULL DEFAULT 'fade'"),
    ("kiosk_sponsoren", "tekst_grootte", "TEXT NOT NULL DEFAULT 'normaal'"),
    ("kiosk_sponsoren", "achtergrond_afbeelding", "TEXT"),
    ("kiosk_sponsoren", "custom_sjabloon_id", "INTEGER"),
    # Welk scherm het gedeelde /kiosk/tv-scherm nu toont (zie kiosk_tv in
    # routes/kiosk.py) -- 'prijzen' of 'dias'. Puur voor wie nog maar 1
    # fysiek scherm heeft en daarop wil kunnen wisselen met een knop i.p.v.
    # de Chromecast zelf aan te raken; de losse /kiosk/prijzen en
    # /kiosk/scherm blijven hierdoor ongewijzigd.
    ("kiosk_scherm_instellingen", "actief_tv_scherm", "TEXT NOT NULL DEFAULT 'prijzen'"),
    # Optionele override van de categorie-kop waaronder dit product op het
    # prijzenscherm valt -- handig voor een product met prijsopties (bijv.
    # een fust in categorie 'Telling') dat je liever onder een bestaande
    # verkoopcategorie toont (bijv. 'Bier'), zonder de echte categorie (die
    # telmethode/rapportage bepaalt) aan te passen. Leeg = gewoon de eigen
    # categorie, zoals voorheen. Zie _prijzen_categorieen in routes/kiosk.py.
    ("producten", "kiosk_categorie", "TEXT"),
    # Aanvangstijd (Europe/Amsterdam, "UU:MM") uit de agenda-feed, voor zover
    # bekend -- een "hele dag"-event in de ICS-feed heeft geen tijd, dan
    # blijft dit NULL. Zie agenda.py (_parse_ics) en de
    # wedstrijddag-welkomstbanner in routes/kiosk.py.
    ("wedstrijden", "tijd", "TEXT"),
    # afgelast = 1: de wedstrijd gaat niet door. Een afgelaste thuiswedstrijd telt
    # nergens mee: niet in de prognose, de dia's, de welkomstmelding of de
    # kassa-herinnering. afgelast_bron zegt wie dat bepaalde: 'agenda' (de feed
    # meldt het, zie agenda.py) of 'handmatig' (iemand heeft het zelf gezet, ook
    # "toch spelen"); een handmatige keuze overschrijft de synchronisatie nooit.
    ("wedstrijden", "afgelast", "INTEGER NOT NULL DEFAULT 0"),
    ("wedstrijden", "afgelast_bron", "TEXT"),
    # Welke categorie-kop in welke van de 3 vaste kolommen van het
    # prijzenscherm staat, en in welke volgorde -- JSON {"1": [...namen],
    # "2": [...], "3": [...]}, versleept via de drag-and-drop-indeling op
    # kiosk_prijzen_instellingen.html. Zie _categorie_kolommen_indeling in
    # routes/kiosk.py.
    ("kiosk_prijzen_instellingen", "categorie_kolommen", "TEXT NOT NULL DEFAULT '{}'"),
    # Eén door de beheerder gekozen product dat groot en omlijnd uitgelicht
    # wordt op het prijzenscherm (bijv. "Snack van de week"), los van zijn
    # eigen categorie -- NULL = uitgeschakeld. Zie _uitgelicht_product in
    # routes/kiosk.py.
    ("kiosk_prijzen_instellingen", "uitgelicht_product_id", "INTEGER"),
    ("kiosk_prijzen_instellingen", "uitgelicht_titel", "TEXT NOT NULL DEFAULT 'Snack van de week'"),
    # Tijdelijk blokkeren van een account (inloggen geweigerd) zonder het te
    # verwijderen -- i.t.t. verwijderen kan dit altijd, ook als het account
    # nog in boekingen/tellingen/kassa- of kluisgeschiedenis staat. Zie
    # account_actief_wisselen in routes/accounts.py en de check in
    # vereis_login (app.py).
    ("gebruikers", "actief", "INTEGER NOT NULL DEFAULT 1"),
    # 6-cijferige code (gehasht, net als wachtwoord_hash) waarmee iemand
    # zichzelf kan aanmelden op de kiosk-tablet/tv-app (die los van deze
    # website wordt gebouwd) -- geen gebruikersnaam nodig, alleen de code.
    # NULL = nog niet ingesteld; iedereen moet 'm bij de eerste keer
    # inloggen kiezen, zie tablet_code_instellen in routes/auth.py.
    ("gebruikers", "tablet_code_hash", "TEXT"),
    # Oplopende teller: elke keer opgehoogd als iemand (vanuit de
    # kiosk-tablet-app) de wedstrijddag-welkomstmelding wil TESTEN op het
    # prijzenscherm, los van of er nu echt een thuiswedstrijd is. Het
    # scherm herkent een nieuwe waarde via zijn gewone 10s-versiepoll (zie
    # kiosk_prijzen_scherm.html) en toont de melding dan 1x, ongeacht het
    # tijdvak. Zie kiosk_wedstrijddag_welkom_testen in routes/kiosk.py.
    ("kiosk_prijzen_instellingen", "wedstrijddag_test_teller", "INTEGER NOT NULL DEFAULT 0"),
    # Weergaveduur (seconden) van het "komende thuiswedstrijden"-blok op het
    # kantine scherm -- was hardcoded op 10s, maar bij meerdere komende
    # wedstrijden is dat soms te kort om te lezen. Zie _bouw_slides in
    # routes/kiosk.py.
    ("kiosk_scherm_instellingen", "wedstrijden_duur_seconden", "INTEGER NOT NULL DEFAULT 10"),
    # Standen-dia's (zie kiosk_stand_teams hierboven in schema.sql) -- zelfde
    # aan/uit + volgorde + duur-opzet als de andere blokken hierboven.
    ("kiosk_scherm_instellingen", "toon_standen", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "standen_volgorde", "INTEGER NOT NULL DEFAULT 4"),
    ("kiosk_scherm_instellingen", "standen_duur_seconden", "INTEGER NOT NULL DEFAULT 10"),
    # Wedstrijdstatistieken per team-rij, handmatig bijgewerkt (zie
    # kiosk_stand_volgorde_opslaan) -- Gespeeld/Punten staan er bewust niet
    # bij, die volgen rechtstreeks uit W/GL/V (3-1-0-systeem). club is de
    # sleutel naar kiosk_club_logos (zie club_van_team_naam in helpers.py);
    # NULL voor rijen van voor deze migratie, zie _migreer_stand_club_backfill.
    ("kiosk_stand_teams", "club", "TEXT"),
    ("kiosk_stand_teams", "gewonnen", "INTEGER NOT NULL DEFAULT 0"),
    ("kiosk_stand_teams", "gelijk", "INTEGER NOT NULL DEFAULT 0"),
    ("kiosk_stand_teams", "verloren", "INTEGER NOT NULL DEFAULT 0"),
    # Man of the Match-dia (zie kiosk_motm hierboven in schema.sql) -- zelfde
    # aan/uit + volgorde + duur-opzet als de andere blokken hierboven.
    ("kiosk_scherm_instellingen", "toon_motm", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "motm_volgorde", "INTEGER NOT NULL DEFAULT 5"),
    ("kiosk_scherm_instellingen", "motm_duur_seconden", "INTEGER NOT NULL DEFAULT 10"),
    ("kiosk_scherm_instellingen", "motm_titel", "TEXT NOT NULL DEFAULT 'Man of de match van vorig weekend!'"),
    # Uitslag van de wedstrijd (bijv. "3-1"), los van de gekozen speler -- een
    # team toont nu op de dia zodra minstens 1 van de 2 is ingevuld (zie
    # _bouw_slides), dus een uitslag zonder gekozen speler is ook zichtbaar.
    ("kiosk_motm", "uitslag", "TEXT"),
    # Naam van de tegenstander (bijv. "Gruno 6") -- in de stijl van
    # voetbal.nl's wedstrijdpagina toont de dia hiermee ook het logo van de
    # tegenstander, via hetzelfde logo-register als de standen-dia's
    # (club_van_team_naam + kiosk_club_logos in routes/kiosk.py). Het eigen
    # team toont altijd het eigen clublogo (static/logo.png).
    ("kiosk_motm", "tegenstander", "TEXT"),
    # Of het eigen team gewonnen, gelijkgespeeld of verloren heeft ('gewonnen',
    # 'gelijk', 'verloren'). Met een gekozen resultaat zet de dia de uitslag zelf
    # in de juiste volgorde (eigen team links), ongeacht in welke volgorde je de
    # cijfers invoert, bijvoorbeeld zoals voetbal.nl ze noemt (thuisploeg eerst).
    ("kiosk_motm", "resultaat", "TEXT"),
    # Club van 20-module (zie club_van_20.py en routes/club_van_20.py): de
    # weergave op het kantine scherm en de publieke pagina. zichtbaar_seizoenen
    # = hoeveel seizoenen terug een betaling nog "telt" voor het scherm (1 =
    # alleen dit seizoen, 2 = dit of vorig seizoen, 0 = elk actief lid).
    ("kiosk_scherm_instellingen", "club_van_20_kolommen", "INTEGER NOT NULL DEFAULT 4"),
    ("kiosk_scherm_instellingen", "club_van_20_duur_seconden", "INTEGER NOT NULL DEFAULT 12"),
    ("kiosk_scherm_instellingen", "club_van_20_zichtbaar_seizoenen", "INTEGER NOT NULL DEFAULT 2"),
    ("kiosk_scherm_instellingen", "club_van_20_markeer_onbetaald", "INTEGER NOT NULL DEFAULT 0"),
    # Tijdelijke herinnering: t/m onbetaald_tot ("2026-10-18") staan ook leden
    # die dit seizoen nog niet betaald hebben lichtrood op het scherm, uit de
    # laatste onbetaald_seizoenen seizoenen (0 = elk actief lid). Daarna valt
    # het scherm vanzelf terug op zichtbaar_seizoenen. Zie onbetaald_actie().
    ("kiosk_scherm_instellingen", "club_van_20_onbetaald_tot", "TEXT"),
    ("kiosk_scherm_instellingen", "club_van_20_onbetaald_seizoenen", "INTEGER NOT NULL DEFAULT 3"),
    ("kiosk_scherm_instellingen", "club_van_20_lege_vakjes", "INTEGER NOT NULL DEFAULT 1"),
    # Standaard houden de bordjes op elke dia dezelfde grootte (die van een
    # volle dia), ook op een laatste dia met maar een paar namen. Aan = die
    # laatste dia vullen met minder, maar grotere bordjes (zie bouw_slides).
    ("kiosk_scherm_instellingen", "club_van_20_laatste_dia_vullen", "INTEGER NOT NULL DEFAULT 0"),
    # Hoeveel betaalde seizoenen een ster opleveren (3 = elke 3 seizoenen lid
    # 1 ster, zie sterren_voor in club_van_20.py). 1 = een ster per seizoen.
    ("kiosk_scherm_instellingen", "club_van_20_seizoenen_per_ster", "INTEGER NOT NULL DEFAULT 3"),
    # Vanaf hoeveel sterren een bordje glanzend metaalgoud is (met een lichtstreep
    # die af en toe over het bordje glijdt). Daaronder gewoon wit.
    ("kiosk_scherm_instellingen", "club_van_20_glans_vanaf_sterren", "INTEGER NOT NULL DEFAULT 2"),
    # Aankondiging met aftelklok bovenaan de publieke Club van 20-pagina (waar
    # de QR-code van de wervingsdia heen wijst), bijv. "Vanaf woensdag kun
    # je verlengen!". aftellen_tot is een lokale Amsterdamse tijd
    # ("2026-10-05T00:00"); na dat moment verschijnt na_tekst, of verdwijnt
    # de aankondiging als die leeg is. Zie aankondiging() in club_van_20.py.
    ("kiosk_scherm_instellingen", "club_van_20_aankondiging_tekst", "TEXT"),
    ("kiosk_scherm_instellingen", "club_van_20_aankondiging_aftellen_tot", "TEXT"),
    ("kiosk_scherm_instellingen", "club_van_20_aankondiging_na_tekst", "TEXT"),
    # De aftelklok van de aankondiging hierboven ook op de wervingsdia van
    # het kantine scherm tonen (zie bouw_slides in club_van_20.py).
    ("kiosk_scherm_instellingen", "club_van_20_aankondiging_op_dia", "INTEGER NOT NULL DEFAULT 1"),
    # Sponsoren met logo (kiosk_sponsorlogos): hoe ze tussen de dia's van het
    # kantine scherm en over de prijzenlijst heen komen. Zie sponsoren.py.
    ("kiosk_scherm_instellingen", "sponsors_kop", "TEXT NOT NULL DEFAULT 'Mede mogelijk gemaakt door'"),
    ("kiosk_scherm_instellingen", "sponsors_kop_meervoud", "TEXT NOT NULL DEFAULT ''"),
    ("kiosk_scherm_instellingen", "club_van_20_aanmelden_aan", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "club_van_20_voorbeeldcode", "TEXT"),
    ("club_van_20_aanmeldingen", "verlengt_lid_id", "INTEGER REFERENCES club_van_20_leden(id) ON DELETE SET NULL"),
    ("kiosk_scherm_instellingen", "club_van_20_bordje_max_tekens", "INTEGER NOT NULL DEFAULT 24"),
    ("kiosk_scherm_instellingen", "sponsors_toon_groepsnaam", "INTEGER NOT NULL DEFAULT 0"),
    ("kiosk_scherm_instellingen", "sponsors_achtergrond", "TEXT"),
    ("kiosk_scherm_instellingen", "sponsors_logos_per_dia", "INTEGER NOT NULL DEFAULT 4"),
    ("kiosk_scherm_instellingen", "sponsors_toon_dias", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "sponsors_elke_dias", "INTEGER NOT NULL DEFAULT 2"),
    ("kiosk_scherm_instellingen", "sponsors_duur_seconden", "INTEGER NOT NULL DEFAULT 8"),
    ("kiosk_scherm_instellingen", "sponsors_toon_prijzen", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "sponsors_prijzen_interval", "INTEGER NOT NULL DEFAULT 60"),
    ("kiosk_scherm_instellingen", "sponsors_prijzen_duur", "INTEGER NOT NULL DEFAULT 8"),
    # Wanneer een lid gearchiveerd is (status 'inactief': niet meer op het
    # scherm, betaalhistorie blijft bewaard), zie club_van_20_lid_archiveren.
    ("club_van_20_leden", "gearchiveerd_op", "TEXT"),
    ("kiosk_scherm_instellingen", "club_van_20_bedrag", "REAL NOT NULL DEFAULT 20"),
    ("kiosk_scherm_instellingen", "club_van_20_achtergrond", "TEXT"),
    ("kiosk_scherm_instellingen", "club_van_20_toon_teller", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "club_van_20_toon_teams", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "club_van_20_toon_nieuw", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "club_van_20_toon_werving", "INTEGER NOT NULL DEFAULT 1"),
    # "Leden? Steun de club!": dia met de leden die dit seizoen nog niet betaald hebben maar eerder wel.
    ("kiosk_scherm_instellingen", "club_van_20_toon_onbetaald", "INTEGER NOT NULL DEFAULT 1"),
    ("kiosk_scherm_instellingen", "club_van_20_onbetaald_per_slide", "INTEGER NOT NULL DEFAULT 12"),
    (
        "kiosk_scherm_instellingen",
        "club_van_20_werving_tekst",
        "TEXT NOT NULL DEFAULT 'Vraag naar de mogelijkheden bij de bar'",
    ),
    ("kiosk_scherm_instellingen", "club_van_20_betaallink", "TEXT"),
    (
        "kiosk_scherm_instellingen",
        "club_van_20_verzoek_tekst",
        "TEXT NOT NULL DEFAULT 'Hoi {voornaam}! Het nieuwe seizoen ({seizoen}) van de Club van 20 is begonnen. "
        "Doe je weer mee voor €{bedrag}? Dan komt \"{naambordje}\" weer op het scherm in de kantine. {betaallink}'",
    ),
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


def _migreer_keuken_categorie(db):
    """Keuken is een eigen navigatie-onderdeel geworden (voorraad +
    instellingen), dus die categorie moet altijd bestaan -- anders is
    'm/producten/nieuw?categorie=Keuken' vanuit /keuken kapot voor een
    verse installatie. Idempotent (OR IGNORE), dus dit doet niets meer
    zodra de categorie er eenmaal staat."""
    db.execute("INSERT OR IGNORE INTO categorieen (naam, verkoopprijs_verplicht) VALUES ('Keuken', 1)")
    db.execute("INSERT OR IGNORE INTO subcategorieen (categorie, naam) VALUES ('Keuken', 'Frituursnacks')")
    db.execute("INSERT OR IGNORE INTO subcategorieen (categorie, naam) VALUES ('Keuken', 'Gehaktballen')")


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


def _migreer_kluis_kassalade(db):
    """instellingen.kassa_stand wordt hernoemd naar kassalade_stand nu de
    kluis een eigen, gescheiden stand krijgt -- kassa_stand was tot nu toe de
    enige pot en die naam dekt de lading niet meer zodra er twee zijn.
    RENAME COLUMN behoudt de bestaande waarde vanzelf (in tegenstelling tot
    een gewone kolom-migratie via KOLOM_MIGRATIES, die 'm terug op de
    default 0 zou zetten). Moet daarom vóór _migreer_kolommen draaien: die
    zou anders zelf al een lege kassalade_stand-kolom aanmaken voordat deze
    functie de kans krijgt om 'm van de oude kolom te voorzien."""
    bestaande = {row["name"] for row in db.execute("PRAGMA table_info(instellingen)")}
    if "kassa_stand" in bestaande and "kassalade_stand" not in bestaande:
        db.execute("ALTER TABLE instellingen RENAME COLUMN kassa_stand TO kassalade_stand")


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


def _migreer_stand_club_backfill(db):
    """club is nieuw op kiosk_stand_teams (voor de koppeling met het
    logo-register kiosk_club_logos) -- vul 'm eenmalig in voor rijen die er
    al stonden voordat dat veld bestond. Nieuwe rijen krijgen 'm al meteen
    bij het toevoegen (zie kiosk_stand_team_nieuw), dus die komen hier nooit
    doorheen."""
    for regel in db.execute("SELECT id, naam FROM kiosk_stand_teams WHERE club IS NULL").fetchall():
        db.execute(
            "UPDATE kiosk_stand_teams SET club = ? WHERE id = ?",
            (club_van_team_naam(regel["naam"]), regel["id"]),
        )


def _migreer_stand_poules_backfill(db):
    """kiosk_stand_poules is nieuw: poules waren hiervoor een hardcoded lijst
    van precies 3 (za2/za3/o23, zie STAND_POULES in routes/kiosk.py) --
    zolang de tabel nog leeg is (dus alleen de allereerste keer na deze
    migratie) worden die 3 er eenmalig in gezet. sleutel blijft gelijk aan
    de oude poule-waarden op kiosk_stand_teams, dus bestaande teams/rijen
    hoeven zelf niet aangepast te worden."""
    if db.execute("SELECT COUNT(*) AS n FROM kiosk_stand_poules").fetchone()["n"]:
        return
    for i, (sleutel, titel) in enumerate([("za2", "ZA 2"), ("za3", "ZA 3"), ("o23", "O23")]):
        db.execute(
            "INSERT INTO kiosk_stand_poules (sleutel, titel, volgorde) VALUES (?, ?, ?)",
            (sleutel, titel, i),
        )


def _migreer_club_van_20_datums(db):
    """startdatum/einddatum zijn nieuw: vul ze eenmalig voor bestaande leden
    (van vóór deze functie) met hun aanmaakdatum als startdatum en de op
    dat moment ingestelde standaard-looptijd, zodat ze niet met een lege
    looptijd in de lijst komen te staan. Nieuwe leden krijgen hun datums al
    meteen bij aanmaken (zie kiosk_lid_nieuw), dus die komen hier nooit
    doorheen."""
    te_vullen = db.execute(
        "SELECT id, aangemaakt_op FROM club_van_20_leden WHERE startdatum IS NULL"
    ).fetchall()
    if not te_vullen:
        return
    looptijd_rij = db.execute(
        "SELECT club_van_20_looptijd_maanden FROM kiosk_scherm_instellingen WHERE id = 1"
    ).fetchone()
    maanden = looptijd_rij["club_van_20_looptijd_maanden"] if looptijd_rij else 12
    for lid in te_vullen:
        start = lid["aangemaakt_op"][:10] if lid["aangemaakt_op"] else date.today().isoformat()
        db.execute(
            "UPDATE club_van_20_leden SET startdatum = ?, einddatum = ? WHERE id = ?",
            (start, voeg_maanden_toe(start, maanden), lid["id"]),
        )


def _migreer_club_van_20_administratie(db):
    """De Club van 20 kreeg een echte administratie: per lid voornaam/
    achternaam/team los van het naambordje (club_van_20_leden.naam), en de
    betalingen per seizoen in club_van_20_bijdragen i.p.v. 1 status + start/
    einddatum. Bewust GEEN gewone kolom-migratie: precies op het moment dat
    de nieuwe kolommen voor het eerst worden aangemaakt, zetten we eenmalig
    de oude gegevens om -- een 'actief' lid krijgt een betaalde bijdrage in
    het seizoen van zijn startdatum, een 'niet betaald'-lid een openstaand
    verzoek ('gevraagd') voor het huidige seizoen en weer status 'actief'
    (niet betaald is nu een eigenschap van het seizoen, niet van het lid).
    Draait daarna nooit meer, ook niet als iemand alle bijdragen wist."""
    from club_van_20 import seizoen_van_datum, huidig_seizoen

    bestaande = {row["name"] for row in db.execute("PRAGMA table_info(club_van_20_leden)")}
    if "voornaam" in bestaande:
        return
    for kolom, definitie in [
        ("voornaam", "TEXT"),
        ("achternaam", "TEXT"),
        ("team", "TEXT"),
        ("telefoon", "TEXT"),
        ("email", "TEXT"),
        ("notitie", "TEXT"),
        ("eerdere_seizoenen", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        db.execute(f"ALTER TABLE club_van_20_leden ADD COLUMN {kolom} {definitie}")
    nu = datetime.now().strftime("%Y-%m-%d %H:%M")
    for lid in db.execute("SELECT * FROM club_van_20_leden").fetchall():
        if lid["status"] == "actief":
            seizoen = seizoen_van_datum(lid["startdatum"] or (lid["aangemaakt_op"] or "")[:10] or None)
            db.execute(
                """INSERT OR IGNORE INTO club_van_20_bijdragen
                   (lid_id, seizoen, status, bedrag, betaald_op, bijgewerkt_door, bijgewerkt_op)
                   VALUES (?, ?, 'betaald', 20, ?, 'omzetting', ?)""",
                (lid["id"], seizoen, lid["startdatum"], nu),
            )
        elif lid["status"] == "niet_betaald":
            db.execute(
                """INSERT OR IGNORE INTO club_van_20_bijdragen
                   (lid_id, seizoen, status, bedrag, bijgewerkt_door, bijgewerkt_op)
                   VALUES (?, ?, 'gevraagd', 0, 'omzetting', ?)""",
                (lid["id"], huidig_seizoen(), nu),
            )
    db.execute("UPDATE club_van_20_leden SET status = 'actief' WHERE status = 'niet_betaald'")


def migreer_alles(db):
    """Past alle migraties toe, in de volgorde waarin ze zijn ontstaan (alle zijn
    zelfhelend: ze doen niets als het al gebeurd is)."""
    _migreer_kluis_kassalade(db)
    _migreer_kolommen(db)
    _migreer_stemmen_meerdere_keuzes(db)
    _migreer_categorieen(db)
    _migreer_keuken_categorie(db)
    _migreer_telling_verkoopprijs(db)
    _migreer_kassa_afgesloten(db)
    _migreer_bieren_backfill(db)
    _migreer_club_van_20_datums(db)
    _migreer_club_van_20_administratie(db)
    _migreer_stand_club_backfill(db)
    _migreer_stand_poules_backfill(db)
