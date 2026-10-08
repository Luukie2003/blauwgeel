from flask import Response, render_template

from helpers import csv_response
from database import get_db
from pdf import seizoensrapport_pdf
from seizoensrapport import bereken_seizoensrapport


def _euro_csv(bedrag):
    return f"{bedrag:.2f}".replace(".", ",")


def register_routes(app):

    @app.route("/rapporten/seizoenen")
    def seizoensrapport():
        return render_template("seizoensrapport.html", rapport=bereken_seizoensrapport(get_db()))

    @app.route("/rapporten/seizoenen/csv")
    def seizoensrapport_csv_route():
        rapport = bereken_seizoensrapport(get_db())
        rijen = []
        if rapport:
            for s in rapport["seizoenen"]:
                for maand, naam in rapport["maanden"]:
                    rijen.append((s["seizoen"], naam, _euro_csv(s["maanden"][maand])))
                rijen.append((s["seizoen"], "Totaal", _euro_csv(s["omzet"])))
        return csv_response("omzet-per-seizoen.csv", ["Seizoen", "Maand", "Omzet"], rijen)

    @app.route("/rapporten/seizoenen/pdf")
    def seizoensrapport_pdf_route():
        rapport = bereken_seizoensrapport(get_db())
        if rapport is None:
            return render_template("seizoensrapport.html", rapport=None)
        return Response(
            seizoensrapport_pdf(rapport),
            mimetype="application/pdf",
            headers={"Content-Disposition": "inline; filename=omzet-per-seizoen.pdf"},
        )
