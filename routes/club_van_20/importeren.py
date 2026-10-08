"""Importeren en exporteren van de Club van 20-spreadsheet."""

from flask import flash, redirect, render_template, request, session, url_for

from club_van_20 import (
    BIJDRAGE_STATUS_LABELS,
    alle_seizoenen,
    bijdrage_status,
    huidig_seizoen,
    import_rij_overzicht,
    import_samenvatting,
    leden_met_bijdragen,
    parse_import,
    rijen_naar_csv,
    rijen_uit_xlsx,
    verlengingen_overzicht,
    voer_import_uit,
)
from database import get_db
from helpers import csv_response, vandaag_amsterdam
from routes.club_van_20.gedeeld import _instellingen


def register_routes(app):
    # ---------- Importeren / exporteren ----------

    @app.route("/club-van-20/importeren", methods=["GET", "POST"])
    def club_van_20_importeren():
        db = get_db()
        instellingen = _instellingen(db)
        tekst = ""
        voorbeeld = None
        if request.method == "POST":
            bestand = request.files.get("bestand")
            xlsx_fout = None
            if bestand and bestand.filename:
                ruw = bestand.read()
                if bestand.filename.lower().endswith((".xlsx", ".xlsm")):
                    # Excel-bestand: omzetten naar dezelfde tekst als een
                    # CSV-import, zodat voorbeeld en bevestigen identiek werken.
                    try:
                        tekst = rijen_naar_csv(rijen_uit_xlsx(ruw))
                    except ValueError as fout:
                        xlsx_fout = str(fout)
                else:
                    try:
                        tekst = ruw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        tekst = ruw.decode("latin-1")
            else:
                tekst = request.form.get("tekst", "")
            voorbeeld = parse_import(tekst, instellingen["club_van_20_bedrag"])
            if xlsx_fout:
                voorbeeld["fout"] = xlsx_fout
            if voorbeeld["fout"]:
                flash(voorbeeld["fout"], "error")
                voorbeeld = None
            else:
                # Het voorbeeld kent per lid een vinkje (zie het sjabloon): alleen de
                # aangevinkte leden gaan mee. Zonder 'kies_aanwezig' (een oud
                # formulier of een eigen aanroep) gaat de hele import door.
                alle_rijen = voorbeeld["rijen"]
                gekozen_rijen = alle_rijen
                if request.form.get("kies_aanwezig"):
                    gekozen = {int(i) for i in request.form.getlist("kies") if i.isdigit()}
                    gekozen_rijen = [r for i, r in enumerate(alle_rijen) if i in gekozen]
                if request.form.get("bevestig") and not gekozen_rijen:
                    flash("Je hebt geen leden aangevinkt, dus er is niets geïmporteerd.", "warning")
                elif request.form.get("bevestig"):
                    nieuw, bijgewerkt = voer_import_uit(
                        db,
                        gekozen_rijen,
                        gebruiker=session.get("gebruiker_naam"),
                        standaard_bedrag=instellingen["club_van_20_bedrag"],
                    )
                    db.commit()
                    overgeslagen = len(alle_rijen) - len(gekozen_rijen)
                    flash(
                        f"Import klaar: {nieuw} nieuwe leden, {bijgewerkt} bijgewerkt"
                        + (f", {overgeslagen} leden uit het bestand overgeslagen." if overgeslagen else "."),
                        "success",
                    )
                    return redirect(url_for("club_van_20_overzicht"))
            if voorbeeld is not None:
                bestaande = {
                    r["naam"].lower()
                    for r in db.execute("SELECT naam FROM club_van_20_leden").fetchall()
                }
                overzicht = import_rij_overzicht(db, voorbeeld["rijen"])
                for rij, wat in zip(voorbeeld["rijen"], overzicht):
                    rij["bestaat"] = rij["naam"].lower() in bestaande
                    rij["wat"] = wat
                voorbeeld["samenvatting"] = import_samenvatting(db, voorbeeld["rijen"])
                # Wie heeft er volgens het bestand dit seizoen betaald (verlengd)?
                verlengd_seizoen = huidig_seizoen() if huidig_seizoen() in voorbeeld["seizoenen"] else (
                    voorbeeld["seizoenen"][-1] if voorbeeld["seizoenen"] else None
                )
                voorbeeld["verlengd"] = (
                    verlengingen_overzicht(db, voorbeeld["rijen"], verlengd_seizoen) if verlengd_seizoen else None
                )
                for index, rij in enumerate(voorbeeld["rijen"]):
                    rij["verlengd"] = bool(voorbeeld["verlengd"]) and index in voorbeeld["verlengd"]["rijen"]
                voorbeeld["totalen"] = {
                    s: sum(
                        r["bijdragen"][s]["bedrag"]
                        for r in voorbeeld["rijen"]
                        if s in r["bijdragen"] and r["bijdragen"][s]["status"] == "betaald"
                    )
                    for s in voorbeeld["seizoenen"]
                }
        return render_template(
            "club_van_20_importeren.html", tekst=tekst, voorbeeld=voorbeeld, status_labels=BIJDRAGE_STATUS_LABELS
        )

    @app.route("/club-van-20/export.csv")
    def club_van_20_exporteren():
        db = get_db()
        seizoenen = alle_seizoenen(db)
        huidig = huidig_seizoen()
        kop = ["Voornaam", "Achternaam", "Team", "Naambordje", *seizoenen,
               f"Status {huidig}", "Betaald door", "Telefoon", "E-mail", "Notitie", "Actief"]
        rijen = []
        for lid in leden_met_bijdragen(db):
            bedragen = []
            for s in seizoenen:
                b = lid["bijdragen"].get(s)
                bedragen.append(f"{b['bedrag']:g}" if b and b["status"] == "betaald" else "")
            huidige = lid["bijdragen"].get(huidig) or {}
            rijen.append(
                [
                    lid.get("voornaam") or "",
                    lid.get("achternaam") or "",
                    lid.get("team") or "",
                    lid["naam"],
                    *bedragen,
                    BIJDRAGE_STATUS_LABELS[bijdrage_status(lid, huidig)],
                    huidige.get("betaald_door") or "",
                    lid.get("telefoon") or "",
                    lid.get("email") or "",
                    lid.get("notitie") or "",
                    "nee" if lid["status"] == "inactief" else "ja",
                ]
            )
        return csv_response(f"club-van-20-{vandaag_amsterdam().isoformat()}.csv", kop, rijen)
