"""De zijbalk: welke groepen en pagina's er in het menu staan, en welke daarvan
bij welke sectie horen, plus het kortere menu van de handterminal-weergave.

Puur gegevens (geen code). Een nieuwe pagina in het menu: voeg een item toe aan
NAV_ITEMS (groep, endpoints, url_endpoint, label)."""

# Voor het filteren van de zijbalk: welke navigatiegroep hoort bij welke
# sectie. "Start" en "Rapporten" staan hier bewust niet in -- die blijven
# voor iedereen zichtbaar, net als het vroegere "Algemeen".
NAV_GROEP_SECTIE = {
    "Voorraad": "voorraad",
    "Bestellen": "voorraad",
    "Producten": "voorraad",
    "Keuken": "keuken",
    "Stemmen": "stemmen",
    "Kantine-tv": "kantine_tv",
    "Club van 20": "club_van_20",
}
# Uitzondering per los NAV-item (i.p.v. de hele groep) op NAV_GROEP_SECTIE/
# NAV_GROEP_ALLEEN_BEHEERDER hieronder -- voor een item dat wél sectie-
# gebonden is terwijl de rest van zijn zijbalkgroep anders is. "Geld" bevat
# bijvoorbeeld de kassa (sectie kassa) én de kluis (alleen beheerders), en in
# "Beheer" is Club instellingen delegeerbaar terwijl Accounts/Back-ups/
# Instellingen dat niet zijn.
NAV_ITEM_SECTIE = {
    "club_instellingen": "club",
    "kassa_tellen": "kassa",
    "kassa_geschiedenis": "kassa",
    "kassa_mutatie_nieuw": "kassa",
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
        "groep": "Start",
        "endpoints": ["eigen_taken_pagina", "eigen_taak_nieuw", "eigen_taak_verwijderen"],
        "url_endpoint": "eigen_taken_pagina",
        "label": "Taken",
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
        "groep": "Voorraad",
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
        "groep": "Voorraad",
        "endpoints": ["tellingen_overzicht", "tellingen_cijfers", "telling_detail", "tellingen_gecombineerd_pdf"],
        "url_endpoint": "tellingen_overzicht",
        "label": "Tellingen",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["kaartjes_pagina", "kaartjes_pdf_route"],
        "url_endpoint": "kaartjes_pagina",
        "label": "Kaartjes printen",
    },
    {
        "groep": "Bestellen",
        "endpoints": ["bestellijst", "bestellijst_voorspeld", "bestelling_aanmaken", "bestelling_nieuw", "bestelling_inboeken"],
        "url_endpoint": "bestellijst",
        "label": "Bestellijst",
    },
    {
        "groep": "Bestellen",
        "endpoints": ["prognose_pagina", "prognose_resultaat"],
        "url_endpoint": "prognose_pagina",
        "label": "Prognose",
    },
    {
        "groep": "Bestellen",
        "endpoints": ["prognose_terugblik"],
        "url_endpoint": "prognose_terugblik",
        "label": "Prognose en verkoop",
    },
    {
        "groep": "Bestellen",
        "endpoints": ["boodschappenlijst"],
        "url_endpoint": "boodschappenlijst",
        "label": "Boodschappenlijst",
    },
    {
        "groep": "Bestellen",
        "endpoints": ["leveranciers_lijst", "leverancier_nieuw", "leverancier_bewerken"],
        "url_endpoint": "leveranciers_lijst",
        "label": "Leveranciers",
    },
    {
        "groep": "Producten",
        "endpoints": [
            "producten_lijst",
            "product_nieuw",
            "product_bewerken",
            "categorieen_lijst",
            "producten_bulk_bewerken",
            "producten_gearchiveerd",
        ],
        "url_endpoint": "producten_lijst",
        "label": "Producten",
    },
    {
        "groep": "Producten",
        "endpoints": ["prijslijst_pagina", "prijslijst_pdf_route"],
        "url_endpoint": "prijslijst_pagina",
        "label": "Prijslijst",
    },
    {
        "groep": "Producten",
        "endpoints": ["producten_prijzen", "prijs_gepland_verwijderen"],
        "url_endpoint": "producten_prijzen",
        "label": "Prijzen aanpassen",
    },
    {
        "groep": "Producten",
        "endpoints": ["gegevenscontrole"],
        "url_endpoint": "gegevenscontrole",
        "label": "Gegevenscontrole",
    },
    {
        "groep": "Producten",
        "endpoints": ["verbruiksvoorwerpen_lijst"],
        "url_endpoint": "verbruiksvoorwerpen_lijst",
        "label": "Verbruiksvoorwerpen",
    },
    {
        "groep": "Geld",
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
        "groep": "Geld",
        "endpoints": ["kassa_geschiedenis"],
        "url_endpoint": "kassa_geschiedenis",
        "label": "Kassa geschiedenis",
    },
    {
        "groep": "Geld",
        "endpoints": ["kassa_mutatie_nieuw"],
        "url_endpoint": "kassa_mutatie_nieuw",
        "label": "Afdracht / toevoeging",
    },
    {
        "groep": "Geld",
        "endpoints": ["kassa_omzet_controle"],
        "url_endpoint": "kassa_omzet_controle",
        "label": "Omzet en kassa",
    },
    {
        "groep": "Geld",
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
        "groep": "Geld",
        "endpoints": ["kluis_geschiedenis"],
        "url_endpoint": "kluis_geschiedenis",
        "label": "Kluis geschiedenis",
    },
    {
        "groep": "Geld",
        "endpoints": ["kluis_mutatie_nieuw"],
        "url_endpoint": "kluis_mutatie_nieuw",
        "label": "Storting / opname",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_voorraad"],
        "url_endpoint": "keuken_voorraad",
        "label": "Producten",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_tellen"],
        "url_endpoint": "keuken_tellen",
        "label": "Tellen",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_inboeken"],
        "url_endpoint": "keuken_inboeken",
        "label": "Inboeken",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_tellingen_overzicht"],
        "url_endpoint": "keuken_tellingen_overzicht",
        "label": "Tellingen",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_prijzen"],
        "url_endpoint": "keuken_prijzen",
        "label": "Prijzen",
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
        "endpoints": ["marge_rapport"],
        "url_endpoint": "marge_rapport",
        "label": "Marge",
    },
    {
        "groep": "Rapporten",
        "endpoints": ["derving_rapport"],
        "url_endpoint": "derving_rapport",
        "label": "Derving",
    },
    {
        "groep": "Rapporten",
        "endpoints": ["niet_lopers_rapport"],
        "url_endpoint": "niet_lopers_rapport",
        "label": "Niet-lopers",
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
        "groep": "Beheer",
        "endpoints": ["accounts_lijst"],
        "url_endpoint": "accounts_lijst",
        "label": "Accounts beheren",
    },
    {
        "groep": "Beheer",
        "endpoints": ["club_instellingen"],
        "url_endpoint": "club_instellingen",
        "label": "Club instellingen",
    },
    {
        "groep": "Beheer",
        "endpoints": ["logboek", "logboek_csv_route", "logboek_pdf_route"],
        "url_endpoint": "logboek",
        "label": "Logboek",
    },
    {
        "groep": "Beheer",
        "endpoints": ["backups_lijst"],
        "url_endpoint": "backups_lijst",
        "label": "Back-ups",
    },
    {
        "groep": "Beheer",
        "endpoints": ["opslag_pagina", "opslag_video_opruimen"],
        "url_endpoint": "opslag_pagina",
        "label": "Opslag",
    },
    {
        "groep": "Beheer",
        "endpoints": ["instellingen_pagina"],
        "url_endpoint": "instellingen_pagina",
        "label": "Instellingen",
    },
    {
        "groep": "Beheer",
        "endpoints": ["gebruiksstatistieken"],
        "url_endpoint": "gebruiksstatistieken",
        "label": "Gebruiksstatistieken",
    },
    {
        "groep": "Beheer",
        "endpoints": ["fouten_lijst"],
        "url_endpoint": "fouten_lijst",
        "label": "Foutmeldingen",
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
    "Bestellen",
    "Producten",
    "Geld",
    "Keuken",
    "Kantine-tv",
    "Club van 20",
    "Stemmen",
    "Rapporten",
    "Beheer",
]
NAV_ITEMS.sort(key=lambda item: NAV_GROEP_VOLGORDE.index(item["groep"]))

