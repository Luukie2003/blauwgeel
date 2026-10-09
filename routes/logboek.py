from datetime import datetime, timedelta

from flask import Response, g, render_template, request, session

from database import get_db
from helpers import csv_response, format_datum, is_ajax_verzoek, now_str
from pdf import logboek_pdf

# Endpoint -> korte omschrijving van de actie, voor Club > Logboek. Alleen
# POSTs die iets belangrijks wijzigen: rechten, geld, assortiment, back-ups
# en instellingen. Gewone dagelijkse handelingen (boeken, tellen, prikbord)
# staan er bewust niet in -- die hebben hun eigen geschiedenis en zouden het
# logboek onleesbaar maken.
LOGBOEK_ACTIES = {
    "login": "Ingelogd",
    "account_nieuw": "Account aangemaakt",
    "account_verwijderen": "Account verwijderd",
    "account_rol_wijzigen": "Rol gewijzigd",
    "account_secties_wijzigen": "Rechten gewijzigd",
    "account_email_wijzigen": "E-mailadres account gewijzigd",
    "account_actief_wisselen": "Account geblokkeerd/geactiveerd",
    "account_wachtwoord_link_versturen": "Wachtwoord-link verstuurd",
    "account_wachtwoord": "Eigen wachtwoord gewijzigd",
    "account_andere_toestellen_uitloggen": "Op alle andere toestellen uitgelogd",
    "account_overal_uitloggen": "Account op alle toestellen uitgelogd",
    "backup_nu": "Back-up gemaakt",
    "backup_herstellen": "Back-up teruggezet",
    "instellingen_pagina": "Algemene instellingen gewijzigd",
    "club_agenda_toevoegen": "Teamagenda toegevoegd",
    "club_agenda_verwijderen": "Teamagenda verwijderd",
    "kassa_telling_goedkeuren": "Kassatelling goedgekeurd",
    "kassa_telling_heropenen": "Kassatelling heropend",
    "kassa_telling_bewerken": "Kassatelling bewerkt",
    "kassa_telling_omzet_corrigeren": "Omzet kassatelling gecorrigeerd",
    "kassa_telling_coupures_corrigeren": "Getelde coupures kassa gecorrigeerd",
    "kassa_mutatie_nieuw": "Kassa afdracht/toevoeging geboekt",
    "kassa_mutatie_corrigeren": "Kassa afdracht/toevoeging gecorrigeerd",
    "kluis_telling_goedkeuren": "Kluistelling goedgekeurd",
    "kluis_telling_heropenen": "Kluistelling heropend",
    "kluis_telling_bewerken": "Kluistelling bewerkt",
    "kluis_telling_coupures_corrigeren": "Getelde coupures kluis gecorrigeerd",
    "kluis_mutatie_nieuw": "Kluis storting/opname geboekt",
    "kluis_mutatie_corrigeren": "Kluis storting/opname gecorrigeerd",
    "product_nieuw": "Product aangemaakt",
    "product_bewerken": "Product bewerkt",
    "product_verwijderen": "Product verwijderd",
    "producten_bulk_bewerken": "Producten in bulk bewerkt",
    "producten_minimumvoorraad": "Minimumvoorraad in bulk gewijzigd",
    "producten_besteleenheid": "Besteleenheid in bulk gewijzigd",
    "categorie_verwijderen": "Categorie verwijderd",
    "subcategorie_verwijderen": "Subcategorie verwijderd",
    "telling_regel_corrigeren": "Tellingregel gecorrigeerd",
    "bestelling_verwijderen": "Bestelling verwijderd",
    "club_van_20_lid_verwijderen": "Club van 20-lid verwijderd",
    "club_van_20_aanmelding_goedkeuren": "Club van 20-aanmelding goedgekeurd",
    "club_van_20_aanmelding_afwijzen": "Club van 20-aanmelding afgewezen",
    "stemvraag_verwijderen": "Stemming verwijderd",
    "seizoensrapport_historie": "Omzet van een eerder seizoen ingevuld",
}

TOONBARE_DAGEN = (7, 30, 90, 365)
STANDAARD_DAGEN = 30
MAX_REGELS = 500
MAX_REGELS_EXPORT = 5000
MAX_OMSCHRIJVING = 300


def _aantal_flashes():
    return len(session.get("_flashes", []))


