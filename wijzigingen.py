"""Het handmatig bijgehouden versie-logje voor de Help-pagina (/help).

Bij elke gebruikersgerichte wijziging: HUIDIGE_VERSIE ophogen en bovenaan
WIJZIGINGEN een item toevoegen (zie CLAUDE.md)."""

# Handmatig bijgehouden versie-overzicht voor de Help-pagina. Geen
# geautomatiseerd systeem (geen releases/tags) -- gewoon een leesbaar logje
# van wat er is toegevoegd, bijgewerkt bij noemenswaardige wijzigingen.
HUIDIGE_VERSIE = "1.37.0"
WIJZIGINGEN = [
    {
        "versie": "1.37.0",
        "datum": "10 oktober 2026",
        "punten": [
            "Kantine-tv, dia 'Welkom nieuwe leden': veel groter (1 nieuw lid vult bijna het hele scherm, bij meer namen worden ze vanzelf kleiner), lange namen staan op 2 regels in plaats van afgekapt, en bij 12 nieuwe leden past de titel nu ook weer op het scherm.",
            "Club van 20: zodra een lid betaalt (nieuw of verlenging, ook via een goedgekeurde aanmelding) komt er op alle schermen even groot een melding met de naam: 'Welkom in de Club van 20!' of 'Bedankt voor je verlenging!' met de sterren. Komen er meer tegelijk, dan staan ze in een wachtrij en komen ze achter elkaar. Bij Club van 20 → Scherm & werving zet je het uit, stel je de duur per melding in en stuur je een testmelding.",
        ],
    },
    {
        "versie": "1.36.0",
        "datum": "10 oktober 2026",
        "punten": [
            "Kantine-tv, dia 'Leden? Steun de club!': nu standaard 24 namen per dia (bij veel namen worden kop en onderkant compacter, zodat alle namen leesbaar blijven) en kleine teksten onder de dia: 'Wel drinken bestellen maar niet die 20 euro betalen?', 'Elke week de kantine tot de laatste cent leeg kopen, maar de club van 20 is te veel?' en 'Scan de QR of regel de betaling bij de bar'. Bij Club van 20 → Scherm & werving kun je het aantal namen en die teksten aanpassen (elke regel een eigen tekst, max. 3) of ze leeg laten.",
            "Club van 20: de naambordjes van de leden kunnen nu uit op de openbare pagina (Scherm & werving → 'Leden op de publieke pagina'). Bezoekers zien dan alleen aantallen, spaardoel, projecten en teamstand; op het scherm in de kantine blijven de namen staan.",
        ],
    },
    {
        "versie": "1.35.0",
        "datum": "10 oktober 2026",
        "punten": [
            "Kantine-tv: nieuwe dramatische dia 'Leden? Steun de club!' met alle leden die dit seizoen nog niet hebben betaald maar eerder wel, 12 per dia, met de prijs en een QR-code om weer mee te doen. Bij Club van 20 > Scherm & werving zet je de dia uit of kies je het aantal namen per dia",
        ],
    },
    {
        "versie": "1.34.0",
        "datum": "9 oktober 2026",
        "punten": [
            "Tellingen, Prognose, Bestellijst en de omzetrapporten laden veel sneller (van enkele seconden naar een fractie daarvan): de berekening wordt bewaard en alleen opnieuw gedaan als er iets verandert, zoals een telling, de voorraad, een bestelling of een wedstrijd. De eerste keer na zo'n wijziging duurt nog even",
            "Mijn voorkeuren: nieuwe knop 'Uitloggen op alle andere toestellen', handig als je een telefoon kwijt bent of ingelogd bent gebleven op een toestel dat je niet meer gebruikt. Een nieuw wachtwoord logt de andere toestellen ook vanzelf uit",
            "Accounts (beheerders): per account een knop 'Overal uitloggen'",
        ],
    },
    {
        "versie": "1.33.0",
        "datum": "9 oktober 2026",
        "punten": [
            "Menu links opnieuw ingedeeld: 11 onderdelen i.p.v. 13 (Tellen zit nu bij Voorraad, kassa en kluis samen onder Geld, 'Club' heet nu Beheer), met een pictogram en een grotere kop. Er staat altijd maar één onderdeel open: klik je op een ander onderdeel, dan klapt het vorige vanzelf dicht",
            "Inloggen: nieuw vinkje 'Ingelogd blijven op dit toestel (30 dagen)', standaard aan. Je hoeft niet meer steeds opnieuw in te loggen na het sluiten van de browser of de app",
            "Dashboard: bovenaan een lijst 'Wat moet er nu?' met wat nu aandacht nodig heeft, afgestemd op wat jouw account mag zien",
            "Rapporten (beheerders): bij 'Omzet per seizoen' kun je met 'Eerdere seizoenen invullen' de omzet per maand uit de oude administratie invoeren, zodat ook seizoenen van vóór de eerste telling vergeleken kunnen worden",
            "Beheerders krijgen een mail als de site een serverfout geeft (maximaal 1 keer per uur per fout)",
        ],
    },
    {
        "versie": "1.32.0",
        "datum": "9 oktober 2026",
        "punten": [
            "Rapporten (alleen beheerders): nieuw rapport 'Omzet per bardienst'. Per persoon op de bardienstplanning zie je het aantal diensten, de uren en de gemiddelde omzet per dienst en per uur, ook gecorrigeerd voor drukke dagen (thuiswedstrijd, training, mooi weer) zodat je eerlijk kunt vergelijken",
            "Zoekbalk: zoekt nu ook in bestellingen, de boodschappenlijst, verbruiksvoorwerpen, afdrachten en stortingen van kassa en kluis, wedstrijden en sponsoren, en onthoudt je laatste 5 zoekopdrachten",
            "Back-ups (alleen beheerders): eens per maand wordt een back-up echt teruggezet in een wegwerp-database en helemaal doorgelezen. Je ziet de uitkomst op de Back-ups-pagina; mislukt het, dan krijg je een melding",
            "Privacy: paginabezoeken en het logboek worden na 2 jaar automatisch opgeruimd (en kortlopende inlogtellers na 30 dagen); de privacyverklaring noemt dat nu, en dat de back-up elke dag per e-mail wordt gekopieerd",
        ],
    },
    {
        "versie": "1.31.0",
        "datum": "8 oktober 2026",
        "punten": [
            "Zoekbalk bovenin elke pagina: typ een product, een telling (ook op datum, bijvoorbeeld 03-10-2026), een prikbordbericht, een lid van de Club van 20 of een pagina van de app en je ziet meteen de resultaten. Met de / op je toetsenbord ga je direct naar het zoekveld. Je ziet alleen wat jouw account mag zien",
            "Rapporten: nieuw rapport 'Omzet per seizoen' (1 juli t/m 30 juni): dit seizoen naast de vorige, per maand, per verkoopdag en tot dezelfde datum als vandaag, met de meest verkochte producten. Ook als PDF en Excel (CSV)",
            "Compacte uitdraai: je kunt er nu ook de bestellijst, de prognose voor de komende 7 dagen en de omzet per seizoen bij kiezen",
            "Logboek: downloaden als Excel (CSV) of PDF, met de periode en persoon die je hebt gekozen",
        ],
    },
    {
        "versie": "1.30.0",
        "datum": "7 oktober 2026",
        "punten": [
            "Compacte uitdraai: bij Rapporten maak je één A4 met het kasverslag, het kluisverslag en de huidige voorraadstand. Je vinkt aan wat erop moet; wat jouw account niet mag zien (de kluis is alleen voor beheerders) staat er niet bij",
            "Logboek (alleen beheerders): bij Club zie je wie wat deed, zoals accounts en rechten, kassa en kluis, producten, instellingen en back-ups, en wie er is ingelogd",
            "Back-ups: elke back-up wordt direct gecontroleerd, de kopie per e-mail komt nu elke dag in plaats van elke week, en het dashboard waarschuwt beheerders als de laatste back-up te oud is",
        ],
    },
    {
        "versie": "1.29.0",
        "datum": "7 oktober 2026",
        "punten": [
            "Club van 20 importeren: upload het Excel-bestand van de penningmeester en de site laat bovenaan zien wie er voor dit seizoen heeft verlengd (\"Status\" op Betaald): wie nog niet op betaald stond, wie al betaald was en wie nog geen lid is. Eén knop vinkt precies de leden aan die nog verlengd moeten worden. Een lid dat in het bestand op Betaald staat met een bedrag van 0 (bijvoorbeeld al vooruit betaald in het vorige seizoen) telt nu ook als verlengd, zonder dat het geld dubbel in de totalen komt",
        ],
    },
    {
        "versie": "1.28.0",
        "datum": "7 oktober 2026",
        "punten": [
            "Club van 20 importeren: in het voorbeeld kies je per lid of 'ie meegaat, met erbij wat er voor dat lid verandert. Niet aangevinkte leden blijven zoals ze in de app staan. Een lid waarvan een betaling in de app na de import anders zou zijn staat als \"let op\" standaard uit. Handige knoppen voor alles, niets of alleen nieuwe leden, en een zoekveld",
        ],
    },
    {
        "versie": "1.27.0",
        "datum": "7 oktober 2026",
        "punten": [
            "Man of the Match: kies per team of jullie hebben gewonnen, gelijkgespeeld of verloren. De dia zet de uitslag dan zelf in de juiste volgorde (eigen team links), ook als je de cijfers in een andere volgorde invult, en toont het resultaat in kleur onder de score",
        ],
    },
    {
        "versie": "1.26.1",
        "datum": "6 oktober 2026",
        "punten": [
            "Wedstrijden: ook een wedstrijd die al geweest is kun je achteraf op afgelast zetten (bij Gespeelde wedstrijden), zodat de prognose er niet meer van leert",
        ],
    },
    {
        "versie": "1.26.0",
        "datum": "6 oktober 2026",
        "punten": [
            "Prognose: er wordt alleen gerekend met de dagen waarop je verkoopt, standaard woensdag en zaterdag. Gesloten dagen verwachten niets en tellen niet mee bij het leren, en de weekomzet wordt alleen over de verkoopdagen verdeeld. In de testrun met jullie eigen tellingen zat de prognose daardoor merkbaar dichter bij de werkelijkheid",
            "Afgelaste thuiswedstrijden: zet een wedstrijd die niet doorgaat op afgelast (bij Prognose en bij Wedstrijden) en hij telt nergens meer mee: niet in de prognose, de dia's, de welkomstmelding en de kassa-herinnering. De agenda-koppeling markeert ook zelf wedstrijden die de feed als afgelast meldt of uit de agenda haalt",
            "Prognose: bovenaan de pagina stel je de vaste verkoopdagen in en geef je uitzonderingen per datum aan (een wedstrijd op zondag, een dichte woensdag), ook voor het verleden. Een thuiswedstrijd op een gesloten dag wordt je voorgelegd met de vraag of je die dag wel verkocht hebt",
        ],
    },
    {
        "versie": "1.25.0",
        "datum": "5 oktober 2026",
        "punten": [
            "Handterminal: het startscherm toont bovenaan wat aandacht nodig heeft (producten onder het minimum, bestellingen om in te boeken, aanmeldingen, prikbord, laatste telling, kassa, frituurvet, volgende thuiswedstrijd), met tellers op de knoppen, en heeft nieuwe knoppen voor Voorraad, Prognose, Tellingen, Keuken, Kluis en Aanmeldingen",
            "Handterminal: voorraadlijst per categorie met zoeken en \"alleen laag\", tellingen en het resultaat van een telling als compacte kaarten (niet meer de desktop-pagina), en op de Bestellijst nu ook het bestel-advies, de voorspelde tekorten en de meldingen om te bekijken",
            "Handterminal: aanmeldingen voor de Club van 20 goedkeuren of afwijzen, bijvoorbeeld aan de bar bij een contante betaling",
            "Looplijst: pauzeren en later verder, ook na uitloggen of op een ander toestel (3 dagen bewaard)",
            "Looplijst: per product staat wat er ongeveer in het schap hoort te staan, en op het controlescherm krijgt een telling die daar ver naast zit een waarschuwing",
            "Wie alleen keuken of kassa mag, ziet in de handterminal geen productzoeker en geen voorraadcijfers",
        ],
    },
    {
        "versie": "1.24.0",
        "datum": "5 oktober 2026",
        "punten": [
            "Prijzenscherm: één algemene prijslijst voor elke dag. De aparte trainingsavond-selectie en de knop om tussen selecties te wisselen zijn weggehaald; wat je bij Producten aanvinkt, staat altijd op het scherm",
        ],
    },
    {
        "versie": "1.23.0",
        "datum": "4 oktober 2026",
        "punten": [
            "Club van 20: tijdelijke herinnering. Bij Scherm & werving kies je een einddatum; tot en met die dag staan ook leden die dit seizoen nog niet betaald hebben lichtrood op het kantine scherm (de laatste 2, 3 of 4 seizoenen, of alle actieve leden). Daarna is het scherm vanzelf weer normaal",
            "Club van 20: de publieke pagina en de tellers (aantal leden, teamstrijd) tellen alleen wie dit seizoen betaald heeft, ook als er onbetaalde bordjes op het scherm staan",
        ],
    },
    {
        "versie": "1.22.1",
        "datum": "4 oktober 2026",
        "punten": [
            "Club van 20: bij verlengen staan nu alle bordjes die in de laatste 3 seizoenen betaald zijn in de lijst, ook als het scherm alleen laat zien wie dit seizoen betaald heeft. Wie vorig seizoen betaalde kan zo zijn eigen bordje kiezen",
        ],
    },
    {
        "versie": "1.22.0",
        "datum": "3 oktober 2026",
        "punten": [
            "Club van 20: verlengen via de QR-code. Op het aanmeldformulier kies je nu \"Een nieuw bordje\" of \"Mijn bordje verlengen\": bij verlengen zoek je je eigen bordje in de lijst, betaal je online of aan de bar, en kun je eventueel de tekst van het bordje aanpassen. Bordjes die dit seizoen al betaald zijn, kun je niet nog eens verlengen",
            "Aanmeldingen: een verlenging staat met het label \"verlenging\" in de concepttabel en bij goedkeuren komt de betaling automatisch bij het gekozen bordje, zonder dubbel lid. De mail bij een nieuwe aanmelding laat ook weten of het een verlenging is",
        ],
    },
    {
        "versie": "1.21.0",
        "datum": "2 oktober 2026",
        "punten": [
            "Tellingen: de omzet per week is nu de omzet van de week zelf. De omzet van elke telling wordt verdeeld over de dagen die erbij horen (drukke dagen zoals een thuiswedstrijd tellen zwaarder), dus het maakt niet meer uit op welke dagen je telt, bijv. woensdag, vrijdag en soms maandag. Het label \"afwijkende periode\" is weg; een week die nog niet helemaal door tellingen gedekt is krijgt een eigen label (\"loopt nog\", \"geteld t/m ...\" of \"begin meting\")",
            "Daardoor werkt de trendkaart op het tellingenoverzicht nu ook voor jullie telritme, en rekent het Weekoverzicht (pagina en maandagmail) met de omzet en de topverkopers van de week zelf in plaats van met de tellingen die in die week gedaan zijn. De waarschuwing staat er alleen nog als er niet t/m zondag geteld is",
        ],
    },
    {
        "versie": "1.20.1",
        "datum": "2 oktober 2026",
        "punten": [
            "Prognose: gecontroleerd op de echte tellingen en bijgesteld. De bandbreedtes zijn nu eerlijk ruim, omdat de verkoop van week tot week flink schommelt (nu: ongeveer een factor 2 omhoog of omlaag); de kans op een tekort rekent mee met wat al besteld is; en er staat alleen een bestel-advies bij producten met een echt risico",
            "Prognose: een product dat nu op is krijgt een rood label \"nu op\", en in plaats van een foutpercentage staat er een betrouwbaarheid (nog grof / redelijk / goed) met een waarschuwing zolang er minder dan 15 tellingen zijn",
        ],
    },
    {
        "versie": "1.20.0",
        "datum": "2 oktober 2026",
        "punten": [
            "Nieuw: Bestellen → Prognose. Wat er de komende 3, 7 of 14 dagen waarschijnlijk verkocht wordt: verwachte omzet met bandbreedte, dag voor dag (met thuiswedstrijden, training en weer), en per product de kans op een tekort, hoe lang de voorraad reikt en een bestel-advies in hele kratten",
            "Het voorspelmodel is vervangen: het rekent per dag in plaats van per week (dus ook met tellingen op wisselende dagen), houdt rekening met uitverkochte producten en met wat al onderweg is, en leert uit de eigen tellingen hoeveel een thuiswedstrijd, de trainingsavond en het weer uitmaken. Onderaan de pagina staat wat het geleerd heeft en hoe nauwkeurig het de laatste tellingen voorspelde",
            "De voorspelde tekorten op de bestellijst tonen nu de kans op een tekort en een bestel-advies; het tellingenoverzicht toont de verwachte omzet voor de komende 7 dagen. Het weer wordt voortaan ook bewaard, zodat het model het weereffect kan leren",
        ],
    },
    {
        "versie": "1.19.5",
        "datum": "1 oktober 2026",
        "punten": [
            "Club van 20: een extra groot bordje telt nu voor twee vakjes mee bij het verdelen van de namen over de dia's, en er blijven geen gaten meer naast een breed bordje (de volgende namen vullen ze op). Het aantal rijen per dia klopt nu ook bij 3 of 5 kolommen",
        ],
    },
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
