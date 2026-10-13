"""Niet-lopers: producten met voorraad die al weken niet verkocht zijn, en hoeveel geld daarin vastzit.

Kijkt naar de gewone tellingen in de gekozen periode. Een product dat in die periode wel is geteld maar nooit minder
was dan de keer ervoor, verkoopt niet. Is het in de periode helemaal niet geteld, dan valt er niets over te zeggen en
staat het apart. De keuken (eigen telling) en producten met 'Niet tellen' doen niet mee."""

from datetime import timedelta

from helpers.producten import inkoop_per_stuk
from productkaart import TELLEN_VOORWAARDE

WEKEN_KEUZES = (4, 8, 13, 26)
STANDAARD_WEKEN = 8


def kies_weken(waarde):
    try:
        weken = int(waarde)
    except (TypeError, ValueError):
        return STANDAARD_WEKEN
    return weken if weken in WEKEN_KEUZES else STANDAARD_WEKEN


def bereken_niet_lopers(db, weken, vandaag):
    """{'niet_lopers', 'niet_geteld', 'waarde', 'vanaf'}: producten met voorraad zonder verkoop sinds 'weken' weken."""
    vanaf = (vandaag - timedelta(weeks=weken)).strftime("%Y-%m-%d 00:00")
    producten = db.execute(
        f"SELECT * FROM producten WHERE {TELLEN_VOORWAARDE} AND voorraad > 0 ORDER BY categorie, naam COLLATE NOCASE"
    ).fetchall()
    in_periode = {
        r["product_id"]: r
        for r in db.execute(
            """SELECT tr.product_id, COUNT(*) AS keer, SUM(tr.verkocht) AS verkocht
               FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
               WHERE t.datum >= ? GROUP BY tr.product_id""",
            (vanaf,),
        ).fetchall()
    }
    laatst_verkocht = {
        r["product_id"]: r["datum"]
        for r in db.execute(
            """SELECT tr.product_id, MAX(t.datum) AS datum
               FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
               WHERE tr.verkocht > 0 GROUP BY tr.product_id"""
        ).fetchall()
    }
    niet_lopers, niet_geteld = [], []
    for p in producten:
        regel = {
            "id": p["id"],
            "naam": p["naam"],
            "categorie": p["categorie"],
            "voorraad": p["voorraad"],
            "eenheid": p["eenheid"],
            "waarde": p["voorraad"] * inkoop_per_stuk(p),
            "heeft_inkoop": p["inkoopprijs"] > 0,
            "laatst_verkocht": laatst_verkocht.get(p["id"]),
        }
        geteld = in_periode.get(p["id"])
        if geteld is None:
            niet_geteld.append(regel)
        elif not geteld["verkocht"]:
            niet_lopers.append(regel)
    niet_lopers.sort(key=lambda r: (-r["waarde"], r["naam"].lower()))
    return {
        "vanaf": vanaf[:10],
        "niet_lopers": niet_lopers,
        "niet_geteld": niet_geteld,
        "waarde": sum(r["waarde"] for r in niet_lopers),
    }