# Beheer (accounts, back-ups, logboek...) is -- op het "club_instellingen"-item na, zie
# NAV_ITEM_SECTIE hierboven -- volledig beheerder-only (zie BEHEERDER_ENDPOINTS). De zijbalk toont
# deze groep daarom nooit aan een vrijwilliger, ook al staat hij niet in NAV_GROEP_SECTIE.
NAV_GROEP_ALLEEN_BEHEERDER = {"Beheer"}

# Losse items in een groep die voor iedereen zichtbaar is, maar zelf alleen voor beheerders
# (de route staat dan ook in BEHEERDER_ENDPOINTS).
NAV_ITEM_ALLEEN_BEHEERDER = {
    "keuken_prijzen",
    # Omzet naast het afgerekende geld: een tekort kan op diefstal wijzen, dus alleen voor beheerders.
    "kassa_omzet_controle",
    "marge_rapport",
    "gegevenscontrole",
    "derving_rapport",
    "niet_lopers_rapport",
    "eigen_taken_pagina",
    "producten_prijzen",
    "bardienstrapport",
    # De kluis is gevoeliger dan de kassalade (minder mutaties, groter bedrag).
    "kluis_tellen",
    "kluis_geschiedenis",
    "kluis_mutatie_nieuw",
}

# Een klein pictogram voor elke groep, zodat je het menu in één oogopslag kunt scannen.
NAV_GROEP_ICOON = {
    "Start": "🏠",
    "Voorraad": "📦",
    "Bestellen": "🛒",
    "Producten": "🏷️",
    "Geld": "💶",
    "Keuken": "🍳",
    "Kantine-tv": "📺",
    "Club van 20": "⭐",
    "Stemmen": "🗳️",
    "Rapporten": "📊",
    "Beheer": "⚙️",
}

