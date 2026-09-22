# Kantine Android-apps

Twee losstaande Android-apps rond kantineblauwgeel.nl:

- **`tv/`** — "Kantine TV", voor Google TV / Android TV. Schermkiezer tussen
  de 3 bestaande kiosk-schermen van de website, met een zoom-instelling die
  bewaard blijft (ook na herstarten van de tv).
- **`tablet/`** — "Kantine Beheer", voor tablets. Toont de volledige website
  (ingelogd, met alle beheerfuncties zoals producten, acties, bardiensten en
  kiosk-instellingen) in een app-schil met een zijmenu voor snelle navigatie.

Beide zijn los te bouwen en los te publiceren op Google Play — het zijn twee
aparte modules in één Gradle-project, zodat je ze in één Android Studio-venster
kunt openen en beheren.

## Zelf bouwen

Deze omgeving heeft geen Android SDK/Java, dus de code is hier niet gebouwd of
getest. Zo bouw je 'm:

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
