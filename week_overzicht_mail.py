"""Verstuurt het wekelijkse omzet-overzicht per e-mail aan iedereen die dat
heeft aangevinkt bij Mijn voorkeuren. Bedoeld om elke ochtend te draaien via
een PythonAnywhere Scheduled Task -- het script doet zelf niets op andere
dagen dan maandag, dus dagelijks inplannen op een vroeg tijdstip is prima:

    python3 week_overzicht_mail.py

Draait binnen de Flask-appcontext, dus met de virtualenv actief.
"""

from datetime import datetime

import mail
from app import bereken_week_overzicht, create_app
from database import get_db

SITE_URL = "https://www.kantineblauwgeel.nl"


def bouw_mailtekst(overzicht):
    regels_top = "\n".join(
        f"  - {tv['product_naam']}: {tv['verkocht']} {tv['eenheid']} (€ {tv['omzet']:.2f})"
        for tv in overzicht["top_verkopers"]
    ) or "  (geen verkoop deze week)"

    regels_minimum = "\n".join(
        f"  - {p['naam']}: {p['voorraad']} / {p['min_voorraad']} {p['eenheid']}"
        for p in overzicht["onder_minimum"]
    ) or "  (niets onder het minimum)"

    verschil = ""
    if overzicht["verschil_percentage"] is not None:
        teken = "+" if overzicht["verschil_percentage"] >= 0 else ""
        verschil = f" ({teken}{overzicht['verschil_percentage']:.0f}% t.o.v. week ervoor)"

    return (
        f"Weekoverzicht {overzicht['week_van']:%d-%m-%Y} t/m {overzicht['week_tot']:%d-%m-%Y}\n\n"
        f"Omzet: € {overzicht['totale_omzet']:.2f}{verschil}\n\n"
        f"Top verkopers:\n{regels_top}\n\n"
        f"Onder minimumvoorraad:\n{regels_minimum}\n\n"
        f"Volledig overzicht: {SITE_URL}/week-overzicht"
    )


def main():
    if datetime.now().weekday() != 0:
        print("Geen maandag -- niets te doen.")
        return

    app = create_app()
    with app.app_context():
        db = get_db()
        overzicht = bereken_week_overzicht(db)
        tekst = bouw_mailtekst(overzicht)

        ontvangers = [
            r["email"]
            for r in db.execute(
                """SELECT email FROM gebruikers
                   WHERE mail_week_overzicht = 1 AND email IS NOT NULL AND email != ''"""
            ).fetchall()
        ]
        if not ontvangers:
            print("Niemand heeft het weekoverzicht per mail aangevinkt -- niets verstuurd.")
            return

        onderwerp = (
            f"Weekoverzicht {overzicht['week_van']:%d-%m} t/m {overzicht['week_tot']:%d-%m}"
        )
        for ontvanger in ontvangers:
            gelukt = mail.stuur_mail(onderwerp, tekst, naar=ontvanger)
            print(f"  {ontvanger}: {'verstuurd' if gelukt else 'mislukt'}")


if __name__ == "__main__":
    main()
