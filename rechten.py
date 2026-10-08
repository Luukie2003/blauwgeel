"""Wie mag welke pagina zien: open pagina's, alleen-beheerder-pagina's en de
rechten per sectie.

Puur gegevens (geen code), zodat je op 1 plek kunt zien welk endpoint bij welke
sectie hoort. De controle zelf staat in app.py (vereis_login). Voeg je een
nieuwe pagina toe die niet voor iedereen is, dan moet het endpoint hier in."""


OPEN_ENDPOINTS = {
    "login",
    "static",
    "favicon_ico",
    "service_worker",
    "offline_pagina",
    "wachtwoord_vergeten",
    "wachtwoord_instellen",
    # Machine-naar-machine JSON-API voor de kiosk-tablet-app (los project,
    # zie android-apps/tablet) -- die heeft nog geen sessie/cookie op het
    # moment van de aanroep zelf (die start 'm juist, bij een geldige code).
    # Zie ook de CSRF-uitzondering in csrf_beschermen hieronder.
    "tablet_code_inloggen",
    # Live zetten vanaf het script scripts/zet_live.py, beveiligd met een handtekening
    # (zie uitrollen.py), plus de statuspagina waarmee het script controleert welke
    # versie er draait.
    "uitrollen_endpoint",
    "status_pagina",
    # De publieke stempagina's hebben geen account nodig, bezoekers scannen
    # 'm via een QR-code of stemmen.kantineblauwgeel.nl, ze loggen nergens in.
    "stem_pagina",
    "stem_overzicht_publiek",
    # Waar de QR-code op een schaplabel naartoe wijst: iedereen mag zonder
    # account een product melden voor de bestellijst. "Naar productpagina"
    # op die landingspagina vraagt daarna alsnog om in te loggen, want
    # product_detail zelf staat niet in deze lijst.
    "scan_landing",
    "scan_melden",
    # Zelfde als hierboven, maar dan voor de QR-code op een
    # verbruiksvoorwerp-schaplabel (geen productpagina om naartoe te gaan,
    # dus alleen een meld-knop).
    "scan_landing_verbruiksvoorwerp",
    "scan_melden_verbruiksvoorwerp",
    # De twee Kantine Kiosk-schermen draaien op een TV via Chromecast --
    # daar kan niemand op inloggen, dus moeten ze net als de stempagina's
    # zonder account bereikbaar zijn. Het beheer ervan (wat erop staat) zit
    # wel achter login, zie BEHEERDER_ENDPOINTS hieronder.
    "kiosk_prijzen_scherm",
    "kiosk_scherm",
    # Optioneel derde scherm voor wie (nog) maar 1 fysiek scherm heeft en
    # daarop wisselt tussen prijzen/dia's (zie kiosk_tv in routes/kiosk.py) --
    # zelfde publieke, geen-account-nodig behandeling als de 2 vaste schermen.
    "kiosk_tv",
    # De schermen pollen deze endpoints zelf (zie de <script> in
    # kiosk_prijzen_scherm.html/kiosk_scherm.html) om te bepalen of ze zichzelf
    # moeten herladen -- dus ook zonder account bereikbaar.
    "kiosk_prijzen_versie",
    "kiosk_scherm_versie",
    "kiosk_tv_versie",
    # Publieke Club van 20-pagina: waar de QR-code op de wervingsdia van het
    # kantine scherm naartoe wijst -- bezoekers hebben geen account.
    "club_van_20_publiek",
    # Aanmeldformulier (en bedankpagina) voor nieuwe leden, bereikbaar via de
    # knop bovenaan die pagina -- ook zonder account; beheerders keuren de
    # aanmeldingen daarna goed (Club van 20 > Aanmeldingen).
    "club_van_20_aanmelden",
    "club_van_20_aanmelden_bedankt",
    "club_van_20_aanmelden_voorbeeld",
    "club_van_20_aanmelden_voorbeeld_stop",
    # De privacyverklaring moet voor iedereen te lezen zijn, ook zonder account.
    "privacyverklaring",
}

