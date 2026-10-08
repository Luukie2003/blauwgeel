import re

from flask import Response, flash, redirect, render_template, request, session, url_for

from club_van_20 import MAANDNAMEN, normaliseer_seizoen, seizoen_van_datum, verschuif_seizoen
from database import get_db
from helpers import csv_response, now_str, vandaag_amsterdam
from pdf import seizoensrapport_pdf
from seizoensrapport import MAANDEN_IN_SEIZOEN, bereken_seizoensrapport, lees_historie

MAX_MAANDOMZET = 1_000_000
AANTAL_KEUZE_SEIZOENEN = 6


def lees_bedrag(tekst):
    """"1.234,56", "1234,5", "1234.56" of "€ 900" -> float; leeg -> None; ongeldig -> ValueError.
    Met een komma is het Nederlandse notatie (de punt is dan een duizendtal)."""
    tekst = (tekst or "").replace("€", "").replace(" ", "").strip()
    if not tekst:
        return None
    if "," in tekst:
        tekst = tekst.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", tekst):
        raise ValueError(tekst)
    bedrag = float(tekst)
    if bedrag > MAX_MAANDOMZET:
        raise ValueError(tekst)
    return bedrag


def _euro_csv(bedrag):
    return f"{bedrag:.2f}".replace(".", ",")


def register_routes(app):

    @app.route("/rapporten/seizoenen")
    def seizoensrapport():
        return render_template("seizoensrapport.html", rapport=bereken_seizoensrapport(get_db()))

    @app.route("/rapporten/seizoenen/invullen", methods=["GET", "POST"])
    def seizoensrapport_historie():
        """Maandtotalen van eerdere seizoenen invullen (alleen beheerders), voor de tijd vóór de eerste
        telling. Zie seizoensrapport.py voor hoe ze worden gebruikt."""
        db = get_db()
        huidig = seizoen_van_datum(vandaag_amsterdam())
        keuzes = [verschuif_seizoen(huidig, -i) for i in range(AANTAL_KEUZE_SEIZOENEN)]
        seizoen = normaliseer_seizoen(request.values.get("seizoen", "")) or verschuif_seizoen(huidig, -1)
        if seizoen not in keuzes:
            keuzes.append(seizoen)
            keuzes.sort(reverse=True)

        if request.method == "POST":
            nieuw, fouten = {}, []
            for maand in MAANDEN_IN_SEIZOEN:
                try:
                    nieuw[maand] = lees_bedrag(request.form.get(f"maand_{maand}", ""))
                except ValueError:
                    fouten.append(MAANDNAMEN[maand - 1])
            if fouten:
                flash("Dit is geen geldig bedrag: " + ", ".join(fouten) + ". Gebruik cijfers met een komma voor de centen, bijvoorbeeld 1234,50.", "error")
            else:
                aantal = 0
                for maand, bedrag in nieuw.items():
                    if bedrag:
                        db.execute(
                            """INSERT INTO omzet_historie (seizoen, maand, omzet, ingevoerd_door, ingevoerd_op)
                               VALUES (?, ?, ?, ?, ?)
                               ON CONFLICT(seizoen, maand) DO UPDATE SET
                                   omzet = excluded.omzet, ingevoerd_door = excluded.ingevoerd_door,
                                   ingevoerd_op = excluded.ingevoerd_op""",
                            (seizoen, maand, bedrag, session.get("gebruiker_naam"), now_str()),
                        )
                        aantal += 1
                    else:
                        db.execute("DELETE FROM omzet_historie WHERE seizoen = ? AND maand = ?", (seizoen, maand))
                db.commit()
                flash(f"Omzet van seizoen {seizoen} opgeslagen ({aantal} {'maand' if aantal == 1 else 'maanden'} ingevuld).", "success")
            return redirect(url_for("seizoensrapport_historie", seizoen=seizoen))

        historie = lees_historie(db)
        rapport = bereken_seizoensrapport(db)
        uit_tellingen = {}
        if rapport:
            rec = next((r for r in rapport["seizoenen"] if r["seizoen"] == seizoen), None)
            if rec:
                uit_tellingen = rec["maanden_tellingen"]
        return render_template(
            "seizoen_invullen.html",
            seizoen=seizoen,
            keuzes=keuzes,
            maanden=[
                {
                    "nummer": m,
                    "naam": MAANDNAMEN[m - 1].capitalize(),
                    "waarde": f"{historie[(seizoen, m)]:.2f}".replace(".", ",") if (seizoen, m) in historie else "",
                    "uit_tellingen": uit_tellingen.get(m, 0.0),
                }
                for m in MAANDEN_IN_SEIZOEN
            ],
            seizoenen_met_gegevens=sorted({s for s, _m in historie}, reverse=True),
        )

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
