"""Wie mag welke pagina zien: open pagina's, alleen-beheerder-pagina's en de
rechten per sectie.

Puur gegevens (geen code), zodat je op 1 plek kunt zien welk endpoint bij welke
sectie hoort. De controle zelf staat in app.py (vereis_login). Voeg je een
nieuwe pagina toe die niet voor iedereen is, dan moet het endpoint hier in."""


OPEN_ENDPOINTS = {
    "login",
    "robots_txt",
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
    # Waar de QR-code op een schaplabel naartoe wijst, voor wie hem met een
    # telefoon scant: wat het is, en "Naar productpagina" (die alsnog om
    # inloggen vraagt, want product_detail zelf staat niet in deze lijst).
    # Melden voor de bestellijst gaat met de handterminal (sinds 1.72.0).
    "scan_landing",
    "scan_landing_verbruiksvoorwerp",
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
    # Idem voor de melding bij een nieuw of verlengd lid van de Club van 20 (templates/_kiosk_welkom.html).
    "kiosk_welkom",
    # Gekoppelde tv's (zie kiosk_tvs.py): het koppelen zelf, het scherm van één tv en zijn versie-poll. Het beheer
    # (koppelen met de code, wat hij toont) zit wel achter login, in de sectie Kantine-tv.
    "kiosk_koppelen",
    "kiosk_tv_scherm",
    "kiosk_tv_scherm_versie",
    # De tv-app wisselt met de afstandsbediening zelf tussen prijzenlijst en dia's (met zijn eigen token).
    "kiosk_tv_scherm_kiezen",
    # De webpagina van een dia (1.81.0, zoals de tussenstand van Shout-out!), die de schermen in een frame tonen; alleen
    # het adres dat bij die dia hoort, zie kiosk_webpagina.py.
    "kiosk_webpagina_scherm",
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
    # Het vergrendel-scherm op de tv vraagt hier na of de noodstop nog actief is (zie noodstop.py).
    "noodstop_status",
}

