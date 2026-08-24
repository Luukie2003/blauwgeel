"""Voorbeeldbestand voor de teamagenda's (iCal-feeds, bijv. van Sportlink).

Kopieer dit bestand op de server naar `agenda_instellingen.py` (die naam
staat in .gitignore -- komt dus nooit in git terecht) en vul de eigen
iCal-links in. De teamnaam wordt automatisch uit elke feed gehaald (de
X-WR-CALNAME), dus je hoeft alleen de links te plakken. Zonder dit bestand
blijft de agenda-koppeling gewoon uitgeschakeld; de rest van de app werkt
dan normaal door.

Op PythonAnywhere doe je dit in een Bash console:

    cd ~/Voorraadbeheer
    cp agenda_instellingen.voorbeeld.py agenda_instellingen.py
    nano agenda_instellingen.py   # vul de iCal-links in, Ctrl+O opslaan, Ctrl+X sluiten
"""

AGENDA_FEEDS = [
    {"url": "https://data.sportlink.com/ical-team?token=..."},
    {"url": "https://data.sportlink.com/ical-team?token=..."},
    {"url": "https://data.sportlink.com/ical-team?token=..."},
]
