import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, send_from_directory, session, url_for

import mail
import uitrollen as uitrollen_module
from aanmeldingen import aantal_openstaand
from club_van_20 import bereken_club_van_20_status  # noqa: F401 (tests importeren 'm via app)
from database import get_db, init_db, register_db
from foutmelding import Melder
from helpers import (
    PRODUCT_AFBEELDINGEN_MAP,
    STEM_AFBEELDINGEN_MAP,
    VIDEO_UPLOAD_ENDPOINTS,
    VIDEO_UPLOAD_MAX_BYTES,
    bepaal_weergave_modus,
    bereken_bestelling_status,
    bereken_frituurvet_status,
    bereken_kassa_coupure_bedrag,
    bereken_kassa_telling_status,
    bereken_kassa_verschil_trend,
    bereken_kassalade_stand,
    bereken_kluis_stand,
    bereken_komende_thuiswedstrijden,
    bereken_laatste_telling_status,
    bereken_omzet_trend_periode,
    bereken_trend,
    bereken_voorspelde_tekorten,
    besteleenheid_factor,
    besteleenheid_naam,
    csrf_token,
    css_uitlijning,
    dagdeel_groet,
    format_datum,
    format_datum_kort,
    SECTIES,
    heeft_sectie_toegang,
    is_ajax_verzoek,
    met_tags_filter,
    naar_besteleenheden,
    naar_voorraadeenheden,
    now_str,
    secties_lijst,
    stemming_is_open,
)
from navigatie import (  # noqa: F401
    NAV_GROEP_ALLEEN_BEHEERDER,
    NAV_GROEP_ICOON,
    NAV_GROEP_SECTIE,
    NAV_ITEM_ALLEEN_BEHEERDER,
    NAV_ITEM_SECTIE,
    NAV_ITEMS,
    PDA_NAV_ITEMS,
)
from rechten import (  # noqa: F401
    BEHEERDER_ENDPOINTS,
    ENDPOINT_SECTIE,
    GEBRUIK_NIET_LOGGEN,
    OPEN_ENDPOINTS,
    SECTIE_ENDPOINTS,
    TABLET_CODE_UITGEZONDERD,
)

BASE_DIR = Path(__file__).parent
SECRET_KEY_PATH = BASE_DIR / "secret_key.txt"


def get_secret_key():
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_PATH.write_text(key)
    return key


