"""@-vermeldingen op het prikbord."""

import re

from markupsafe import Markup, escape

import mail


# Voor het @taggen van gebruikers in mededelingen/opmerkingen op het
# prikbord. Gebruikersnamen bevatten in de praktijk geen spaties, dus een
# eenvoudige woordmatch is genoeg.
TAG_PATROON = re.compile(r"@([A-Za-z0-9_.\-]+)")


def vind_getagde_gebruikers(db, tekst):
    """Zoekt @naam-vermeldingen in tekst en matcht ze tegen bestaande
    gebruikersnamen (hoofdletterongevoelig). Geeft de bijbehorende
    gebruikersrijen terug, zonder duplicaten."""
    namen = {m.group(1).lower() for m in TAG_PATROON.finditer(tekst)}
    if not namen:
        return []
    gebruikers = db.execute("SELECT * FROM gebruikers").fetchall()
    gezien = set()
    resultaat = []
    for g in gebruikers:
        if g["naam"].lower() in namen and g["id"] not in gezien:
            gezien.add(g["id"])
            resultaat.append(g)
    return resultaat


def stuur_tag_notificaties(db, tekst, wie_plaatste, omschrijving, link):
    """Mailt elke getagde gebruiker (met een e-mailadres, en niet de
    plaatser zelf) een korte melding. Een mislukte mail mag het plaatsen
    van de mededeling/opmerking nooit laten mislukken -- stuur_mail() vangt
    dat zelf al af."""
    for gebruiker in vind_getagde_gebruikers(db, tekst):
        if gebruiker["naam"] == wie_plaatste or not gebruiker["email"]:
            continue
        mail.stuur_mail(
            f"Je bent getagd op het prikbord: {omschrijving}",
            f"{wie_plaatste or 'Iemand'} tagde je op het prikbord:\n\n"
            f"\"{tekst}\"\n\nBekijk het op {link}",
            naar=gebruiker["email"],
        )


def met_tags_filter(tekst):
    """Jinja-filter: rendert @naam-vermeldingen als een opvallend label. De
    tekst wordt eerst zelf ge-escaped (het staat verder los van autoescape,
    dus dat gebeurt hier handmatig) en pas daarna vervangen we de
    @vermeldingen door veilige, vaste HTML."""
    escaped = str(escape(tekst or ""))

    def vervang(match):
        return f'<span class="tag-mention">@{escape(match.group(1))}</span>'

    return Markup(TAG_PATROON.sub(vervang, escaped))