# Iedereen moet bij de eerste keer inloggen een eigen 6-cijferige tablet-code
# instellen (zie tablet_code_instellen in routes/auth.py) -- die code wordt
# straks gebruikt om aan te melden op de kiosk-tablet/tv-app (los van deze
# website), zonder gebruikersnaam. Zolang dat nog niet is gebeurd, blokkeert
# vereis_login hieronder alle andere pagina's; deze twee blijven bereikbaar
# zodat niemand vast komt te zitten.
TABLET_CODE_UITGEZONDERD = {"tablet_code_instellen", "logout"}

# Endpoints die niet meetellen als paginabezoek voor Club > Gebruiksstatistieken
# (zie log_paginabezoek hieronder en routes/gebruik.py) -- puur technisch
# verkeer zonder betekenis voor "wie gebruikt welk onderdeel". De _versie-
# polls draaien elke 10s zolang een kiosk-scherm openstaat; het scherm zelf
# openen/herladen (kiosk_scherm/kiosk_prijzen_scherm/kiosk_tv) wordt wél
# gelogd, want dat gebeurt alleen bij een echte (her)start van het scherm.
GEBRUIK_NIET_LOGGEN = {
    "static",
    "status_pagina",
    # Typen in de zoekbalk haalt bij elke toetsslag resultaten op.
    "zoeken_live",
    "favicon_ico",
    "service_worker",
    "offline_pagina",
    "kiosk_prijzen_versie",
    "kiosk_scherm_versie",
    "kiosk_tv_versie",
}

# Routes die alleen voor de rol 'beheerder' toegankelijk zijn. Vrijwilligers
# komen hier niet in -- zij kunnen de dagelijkse operatie doen (tellen,
# boeken, bestellijst, bijzonderheden) maar niet het assortiment, accounts,
# categorieën of back-ups beheren.
BEHEERDER_ENDPOINTS = {
    "accounts_lijst",
    "account_nieuw",
    "account_verwijderen",
    "account_rol_wijzigen",
    "account_secties_wijzigen",
    "account_email_wijzigen",
    "account_actief_wisselen",
    "account_wachtwoord_link_versturen",
    "categorieen_lijst",
    "categorie_verwijderen",
    "categorie_verkoopprijs_verplicht_wisselen",
    "subcategorie_nieuw",
    "subcategorie_verwijderen",
    "backups_lijst",
    "backup_nu",
    "backup_download",
    "backup_herstellen",
    "product_nieuw",
    "product_bewerken",
    "product_verwijderen",
    "producten_minimumvoorraad",
    "producten_besteleenheid",
    "producten_bulk_bewerken",
    "instellingen_pagina",
    # Kluis-acties zijn gevoeliger dan de kassalade (minder mutaties, groter
    # bedrag) en daarom bewust beheerder-only, i.t.t. kassa_mutatie_nieuw
    # (zie SECTIE_ENDPOINTS["kassa"] hieronder, die blijft voor iedereen met
    # de kassa-sectie).
    "kluis_tellen",
    "kluis_telling_detail",
    "kluis_telling_heropenen",
    "kluis_telling_coupures_corrigeren",
    "kluis_telling_bewerken",
    "kluis_telling_goedkeuren",
    "kluis_geschiedenis",
    "kluis_mutatie_nieuw",
    "kluis_mutatie_corrigeren",
    "gebruiksstatistieken",
    "logboek",
    "logboek_csv_route",
    "logboek_pdf_route",
    # Omzet per persoon: gevoelig tussen vrijwilligers, dus alleen voor beheerders.
    "bardienstrapport",
}

