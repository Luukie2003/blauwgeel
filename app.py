import secrets
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, send_from_directory, session, url_for

from database import get_db, init_db, register_db
from helpers import (
    PRODUCT_AFBEELDINGEN_MAP,
    STEM_AFBEELDINGEN_MAP,
    bepaal_weergave_modus,
    bereken_bestelling_status,
    bereken_frituurvet_status,
    bereken_kassa_coupure_bedrag,
    bereken_kassa_stand,
    bereken_kassa_telling_status,
    bereken_kassa_verschil_trend,
    bereken_komende_thuiswedstrijden,
    bereken_laatste_telling_status,
    bereken_omzet_trend_periode,
    bereken_trend,
    bereken_voorspelde_tekorten,
    besteleenheid_factor,
    besteleenheid_naam,
    csrf_token,
    dagdeel_groet,
    format_datum,
    SECTIES,
    heeft_sectie_toegang,
    met_tags_filter,
    naar_besteleenheden,
    naar_voorraadeenheden,
    secties_lijst,
    stemming_is_open,
)

BASE_DIR = Path(__file__).parent
SECRET_KEY_PATH = BASE_DIR / "secret_key.txt"

OPEN_ENDPOINTS = {
    "login",
    "static",
    "favicon_ico",
    "service_worker",
    "offline_pagina",
    "wachtwoord_vergeten",
    "wachtwoord_instellen",
    # De publieke stempagina's hebben geen account nodig, bezoekers scannen
    # 'm via een QR-code of stemmen.kantineblauwgeel.nl, ze loggen nergens in.
    "stem_pagina",
    "stem_overzicht_publiek",
}

# Routes die alleen voor de rol 'beheerder' toegankelijk zijn. Vrijwilligers
# komen hier niet in -- zij kunnen de dagelijkse operatie doen (tellen,
# boeken, bestellijst, bijzonderheden) maar niet het assortiment, accounts,
# categorieën of back-ups beheren.
BEHEERDER_ENDPOINTS = {
    "accounts_lijst",
    "account_nieuw",
    "account_verwijderen",
    "account_rol_wijzigen",
    "account_secties_wijzigen",
    "account_email_wijzigen",
    "categorieen_lijst",
    "categorie_verwijderen",
    "categorie_verkoopprijs_verplicht_wisselen",
    "subcategorie_nieuw",
    "subcategorie_verwijderen",
    "backups_lijst",
    "backup_nu",
    "backup_download",
    "backup_herstellen",
    "product_nieuw",
    "product_bewerken",
    "product_verwijderen",
    "product_actief_wisselen",
    "producten_minimumvoorraad",
    "producten_besteleenheid",
    "instellingen_pagina",
    "club_instellingen",
    "club_agenda_toevoegen",
    "club_agenda_verwijderen",
    "club_agenda_verversen",
    "club_agenda_controleren",
    "mededeling_pinnen_als_banner",
}

