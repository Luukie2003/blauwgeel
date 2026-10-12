"""Alle verkoopprijzen in één keer nalopen en aanpassen."""

from flask import flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import categorienamen_zonder_verkoopprijsplicht, now_str


def _lees_prijs(tekst):
    """'2,50', '2.5' of ' 3 ' -> 2.5, 2.5, 3.0; None als het geen prijs van 0 of meer is."""
    try:
        waarde = float((tekst or "").strip().replace(",", "."))
    except ValueError:
        return None
    return round(waarde, 2) if 0 <= waarde < 100000 else None


def _wijzigt(oud, nieuw):
    return abs(oud - nieuw) > 0.001


def register_routes(app):
    @app.route("/producten/prijzen", methods=["GET", "POST"])
    def producten_prijzen():
        """Eén tabel met de verkoopprijs van elk product (en van de prijsopties en de prijs per glas), die je in
        één keer opslaat. Elke gewijzigde verkoopprijs komt in de prijsgeschiedenis van het product, net als bij
        het bewerken van één product."""
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, actief DESC, naam COLLATE NOCASE"
        ).fetchall()
        opties = {}
        for optie in db.execute("SELECT * FROM product_prijsopties ORDER BY product_id, volgorde, id").fetchall():
            opties.setdefault(optie["product_id"], []).append(optie)

        fouten = []
        ingevuld = {}
        if request.method == "POST":
            ingevuld = request.form
            datum, naam, gebruiker_id = now_str(), session.get("gebruiker_naam"), session.get("gebruiker_id")
            prijs_updates, optie_updates, glas_updates, geschiedenis = [], [], [], []
            for p in producten:
                velden = [(f"prijs_{p['id']}", p["verkoopprijs"], "verkoopprijs")]
                if p["glazen_per_fust"]:
                    velden.append((f"glas_{p['id']}", p["prijs_per_glas"], "prijs per glas"))
                velden += [(f"optie_{o['id']}", o["prijs"], f"prijsoptie '{o['naam']}'") for o in opties.get(p["id"], [])]
                for veld, huidig, wat in velden:
                    if veld not in request.form:
                        continue  # niet in het formulier: niet aanraken
                    nieuw = _lees_prijs(request.form[veld])
                    if nieuw is None:
                        fouten.append(f"{p['naam']}: de {wat} ('{request.form[veld]}') is geen geldig bedrag.")
                    elif _wijzigt(huidig, nieuw):
                        if veld.startswith("prijs_"):
                            prijs_updates.append((nieuw, p["id"]))
                            geschiedenis.append((p["id"], "verkoopprijs", huidig, nieuw, datum, naam, gebruiker_id))
                        elif veld.startswith("glas_"):
                            glas_updates.append((nieuw, p["id"]))
                        else:
                            optie_updates.append((nieuw, int(veld.split("_")[1])))
            if not fouten:
                db.executemany("UPDATE producten SET verkoopprijs = ? WHERE id = ?", prijs_updates)
                db.executemany("UPDATE producten SET prijs_per_glas = ? WHERE id = ?", glas_updates)
                db.executemany("UPDATE product_prijsopties SET prijs = ? WHERE id = ?", optie_updates)
                db.executemany(
                    """INSERT INTO prijs_geschiedenis (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    geschiedenis,
                )
                db.commit()
                aantal = len(prijs_updates) + len(glas_updates) + len(optie_updates)
                if aantal:
                    flash(f"{aantal} {'prijs' if aantal == 1 else 'prijzen'} aangepast.", "success")
                else:
                    flash("Geen prijzen gewijzigd: alles klopte al.", "success")
                return redirect(url_for("producten_prijzen"))

        return render_template(
            "producten_prijzen.html",
            producten=producten,
            opties=opties,
            categorieen=sorted({p["categorie"] for p in producten}),
            niet_verplicht=set(categorienamen_zonder_verkoopprijsplicht(db)),
            fouten=fouten,
            ingevuld=ingevuld,
        )
