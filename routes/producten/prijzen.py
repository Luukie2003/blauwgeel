"""Alle verkoopprijzen in één keer nalopen en aanpassen."""

import time
from datetime import date, timedelta

from flask import flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import categorienamen_zonder_verkoopprijsplicht, now_str
from helpers.tijd import vandaag_amsterdam
from prijzen import (
    SOORT_GLAS,
    SOORT_OPTIE,
    SOORT_VERKOOPPRIJS,
    geplande_wijzigingen,
    pas_geplande_prijzen_toe,
    plan_prijs,
)

# Hoe vaak (in seconden) er hooguit wordt gekeken of er een geplande prijswijziging aan de beurt is.
CONTROLE_ELKE_SECONDEN = 60
_laatste_controle = {"tijd": 0.0}


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
    @app.before_request
    def geplande_prijzen_toepassen():
        """Elke minuut hooguit eenmaal kijken of er een geplande prijswijziging aan de beurt is; ook de tv-schermen
        (die elke paar seconden vragen of er iets veranderd is) zorgen daarvoor, dus de prijzen gaan op de dag zelf in."""
        if request.endpoint in (None, "static", "status_pagina", "service_worker", "favicon_ico"):
            return None
        nu = time.monotonic()
        if nu - _laatste_controle["tijd"] < CONTROLE_ELKE_SECONDEN:
            return None
        _laatste_controle["tijd"] = nu
        try:
            pas_geplande_prijzen_toe(get_db(), vandaag_amsterdam())
        except Exception as fout:  # de site mag er nooit door stukgaan
            print(f"[prijzen] geplande prijzen toepassen mislukt: {fout}")
        return None

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
            ingang = None  # leeg: nu doorvoeren
            ingang_tekst = (request.form.get("ingangsdatum") or "").strip()
            if ingang_tekst:
                try:
                    ingang = date.fromisoformat(ingang_tekst)
                except ValueError:
                    fouten.append(f"De ingangsdatum ('{ingang_tekst}') is geen geldige datum.")
            if ingang is not None and ingang <= vandaag_amsterdam():
                ingang = None  # vandaag of eerder: gewoon nu doorvoeren
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
            if not fouten and ingang is not None:
                for nieuw, pid in prijs_updates:
                    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, nieuw, ingang.isoformat(), naam)
                for nieuw, pid in glas_updates:
                    plan_prijs(db, SOORT_GLAS, pid, nieuw, ingang.isoformat(), naam)
                for nieuw, optie_id in optie_updates:
                    product_id = next(p["id"] for p in producten if any(o["id"] == optie_id for o in opties.get(p["id"], [])))
                    plan_prijs(db, SOORT_OPTIE, product_id, nieuw, ingang.isoformat(), naam, optie_id=optie_id)
                db.commit()
                aantal = len(prijs_updates) + len(glas_updates) + len(optie_updates)
                if aantal:
                    flash(
                        f"{aantal} {'prijs staat' if aantal == 1 else 'prijzen staan'} klaar en "
                        f"{'gaat' if aantal == 1 else 'gaan'} in op {ingang.strftime('%d-%m-%Y')}.",
                        "success",
                    )
                else:
                    flash("Geen prijzen gewijzigd: alles klopte al.", "success")
                return redirect(url_for("producten_prijzen"))
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

        gepland = geplande_wijzigingen(db)
        gepland_per_prijs = {}
        for g in gepland:
            gepland_per_prijs.setdefault((g["soort"], g["product_id"], g["optie_id"] or 0), []).append(g)
        return render_template(
            "producten_prijzen.html",
            producten=producten,
            opties=opties,
            gepland=gepland,
            gepland_per_prijs=gepland_per_prijs,
            morgen=(vandaag_amsterdam() + timedelta(days=1)).isoformat(),
            categorieen=sorted({p["categorie"] for p in producten}),
            niet_verplicht=set(categorienamen_zonder_verkoopprijsplicht(db)),
            fouten=fouten,
            ingevuld=ingevuld,
        )

    @app.route("/producten/prijzen/gepland/<int:gepland_id>/verwijderen", methods=["POST"])
    def prijs_gepland_verwijderen(gepland_id):
        db = get_db()
        cursor = db.execute("DELETE FROM prijs_wijzigingen_gepland WHERE id = ?", (gepland_id,))
        db.commit()
        flash("Geplande prijswijziging verwijderd." if cursor.rowcount else "Die geplande prijswijziging bestaat niet meer.", "success")
        return redirect(url_for("producten_prijzen"))
