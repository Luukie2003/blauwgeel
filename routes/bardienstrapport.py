from datetime import date, timedelta

from flask import render_template, request

from bardienstrapport import bereken_bardienstrapport
from club_van_20 import seizoen_van_datum, verschuif_seizoen
from database import get_db
from helpers import vandaag_amsterdam
from seizoensrapport import seizoen_einde, seizoen_start


def _beschikbare_seizoenen(db, huidig):
    rij = db.execute("SELECT MIN(datum) AS eerste FROM kiosk_bardiensten").fetchone()
    if not rij or not rij["eerste"]:
        return [huidig]
    seizoenen = [huidig]
    seizoen = huidig
    while seizoen_start(seizoen) > date.fromisoformat(rij["eerste"]):
        seizoen = verschuif_seizoen(seizoen, -1)
        seizoenen.append(seizoen)
    return seizoenen


def register_routes(app):

    @app.route("/rapporten/bardiensten")
    def bardienstrapport():
        db = get_db()
        vandaag = vandaag_amsterdam()
        huidig = seizoen_van_datum(vandaag)
        seizoenen = _beschikbare_seizoenen(db, huidig)
        keuze = request.args.get("periode", huidig)
        if keuze == "90":
            vanaf, tot, titel = vandaag - timedelta(days=89), vandaag, "Laatste 90 dagen"
        else:
            if keuze not in seizoenen:
                keuze = huidig
            vanaf, tot, titel = seizoen_start(keuze), min(seizoen_einde(keuze), vandaag), f"Seizoen {keuze}"
        return render_template(
            "bardienstrapport.html",
            rapport=bereken_bardienstrapport(db, vanaf, tot),
            seizoenen=seizoenen,
            keuze=keuze,
            titel=titel,
        )
