"""De productenlijst, de handterminal-voorraadlijst en het in bulk bewerken van producten."""

from flask import flash, jsonify, redirect, render_template, request, url_for

from database import get_db
from helpers import categorienamen_zonder_verkoopprijsplicht, is_ajax_verzoek


def render_producten_pagina(categorie_vergrendeld=None):
    """Rendert de Producten-pagina, optioneel vergrendeld op 1 categorie.
    Gebruikt door zowel /producten als /keuken (zie routes/keuken.py) -- zo
    delen ze dezelfde tabel/acties i.p.v. een eigen, bijna-identiek
    sjabloon. Bij een vergrendelde categorie worden ook de
    categorieen/subcategorieen-lijsten al op de database beperkt, niet pas
    in het sjabloon -- /keuken zit achter de sectie 'keuken' i.p.v.
    'voorraad', dus die gebruiker mag ook geen namen van andere categorieën
    te zien krijgen."""
    db = get_db()
    if categorie_vergrendeld:
        producten = db.execute(
            "SELECT * FROM producten WHERE categorie = ? ORDER BY actief DESC, subcategorie, naam",
            (categorie_vergrendeld,),
        ).fetchall()
        categorieen = []
        subcategorieen = db.execute(
            "SELECT categorie, naam FROM subcategorieen WHERE categorie = ? ORDER BY naam",
            (categorie_vergrendeld,),
        ).fetchall()
    else:
        # Categorie eerst (voor de groepering hieronder in het sjabloon),
        # daarna actief/subcategorie/naam zoals voorheen -- Jinja's
        # groupby-filter sorteert stabiel op alleen 'categorie', dus deze
        # volgorde blijft binnen elke groep behouden.
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, actief DESC, subcategorie, naam"
        ).fetchall()
        categorieen = db.execute("SELECT naam FROM categorieen ORDER BY naam").fetchall()
        subcategorieen = db.execute(
            "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
        ).fetchall()
    return render_template(
        "producten.html",
        producten=producten,
        categorieen=categorieen,
        subcategorieen=subcategorieen,
        niet_verplicht_categorieen=categorienamen_zonder_verkoopprijsplicht(db),
        categorie_vergrendeld=categorie_vergrendeld,
    )


def render_voorraad_pda(categorie=None, titel="Voorraad"):
    """De voorraadlijst voor de handterminal-weergave: per categorie een
    compacte lijst met wat er op voorraad is, met zoeken en een filter
    "alleen wat laag is". Optioneel beperkt tot 1 categorie (de
    keuken-pagina, zie routes/keuken.py -- die zit achter de sectie
    'keuken', dus dan komen er geen producten van andere categorieën
    in beeld)."""
    db = get_db()
    if categorie:
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 AND categorie = ? ORDER BY categorie, naam",
            (categorie,),
        ).fetchall()
    else:
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
    laag = [p for p in producten if p["voorraad"] < p["min_voorraad"]]
    leeg = [p for p in producten if p["voorraad"] <= 0]
    return render_template(
        "pda_voorraad.html",
        titel=titel,
        producten=producten,
        aantal_laag=len(laag),
        aantal_leeg=len(leeg),
        alleen_laag=request.args.get("alleen") == "laag",
        categorie_vergrendeld=categorie,
    )


