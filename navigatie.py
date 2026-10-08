"""De zijbalk: welke groepen en pagina's er in het menu staan, en welke daarvan
bij welke sectie horen, plus het kortere menu van de handterminal-weergave.

Puur gegevens (geen code). Een nieuwe pagina in het menu: voeg een item toe aan
NAV_ITEMS (groep, endpoints, url_endpoint, label)."""

# Voor het filteren van de zijbalk: welke navigatiegroep hoort bij welke
# sectie. "Start" en "Rapporten" staan hier bewust niet in -- die blijven
# voor iedereen zichtbaar, net als het vroegere "Algemeen".
NAV_GROEP_SECTIE = {
    "Voorraad": "voorraad",
    "Tellen": "voorraad",
    "Bestellen": "voorraad",
    "Assortiment": "voorraad",
    "Kassa": "kassa",
    "Keuken": "keuken",
    "Stemmen": "stemmen",
    "Kantine-tv": "kantine_tv",
    "Club van 20": "club_van_20",
}
# Uitzondering per los NAV-item (i.p.v. de hele groep) op NAV_GROEP_SECTIE/
# NAV_GROEP_ALLEEN_BEHEERDER hieronder -- voor een item dat wél sectie-
# gebonden is terwijl de rest van zijn zijbalkgroep beheerder-only blijft
# (zie "club" hierboven: Club instellingen is delegeerbaar, Accounts/
# Back-ups/Instellingen in dezelfde groep niet).
NAV_ITEM_SECTIE = {
    "club_instellingen": "club",
}

