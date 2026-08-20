"""Eenmalig script om het productoverzicht in te laden of bij te werken.

Gebruik (vanuit de projectmap, met de virtualenv actief):

    python importeer_producten.py

Producten worden herkend op artikelcode: bestaat die al, dan worden naam,
categorie, eenheid, minimumvoorraad, verkoopprijs en actief-status
bijgewerkt (de huidige voorraad blijft ongemoeid). Bestaat de artikelcode
nog niet, dan wordt het product toegevoegd met voorraad 0. Er wordt nooit
iets verwijderd, dus dit script is veilig om opnieuw te draaien.
"""

import sqlite3
from pathlib import Path

from database import SCHEMA_PATH, SEED_PRODUCTEN, _migreer_kolommen

DB_PATH = Path(__file__).parent / "voorraad.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    _migreer_kolommen(conn)

    toegevoegd = 0
    bijgewerkt = 0

    for artikelcode, naam, categorie, eenheid, _voorraad, min_voorraad, bestel_hoeveelheid, verkoopprijs, actief in SEED_PRODUCTEN:
        bestaand = conn.execute(
            "SELECT id FROM producten WHERE artikelcode = ?", (artikelcode,)
        ).fetchone()
        if bestaand:
            conn.execute(
                """UPDATE producten
                   SET naam = ?, categorie = ?, eenheid = ?, min_voorraad = ?,
                       verkoopprijs = ?, actief = ?
                   WHERE artikelcode = ?""",
                (naam, categorie, eenheid, min_voorraad, verkoopprijs, actief, artikelcode),
            )
            bijgewerkt += 1
        else:
            conn.execute(
                """INSERT INTO producten
                   (artikelcode, naam, categorie, eenheid, voorraad, min_voorraad,
                    bestel_hoeveelheid, verkoopprijs, actief)
                   VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)""",
                (artikelcode, naam, categorie, eenheid, min_voorraad, bestel_hoeveelheid, verkoopprijs, actief),
            )
            toegevoegd += 1

    conn.commit()
    conn.close()
    print(f"Klaar: {toegevoegd} product(en) toegevoegd, {bijgewerkt} bijgewerkt.")


if __name__ == "__main__":
    main()