# Fijnmazige rechten bovenop BEHEERDER_ENDPOINTS: elk account (ook
# vrijwilligers) heeft per sectie een los aan/uit-vinkje (zie Accounts).
# Beheerders omzeilen deze check altijd (zie vereis_login hieronder) -- dit
# is puur om te bepalen welke secties een vrijwilliger wél/niet mag. Routes
# die al in BEHEERDER_ENDPOINTS staan (bijv. product_nieuw) hoeven hier niet
# ook nog in: die blijven sowieso beheerder-only, ongeacht secties.
SECTIE_ENDPOINTS = {
    "voorraad": {
        "voorraadoverzicht",
        "voorraadoverzicht_pdf_route",
        "voorraadoverzicht_csv_route",
        "producten_lijst",
        "product_zoeken",
        "product_detail",
        "product_snel_toevoegen",
        "product_label_pdf",
        "producten_labels_pdf",
        "boeken",
        "levering_inboeken",
        "geschiedenis",
        "tellen",
        "tellen_lopen_starten",
        "tellen_lopen",
        "tellen_lopen_controleren",
        "tellingen_overzicht",
        "tellingen_gecombineerd_pdf",
        "telling_detail",
        "telling_regel_corrigeren",
        "telling_pdf",
        "bestellijst",
        "bestellijst_pdf_route",
        "bestelling_aanmaken",
        "bestelling_nieuw",
        "bestelling_bewerken",
        "bestelling_inboeken",
        "bestelling_verwijderen",
        "fusten_overzicht",
        "boodschappenlijst",
        "boodschap_afvinken",
        "boodschap_verwijderen",
        "scannen",
    },
    "kassa": {
        "kassa_tellen",
        "kassa_telling_detail",
        "kassa_telling_heropenen",
        "kassa_telling_omzet_corrigeren",
        "kassa_telling_coupures_corrigeren",
        "kassa_telling_bewerken",
        "kassa_telling_goedkeuren",
        "kassa_telling_pdf",
        "kassa_geschiedenis",
        "kassa_mutatie_nieuw",
        "kassa_mutatie_corrigeren",
    },
    "keuken": {
        "frituurvet_vervangen",
        "keuken_voorraad",
        "keuken_instellingen",
    },
    "stemmen": {
        "stemmen_overzicht",
        "stemvraag_nieuw",
        "stemvraag_detail",
        "stemvraag_poster_pdf",
        "stem_afkeuren",
        "stem_goedkeuren",
        "stemvraag_sluiten",
        "stemvraag_heropenen",
        "stemvraag_einddatum_instellen",
        "stemvraag_instellingen_bijwerken",
        "stemvraag_verwijderen",
        "bieren_lijst",
        "bier_verwijderen",
    },
}
# Omgekeerde opzoektabel: endpoint -> vereiste sectie, 1x opgebouwd bij het
# starten van het proces i.p.v. bij elk verzoek opnieuw over te zoeken.
ENDPOINT_SECTIE = {
    endpoint: sectie for sectie, endpoints in SECTIE_ENDPOINTS.items() for endpoint in endpoints
}
# Voor het filteren van de zijbalk: welke navigatiegroep hoort bij welke
# sectie. "Algemeen" staat hier bewust niet in -- dat blijft voor iedereen
# zichtbaar.
NAV_GROEP_SECTIE = {"Voorraad": "voorraad", "Kassa": "kassa", "Keuken": "keuken", "Stemmen": "stemmen"}

NAV_ITEMS = [
    {
        "groep": "Algemeen",
        "endpoints": ["dashboard"],
        "url_endpoint": "dashboard",
        "label": "Overzicht",
    },
    {
        "groep": "Algemeen",
        "endpoints": ["bijzonderheden"],
        "url_endpoint": "bijzonderheden",
        "label": "Bijzonderheden",
    },
    {
        "groep": "Algemeen",
        "endpoints": ["week_overzicht"],
        "url_endpoint": "week_overzicht",
        "label": "Weekoverzicht",
    },
    {
        "groep": "Algemeen",
        "endpoints": ["wedstrijden_overzicht"],
        "url_endpoint": "wedstrijden_overzicht",
        "label": "Wedstrijden",
    },
    {
        "groep": "Algemeen",
        "endpoints": ["verkooprapport", "verkooprapport_pdf_route", "verkooprapport_csv_route"],
        "url_endpoint": "verkooprapport",
        "label": "Verkooprapport",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["voorraadoverzicht"],
        "url_endpoint": "voorraadoverzicht",
        "label": "Voorraadoverzicht",
    },
    {
        "groep": "Voorraad",
        "endpoints": [
            "producten_lijst",
            "product_nieuw",
            "product_bewerken",
            "categorieen_lijst",
            "producten_minimumvoorraad",
            "producten_besteleenheid",
        ],
        "url_endpoint": "producten_lijst",
        "label": "Producten",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["boeken", "levering_inboeken"],
        "url_endpoint": "boeken",
        "label": "In/uit boeken",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["geschiedenis"],
        "url_endpoint": "geschiedenis",
        "label": "Mutatieoverzicht",
    },
    {
        "groep": "Voorraad",
        "endpoints": [
            "tellen",
            "tellen_lopen",
            "tellen_lopen_starten",
            "tellen_lopen_controleren",
        ],
        "url_endpoint": "tellen",
        "label": "Voorraad tellen",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["tellingen_overzicht", "telling_detail", "tellingen_gecombineerd_pdf"],
        "url_endpoint": "tellingen_overzicht",
        "label": "Tellingen",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["bestellijst", "bestelling_aanmaken", "bestelling_nieuw", "bestelling_inboeken"],
        "url_endpoint": "bestellijst",
        "label": "Bestellijst",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["fusten_overzicht"],
        "url_endpoint": "fusten_overzicht",
        "label": "Fusten",
    },
    {
        "groep": "Voorraad",
        "endpoints": ["boodschappenlijst"],
        "url_endpoint": "boodschappenlijst",
        "label": "Boodschappenlijst",
    },
    {
        "groep": "Kassa",
        "endpoints": [
            "kassa_tellen",
            "kassa_telling_detail",
            "kassa_telling_bewerken",
            "kassa_telling_goedkeuren",
            "kassa_telling_pdf",
            "kassa_telling_heropenen",
        ],
        "url_endpoint": "kassa_tellen",
        "label": "Kassa tellen",
    },
    {
        "groep": "Kassa",
        "endpoints": ["kassa_geschiedenis"],
        "url_endpoint": "kassa_geschiedenis",
        "label": "Kassa geschiedenis",
    },
    {
        "groep": "Kassa",
        "endpoints": ["kassa_mutatie_nieuw"],
        "url_endpoint": "kassa_mutatie_nieuw",
        "label": "Afdracht / toevoeging",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_voorraad"],
        "url_endpoint": "keuken_voorraad",
        "label": "Voorraad",
    },
    {
        "groep": "Keuken",
        "endpoints": ["keuken_instellingen"],
        "url_endpoint": "keuken_instellingen",
        "label": "Instellingen",
    },
    {
        "groep": "Stemmen",
        "endpoints": [
            "stemmen_overzicht",
            "stemvraag_nieuw",
            "stemvraag_detail",
            "stemvraag_poster_pdf",
            "stemvraag_sluiten",
            "stemvraag_heropenen",
            "stemvraag_verwijderen",
            "stemvraag_einddatum_instellen",
            "stemvraag_instellingen_bijwerken",
            "stem_goedkeuren",
            "stem_afkeuren",
        ],
        "url_endpoint": "stemmen_overzicht",
        "label": "Overzicht",
    },
    {
        "groep": "Stemmen",
        "endpoints": ["bieren_lijst", "bier_verwijderen"],
        "url_endpoint": "bieren_lijst",
        "label": "Bierbibliotheek",
    },
]

