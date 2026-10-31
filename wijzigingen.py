"""Het handmatig bijgehouden versie-logje voor de Help-pagina (/help).

Bij elke gebruikersgerichte wijziging: HUIDIGE_VERSIE ophogen en bovenaan
WIJZIGINGEN een item toevoegen (zie CLAUDE.md)."""

# Handmatig bijgehouden versie-overzicht voor de Help-pagina. Geen
# geautomatiseerd systeem (geen releases/tags) -- gewoon een leesbaar logje
# van wat er is toegevoegd, bijgewerkt bij noemenswaardige wijzigingen.
HUIDIGE_VERSIE = "1.80.0"
WIJZIGINGEN = [
    {
        "versie": "1.80.0",
        "datum": "31 oktober 2026",
        "punten": [
            "Kantine-tv, Diashow: bij 's Avonds kies je vanaf hoe laat alleen nog de dia's draaien, plus de onderdelen die je aanzet (bijvoorbeeld vanaf 16:00 alleen nog de Club van 20, geen standen, wedstrijden of sponsorlogo's). Dat duurt tot de volgende ochtend; overdag draait alles weer mee.",
            "Het programma van een feest (een dia met het effect Programma) staat al de hele dag op de tv, ook als de map pas 's middags begint, zodat iedereen weet wat er komt.",
        ],
    },
    {
        "versie": "1.79.0",
        "datum": "31 oktober 2026",
        "punten": [
            "De kantine-tv heeft een nieuwe, rustigere indeling met tabbladen: Nu (de tv's met een live beeld, de momenten van vanavond en snelknoppen), Dia's (mappen, en elke dia als tegel met een klein plaatje van hoe hij op de tv staat, een schakelaar, Nu groot, Voorbeeld en Bewerken; filteren en zoeken), Diashow (de onderdelen op volgorde slepen, de standen, Man of the Match en de eigen sjablonen), Prijzenscherm, Sponsoren en Tv's (koppelen en instellen). Bovenaan elke pagina zie je hoeveel tv's aan staan en wat er nu groot op de tv staat, met Stop.",
            "Een staande foto op een dia krijgt nu zwarte balken ernaast in plaats van witte.",
            "Eigen sjablonen: teksten slepen en groter maken werkt weer.",
            "Handterminal-app 2.21.0: Kantine-tv met snelknoppen bovenaan (dia groot tonen, timer, uitverkocht, tv koppelen), een gele balk met Stop zolang er iets groot op de tv staat, labels voor wat aan of uit staat, en de dia's bij Diashow als tegels in de kleur van hun effect.",
        ],
    },
    {
        "versie": "1.78.0",
        "datum": "30 oktober 2026",
        "punten": [
            "Handterminal-app 2.20.0: onder Kantine-tv > Diashow tik je op een dia om hem meteen groot op alle tv's te zetten, ook een dia zonder moment zoals het programma. De dia's staan per map, de map van het feest bovenaan, en zolang er iets groot staat, staat Stop de schijnwerper erboven. Bij Momenten brengt 'Een andere dia groot tonen' je daar meteen naartoe.",
            "Het programma op de Kiosk-hub en in de app laat geen momenten meer zien uit een map die uit staat (zoals een archief met een oude versie van het feest), zodat elk moment er één keer staat.",
        ],
    },
    {
        "versie": "1.77.0",
        "datum": "30 oktober 2026",
        "punten": [
            "Een griezeldia als poster: kies een tekening (heksenketel, schaal met een verrassing, toverstaf, duivelsdrietand, zombiehand, rij shotjes of pompoen) en de dia wordt een poster met de titel groot bovenaan, de bewegende tekening linksonder en de prijs op een houten bord. Alles knalt in beeld als de dia aan de beurt is (in de schijnwerper na de intro): de titel slaat in, het bord valt naar beneden en de prijs wordt erop gestempeld.",
            "Het programma als griezeldia: met het effect Programma worden regels als '16:00 Feest start!' een programma in de kleuren van de momenten. Het tijdslot van nu licht op met NU en wat al geweest is, wordt zachter; de andere regels (zoals 'De hele avond: Griezelshot') komen op het bord.",
            "Het live voorbeeld bij een griezeldia laat de dia nu precies zien zoals op de tv.",
        ],
    },
    {
        "versie": "1.76.0",
        "datum": "29 oktober 2026",
        "punten": [
            "Mappen voor de dia's: zet dia's bij elkaar in een map, zoals 'Halloween feest'. Een hele map zet je met één klik aan of uit (bij Kantine-tv > Dia's of in de handterminal-app), en met een begin en einde gaat hij vanzelf aan en uit.",
            "Momenten: een dia kan een tijdslot krijgen, zoals 17:00 Heksenbrouwsel. Hij staat dan alleen in de diashow van zijn moment tot het volgende moment in dezelfde map.",
            "De schijnwerper: de eerste minuten van een moment (standaard 5) neemt de dia alle tv's over, ook het prijzenscherm. Eerst bliksem en een groot NU!, dan knalt de dia in beeld met een kloppende rand, en elke halve minuut volgt een flits. Daarna staat er bovenaan de prijzen een balk 'Nu aan de bar' tot het volgende moment. De tv's rekenen met de klok van de server, dus het begint op de minuut.",
            "Effecten over een dia: groene bubbels uit de heksenketel, vonken en vlammen, paarse glitters met een heks op een bezem, rode bliksem met bloed, groen slijm met confetti, en bij het programma licht het tijdslot van nu op met NU. Tik in het voorbeeld aan waar de prijs staat; daar klopt een gloed. Nieuw is ook de griezeldia: griezelletters in de kleur van het effect, met maan, spinnenwebben, pompoenen en kaarsen.",
            "Bijsturen op de avond: op de Kiosk-hub staat het programma met Nu tonen, +15 min en Voorbeeld (de schijnwerper in je browser, zonder dat de tv's iets merken), en Stop de schijnwerper.",
            "Handterminal-app 2.19.0: bij Kantine-tv de momenten (nu tonen, een kwartier later of eerder, stoppen) en bij Diashow de mappen aan of uit.",
        ],
    },
    {
        "versie": "1.75.0",
        "datum": "27 oktober 2026",
        "punten": [
            "De keuken boekt per verpakking in, nooit meer per stuk. Elke scan is een zak of doos, met wat er bij dat merk in zit (de zak van 20 van AH, die van 15 van Plus). Zonder barcode kies je de verpakking van het merk dat binnenkwam; een product zonder barcode (gehaktballen van de slager) geef je één keer een verpakking. Staat bij een barcode nog niet hoeveel erin zit, dan vraagt de site of de app dat bij de eerste scan.",
            "Koppelen in de keuken laat alleen keukenproducten zien en vraagt één ding: hoeveel zit erin (de naam en de inkoopprijs mogen leeg). Dat kan nu ook wie alleen keukenrechten heeft. De inkoopprijs van een keukenproduct komt van de merken (het gemiddelde per stuk); bij het inboeken pas je hem alleen nog aan bij een product zonder barcode.",
            "Keuken tellen gaat blind: wat de site verwacht, zie je pas op het controlescherm na het tellen, ook bij Keuken > Tellen op de computer. De snelknoppen zijn je echte verpakkingen (+12, +15, +20, +40) in plaats van één vaste doos.",
            "Nieuw: Keuken > Muteren. Wat weggegooid wordt (verbrand, over de datum, gevallen), boek je als derving met een reden; dan telt het bij de volgende telling niet als verkocht en staat het bij Derving. Klopt de voorraad niet, dan zet je hem bij met erbij of eraf. In de app tik je daarvoor op een keukenproduct.",
            "Zakt een keukenproduct onder zijn minimum, dan komt het vanzelf op de boodschappenlijst, en bij het inboeken gaat het er weer af. Keukenspullen staan niet meer op de bestellijst van de kantine en tellen niet meer mee bij 'onder het minimum'.",
            "Handterminal-app 2.18.0: inboeken in de keuken blijft bewaard tot je inboekt, ook als de app uitlogt; weggooien en erbij of eraf bij een keukenproduct; blind tellen met een knop per verpakking.",
        ],
    },
    {
        "versie": "1.74.0",
        "datum": "27 oktober 2026",
        "punten": [
            "Halloween-thema voor de kantine-tv: bovenaan de Kiosk-hub, of in de handterminal-app bij Kantine-tv, zet je met één klik het Halloween-thema aan. Over alle tv's vliegen dan vleermuizen, er zakt een spin aan zijn draad, er zitten spinnenwebben in de hoeken, pompoenen lichten op, er kijkt af en toe een spookje om de hoek en er hangt mist. Op het prijzenscherm worden de achtergrond nachtpaars en de prijzen oranje, met de maan erboven; de prijzen blijven goed leesbaar. Met één klik weer uit; de tv's nemen het binnen 10 seconden over.",
            "Handterminal-app 2.17.0: de knop voor het Halloween-thema bij Kantine-tv.",
        ],
    },
    {
        "versie": "1.73.0",
        "datum": "27 oktober 2026",
        "punten": [
            "De bestelling nalopen op de handterminal: de Bestellijst in de app is nu de plek waar je de bestelling controleert. Tik op een product: er schuift een blad omhoog met het aantal colli, − en +, en Bevestigen; dan krijgt de regel een groen vinkje. Scan een product of zoek het op en het komt onder 'Erbij', met het blad meteen open; nog een keer scannen is één colli meer. Klaarzetten neemt alleen wat gecontroleerd is, een bestelling per leverancier, en zegt het als er nog iets niet gecontroleerd is.",
            "Wat je bevestigt, wordt meteen op de site bewaard: logt de handterminal uit (na 15 minuten niets doen), dan staan je vinkjes er na het inloggen nog. Op de bestellijst op de computer staat bij zo'n product '✓ gecontroleerd'. Na het klaarzetten begint de volgende keer weer met een schone lijst.",
            "Na het klaarzetten laat de app het besteloverzicht zien: per leverancier je klantnummer, tot wanneer je moet bestellen, en per product het artikelnummer en het aantal colli, om het bij de leverancier te bestellen. Met Kopiëren of Delen stuur je de lijst door. Onder Onderweg staan nu de leverancier en het aantal colli; tik erop voor hetzelfde overzicht, met Levering inscannen.",
            "Handterminal-app 2.16.0: het aparte scherm 'Bestelling klaarzetten' is opgegaan in de Bestellijst.",
        ],
    },
    {
        "versie": "1.72.0",
        "datum": "26 oktober 2026",
        "punten": [
            "Schaplabels scannen met de handterminal: scan de QR-code op een schaplabel met de Zebra en je staat meteen bij het product, met 'Bestellen' om het aantal colli te kiezen. Bij een verbruiksvoorwerp (toiletpapier, bakjes) vraagt de app of het op de bestellijst moet, en zegt hij het als het er al staat. Melden voor de bestellijst met een telefooncamera kan niet meer; met een telefoon zie je alleen wat het is.",
            "Uitgebreide schaplabels: naast het minimum (ook in colli, bijvoorbeeld '48 stuks (2 tray)') staat erop hoe je het bestelt ('Bestellen per tray van 24') en bij wie, met het artikelnummer, en onder de QR-code 'Scan met de handterminal'. Bij het printen kies je groot (6 per A4, met logo en foto) of klein (16 per A4, voor een smal schap of de koeling), en of de verkoopprijs erop moet. Een product zonder foto krijgt geen leeg fotovak meer.",
            "Prognose en 'Prognose en verkoop' zijn één menu-item geworden, met twee tabbladen.",
            "De bijstelling van de prognose in stuks (uit 1.68.0) is weg: sinds 1.69.0 kies je het aantal colli. Wat er nog van stond, vervalt; een gekozen aantal blijft staan.",
            "Handterminal-app 2.15.2: scant ook de QR-code van een verbruiksvoorwerp. De lijst onderaan de Bestellijst en bij Bestelling klaarzetten heet nu 'Kan opraken', want daar staat ook wat maar een kleine kans heeft om op te raken. Op de bestellijst op de telefoon staat nu dat je ook met de app een bestelling klaarzet.",
        ],
    },
    {
        "versie": "1.71.0",
        "datum": "26 oktober 2026",
        "punten": [
            "Eén besteladvies: bij het product, op de bestellijst, op de Prognose-pagina, bij de voorspelde tekorten, de thuiswedstrijd op het overzicht, de compacte uitdraai en in de app staat nu overal hetzelfde aantal. Het advies is genoeg tot de levering ná de volgende bestelling (in 9 van de 10 gevallen), minstens het minimum en minstens de vaste bestelhoeveelheid als je die gebruikt, min de voorraad en wat al onderweg is, in hele colli. Eerder rekenden de Prognose-pagina en de voorspelde tekorten elk op hun eigen manier, waardoor je soms verschillende aantallen zag.",
            "Op de bestellijst staat nu alles waarvoor dat advies boven 0 komt. Een product met een kleinere kans op tekort staat er niet aangevinkt bij als 'Kan opraken (…%)'; vanaf 50% heet het 'Raakt waarschijnlijk op' en is het aangevinkt.",
        ],
    },
    {
        "versie": "1.70.1",
        "datum": "26 oktober 2026",
        "punten": [
            "De prognose is nu ook de eerste keer van de dag snel: het rekenmodel blijft bewaard tot er een nieuwe telling bijkomt (niet meer elke dag om 12.00 uur opnieuw), en na een telling rekent het vanzelf op de achtergrond zodra iemand met voorraadrechten een pagina van de site of het startscherm van de handterminal-app opent. Een wedstrijd of het weer van de komende dagen past alleen de verwachting aan, zonder het hele model opnieuw te rekenen.",
            "Handterminal-app 2.15.1: het startscherm laat het rekenmodel op de achtergrond alvast rekenen, zodat ook na een telling op de handterminal de bestellijst en een gescand product meteen openen.",
        ],
    },
    {
        "versie": "1.70.0",
        "datum": "26 oktober 2026",
        "punten": [
            "De prognose is veel sneller: het zware rekenwerk gebeurt nog maar één keer per dag (en opnieuw na een nieuwe telling), voor alle periodes tegelijk. Een product scannen op de handterminal, de bestellijst, de agenda-omzet en de omzettrend op het overzicht wachten daardoor niet meer steeds 10 tot 20 seconden. Alleen de eerste keer van de dag kan nog even duren.",
            "Klaarzetten per leverancier: kies je op de bestellijst (of in de app) producten van Sligro en van de Makro, dan worden het twee bestellingen, een per leverancier. Bij elke openstaande bestelling staan nu 'PDF voor de leverancier' (met je klantnummer en de artikelnummers) en 'Tekst kopiëren', om in een mail of WhatsApp te plakken. Bij het inboeken krijgt de factuur meteen de goede leverancier.",
            "'Op de bestellijst' bij een product zet het nu echt bij 'Voorgesteld om te bestellen', met het advies en minstens 1 colli (op de site en in de app). Bezoekers die met de QR-code op een schaplabel iets melden, staan nog steeds bij 'Gemeld'.",
            "Handterminal-app 2.15.0: een herinnering om te bestellen. Een paar uur voor het uiterste bestelmoment van een leverancier (of de avond ervoor als dat 's ochtends vroeg is) komt er een melding op het toestel, ook als de app dicht is, en staat het bij 'Let op' op het startscherm: 'Vandaag vóór 16:00 bestellen bij Sligro'. Uit te zetten in Instellingen.",
            "Handterminal-app 2.15.0: een telling corrigeren kan nu ook in de app (Tellingen, tik op een product), en beheerders passen de naam en de verkoopprijs van een product aan in hetzelfde venster als het minimum en de besteleenheid.",
            "Verkooprapport: een balk is alleen nog gestippeld (⚠️) als die periode veel korter of langer is dan je gewoonlijk telt. Wie twee keer per week telt, kreeg eerst bij bijna elke balk een waarschuwing. Onder de grafiek staat nu wat het betekent.",
        ],
    },
    {
        "versie": "1.69.0",
        "datum": "26 oktober 2026",
        "punten": [
            "Bestellen in colli: bij een product (gescand op de handterminal of op de site) zie je de prognose en het advies, en kies je met − en + hoeveel kratten, dozen of trays je bestelt. Dat gaat per hele colli, dus niet meer via een prognose in stuks die wordt afgerond. In de app tik je op het getal om het in te vullen; op 0 bestel je het niet, en met 'Terug naar het advies' haal je je keuze weg.",
            "Wat je kiest staat meteen zo bij 'Voorgesteld om te bestellen' op de bestellijst en bij Bestelling klaarzetten in de app, met 'zelf gekozen (naam)' erbij, ook als het product niet onder het minimum zit. Is het besteld, dan vervalt de keuze vanzelf.",
            "Scannen op de bestellijst: op de site staat boven 'Voorgesteld om te bestellen' een scanveld (scan een barcode, ook die van de doos, of typ een naam en druk op Enter). Het product komt erbij en wordt aangevinkt; scan je het nog een keer, dan is het één colli meer. In de app scan je een product op de Bestellijst of bij Bestelling klaarzetten, en dan komt het onder 'Gescand' te staan.",
            "Handterminal-app 2.14.0: onderaan het startscherm staan onder 'Meer' niet langer twaalf knoppen door elkaar, maar vier onderwerpen: Voorraad en bestellen, Kantine en keuken, Geld en Club. Tik op een onderwerp en er schuift een blad omhoog met de onderdelen, elk met een korte uitleg en een teller als er iets is (bijvoorbeeld 2 bestellingen). Op de tegel van het onderwerp staat het totaal, rood als er iets dringends bij zit.",
        ],
    },
    {
        "versie": "1.68.0",
        "datum": "24 oktober 2026",
        "punten": [
            "Prognose bijstellen, zoals op de handterminal van de supermarkt: scan een product (of open het op de site) en je ziet onder 'Bestellen bij ...' tot wanneer je uiterlijk moet bestellen, wanneer het geleverd wordt en hoeveel er verwacht wordt tot de levering daarna. Met − en + stel je die prognose bij (per krat, doos of tray; in de app tik je op het getal voor een eigen aantal). Het advies gaat meteen mee.",
            "Een bijstelling telt mee bij 'Voorgesteld om te bestellen' op de bestellijst en bij Bestelling klaarzetten in de app, met 'bijgesteld +6 (naam)' erbij. Ook een product met een prognose van 0 komt er zo bij te staan, aangevinkt. Is het besteld, dan vervalt de bijstelling vanzelf.",
            "De prognose op de bestellijst rekent nu per leverancier tot de levering ná de bestelling (uit de besteldagen, de besteltijd en de levertijd), in plaats van altijd 7 dagen. Zonder besteldagen blijft het 7 dagen.",
        ],
    },
    {
        "versie": "1.67.1",
        "datum": "23 oktober 2026",
        "punten": [
            "Tablet-app 2.0 'Kantine Beheer' (voorheen Kantine Kiosk): naast de producten, acties, bardienst, het uitgelichte product en de wedstrijddag nu ook de tv's (wat ze tonen, opnieuw laden, de wisselknop), de dia's (onderdelen en losse dia's aan of uit), uitverkocht op het prijzenscherm en de timer op de tv's.",
            "Tablet-app 2.0: bij een foute code staat er hoeveel pogingen je nog hebt (of hoe lang je moet wachten); dat stond er eerder niet. Na 10 minuten niets doen logt hij vanzelf uit, en bij een noodstop gaat hij op slot.",
        ],
    },
    {
        "versie": "1.67.0",
        "datum": "23 oktober 2026",
        "punten": [
            "Factuur inboeken op de site werkt nu net als in de app. Scan je een los flesje terwijl er een krat of doos van bestaat, dan vraagt de site: 'Hele colli inboeken?', en die keuze geldt voor de rest van de factuur. Fusten en producten zonder barcode voeg je toe uit de lijst 'Zonder barcode (PLU)'. De knop heet 'Factuur gecontroleerd' en laat eerst zien wat er van de bestelling nog mist; dat wordt manco.",
            "Niet geleverd blijft niet liggen: wat bij een bestelling niet (of te weinig) binnenkwam, staat bij 'Voorgesteld om te bestellen' op de bestellijst ('niet geleverd bij #12'), met het tekort al ingevuld. Zet je het in een nieuwe bestelling, dan is het opgevolgd; anders tik je op 'Niet meer nodig'.",
            "Nieuwe pagina Bestellen → Bestellingen: alle bestellingen, ook de ontvangen (die blijven bewaard), met per product wat er besteld en binnengekomen is. Bovenaan per leverancier wat er nog niet geleverd is.",
            "Inkoopprijs uit de factuur: bij Factuur inboeken pas je per scan de prijs aan naar wat er op de factuur staat. Bij 'Factuur gecontroleerd' wordt dat de nieuwe inkoopprijs van het artikel en het product, zodat de marge klopt.",
            "Handterminal-app 2.12: een bestelling klaarzetten kan nu ook in de app (Bestellijst → Bestelling klaarzetten). Wat onder het minimum zit staat klaar met het voorgestelde aantal (of meer als de prognose dat zegt), net als wat niet geleverd is; wat waarschijnlijk opraakt staat eronder. Tik om het aantal te veranderen en zet hem klaar: hij staat meteen bij Factuur inboeken.",
            "Handterminal-app 2.12 (beheerders): het minimum en de besteleenheid van een product pas je aan op het productscherm, en de keukenprijzen en hoe vaak het frituurvet vervangen moet onder Keuken.",
            "De keukentelling loopt nu gelijk op de site en in de app: pauzeer je op de handterminal, dan ga je op de site verder (Keuken → Tellen met de looplijst), of andersom. Begint iemand ergens anders opnieuw, dan zie je dat meteen.",
            "Dashboard: bij de omzettrend staat per week ook de keukenomzet (🍳), apart van de kantine-omzet.",
            "Op de telefoon vallen de pagina's van de sponsoren en standen (Kantine-tv) niet meer buiten beeld.",
            "Invoervelden op Bulk bewerken, de bestellijst en de sponsorpagina hebben nu een naam, zodat een schermlezer zegt waar het veld voor is.",
        ],
    },
    {
        "versie": "1.66.0",
        "datum": "23 oktober 2026",
        "punten": [
            "Handterminal-app 2.11, keukentelling als looplijst: product voor product, met foto, voortgang ('Product 3 van 22 · 2 geteld'), de snelknoppen en de rekenmachine, net als Tellen. Losse stuks tik je in; scan je een volle doos of zak, dan telt wat erin zit er meteen bij. Onder de naam staat wat je gescand hebt ('Gescand: +40 · +15'); tik erop om een verkeerde scan weg te halen. Scan je een ander keukenproduct, dan springt de lijst daarheen, en een onbekende barcode koppel je meteen.",
            "Keukentelling in de app: aan het eind een controlescherm met per product wat er was, wat je telde en wat er als verkocht telt, met de omzet. Daar kies je ook of het een begintelling is. De stand blijft op de handterminal bewaard: na Terug, de slaapstand of een herstart ga je verder waar je was.",
            "Keuken inboeken in de app: wat je scant staat bovenaan in een lijst ('Gescand'), elke scan met een kruisje om hem weg te halen.",
            "Keuken in de app: tik op een keukentelling om te zien wat er per product is verkocht (een begintelling staat er als zodanig bij). Bij elk product zie je de gekoppelde dozen en zakken, en je zet het met één tik op de boodschappenlijst, ook met alleen keukenrechten.",
        ],
    },
    {
        "versie": "1.65.1",
        "datum": "23 oktober 2026",
        "punten": [
            "Inloggen met je code (handterminal en tablet) gaat pas na 10 foute codes op slot, en dan 10 minuten (was 5 keer en een half uur). Na die 10 minuten heb je weer 10 pogingen. Wie op slot zat, kan meteen weer inloggen.",
        ],
    },
    {
        "versie": "1.65.0",
        "datum": "23 oktober 2026",
        "punten": [
            "Handterminal-app 2.10, Factuur inboeken: wat geen barcode heeft (fusten, en producten op 'Heeft geen barcode') kies je uit de lijst 'Zonder barcode (PLU)'. Tik het product aan en vul in hoeveel fusten of kratten er binnen zijn. Wat besteld is, staat bovenaan, met hoeveel er al binnen is.",
            "Factuur inboeken: de knop heet nu 'Factuur gecontroleerd'. Bij een klaargezette bestelling zie je eerst wat er nog niet (helemaal) binnen is. Daarna boek je in, en wat mist komt op manco, zoals altijd.",
            "Scan je een los flesje of blikje terwijl er een krat of tray van bestaat (ook als die krat zelf geen barcode heeft), dan vraagt de app: 'Los gescand: 1 fles los van Hertog Jan. Hele colli inboeken?'",
        ],
    },
    {
        "versie": "1.64.0",
        "datum": "23 oktober 2026",
        "punten": [
            "Keuken tellen met de looplijst (Keuken → Tellen → Tellen met de looplijst): product voor product, net als de gewone looplijst, met de rekenmachine. Losse stuks tel je met de hand; een volle doos of zak scan je en wat erin zit telt er meteen bij. Een AH-doos en een Plus-doos tellen elk hun eigen aantal. Een onbekende barcode koppel je ter plekke, met hoeveel erin zit. Aan het eind controleer je alles op één scherm en sla je het op. Valt het bereik weg, dan ben je niets kwijt: de stand blijft op je telefoon bewaard.",
            "Begintelling voor de keuken: zet alleen de voorraad goed, zonder dat het verschil als verkocht telt. Bij de allereerste keukentelling staat hij al aan. Ook in de handterminal-app: bij het opslaan kies je een gewone telling of een begintelling.",
            "Keuken inboeken door te scannen: scan wat er binnenkomt en de site weet per barcode hoeveel erin zit, ook als dat per supermarkt verschilt. Zonder barcode vul je nog steeds het aantal verpakkingen in.",
            "Handterminal-app 2.9: bij de keukentelling en Keuken inboeken telt een gescande doos of zak meteen mee (je hoeft niets meer in te tikken). Bij een onbekende barcode opent het koppelen.",
            "De pagina Tellingen laadt sneller: de producten van een telling worden pas opgehaald als je op Bekijken tikt.",
            "Op de telefoon vallen formulieren niet meer rechts buiten beeld, onder meer bij Boeken, een nieuwe bestelling, Levering inboeken en Tellen.",
        ],
    },
    {
        "versie": "1.63.0",
        "datum": "20 oktober 2026",
        "punten": [
            "Tv koppelen met de handterminal: naast de koppelcode staat op een nieuwe tv nu ook een QR-code. Scan die met de handterminal-app (2.8), geef de tv een naam, kies wat hij toont en hij is gekoppeld. Code intikken kan ook, via Kantine-tv → Tv koppelen in de app. Met een telefoon gescand opent Kantine-tv op de site met de code al ingevuld.",
            "Tv-app 1.2: alleen nog een gekoppeld scherm, zonder menu. De app start meteen op het eigen scherm van de tv (of de koppelcode), ook als je hem met de hand opent. Met de afstandsbediening wissel je: knop omlaag de prijzenlijst, knop omhoog de dia's. Dat blijft zo (ook na een herstart) en je ziet het op de site en de handterminal. De OK-knop opent de instellingen: hoe groot de prijzenlijst en de dia's op die tv staan, elk apart (of 'Zoals op de site'). Een zoom die al op de tv was ingesteld, blijft bewaard.",
            "Handterminal-app 2.8: een telling starten gaat meteen. De app wachtte eerst tot de site het voorspelmodel had doorgerekend (voor 'ongeveer verwacht'); nu staat het eerste product er direct en verschijnt de verwachting een paar seconden later. Tijdens het laden staat erbij wat hij doet, en daarna zet hij alle foto's van de looplijst op het toestel, met de voortgang in de kopbalk ('Foto's klaarzetten 23/40').",
            "Een nieuwe tv toont standaard de dia's (op de site en in de handterminal-app staat 'Dia's' voorgekozen bij het koppelen).",
        ],
    },
    {
        "versie": "1.62.1",
        "datum": "20 oktober 2026",
        "punten": [
            "Handterminal-app 2.7.1: een product opent overal als informatiepagina, met in- of uitboeken onderaan: via de zoekbalk, Voorraad, Barcodes, de bestellijst en een scan. Alleen via Boeken (en na het koppelen van een onbekende barcode) staat boeken bovenaan, met het gescande aantal al ingevuld. Eerder gold dat alleen voor een scan op het startscherm.",
        ],
    },
    {
        "versie": "1.62.0",
        "datum": "20 oktober 2026",
        "punten": [
            "Handterminal-app 2.7: barcodes aanpassen. Tik op het productscherm op een artikel om de barcode (of die van de doos), de naam, het aantal, de inkoopprijs of de leverancier aan te passen, of om het te verwijderen. Een scan vult de barcode in.",
            "Koppelronde in de handterminal-app (Meer → Barcodes → Koppelronde): alle producten die nog geen barcode van een losse verpakking hebben, één voor één. Scan één los exemplaar en het volgende product staat klaar, met een voortgangsbalk. Overslaan kan, wat geen barcode heeft (tapbier, een portie uit de keuken) zet je op 'heeft geen barcode', en de laatste koppeling maak je met één tik ongedaan. Een barcode van 14 cijfers (meestal een doos) vraagt eerst of het echt een losse verpakking is: dozen en kratten koppel je bij het inboeken van facturen.",
        ],
    },
    {
        "versie": "1.61.0",
        "datum": "20 oktober 2026",
        "punten": [
            "Handterminal-app 2.6: de kantine-tv vanaf de bar (Meer → Kantine-tv, met de rechten voor de kantine-tv). Je ziet per tv of hij aan staat en wat hij toont, kiest wat hij toont (prijzenlijst, dia's of wisselscherm), laadt hem opnieuw en zet het wisselscherm om. Verder het uitgelichte product (kies een ander product, pas de titel aan of zet het uit), de prijs-acties aan of uit, de bardienst van vandaag en morgen (een wissel ter plekke aanpassen, toevoegen of verwijderen) en de diashow: hele onderdelen zoals de standen, of losse dia's aan of uit. Uitverkocht en de timer staan er ook. Dia's maken en bewerken, de indeling en een nieuwe tv koppelen doe je op de site.",
        ],
    },
    {
        "versie": "1.60.0",
        "datum": "20 oktober 2026",
        "punten": [
            "Handterminal-app 2.5: scan je een barcode op het startscherm, dan zie je alleen de informatie van het product. In- of uitboeken staat dan onderaan de pagina, onder 'Erin of eruit', en er staat niets meer klaar. Vanuit Boeken en de andere schermen werkt het zoals altijd.",
        ],
    },
    {
        "versie": "1.59.0",
        "datum": "20 oktober 2026",
        "punten": [
            "Tv's koppelen: open op een tv /kiosk/koppelen (in de tv-app: 'Gekoppeld scherm'), vul op Kantine-tv bij 'Tv koppelen' de code in die op de tv staat en geef hem een naam. Daarna kies je per tv wat hij toont (de prijzenlijst, de dia's of het wisselscherm) en hoe groot, laad je hem op afstand opnieuw en zie je of hij aan staat, wat hij toont en hoe groot zijn beeld is. Staat een tv uit terwijl er bardienst is, dan staat dat bij 'Wat moet er nu?'. De oude vaste adressen blijven gewoon werken.",
            "De tv-schermen herstellen zichzelf: ze herladen pas als de site de nieuwe pagina ook echt geeft, dus bij een haperende wifi blijft het oude beeld staan in plaats van een foutpagina. De diashow herlaadt pas als de dia in beeld klaar is en gaat daarna verder waar hij was, en 's nachts herladen de schermen zich één keer. De tv-app (versie 1.1) probeert het na een storing elke 15 seconden vanzelf opnieuw, en meteen als het netwerk terug is; eerder bleef hij op de foutmelding staan tot iemand op 'Opnieuw proberen' drukte.",
            "Timer op de tv, bijvoorbeeld voor de gehaktballen: linksonder op alle tv's telt hij af (op het prijzenscherm schuift de prijslijst er netjes voor op), daarna staat er 'Klaar!' tot je hem weghaalt, of tot een kwartier later. Starten, er 5 minuten bij doen en weghalen via Start → Timer op de tv (ook in de tablet-app) of op de handterminal. De knoppen onthouden de tijd van de vorige keer.",
            "Handterminal-app 2.4: producten op het prijzenscherm op uitverkocht zetten (Meer → Op de tv, of op het productscherm), met de vraag of het weer te koop moet als je er iets van inboekt. En de timer op de tv, ook bij 'Let op' op het startscherm.",
        ],
    },
    {
        "versie": "1.58.1",
        "datum": "19 oktober 2026",
        "punten": [
            "Tijden kloppen: de server draait in Engelse tijd (UTC), waardoor alles wat de site zelf vastlegde (het logboek, boekingen, tellingen, de kassa, het prikbord) 1 uur in de winter en 2 uur in de zomer te vroeg stond. Vanaf nu in Nederlandse tijd, met zomer- en wintertijd.",
        ],
    },
    {
        "versie": "1.58.0",
        "datum": "19 oktober 2026",
        "punten": [
            "Noodstop: iedereen wordt uitgelogd, ook de beheerders en de eigenaar zelf. Daarna kan alleen een beheerder inloggen, met het wachtwoord én de noodcode; weer openen kan alleen de eigenaar. Zonder noodcode kan de noodstop niet aan.",
            "Tellen: de looplijst op de site en in de handterminal-app is één telling. Afbreken (of opslaan) geldt nu overal: hij komt niet meer terug doordat een ander toestel of de app hem bij de volgende stap opnieuw bewaarde. Op Voorraad tellen staat een knop Afbreken, en de vraag 'Afbreken?' heeft nu de knoppen 'Ja, afbreken' en 'Nee, verder tellen'.",
            "Tellen in de app: 'Stoppen zonder opslaan' werkt nu echt; de telling bleef eerder bewaard.",
            "Handterminal-app: een artikel toevoegen op het productscherm (naam, merk, inhoud, inkoopprijs, leverancier en de barcodes van de verpakking en de doos, door te scannen).",
            "Rechten: haalt een beheerder bij iemand een sectie weg (of maakt hij een beheerder vrijwilliger), dan geldt dat meteen, ook als die al is ingelogd. Een prikbordbericht verwijderen kan alleen wie het schreef, of een beheerder.",
        ],
    },
    {
        "versie": "1.57.0",
        "datum": "19 oktober 2026",
        "punten": [
            "Bestellijst: de prognose zit nu in 'Voorgesteld om te bestellen'. Per product staat wat er de komende 7 dagen verwacht wordt; vraagt de komende week meer dan het minimum, dan staat het aantal al hoger. Producten die nog boven het minimum zitten maar waarschijnlijk opraken, komen er onderaan bij.",
            "Een klaargezette bestelling is het concept van de factuur: hij staat meteen bij Factuur inboeken (op de site en op de handterminal). Bij het inscannen zie je per product wat er besteld is en wat er al binnen is, met 'zoals besteld' voor wat zonder barcode komt. Wat extra meekomt, komt er bij het afronden bij. 'Inboeken' op de bestellijst opent dit ook; het oude afvinkformulier is er alleen nog om een ontvangen bestelling te corrigeren.",
            "Handterminal-app 2.3: klaargezette bestellingen inboeken met besteld naast gescand, de prognose bij de bestellijst, en een nieuw product aanmaken als een gescande barcode bij nog geen product hoort.",
            "Noodstop: ook een pagina die al openstond gaat binnen een halve minuut dicht, en de handterminal-app gaat binnen 15 seconden op slot met een vergrendel-scherm, ook als hij net geen verbinding had. Is alles weer open, dan gaat de app vanzelf naar het inlogscherm. De welkomstmeldingen op de tv komen na een noodstop niet nog eens.",
            "De pagina 'Geen verbinding' probeert het nu zelf opnieuw, handig voor een scherm aan de muur.",
        ],
    },
    {
        "versie": "1.56.0",
        "datum": "19 oktober 2026",
        "punten": [
            "Handterminal-app 2.2: alles in de app, zonder de website. Nieuwe schermen voor Kassa (tellen per munt en briefje met de contante omzet en kaartbetalingen, en goedkeuren), Kluis (beheerders), Keuken (frituurvet, keukentelling en inboeken), Boodschappen, Club van 20-aanmeldingen (goedkeuren na het controleren van de betaling, of afwijzen), Agenda, Prognose en Barcodes.",
            "Handterminal-app: het productscherm is net zo uitgebreid als de productpagina op de site: kerncijfers (prijs, marge voor beheerders, laatst geteld, voorraadwaarde), de verkoop per week met grafiek, de verwachting met besteladvies, prijzen en geplande prijswijzigingen, inkoop en bestellen met 'Op de bestellijst', de artikelen met barcodes en inkoopprijs, en de laatste tellingen.",
            "Handterminal-app: taken die een beheerder voor je klaarzet, open je in de app: stappen afvinken, afronden en met één tik naar het juiste scherm. Na kassa tellen, kluis tellen, een telling of frituurvet vervangen vraagt de app, net als de site, of de taak daarmee klaar is.",
            "Handterminal-app: wat alleen op de computer kan (de kantine-tv, een telling corrigeren of heropenen, een bestelling klaarzetten, een product bewerken, de keukenprijzen) meldt 'Niet mogelijk in de app' in plaats van de website te openen.",
        ],
    },
    {
        "versie": "1.55.0",
        "datum": "19 oktober 2026",
        "punten": [
            "Handterminal-app 2.1: een zelfstandige app, zonder websitepagina's. Het prikbord (lezen, plaatsen, reageren en afhandelen), de bestellijst, de tellingen en de geschiedenis hebben nu eigen schermen. Kassa, kluis, de kantine-tv en de Club van 20 doe je op de computer.",
            "Handterminal-app: het telscherm is nu net als de looplijst op de site, met de productfoto, de geregistreerde voorraad, de verwachting en de knoppen 0, −1, +1, +2 en +1 krat. Productfoto's staan ook in de lijsten en op het productscherm.",
            "Rekenmachine bij het tellen, op de looplijst van de site en in de app: bijvoorbeeld 3×24+7, en de uitkomst met één tik invullen.",
            "Handterminal-app: scan je een los artikel (één zakje chips) terwijl er een doos of krat van bestaat, dan vraagt de app 'Let op! Artikel gescand, volledige besteleenheid inboeken?', bij boeken en bij Factuur inboeken.",
            "Handterminal-app: een barcode van spullen uit de keuken koppel je als 'verpakking met meer stuks', met de naam, hoeveel erin zit en de inkoopprijs (AH frikandellen 20 stuks naast Plus frikandellen 15 stuks bij 'Frikandel').",
        ],
    },
    {
        "versie": "1.54.0",
        "datum": "19 oktober 2026",
        "punten": [
            "Handterminal-app 2.0: het dagelijkse werk heeft nu eigen schermen in plaats van de website, en is daardoor veel sneller. Startscherm, zoeken en voorraad (de productlijst staat op de handterminal zelf), een product met boeken, tellen met de looplijst, factuur inboeken en barcodes koppelen. Andere pagina's (prikbord, kassa, bestellijst en meer) openen als website in de app, onder 'Meer'.",
            "Handterminal-app: tellen gaat zonder wachten. Het volgende product staat er meteen, met een groot cijferpad. Scan een product om ernaartoe te springen, en pauzeer wanneer je wilt: je gaat later verder waar je was, ook op de site.",
            "Handterminal-app: een product scannen opent het met het aantal al ingevuld (een krat: 24, en Erin staat aan); nog een keer scannen telt erbij op. Een onbekende barcode koppel je in twee tikken: het product, en 'één fles' of 'een krat van 24'.",
            "Barcode opzoeken op de site: een onbekende barcode koppelen vraagt nu alleen het product en of het een losse verpakking of een doos is. Het uitgebreide formulier (merk, leverancier, inkoopprijs) blijft beschikbaar.",
            "Valt de verbinding weg net nadat de handterminal iets heeft opgeslagen (boeken, een telling, een scan bij Factuur inboeken), dan stuurt de app het opnieuw zonder dat het dubbel wordt geboekt.",
        ],
    },
    {
        "versie": "1.53.0",
        "datum": "18 oktober 2026",
        "punten": [
            "Nieuw: de app Kantine Handterminal voor de Zebra-handterminal (TC51). Je logt in met je eigen 6-cijferige code, en na 15 minuten niets doen logt de app vanzelf uit. Daarna zie je de handterminal-weergave van de site.",
            "Handterminal-app: de scanknoppen werken altijd. Staat er een scanveld open, dan komt de barcode daarin; anders spring je meteen naar het product of naar het toevoegen van een onbekende barcode. Een QR-code van de site opent die pagina.",
            "Handterminal-app: bovenin een balk met wie er is ingelogd en hoe de verbinding is. Valt de wifi of de site weg, dan verschijnt een duidelijk scherm dat vanzelf verdergaat zodra alles terug is. Viel de verbinding weg tijdens het opslaan, dan verstuurt de app niets opnieuw, maar vraagt hij eerst te kijken of het al is opgeslagen.",
            "Handterminal-app: werkt ook op Android 6, met een veilige verbinding met de site. Is de webweergave van het toestel te oud, dan zegt de app dat, met een knop om hem bij te werken.",
            "Inloggen met je code: na een foute code meldt de app hoeveel pogingen er nog zijn voordat inloggen vanaf dat netwerk een half uur op slot gaat.",
        ],
    },
    {
        "versie": "1.52.2",
        "datum": "17 oktober 2026",
        "punten": [
            "Komende thuiswedstrijden (de kaart op het overzicht, de Wedstrijden-pagina en de schermen) rekenden met de klok van de server; tussen middernacht en 2 uur 's nachts schoof de lijst daardoor een dag op. Nu altijd met de Nederlandse tijd.",
        ],
    },
    {
        "versie": "1.52.1",
        "datum": "17 oktober 2026",
        "punten": [
            "Noodstop: de tv-schermen gaan nu altijd op slot, ook als ze draaien via een browser of de tablet-app waar iemand (zelfs de eigenaar) is ingelogd.",
            "Noodstop: alleen het venster waarin de eigenaar de noodstop indrukte blijft werken; een oudere sessie van de eigenaar op een ander toestel is ook uitgelogd.",
        ],
    },
    {
        "versie": "1.52.0",
        "datum": "16 oktober 2026",
        "punten": [
            "Nieuw: Beheer → Noodstop, alleen voor de eigenaar van de site. Met één knop (en je wachtwoord) sluit je bij een vermoeden van een hack alles af: iedereen wordt overal uitgelogd, alleen de eigenaar kan nog inloggen, en de publieke pagina's, de apps en 'wachtwoord vergeten' gaan dicht.",
            "De tv-schermen tonen tijdens een noodstop een vergrendel-scherm ('Systeem vergrendeld', met de klok, dat de gegevens veilig zijn en dat de bar gewoon open blijft) en springen vanzelf terug zodra alles weer open is.",
            "Weer openen vraagt het wachtwoord én een aparte noodcode, met een korte wachttijd na te veel foute pogingen. Afsluiten en openen staan in het logboek. Vanaf de server kan het altijd: python3 noodstop.py open.",
        ],
    },
    {
        "versie": "1.51.0",
        "datum": "16 oktober 2026",
        "punten": [
            "Handterminal: nieuw startscherm met vier grote knoppen voor het dagelijkse werk (Factuur inboeken, Tellen, Boeken, Voorraad), daaronder wat aandacht nodig heeft en alles per onderwerp (Voorraad, Bestellen, Kantine, Beheer). Nieuw erbij: Barcodes, Facturen en de Agenda.",
            "Handterminal: een tabbalk onderin op elke pagina (Start, Zoeken, Tellen, Factuur, Boeken) en een knop Terug bovenin. Het zoekveld zegt nu 'Scan of zoek'; uitloggen staat onderaan het startscherm.",
            "Handterminal: in de voorraadlijst kies je met de knoppen bovenaan één categorie. De barcodepagina's en de foutpagina openen nu ook in de handterminal-weergave.",
            "Prognose → Verkoopdagen: een uitzondering kan nu voor een hele periode gelden (vul 'tot en met' in), zoals de winterstop. In de lijst staat zo'n periode als één regel, die je ook in één keer verwijdert.",
        ],
    },
    {
        "versie": "1.50.0",
        "datum": "16 oktober 2026",
        "punten": [
            "Nieuw: Bestellen → Factuur inboeken. Scan de dozen, kratten en verpakkingen van een levering; de site telt per product op hoeveel erbij komt en wat het kost, legt het naast het bedrag op de factuur, en boekt bij het afronden alles in één keer in. Een gekoppelde bestelling staat daarna op ontvangen (wat niet gescand is, is manco). Een onbekende barcode koppel je ter plekke aan een product. Werkt ook in de browser van de handterminal.",
            "Voorbereiding op de app voor de handterminal: die logt in met de 6-cijferige code van een account en kan facturen inboeken via dezelfde stappen (beginnen, scannen, onbekende barcode koppelen, aantal aanpassen, afronden).",
            "Productenlijst: kerncijfers bovenaan (actieve producten, voorraadwaarde, onder het minimum, zonder prijs, zonder barcode), snelfilters, sorteren (naam, voorraad, tekort, waarde, marge, prijs), de marge per product voor beheerders, merk en leverancier onder de naam, en de naam is een link naar alles over dat product. Op de telefoon alleen de belangrijkste kolommen.",
            "Prognose: het model leert per team hoeveel drukker (of rustiger) een thuiswedstrijd van dat team is dan een gemiddelde thuiswedstrijd, zodat het eerste elftal na een tijdje zwaarder telt dan een jeugdteam.",
            "Een voorraad die je via Bewerken aanpast, komt voortaan als boeking in de geschiedenis.",
            "Handterminal: een barcode scannen in het zoekveld bovenin brengt je meteen naar het product (of naar het toevoegen van een onbekende barcode).",
            "Bij het live zetten worden nu ook de pagina's van losse producten, tellingen, bestellingen, kassa- en kluistellingen met de echte gegevens getest.",
        ],
    },
    {
        "versie": "1.49.2",
        "datum": "16 oktober 2026",
        "punten": [
            "'Koud zetten' is weg van het overzicht en het startscherm van de handterminal.",
        ],
    },
    {
        "versie": "1.49.1",
        "datum": "16 oktober 2026",
        "punten": [
            "Een telling achteraf corrigeren past nu ook de huidige voorraad aan, als het de laatste telling van dat product is (vinkje 'Ook de huidige voorraad aanpassen', standaard aan). Tot nu toe veranderde alleen de verkoop en de omzet van de telling, niet de voorraad.",
            "Klopt de voorraad na een correctie niet met de telling en wat er daarna is geboekt (bijvoorbeeld bij een correctie van vóór deze versie), dan staat dat bij die regel van de telling, met een knop om de voorraad op het juiste aantal te zetten. Heb je de voorraad al zelf goed gezet, dan verschijnt er niets.",
            "Bij producten met een lege opmerking stond soms 'None' als opmerking (een foutje in het bewerkformulier). Dat is opgelost en weggehaald.",
        ],
    },
    {
        "versie": "1.49.0",
        "datum": "16 oktober 2026",
        "punten": [
            "De productpagina (wat je ziet als je een product zoekt of aanklikt) is flink uitgebreid: kerncijfers bovenaan (voorraad, ook in kratten; verkoopprijs; marge voor beheerders; wanneer het laatst geteld is), de verkoop per week met een grafiekje van de laatste 12 weken, de verwachting voor de komende 7 dagen en hoe lang je met de voorraad doet, met een besteladvies als het krap wordt.",
            "Ook op de productpagina: prijzen en geplande prijswijzigingen, de laatste prijswijzigingen, inkoop en voorraadwaarde, de leverancier met besteldagen, wat er al besteld is (met een knop om het in te boeken), wanneer het laatst binnenkwam, de barcodes, de laatste tellingen en de derving van de afgelopen 3 maanden. Wordt iets al weken niet verkocht, dan staat dat erbij.",
            "Nieuwe knop 'Op de bestellijst' op de productpagina, net als de QR-code op het schaplabel.",
            "Op een breed scherm staat de informatie links en het boeken rechts; op de handterminal staat het boeken bovenaan.",
        ],
    },
    {
        "versie": "1.48.0",
        "datum": "15 oktober 2026",
        "punten": [
            "Nieuw: Producten → Barcodes. Leg per product vast welke artikelen je inkoopt, met de barcode (EAN) van de verpakking en van de doos, hoeveel erin zit en de inkoopprijs. Meerdere artikelen kunnen bij één product horen (AH en Plus frikandellen bij 'Frikandel', vier witte wijnen bij 'Witte wijn'); op de overzichten blijft het één product.",
            "Barcode opzoeken: scan of typ een barcode en je ziet wat het is, met het aantal en de inkoopprijs (van de zak of van de hele doos). Een onbekende barcode voeg je meteen toe, of je koppelt hem als doos aan een bekend artikel. De site controleert het laatste cijfer van de barcode, zodat een tikfout meteen opvalt.",
            "Bij elk product staan de artikelen onder 'Artikelen en barcodes', en de zoekbalk vindt een artikel ook op zijn barcode.",
            "Hebben de artikelen van een product een inkoopprijs, dan is de inkoopprijs van het product voortaan het gemiddelde daarvan per stuk (AH € 1,00 en Plus € 1,20 per frikandel wordt € 1,10). Zo klopt de marge ook als je bij verschillende winkels inkoopt; elke wijziging staat in de prijsgeschiedenis.",
            "Voorbereiding op de app voor de handterminal: die kan een barcode opvragen bij de site en krijgt terug wat het is, hoeveel en tegen welke prijs.",
        ],
    },
    {
        "versie": "1.47.2",
        "datum": "14 oktober 2026",
        "punten": [
            "Omzet per week (overzicht en Tellingen): een week telt als volledig zodra alle verkoopdagen ervan geteld zijn. Een dag dat de kantine dicht is, zoals een zaterdag zonder thuiswedstrijd of een dag vóór de eerste telling die als dicht staat, hoeft niet meer gedekt te zijn. Zo kan de eerste week (week 34) ook als volledig meetellen.",
        ],
    },
    {
        "versie": "1.47.1",
        "datum": "14 oktober 2026",
        "punten": [
            "Accounts beheren toont per account wanneer iemand voor het laatst actief was op de site (bijvoorbeeld 'Actief vandaag 14:05' of '3 dagen geleden') in plaats van de laatste inlog, die bij 'Ingelogd blijven' weinig zegt. Uitgeklapt staan de precieze tijd en de laatste inlog.",
        ],
    },
    {
        "versie": "1.47.0",
        "datum": "14 oktober 2026",
        "punten": [
            "Prognose → Verkoopdagen: kies per weekdag 'dicht', 'altijd open' of 'alleen bij een thuiswedstrijd'. Staat zaterdag op 'alleen bij een thuiswedstrijd', dan is de kantine op een zaterdag zonder thuiswedstrijd dicht: de prognose verwacht dan niets en de agenda laat de dag weg.",
            "Rapporten → Wedstrijden: zelf een thuiswedstrijd toevoegen die (nog) niet in de teamagenda staat. Hij telt meteen mee in de prognose en op de agenda; komt hij later toch in de agenda van hetzelfde team, dan vervangt die de jouwe. Een zelf toegevoegde wedstrijd kun je ook weer verwijderen.",
            "De Wedstrijden-pagina toont de thuiswedstrijden van de komende 60 dagen in plaats van 14.",
        ],
    },
    {
        "versie": "1.46.0",
        "datum": "14 oktober 2026",
        "punten": [
            "Nieuwe pagina Start → Agenda: per dag wat er de komende 2, 3 of 4 weken in de kantine gebeurt. Of de kantine open of dicht is (met de reden), de thuiswedstrijden met aanvangstijd, evenementen en rustige activiteiten met voor wie, de bardiensten, de trainingsavond, het weer en de verwachte omzet. Werkt ook op de telefoon.",
            "De melding over een evenement in de komende 7 dagen op het overzicht gaat nu naar de agenda.",
        ],
    },
    {
        "versie": "1.45.2",
        "datum": "14 oktober 2026",
        "punten": [
            "Overzicht: de kaart 'Koud zetten' staat ingeklapt; de kop zegt voor welke dag en hoeveel drankjes, klik voor de lijst.",
            "Prognose → Evenementen: kies 'druk' (toernooi, feest, verhuur) of 'rustig' (lunch van een team, vergadering). Een rustige activiteit op een dag dat de kantine anders dicht is, telt als een klein deel van een gewone verkoopdag in plaats van als een drukke dag; ook dat leert de prognose zelf bij.",
            "Evenementen: vul bij 'Voor wie' het team of de groep in (bijvoorbeeld UC). 'UC Lunch' en 'UC Activiteit' leren dan samen hoe UC afwijkt van een gemiddelde dag van die soort; een aantal personen is niet nodig. Begint de naam met een bekende groep, dan vult de site die zelf in.",
            "Overzicht: een evenement in de komende 7 dagen staat in 'Wat moet er nu?', zodat je er op tijd rekening mee houdt.",
        ],
    },
    {
        "versie": "1.45.1",
        "datum": "13 oktober 2026",
        "punten": [
            "Producten: inactieve producten staan niet meer standaard in de lijst; met het vinkje 'Inactieve tonen' zie je ze terug, en bij zoeken komen ze ook gewoon naar voren.",
            "Een product dat in een telling of bestelling staat, heeft geen knop Verwijderen meer (het kan niet weg zonder die geschiedenis kapot te maken), maar Archiveren: dan staat het in geen enkele lijst meer, ook niet bij de prijzen, het zoeken of de gegevenscontrole, terwijl de tellingen en rapporten van toen blijven kloppen. Inactieve producten archiveer je ook in één keer met 'Selectie archiveren'; terugzetten kan onder Producten > Gearchiveerd.",
            "De melding als je een product met geschiedenis toch probeert te verwijderen, zegt nu ook of het al op inactief staat.",
        ],
    },
    {
        "versie": "1.45.0",
        "datum": "13 oktober 2026",
        "punten": [
            "Tapbier telt mee in de omzet: een weggeteld fust telt als 60 glazen van 33 cl à € 2,00 (€ 120). Dat geldt voor de tellingen, de weekomzet, de trend, de marge en de prognose; de eerdere tellingen zijn aangevuld, zodat de cijfers niet ineens verspringen. Glazen per fust en de glasprijs pas je aan bij het fust.",
            "Rapport Marge: per fust wat een glas kost, na hoeveel glazen het fust is terugverdiend en wat schuim en spoelen per fust kosten; met de kostprijs van een pitcher als je invult hoeveel glazen erin gaan. Onder de doelmarge (instelbaar, standaard 30%) staat een voorgestelde prijs, die je met één klik klaarzet bij Prijzen aanpassen.",
            "Nieuwe pagina Producten → Gegevenscontrole (beheerders): wat er aan de productgegevens niet klopt, zoals een verkoopprijs onder de inkoopprijs, een inkoopprijs per stuk in plaats van per krat, een krat zonder aantal, een fust zonder glazen, dubbele artikelcodes en afwijkende eenheden.",
            "Productkaart: eenheid en besteleenheid kies je uit een vaste lijst (met 'Anders'), er is een veld voor het merk en een vinkje 'Niet tellen' (voor bijvoorbeeld een kassaknop zonder voorraad), en een artikelcode kan nog maar bij één product horen.",
            "Kassa tellen: een veld voor de kaartbetalingen uit het PayPal-overzicht (ook achteraf in te vullen). Nieuwe pagina Geld → Omzet en kassa (beheerders): per periode wat PayPal zegt naast de omzet uit de voorraadtellingen.",
            "Prijzen aanpassen: met 'Actie tot en met' komt de oude prijs na de actie vanzelf terug.",
            "Bestellen → Leveranciers: per leverancier de besteldagen, de tijd, levertijd en het minimum bedrag, en welke producten je daar haalt. De bestellijst toont per leverancier wat er besteld moet worden en wat het ongeveer kost, met een pdf per leverancier; op een besteldag staat 'Vandaag bestellen bij ...' op het overzicht.",
            "Nieuw rapport Niet-lopers (beheerders): wat er wel is geteld maar niet verkocht, met de waarde die erin vastzit.",
            "De keuken is een eigen module: Keuken → Tellen (los van de gewone telling), Inboeken (per doos of zak) en Prijzen; de keukenomzet staat bij Keuken → Tellingen en telt mee in Marge en Omzet en kassa.",
            "Koud zetten: op de dag voor een verkoopdag en op de dag zelf staat op het overzicht en de handterminal hoeveel van elk drankje er koud moet.",
            "Prognose → Evenementen: een toernooi, feest of verhuur telt als verkoopdag en wordt drukker gerekend; de prognose leert zelf hoeveel.",
            "Nieuwe pagina Bestellen → Prognose en verkoop: per telling wat de prognose voorspelde (teruggerekend met alleen de tellingen van daarvoor) en wat er werkelijk verkocht is, met de producten waar het het verst naast zat.",
            "Mijn voorkeuren → Weergave: een eenvoudige weergave met alleen je favorieten in het menu en grote knoppen op het overzicht. Ook het blok 'Uitloggen op alle andere toestellen' staat daar nu echt (het viel eerder buiten beeld).",
            "Beheer → Foutmeldingen: kreeg iemand een foutpagina, dan staat dat hier (en op het overzicht). Gebruiksstatistieken tonen nu ook hoe snel de pagina's zijn en wie de inlogpagina opent; zoekmachines tellen niet meer mee en worden buiten het beheer gehouden.",
            "Live zetten is veiliger: de server opent eerst alle pagina's met de nieuwe code op een kopie van de echte gegevens, en zet bij een fout de vorige versie terug. Eenmalige gegevensaanpassingen hebben nu een volgnummer, en de omrekening van de inkoopprijs per krat naar per stuk staat op één plek. Het voorspelmodel is in drie delen gesplitst.",
        ],
    },
    {
        "versie": "1.44.3",
        "datum": "13 oktober 2026",
        "punten": [
            "Snellere pagina's met productfoto's: in lijsten (Producten, Bestellijst, Inboeken, Tellen, zoeken op de handterminal) worden de foto's nu als klein plaatje opgehaald. De pagina Producten haalde voorheen ruim 11 MB aan foto's op voor plaatjes van 32 pixels; alle foto's samen zijn nu 148 kB (13 MB eerst). De kleine versie wordt vanzelf gemaakt.",
            "Beheer → Opslag staat meteen klaar en laat daarna de meting zien (alle bestanden langslopen duurt op de server een paar seconden).",
            "De Kantine-tv-schermen vragen minder van de server: de controle of er iets veranderd is wordt bewaard zolang er niets verandert.",
            "Gebruiksstatistieken: de melding-controle van de Kantine-tv (elke 5 seconden per scherm) telde als paginabezoek en was 64% van alle 'bezoeken'. Dat telt niet meer mee en de oude regels zijn opgeruimd.",
        ],
    },
    {
        "versie": "1.44.2",
        "datum": "13 oktober 2026",
        "punten": [
            "Kaartjes printen: het veld Datum staat weer op alle vijf de ontwerpen, naast Naam en Team. De hardlopers, de turfvakken en het aantal lege regels zijn zoals ze waren.",
        ],
    },
    {
        "versie": "1.44.1",
        "datum": "12 oktober 2026",
        "punten": [
            "Fix in het rapport Marge en bij Derving: de inkoopprijs bij een product is per besteleenheid (bijvoorbeeld een krat van 24), maar werd per stuk gerekend. Daardoor leek de winst sterk negatief en was de waarde van derving veel te hoog. Nu wordt de inkoopprijs eerst naar een stuk omgerekend.",
        ],
    },
    {
        "versie": "1.44.0",
        "datum": "12 oktober 2026",
        "punten": [
            "Taken die terugkomen: bij een eigen taak kies je 'Terugkomen?' (elke week, elke 2 weken, elke maand of op elke verkoopdag). Zodra de taak klaar is, staat de volgende er, en pas een paar dagen voor de uiterste datum op het overzicht.",
            "Checklists: een taak kan stappen hebben (bijvoorbeeld 'Kantine openen' of 'Kantine sluiten', met voorbeelden die je kunt aanpassen). Wie de taak krijgt vinkt de stappen zelf af; afronden kan pas als alles is afgevinkt.",
            "Eigen taken staan nu ook op het startscherm van de handterminal.",
            "Producten → Prijslijst: alle prijzen bekijken zonder ze te kunnen wijzigen (voor iedereen met de voorraadsectie), met wat er binnenkort verandert en een pdf van de prijslijst voor aan de bar. Er is een taak 'Prijzenlijst nalopen (alleen kijken)' om vrijwilligers de prijzen te laten nalopen.",
            "Prijzen aanpassen: je kunt een 'Ingaan op'-datum invullen. De prijzen staan dan klaar en gaan op die dag vanzelf in (op de tv en in de prijsgeschiedenis).",
            "Nieuw rapport Marge (beheerders): wat elk product en elke categorie oplevert, welke producten het minst verdienen en welke geen inkoopprijs hebben.",
            "Derving: bij In/uit boeken → Uit kun je een reden kiezen (breuk, over de datum, gratis weggegeven, eigen gebruik). Het nieuwe rapport Derving (beheerders) laat zien wat er zonder verkocht te zijn uit de voorraad is verdwenen en wat dat kost.",
            "Overzicht: een kaart 'Thuiswedstrijd' bij een thuiswedstrijd in de komende 5 dagen, met het weer, de verwachte omzet die dag en welke producten kunnen opraken ('Bestel nu' binnen 3 dagen).",
            "Tellen: naast elk invulveld staan turfknoppen (+1, +5 en een hele krat of doos).",
            "Kantine-tv: een dia kan een begin- en einddatum krijgen ('Tonen vanaf' en 'Tonen tot en met'), zodat hij zichzelf aan en uit zet.",
            "Sneller: de berekeningen van het voorspelmodel worden ook op schijf bewaard, zodat de verschillende serverprocessen en een nieuwe start ze niet allemaal zelf opnieuw hoeven uit te rekenen.",
        ],
    },
    {
        "versie": "1.43.6",
        "datum": "12 oktober 2026",
        "punten": [
            "Kaartjes printen: het veld Datum is van alle ontwerpen weggehaald. Naam en Team hebben de plek gekregen, en bij de vierkante en het staande ontwerp is de vrijgekomen ruimte schrijfruimte geworden: 'Vierkant' en 'Staand, smal' hebben nu 4 lege regels, 'Vierkant, met logo' 3.",
        ],
    },
    {
        "versie": "1.43.5",
        "datum": "12 oktober 2026",
        "punten": [
            "Kaartjes printen: de andere vier ontwerpen zijn opnieuw opgezet, in dezelfde stijl als het brede kaartje (Naam, Team en Datum bovenaan, dubbele blauwe lijn, een leeg turfvak per hardloper, lege regels onderaan). 'Breed, hoog turfvak' heeft grote vakken en 3 lege regels; 'Vierkant' heeft per hardloper een lang turfvak en 3 lege regels; 'Vierkant, met logo' heeft een slanke logobalk en 2 lege regels; 'Staand, smal' (46 x 82 mm, 12 op een vel) heeft de naam boven een breed turfvak en 3 lege regels. De kleine hokjes waar je geen streepjes in kon zetten zijn overal weg.",
        ],
    },
    {
        "versie": "1.43.4",
        "datum": "12 oktober 2026",
        "punten": [
            "Kaartjes printen: er passen nu 4 hardlopers op een kaartje in plaats van 6, zodat er meer vrije ruimte overblijft. De ruimte van de twee weggevallen artikelen is schrijfruimte geworden: elk ontwerp heeft meer lege regels (bij het brede ontwerp 4, bij het brede met turflijn 4, bij het vierkante 'ruim' 5 en bij de andere twee 3). Had je er al meer ingesteld, dan staan de laatste hardlopers niet meer op het kaartje en zegt de pagina welke.",
        ],
    },
    {
        "versie": "1.43.3",
        "datum": "12 oktober 2026",
        "punten": [
            "Kaartjes printen: de lichte streepjes in de turfvakken zijn weggehaald. Het vak achter elke hardloper is nu helemaal leeg, zodat je zelf turft zoals je gewend bent.",
        ],
    },
    {
        "versie": "1.43.2",
        "datum": "12 oktober 2026",
        "punten": [
            "Bestellijst en Prognose openen meteen. De bestellijst zelf en de instellingen van de prognose staan direct klaar; de voorspelde tekorten en de prognose zelf worden erna berekend en komen er een paar seconden later bij.",
            "Het voorspelmodel onthoudt zijn uitkomst nu een uur in plaats van tien minuten, en het overzicht laat het alvast rekenen zodra het klaar is. Daardoor zijn Bestellijst, Prognose en Tellingen meestal meteen volledig, ook na een pauze. Een nieuwe telling, boeking of wedstrijd rekent het nog steeds meteen opnieuw door.",
            "Delen van een pagina die apart laden tellen niet meer mee als paginabezoek bij de gebruiksstatistieken.",
        ],
    },
    {
        "versie": "1.43.1",
        "datum": "12 oktober 2026",
        "punten": [
            "Het tellingenoverzicht opent meteen. De lijst met tellingen staat direct klaar; de verwachting, de trend en de omzet per week worden erna berekend en komen er een paar seconden later bij. Voorheen duurde het openen na een tijdje niet gebruikt te zijn zo'n 5 seconden, omdat die cijfers eerst klaar moesten zijn.",
        ],
    },
    {
        "versie": "1.43.0",
        "datum": "12 oktober 2026",
        "punten": [
            "Nieuwe pagina Producten → Prijzen aanpassen (beheerders): alle verkoopprijzen in één tabel nalopen en in één keer opslaan, inclusief de prijsopties van een fust en de prijs per glas. Je kunt alle getoonde prijzen met een percentage of bedrag verhogen of verlagen (met afronden op 5, 10 of 50 cent) en daarna nakijken; gewijzigde prijzen kleuren geel, de marge staat erbij, en elke wijziging komt in de prijsgeschiedenis.",
            "Eigen taken bij 'Wat moet er nu?': een beheerder voegt via Start → Taken (of de knop '+ Taak toevoegen' op het overzicht) een taak toe en koppelt die aan een of meer mensen door ze te taggen met een @ (net als op het prikbord; alleen mensen met een account, die ook een mail krijgen als hun e-mailadres bekend is), met eventueel een uiterste datum. Kies een veelvoorkomende klus (prijzen nalopen, nieuw product toevoegen, tellen, bestellen, inboeken, frituurvet, dia's), een pagina uit het menu, of een taak zonder pagina. Een klik op de taak brengt je op die pagina; sla je daar iets op, dan vraagt een pop-up 'Taak … afgerond?'. Met 'Klaar' rond je een taak ook zo af. Je kiest of iedereen het zelf moet afronden of dat een van hen genoeg is.",
            "Bovenaan dit versielogboek staat nu een overzicht van alle modules met hun vermoedelijke versienummer.",
        ],
    },
    {
        "versie": "1.42.2",
        "datum": "12 oktober 2026",
        "punten": [
            "Het overzicht (startpagina) opent weer meteen. De omzettrend per week staat er een paar seconden later bij, en de opslagmelding wordt elke nacht gemeten in plaats van bij elk bezoek. Daardoor kon het openen van het overzicht, na een tijdje niet gebruikt te zijn, wel 8 seconden duren.",
        ],
    },
    {
        "versie": "1.42.1",
        "datum": "12 oktober 2026",
        "punten": [
            "Breder scherm: op een computer gebruikt de site nu de hele breedte van het scherm in plaats van een smalle kolom in het midden. Het menu staat links, onder het logo. Op telefoon en tablet verandert er niets.",
        ],
    },
    {
        "versie": "1.42.0",
        "datum": "12 oktober 2026",
        "punten": [
            "Overzicht: de omzettrend staat nu per week (maandag t/m zondag) in plaats van per telling, met het aantal thuiswedstrijden per week en de vergelijking van vorige week met de week ervoor en met het gemiddelde. Dat voorkomt schijnbare dalen doordat de tijd tussen tellingen wisselt.",
            "Nieuwe pagina Beheer → Opslag: hoeveel schijfruimte de site gebruikt, wat het meeste inneemt (video's, back-ups, foto's), bij welke dia een video hoort en welke video's nergens meer bij horen (met een knop om die op te ruimen). Vanaf 80% van de ingestelde ruimte staat er een melding bij 'Wat moet er nu?' (alleen voor beheerders).",
            "Video's: een zware video (bijvoorbeeld een opname van een iPhone of Mac) wordt bij het uploaden automatisch verkleind naar 720p en ongeveer 3 Mbit/s, als de server ffmpeg heeft. Zo laadt hij snel op de tv en neemt hij weinig ruimte in. Bij een fout blijft het origineel gewoon bewaard.",
        ],
    },
    {
        "versie": "1.41.0",
        "datum": "12 oktober 2026",
        "punten": [
            "Nieuwe pagina Voorraad → Kaartjes printen: voorgedrukte kaartjes (Naam, Team, Datum, hardlopers met turfvakken en lege regels) op A4 om uit te knippen. Kies uit 5 ontwerpen (breed, breed met lange turflijn, en drie vierkante maten), typ zelf de hardlopers (of klik ze aan uit wat dit seizoen het meest is verkocht, met merken samengenomen zoals alle Bozu-smaken), kies het aantal vellen en eventueel zwart-wit. De instellingen blijven bewaard en het voorbeeld past zich meteen aan.",
        ],
    },
    {
        "versie": "1.40.0",
        "datum": "10 oktober 2026",
        "punten": [
            "Kantine-tv: een dia (video, sponsor of mededeling) kan nu vaker per ronde van de diashow in beeld komen. Bij Dia's & sponsoren → bewerken kies je 'Hoe vaak per ronde' (1 t/m 6); de extra keren worden gelijkmatig over de ronde verspreid en een dia komt nooit direct na zichzelf. Een video wordt daarbij nog steeds maar één keer opgehaald.",
        ],
    },
    {
        "versie": "1.39.1",
        "datum": "10 oktober 2026",
        "punten": [
            "Video op een dia laadde niet goed (haperen, of de dia was weg voordat de video speelde). Het scherm haalt een video nu eerst helemaal binnen en toont de dia pas als hij klaar is (een nog ladende video-dia wordt tijdelijk overgeslagen), en speelt hem daarna steeds meteen af zonder opnieuw te laden.",
            "Een te zware video (bijvoorbeeld een opname van een iPhone of Mac van 18 Mbit/s) geeft bij het uploaden een waarschuwing, en het formulier toont de grootte van de huidige video. Richtlijn: 720p en ongeveer 3 Mbit/s.",
        ],
    },
    {
        "versie": "1.39.0",
        "datum": "10 oktober 2026",
        "punten": [
            "Kantine-tv: een video op een dia. Kies bij Dia's & sponsoren → Nieuwe dia de layout 'Video (schermvullend, met optioneel onderschrift)' en upload een filmpje (mp4, mov of webm, maximaal 80 MB). Het scherm speelt de video schermvullend af, standaard zonder geluid en zo lang als de video duurt (of een vaste tijd, en op wens met geluid). Het formulier toont een live voorbeeld; een nieuwe upload vervangt de oude video en bij het verwijderen van de dia verdwijnt de video ook.",
        ],
    },
    {
        "versie": "1.38.0",
        "datum": "10 oktober 2026",
        "punten": [
            "Kantine-tv, dia 'Leden? Steun de club!': staat nu los van de naammuur. Eerder verdwenen de onbetaalde leden van die dia zodra je de muur op 'alleen wie dit seizoen betaald heeft' zette; nu kun je de muur alleen de betaalde leden laten tonen en staan de onbetaalde leden alleen op deze dia's. Bij Club van 20 → Scherm & werving kies je onder 'Wie staat er op die dia?' hoe ver terug iemand betaald moet hebben (standaard: de laatste 3 seizoenen).",
        ],
    },
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


# Het overzicht van de modules bovenaan het versielogboek op de Help-pagina. Er is geen aparte versiebeheer per module:
# dit nummer is een schatting uit het logboek hierboven en bedoeld als houvast, niet als exacte administratie.
# Het is opgebouwd als hoofd.uitbreidingen.verbeteringen: hoofd 1 = in gebruik (0 = nog nieuw), uitbreidingen = het
# aantal versies waarin er iets bij is gekomen, verbeteringen = het aantal versies met alleen een kleine aanpassing of fix.
# Pas een module aan? Tel dan bij 'versie' de uitbreiding of verbetering erbij op en zet 'laatst' op de nieuwe appversie
# (zie CLAUDE.md).
MODULES_UITLEG = (
    "Er is geen aparte versie per module; dit nummer is een schatting op basis van dit logboek. Het eerste getal is 1 "
    "voor een module die in gebruik is (0 = nog nieuw), het tweede telt de versies waarin er iets bij is gekomen en het "
    "derde de versies met een kleine verbetering of fix."
)
MODULES = [
    {"naam": "Voorraad & tellen", "versie": "1.16.0", "sinds": "0.1.0", "laatst": "1.72.0",
     "inhoud": "Voorraadoverzicht, in- en uitboeken, tellen (ook met de looplijst), tellingen, leveringen inboeken, schaplabels en kaartjes printen"},
    {"naam": "Bestellen & prognose", "versie": "1.20.1", "sinds": "0.4.0", "laatst": "1.75.0",
     "inhoud": "Bestellijst met de prognose erin (ook per leverancier), leveranciers, bestellen en de klaargezette bestelling als concept van de factuur, voorspelde tekorten, prognose van de verkoop met evenementen en de vergelijking met de werkelijke verkoop, boodschappenlijst"},
    {"naam": "Producten & prijzen", "versie": "1.16.1", "sinds": "0.1.0", "laatst": "1.72.0",
     "inhoud": "Assortiment, categorieën, prijsopties, verbruiksvoorwerpen, gegevenscontrole en alle verkoopprijzen in één keer aanpassen (ook als actie)"},
    {"naam": "Geld (kassa & kluis)", "versie": "1.4.0", "sinds": "1.0.0", "laatst": "1.45.0",
     "inhoud": "Kassa tellen met vier-ogen-goedkeuring en kaartbetalingen, omzet en kassa naast elkaar, afdracht en toevoeging, kluis, geschiedenis"},
    {"naam": "Keuken", "versie": "1.7.0", "sinds": "1.6.0", "laatst": "1.75.0",
     "inhoud": "Keukenvoorraad met een eigen, blinde telling (ook als looplijst met dozen scannen, en een begintelling), inboeken per verpakking (per merk, ook door te scannen), weggooien en bijstellen, prijzen, de boodschappenlijst bij een tekort, en de herinnering voor het frituurvet"},
    {"naam": "Kantine-tv", "versie": "1.27.0", "sinds": "1.10.1", "laatst": "1.80.0",
     "inhoud": "Prijzenscherm, dia's (in mappen, met momenten, de schijnwerper over alle tv's, effecten en griezelposters met tekeningen), sponsoren, standen, Man of the Match, video's en meldingen op het scherm, gekoppelde tv's die je op afstand beheert (ook vanaf de handterminal), zelfherstel en de timer op de tv, het Halloween-thema, en de tablet-app Kantine Beheer"},
    {"naam": "Club van 20", "versie": "1.11.6", "sinds": "1.16.0", "laatst": "1.38.0",
     "inhoud": "Ledenlijst, betalingen, naammuur en dia's, openbare pagina, aanmelden en verlengen, importeren"},
    {"naam": "Stemmen", "versie": "1.0.0", "sinds": "", "laatst": "",
     "inhoud": "Stemvragen met een openbare stempagina (staat niet apart in dit logboek, dus een gok)"},
    {"naam": "Rapporten", "versie": "1.14.1", "sinds": "0.1.0", "laatst": "1.70.0",
     "inhoud": "Verkooprapport, weekoverzicht, omzet per seizoen en bardienst, compacte uitdraai, omzettrend"},
    {"naam": "Handterminal", "versie": "1.6.2", "sinds": "1.5.0", "laatst": "1.54.0",
     "inhoud": "De weergave voor de handterminal: boeken, inboeken, tellen en een startscherm met wat aandacht nodig heeft"},
    {"naam": "Handterminal-app", "versie": "0.25.0", "sinds": "1.53.0", "laatst": "1.79.0",
     "inhoud": "De zelfstandige Android-app voor de Zebra: zoeken, productinformatie (ook door een schaplabel te scannen), boeken, tellen, factuur inboeken (ook een klaargezette bestelling), barcodes (aanpassen en de koppelronde), artikelen en nieuwe producten, prikbord, bestellijst (nalopen met vinkjes, klaarzetten met het besteloverzicht, verbruiksvoorwerpen melden), boodschappen, prognose, agenda, kassa en kluis, keuken (inboeken per verpakking, blind tellen, weggooien), Club van 20-aanmeldingen en taken, uitverkocht op de tv, de timer en de kantine-tv (tv's koppelen en beheren, specials, bardienst, momenten met de schijnwerper, mappen en dia's aan of uit, en het Halloween-thema), plus inloggen met je code, de scanner, verbindingsbewaking en het vergrendel-scherm bij een noodstop"},
    {"naam": "Accounts & rechten", "versie": "1.10.5", "sinds": "0.1.0", "laatst": "1.65.1",
     "inhoud": "Inloggen, rollen en rechten per sectie, tablet-code, blokkeren en overal uitloggen"},
    {"naam": "Back-ups & beheer", "versie": "1.10.0", "sinds": "0.2.0", "laatst": "1.45.0",
     "inhoud": "Dagelijkse back-up en herstelcontrole, logboek, opslag, gebruiksstatistieken, privacy"},
    {"naam": "Overzicht & prikbord", "versie": "1.13.0", "sinds": "0.2.0", "laatst": "1.67.0",
     "inhoud": "Dashboard, 'Wat moet er nu?', agenda, prikbord, zoekbalk en de tips-pagina"},
    {"naam": "Taken", "versie": "0.3.0", "sinds": "1.43.0", "laatst": "1.44.0",
     "inhoud": "Eigen taken voor mensen bij 'Wat moet er nu?': terugkerend, met checklists, en de vraag 'Taak afgerond?' na het opslaan"},
    {"naam": "Techniek & beveiliging", "versie": "1.9.2", "sinds": "1.1.0", "laatst": "1.64.0",
     "inhoud": "Geautomatiseerde tests, beveiligingsheaders, de noodstop, bereikbaarheidscontrole, snelheid"},
]
