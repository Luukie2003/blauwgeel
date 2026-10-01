from datetime import datetime, timedelta

from flask import Response, flash, g, jsonify, redirect, render_template, request, session, url_for

from club_van_20 import bereken_club_van_20_status
from database import get_db
from helpers import (
    bereken_bestelling_status,
    bereken_frituurvet_status,
    bereken_kassa_telling_status,
    bereken_komende_thuiswedstrijden,
    bereken_laatste_telling_status,
    bereken_omzet_trend_periode,
    bereken_wedstrijd_geschiedenis,
    bereken_week_overzicht,
    csv_response,
    dagdeel_groet,
    format_datum,
    heeft_sectie_toegang,
    is_ajax_verzoek,
    now_str,
    stuur_tag_notificaties,
)
from pdf import periode_verkoop_pdf

# Handmatig bijgehouden versie-overzicht voor de Help-pagina. Geen
# geautomatiseerd systeem (geen releases/tags) -- gewoon een leesbaar logje
# van wat er is toegevoegd, bijgewerkt bij noemenswaardige wijzigingen.
HUIDIGE_VERSIE = "1.19.4"
WIJZIGINGEN = [
    {
        "versie": "1.19.4",
        "datum": "1 oktober 2026",
        "punten": [
            "Club van 20: met een geheime knop (bijna onzichtbaar puntje onderaan de openbare pagina) en een zelf in te stellen code kun je het aanmeldformulier al vóór het openingsmoment bekijken en uitproberen",
            "Club van 20: de openbare pagina heeft geen lange streepjes meer in de tekst en toont het seizoen als 2026/2027",
        ],
    },
    {
        "versie": "1.19.3",
        "datum": "1 oktober 2026",
        "punten": [
            "Privacyverklaring: vermeld dat de server van de hostingpartij (PythonAnywhere) in de Verenigde Staten staat",
        ],
    },
    {
        "versie": "1.19.2",
        "datum": "1 oktober 2026",
        "punten": [
            "Nieuw: privacyverklaring op /privacy (openbaar, met links op het aanmeldformulier, de Club van 20-pagina, de stempagina's en onderaan de beheersite); het contactadres stel je in bij Club → Instellingen",
            "Oude gegevens ruimen zichzelf op volgens die verklaring: afgewezen aanmeldingen na een jaar, de afgeleide IP-code bij aanmeldingen na 30 dagen en paginatellingen na twee jaar",
        ],
    },
    {
        "versie": "1.19.1",
        "datum": "1 oktober 2026",
        "punten": [
            "Club van 20: je kunt bij Mijn voorkeuren aanvinken dat je een mail krijgt bij elke nieuwe aanmelding (naar het e-mailadres van je account)",
        ],
    },
    {
        "versie": "1.19.0",
        "datum": "1 oktober 2026",
        "punten": [
            "Club van 20: nieuwe leden kunnen zich zelf aanmelden. Bovenaan de QR-pagina verschijnt op het aftelmoment een knop; daarna kiezen ze Mollie of contant aan de bar (met de naam van de bardienst), vullen hun naam in en wat er op het bordje moet komen (maximaal 24 tekens, instelbaar)",
            "Club van 20 > Aanmeldingen: elke aanmelding is eerst een concept. Na het controleren van de betaling keur je goed (met een pop-up om ontbrekende gegevens aan te vullen) of wijs je af; een bestaand lid wordt verlengd in plaats van dubbel aangemaakt. In het menu staat een teller met het aantal wachtende aanmeldingen",
            "Club van 20 > Scherm & werving: de betaallink is nu de Mollie-link voor het aanmeldformulier, en je kunt aanmelden aan/uit zetten",
        ],
    },
    {
        "versie": "1.18.3",
        "datum": "1 oktober 2026",
        "punten": [
            "Sponsordia's: bij een groep sponsoren staat nu standaard alleen de koptekst (bijv. \"Wij bedanken onze sponsoren\") boven in beeld, zonder de groepsnaam; wil je de groepsnaam (bijv. \"Zaterdag 1\") toch als titel, dan zet je dat aan onder Sponsoren → Opmaak",
        ],
    },
    {
        "versie": "1.18.2",
        "datum": "1 oktober 2026",
        "punten": [
            "Sponsordia's: staan er meerdere logo's op een dia, dan staat de koptekst automatisch in het meervoud (\"Wij bedanken onze sponsoren\"); zelf aan te passen onder Sponsoren → Opmaak",
        ],
    },
    {
        "versie": "1.18.1",
        "datum": "1 oktober 2026",
        "punten": [
            "Sponsordia's: staan 2 of 3 sponsoren in dezelfde groep, dan komen hun logo's veel groter naast elkaar in beeld, elk in een breedte die past bij de vorm van het logo (een breed logo krijgt meer ruimte dan een vierkant)",
        ],
    },
    {
        "versie": "1.18.0",
        "datum": "1 oktober 2026",
        "punten": [
            "Club van 20: een ster is er nu voor elke 3 betaalde seizoenen (in te stellen onder Scherm & werving) en staat groter, als label op de hoek van het bordje, op het kantine scherm, de publieke pagina en het ledenoverzicht",
            "Club van 20: bordjes zijn gewoon wit tot 2 sterren; vanaf 2 sterren (6 seizoenen) zijn ze glanzend metaalgoud met af en toe een lichtstreep (ook instelbaar). Het oude zilver/goud op basis van het aantal seizoenen is vervangen",
            "Club van 20 importeren: je kunt nu het Excel-bestand (.xlsx) zelf uploaden, met alle jaren historie; bestaande leden worden alleen aangevuld (een aangepast team blijft staan) en je ziet vooraf welke bestaande betalingen zouden wijzigen",
        ],
    },
    {
        "versie": "1.17.3",
        "datum": "30 september 2026",
        "punten": [
            "Standen-dia: teams in een leeftijdscategorie (bijv. 'HSC 18+1' of 'FVV 18+2') worden nu ook herkend als team van een club, zodat ze het clublogo delen met de andere teams van die club",
        ],
    },
    {
        "versie": "1.17.2",
        "datum": "30 september 2026",
        "punten": [
            "De Club van 20-wervingsdia (met QR-code en aftelklok) is ongeveer een kwart groter, en blijft ook met een lange aankondigingstekst helemaal in beeld",
        ],
    },
    {
        "versie": "1.17.1",
        "datum": "30 september 2026",
        "punten": [
            "Standen-, teamstrijd-, welkom- en wervingsdia passen nu ook op het scherm van de tv-app (ze liepen daar boven en onder uit beeld); ze schalen nu mee met de schermgrootte, en een stand met veel teams past altijd op één dia",
            "Het clubbadge rechtsonder schaalt mee met het scherm",
        ],
    },
    {
        "versie": "1.17.0",
        "datum": "30 september 2026",
        "punten": [
            "Nieuw: Sponsoren met logo (Kantine-tv > Sponsoren) -- 'Mede mogelijk gemaakt door'-dia's die tussen alle dia's van het kantine scherm door komen en af en toe over de prijzenlijst heen; per groep (bijv. 'Zaterdag 1') samen op 1 dia, en alles zelf in te stellen (hoe vaak, hoe lang, koptekst, achtergrond)",
            "De aftelklok van de Club van 20-aankondiging staat nu ook op de wervingsdia van het kantine scherm",
        ],
    },
    {
        "versie": "1.16.3",
        "datum": "30 september 2026",
        "punten": [
            "Aankondiging met aftelklok bovenaan de publieke Club van 20-pagina (waar de QR-code heen gaat), in te stellen bij Scherm & werving",
        ],
    },
    {
        "versie": "1.16.2",
        "datum": "30 september 2026",
        "punten": [
            "Club van 20-teamstrijd: elk team dat bij een lid staat doet mee, ook als er nog niemand van betaald heeft (dan met 0)",
            "Kolom 'Betaald door' uit het Club van 20-overzicht gehaald (staat nog wel bij de details van een lid)",
        ],
    },
    {
        "versie": "1.16.1",
        "datum": "29 september 2026",
        "punten": [
            "Club van 20-leden archiveren (per lid of meerdere tegelijk): van het scherm af, betaalhistorie blijft bewaard, en later weer terug te zetten",
            "Club van 20-dia's: de bordjes zijn op de laatste dia even groot als op de andere (grotere bordjes op de laatste dia is nu een instelling)",
            "Uitleg bij de kolom 'Betaald door' in het Club van 20-overzicht",
        ],
    },
    {
        "versie": "1.16.0",
        "datum": "29 september 2026",
        "punten": [
            "Club van 20 heeft een eigen onderdeel in het menu: leden met naambordje, team en contactgegevens, en per seizoen of ze betaald hebben (net als de oude spreadsheet)",
            "Betalingen per lid direct in de tabel bijwerken, meerdere leden tegelijk op 'gevraagd' zetten, en een kant-en-klaar WhatsApp-betaalverzoek",
            "Projecten bijhouden waar het Club van 20-geld aan besteed wordt",
            "Nieuwe Club van 20-dia's in de stijl van de oude dia's: naammuur met gouden/zilveren bordjes voor trouwe leden, 'Samen opgehaald' met het volgende doel, teamstrijd, welkom nieuwe leden en een wervingsdia met QR-code",
            "Openbare Club van 20-pagina (via de QR-code) met alle namen, opbrengst en projecten",
            "De oude Club van 20-spreadsheet importeren (en de administratie exporteren) als CSV",
        ],
    },
    {
        "versie": "1.15.16",
        "datum": "29 september 2026",
        "punten": [
            "Man of the Match-dia vormgegeven in de stijl van voetbal.nl's wedstrijdpagina (clublogo's + uitslag, zonder foto's) -- tegenstander is nu ook per team in te vullen",
        ],
    },
    {
        "versie": "1.15.15",
        "datum": "29 september 2026",
        "punten": [
            "Man of the Match-dia: uitslag per team is nu ook in te vullen (naast de naam), en de titel boven de dia is zelf aan te passen",
        ],
    },
    {
        "versie": "1.15.14",
        "datum": "29 september 2026",
        "punten": [
            "Fix: teamnamen in de standen-dia op het kantine scherm waren onzichtbaar op een smal scherm (zoals de tablet-app)",
        ],
    },
    {
        "versie": "1.15.13",
        "datum": "29 september 2026",
        "punten": [
            "Standen: zelf poules toevoegen en verwijderen bij 'Standen bijwerken' (was een vaste lijst van precies 3)",
        ],
    },
    {
        "versie": "1.15.12",
        "datum": "29 september 2026",
        "punten": [
            "Titel van een standen-dia is nu per poule aan te passen (bijv. 'ZA 2' naar 'Zaterdag 2'), bij 'Standen bijwerken'",
        ],
    },
    {
        "versie": "1.15.11",
        "datum": "29 september 2026",
        "punten": [
            "Teamnamen zijn nu ook achteraf aan te passen (standen en Man of the Match), en bij Man of the Match kunnen meerdere namen (komma-gescheiden) per team ingevuld worden",
        ],
    },
    {
        "versie": "1.15.10",
        "datum": "28 september 2026",
        "punten": [
            "Man of the Match-dia toegevoegd (in de stijl van voetbal.nl, zonder foto's) -- alleen teams met een ingevulde speler komen in beeld",
        ],
    },
    {
        "versie": "1.15.9",
        "datum": "27 september 2026",
        "punten": [
            "Standen-dia's: W/GL/V (Gespeeld en Punten volgen daaruit) en clublogo's toegevoegd, met een herbruikbaar logo-register per club",
        ],
    },
    {
        "versie": "1.15.8",
        "datum": "27 september 2026",
        "punten": [
            "Nieuw: standen-dia's op het kantine scherm voor ZA 2, ZA 3 en O23 -- teams zelf slepen in de juiste volgorde bij Kiosk → Dia's & sponsoren",
        ],
    },
    {
        "versie": "1.15.7",
        "datum": "27 september 2026",
        "punten": [
            "Weergaveduur van de \"komende thuiswedstrijden\"-dia op het kantine scherm is nu zelf instelbaar (was vast op 10 seconden)",
        ],
    },
    {
        "versie": "1.15.6",
        "datum": "27 september 2026",
        "punten": [
            "Prijzenscherm past zichzelf automatisch aan zodat alles op 1 scherm blijft passen, ook met het uitgelichte product (\"snack van de week\") erbij",
        ],
    },
    {
        "versie": "1.15.5",
        "datum": "25 september 2026",
        "punten": [
            "Trainingsavond-modus op het prijzenscherm is nu een handmatige knop (bij Prijzenscherm instellen) i.p.v. automatisch op de vaste kalenderdag",
        ],
    },
    {
        "versie": "1.15.4",
        "datum": "25 september 2026",
        "punten": [
            "Testknop wedstrijddag-welkomstmelding (tablet): toont nu de eerstvolgende bekende tegenstander i.p.v. het kale 'Tegenstander'",
        ],
    },
    {
        "versie": "1.15.3",
        "datum": "23 september 2026",
        "punten": [
            "Wedstrijddag-welkomstmelding op het prijzenscherm: de vaste gele banner is weg, alleen nog de schermvullende melding die af en toe verschijnt",
        ],
    },
    {
        "versie": "1.15.2",
        "datum": "23 september 2026",
        "punten": [
            "Bardienst op het prijzenscherm: nu subtiel in de kop (tussen titel en klok) i.p.v. een gele balk onderaan -- bij een wissel naar een nieuwe dienst verschijnen de namen ook even groot in beeld",
        ],
    },
    {
        "versie": "1.15.1",
        "datum": "22 september 2026",
        "punten": [
            "Nieuw: verplichte 6-cijferige tablet-code bij de eerste keer inloggen (te wijzigen via 'Welkom, [naam]' → 'Tablet-code wijzigen') -- voorbereiding op aanmelden via de kiosk-tablet zonder gebruikersnaam",
        ],
    },
    {
        "versie": "1.15.0",
        "datum": "21 september 2026",
        "punten": [
            "Accounts beheren vernieuwd: elk account is nu uitklapbaar voor alle instellingen op één plek (i.p.v. één brede tabel)",
            "Nieuw: 2 extra rechten-secties (Kantine-tv, Club instellingen) zodat een vrijwilliger ook zonder beheerder te zijn het prijzenscherm/de dia's of de club-agenda kan beheren",
            "Nieuw: een account tijdelijk blokkeren (inloggen geweigerd) zonder het te verwijderen",
            "Nieuw: een wachtwoord-link opnieuw versturen voor een account",
        ],
    },
    {
        "versie": "1.14.2",
        "datum": "21 september 2026",
        "punten": [
            "Chromecasten van een losse video-URL naar het prijzenscherm verwijderd (werkte niet meer)",
            "Prijsopties (bijv. pitcher/glas van een fust) tonen weer als gewone prijsregels i.p.v. een omlijnd kaartje",
            "Nieuw: 1 zelf gekozen product groot en omlijnd uitlichten op het prijzenscherm (bijv. 'Snack van de week'), los van zijn eigen categorie, bij Kiosk → Prijzenscherm & acties",
        ],
    },
    {
        "versie": "1.14.1",
        "datum": "21 september 2026",
        "punten": [
            "Fix: het prijzenscherm kon vastlopen met een foutmelding op het moment dat het zichzelf herlaadde (bijv. op een Chromecast) tijdens het bijwerken van de site",
            "Nieuw: indeling van het prijzenscherm zelf te slepen over 3 vaste kolommen (bijv. dranken links) bij Kiosk → Prijzenscherm & acties",
        ],
    },
    {
        "versie": "1.14.0",
        "datum": "21 september 2026",
        "punten": [
            "Kiosk-hub toont nu een live miniatuurvoorbeeld van elk van de 3 schermen i.p.v. alleen tekst en knoppen; QR-codes staan achter een knopje",
            "Wedstrijddag-welkomstbanner verschijnt nu ook af en toe groot in beeld, en houdt bij een bekende aanvangstijd rekening met een tijdvak (en met meerdere thuiswedstrijden op één dag)",
            "Prijsopties (bijv. pitcher/glas van een fust) staan nu in een duidelijk afgebakend special-kaartje op het prijzenscherm i.p.v. tussen de gewone prijsregels",
            "Nieuw 'Prijs'-element in de sjabloonbouwer: koppel een vlak op een dia aan een zelf gekozen product, toont altijd de actuele verkoopprijs",
        ],
    },
    {
        "versie": "1.13.0",
        "datum": "20 september 2026",
        "punten": [
            "Dia's en Prijzenscherm & acties opnieuw ingedeeld met tabbladen i.p.v. één lange pagina of losse verstopte schermen",
            "Trainingsavond-tabblad bij Producten: eigen productselectie voor de vaste trainingsavond, het prijzenscherm schakelt daar automatisch naartoe",
            "Wedstrijddag-welkomstbanner op het prijzenscherm: speelt de club vandaag thuis (volgens de agenda), dan verschijnt automatisch een instelbare welkomsttekst met de tegenstander erin",
        ],
    },
    {
        "versie": "1.12.0",
        "datum": "20 september 2026",
        "punten": [
            "Nieuwe pagina 'Gebruiksstatistieken' (Club, alleen beheerder): bezoeken per dag, meest gebruikte functies, gebruik per account en desktop vs. handterminal — puur intern, geen externe trackingdienst",
        ],
    },
    {
        "versie": "1.11.7",
        "datum": "20 september 2026",
        "punten": [
            "Bardienst aanmaken (Kiosk) vulde de datum rond middernacht soms een dag te vroeg in door hetzelfde tijdzoneverschil als de eerdere weergavefix -- vult nu ook hier de juiste (Amsterdamse) datum in",
        ],
    },
    {
        "versie": "1.11.6",
        "datum": "20 september 2026",
        "punten": [
            "'Kassalade volledig legen' vulde bij een stand van €1000 of meer een bedrag in dat niet werd geaccepteerd -- werkt nu ook correct bij grote bedragen",
        ],
    },
    {
        "versie": "1.11.5",
        "datum": "20 september 2026",
        "punten": [
            "De UITVERKOCHT-popup op het prijzenscherm toonde bij een product met prijsopties (bijv. een fust) de naam van de portie (\"Klein glas\") i.p.v. het product zelf (\"Jupiler\") -- toont nu de juiste naam, en maar 1x per product",
        ],
    },
    {
        "versie": "1.11.4",
        "datum": "20 september 2026",
        "punten": [
            "Een account verwijderen dat nog in boekingen, tellingen of kassa-/kluisgeschiedenis voorkomt gaf een foutpagina -- geeft nu een duidelijke melding met het advies om het account op vrijwilliger zonder secties te zetten in plaats van te verwijderen",
        ],
    },
    {
        "versie": "1.11.3",
        "datum": "16 september 2026",
        "punten": [
            "Product bewerken heeft een nieuw veld 'Categorie op het prijzenscherm' -- handig om bijv. prijsopties van een fust (pitcher/glas) onder een bestaande verkoopcategorie zoals 'Bier' te tonen in plaats van onder de echte (tel)categorie",
            "Kolommen op het prijzenscherm die per ongeluk niet mooi op een lijn stonden met de rest, staan nu weer netjes uitgelijnd",
        ],
    },
    {
        "versie": "1.11.2",
        "datum": "16 september 2026",
        "punten": [
            "De gele bardienst-balk op het prijzenscherm kon de laatste prijzen aan de onderkant verbergen als de prijslijst al (bijna) het hele scherm vulde -- staat nu altijd los onder de prijzen, nooit meer eroverheen",
        ],
    },
    {
        "versie": "1.11.1",
        "datum": "16 september 2026",
        "punten": [
            "Een product verwijderen dat nog in een bestelling of telling voorkomt gaf een foutpagina -- geeft nu een duidelijke melding met het advies om het product op inactief te zetten in plaats van te verwijderen",
        ],
    },
    {
        "versie": "1.11.0",
        "datum": "16 september 2026",
        "punten": [
            "Product bewerken heeft een nieuw veld 'Prijsopties op het prijzenscherm' -- voor een product dat je niet in zijn geheel verkoopt (bijv. een fust), kun je nu losse porties met eigen naam en prijs opgeven (bijv. pitcher en glas) die op het prijzenscherm verschijnen in plaats van de gewone verkoopprijs",
        ],
    },
    {
        "versie": "1.10.1",
        "datum": "16 september 2026",
        "punten": [
            "Bardienst op het prijzenscherm werkte rond middernacht soms niet door een tijdzoneverschil tussen de server en het scherm zelf -- werkt nu ook correct bij een dienst die middernacht overschrijdt",
        ],
    },
    {
        "versie": "1.10.0",
        "datum": "14 september 2026",
        "punten": [
            "Nieuwe 'Tips & functies'-pagina met een overzicht van alle functies per onderdeel (link in de footer)",
            "Verkooprapport laat nu per omzetbalk ook trainingsavonden zien (naast de bestaande thuiswedstrijden-indicator), plus het aantal dagen en de omzet per dag van die periode",
            "Een ongebruikelijk korte of lange telperiode wordt gemarkeerd en genegeerd in de omzettrend en het weekoverzicht, zodat een andere teldag de cijfers niet vertekent",
            "Tekortvoorspelling houdt nu ook rekening met trainingsavonden, naast wedstrijden en het weer",
        ],
    },
    {
        "versie": "1.9.0",
        "datum": "8 september 2026",
        "punten": [
            "Producten-pagina getoond per categorie, inklapbaar, i.p.v. één lange tabel",
            "Per product instelbaar: automatisch op inactief zodra de voorraad op 0 komt",
            "Verbruiksvoorwerpen (bijv. bakjes): eigen lijst zonder voorraad, alleen voor schaplabels en om op de bestellijst te zetten",
            "QR-code op een schaplabel scannen opent nu een keuzescherm: naar de productpagina, of (zonder account) melden voor de bestellijst",
            "Bestellijst toont nu ook wat bezoekers zo hebben gemeld, met een teller en een 'afhandelen'-knop",
        ],
    },
    {
        "versie": "1.8.0",
        "datum": "8 september 2026",
        "punten": [
            "Rechten per account nu instelbaar per sectie (Voorraad/Kassa/Keuken/Stemmen) i.p.v. alleen beheerder/vrijwilliger",
            "Schaplabels printen (A4, om te knippen) met logo, minimumvoorraad en een QR-code naar de productpagina — per product of in bulk vanaf Producten",
            "QR-code op een schaplabel scannen (handterminal) opent direct dat product, ook met de camera-app van je telefoon zelf",
            "Boeken werkt nu door bij een wegvallende verbinding: de boeking wordt lokaal bewaard en alsnog verstuurd zodra er weer bereik is",
            "Looplijst tellen probeert het na een mislukte stap nu vanzelf opnieuw zodra de verbinding terugkomt",
        ],
    },
    {
        "versie": "1.7.0",
        "datum": "6 september 2026",
        "punten": [
            "Keuken heeft nu een eigen plek in het menu: voorraad en frituurvet-instellingen bij elkaar",
            "'+ Nieuw Keuken-product' zet de categorie meteen goed bij het aanmaken",
        ],
    },
    {
        "versie": "1.6.0",
        "datum": "6 september 2026",
        "punten": [
            "Keuken toegevoegd als categorie, voor frituursnacks, gehaktballen e.d. — werkt met dezelfde voorraad, bestellijst en tellijsten als de rest",
            "Herinnering op het dashboard voor het vervangen van het frituurvet, met instelbare termijn (Instellingen)",
        ],
    },
    {
        "versie": "1.5.0",
        "datum": "6 september 2026",
        "punten": [
            "Boodschappenlijst voor losse inkopen buiten de vaste voorraad om (bijv. schoonmaakspullen)",
            "Leveringen inboeken op de handterminal: alles start als manco, pas aanvinken als het echt binnen is gecontroleerd",
            "Handterminal beperkt tot inboeken/controleren/manco melden; bestellen en leveringen inladen blijven desktop",
            "Zoekbalk en productpagina op de handterminal, bestellijst en inboeken als kaartjes i.p.v. een tabel",
            "Rotatiebug op de handterminal opgelost, meer icoon-knoppen, kortere instructieteksten",
            "Inloggen fors versneld (wachtwoord-controle nam voorheen ruim 0,7 seconde per poging in beslag)",
            "Tellingregel achteraf kunnen corrigeren, bijv. als er bij het tellen iets over het hoofd is gezien",
        ],
    },
    {
        "versie": "1.4.0",
        "datum": "25 augustus 2026",
        "punten": [
            "Bijzonderheden: mededelingen 'afhandelen' i.p.v. alleen verwijderen, met wie en wanneer",
            "Urgente mededelingen vallen op tussen de rest van het prikbord",
            "Een mededeling met één klik als de site-brede banner tonen",
        ],
    },
    {
        "versie": "1.3.0",
        "datum": "25 augustus 2026",
        "punten": [
            "Vier-ogen-principe bij kassatellingen: de teller keurt zijn eigen telling niet meer zelf goed",
            "Opmerking bij goedkeuring, apart van de opmerking van de teller",
            "Wie geteld en wie goedgekeurd heeft staat nu in het kasverslag (scherm en PDF)",
            "Team-agenda's en weer gecombineerd op de nieuwe Wedstrijden-pagina",
            "Voorspelde tekorten op de bestellijst, ook boven het minimum",
            "Correctie-boekingen licht rood gemarkeerd in de geschiedenis",
        ],
    },
    {
        "versie": "1.2.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Automatische tests bij elke push naar GitHub (CI)",
            "Signalering van verouderde dependencies (Dependabot)",
            "Beveiligingsheaders toegevoegd (Content-Security-Policy e.a.)",
            "Uurlijkse controle of de site bereikbaar is, met mailmelding bij storing",
        ],
    },
    {
        "versie": "1.1.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Geautomatiseerde tests voor de kernberekeningen (kassa, voorraad, inloggen)",
            "Overgestapt naar Python 3.13 (voorheen 3.9), zowel lokaal als op de server",
        ],
    },
    {
        "versie": "1.0.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Nieuwe kassa-module: tellen per coupure, afdracht/toevoeging boeken, kassa-geschiedenis",
            "Wekelijks overzicht: nieuwe pagina + opgemaakte maandagochtend-mail met logo",
            "Boekingen gekoppeld aan het echte ingelogde account i.p.v. een vrij in te typen naam",
            "Wegklikbare mededelingenbalk bovenaan de site, instelbaar door de beheerder",
            "Omzettrend op het dashboard en het verkooprapport",
        ],
    },
    {
        "versie": "0.4.0",
        "datum": "23 augustus 2026",
        "punten": [
            "Bestellen, ontvangen en leveringen inboeken per besteleenheid (bijv. kratten, dozen)",
            "Verkoopprijs vastgezet per telling, zodat latere prijswijzigingen historische omzet niet meer aantasten",
            "Inkoopprijzen, artikelcodes en besteleenheden bijgewerkt op basis van de leverancierslijst",
            "Subcategorieën onder hoofdcategorieën",
            "Zelf-registratie via e-mail, wachtwoord vergeten, en mailvoorkeuren per account",
            "Mobiele navigatie herzien, homescreen-icoon, eigen 404/500-paginas, favicons",
        ],
    },
    {
        "versie": "0.3.0",
        "datum": "22 augustus 2026",
        "punten": [
            "Categorieën als beheerbare lijst, filter/zoekbalk op de Producten-pagina",
            "Rollen en rechten voor accounts (beheerder/vrijwilliger)",
            "Uitgebreid voorraadoverzicht met waarde per categorie en PDF",
        ],
    },
    {
        "versie": "0.2.0",
        "datum": "21 augustus 2026",
        "punten": [
            "Automatische dagelijkse back-up, met terugzetten vanuit de app",
            "Prikbord (Bijzonderheden)",
            "Losse levering/factuur inboeken, controlescherm na de looplijst",
        ],
    },
    {
        "versie": "0.1.0",
        "datum": "20 augustus 2026",
        "punten": [
            "Eerste versie: producten, voorraad bijhouden, in-/uitboeken",
            "Inloggen en accountbeheer",
            "Voorraad tellen, ook via een looplijst voor onderweg met de telefoon",
            "Verkooprapport per periode (PDF), huisstijl s.v. Blauw-Geel 1915",
        ],
    },
]


