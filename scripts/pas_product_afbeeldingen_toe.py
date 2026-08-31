"""Eenmalig hulpscript: koppelt de foto's uit product_afbeelding_mapping.json
aan de producten op basis van naam (i.p.v. id, want id's kunnen per
omgeving verschillen). Verondersteld dat de afbeeldingsbestanden al op hun
plek staan in static/product_afbeeldingen/ (via git). Geen onderdeel van de
applicatie zelf -- eenmalig te draaien na een `git pull` op een omgeving die
deze koppeling nog niet heeft.

Gebruik: python3 scripts/pas_product_afbeeldingen_toe.py
"""
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PAD = BASE_DIR / "voorraad.db"
MAPPING_PAD = Path(__file__).resolve().parent / "product_afbeelding_mapping.json"


def main():
    with open(MAPPING_PAD) as f:
        mapping = json.load(f)

    db = sqlite3.connect(DB_PAD)
    db.row_factory = sqlite3.Row

    # De kolom heette oorspronkelijk "Water"; is inmiddels hernoemd naar het
    # daadwerkelijke merk. Op een omgeving die deze migratie nog niet heeft
    # gehad, staat de rij nog onder de oude naam.
    if "Water" in [r["naam"] for r in db.execute("SELECT naam FROM producten")]:
        db.execute("UPDATE producten SET naam = 'Chaudfontaine' WHERE naam = 'Water'")

    bijgewerkt, niet_gevonden = [], []
    for naam, afbeelding in mapping.items():
        bestand = BASE_DIR / "static" / "product_afbeeldingen" / afbeelding
        if not bestand.exists():
            print(f"WAARSCHUWING: bestand ontbreekt op schijf: {afbeelding} ({naam})")
            continue
        cur = db.execute(
            "UPDATE producten SET afbeelding = ? WHERE naam = ? AND afbeelding IS NULL",
            (afbeelding, naam),
        )
        if cur.rowcount:
            bijgewerkt.append(naam)
        else:
            bestaand = db.execute(
                "SELECT afbeelding FROM producten WHERE naam = ?", (naam,)
            ).fetchone()
            if bestaand is None:
                niet_gevonden.append(naam)

    db.commit()
    db.close()
    print(f"{len(bijgewerkt)} product(en) bijgewerkt.")
    if niet_gevonden:
        print("Niet gevonden op naam (mogelijk hernoemd of verwijderd):")
        for naam in niet_gevonden:
            print(" -", naam)


if __name__ == "__main__":
    main()
