# Kantine Voorraadbeheer

Webapplicatie om de voorraad van de voetbalkantine bij te houden: producten en
voorraadniveaus, in/uit boeken, en een bestellijst die automatisch wordt
samengesteld op basis van producten die onder hun minimumvoorraad zitten. Als
een bestelling binnenkomt boek je hem in en wordt de voorraad automatisch
bijgewerkt.

Gebouwd met Python (Flask) en SQLite — geen Node.js nodig.

## Functies

- **Overzicht** — status in één oogopslag: aantal producten, wat onder het
  minimum zit, openstaande bestellingen, recente boekingen.
- **Producten** — assortiment beheren: naam, categorie, eenheid, huidige
  voorraad, minimumvoorraad, standaard bestelhoeveelheid. Weergegeven per
  (inklapbare) categorie. Optioneel per product: automatisch op inactief
  zodra de voorraad op 0 komt.
- **Verbruiksvoorwerpen** — losse lijst voor dingen zonder eigen voorraad
  (bijv. bakjes): alleen een naam om een schaplabel voor te printen en
  desgewenst als tekstmelding op de bestellijst te zetten.
- **In/uit boeken** — voorraad bijwerken bij levering of verkoop/verbruik,
  met naam van de boeker en optionele opmerking. Alles wordt gelogd.
- **Bestellijst** — automatisch gegenereerde lijst van producten onder het
  minimum. Selecteer wat je bestelt → bestelling wordt aangemaakt. Zodra de
  levering binnen is, open je de bestelling en boek je de ontvangen
  aantallen in; de voorraad wordt dan automatisch bijgewerkt. Ook te
  downloaden als PDF.
- **Voorraad tellen** — vul periodiek de werkelijk getelde voorraad in per
  product. Het verschil met de geregistreerde voorraad (rekening houdend met
  tussentijdse leveringen) wordt automatisch verwerkt: minder geteld =
  verkocht, meer geteld = correctie. Elke telling sluit een periode af en
  genereert een verkooprapport (PDF) met aantallen en omzet per product.
- **Geschiedenis** — volledig log van alle boekingen, filterbaar per product.
- **Rechten per sectie** — naast de rol beheerder/vrijwilliger is per account
  in te stellen bij welke secties (Voorraad, Kassa, Keuken, Stemmen) iemand
  mag; beheerders hebben altijd overal toegang.
- **Schaplabels & scannen** — printbare schaplabels (A4, om te knippen) met
  logo, foto, minimumvoorraad en een QR-code, per product of in bulk. Die
  QR-code is met elke telefooncamera te scannen (ook zonder account) en
  opent een keuzescherm: naar de productpagina, of direct melden voor de
  bestellijst. De handterminal-weergave heeft ook een ingebouwde scanner.
  De bestellijst toont zulke meldingen (en handmatige meldingen vanuit
  Verbruiksvoorwerpen) in een aparte sectie, met een teller en een
  afhandelen-knop.
- **Offline-bestendig boeken en tellen** — een boeking die niet weg kan door
  slecht bereik wordt lokaal bewaard en alsnog verstuurd zodra er weer
  verbinding is; de looplijst probeert een mislukte stap vanzelf opnieuw
  zodra het bereik terugkomt.

## Lokaal draaien

Vereist Python 3.9+. Gebruik bij voorkeur **Python 3.13**: dat is de versie
waarop de site op PythonAnywhere draait, dus wat lokaal werkt, werkt daar ook.
`bash scripts/maak_venv.sh` maakt een venv met 3.13 en installeert alles
(installeer Python 3.13 eerst, bijvoorbeeld met `brew install python@3.13`).

```bash
cd "Voorraadbeheer"
python3.13 -m venv venv   # of: bash scripts/maak_venv.sh
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

De app draait dan op [http://localhost:5050](http://localhost:5050). Meerdere
mensen op hetzelfde wifi-netwerk kunnen ook naar `http://<jouw-ip>:5050`
zodat ze tegelijk kunnen boeken vanaf hun eigen telefoon.

De database (`voorraad.db`) wordt automatisch aangemaakt bij de eerste start,
inclusief een paar voorbeeldproducten om mee te beginnen. Pas die gerust aan
of verwijder ze via de Producten-pagina.

## Tests draaien

```bash
pip install -r requirements-dev.txt
pytest
```

De tests draaien (in ongeveer 40 seconden) tegen een tijdelijke, lege database
per test (nooit tegen `voorraad.db`) en dekken de kernberekeningen: kassa-tellingen (concept →
afsluiten → heropenen), voorraadmutaties bij het tellen, inloggen/CSRF en de
brute-force-blokkade.

