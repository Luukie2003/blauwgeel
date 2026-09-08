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
  voorraad, minimumvoorraad, standaard bestelhoeveelheid.
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
  logo, minimumvoorraad en een QR-code naar de productpagina, per product of
  in bulk. Die QR-code is met elke telefooncamera te scannen, en de
  handterminal-weergave heeft ook een ingebouwde scanner (Scannen-knop).
- **Offline-bestendig boeken en tellen** — een boeking die niet weg kan door
  slecht bereik wordt lokaal bewaard en alsnog verstuurd zodra er weer
  verbinding is; de looplijst probeert een mislukte stap vanzelf opnieuw
  zodra het bereik terugkomt.

## Lokaal draaien

Vereist Python 3.9+ (al aanwezig op macOS).

```bash
cd "Voorraadbeheer"
python3 -m venv venv
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

De tests draaien tegen een tijdelijke, lege database per test (nooit tegen
`voorraad.db`) en dekken de kernberekeningen: kassa-tellingen (concept →
afsluiten → heropenen), voorraadmutaties bij het tellen, inloggen/CSRF en de
brute-force-blokkade.

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
app.py          Flask-routes
database.py     Database-verbinding, init, migraties en voorbeelddata
pdf.py          PDF-opmaak (bestellijst en verkooprapporten)
schema.sql      Tabellen: producten, mutaties, bestellingen, bestelregels,
                tellingen, telling_regels
templates/      Pagina's (Jinja2)
static/         Stijl (CSS)
```