# Tijdens een noodstop (zie noodstop.py en noodstop_bewaken in app.py) blijven alleen deze bereikbaar voor iedereen:
# inloggen (dat lukt dan alleen de eigenaar), de statuspagina en het live zetten met handtekening (zodat een herstel
# nog live kan), en wat het vergrendel-scherm zelf nodig heeft.
NOODSTOP_ALTIJD_OPEN = {
    "static", "favicon_ico", "service_worker", "robots_txt", "offline_pagina",
    "login", "logout", "status_pagina", "uitrollen_endpoint", "noodstop_status",
}
# De tv-schermen en hun polls: die krijgen tijdens een noodstop het vergrendel-scherm.
KIOSK_SCHERMEN = {"kiosk_prijzen_scherm", "kiosk_scherm", "kiosk_tv", "kiosk_koppelen", "kiosk_tv_scherm"}
KIOSK_POLLS = {"kiosk_prijzen_versie", "kiosk_scherm_versie", "kiosk_tv_versie", "kiosk_welkom", "kiosk_tv_scherm_versie"}

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
    # De webpagina in een dia (1.81.0): een onderdeel van het scherm, geen eigen bezoek.
    "kiosk_webpagina_scherm",
    "kiosk_webpagina_voorbeeld",
    # Een barcode opzoeken vanuit de app op de handterminal (JSON): geen paginabezoek.
    "api_barcode",
    # Het blok 'Verkoop en verwachting' van de productpagina (apart opgehaald).
    "product_detail_verkoop",
    # Het vergrendel-scherm vraagt elke 15 seconden of de noodstop nog actief is.
    "noodstop_status",
    # De JSON-adressen voor de app op de handterminal (facturen inboeken): geen paginabezoeken.
    "api_facturen",
    "api_factuur",
    "api_factuur_scan",
    "api_factuur_koppelen",
    "api_factuur_regel",
    "api_factuur_afronden",
    "api_factuur_bestelling",
    "api_factuur_zoals_besteld",
    "api_factuur_plu",
    "api_app_keuken_stand",
    # De handterminal-app haalt de productlijst en de looplijst op de achtergrond op. Het startscherm en een product
    # openen (api_app_start, api_app_product) tellen wel als bezoek, net als op de site.
    "api_app_producten",
    "api_app_tellen",
    "api_app_tellen_verwachting",
    "api_app_product_verkoop",
    # Delen van een pagina die na het laden apart worden opgehaald (zie data-lazy-bron in gedeeld.js), en het
    # voorverwarmen van het voorspelmodel: dat is geen bezoek aan een pagina.
    "dashboard_omzettrend",
    "dashboard_wedstrijddag",
    "tellingen_cijfers",
    "telling_regels",
    "bestellijst_voorspeld",
    "bestellijst_prognose",
    "api_app_bestellijst_prognose",
    # Een scan op de bestellijst opzoeken (JSON).
    "bestellijst_zoek",
    "prognose_resultaat",
    "prognose_terugblik_resultaat",
    "agenda_omzet",
    "voorspelling_opwarmen",
    "opslag_meting",
    # Typen in de zoekbalk haalt bij elke toetsslag resultaten op.
    "zoeken_live",
    "favicon_ico",
    "robots_txt",
    "service_worker",
    "offline_pagina",
    "kiosk_prijzen_versie",
    "kiosk_scherm_versie",
    "kiosk_tv_versie",
    # De schermen vragen dit elke 5 seconden: geen bezoek, en zonder deze regel stond er per scherm elke 5 seconden
    # een nieuwe regel in de database.
    "kiosk_welkom",
    # Een gekoppelde tv vraagt elke 10 seconden of er iets veranderd is; Kantine-tv en de timerpagina verversen
    # zichzelf, en de handterminal-app vraagt de timers elke paar seconden zolang het timerscherm open is.
    "kiosk_tv_scherm_versie",
    "kiosk_tvs_status",
    "timer_stand",
    "api_app_timers",
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
    "account_overal_uitloggen",
    "account_wachtwoord_link_versturen",
    "categorieen_lijst",
    "categorie_verwijderen",
    "categorie_verkoopprijs_verplicht_wisselen",
    "subcategorie_nieuw",
    "subcategorie_verwijderen",
    "backups_lijst",
    "opslag_pagina",
    "opslag_meting",
    "opslag_video_opruimen",
    # Eigen taken toevoegen en beheren; zelf afronden (eigen_taak_afronden/-openen) mag iedereen die is ingelogd.
    "eigen_taken_pagina",
    "eigen_taak_nieuw",
    "eigen_taak_verwijderen",
    # Alle verkoopprijzen in één keer aanpassen.
    "producten_prijzen",
    "prijs_gepland_verwijderen",
    # Wat elk product oplevert (met de inkoopprijzen) en wat er zonder te verkopen uit de voorraad verdwijnt.
    "marge_rapport",
    "derving_rapport",
    "marge_doelmarge",
    # Verkoopprijzen van de keuken (de keuken zelf tellen en inboeken mag iedereen met de keukensectie).
    "keuken_prijzen",
    "api_app_keuken_prijzen",
    "leverancier_nieuw",
    "leverancier_bewerken",
    "leverancier_verwijderen",
    # Wat er al weken niet verkocht is, met de waarde tegen inkoopprijs.
    "niet_lopers_rapport",
    # De serverfouten van de site (Beheer > Foutmeldingen).
    "fouten_lijst",
    "fout_opgelost",
    # Wat er aan de productgegevens niet klopt (met inkoopprijzen).
    "gegevenscontrole",
    # De omzet uit de voorraad naast het afgerekende geld (een tekort kan op diefstal wijzen).
    "kassa_omzet_controle",
    # De noodstop (zie noodstop.py): de routes controleren zelf nog dat het de eigenaar is.
    "noodstop_pagina",
    "noodstop_dicht",
    "noodstop_open",
    "noodstop_code",
    "backup_nu",
    "backup_download",
    "backup_herstellen",
    "product_nieuw",
    "product_bewerken",
    "api_app_product_instellingen",
    "product_verwijderen",
    "product_archiveren",
    "producten_archiveren",
    "producten_gearchiveerd",
    "product_terugzetten",
    "producten_minimumvoorraad",
    "producten_besteleenheid",
    "producten_bulk_bewerken",
    "instellingen_pagina",
    # Kluis-acties zijn gevoeliger dan de kassalade (minder mutaties, groter
    # bedrag) en daarom bewust beheerder-only, i.t.t. kassa_mutatie_nieuw
    # (zie SECTIE_ENDPOINTS["kassa"] hieronder, die blijft voor iedereen met
    # de kassa-sectie).
    "kluis_tellen",
    "api_app_kluis",
    "api_app_kluis_tellen",
    "api_app_kluis_goedkeuren",
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
    # Omzet van eerdere seizoenen met de hand invullen.
    "seizoensrapport_historie",
}

