# CLAUDE.md

Instructies voor Claude Code in deze repository.

## Documentatie die in sync moet blijven met featurewijzigingen

Wanneer je een gebruikersgerichte functie toevoegt, wijzigt of verwijdert,
werk in dezelfde wijziging ook het volgende bij:

1. **[templates/tips.html](templates/tips.html)** — de "Tips & functies"-pagina
   (`/tips`, gelinkt vanuit de footer op elke pagina), bedoeld als overzicht
   voor eindgebruikers (de vrijwilligers). Voeg een bullet toe onder de
   juiste sectie, of pas een bestaande aan/verwijder 'm bij een wijziging of
   verwijdering. Zet 💡 vóór de naam voor functies die makkelijk over het
   hoofd worden gezien (niet voor de voor de hand liggende dingen). Schrijf
   kort, in gewoon Nederlands, gericht op wat de vrijwilliger ermee kan —
   niet op de implementatie.
2. **`WIJZIGINGEN`/`HUIDIGE_VERSIE` in [routes/dashboard.py](routes/dashboard.py)**
   — het handmatige versie-logje voor de Help-pagina (`/help`). Bump
   `HUIDIGE_VERSIE` (patch/minor — er is geen releases/tags-systeem) en voeg
   een nieuw item toe aan `WIJZIGINGEN` met datum en een korte,
   gebruikersgerichte omschrijving van wat er is veranderd.

Beide lijsten zijn handmatig bijgehouden, geen generator — dat gebeurt dus
niet vanzelf, alleen door het er zelf bij te doen zodra de code verandert.

Sla dit over bij pure refactors, bugfixes zonder zichtbaar gedragsverschil,
of interne/technische wijzigingen die een eindgebruiker niet raakt.