def register_routes(app):
    # ---------- Producten ----------

    @app.route("/producten")
    def producten_lijst():
        return render_producten_pagina()

    @app.route("/api/tablet/producten")
    def api_tablet_producten():
        """Lichtgewicht JSON-lijst voor de kiosk-tablet-app (los project,
        zie android-apps/tablet) -- de bestaande /producten-pagina rendert
        een volledige HTML-pagina (filters, paginering, ...), dat wil de
        native app niet parsen. Schrijven gaat via de bestaande
        /producten/<id>/actief (zie product_actief_wisselen hierboven) en
        /kiosk/prijzen/product/<id>/uitverkocht (zie
        kiosk_product_uitverkocht_wisselen in routes/kiosk.py) -- dat laatste
        is een apart, kiosk-specifiek veld (kiosk_uitverkocht), los van de
        echte voorraad/actief-status."""
        db = get_db()
        producten = db.execute(
            """SELECT id, naam, categorie, actief, kiosk_uitverkocht FROM producten
               ORDER BY actief DESC, categorie, naam"""
        ).fetchall()
        return jsonify(
            {
                "producten": [
                    {
                        "id": p["id"],
                        "naam": p["naam"],
                        "categorie": p["categorie"],
                        "actief": bool(p["actief"]),
                        "uitverkocht": bool(p["kiosk_uitverkocht"]),
                    }
                    for p in producten
                ]
            }
        )

    @app.route("/producten/bulk-bewerken", methods=["GET", "POST"])
    def producten_bulk_bewerken():
        """Minimumvoorraad én besteleenheid in 1 scherm i.p.v. 2 losse
        bijna-identieke pagina's (zie de omleidingen bij
        producten_minimumvoorraad/producten_besteleenheid hieronder)."""
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            # Beide soorten wijzigingen verzamelen en pas daarna in 1 executemany
            # per soort wegschrijven, i.p.v. tot 2 losse UPDATEs per product in
            # de loop (kan aardig oplopen bij een grote productenlijst).
            min_updates = []
            eenheid_updates = []
            aangepast_ids = set()
            for p in producten:
                min_waarde = request.form.get(f"min_{p['id']}", "").strip()
                if min_waarde != "":
                    try:
                        nieuw_minimum = int(min_waarde)
                    except ValueError:
                        nieuw_minimum = None
                    if nieuw_minimum is not None and nieuw_minimum >= 0:
                        min_updates.append((nieuw_minimum, p["id"]))
                        aangepast_ids.add(p["id"])

                factor_waarde = request.form.get(f"factor_{p['id']}", "").strip()
                if factor_waarde != "":
                    try:
                        nieuwe_factor = int(factor_waarde)
                    except ValueError:
                        nieuwe_factor = None
                    if nieuwe_factor is not None and nieuwe_factor >= 1:
                        eenheid_waarde = request.form.get(f"eenheid_{p['id']}", "").strip()
                        eenheid_updates.append((eenheid_waarde or None, nieuwe_factor, p["id"]))
                        aangepast_ids.add(p["id"])

            if min_updates:
                db.executemany("UPDATE producten SET min_voorraad = ? WHERE id = ?", min_updates)
            if eenheid_updates:
                db.executemany(
                    "UPDATE producten SET besteleenheid = ?, besteleenheid_factor = ? WHERE id = ?",
                    eenheid_updates,
                )
            db.commit()
            flash(f"Bulkwijzigingen opgeslagen voor {len(aangepast_ids)} product(en).", "success")
            return redirect(url_for("producten_bulk_bewerken"))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY actief DESC, categorie, naam"
        ).fetchall()
        return render_template("producten_bulk_bewerken.html", producten=producten)

    @app.route("/producten/minimumvoorraad")
    def producten_minimumvoorraad():
        return redirect(url_for("producten_bulk_bewerken"))

    @app.route("/producten/besteleenheid")
    def producten_besteleenheid():
        return redirect(url_for("producten_bulk_bewerken"))

    @app.route("/producten/<int:product_id>/actief", methods=["POST"])
    def product_actief_wisselen(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Product niet gevonden."}), 404
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        nieuwe_status = 0 if product["actief"] else 1
        db.execute(
            "UPDATE producten SET actief = ? WHERE id = ?", (nieuwe_status, product_id)
        )
        db.commit()
        if is_ajax_verzoek():
            melding = (
                f"'{product['naam']}' is actief. Komt bij de volgende paginalaad weer bovenaan te staan."
                if nieuwe_status
                else f"'{product['naam']}' is inactief. Zakt bij de volgende paginalaad naar onderen."
            )
            return jsonify({"ok": True, "actief": nieuwe_status, "melding": melding})
        return redirect(url_for("producten_lijst"))
