# Kantine Android-apps

Drie losstaande Android-apps rond kantineblauwgeel.nl:

- **`tv/`** — "Kantine TV", voor Google TV / Android TV. Alleen een gekoppeld
  scherm (sinds 1.2 geen menu meer): koppelen met de QR-code of de code, en wat
  hij toont en hoe groot stel je op de site of de handterminal in. Met de
  afstandsbediening: omlaag de prijzenlijst, omhoog de dia's, OK de instellingen
  (zoom per scherm, bewaard op de tv). Start vanzelf na een
  herstart en herstelt zichzelf na een storing. Zie het kopje "Hoe de apps met de
  website praten".
- **`tablet/`** — "Kantine Beheer", voor tablets. Toont de volledige website
  (ingelogd, met alle beheerfuncties zoals producten, acties, bardiensten en
  kiosk-instellingen) in een app-schil met een zijmenu voor snelle navigatie.
- **`handterminal/`** — "Kantine Handterminal", voor de Zebra TC51 (en andere
  Android-handterminals vanaf Android 6). Zie het kopje hieronder.

Ze zijn los te bouwen en los te publiceren — het zijn aparte modules in één
Gradle-project, zodat je ze in één Android Studio-venster kunt openen en beheren.

## Kantine Handterminal (`handterminal/`)

