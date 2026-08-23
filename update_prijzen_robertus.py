"""Eenmalig update-script op basis van de prijslijst van Drankenhandel Fa. A.
Robertus en Zn. (23-08-2026). Werkt bestaande producten bij op hun HUIDIGE
artikelcode -- verandert dus artikelcode, besteleenheid, aantal per
besteleenheid en inkoopprijs (per besteleenheid). Namen en verkoopprijzen
blijven ongewijzigd.

Bevat alleen producten waarvoor de koppeling met de prijslijst eenduidig was.
Twijfelgevallen (AA Drink-variant, watermerk) staan er expres niet in -- die
moeten eerst met Luuk worden afgestemd.

Gebruik (vanuit de projectmap, met de virtualenv actief):

    python update_prijzen_robertus.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "voorraad.db"

# (huidige_artikelcode, nieuwe_artikelcode, besteleenheid, factor, inkoopprijs)
UPDATES = [
    ("HJFUST", "010203", None, 1, 63.28),
    ("HERTOG", "030201", "Krat", 24, 19.78),
    ("HERTOG0.0", "030217", "Krat", 24, 19.54),
    ("LIEFMANS", "040901", "Krat", 24, 28.39),
    ("GUINNESSBLK", "040991", "Krat", 24, 55.26),
    ("COCA", "100101", "Krat", 24, 14.64),
    ("COCAZERO", "100103", "Krat", 24, 14.64),
    ("RIV", "110001", "Krat", 28, 25.15),
    ("SINASBB", "270030", "Doos", 12, 27.07),
    ("BACARDI", "270050", "Doos", 12, 20.35),
    ("COLABB", "270011", "Doos", 12, 26.95),
    ("BOZUBLUE", "270016", "Doos", 12, 16.15),
    ("BOZUGREEN", "270015", "Doos", 12, 16.15),
    ("BOZUORANJE", "270014", "Doos", 12, 16.15),
    ("BOZUDARK", "270012", "Doos", 12, 16.15),
    ("CAPTAIN", "270045", "Doos", 12, 25.25),
    ("MARS", "302101", "Doos", 32, 20.44),
    ("SNICKER", "302103", "Doos", 32, 20.43),
    ("TWIX", "302106", "Doos", 25, 16.64),
    ("HARIBO", "303104", "Doos", 28, 18.40),
    ("DORITOS", "304011", "Doos", 20, 15.52),
    ("DORITOSZW", "304015", "Doos", 20, 15.52),
    ("CHOCO", "197001", "Krat", 24, 18.42),
    # Onderstaande zijn licht aangenomen (zie toelichting in het chatbericht):
    ("RADLER", "040303", "Krat", 24, 18.91),  # Amstel Radler 2.0-variant aangenomen
    ("POWERG", "181031", "Krat", 24, 23.71),  # golden mango = geel aangenomen
    ("POWERB", "181004", "Krat", 24, 23.71),  # mountain blast = blauw aangenomen
    ("FANTA", "102101", "Krat", 24, 14.64),  # orange (standaard) aangenomen
    ("LAYS", "304001", "Doos", 20, 12.87),  # groen = paprika aangenomen
    ("LAYSBLW", "304003", "Doos", 20, 12.87),  # blauw = naturel aangenomen
    ("MM", "302110", "Doos", 24, 17.24),  # enige M&M-optie in de lijst (pinda)
    # Afgestemd met Luuk:
    ("AA", "183001", "Krat", 24, 19.34),  # High Energy Orange + Iso Lemon: zelfde prijs, code van Orange gebruikt
    ("WATER", "111003", "Krat", 24, 14.90),  # Chaudfontaine
    # Geen directe SKU-match, wel de grondstof: Tray Berenburg wordt
    # kennelijk zelf samengesteld uit flessen Beerenburg. Fles-naar-tray
    # verhouding is onbekend, dus geen besteleenheid-omrekening toegepast --
    # dit is puur een referentieprijs per fles.
    ("TRAYBB", "203102", "Fles", 1, 14.60),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    bijgewerkt = 0
    niet_gevonden = []
    for oude_code, nieuwe_code, besteleenheid, factor, inkoopprijs in UPDATES:
        product = conn.execute(
            "SELECT id, naam FROM producten WHERE artikelcode = ?", (oude_code,)
        ).fetchone()
        if product is None:
            niet_gevonden.append(oude_code)
            continue
        conn.execute(
            """UPDATE producten
               SET artikelcode = ?, besteleenheid = ?, besteleenheid_factor = ?, inkoopprijs = ?
               WHERE id = ?""",
            (nieuwe_code, besteleenheid, factor, inkoopprijs, product["id"]),
        )
        print(f"  {oude_code} -> {nieuwe_code}  ({product['naam']})")
        bijgewerkt += 1

    conn.commit()
    conn.close()

    print(f"\nKlaar: {bijgewerkt} product(en) bijgewerkt.")
    if niet_gevonden:
        print(f"Niet gevonden (artikelcode bestond niet): {', '.join(niet_gevonden)}")


if __name__ == "__main__":
    main()