def create_app(database_path=None, admin_wachtwoord=None, sjablonen_voorladen=False):
    app = Flask(__name__)
    app.config["DATABASE"] = database_path or str(BASE_DIR / "voorraad.db")
    app.config["SECRET_KEY"] = get_secret_key()
    # Secure staat hier standaard aan omdat de site altijd via https draait
    # (PythonAnywhere dwingt dit af); voor lokaal testen over http wordt dit
    # in het "__main__"-blok onderaan dit bestand weer uitgezet.
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Hoe lang "Ingelogd blijven" duurt (zie de inlogpagina); een geblokkeerd account wordt bij
    # elk verzoek gecontroleerd (vereis_login), dus dat is daarna alsnog meteen buitengesloten.
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    # Ruim genoeg voor een paar afbeeldingen bij stemopties, of het
    # terugzetten van een back-up.
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
    # Lang cachen mag: geuploade afbeeldingen krijgen bij het opslaan altijd
    # een gloednieuwe, willekeurige bestandsnaam (zie sla_afbeelding_op in
    # helpers.py) -- een vervangen foto overschrijft dus nooit een bestaande
    # URL, en style.css heeft z'n eigen cache-buster (?v=..., zie css_versie
    # hieronder). Zonder dit stond hier geen Cache-Control-header op, dus
    # werd elk statisch bestand bij elk bezoek opnieuw gevalideerd.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000  # 365 dagen

    register_db(app)
    init_db(app, admin_wachtwoord=admin_wachtwoord)

    app.jinja_env.filters["datum_nl"] = format_datum
    app.jinja_env.filters["datum_kort"] = format_datum_kort
    app.jinja_env.filters["besteleenheid_naam"] = besteleenheid_naam
    app.jinja_env.filters["naar_besteleenheden"] = naar_besteleenheden
    app.jinja_env.filters["met_tags"] = met_tags_filter
    app.jinja_env.filters["css_uitlijning"] = css_uitlijning
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
    def ruim_uploadlimiet_op_voor_video():
        """Een dia met een video is veel groter dan de gewone uploadlimiet (MAX_CONTENT_LENGTH). Alleen de twee
        dia-formulieren, en alleen voor wie is ingelogd, mogen daarom groter zijn. Moet vóór
        csrf_beschermen draaien: dat leest het formulier al, en daar zou de lage limiet nog gelden."""
        if request.method == "POST" and request.endpoint in VIDEO_UPLOAD_ENDPOINTS and "gebruiker_id" in session:
            request.max_content_length = VIDEO_UPLOAD_MAX_BYTES

    @app.before_request
    def csrf_beschermen():
        """Simpele CSRF-bescherming zonder externe library: elk formulier op
        de site bevat een verborgen csrf_token-veld (zie de context_processor
        hieronder), dat moet overeenkomen met de waarde die bij het laden van
        de pagina in de sessie is gezet. Geldt voor alle POSTs, ook naar
        open endpoints (login e.d.) -- op precies 1 na (zie hieronder), dat
        voorkomt dat er per ongeluk een nieuw gat ontstaat als er later een
        open endpoint bijkomt.

        Bij een mismatch (bijv. een pagina die via de terug-knop/cache met
        een verouderd token werd getoond) sturen we terug naar dezelfde
        pagina i.p.v. een kale 400-foutpagina te tonen -- die pagina heeft
        dan meteen weer een geldig token."""
        if request.method == "POST" and request.endpoint in ("tablet_code_inloggen", "uitrollen_endpoint"):
            # CSRF is een misbruik van een browser die AL een geldige sessie
            # heeft -- dat bestaat hier niet: dit is een kale JSON-API-aanroep
            # vanuit de kiosk-tablet-app, zonder cookies/sessie, dus zonder
            # csrf_token om te controleren. Eigen brute-force-bescherming
            # (per IP) zit al in tablet_code_inloggen zelf. Hetzelfde geldt voor
            # uitrollen_endpoint: een script, beveiligd met een handtekening.
            return None
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
        # Elke keer opnieuw (i.p.v. alleen als rol/secties nog in de sessie
        # ontbreken, zoals hieronder) omdat "actief" direct moet gelden zodra
        # een beheerder iemand blokkeert (zie account_actief_wisselen) -- een
        # geblokkeerd account moet niet kunnen doorwerken met een sessie die
        # van vóór de blokkade dateert.
        db = get_db()
        gebruiker = db.execute(
            "SELECT rol, secties, actief, tablet_code_hash, sessie_versie FROM gebruikers WHERE id = ?",
            (session["gebruiker_id"],),
        ).fetchone()
        if gebruiker is None or not gebruiker["actief"]:
            session.clear()
            flash("Dit account bestaat niet meer of is geblokkeerd. Neem contact op met een beheerder.", "error")
            return redirect(url_for("login"))
        # "Overal uitloggen" verhoogt sessie_versie in de database; een sessie met een oudere versie
        # is daarna ongeldig. Sessies van vóór deze functie hebben nog geen versie: dat telt als 0,
        # net als de beginwaarde in de database, dus niemand wordt bij het invoeren uitgelogd.
        if session.get("sessie_versie", 0) != gebruiker["sessie_versie"]:
            session.clear()
            flash("Je bent uitgelogd, want je account is op alle toestellen uitgelogd. Log opnieuw in.", "error")
            return redirect(url_for("login"))
        if "gebruiker_rol" not in session or "gebruiker_secties" not in session:
            # Sessie is aangemaakt voor rollen/secties bestonden (of
            # anderszins verouderd) -- alsnog ophalen zodat je niet
            # handmatig hoeft uit/in te loggen na een update.
            session["gebruiker_rol"] = gebruiker["rol"]
            session["gebruiker_secties"] = gebruiker["secties"]
        if (
            gebruiker["tablet_code_hash"] is None
            and request.endpoint not in TABLET_CODE_UITGEZONDERD
        ):
            return redirect(url_for("tablet_code_instellen", next=request.path))
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

    def _nav_item_zichtbaar(item, gebruiker_rol, gebruiker_secties):
        # Een los item-vlak (NAV_ITEM_SECTIE) wint altijd van de groepregels
        # hieronder -- daarmee kan 1 item uit een verder beheerder-only groep
        # (bijv. "Club instellingen" in de groep "Beheer") toch aan een
        # vrijwilliger met de juiste sectie getoond worden.
        if item["url_endpoint"] in NAV_ITEM_ALLEEN_BEHEERDER:
            return gebruiker_rol == "beheerder"
        sectie = NAV_ITEM_SECTIE.get(item["url_endpoint"]) or NAV_GROEP_SECTIE.get(item["groep"])
        if sectie:
            return heeft_sectie_toegang(gebruiker_rol, gebruiker_secties, sectie)
        if item["groep"] in NAV_GROEP_ALLEEN_BEHEERDER:
            return gebruiker_rol == "beheerder"
        return True

    # De zoekfunctie (routes/zoeken.py) zoekt ook in de pagina's van de app zelf,
    # en mag alleen de pagina's tonen die dit account in de zijbalk ziet.
    app.extensions["zichtbare_nav_items"] = lambda: [
        item
        for item in NAV_ITEMS
        if _nav_item_zichtbaar(item, session.get("gebruiker_rol"), session.get("gebruiker_secties"))
    ]

    @app.context_processor
    def inject_nav():
        gebruiker_rol = session.get("gebruiker_rol")
        gebruiker_secties = session.get("gebruiker_secties")
        zichtbare_nav_items = [
            item for item in NAV_ITEMS if _nav_item_zichtbaar(item, gebruiker_rol, gebruiker_secties)
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
        # Aantal aanmeldingen dat op goedkeuring wacht, als badge in de zijbalk.
        club_aanmeldingen_open = 0
        if "gebruiker_id" in session and heeft_sectie_toegang(
            gebruiker_rol, gebruiker_secties, "club_van_20"
        ):
            club_aanmeldingen_open = aantal_openstaand(get_db())
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
            "nav_groep_icoon": NAV_GROEP_ICOON,
            "sectie_toegang": sectie_toegang,
            "club_aanmeldingen_open": club_aanmeldingen_open,
            "actieve_nav": actieve_nav,
            "pda_actieve_label": pda_actieve_item["pda_label"] if pda_actieve_item else None,
            "huidige_gebruiker": session.get("gebruiker_naam"),
            "huidige_gebruiker_rol": session.get("gebruiker_rol"),
            "css_versie": int((BASE_DIR / "static" / "style.css").stat().st_mtime),
            "gedeeld_js_versie": int((BASE_DIR / "static" / "gedeeld.js").stat().st_mtime),
            "kiosk_stijl_versie": int((BASE_DIR / "static" / "kiosk_scherm_stijl.css").stat().st_mtime),
            "kiosk_welkom_stijl_versie": int((BASE_DIR / "static" / "kiosk_welkom_stijl.css").stat().st_mtime),
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
        # De 3 kiosk-schermen zijn publieke, puur tonende pagina's zonder
        # enige interactieve/klikbare inhoud (geen formulieren, geen links)
        # -- geen clickjacking-risico dus, en die uitzondering is nodig
        # zodat de instellingenpagina en de Kiosk-hub 'm in een
        # live-voorbeeld-iframe kunnen tonen. Overal elders blijft framen
        # (SAMEORIGIN-uitzondering incluis) uit.
        response.headers["X-Frame-Options"] = (
            "SAMEORIGIN"
            if request.endpoint in ("kiosk_scherm", "kiosk_prijzen_scherm", "kiosk_tv")
            else "DENY"
        )
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

    @app.after_request
    def log_paginabezoek(response):
        """Registreert paginabezoeken voor Club > Gebruiksstatistieken (zie
        routes/gebruik.py) -- alleen gewone volledige paginabezoeken tellen
        mee: een echte GET-navigatie (geen AJAX-fetch die maar een stukje
        JSON ophaalt), geen technisch/polling-verkeer (zie
        GEBRUIK_NIET_LOGGEN hierboven) en geen foutpagina's (status >= 400),
        want de view heeft dan mogelijk niet eens gecommit."""
        if (
            request.method == "GET"
            and response.status_code < 400
            and request.endpoint is not None
            and request.endpoint not in GEBRUIK_NIET_LOGGEN
            and not is_ajax_verzoek()
        ):
            db = get_db()
            db.execute(
                """INSERT INTO paginabezoeken (endpoint, gebruiker_id, weergave_modus, datum)
                   VALUES (?, ?, ?, ?)""",
                (
                    request.endpoint,
                    session.get("gebruiker_id"),
                    g.get("weergave_modus", "desktop"),
                    now_str(),
                ),
            )
            db.commit()
        return response

    @app.errorhandler(413)
    def upload_te_groot(fout):
        limiet = (request.max_content_length or app.config["MAX_CONTENT_LENGTH"]) // (1024 * 1024)
        flash(f"Dit bestand is te groot om te uploaden (maximaal {limiet} MB).", "error")
        return redirect(request.referrer or url_for("login"))

    @app.errorhandler(404)
    def pagina_niet_gevonden(fout):
        return render_template("404.html"), 404

    def _ontvanger_foutmeldingen():
        """Het vaste e-mailadres voor systeemmeldingen (Club > Instellingen); anders het standaardadres."""
        try:
            rij = get_db().execute("SELECT notificatie_email FROM instellingen WHERE id = 1").fetchone()
            return (rij["notificatie_email"] or None) if rij else None
        except Exception:
            return None  # ook als de database zelf het probleem is

    foutmelder = Melder()

    @app.errorhandler(500)
    def interne_fout(fout):
        # Alleen echte (onverwachte) fouten melden, en niet tijdens de tests.
        origineel = getattr(fout, "original_exception", None)
        if origineel is not None and app.config.get("FOUTMELDING_MAIL", not app.testing):
            from wijzigingen import HUIDIGE_VERSIE

            naar = _ontvanger_foutmeldingen()
            foutmelder.meld(
                origineel,
                lambda onderwerp, tekst: mail.stuur_mail(onderwerp, tekst, naar=naar),
                endpoint=request.endpoint,
                methode=request.method,
                pad=request.path,
                gebruiker=session.get("gebruiker_naam"),
                versie=HUIDIGE_VERSIE,
                commit=uitrollen_module.huidige_commit(),
            )
        return render_template("500.html"), 500

    from routes import (
        aanmeldingen,
        accounts,
        auth,
        bardienstrapport,
        bestellijst,
        boeken,
        boodschappenlijst,
        club_van_20,
        dashboard,
        fusten,
        gebruik,
        instellingen,
        kassa,
        keuken,
        kiosk,
        kluis,
        logboek,
        privacy,
        producten,
        prognose,
        seizoensrapport,
        sponsoren,
        stemmen,
        tellen,
        uitdraai,
        uitrollen,
        verbruiksvoorwerpen,
        zoeken,
    )

    aanmeldingen.register_routes(app)
    privacy.register_routes(app)
    prognose.register_routes(app)
    accounts.register_routes(app)
    auth.register_routes(app)
    bardienstrapport.register_routes(app)
    bestellijst.register_routes(app)
    boeken.register_routes(app)
    boodschappenlijst.register_routes(app)
    club_van_20.register_routes(app)
    dashboard.register_routes(app)
    fusten.register_routes(app)
    gebruik.register_routes(app)
    instellingen.register_routes(app)
    kassa.register_routes(app)
    keuken.register_routes(app)
    kiosk.register_routes(app)
    kluis.register_routes(app)
    logboek.register_routes(app)
    producten.register_routes(app)
    seizoensrapport.register_routes(app)
    sponsoren.register_routes(app)
    stemmen.register_routes(app)
    tellen.register_routes(app)
    uitdraai.register_routes(app)
    uitrollen.register_routes(app)
    verbruiksvoorwerpen.register_routes(app)
    zoeken.register_routes(app)
    if sjablonen_voorladen:
        _laad_sjablonen_voor(app)
    return app


def _laad_sjablonen_voor(app):
    """Leest alle sjablonen nu al in, in plaats van pas wanneer ze voor het eerst nodig zijn.

    Bij live zetten wordt de code op schijf vervangen en daarna de web-app herstart. In die paar
    seconden (of langer, als het herstarten wordt vergeten) draait het oude proces nog: laadde het
    dan een sjabloon die het nog niet kende, dan las het de NIEUWE versie van schijf, die naar
    routes verwijst die dit proces niet heeft. Zo ontstond op 20 september een reeks BuildErrors.
    Zijn alle sjablonen al ingelezen, dan draait een oud proces consequent op oude code en sjablonen
    tot het wordt herstart. Een sjabloon dat niet te lezen is mag het starten nooit tegenhouden;
    de tests (test_sjablonen.py) vangen zulke fouten eerder af."""
    for naam in app.jinja_env.list_templates():
        try:
            app.jinja_env.get_template(naam)
        except Exception as fout:  # pragma: no cover
            print(f"[sjablonen] {naam} niet te laden: {fout}")


app = create_app(sjablonen_voorladen=True)

if __name__ == "__main__":
    # Lokaal draait de app over gewone http, niet https -- met
    # SESSION_COOKIE_SECURE aan zou de browser de sessie-cookie dan nooit
    # terugsturen en zou inloggen niet werken.
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(debug=True, host="0.0.0.0", port=5050)
