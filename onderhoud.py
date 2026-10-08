"""Opruimen van gegevens die niet eeuwig bewaard hoeven te blijven.

Draait elke dag mee met de back-uptaak (zie backup.py), en wel nadat de
back-up van die dag klaar is: wat hier wordt opgeruimd staat dus nog in de
back-ups van de 90 dagen ervoor. Gebruikt alleen de standaardbibliotheek,
zodat het ook buiten de virtualenv kan draaien.

De bewaartermijnen staan ook in de privacyverklaring (templates/privacy.html);
pas je ze hier aan, pas dan ook die tekst aan."""

import sqlite3
from datetime import datetime, timedelta

# (tabel, kolom met het tijdstip, bewaartermijn in dagen, extra voorwaarde)
BEWAARTERMIJNEN = [
    # Voor de gebruiksstatistieken -- zie de privacyverklaring ("2 jaar").
    ("paginabezoeken", "datum", 730, None),
    # Wie wat deed (Club > Logboek).
    ("logboek", "datum", 730, None),
    # Tellers van mislukte inlogpogingen. Een nog lopende blokkade blijft staan.
    ("login_pogingen", "laatste_poging", 30, "(geblokkeerd_tot IS NULL OR geblokkeerd_tot < :nu)"),
    ("tablet_code_pogingen", "laatste_poging", 30, "(geblokkeerd_tot IS NULL OR geblokkeerd_tot < :nu)"),
    # Teller voor het vooraf bekijken van het aanmeldformulier.
    ("club_van_20_voorbeeld_pogingen", "sinds", 30, None),
]

DATUM_FORMAAT = "%Y-%m-%d %H:%M"


def ruim_oude_gegevens(conn, nu=None):
    """Verwijdert alles dat de bewaartermijn voorbij is. Geeft {tabel: aantal
    verwijderde regels} terug. Een tabel die (nog) niet bestaat, wordt
    overgeslagen: een oudere database mag dit nooit laten mislukken."""
    nu = nu or datetime.now()
    verwijderd = {}
    for tabel, kolom, dagen, extra in BEWAARTERMIJNEN:
        grens = (nu - timedelta(days=dagen)).strftime(DATUM_FORMAAT)
        voorwaarde = f"{kolom} < :grens" + (f" AND {extra}" if extra else "")
        try:
            cursor = conn.execute(
                f"DELETE FROM {tabel} WHERE {voorwaarde}",
                {"grens": grens, "nu": nu.strftime(DATUM_FORMAAT)},
            )
        except sqlite3.OperationalError:
            continue
        verwijderd[tabel] = cursor.rowcount
    conn.commit()
    return verwijderd