NAV_ITEMS = [
    {
        "groep": "Start",
        "endpoints": ["dashboard"],
        "url_endpoint": "dashboard",
        "label": "Overzicht",
    },
    {
        "groep": "Start",
        "endpoints": ["bijzonderheden"],
        "url_endpoint": "bijzonderheden",
        "label": "Prikbord",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["voorraadoverzicht"],
        "url_endpoint": "voorraadoverzicht",
        "label": "Voorraadoverzicht",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["boeken", "levering_inboeken"],
        "url_endpoint": "boeken",
        "label": "In/uit boeken",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["geschiedenis"],
        "url_endpoint": "geschiedenis",
        "label": "Mutatieoverzicht",
    },
    {
        "groep": "Tellen",
        "endpoints": [
            "tellen",
            "tellen_lopen",
            "tellen_lopen_starten",
            "tellen_lopen_hervatten",
            "tellen_lopen_controleren",
        ],
        "url_endpoint": "tellen",
        "label": "Voorraad tellen",
    },
    {
        "groep": "Tellen",
        "endpoints": ["tellingen_overzicht", "telling_detail", "tellingen_gecombineerd_pdf"],
        "url_endpoint": "tellingen_overzicht",
        "label": "Tellingen",
    },
    {
        "groep": "Bestellen",
        "endpoints": ["bestellijst", "bestelling_aanmaken", "bestelling_nieuw", "bestelling_inboeken"],
        "url_endpoint": "bestellijst",
        "label": "Bestellijst",
    },
    {
        "groep": "Bestellen",
        "endpoints": ["prognose_pagina"],
        "url_endpoint": "prognose_pagina",
        "label": "Prognose",
    },
    {
        "groep": "Bestellen",
        "endpoints": ["boodschappenlijst"],
        "url_endpoint": "boodschappenlijst",
        "label": "Boodschappenlijst",
    },
    {
        "groep": "Assortiment",
        "endpoints": [
            "producten_lijst",
            "product_nieuw",
            "product_bewerken",
            "categorieen_lijst",
            "producten_bulk_bewerken",
        ],
        "url_endpoint": "producten_lijst",
        "label": "Producten",
    },
    {
        "groep": "Assortiment",
        "endpoints": ["verbruiksvoorwerpen_lijst"],
        "url_endpoint": "verbruiksvoorwerpen_lijst",
        "label": "Verbruiksvoorwerpen",
    },
    {
        "groep": "Kassa",
        "endpoints": [
            "kassa_tellen",
            "kassa_telling_detail",
            "kassa_telling_bewerken",
            "kassa_telling_goedkeuren",
            "kassa_telling_pdf",
            "kassa_telling_heropenen",
        ],
        "url_endpoint": "kassa_tellen",
        "label": "Kassa tellen",
    },
    {
        "groep": "Kassa",
        "endpoints": ["kassa_geschiedenis"],
        "url_endpoint": "kassa_geschiedenis",
        "label": "Kassa geschiedenis",
    },
    {
        "groep": "Kassa",
        "endpoints": ["kassa_mutatie_nieuw"],
        "url_endpoint": "kassa_mutatie_nieuw",
        "label": "Afdracht / toevoeging",
    },
    {
        "groep": "Kluis",
        "endpoints": [
            "kluis_tellen",
            "kluis_telling_detail",
            "kluis_telling_bewerken",
            "kluis_telling_goedkeuren",
            "kluis_telling_heropenen",
        ],
        "url_endpoint": "kluis_tellen",
        "label": "Kluis tellen",
    },
    {
        "groep": "Kluis",
        "endpoints": ["kluis_geschiedenis"],
        "url_endpoint": "kluis_geschiedenis",
        "label": "Kluis geschiedenis",
    },
    {
        "groep": "Kluis",
        "endpoints": ["kluis_mutatie_nieuw"],
        "url_endpoint": "kluis_mutatie_nieuw",
        "label": "Storting / opname",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_voorraad"],
        "url_endpoint": "keuken_voorraad",
        "label": "Voorraad",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_instellingen"],
        "url_endpoint": "keuken_instellingen",
        "label": "Instellingen",
    },
    {
        "groep": "Kantine-tv",
        "endpoints": ["kiosk_hub"],
        "url_endpoint": "kiosk_hub",
        "label": "Overzicht",
    },
    {
        "groep": "Kantine-tv",
        "endpoints": [
            "kiosk_prijzen_instellingen",
            "kiosk_wedstrijddag_welkom_instellingen",
            "kiosk_categorie_kolommen_instellingen",
            "kiosk_uitgelicht_product_instellingen",
            "kiosk_acties",
            "kiosk_actie_nieuw",
            "kiosk_actie_bewerken",
            "kiosk_bardienst",
            "kiosk_bardienst_bewerken",
        ],
        "url_endpoint": "kiosk_prijzen_instellingen",
        "label": "Prijzenscherm & acties",
    },
    {
        "groep": "Kantine-tv",
        "endpoints": [
            "kiosk_scherm_instellingen",
            "kiosk_sponsoren_leden",
            "kiosk_sponsor_nieuw",
            "kiosk_sponsor_bewerken",
            "kiosk_sjabloon_nieuw",
            "kiosk_sjabloon_bewerken",
        ],
        "url_endpoint": "kiosk_sponsoren_leden",
        "label": "Dia's",
    },
    {
        "groep": "Kantine-tv",
        "endpoints": ["kiosk_sponsorlogos", "kiosk_sponsorlogo_bewerken"],
        "url_endpoint": "kiosk_sponsorlogos",
        "label": "Sponsoren",
    },
    {
        "groep": "Club van 20",
        "endpoints": [
            "club_van_20_overzicht",
            "club_van_20_lid_nieuw",
            "club_van_20_lid_bewerken",
        ],
        "url_endpoint": "club_van_20_overzicht",
        "label": "Leden & betalingen",
    },
    {
        "groep": "Club van 20",
        "endpoints": ["club_van_20_aanmeldingen"],
        "url_endpoint": "club_van_20_aanmeldingen",
        "label": "Aanmeldingen",
    },
    {
        "groep": "Club van 20",
        "endpoints": ["club_van_20_projecten", "club_van_20_project_bewerken"],
        "url_endpoint": "club_van_20_projecten",
        "label": "Projecten",
    },
    {
        "groep": "Club van 20",
        "endpoints": ["club_van_20_instellingen"],
        "url_endpoint": "club_van_20_instellingen",
        "label": "Scherm & werving",
    },
    {
        "groep": "Club van 20",
        "endpoints": ["club_van_20_importeren"],
        "url_endpoint": "club_van_20_importeren",
        "label": "Importeren / exporteren",
    },
    {
        "groep": "Stemmen",
        "endpoints": [
            "stemmen_overzicht",
            "stemvraag_nieuw",
            "stemvraag_detail",
            "stemvraag_poster_pdf",
            "stemvraag_sluiten",
            "stemvraag_heropenen",
            "stemvraag_verwijderen",
            "stemvraag_einddatum_instellen",
            "stemvraag_instellingen_bijwerken",
            "stem_goedkeuren",
            "stem_afkeuren",
        ],
        "url_endpoint": "stemmen_overzicht",
        "label": "Overzicht",
    },
    {
        "groep": "Stemmen",
        "endpoints": ["bieren_lijst", "bier_verwijderen"],
        "url_endpoint": "bieren_lijst",
        "label": "Bierbibliotheek",
    },
    {
        "groep": "Rapporten",
        "endpoints": ["verkooprapport", "verkooprapport_pdf_route", "verkooprapport_csv_route"],
        "url_endpoint": "verkooprapport",
        "label": "Verkooprapport",
    },
    {
        "groep": "Rapporten",
        "endpoints": ["seizoensrapport", "seizoensrapport_csv_route", "seizoensrapport_pdf_route"],
        "url_endpoint": "seizoensrapport",
        "label": "Omzet per seizoen",
    },
    {
        "groep": "Rapporten",
        "endpoints": ["compacte_uitdraai", "compacte_uitdraai_pdf_route"],
        "url_endpoint": "compacte_uitdraai",
        "label": "Compacte uitdraai",
    },
    {
        "groep": "Rapporten",
        "endpoints": ["bardienstrapport"],
        "url_endpoint": "bardienstrapport",
        "label": "Omzet per bardienst",
    },
    {
        "groep": "Rapporten",
        "endpoints": ["week_overzicht"],
        "url_endpoint": "week_overzicht",
        "label": "Weekoverzicht",
    },
    {
        "groep": "Rapporten",
        "endpoints": ["wedstrijden_overzicht"],
        "url_endpoint": "wedstrijden_overzicht",
        "label": "Wedstrijden",
    },
    {
        "groep": "Club",
        "endpoints": ["accounts_lijst"],
        "url_endpoint": "accounts_lijst",
        "label": "Accounts beheren",
    },
    {
        "groep": "Club",
        "endpoints": ["club_instellingen"],
        "url_endpoint": "club_instellingen",
        "label": "Club instellingen",
    },
    {
        "groep": "Club",
        "endpoints": ["logboek", "logboek_csv_route", "logboek_pdf_route"],
        "url_endpoint": "logboek",
        "label": "Logboek",
    },
    {
        "groep": "Club",
        "endpoints": ["backups_lijst"],
        "url_endpoint": "backups_lijst",
        "label": "Back-ups",
    },
    {
        "groep": "Club",
        "endpoints": ["instellingen_pagina"],
        "url_endpoint": "instellingen_pagina",
        "label": "Instellingen",
    },
    {
        "groep": "Club",
        "endpoints": ["gebruiksstatistieken"],
        "url_endpoint": "gebruiksstatistieken",
        "label": "Gebruiksstatistieken",
    },
]