# Fijnmazige rechten bovenop BEHEERDER_ENDPOINTS: elk account (ook
# vrijwilligers) heeft per sectie een los aan/uit-vinkje (zie Accounts).
# Beheerders omzeilen deze check altijd (zie vereis_login hieronder) -- dit
# is puur om te bepalen welke secties een vrijwilliger wél/niet mag. Routes
# die al in BEHEERDER_ENDPOINTS staan (bijv. product_nieuw) hoeven hier niet
# ook nog in: die blijven sowieso beheerder-only, ongeacht secties.
SECTIE_ENDPOINTS = {
    "voorraad": {
        "voorraadoverzicht",
        "voorraadoverzicht_pdf_route",
        "voorraadoverzicht_csv_route",
        "producten_lijst",
        "api_tablet_producten",
        "product_actief_wisselen",
        "product_zoeken",
        "product_detail",
        "product_snel_toevoegen",
        "product_label_pdf",
        "producten_labels_pdf",
        "boeken",
        "levering_inboeken",
        "geschiedenis",
        "tellen",
        "tellen_lopen_starten",
        "tellen_lopen_hervatten",
        "tellen_lopen",
        "tellen_lopen_controleren",
        "tellingen_overzicht",
        "tellingen_gecombineerd_pdf",
        "telling_detail",
        "telling_regel_corrigeren",
        "telling_pdf",
        "bestellijst",
        "prognose_pagina",
        "wedstrijd_afgelast_wisselen",
        "prognose_verkoopdagen",
        "prognose_uitzondering_toevoegen",
        "prognose_uitzondering_verwijderen",
        "bestellijst_pdf_route",
        "bestelling_aanmaken",
        "bestelling_nieuw",
        "bestelling_bewerken",
        "bestelling_inboeken",
        "bestelling_verwijderen",
        "bestellijst_melding_product_afhandelen",
        "bestellijst_melding_afhandelen",
        "fusten_overzicht",
        "boodschappenlijst",
        "boodschap_afvinken",
        "boodschap_verwijderen",
        "scannen",
        "verbruiksvoorwerpen_lijst",
        "verbruiksvoorwerp_verwijderen",
        "verbruiksvoorwerp_bestellijst_melden",
        "verbruiksvoorwerp_label_pdf",
        "verbruiksvoorwerpen_labels_pdf",
    },
    "kassa": {
        "kassa_tellen",
        "kassa_telling_detail",
        "kassa_telling_heropenen",
        "kassa_telling_omzet_corrigeren",
        "kassa_telling_coupures_corrigeren",
        "kassa_telling_bewerken",
        "kassa_telling_goedkeuren",
        "kassa_telling_pdf",
        "kassa_geschiedenis",
        "kassa_mutatie_nieuw",
        "kassa_mutatie_corrigeren",
    },
    "keuken": {
        "frituurvet_vervangen",
        "keuken_voorraad",
        "keuken_instellingen",
    },
    "stemmen": {
        "stemmen_overzicht",
        "stemvraag_nieuw",
        "stemvraag_detail",
        "stemvraag_poster_pdf",
        "stem_afkeuren",
        "stem_goedkeuren",
        "stemvraag_sluiten",
        "stemvraag_heropenen",
        "stemvraag_einddatum_instellen",
        "stemvraag_instellingen_bijwerken",
        "stemvraag_verwijderen",
        "bieren_lijst",
        "bier_verwijderen",
    },
    # Kantine-tv is losgemaakt van BEHEERDER_ENDPOINTS: puur scherminstellingen
    # (prijzenscherm, dia's), geen toegang tot accounts/back-ups/instellingen,
    # dus veilig om als losse sectie aan een vrijwilliger te geven.
    "kantine_tv": {
        "kiosk_hub",
        "kiosk_prijzen_instellingen",
        "kiosk_wedstrijddag_welkom_instellingen",
        "kiosk_wedstrijddag_welkom_testen",
        "api_tablet_wedstrijddag_welkom",
        "kiosk_categorie_kolommen_instellingen",
        "kiosk_uitgelicht_product_instellingen",
        "api_tablet_uitgelicht",
        "kiosk_product_toon_wisselen",
        "kiosk_product_uitverkocht_wisselen",
        "kiosk_acties",
        "kiosk_actie_nieuw",
        "kiosk_actie_bewerken",
        "kiosk_actie_verwijderen",
        "kiosk_actie_toon_wisselen",
        "api_tablet_acties",
        "kiosk_bardienst",
        "kiosk_bardienst_nieuw",
        "kiosk_bardienst_bewerken",
        "kiosk_bardienst_verwijderen",
        "api_tablet_bardiensten",
        "kiosk_tv_wisselen",
        "kiosk_sponsoren_leden",
        "kiosk_sponsor_nieuw",
        "kiosk_sponsor_bewerken",
        "kiosk_sponsor_verwijderen",
        "kiosk_sponsorlogos",
        "kiosk_sponsorlogos_instellingen",
        "kiosk_sponsorlogo_bewerken",
        "kiosk_sponsorlogo_actief_wisselen",
        "kiosk_sponsorlogo_verwijderen",
        "kiosk_sjabloon_nieuw",
        "kiosk_sjabloon_bewerken",
        "kiosk_sjabloon_verwijderen",
        "kiosk_scherm_instellingen",
        "kiosk_stand_team_nieuw",
        "kiosk_stand_team_verwijderen",
        "kiosk_stand_team_eigen_wisselen",
        "kiosk_stand_volgorde_opslaan",
        "kiosk_club_logo_opslaan",
        "kiosk_stand_poule_nieuw",
        "kiosk_stand_poule_verwijderen",
        "kiosk_motm_team_nieuw",
        "kiosk_motm_team_verwijderen",
        "kiosk_motm_volgorde_opslaan",
    },
    # Club van 20: ledenadministratie + betalingen + projecten + de
    # Club van 20-dia's. Eigen sectie (los van Kantine-tv) zodat bijv. de
    # penningmeester/coördinator van de Club van 20 hier wel bij kan zonder
    # de rest van de kantine-tv te beheren -- en andersom.
    "club_van_20": {
        "club_van_20_overzicht",
        "club_van_20_bijdrage_opslaan",
        "club_van_20_bulk",
        "club_van_20_lid_nieuw",
        "club_van_20_lid_bewerken",
        "club_van_20_lid_verwijderen",
        "club_van_20_lid_archiveren",
        "club_van_20_projecten",
        "club_van_20_project_bewerken",
        "club_van_20_project_status",
        "club_van_20_project_verwijderen",
        "club_van_20_importeren",
        "club_van_20_exporteren",
        "club_van_20_aanmeldingen",
        "club_van_20_aanmelding_goedkeuren",
        "club_van_20_aanmelding_afwijzen",
        "club_van_20_instellingen",
    },
    # Losgemaakt van BEHEERDER_ENDPOINTS voor hetzelfde soort reden --
    # agenda/banner raakt geen accounts, categorieën of back-ups. Alleen
    # club_instellingen zelf (het NAV-item) i.p.v. de hele "Club"-groep, zie
    # NAV_ITEM_SECTIE hieronder: Accounts/Back-ups/Instellingen/Statistieken
    # in diezelfde zijbalkgroep blijven beheerder-only.
    "club": {
        "club_instellingen",
        "club_agenda_toevoegen",
        "club_agenda_verwijderen",
        "club_agenda_verversen",
        "club_agenda_controleren",
        "mededeling_pinnen_als_banner",
    },
}
# Omgekeerde opzoektabel: endpoint -> vereiste sectie, 1x opgebouwd bij het
# starten van het proces i.p.v. bij elk verzoek opnieuw over te zoeken.
ENDPOINT_SECTIE = {
    endpoint: sectie for sectie, endpoints in SECTIE_ENDPOINTS.items() for endpoint in endpoints
}
