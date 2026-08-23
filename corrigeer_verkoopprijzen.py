"""Eenmalige correctie van verkoopprijzen die niet klopten met de kassa
(gecontroleerd tegen screenshots van het Sell-scherm, 23-08-2026):

- Liefmans Fruitesse stond op EUR 3,50, moet EUR 2,50 zijn.
- M&M Geel stond op EUR 14,00 (duidelijk een verkeerde invoer), moet EUR 1,00 zijn.
- Droge Worst had nog geen prijs (EUR 0,00); op de kassa heet dit "Halve
  metworst" a EUR 1,80 -- prijs overgenomen, naam bewust ongewijzigd gelaten.

Gebruik (vanuit de projectmap, met de virtualenv actief):

    python corrigeer_verkoopprijzen.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "voorraad.db"

# (artikelcode, nieuwe_verkoopprijs)
CORRECTIES = [
    ("040901", 2.50),  # Liefmans Fruitesse
    ("302110", 1.00),  # M&M Geel
    ("DROGE", 1.80),  # Droge Worst / kassa: "Halve metworst"
]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    aangepast = 0
    for artikelcode, nieuwe_prijs in CORRECTIES:
        product = conn.execute(
            "SELECT id, naam, verkoopprijs FROM producten WHERE artikelcode = ?",
            (artikelcode,),
        ).fetchone()
        if product is None:
            print(f"  Niet gevonden: {artikelcode}")
            continue
        print(
            f"  {product['naam']}: EUR {product['verkoopprijs']:.2f} -> EUR {nieuwe_prijs:.2f}"
        )
        conn.execute(
            "UPDATE producten SET verkoopprijs = ? WHERE id = ?",
            (nieuwe_prijs, product["id"]),
        )
        aangepast += 1

    conn.commit()
    conn.close()
    print(f"\nKlaar: {aangepast} verkoopprijs/prijzen gecorrigeerd.")


if __name__ == "__main__":
    main()
