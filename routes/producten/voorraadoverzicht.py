"""Voorraadoverzicht: waarde per categorie, tekorten en de PDF/CSV-export."""

from flask import Response, g, render_template

from database import get_db
from helpers import bereken_fust_verkopen, categorienamen_zonder_verkoopprijsplicht, csv_response
from pdf import voorraadoverzicht_pdf
from routes.producten.overzicht import render_voorraad_pda


def bereken_voorraadoverzicht(db):
    """Verzamelt alle cijfers voor het voorraadoverzicht -- gebruikt door
    zowel de webpagina als de PDF, zodat ze altijd hetzelfde tonen."""
    producten = db.execute("SELECT * FROM producten ORDER BY categorie, naam").fetchall()
    niet_verplicht = categorienamen_zonder_verkoopprijsplicht(db)

    totale_waarde = sum(p["voorraad"] * p["verkoopprijs"] for p in producten)
    zonder_voorraad = [p for p in producten if p["actief"] and p["voorraad"] == 0]
    onder_minimum = [p for p in producten if p["actief"] and p["voorraad"] < p["min_voorraad"]]
    zonder_prijs = [
        p for p in producten
        if p["actief"] and p["verkoopprijs"] == 0 and p["categorie"] not in niet_verplicht
    ]
    inactief_met_voorraad = [p for p in producten if not p["actief"] and p["voorraad"] > 0]

    per_categorie = {}
    for p in producten:
        c = per_categorie.setdefault(p["categorie"], {"aantal": 0, "waarde": 0.0, "subcats": {}})
        c["aantal"] += 1
        c["waarde"] += p["voorraad"] * p["verkoopprijs"]
        sub = c["subcats"].setdefault(p["subcategorie"], {"aantal": 0, "waarde": 0.0})
        sub["aantal"] += 1
        sub["waarde"] += p["voorraad"] * p["verkoopprijs"]

    def _subcategorie_lijst(info):
        # Alleen tonen als er binnen deze categorie echt subcategorieën in
        # gebruik zijn -- anders levert elke categorie een nietszeggende
        # "Overig 100%"-regel op.
        if not any(naam is not None for naam in info["subcats"]):
            return []
        return sorted(
            [
                {
                    "naam": naam or "Overig",
                    "aantal": sub_info["aantal"],
                    "waarde": sub_info["waarde"],
                    "percentage": (sub_info["waarde"] / info["waarde"] * 100) if info["waarde"] else 0,
                }
                for naam, sub_info in info["subcats"].items()
            ],
            key=lambda x: x["waarde"],
            reverse=True,
        )

    categorie_lijst = sorted(
        [
            {
                "naam": naam,
                "aantal": info["aantal"],
                "waarde": info["waarde"],
                "percentage": (info["waarde"] / totale_waarde * 100) if totale_waarde else 0,
                "subcategorieen": _subcategorie_lijst(info),
            }
            for naam, info in per_categorie.items()
        ],
        key=lambda x: x["waarde"],
        reverse=True,
    )

    top_waarde = sorted(
        producten, key=lambda p: p["voorraad"] * p["verkoopprijs"], reverse=True
    )[:10]

    laatste_tellingen = db.execute(
        """SELECT tr.product_id, MAX(t.datum) AS laatste_datum
           FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
           GROUP BY tr.product_id"""
    ).fetchall()
    laatste_per_product = {r["product_id"]: r["laatste_datum"] for r in laatste_tellingen}
    nooit_geteld = [p for p in producten if p["actief"] and p["id"] not in laatste_per_product]
    langst_niet_geteld = sorted(
        (
            {"product": p, "laatste_datum": laatste_per_product[p["id"]]}
            for p in producten
            if p["actief"] and p["id"] in laatste_per_product
        ),
        key=lambda x: x["laatste_datum"],
    )[:5]

    # Gewone, volledige lijst van alle actieve producten -- de rest van
    # deze functie levert alleen samenvattingen/aggregaten, maar "wat heb
    # ik nu allemaal actief op voorraad" is de meest gestelde vraag op
    # deze pagina. Al gesorteerd op categorie/naam via de query hierboven.
    actieve_producten = [p for p in producten if p["actief"]]

    # Voor het filterbare/sorteerbare "hoofdstuk" onderaan: alle
    # categorieën/subcategorieën die daadwerkelijk in gebruik zijn (niet
    # de volledige categorieen-tabel, die kan ook nooit-gebruikte namen
    # bevatten) -- dat wordt daar de vinkjeslijst.
    alle_categorieen_lijst = sorted({p["categorie"] for p in producten})
    alle_subcategorieen_lijst = sorted({p["subcategorie"] for p in producten if p["subcategorie"]})
    heeft_producten_zonder_subcategorie = any(p["subcategorie"] is None for p in producten)

    # Fusten hebben geen eigen tabel -- gewoon producten met
    # glazen_per_fust > 0, hier meegenomen i.p.v. op een eigen pagina
    # (zie routes/fusten.py, die alleen nog doorverwijst hierheen).
    fust_producten = [p for p in producten if p["glazen_per_fust"] > 0]

    return {
        "producten": producten,
        "actieve_producten": actieve_producten,
        "alle_categorieen_lijst": alle_categorieen_lijst,
        "alle_subcategorieen_lijst": alle_subcategorieen_lijst,
        "heeft_producten_zonder_subcategorie": heeft_producten_zonder_subcategorie,
        "totale_waarde": totale_waarde,
        "aantal_producten": len(producten),
        "aantal_categorieen": len(per_categorie),
        "zonder_voorraad": zonder_voorraad,
        "onder_minimum": onder_minimum,
        "zonder_prijs": zonder_prijs,
        "inactief_met_voorraad": inactief_met_voorraad,
        "nooit_geteld": nooit_geteld,
        "categorie_lijst": categorie_lijst,
        "top_waarde": top_waarde,
        "langst_niet_geteld": langst_niet_geteld,
        "fust_producten": fust_producten,
        "fust_verkopen": bereken_fust_verkopen(db) if fust_producten else None,
    }


def register_routes(app):
    @app.route("/voorraadoverzicht")
    def voorraadoverzicht():
        if g.get("weergave_modus") == "pda":
            return render_voorraad_pda()
        db = get_db()
        return render_template(
            "voorraadoverzicht.html", **bereken_voorraadoverzicht(db)
        )

    @app.route("/voorraadoverzicht/pdf")
    def voorraadoverzicht_pdf_route():
        db = get_db()
        gegevens = bereken_voorraadoverzicht(db)
        pdf_bytes = voorraadoverzicht_pdf(gegevens)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=voorraadoverzicht.pdf"},
        )

    @app.route("/voorraadoverzicht/csv")
    def voorraadoverzicht_csv_route():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, subcategorie, naam"
        ).fetchall()
        rijen = [
            (
                p["artikelcode"] or "",
                p["naam"],
                p["categorie"],
                p["subcategorie"] or "",
                p["voorraad"],
                p["eenheid"],
                p["min_voorraad"],
                f"{p['verkoopprijs']:.2f}".replace(".", ","),
                f"{p['voorraad'] * p['verkoopprijs']:.2f}".replace(".", ","),
                "Ja" if p["actief"] else "Nee",
            )
            for p in producten
        ]
        return csv_response(
            "voorraadoverzicht.csv",
            ["Artikelcode", "Naam", "Categorie", "Subcategorie", "Voorraad", "Eenheid",
             "Minimum", "Verkoopprijs", "Waarde", "Actief"],
            rijen,
        )
