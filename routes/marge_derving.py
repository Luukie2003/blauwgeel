"""Rapporten: het marge-overzicht en de derving (wat er zonder te verkopen uit de voorraad verdwijnt)."""

from flask import flash, redirect, render_template, request, url_for

from database import get_db
from derving import DERVING_REDENEN, bereken_derving
from helpers.tijd import vandaag_amsterdam
from niet_lopers import WEKEN_KEUZES as NIET_LOPERS_WEKEN, bereken_niet_lopers, kies_weken as kies_niet_lopers_weken
from marge import (
    VERLIES_GLAZEN,
    WEKEN_KEUZES,
    bereken_marge,
    bereken_tap,
    bewaar_doelmarge,
    kies_weken,
    lees_doelmarge,
    prijsadvies,
)


def register_routes(app):
    @app.route("/rapporten/marge")
    def marge_rapport():
        db = get_db()
        weken = kies_weken(request.args.get("weken"))
        doel = lees_doelmarge(db)
        rapport = bereken_marge(db, weken, vandaag_amsterdam())
        # Prijsadvies: wat de prijs moet zijn om op de doelmarge uit te komen (afgerond op 10 cent naar boven).
        advies = {p["id"]: a for p in rapport["laagste"] if (a := prijsadvies(p, doel))}
        voorstel = ",".join(f"{veld}:{prijs:.2f}" for veld, prijs in advies.values())
        return render_template(
            "marge_rapport.html",
            weken=weken,
            weken_keuzes=WEKEN_KEUZES,
            lage_marge=doel,
            rapport=rapport,
            advies=advies,
            alle_voorstellen=voorstel,
            tap=bereken_tap(db),
            verlies_glazen=VERLIES_GLAZEN,
        )

    @app.route("/rapporten/marge/doelmarge", methods=["POST"])
    def marge_doelmarge():
        try:
            bewaar_doelmarge(get_db(), int(request.form.get("doelmarge") or 0))
            flash("Doelmarge opgeslagen.", "success")
        except ValueError:
            flash("Vul de doelmarge in als heel getal, bijvoorbeeld 30.", "error")
        return redirect(url_for("marge_rapport", weken=request.form.get("weken") or None))

    @app.route("/rapporten/derving")
    def derving_rapport():
        weken = kies_weken(request.args.get("weken"))
        return render_template(
            "derving_rapport.html",
            weken=weken,
            weken_keuzes=WEKEN_KEUZES,
            redenen=DERVING_REDENEN,
            rapport=bereken_derving(get_db(), weken, vandaag_amsterdam()),
        )

    @app.route("/rapporten/niet-lopers")
    def niet_lopers_rapport():
        weken = kies_niet_lopers_weken(request.args.get("weken"))
        return render_template(
            "niet_lopers.html",
            weken=weken,
            weken_keuzes=NIET_LOPERS_WEKEN,
            uitkomst=bereken_niet_lopers(get_db(), weken, vandaag_amsterdam()),
        )
