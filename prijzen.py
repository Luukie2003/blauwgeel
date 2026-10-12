"""Prijswijzigingen die op een afgesproken datum ingaan, bijvoorbeeld aan het begin van het seizoen.

Je zet ze klaar bij Producten > Prijzen aanpassen met een ingangsdatum. Op die dag worden ze vanzelf doorgevoerd:
de prijs verandert (de tv en de prijslijst volgen), en bij een verkoopprijs komt er een regel in de prijsgeschiedenis.
Er draait geen apart taakje voor: elke paar minuten dat iemand de site of de tv gebruikt, wordt gekeken of er iets aan
de beurt is (zie routes/producten/prijzen.py)."""

from datetime import datetime

from helpers import now_str

SOORT_VERKOOPPRIJS = "verkoopprijs"
SOORT_GLAS = "prijs_per_glas"
SOORT_OPTIE = "prijsoptie"


def plan_prijs(db, soort, product_id, nieuwe_prijs, ingangsdatum, door, optie_id=None):
    """Zet een prijswijziging klaar voor 'ingangsdatum' (tekst JJJJ-MM-DD). Een eerdere gepland voor dezelfde prijs op
    dezelfde datum wordt vervangen."""
    db.execute(
        """DELETE FROM prijs_wijzigingen_gepland
           WHERE soort = ? AND product_id = ? AND COALESCE(optie_id, 0) = ? AND ingangsdatum = ?""",
        (soort, product_id, optie_id or 0, ingangsdatum),
    )
    db.execute(
        """INSERT INTO prijs_wijzigingen_gepland
           (soort, product_id, optie_id, nieuwe_prijs, ingangsdatum, aangemaakt_door, aangemaakt_op)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (soort, product_id, optie_id, nieuwe_prijs, ingangsdatum, door, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )


def _voer_door(db, rij):
    if rij["soort"] == SOORT_VERKOOPPRIJS:
        oud = db.execute("SELECT verkoopprijs FROM producten WHERE id = ?", (rij["product_id"],)).fetchone()
        if oud is None:
            return
        db.execute("UPDATE producten SET verkoopprijs = ? WHERE id = ?", (rij["nieuwe_prijs"], rij["product_id"]))
        if abs(oud["verkoopprijs"] - rij["nieuwe_prijs"]) > 0.001:
            db.execute(
                """INSERT INTO prijs_geschiedenis (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id)
                   VALUES (?, 'verkoopprijs', ?, ?, ?, ?, NULL)""",
                (rij["product_id"], oud["verkoopprijs"], rij["nieuwe_prijs"], now_str(),
                 f"gepland door {rij['aangemaakt_door'] or 'een beheerder'}"),
            )
    elif rij["soort"] == SOORT_GLAS:
        db.execute("UPDATE producten SET prijs_per_glas = ? WHERE id = ?", (rij["nieuwe_prijs"], rij["product_id"]))
    elif rij["soort"] == SOORT_OPTIE and rij["optie_id"]:
        db.execute(
            "UPDATE product_prijsopties SET prijs = ? WHERE id = ? AND product_id = ?",
            (rij["nieuwe_prijs"], rij["optie_id"], rij["product_id"]),
        )


def pas_geplande_prijzen_toe(db, vandaag):
    """Voert alle geplande prijswijzigingen door waarvan de ingangsdatum vandaag of eerder is (vandaag: een date).
    Geeft het aantal doorgevoerde wijzigingen. Veilig bij meerdere processen tegelijk: wie de rij als eerste
    verwijdert, voert hem door."""
    aantal = 0
    for rij in db.execute(
        "SELECT * FROM prijs_wijzigingen_gepland WHERE ingangsdatum <= ? ORDER BY ingangsdatum, id",
        (vandaag.isoformat(),),
    ).fetchall():
        if db.execute("DELETE FROM prijs_wijzigingen_gepland WHERE id = ?", (rij["id"],)).rowcount != 1:
            continue
        _voer_door(db, rij)
        aantal += 1
    db.commit()
    return aantal


def geplande_wijzigingen(db):
    """Alle klaarstaande wijzigingen, met de naam van het product (en de optie) en de huidige prijs erbij."""
    return db.execute(
        """SELECT g.*, p.naam AS product_naam, o.naam AS optie_naam,
                  CASE g.soort WHEN 'verkoopprijs' THEN p.verkoopprijs
                               WHEN 'prijs_per_glas' THEN p.prijs_per_glas
                               ELSE o.prijs END AS huidige_prijs
           FROM prijs_wijzigingen_gepland g
           JOIN producten p ON p.id = g.product_id
           LEFT JOIN product_prijsopties o ON o.id = g.optie_id
           ORDER BY g.ingangsdatum, p.naam COLLATE NOCASE, g.id"""
    ).fetchall()