Een zelfstandige app met eigen schermen (er opent nergens een websitepagina) voor het werk op de handterminal. Hij
praat met de site via een JSON-API (`routes/app_api.py` voor het dagelijkse werk, `routes/app_api_meer.py` voor de rest:
productinformatie, kassa en kluis, keuken, boodschappen, aanmeldingen, agenda, prognose, barcodes en taken,
`routes/app_api_tv.py` voor de kantine-tv, `routes/app_api_barcodes.py` voor artikelen aanpassen en de koppelronde, en voor facturen `routes/facturen.py`) en gebruikt dezelfde logica en database als de site. Wat alleen op de site kan
(corrigeren, bewerken, dia's maken), meldt de app met "Niet mogelijk in de app" (`nietInApp` in `BasisActivity`);
hij opent nooit de website. Inloggen gaat met de persoonlijke 6-cijferige code (`/api/tablet-code/inloggen`); de app bewaart
de sessie-cookie zelf (`Sessie.kt`) en stuurt bij een POST het csrf_token mee in `X-CSRF-Token`.

- **Schermen**: `InlogActivity` (code), `StartActivity` (tegels, "Let op", "Meer"), `ProductenActivity`
  (zoeken/voorraad/boeken), `ProductActivity` (voorraad, boeken en alles van de productpagina van de site, met
  `WeekGrafiek`), `KoppelenActivity` (onbekende barcode), `TellenActivity` (looplijst zoals op de site, met rekenmachine,
  en de controle), `FacturenActivity`/`FactuurActivity` (factuur inboeken), `PrikbordActivity`, `BestellijstActivity`,
  `KlaarzettenActivity` (een bestelling klaarzetten), `TellingenActivity`, `GeschiedenisActivity`, `BoodschappenActivity`, `PrognoseActivity`, `AgendaActivity`,
  `UitverkochtActivity` (producten op het prijzenscherm op uitverkocht zetten), `TimerActivity` (de timer op de tv's),
  `KantineTvActivity` (tv's: koppelen met de QR-code of de code, aan of uit, wat ze tonen, opnieuw laden, de wisselknop; specials; bardienst van vandaag en
  morgen), `DiasActivity` (onderdelen van de diashow en losse dia's aan of uit), `KoppelrondeActivity` (alle producten
  zonder barcode van een losse verpakking één voor één scannen),
  `BarcodesActivity`, `GeldActivity`/`GeldTellenActivity` (kassa en kluis), `KeukenActivity` (frituurvet, voorraad met de gekoppelde dozen, boodschappenlijst), `KeukenTellenActivity` (de keukentelling als looplijst met scans en controle; de stand staat op het toestel én op de site, gedeeld met de keukenlooplijst van de site), `KeukenTellingActivity` (een keukentelling bekijken), `KeukenInvoerActivity` (keuken inboeken),
  `AanmeldingenActivity`, `TaakActivity` (een taak van een beheerder; `Schermen.kt` weet welk scherm bij welke
  pagina van de site hoort) en `VergrendeldActivity` (de noodstop). Gedeeld gedrag (kopbalk, scanner, automatisch uitloggen, fouten, "Niet mogelijk in de
  app", de vraag "Taak afgerond?") zit in `BasisActivity`; lijsten en kaarten in `Lijst.kt`, productfoto's in
  `Fotos.kt`, het koppelen van een barcode in `Koppelvraag.kt`.
- **Snel**: de hele productlijst met barcodes staat op het toestel (`Catalogus.kt`, ververst met een ETag); zoeken en
  een scan opzoeken wachten dus niet op de site. Tellen gebeurt helemaal op het toestel; de stand gaat elke paar
  producten naar de site (zelfde vorm als de looplijst van de site, dus verder gaan kan ook daar).
- **Nooit dubbel**: schrijfacties krijgen een `verzoek_id`. Valt de verbinding weg, dan probeert de app het opnieuw en
  geeft de site het bewaarde antwoord terug in plaats van het nog eens te doen (`eenmalig` in `routes/app_api.py`,
  tabel `app_verzoeken`). Zware berekeningen (de verkoop per week, de prognose en bij het tellen wat er verwacht wordt) haalt een
  scherm pas op als het nodig is, apart van de rest. Bij het begin van een telling zet de app alle foto's van de looplijst
  op het toestel, met de voortgang in de kopbalk.
- **Scanner (DataWedge)**: de app maakt bij het starten zelf een DataWedge-profiel "Kantine Handterminal" aan (scans
  als broadcast, geen toetsaanslagen). Een scan opent het product, of het koppelen van een onbekende barcode. Een product
  opent als informatie (`alleenInfo`, de standaard): boeken staat onderaan en er staat niets klaar. Alleen via Boeken
  (en na het koppelen van een onbekende barcode) staat boeken bovenaan, met het gescande aantal ingevuld. Een losse
  verpakking terwijl er een doos van bestaat: de vraag of de volle besteleenheid erin moet.
- **Verbinding**: een stip in de kopbalk, automatisch opnieuw proberen, en een wifi-lock zolang de app voorin staat.
- **Noodstop**: elk scherm kijkt elke 15 seconden naar `/noodstop/status` (staat ook tijdens een noodstop open). Is de
  site afgesloten, dan logt de app uit en toont hij het vergrendel-scherm (`VergrendeldActivity`), net als de tv; dat
  kijkt of alles weer open is en gaat dan naar het inlogscherm. Zonder verbinding gebeurt het zodra de site weer
  bereikbaar is.
- **Bestellingen**: een klaargezette bestelling staat bij Factuur inboeken als concept (`/api/facturen/bestelling/<id>`);
  het factuurscherm toont dan besteld naast gescand, met "zoals besteld" (`/api/facturen/<id>/zoals-besteld`). Een
  barcode die bij geen enkel product hoort: in `KoppelenActivity` kan ook een nieuw product
  (`/api/app/producten/nieuw`). Een artikel toevoegen kan op het productscherm (`/api/app/producten/<id>/artikelen`).
- **Tellen samen met de site**: elke telling heeft een `loop_id`. Wordt hij op de site of een ander toestel
  afgebroken, opgeslagen of opnieuw begonnen, dan antwoordt de site bij het doorgeven met 409 `afgebroken` en stopt
  de app ook. Afbreken en pauzeren gaan op de achtergrond door als het scherm sluit (`Achtergrond.kt`).
- **Android 6**: de site gebruikt Let's Encrypt (ISRG Root X1), dat Android 6 en 7.0 niet kennen. Het rootcertificaat
  zit in `res/raw`; zie `Beveiliging.kt`.
- **Nieuwe versie**: zet `HANDTERMINAL_APP_VERSIE` in `routes/app_api.py` gelijk aan `versionName`; een oudere app
  meldt dan op het startscherm dat er een nieuwe is.

**Bouwen** (de buildmap staat buiten iCloud, in `~/.kantine-apps/build/handterminal`,
omdat iCloud anders "… 2"-kopieën maakt waarop de build vastloopt):

```bash
cd android-apps
JAVA_HOME=~/Library/Java/JavaVirtualMachines/jbr-21.0.11/Contents/Home ./gradlew :handterminal:assembleRelease
```

De APK staat dan in `~/.kantine-apps/build/handterminal/outputs/apk/release/`.

**Ondertekenen**: de sleutel staat in `~/.kantine-apps/handterminal.jks`, het
wachtwoord in `~/.kantine-apps/handterminal-ondertekenen.properties` (allebei
buiten de repository). Bewaar ze samen op een veilige plek: een update van de app
moet met dezelfde sleutel ondertekend zijn, anders moet hij er eerst af en opnieuw op.
Bij een nieuwe versie: `versionCode` en `versionName` in `handterminal/build.gradle.kts`
ophogen.

**Testen**: de testversie (`assembleDebug`) heeft in Instellingen een aanpasbaar
website-adres (bijvoorbeeld `http://10.0.2.2:5050` voor een lokale server vanuit de
emulator). Een scan nabootsen:
`adb shell am broadcast -a nl.kantineblauwgeel.handterminal.SCAN -c android.intent.category.DEFAULT --es com.symbol.datawedge.data_string 8710200001234`.

## Zelf bouwen

Zo bouw je de tv- en tablet-app (voor de handterminal: zie hierboven):

1. Open de map `android-apps/` in Android Studio (laatste stabiele versie).
   Android Studio herkent het als Gradle-project en biedt aan de Gradle
   wrapper aan te maken/synchroniseren — accepteer dat.
2. Laat Android Studio de benodigde SDK-platformen (API 34) installeren als
   erom gevraagd wordt.
3. Kies boven in de werkbalk het run-configuratie `tv` of `tablet` en klik op
   Run, met een Android TV-emulator/toestel resp. een tablet-emulator/toestel
   aangesloten.

## Voor het publiceren op Google Play

Dit zijn dingen die alleen jij handmatig kunt doen (jouw Google-account,
tekenmateriaal, keuzes over vermelding):

1. **Icoon/banner vervangen** — er staat nu een tijdelijk icoon in
   (`tv/src/main/res/drawable/app_icon.png` en `.../banner.png`,
   `tablet/src/main/res/drawable/app_icon.png`), gekopieerd van het bestaande
   website-logo. Gebruik in Android Studio **File → New → Image Asset** om
   nette adaptieve iconen (en voor de tv-app een banner van 320×180) te
   genereren.
2. **App-ID's** — de apps heten nu `nl.kantineblauwgeel.tv` en
   `nl.kantineblauwgeel.tablet` (in de `build.gradle.kts` van elke module).
   Dit is de unieke Play Store-identiteit; eenmaal gepubliceerd kun je dit
   niet meer wijzigen.
3. **Signing/AAB** — maak via **Build → Generate Signed App Bundle** een
   signed `.aab` per app, met een eigen keystore (bewaar deze goed, je hebt 'm
   nodig voor elke toekomstige update).
4. **Play Console** — maak twee nieuwe app-vermeldingen aan (één voor de
   tv-app, één voor de tablet-app). Voor de tv-app moet je in de
   Play Console-formfactorinstellingen "Android TV" aanvinken. Beide hebben
   verplicht: een privacyverklaring-URL, contentbeoordeling-vragenlijst,
   screenshots en een korte/lange omschrijving.
5. **Testen op een echt toestel**: zet het Chromecast/Google TV-toestel en de
   tablet in dezelfde ontwikkelaarsmodus (USB-debugging) om rechtstreeks
   vanuit Android Studio te installeren, vóór je naar Play Console upload.

## Hoe de apps met de website praten

- **Gekoppeld scherm** (het enige scherm): de app opent `/kiosk/koppelen`. Die pagina
  geeft de tv een eigen token en gaat naar `/kiosk/t/<token>`; daar staat een
  koppelcode met een QR-code (`/kiosk/koppel/<code>`). Scan die met de
  handterminal-app, of vul de code op de site in bij Kantine-tv → Tv koppelen (zie
  `kiosk_tvs.py`). Daarna kies je wat de tv toont en hoe groot. De app onthoudt dat
  eigen adres (`Prefs.getGekoppeldUrl`), en gaat bij het starten (ook met de hand,
  via `SplashActivity`) meteen terug naar dat scherm. De pagina praat met de app
  via `window.KantineTv` (`PlayerActivity.Brug`): `versie()` (zo ziet de site welke
  app-versie er draait) en `scherm(toont, zoom)` (wat de pagina toont en de grootte
  van de site; de app gebruikt zijn eigen zoom voor dat scherm als die in de
  instellingen is gekozen, anders die van de site, als `textZoom`). Zie `templates/_kiosk_herstel.html` op de site.
- **Afstandsbediening**: knop omlaag/omhoog stuurt `POST /kiosk/t/<token>/scherm`
  (`{"toont": "prijzen"}` of `"dias"`); het token van de tv is de toegang. Dat
  wordt de instelling van de tv op de site, en de app laadt meteen opnieuw.
- De vaste, inlogvrije kiosk-URL's (`/kiosk/prijzen`, `/kiosk/scherm`, `/kiosk/tv`)
  werken nog voor een browser of Chromecast, maar zitten niet meer in de tv-app.
- **Zelfherstel**: lukt het laden niet (geen wifi, een foutpagina van de server),
  dan probeert `PlayerActivity` het elke 15 seconden opnieuw, en meteen als het
  netwerk terug is; loopt de webweergave vast, dan begint het scherm opnieuw.
- **Testen**: de testversie kan een ander adres krijgen, bijvoorbeeld een lokale
  server vanuit de emulator: `./gradlew :tv:assembleDebug -PtvBasisUrl=http://10.0.2.2:5050`
  (alleen de testversie mag dan ook zonder https). De tv-app vraagt Android 7 of
  nieuwer.
- De tablet-app is een volwaardige webweergave van `https://kantineblauwgeel.nl`
  (aanpasbaar via **Instellingen** in de app, voor bijvoorbeeld een
  test-omgeving). Inloggen gebeurt gewoon via de normale inlogpagina van de
  website; de sessie (cookies) blijft bewaard in de app totdat je op
  "Uitloggen" drukt in de app-instellingen.
- Het zijmenu in de tablet-app springt direct naar: Dashboard, Voorraadoverzicht,
  Producten, Acties, Bardiensten, Prijzenscherm-instellingen, Dia's & sponsoren
  en het Kiosk-overzicht — dit zijn bestaande, ingelogde pagina's van de site.