def register_routes(app):
    @app.route("/help")
    def help_pagina():
        return render_template(
            "help.html", huidige_versie=HUIDIGE_VERSIE, wijzigingen=WIJZIGINGEN
        )

    @app.route("/tips")
    def tips_pagina():
        return render_template("tips.html")

    def bereken_omzet_trend(db, aantal_dagen=8):
        """Omzet per dag (chronologisch, tellingen van dezelfde dag samengevoegd
        tot één balk) plus de best verkopende producten over die periode --
        gebruikt voor het trendgrafiekje op het dashboard. Rekent altijd met
        de bevroren telling-prijs (tr.verkoopprijs), niet de actuele
        productprijs, om dezelfde reden als het verkooprapport."""
        ruwe_dagen = db.execute(
            """SELECT date(t.datum) AS dag,
                      COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
               FROM tellingen t
               LEFT JOIN telling_regels tr ON tr.telling_id = t.id
               GROUP BY dag
               ORDER BY dag DESC
               LIMIT ?""",
            (aantal_dagen,),
        ).fetchall()
        dagen = list(reversed(ruwe_dagen))

        top_verkopers = []
        if dagen:
            dag_lijst = [d["dag"] for d in dagen]
            placeholders = ",".join("?" for _ in dag_lijst)
            top_verkopers = db.execute(
                f"""SELECT p.naam AS product_naam, p.eenheid,
                           SUM(tr.verkocht) AS verkocht,
                           SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                    FROM telling_regels tr
                    JOIN producten p ON p.id = tr.product_id
                    JOIN tellingen t ON t.id = tr.telling_id
                    WHERE date(t.datum) IN ({placeholders})
                    GROUP BY tr.product_id
                    HAVING SUM(tr.verkocht) > 0
                    ORDER BY omzet DESC
                    LIMIT 6""",
                dag_lijst,
            ).fetchall()

        max_omzet = max((d["omzet"] for d in dagen), default=0)
        laatste_omzet = dagen[-1]["omzet"] if dagen else 0
        eerdere_omzetten = [d["omzet"] for d in dagen[:-1]]
        gemiddelde_omzet = (
            sum(eerdere_omzetten) / len(eerdere_omzetten) if eerdere_omzetten else 0
        )
        verschil_percentage = None
        if gemiddelde_omzet > 0:
            verschil_percentage = (laatste_omzet - gemiddelde_omzet) / gemiddelde_omzet * 100

        balken = [
            {
                "datum_kort": datetime.strptime(d["dag"], "%Y-%m-%d").strftime("%d-%m"),
                "omzet": d["omzet"],
                "hoogte_pct": (d["omzet"] / max_omzet * 100) if max_omzet else 0,
            }
            for d in dagen
        ]

        return {
            "balken": balken,
            "top_verkopers": top_verkopers,
            "laatste_omzet": laatste_omzet,
            "gemiddelde_omzet": gemiddelde_omzet,
            "verschil_percentage": verschil_percentage,
        }

    @app.route("/")
    def dashboard():
        if g.get("weergave_modus") == "pda":
            # Geen van de zware dashboard-cijfers is relevant voor de
            # PDA-modus (puur een menu naar de vloerpagina's), dus die
            # queries hoeven hier niet te draaien.
            return render_template("pda_start.html", groet=dagdeel_groet())

        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        laag = [p for p in producten if p["voorraad"] < p["min_voorraad"]]
        recente_mutaties = db.execute(
            """SELECT m.*, p.naam AS product_naam, p.eenheid
               FROM mutaties m JOIN producten p ON p.id = m.product_id
               ORDER BY m.id DESC LIMIT 8"""
        ).fetchall()
        open_bestellingen = db.execute(
            "SELECT COUNT(*) AS n FROM bestellingen WHERE status = 'besteld'"
        ).fetchone()["n"]
        omzet_trend = bereken_omzet_trend(db)
        komende_thuiswedstrijden = bereken_komende_thuiswedstrijden(db)
        return render_template(
            "dashboard.html",
            producten=producten,
            laag=laag,
            recente_mutaties=recente_mutaties,
            open_bestellingen=open_bestellingen,
            omzet_trend=omzet_trend,
            komende_thuiswedstrijden=komende_thuiswedstrijden,
            laatste_telling_status=bereken_laatste_telling_status(db),
            kassa_telling_status=bereken_kassa_telling_status(db),
            bestelling_status=bereken_bestelling_status(db),
            frituurvet_status=bereken_frituurvet_status(db),
            # Alleen voor wie de Club van 20-sectie heeft (beheerders altijd) --
            # deze query overslaan voor wie de tegel toch niet te zien krijgt.
            club_van_20_status=(
                bereken_club_van_20_status(db)
                if heeft_sectie_toegang(
                    session.get("gebruiker_rol"), session.get("gebruiker_secties"), "club_van_20"
                )
                else None
            ),
        )

    @app.route("/verkooprapport")
    def verkooprapport():
        van = request.args.get("van") or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        tot = request.args.get("tot") or datetime.now().strftime("%Y-%m-%d")
        db = get_db()
        omzet_trend = bereken_omzet_trend_periode(db, van, tot)
        return render_template(
            "verkooprapport.html", van=van, tot=tot, omzet_trend=omzet_trend
        )

    @app.route("/week-overzicht")
    def week_overzicht():
        db = get_db()
        overzicht = bereken_week_overzicht(db)
        return render_template("week_overzicht.html", overzicht=overzicht)

    @app.route("/wedstrijden")
    def wedstrijden_overzicht():
        db = get_db()
        komende_thuiswedstrijden = bereken_komende_thuiswedstrijden(db)
        wedstrijd_geschiedenis = bereken_wedstrijd_geschiedenis(db)
        return render_template(
            "wedstrijden.html",
            komende_thuiswedstrijden=komende_thuiswedstrijden,
            wedstrijd_geschiedenis=wedstrijd_geschiedenis,
        )

    @app.route("/verkooprapport/pdf")
    def verkooprapport_pdf_route():
        van = request.args.get("van", "").strip() or (
            datetime.now() - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        tot = request.args.get("tot", "").strip() or datetime.now().strftime("%Y-%m-%d")

        db = get_db()
        # Sommeert per regel verkocht * de destijds vastgezette prijs, i.p.v.
        # de huidige prijs van het product -- een periode kan meerdere
        # tellingen omvatten waartussen de prijs kan zijn gewijzigd.
        regels = db.execute(
            """SELECT p.naam AS product_naam, p.categorie, p.subcategorie, p.eenheid,
                      SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                      SUM(tr.verkocht * tr.verkoopprijs) AS omzet
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
               JOIN producten p ON p.id = tr.product_id
               WHERE t.datum >= ? AND t.datum <= ?
               GROUP BY tr.product_id
               ORDER BY p.categorie, p.naam""",
            (f"{van} 00:00", f"{tot} 23:59"),
        ).fetchall()

        pdf_bytes = periode_verkoop_pdf(format_datum(f"{van} 00:00"), format_datum(f"{tot} 23:59"), regels)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-{van}-tot-{tot}.pdf"
            },
        )

    @app.route("/verkooprapport/csv")
    def verkooprapport_csv_route():
        van = request.args.get("van", "").strip() or (
            datetime.now() - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        tot = request.args.get("tot", "").strip() or datetime.now().strftime("%Y-%m-%d")

        db = get_db()
        regels = db.execute(
            """SELECT p.naam AS product_naam, p.categorie, p.subcategorie, p.eenheid,
                      SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                      SUM(tr.verkocht * tr.verkoopprijs) AS omzet
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
               JOIN producten p ON p.id = tr.product_id
               WHERE t.datum >= ? AND t.datum <= ?
               GROUP BY tr.product_id
               ORDER BY p.categorie, p.naam""",
            (f"{van} 00:00", f"{tot} 23:59"),
        ).fetchall()
        rijen = [
            (
                r["product_naam"],
                r["categorie"],
                r["subcategorie"] or "",
                r["verkocht"],
                r["eenheid"],
                f"{r['omzet']:.2f}".replace(".", ","),
            )
            for r in regels
            if r["verkocht"] > 0
        ]
        return csv_response(
            f"verkooprapport-{van}-tot-{tot}.csv",
            ["Product", "Categorie", "Subcategorie", "Verkocht", "Eenheid", "Omzet"],
            rijen,
        )

    # ---------- Geschiedenis ----------

    @app.route("/geschiedenis")
    def geschiedenis():
        db = get_db()
        product_id = request.args.get("product_id", type=int)

        query = """SELECT m.*, p.naam AS product_naam, p.eenheid
                    FROM mutaties m JOIN producten p ON p.id = m.product_id"""
        params = ()
        if product_id:
            query += " WHERE m.product_id = ?"
            params = (product_id,)
        query += " ORDER BY m.id DESC LIMIT 300"

        mutaties = db.execute(query, params).fetchall()
        producten = db.execute("SELECT id, naam FROM producten ORDER BY naam").fetchall()
        return render_template(
            "geschiedenis.html",
            mutaties=mutaties,
            producten=producten,
            gekozen_product_id=product_id,
        )

    # ---------- Bijzonderheden (prikbord) ----------

    @app.route("/bijzonderheden", methods=["GET", "POST"])
    def bijzonderheden():
        db = get_db()
        if request.method == "POST":
            tekst = request.form.get("tekst", "").strip()
            if not tekst:
                flash("Vul een tekst in.", "error")
                return redirect(url_for("bijzonderheden"))
            naam = session.get("gebruiker_naam")
            cur = db.execute(
                "INSERT INTO mededelingen (tekst, naam, datum, urgent) VALUES (?, ?, ?, ?)",
                (tekst, naam, now_str(), 1 if request.form.get("urgent") else 0),
            )
            db.commit()
            stuur_tag_notificaties(
                db, tekst, naam, "nieuwe mededeling", url_for("bijzonderheden", _external=True)
            )
            return redirect(url_for("bijzonderheden"))

        # Nog niet afgehandeld eerst (urgent bovenaan), afgehandelde
        # onderaan -- zodat het prikbord niet dichtslibt met opgeloste
        # dingen, maar ze ook niet spoorloos verdwijnen zoals bij
        # verwijderen.
        mededelingen = db.execute(
            "SELECT * FROM mededelingen ORDER BY afgehandeld ASC, urgent DESC, id DESC"
        ).fetchall()
        opmerkingen_per_mededeling = {}
        for regel in db.execute(
            "SELECT * FROM mededeling_opmerkingen ORDER BY id ASC"
        ).fetchall():
            opmerkingen_per_mededeling.setdefault(regel["mededeling_id"], []).append(regel)
        gebruikersnamen = [
            g["naam"] for g in db.execute("SELECT naam FROM gebruikers ORDER BY naam").fetchall()
        ]
        return render_template(
            "bijzonderheden.html",
            mededelingen=mededelingen,
            opmerkingen_per_mededeling=opmerkingen_per_mededeling,
            gebruikersnamen=gebruikersnamen,
        )

    @app.route("/bijzonderheden/<int:mededeling_id>/opmerking", methods=["POST"])
    def mededeling_opmerking_toevoegen(mededeling_id):
        db = get_db()
        mededeling = db.execute(
            "SELECT * FROM mededelingen WHERE id = ?", (mededeling_id,)
        ).fetchone()
        if mededeling is None:
            flash("Mededeling niet gevonden.", "error")
            return redirect(url_for("bijzonderheden"))
        tekst = request.form.get("tekst", "").strip()
        if not tekst:
            flash("Vul een tekst in.", "error")
            return redirect(url_for("bijzonderheden"))
        naam = session.get("gebruiker_naam")
        db.execute(
            "INSERT INTO mededeling_opmerkingen (mededeling_id, tekst, naam, gebruiker_id, datum) "
            "VALUES (?, ?, ?, ?, ?)",
            (mededeling_id, tekst, naam, session.get("gebruiker_id"), now_str()),
        )
        db.commit()
        stuur_tag_notificaties(
            db, tekst, naam, "reactie op een mededeling", url_for("bijzonderheden", _external=True)
        )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/verwijderen", methods=["POST"])
    def mededeling_verwijderen(mededeling_id):
        db = get_db()
        db.execute("DELETE FROM mededelingen WHERE id = ?", (mededeling_id,))
        db.commit()
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/afhandelen", methods=["POST"])
    def mededeling_afhandelen(mededeling_id):
        db = get_db()
        db.execute(
            """UPDATE mededelingen
               SET afgehandeld = 1, afgehandeld_door = ?, afgehandeld_op = ?
               WHERE id = ?""",
            (session.get("gebruiker_naam"), now_str(), mededeling_id),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgehandeld": 1,
                    "melding": "Afgehandeld. Zakt bij de volgende paginalaad naar onderen.",
                }
            )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/heropenen", methods=["POST"])
    def mededeling_heropenen(mededeling_id):
        db = get_db()
        db.execute(
            """UPDATE mededelingen
               SET afgehandeld = 0, afgehandeld_door = NULL, afgehandeld_op = NULL
               WHERE id = ?""",
            (mededeling_id,),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgehandeld": 0,
                    "melding": "Heropend. Komt bij de volgende paginalaad weer bovenaan te staan.",
                }
            )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/pin-als-banner", methods=["POST"])
    def mededeling_pinnen_als_banner(mededeling_id):
        db = get_db()
        mededeling = db.execute(
            "SELECT * FROM mededelingen WHERE id = ?", (mededeling_id,)
        ).fetchone()
        if mededeling is None:
            flash("Mededeling niet gevonden.", "error")
            return redirect(url_for("bijzonderheden"))
        db.execute(
            "UPDATE instellingen SET banner_tekst = ? WHERE id = 1", (mededeling["tekst"],)
        )
        db.commit()
        flash("Mededeling als banner bovenaan de site gezet.", "success")
        return redirect(url_for("bijzonderheden"))
