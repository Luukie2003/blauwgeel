# Kantine Android-apps

Drie losstaande Android-apps rond kantineblauwgeel.nl:

- **`tv/`** — "Kantine TV", voor Google TV / Android TV. Schermkiezer tussen
  de 3 bestaande kiosk-schermen van de website, met een zoom-instelling die
  bewaard blijft (ook na herstarten van de tv).
- **`tablet/`** — "Kantine Beheer", voor tablets. Toont de volledige website
  (ingelogd, met alle beheerfuncties zoals producten, acties, bardiensten en
  kiosk-instellingen) in een app-schil met een zijmenu voor snelle navigatie.
- **`handterminal/`** — "Kantine Handterminal", voor de Zebra TC51 (en andere
  Android-handterminals vanaf Android 6). Zie het kopje hieronder.

Ze zijn los te bouwen en los te publiceren — het zijn aparte modules in één
Gradle-project, zodat je ze in één Android Studio-venster kunt openen en beheren.

## Kantine Handterminal (`handterminal/`)

Inloggen met de persoonlijke 6-cijferige code (dezelfde als de tablet-code, via
`/api/tablet-code/inloggen`), daarna de handterminal-weergave van de site in een
WebView. Wat de app daaraan toevoegt:

- **Automatisch uitloggen** na een instelbare tijd zonder aanraken of scannen
  (standaard 15 minuten): iedereen gebruikt hetzelfde toestel met een eigen code.
  Dezelfde persoon gaat na opnieuw inloggen verder waar hij was.
- **Scanner (DataWedge)**: de app maakt bij het starten zelf een DataWedge-profiel
  "Kantine Handterminal" aan (scans als broadcast, geen toetsaanslagen). Wat er met
  een scan gebeurt staat in `src/main/assets/scan.js`: een scanveld op de pagina,
  anders `/barcodes/zoek?direct=1` (bekende barcode → product). Een pagina kan het
  ook zelf afhandelen met een `kantine-scan`-event. In andere apps blijft de scanner
  gewoon typen.
- **Verbinding**: een balk bovenin (groen/oranje/rood), een foutscherm dat vanzelf
  opnieuw probeert (en meteen zodra het netwerk terug is), een wifi-lock zolang de
  app voorin staat, en een mislukt formulier wordt nooit vanzelf opnieuw verstuurd.
- **Android 6**: de site gebruikt Let's Encrypt (ISRG Root X1), dat Android 6 en
  7.0 niet kennen. Het rootcertificaat zit in `res/raw`; zie `Beveiliging.kt`.
  De WebView moet wel versie 72 of nieuwer zijn (anders stuurt `fetch()` de
  inlogcookie niet mee); bij een oudere toont het inlogscherm een waarschuwing.

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
emulator) en opent met `adb shell am start -n nl.kantineblauwgeel.handterminal/.HoofdActivity --es test_url <adres>`
een pagina zonder in te loggen. Een scan nabootsen:
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

- De 3 tv-schermen zijn de bestaande, inlogvrije kiosk-URL's:
  `/kiosk/prijzen`, `/kiosk/scherm`, `/kiosk/tv`. Elk ververst zichzelf al via
  JavaScript-polling op de website — de app hoeft daar niets extra's voor te
  doen.
- De tablet-app is een volwaardige webweergave van `https://kantineblauwgeel.nl`
  (aanpasbaar via **Instellingen** in de app, voor bijvoorbeeld een
  test-omgeving). Inloggen gebeurt gewoon via de normale inlogpagina van de
  website; de sessie (cookies) blijft bewaard in de app totdat je op
  "Uitloggen" drukt in de app-instellingen.
- Het zijmenu in de tablet-app springt direct naar: Dashboard, Voorraadoverzicht,
  Producten, Acties, Bardiensten, Prijzenscherm-instellingen, Dia's & sponsoren
  en het Kiosk-overzicht — dit zijn bestaande, ingelogde pagina's van de site.