# Groepen komen in deze volgorde in de zijbalk te staan (Python dicts noch
# SQL-resultaten garanderen een stabiele groepsvolgorde als items ooit worden
# herschikt, dus NAV_ITEMS wordt bij het opbouwen van de zijbalk hierop
# gesorteerd). Nieuwe groepen (bijv. een toekomstige "Keuken") hoeven hier
# alleen aan toegevoegd te worden om vanzelf een eigen sectie te krijgen.
NAV_GROEP_VOLGORDE = ["Algemeen", "Voorraad", "Kassa", "Keuken", "Stemmen"]
NAV_ITEMS.sort(key=lambda item: NAV_GROEP_VOLGORDE.index(item["groep"]))

# De PDA-modus (zie WEERGAVE_TELEFOON_PATROON hieronder) toont alleen deze
# handvol pagina's -- puur vloerwerk, geen beheer/rapportages. Bewust een
# losse, kortere lijst i.p.v. een subset-vlag op NAV_ITEMS: die twee navigaties
# verschillen te veel (geen groepen, kortere labels) om hetzelfde datamodel
# te delen.
PDA_NAV_ITEMS = [
    {"url_endpoint": "tellen", "pda_label": "Tellen"},
    {"url_endpoint": "boeken", "pda_label": "Boeken"},
    {"url_endpoint": "bijzonderheden", "pda_label": "Prikbord"},
    {"url_endpoint": "kassa_tellen", "pda_label": "Kassa"},
    {"url_endpoint": "bestellijst", "pda_label": "Bestellijst"},
    {"url_endpoint": "geschiedenis", "pda_label": "Geschiedenis"},
    {"url_endpoint": "boodschappenlijst", "pda_label": "Boodschappen"},
]


def get_secret_key():
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_PATH.write_text(key)
    return key


