"""De Prognose-pagina (Bestellen > Prognose): wat wordt er de komende dagen
verkocht, welke producten raken op en wat moet er besteld worden. De
rekenregels staan in voorspelling.py. Hier staat ook het instellen van de
verkoopdagen (standaard woensdag en zaterdag, met uitzonderingen per datum)."""

from datetime import date, timedelta

from flask import flash, redirect, render_template, request, url_for

from database import get_db
from helpers import bereken_komende_thuiswedstrijden
from voorspelling import (
    _WEEKDAG,
    lees_verkoopdagen,
    maak_prognose,
    wedstrijden_op_gesloten_dagen,
)

HORIZONNEN = (3, 7, 14)
UITZONDERINGEN_TERUG_DAGEN = 56  # zo ver terug staan uitzonderingen nog in het overzicht


def _verkoop_context(db):
    """Alles voor het blokje "Verkoopdagen" op de pagina."""
    weekdagen, uitzonderingen = lees_verkoopdagen(db)
    grens = (date.today() - timedelta(days=UITZONDERINGEN_TERUG_DAGEN)).isoformat()
    lijst = [
        {
            "datum": date.fromisoformat(r["datum"]),
            "open": bool(r["open"]),
            "opmerking": r["opmerking"],
            "standaard_open": date.fromisoformat(r["datum"]).weekday() in weekdagen,
        }
        for r in db.execute(
            "SELECT datum, open, opmerking FROM verkoop_uitzonderingen WHERE datum >= ? ORDER BY datum", (grens,)
        ).fetchall()
    ]
    return {
        "weekdagen": weekdagen,
        "dagnamen": [(i, naam) for i, naam in enumerate(_WEEKDAG)],
        "samenvatting": ", ".join(_WEEKDAG[i] for i in sorted(weekdagen)),
        "uitzonderingen": lijst,
        "onbeslist": wedstrijden_op_gesloten_dagen(db),
    }


def register_routes(app):
    def _horizon():
        dagen = request.args.get("dagen", 7, type=int)
        return dagen if dagen in HORIZONNEN else 7

    @app.route("/prognose")
    def prognose_pagina():
        """De pagina zelf: de instellingen en de thuiswedstrijden staan meteen klaar. De prognose komt uit het
        voorspelmodel en dat rekent op de server soms enkele seconden, dus die haalt de pagina na het laden apart op
        (zie prognose_resultaat)."""
        db = get_db()
        return render_template(
            "prognose.html",
            dagen=_horizon(),
            horizonnen=HORIZONNEN,
            categorie=request.args.get("categorie") or "",
            verkoop=_verkoop_context(db),
            thuiswedstrijden=bereken_komende_thuiswedstrijden(db, dagen=14, inclusief_afgelast=True),
        )

    @app.route("/prognose/resultaat")
    def prognose_resultaat():
        """Het rekenwerk van de Prognose-pagina (verwachte omzet, dag voor dag, producten, wat het systeem heeft
        geleerd), apart opgehaald. Krijgt dezelfde ?dagen= en ?categorie= als de pagina."""
        db = get_db()
        dagen = _horizon()
        prognose = maak_prognose(db, dagen=dagen)
        categorie = request.args.get("categorie") or ""
        if prognose["beschikbaar"]:
            categorieen = sorted({p["product"]["categorie"] for p in prognose["producten"]})
            if categorie in categorieen:
                prognose = dict(
                    prognose,
                    producten=[p for p in prognose["producten"] if p["product"]["categorie"] == categorie],
                )
            else:
                categorie = ""
        else:
            categorieen = []
        return render_template(
            "_prognose_resultaat.html",
            prognose=prognose,
            dagen=dagen,
            categorie=categorie,
            categorieen=categorieen,
        )

    @app.route("/voorspelling/opwarmen")
    def voorspelling_opwarmen():
        """Laat het voorspelmodel alvast rekenen (en bewaren), zodat Bestellijst, Prognose en Tellingen daarna meteen
        openen. Het overzicht roept dit op zodra het zelf klaar is. Geeft niets terug; mislukt het, dan merkt niemand
        er iets van (de pagina's rekenen het dan zelf wel)."""
        try:
            maak_prognose(get_db(), dagen=7)
        except Exception as fout:
            print(f"[voorspelling] voorverwarmen mislukt: {fout}")
        return "", 204

    @app.route("/prognose/verkoopdagen", methods=["POST"])
    def prognose_verkoopdagen():
        """De vaste weekdagen waarop verkocht wordt."""
        gekozen = sorted(i for i in range(7) if request.form.get(f"dag_{i}"))
        if not gekozen:
            flash("Kies minstens één dag waarop je verkoopt.", "error")
            return redirect(url_for("prognose_pagina") + "#verkoopdagen")
        db = get_db()
        db.execute("UPDATE instellingen SET verkoopdagen = ? WHERE id = 1", (",".join(str(i) for i in gekozen),))
        db.commit()
        flash(
            "Verkoopdagen opgeslagen: " + ", ".join(_WEEKDAG[i] for i in gekozen) + ". De prognose rekent hier meteen mee.",
            "success",
        )
        return redirect(url_for("prognose_pagina") + "#verkoopdagen")

    @app.route("/prognose/uitzondering", methods=["POST"])
    def prognose_uitzondering_toevoegen():
        """Een losse datum waarop je wel of juist niet verkoopt, afwijkend van de vaste dagen."""
        try:
            datum = date.fromisoformat((request.form.get("datum") or "").strip())
        except ValueError:
            flash("Kies een geldige datum.", "error")
            return redirect(url_for("prognose_pagina") + "#verkoopdagen")
        open_ = 1 if request.form.get("status") == "open" else 0
        opmerking = (request.form.get("opmerking") or "").strip()[:80] or None
        db = get_db()
        db.execute(
            "INSERT OR REPLACE INTO verkoop_uitzonderingen (datum, open, opmerking) VALUES (?, ?, ?)",
            (datum.isoformat(), open_, opmerking),
        )
        db.commit()
        flash(
            f"{_WEEKDAG[datum.weekday()].capitalize()} {datum.day}-{datum.month}-{datum.year} staat als "
            f"{'open' if open_ else 'gesloten'}.",
            "success",
        )
        return redirect(url_for("prognose_pagina") + "#verkoopdagen")

    @app.route("/prognose/uitzondering/<datum>/verwijderen", methods=["POST"])
    def prognose_uitzondering_verwijderen(datum):
        try:
            iso = date.fromisoformat(datum).isoformat()
        except ValueError:
            return redirect(url_for("prognose_pagina") + "#verkoopdagen")
        db = get_db()
        db.execute("DELETE FROM verkoop_uitzonderingen WHERE datum = ?", (iso,))
        db.commit()
        flash("Uitzondering verwijderd: die dag volgt weer de vaste verkoopdagen.", "success")
        return redirect(url_for("prognose_pagina") + "#verkoopdagen")
