"""Verstuurt e-mailmeldingen via SMTP. Werkt alleen als email_instellingen.py
bestaat (zie email_instellingen.voorbeeld.py) -- ontbreekt dat bestand, dan
wordt mailen stilzwijgend overgeslagen zodat de rest van de app gewoon blijft
werken (bijvoorbeeld lokaal tijdens ontwikkelen).
"""

import smtplib
import sqlite3
from email.message import EmailMessage
from pathlib import Path

try:
    import email_instellingen as instellingen

    MAIL_BESCHIKBAAR = True
except ImportError:
    instellingen = None
    MAIL_BESCHIKBAAR = False


def stuur_mail(onderwerp, tekst, naar=None, html=None, bijlage_pad=None):
    """Verstuurt een e-mail. Geeft True/False terug; gooit nooit een
    uitzondering -- een mislukte mail mag de rest van een boeking nooit
    laten mislukken.

    naar: ontvangersadres. Als dit leeg is (geen instelling opgeslagen in de
    app), valt de functie terug op MAIL_NAAR uit email_instellingen.py.

    html: optionele opgemaakte versie van het bericht. tekst blijft altijd
    meegestuurd als platte-tekst-fallback voor mailclients die geen HTML
    tonen.

    bijlage_pad: optioneel pad naar een bestand dat als bijlage wordt
    meegestuurd (bijv. een back-up-bestand)."""
    if not MAIL_BESCHIKBAAR:
        print(f"[mail] Overgeslagen (geen email_instellingen.py): {onderwerp}")
        return False

    ontvanger = naar or instellingen.MAIL_NAAR

    bericht = EmailMessage()
    bericht["Subject"] = onderwerp
    bericht["From"] = instellingen.SMTP_GEBRUIKER
    bericht["To"] = ontvanger
    bericht.set_content(tekst)
    if html:
        bericht.add_alternative(html, subtype="html")
    if bijlage_pad:
        bijlage_pad = Path(bijlage_pad)
        bericht.add_attachment(
            bijlage_pad.read_bytes(),
            maintype="application",
            subtype="octet-stream",
            filename=bijlage_pad.name,
        )

    try:
        with smtplib.SMTP(instellingen.SMTP_HOST, instellingen.SMTP_POORT, timeout=10) as server:
            server.starttls()
            server.login(instellingen.SMTP_GEBRUIKER, instellingen.SMTP_WACHTWOORD)
            server.send_message(bericht)
        return True
    except Exception as fout:
        print(f"[mail] Versturen mislukt: {fout}")
        return False


def systeembeheerder_adres(db=None, db_pad=None):
    """Het e-mailadres van de systeembeheerder: het account dat eigenaar is (gebruikers.eigenaar, één account; zie
    noodstop.py). Technische meldingen (serverfouten, back-ups, storingen) gaan alleen daarheen. Geef een open
    database (db) of het pad ernaar (db_pad, voor de losse scripts). None als dat account geen e-mailadres heeft of de
    database niet te lezen is: de aanroeper valt dan terug op zijn oude adres, zodat een melding nooit verdwijnt."""
    try:
        # Alleen lezen, en nooit per ongeluk een lege database aanmaken als het bestand er niet is.
        verbinding = db if db is not None else sqlite3.connect(f"{Path(db_pad).resolve().as_uri()}?mode=ro", uri=True)
        try:
            rij = verbinding.execute(
                """SELECT email FROM gebruikers WHERE eigenaar = 1 AND actief = 1 AND COALESCE(email, '') != ''
                   ORDER BY id LIMIT 1"""
            ).fetchone()
        finally:
            if db is None:
                verbinding.close()
        return rij[0] if rij else None
    except Exception:
        return None