def create_app(database_path=None):
    app = Flask(__name__)
    app.config["DATABASE"] = database_path or str(BASE_DIR / "voorraad.db")
    app.config["SECRET_KEY"] = get_secret_key()
    # Secure staat hier standaard aan omdat de site altijd via https draait
    # (PythonAnywhere dwingt dit af); voor lokaal testen over http wordt dit
    # in het "__main__"-blok onderaan dit bestand weer uitgezet.
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Ruim genoeg voor een paar afbeeldingen bij stemopties, of het
    # terugzetten van een back-up.
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

    register_db(app)
    init_db(app)

    app.jinja_env.filters["datum_nl"] = format_datum
    app.jinja_env.filters["besteleenheid_naam"] = besteleenheid_naam
    app.jinja_env.filters["naar_besteleenheden"] = naar_besteleenheden
    app.jinja_env.filters["met_tags"] = met_tags_filter
    app.jinja_env.globals["stemming_is_open"] = stemming_is_open
    app.jinja_env.globals["secties_lijst"] = secties_lijst

    @app.before_request
    def zet_weergave_modus():
        """Moet als allereerste before_request draaien, vóór alles wat een
        request kan afkappen met een redirect (met name vereis_login()
        hieronder) -- anders krijgt een nog niet ingelogde telefoon nooit de
        kans om herkend te worden: de omleiding naar /login zou dan al
        (verkeerd) 'desktop' vastzetten in het cookie voordat deze functie
        ooit draait, en dat cookie wint daarna altijd van de User-Agent."""
        g.weergave_modus = bepaal_weergave_modus()

    @app.before_request
    def csrf_beschermen():
        """Simpele CSRF-bescherming zonder externe library: elk formulier op
        de site bevat een verborgen csrf_token-veld (zie de context_processor
        hieronder), dat moet overeenkomen met de waarde die bij het laden van
        de pagina in de sessie is gezet. Geldt voor alle POSTs, ook naar
        open endpoints (login e.d.) -- geen uitzonderingen, dat voorkomt dat
        er per ongeluk een nieuw gat ontstaat als er later een open endpoint
        bijkomt.

        Bij een mismatch (bijv. een pagina die via de terug-knop/cache met
        een verouderd token werd getoond) sturen we terug naar dezelfde
        pagina i.p.v. een kale 400-foutpagina te tonen -- die pagina heeft
        dan meteen weer een geldig token."""
        if request.method == "POST":
            verwacht = session.get("csrf_token")
            verzonden = request.form.get("csrf_token", "")
            if not verwacht or not secrets.compare_digest(verzonden, verwacht):
                flash("Deze pagina was verlopen, probeer het nog eens.", "error")
                return redirect(request.referrer or url_for("login"))

    @app.before_request
    def vereis_login():
        if request.endpoint in OPEN_ENDPOINTS or request.endpoint is None:
            return None
        if "gebruiker_id" not in session:
            return redirect(url_for("login", next=request.path))
        if "gebruiker_rol" not in session or "gebruiker_secties" not in session:
            # Sessie is aangemaakt voor rollen/secties bestonden (of
            # anderszins verouderd) -- alsnog ophalen zodat je niet
            # handmatig hoeft uit/in te loggen na een update.
            db = get_db()
            gebruiker = db.execute(
                "SELECT rol, secties FROM gebruikers WHERE id = ?", (session["gebruiker_id"],)
            ).fetchone()
            if gebruiker is None:
                session.clear()
                return redirect(url_for("login", next=request.path))
            session["gebruiker_rol"] = gebruiker["rol"]
            session["gebruiker_secties"] = gebruiker["secties"]
        if request.endpoint in BEHEERDER_ENDPOINTS and session.get("gebruiker_rol") != "beheerder":
            flash("Deze pagina is alleen voor beheerders.", "error")
            return redirect(url_for("dashboard"))
        vereiste_sectie = ENDPOINT_SECTIE.get(request.endpoint)
        if vereiste_sectie and not heeft_sectie_toegang(
            session.get("gebruiker_rol"), session.get("gebruiker_secties"), vereiste_sectie
        ):
            flash("Deze pagina is niet beschikbaar voor jouw account.", "error")
            return redirect(url_for("dashboard"))
        return None

    @app.context_processor
    def inject_nav():
        gebruiker_rol = session.get("gebruiker_rol")
        gebruiker_secties = session.get("gebruiker_secties")
        zichtbare_nav_items = [
            item
            for item in NAV_ITEMS
            if item["groep"] not in NAV_GROEP_SECTIE
            or heeft_sectie_toegang(gebruiker_rol, gebruiker_secties, NAV_GROEP_SECTIE[item["groep"]])
        ]
        zichtbare_pda_items = [
            item
            for item in PDA_NAV_ITEMS
            if item["url_endpoint"] not in ENDPOINT_SECTIE
            or heeft_sectie_toegang(
                gebruiker_rol, gebruiker_secties, ENDPOINT_SECTIE[item["url_endpoint"]]
            )
        ]
        actieve_nav = next(
            (item for item in NAV_ITEMS if request.endpoint in item["endpoints"]),
            None,
        )
        banner_tekst = None
        if "gebruiker_id" in session:
            rij = get_db().execute(
                "SELECT banner_tekst FROM instellingen WHERE id = 1"
            ).fetchone()
            banner_tekst = rij["banner_tekst"] if rij else None
        pda_modus = g.get("weergave_modus") == "pda"
        pda_actieve_item = next(
            (
                item
                for item in PDA_NAV_ITEMS
                if actieve_nav and item["url_endpoint"] == actieve_nav["url_endpoint"]
            ),
            None,
        )
        sectie_toegang = {
            sectie: heeft_sectie_toegang(gebruiker_rol, gebruiker_secties, sectie) for sectie in SECTIES
        }
        return {
            "nav_items": zichtbare_nav_items,
            "pda_nav_items": zichtbare_pda_items,
            "sectie_toegang": sectie_toegang,
            "actieve_nav": actieve_nav,
            "pda_actieve_label": pda_actieve_item["pda_label"] if pda_actieve_item else None,
            "huidige_gebruiker": session.get("gebruiker_naam"),
            "huidige_gebruiker_rol": session.get("gebruiker_rol"),
            "css_versie": int((BASE_DIR / "static" / "style.css").stat().st_mtime),
            "site_banner_tekst": banner_tekst,
            "csrf_token": csrf_token,
            "pda_modus": pda_modus,
            "basis_template": "base_pda.html" if pda_modus else "base.html",
            "toon_welkom_popup": session.pop("toon_welkom_popup", False),
            "welkom_groet": dagdeel_groet(),
        }

    @app.route("/favicon.ico")
    def favicon_ico():
        return send_from_directory(app.static_folder, "favicon.ico")

    @app.route("/sw.js")
    def service_worker():
        # Moet op het domeinniveau ("/sw.js") staan, niet onder /static/ --
        # anders beperkt de browser de scope van de service worker tot
        # /static/, en kan die geen navigaties (paginabezoeken) elders op de
        # site opvangen. send_from_directory herkent .js zelf al correct als
        # text/javascript.
        return send_from_directory(app.static_folder, "sw.js")

    @app.route("/offline")
    def offline_pagina():
        """Losstaande, minimale pagina (geen base.html) die de service
        worker toont als een navigatie mislukt zonder verbinding -- bewust
        geen sessie-afhankelijke inhoud (ingelogde naam, zijbalk), want die
        kan op het moment van cachen allang verouderd zijn."""
        return render_template("offline.html")

    @app.after_request
    def beveiligingsheaders(response):
        """Standaard beveiligingsheaders. De site heeft geen externe
        scripts/stijlen/fonts -- alleen 'self' plus 'unsafe-inline' omdat
        sommige pagina's nog inline <script>- en onsubmit-attributen
        gebruiken."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:"
        )
        if request.endpoint == "login":
            # Voorkomt dat de browser (of terug-knop/bfcache) een oude
            # inlogpagina met een inmiddels verlopen csrf-token laat zien --
            # dat gaf af en toe een "Bad Request" bij het inloggen.
            response.headers["Cache-Control"] = "no-store"
        weergave_al_gezet_door_view = any(
            c.startswith("weergave=") for c in response.headers.getlist("Set-Cookie")
        )
        if "weergave" not in request.cookies and not weergave_al_gezet_door_view:
            # Allereerste bezoek op dit toestel: de op de User-Agent
            # gebaseerde gok (zie bepaal_weergave_modus()) meteen vastzetten
            # in een cookie, zodat 'ie vanaf nu "onthouden" is -- ook al is
            # er nooit bewust op de PDA/desktop-knop geklikt. (Als de route
            # zelf al expliciet een weergave-cookie heeft gezet -- zoals de
            # "Aanmelden in handterminal-weergave"-knop -- laten we die keuze
            # ongemoeid in plaats van 'm hier stiekem te overschrijven.)
            response.set_cookie(
                "weergave",
                g.get("weergave_modus", "desktop"),
                max_age=60 * 60 * 24 * 365,
                samesite="Lax",
                secure=app.config.get("SESSION_COOKIE_SECURE", True),
            )
        return response

    @app.errorhandler(404)
    def pagina_niet_gevonden(fout):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def interne_fout(fout):
        return render_template("500.html"), 500

    from routes import (
        accounts,
        auth,
        bestellijst,
        boeken,
        boodschappenlijst,
        dashboard,
        fusten,
        instellingen,
        kassa,
        keuken,
        producten,
        stemmen,
        tellen,
    )

    accounts.register_routes(app)
    auth.register_routes(app)
    bestellijst.register_routes(app)
    boeken.register_routes(app)
    boodschappenlijst.register_routes(app)
    dashboard.register_routes(app)
    fusten.register_routes(app)
    instellingen.register_routes(app)
    kassa.register_routes(app)
    keuken.register_routes(app)
    producten.register_routes(app)
    stemmen.register_routes(app)
    tellen.register_routes(app)
    return app


app = create_app()

if __name__ == "__main__":
    # Lokaal draait de app over gewone http, niet https -- met
    # SESSION_COOKIE_SECURE aan zou de browser de sessie-cookie dan nooit
    # terugsturen en zou inloggen niet werken.
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(debug=True, host="0.0.0.0", port=5050)
