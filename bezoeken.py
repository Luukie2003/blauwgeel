"""Wat een paginabezoek is, voor de gebruiksstatistieken: hoe lang het duurde, en of het van een mens kwam.

De inlogpagina werd in 90 dagen 749 keer bekeken bij 4 accounts. Om te zien waar dat vandaan komt, krijgt een bezoek
een soort: 'bot' (een zoekmachine of ander programma, telt niet mee in de cijfers), 'doorverwezen' (iemand opende een
pagina zonder ingelogd te zijn, bijvoorbeeld omdat de sessie op een tablet verlopen was) of 'direct'."""

import re

TRAAG_MS = 3000  # langzamer dan dit wordt ook bewaard als het geen paginabezoek is (zie trage_verzoeken)

_BOT = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|curl|wget|python-requests|httpx|go-http|java/|headless|"
    r"monitor|uptime|scan",
    re.IGNORECASE,
)


def is_bot(user_agent):
    """True voor een zoekmachine, linkvoorbeeld of ander programma (geen mens met een browser)."""
    return not user_agent or bool(_BOT.search(user_agent))


def soort_bezoek(endpoint, user_agent, volgende=None):
    """'bot', 'doorverwezen' (alleen bij de inlogpagina, met ?next=) of 'direct' (de inlogpagina zelf); anders None."""
    if is_bot(user_agent):
        return "bot"
    if endpoint == "login":
        return "doorverwezen" if volgende else "direct"
    return None
