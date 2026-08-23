"""Verstuurt e-mailmeldingen via SMTP. Werkt alleen als email_instellingen.py
bestaat (zie email_instellingen.voorbeeld.py) -- ontbreekt dat bestand, dan
wordt mailen stilzwijgend overgeslagen zodat de rest van de app gewoon blijft
werken (bijvoorbeeld lokaal tijdens ontwikkelen).
"""

import smtplib
from email.message import EmailMessage

try:
    import email_instellingen as instellingen

    MAIL_BESCHIKBAAR = True
except ImportError:
    instellingen = None
    MAIL_BESCHIKBAAR = False


def stuur_mail(onderwerp, tekst, naar=None, html=None):
    """Verstuurt een e-mail. Geeft True/False terug; gooit nooit een
    uitzondering -- een mislukte mail mag de rest van een boeking nooit
    laten mislukken.

    naar: ontvangersadres. Als dit leeg is (geen instelling opgeslagen in de
    app), valt de functie terug op MAIL_NAAR uit email_instellingen.py.

    html: optionele opgemaakte versie van het bericht. tekst blijft altijd
    meegestuurd als platte-tekst-fallback voor mailclients die geen HTML
    tonen."""
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

    try:
        with smtplib.SMTP(instellingen.SMTP_HOST, instellingen.SMTP_POORT, timeout=10) as server:
            server.starttls()
            server.login(instellingen.SMTP_GEBRUIKER, instellingen.SMTP_WACHTWOORD)
            server.send_message(bericht)
        return True
    except Exception as fout:
        print(f"[mail] Versturen mislukt: {fout}")
        return False