# De PDA-modus (zie WEERGAVE_TELEFOON_PATROON hieronder) heeft zijn eigen
# kop met alleen een kort label per pagina (geen zijbalk): vloerwerk plus een
# paar overzichten om te bekijken, geen beheer en geen zware rapportages.
# Bewust een losse lijst i.p.v. een subset-vlag op NAV_ITEMS: die twee
# navigaties verschillen te veel (geen groepen, kortere labels) om hetzelfde
# datamodel te delen. De knoppen op het startscherm staan in pda_start.html.
# Eenvoudige weergave (Mijn voorkeuren): wie dat aanzet, ziet in het menu alleen zijn favorieten (de rest achter
# "Alle onderdelen") en op het overzicht grote knoppen. Zonder eigen keuze zijn dit de favorieten.
STANDAARD_FAVORIETEN = ["tellen", "boeken", "bestellijst", "bijzonderheden"]


def favoriete_items(zichtbare_items, favorieten):
    """De menu-items uit 'favorieten' (een tekst met url_endpoints, komma's ertussen; leeg = de standaard), in die
    volgorde, en alleen als dit account ze mag zien."""
    gekozen = [f for f in (favorieten or "").split(",") if f] or STANDAARD_FAVORIETEN
    per_endpoint = {item["url_endpoint"]: item for item in zichtbare_items}
    return [per_endpoint[f] for f in gekozen if f in per_endpoint]


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