# Groepen komen in deze volgorde in de zijbalk te staan (Python dicts noch
# SQL-resultaten garanderen een stabiele groepsvolgorde als items ooit worden
# herschikt, dus NAV_ITEMS wordt bij het opbouwen van de zijbalk hierop
# gesorteerd). Nieuwe groepen hoeven hier alleen aan toegevoegd te worden om
# vanzelf een eigen sectie te krijgen.
NAV_GROEP_VOLGORDE = [
    "Start",
    "Voorraad",
    "Tellen",
    "Bestellen",
    "Assortiment",
    "Kassa",
    "Kluis",
    "Keuken",
    "Kantine-tv",
    "Club van 20",
    "Stemmen",
    "Rapporten",
    "Club",
]
NAV_ITEMS.sort(key=lambda item: NAV_GROEP_VOLGORDE.index(item["groep"]))

# Club- en Kluisbeheer zijn (op het "club_instellingen"-item na, zie
# NAV_ITEM_SECTIE hierboven) volledig beheerder-only (zie BEHEERDER_ENDPOINTS)
# -- i.t.t. de sectie-gebonden groepen hierboven (die vrijwilligers met de
# juiste sectie wel mogen zien) toont de zijbalk deze groepen daarom nooit aan
# een vrijwilliger, ook al staan ze niet in NAV_GROEP_SECTIE.
NAV_GROEP_ALLEEN_BEHEERDER = {"Club", "Kluis"}

# Losse items in een groep die voor iedereen zichtbaar is, maar zelf alleen voor beheerders
# (de route staat dan ook in BEHEERDER_ENDPOINTS).
NAV_ITEM_ALLEEN_BEHEERDER = {"bardienstrapport"}

# De PDA-modus (zie WEERGAVE_TELEFOON_PATROON hieronder) heeft zijn eigen
# kop met alleen een kort label per pagina (geen zijbalk): vloerwerk plus een
# paar overzichten om te bekijken, geen beheer en geen zware rapportages.
# Bewust een losse lijst i.p.v. een subset-vlag op NAV_ITEMS: die twee
# navigaties verschillen te veel (geen groepen, kortere labels) om hetzelfde
# datamodel te delen. De knoppen op het startscherm staan in pda_start.html.
PDA_NAV_ITEMS = [
    {"url_endpoint": "tellen", "pda_label": "Tellen"},
    {"url_endpoint": "boeken", "pda_label": "Boeken"},
    {"url_endpoint": "bijzonderheden", "pda_label": "Prikbord"},
    {"url_endpoint": "kassa_tellen", "pda_label": "Kassa"},
    {"url_endpoint": "kiosk_prijzen_instellingen", "pda_label": "Kiosk"},
    {"url_endpoint": "bestellijst", "pda_label": "Bestellijst"},
    {"url_endpoint": "geschiedenis", "pda_label": "Geschiedenis"},
    {"url_endpoint": "boodschappenlijst", "pda_label": "Boodschappen"},
    {"url_endpoint": "voorraadoverzicht", "pda_label": "Voorraad"},
    {"url_endpoint": "tellingen_overzicht", "pda_label": "Tellingen"},
    {"url_endpoint": "prognose_pagina", "pda_label": "Prognose"},
    {"url_endpoint": "keuken_voorraad", "pda_label": "Keuken"},
    {"url_endpoint": "kluis_tellen", "pda_label": "Kluis"},
    {"url_endpoint": "club_van_20_aanmeldingen", "pda_label": "Club 20"},
]
