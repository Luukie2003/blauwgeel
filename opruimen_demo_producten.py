"""Eenmalig opruimscript: verwijdert de originele demo-producten (Pilsbier,
Cola 33cl, Koffie, enzovoort) inclusief hun boekingen en tellingen.

Deze demo-producten zijn te herkennen doordat ze nooit een artikelcode
hebben gekregen -- elk echt geimporteerd product heeft er wel een. Als je
zelf later een product zonder artikelcode aanmaakt, raakt dit script daar
niet aan (het draait toch maar één keer, nu).

Gebruik (vanuit de projectmap, met de virtualenv actief):

    python opruimen_demo_producten.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "voorraad.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    demo_producten = conn.execute(
        "SELECT id, naam FROM producten WHERE artikelcode IS NULL"
    ).fetchall()

    if not demo_producten:
        print("Geen demo-producten (zonder artikelcode) gevonden -- niets te doen.")
        conn.close()
        return

    print("Wordt verwijderd, inclusief boekingen en tellingen:")
    for p in demo_producten:
        print(f"  - {p['naam']}")

    ids = [p["id"] for p in demo_producten]
    plaatshouders = ",".join("?" * len(ids))

    conn.execute(f"DELETE FROM mutaties WHERE product_id IN ({plaatshouders})", ids)
    conn.execute(f"DELETE FROM telling_regels WHERE product_id IN ({plaatshouders})", ids)
    conn.execute(f"DELETE FROM bestelregels WHERE product_id IN ({plaatshouders})", ids)
    conn.execute(f"DELETE FROM producten WHERE id IN ({plaatshouders})", ids)

    # Tellingen/bestellingen die nu helemaal leeg zijn (bevatten alleen
    # demo-producten) ruimen we ook op, zodat er geen lege spookrecords
    # achterblijven in de geschiedenis.
    conn.execute(
        """DELETE FROM tellingen
           WHERE id NOT IN (SELECT DISTINCT telling_id FROM telling_regels)"""
    )
    conn.execute(
        """DELETE FROM bestellingen
           WHERE id NOT IN (SELECT DISTINCT bestelling_id FROM bestelregels)"""
    )

    conn.commit()
    conn.close()
    print(f"\nKlaar: {len(demo_producten)} demo-product(en) en hun geschiedenis verwijderd.")


if __name__ == "__main__":
    main()