## Live zetten

De site draait op PythonAnywhere. Met 1 commando zet je de nieuwste code live:

```bash
venv/bin/python scripts/zet_live.py
```

Dat controleert dat alles gecommit is, draait ruff en de tests, pusht naar GitHub, laat de server
de nieuwe code ophalen en herstarten, en wacht tot `/status` de nieuwe versie laat zien.

Eenmalig instellen: `venv/bin/python scripts/zet_live.py --maak-geheim` maakt een geheim op jouw computer
aan en toont de ene regel die je in een Bash-console op PythonAnywhere plakt (hij zet het geheim in
`uitrol_geheim.txt`). Zonder dat bestand op de server is het endpoint `POST /uitrollen` uitgeschakeld.
Het endpoint doet alleen `git pull --ff-only`, installeert zo nodig de vastgezette pakketten (zie
hieronder) en herstart de web-app; zie `uitrollen.py`. Lukt het installeren niet, dan zet de server de
vorige versie terug en blijft alles zoals het was.

Bij elke push draait GitHub Actions (`.github/workflows/tests.yml`) ruff en alle tests.

## Pakketten

`requirements.txt` bevat de minimumversies die wij kiezen. `requirements-vast.txt` bevat de **exacte**
versies van alles (ook Werkzeug, Jinja2, ...), en is wat de tests, de CI en de server installeren. Zo
draait overal hetzelfde: vroeger stond op de server een oudere Pillow dan waar de tests op liepen.

- Een minimum verhogen (of Dependabot doet dat): pas `requirements.txt` aan en draai daarna
  `bash scripts/leg_pakketten_vast.sh` om `requirements-vast.txt` te vernieuwen.
- `tests/test_pakketten.py` controleert dat die twee bij elkaar passen, en dat de CI op precies de
  vastgezette versies draait.
- Live zetten installeert de vastgezette pakketten op de server zodra dat bestand verandert.

## Onderhoud

De dagelijkse taak op PythonAnywhere is `python3 backup.py`. Die maakt en controleert de back-up, mailt
een kopie, zet eens per maand een back-up terug in een wegwerp-database (herstelcontrole) en ruimt daarna
oude gegevens op (zie `onderhoud.py`: paginabezoeken en logboek na 2 jaar, inlogtellers na 30 dagen).

## Straks online hosten

Omdat dit een normale Flask-app met een SQLite-bestand is, kun je hem op veel
plekken hosten zonder de code aan te passen:

- **Render / Railway / Fly.io** — koppel de repo, zet `gunicorn app:app` als
  startcommando (voeg `gunicorn` toe aan `requirements.txt`).
- **PythonAnywhere** — eenvoudig te draaien voor kleine Flask-apps, gratis
  tier beschikbaar.
- **Eigen VPS** — draai achter `gunicorn` + `nginx`.

Let op: bij hosting met meerdere gelijktijdige gebruikers is SQLite prima
voor het gebruik van een kantine (paar boekingen per minuut), maar zorg dat
`voorraad.db` op persistente opslag staat (niet iets dat bij elke deploy
gewist wordt).

## Projectstructuur

```
app.py          Flask-app: hooks (inloggen, CSRF, rechten), context en het koppelen van alle routes
rechten.py      Welk endpoint bij welke sectie hoort, en wat alleen voor beheerders is
navigatie.py    De zijbalk (menu) en het menu van de handterminal
database/       Verbinding, schema toepassen, eerste account; migraties.py en seed.py
schema.sql      Tabellen (producten, tellingen, kassa/kluis, logboek, ...)
pdf/            PDF-opmaak per onderwerp (voorraad, kas, verkoop, labels, uitdraai, seizoen, logboek)
helpers/        Gedeelde hulpfuncties, per onderwerp (tijd, kas, producten, ...)
club_van_20/    Rekenregels van de Club van 20 (seizoenen, administratie, scherm, import)
routes/         De pagina's, per onderdeel; grote onderdelen zijn een map
                (producten/, tellen/, kiosk/, club_van_20/)
voorspelling.py Prognose en omzetverdeling per dag
seizoensrapport.py, bardienstrapport.py   Omzet per seizoen en per bardienst
backup.py       Dagelijkse taak: back-up, herstelcontrole, opruimen (onderhoud.py)
uitrollen.py    Het beveiligde "live zetten"-endpoint (scripts/zet_live.py is de andere kant)
wijzigingen.py  Versie-logje voor de Help-pagina
templates/      Pagina's (Jinja2)
static/         Stijl (CSS) en scripts
tests/          pytest-tests
```
