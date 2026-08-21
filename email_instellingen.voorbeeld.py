"""Voorbeeldbestand voor e-mailinstellingen.

Kopieer dit bestand op de server naar `email_instellingen.py` (die naam
staat in .gitignore -- komt dus nooit in git terecht) en vul je eigen
gegevens in. Zonder dat bestand blijft mailen gewoon uitgeschakeld; de app
werkt dan verder normaal.

Op PythonAnywhere doe je dit in een Bash console:

    cd ~/Voorraadbeheer
    cp email_instellingen.voorbeeld.py email_instellingen.py
    nano email_instellingen.py   # vul je gegevens in, Ctrl+O opslaan, Ctrl+X sluiten

Daarna: Reload op het Web-tabblad.
"""

SMTP_HOST = "smtp.strato.de"
SMTP_POORT = 587
SMTP_GEBRUIKER = "voorraad@kantineblauwgeel.nl"
SMTP_WACHTWOORD = "vul-hier-het-mailbox-wachtwoord-in"
MAIL_NAAR = "iemand@voorbeeld.nl"