def schrijf_logboek(db, endpoint, omschrijving=None):
    """Voegt 1 regel toe aan het logboek. Los beschikbaar zodat een route
    iets kan loggen dat het centrale mechanisme niet ziet."""
    db.execute(
        """INSERT INTO logboek (datum, gebruiker_id, gebruiker_naam, endpoint, actie, omschrijving)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            now_str(),
            session.get("gebruiker_id"),
            session.get("gebruiker_naam"),
            endpoint,
            LOGBOEK_ACTIES.get(endpoint, endpoint),
            (omschrijving or "")[:MAX_OMSCHRIJVING] or None,
        ),
    )
    db.commit()


def _omschrijving_uit_flashes(vanaf):
    """De melding die de gebruiker na de actie zelf zag is al een nette
    Nederlandse omschrijving ("Account 'Piet' aangemaakt.") -- die hergebruiken
    we i.p.v. per route een eigen tekst bij te houden. None als er geen
    succesmelding was, of er een foutmelding bij zat (dan is de actie niet
    doorgegaan en loggen we niets)."""
    nieuwe = session.get("_flashes", [])[vanaf:]
    if any(categorie == "error" for categorie, _ in nieuwe):
        return None
    succes = [tekst for categorie, tekst in nieuwe if categorie == "success"]
    return " ".join(succes)


def register_routes(app):
    @app.before_request
    def logboek_onthoud_flashes():
        g.logboek_flashes_voor = _aantal_flashes()

    @app.after_request
    def logboek_vastleggen(response):
        if request.method != "POST" or request.endpoint not in LOGBOEK_ACTIES:
            return response
        # Is een eerdere before_request (CSRF, inloggen, rechten) de aanvraag
        # al komen afkappen, dan is de actie zelf nooit uitgevoerd.
        if "logboek_flashes_voor" not in g:
            return response
        # Alleen een afgeronde actie: een redirect na het opslaan, of (AJAX)
        # een gewoon 200. Een 200-pagina van een niet-AJAX-POST is het
        # formulier dat opnieuw getoond wordt met een fout.
        afgerond = 300 <= response.status_code < 400 or (
            response.status_code == 200 and is_ajax_verzoek()
        )
        if not afgerond:
            return response
        omschrijving = _omschrijving_uit_flashes(g.logboek_flashes_voor)
        if omschrijving is None:
            return response
        schrijf_logboek(get_db(), request.endpoint, omschrijving)
        return response

    def _gekozen_filter():
        dagen = request.args.get("dagen", STANDAARD_DAGEN, type=int)
        if dagen not in TOONBARE_DAGEN:
            dagen = STANDAARD_DAGEN
        return dagen, request.args.get("gebruiker", "").strip()

    def _haal_regels(db, dagen, gebruiker_filter, limiet):
        sinds = (datetime.now() - timedelta(days=dagen - 1)).strftime("%Y-%m-%d 00:00")
        voorwaarden = ["datum >= ?"]
        parameters = [sinds]
        if gebruiker_filter:
            voorwaarden.append("gebruiker_naam = ?")
            parameters.append(gebruiker_filter)
        return db.execute(
            f"""SELECT * FROM logboek WHERE {' AND '.join(voorwaarden)}
                ORDER BY datum DESC, id DESC LIMIT ?""",
            (*parameters, limiet),
        ).fetchall()

    @app.route("/logboek")
    def logboek():
        dagen, gebruiker_filter = _gekozen_filter()
        db = get_db()
        regels = _haal_regels(db, dagen, gebruiker_filter, MAX_REGELS + 1)
        namen = [
            r["gebruiker_naam"]
            for r in db.execute(
                "SELECT DISTINCT gebruiker_naam FROM logboek WHERE gebruiker_naam IS NOT NULL ORDER BY gebruiker_naam"
            ).fetchall()
        ]
        return render_template(
            "logboek.html",
            regels=regels[:MAX_REGELS],
            te_veel=len(regels) > MAX_REGELS,
            max_regels=MAX_REGELS,
            gekozen_dagen=dagen,
            toonbare_dagen=TOONBARE_DAGEN,
            gebruiker_filter=gebruiker_filter,
            namen=namen,
        )

    @app.route("/logboek/csv")
    def logboek_csv_route():
        dagen, gebruiker_filter = _gekozen_filter()
        regels = _haal_regels(get_db(), dagen, gebruiker_filter, MAX_REGELS_EXPORT)
        return csv_response(
            "logboek.csv",
            ["Moment", "Wie", "Actie", "Details"],
            [(format_datum(r["datum"]), r["gebruiker_naam"] or "", r["actie"], r["omschrijving"] or "") for r in regels],
        )

    @app.route("/logboek/pdf")
    def logboek_pdf_route():
        dagen, gebruiker_filter = _gekozen_filter()
        regels = _haal_regels(get_db(), dagen, gebruiker_filter, MAX_REGELS_EXPORT)
        periode = "Laatste jaar" if dagen == 365 else f"Laatste {dagen} dagen"
        if gebruiker_filter:
            periode += f"  -  {gebruiker_filter}"
        return Response(
            logboek_pdf(
                [
                    {
                        "moment": format_datum(r["datum"]),
                        "wie": r["gebruiker_naam"] or "-",
                        "actie": r["actie"],
                        "details": r["omschrijving"] or "",
                    }
                    for r in regels
                ],
                periode,
            ),
            mimetype="application/pdf",
            headers={"Content-Disposition": "inline; filename=logboek.pdf"},
        )