# Fijnmazige rechten bovenop BEHEERDER_ENDPOINTS: elk account (ook
# vrijwilligers) heeft per sectie een los aan/uit-vinkje (zie Accounts).
# Beheerders omzeilen deze check altijd (zie vereis_login hieronder) -- dit
# is puur om te bepalen welke secties een vrijwilliger wél/niet mag. Routes
# die al in BEHEERDER_ENDPOINTS staan (bijv. product_nieuw) hoeven hier niet
# ook nog in: die blijven sowieso beheerder-only, ongeacht secties.
SECTIE_ENDPOINTS = {
    "voorraad": {
        # De handterminal-app (routes/app_api.py): zoeken, boeken, koppelen en tellen. Het startscherm
        # (api_app_start) is voor iedereen die is ingelogd; dat toont zelf alleen wat bij je rechten past.
        "api_app_producten",
        "api_app_product",
        "api_app_boeken",
        "api_app_barcode_koppelen",
        "api_app_product_nieuw",
        "api_app_artikel_nieuw",
        "api_app_tellen",
        "api_app_tellen_verwachting",
        "api_app_tellen_stand",
        "api_app_tellen_controleren",
        "api_app_tellen_bevestigen",
        "api_app_tellen_stoppen",
        "api_app_geschiedenis",
        "api_app_tellingen",
        "api_app_telling",
        "api_app_telling_regel_corrigeren",
        "api_app_bestellijst",
        "api_app_bestellijst_melding_afhandelen",
        "api_app_bestellijst_bestellen",
        "api_app_bestellijst_controleren",
        "api_app_bestelling",
        "api_app_product_bijstelling",
        "api_app_product_bestelaantal",
        "product_bestelaantal",
        "api_app_product_instellingen",
        "api_app_bestellijst_prognose",
        "api_app_product_verkoop",
        "api_app_product_melden",
        "api_app_verbruiksvoorwerp",
        "api_app_verbruiksvoorwerp_melden",
        "api_app_boodschappen",
        "api_app_boodschap_afvinken",
        "api_app_boodschap_verwijderen",
        "api_app_prognose",
        "api_app_barcodes",
        # Uitverkocht zetten op het prijzenscherm vanaf de handterminal (op de site: kiosk_product_uitverkocht_wisselen
        # in de sectie Kantine-tv). Wie aan de bar staat, ziet als eerste dat iets op is.
        "api_app_prijzenscherm",
        "api_app_product_uitverkocht",
        # Barcodes aanpassen en de koppelronde (routes/app_api_barcodes.py), net als artikel_bewerken op de site.
        "api_app_artikel",
        "api_app_artikel_verwijderen",
        "api_app_koppelronde",
        "api_app_koppelronde_geen_barcode",
        "api_app_koppelronde_ongedaan",
        "voorraadoverzicht",
        "voorraadoverzicht_pdf_route",
        "voorraadoverzicht_csv_route",
        "producten_lijst",
        "prijslijst_pagina",
        "prijslijst_pdf_route",
        "api_tablet_producten",
        "product_actief_wisselen",
        "product_zoeken",
        "product_detail",
        "product_detail_verkoop",
        "product_melden",
        "product_snel_toevoegen",
        "product_label_pdf",
        "producten_labels_pdf",
        "boeken",
        "levering_inboeken",
        # Barcodes (EAN) van de artikelen die je inkoopt: opzoeken, toevoegen en bijwerken (zie barcodes.py).
        "barcodes_overzicht",
        "barcode_zoeken",
        "barcode_snel_koppelen",
        "artikel_nieuw",
        "artikel_bewerken",
        "artikel_verwijderen",
        "barcode_doos_koppelen",
        "api_barcode",
        # Facturen inboeken door te scannen (zie facturen.py), in de browser en via de app.
        "facturen_overzicht",
        "factuur_start",
        "factuur_ronde",
        "factuur_scan",
        "factuur_handmatig",
        "factuur_regel_aantal",
        "factuur_gegevens",
        "factuur_afronden",
        "factuur_annuleren",
        "factuur_voor_bestelling",
        "factuur_zoals_besteld",
        "factuur_colli",
        "factuur_regel_prijs",
        "factuur_plu",
        "api_facturen",
        "api_factuur_bestelling",
        "api_factuur_zoals_besteld",
        "api_factuur_plu",
        "api_factuur",
        "api_factuur_scan",
        "api_factuur_koppelen",
        "api_factuur_regel",
        "api_factuur_afronden",
        "geschiedenis",
        "tellen",
        "tellen_lopen_starten",
        "tellen_lopen_hervatten",
        "tellen_lopen_afbreken",
        "tellen_lopen",
        "tellen_lopen_controleren",
        "tellingen_overzicht",
        "tellingen_cijfers",
        "tellingen_gecombineerd_pdf",
        # Leveranciers bekijken (contact, besteldag) mag iedereen die bestelt; beheren alleen een beheerder.
        "leveranciers_lijst",
        "kaartjes_pagina",
        "kaartjes_pdf_route",
        "telling_detail",
        "telling_regels",
        "telling_regel_corrigeren",
        "telling_regel_voorraad_bijwerken",
        "telling_pdf",
        "bestellijst",
        "bestellijst_voorspeld",
        "bestellijst_prognose",
        "bestellijst_zoek",
        "dashboard_wedstrijddag",
        "prognose_pagina",
        "prognose_resultaat",
        "voorspelling_opwarmen",
        "wedstrijd_afgelast_wisselen",
        "wedstrijd_toevoegen",
        "wedstrijd_verwijderen",
        "prognose_verkoopdagen",
        "prognose_uitzondering_toevoegen",
        "prognose_uitzondering_verwijderen",
        "prognose_uitzondering_periode_verwijderen",
        "prognose_evenement_toevoegen",
        "prognose_evenement_verwijderen",
        "prognose_terugblik",
        "prognose_terugblik_resultaat",
        # De verwachte omzet in de agenda (de agenda zelf mag iedereen zien).
        "agenda_omzet",
        "bestellijst_pdf_route",
        "bestelling_pdf_route",
        "bestelling_aanmaken",
        "bestelling_nieuw",
        "bestelling_bewerken",
        "bestelling_inboeken",
        "bestelling_verwijderen",
        "bestellijst_melding_product_afhandelen",
        "manco_afhandelen",
        "bestellingen_overzicht",
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
        "api_app_kassa",
        "api_app_kassa_tellen",
        "api_app_kassa_goedkeuren",
        "kassa_tellen",
        "kassa_telling_detail",
        "kassa_telling_heropenen",
        "kassa_telling_omzet_corrigeren",
        "kassa_telling_kaartomzet",
        "kassa_telling_coupures_corrigeren",
        "kassa_telling_bewerken",
        "kassa_telling_goedkeuren",
        "kassa_telling_pdf",
        "kassa_geschiedenis",
        "kassa_mutatie_nieuw",
        "kassa_mutatie_corrigeren",
    },
    "keuken": {
        "api_app_keuken",
        "api_app_keuken_tellen",
        "api_app_keuken_inboeken",
        "api_app_keuken_telling",
        "api_app_keuken_boodschap",
        "api_app_keuken_prijzen",
        "api_app_keuken_instellingen",
        "api_app_keuken_stand",
        "api_app_keuken_muteren",
        "api_app_keuken_koppelen",
        "api_app_keuken_verpakking",
        "api_app_keuken_product_verpakking",
        "api_app_frituurvet",
        "frituurvet_vervangen",
        "keuken_voorraad",
        "keuken_instellingen",
        "keuken_tellen",
        "keuken_tellen_lopen",
        "keuken_inboeken",
        "keuken_muteren",
        "keuken_barcode_koppelen",
        "keuken_verpakking_zetten",
        "keuken_product_verpakking",
        "keuken_tellingen_overzicht",
        "keuken_prijzen",
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
        "kiosk_thema_zetten",
        # Mappen, momenten en de schijnwerper (1.76.0, zie kiosk_momenten.py).
        "kiosk_moment_nu",
        "kiosk_moment_stop",
        "kiosk_moment_later",
        "kiosk_moment_voorbeeld",
        "kiosk_griezel_voorbeeld",  # het live voorbeeld van een griezeldia bij het dia-formulier (1.77.0)
        "kiosk_webpagina_voorbeeld",  # en van een webpagina (1.81.0)
        # De nieuwe indeling (1.79.0): Tv's en Diashow als eigen tabblad, en een dia aan of uit vanaf zijn tegel, met een
        # plaatje van de dia zelf.
        "kiosk_tvs_beheer",
        "kiosk_diashow",
        "kiosk_dia_wisselen",
        "kiosk_dia_miniatuur",
        "kiosk_scherm_avond",  # 's avonds alleen de dia's en wat je aanvinkt (1.80.0)
        "kiosk_dia_map_opslaan",
        "kiosk_dia_map_wisselen",
        "kiosk_dia_map_verwijderen",
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
        # Gekoppelde tv's (zie kiosk_tvs.py).
        "kiosk_tv_koppelen",
        "kiosk_koppel_link",
        "kiosk_tv_opslaan",
        "kiosk_tv_herladen",
        "kiosk_tv_verwijderen",
        "kiosk_tvs_status",
        # De kantine-tv vanaf de handterminal (routes/app_api_tv.py).
        "api_app_kantine_tv",
        "api_app_tv_scherm",
        "api_app_tv_herladen",
        "api_app_tv_koppelen",
        "api_app_tv_wissel",
        "api_app_tv_thema",
        "api_app_tv_actie",
        "api_app_tv_uitgelicht",
        "api_app_tv_producten",
        "api_app_tv_bardienst_nieuw",
        "api_app_tv_bardienst",
        "api_app_tv_bardienst_verwijderen",
        "api_app_tv_dias",
        "api_app_tv_dia",
        "api_app_tv_dia_blok",
        "api_app_tv_map",
        "api_app_tv_moment_nu",
        "api_app_tv_moment_later",
        "api_app_tv_schijnwerper_stop",
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
        "api_app_aanmeldingen",
        "api_app_aanmelding_goedkeuren",
        "api_app_aanmelding_afwijzen",
        "club_van_20_aanmelding_goedkeuren",
        "club_van_20_aanmelding_afwijzen",
        "club_van_20_instellingen",
        "club_van_20_melding_testen",
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
