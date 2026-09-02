import csv
import hashlib
import io
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

import agenda
import qr
import backup as backup_module
import mail
import weer
from database import get_db, init_db, register_db
from pdf import (
    bestellijst_pdf,
    kassa_pdf,
    periode_verkoop_pdf,
    stemming_poster_pdf,
    verkoop_pdf,
    voorraadoverzicht_pdf,
)

BASE_DIR = Path(__file__).parent
SECRET_KEY_PATH = BASE_DIR / "secret_key.txt"
BACKUP_BESTANDSNAAM = re.compile(
    r"^voorraad-(\d{4}-\d{2}-\d{2}|voor-herstel-\d{8}-\d{6})\.db$"
)

# Voor het @taggen van gebruikers in mededelingen/opmerkingen op het
# prikbord. Gebruikersnamen bevatten in de praktijk geen spaties, dus een
# eenvoudige woordmatch is genoeg.
TAG_PATROON = re.compile(r"@([A-Za-z0-9_.\-]+)")

# Handmatig bijgehouden versie-overzicht voor de Help-pagina. Geen
# geautomatiseerd systeem (geen releases/tags) -- gewoon een leesbaar logje
# van wat er is toegevoegd, bijgewerkt bij noemenswaardige wijzigingen.
HUIDIGE_VERSIE = "1.4.0"
WIJZIGINGEN = [
    {
        "versie": "1.4.0",
        "datum": "25 augustus 2026",
        "punten": [
            "Bijzonderheden: mededelingen 'afhandelen' i.p.v. alleen verwijderen, met wie en wanneer",
            "Urgente mededelingen vallen op tussen de rest van het prikbord",
            "Een mededeling met één klik als de site-brede banner tonen",
        ],
    },
    {
        "versie": "1.3.0",
        "datum": "25 augustus 2026",
        "punten": [
            "Vier-ogen-principe bij kassatellingen: de teller keurt zijn eigen telling niet meer zelf goed",
            "Opmerking bij goedkeuring, apart van de opmerking van de teller",
            "Wie geteld en wie goedgekeurd heeft staat nu in het kasverslag (scherm en PDF)",
            "Team-agenda's en weer gecombineerd op de nieuwe Wedstrijden-pagina",
            "Voorspelde tekorten op de bestellijst, ook boven het minimum",
            "Correctie-boekingen licht rood gemarkeerd in de geschiedenis",
        ],
    },
    {
        "versie": "1.2.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Automatische tests bij elke push naar GitHub (CI)",
            "Signalering van verouderde dependencies (Dependabot)",
            "Beveiligingsheaders toegevoegd (Content-Security-Policy e.a.)",
            "Uurlijkse controle of de site bereikbaar is, met mailmelding bij storing",
        ],
    },
    {
        "versie": "1.1.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Geautomatiseerde tests voor de kernberekeningen (kassa, voorraad, inloggen)",
            "Overgestapt naar Python 3.13 (voorheen 3.9), zowel lokaal als op de server",
        ],
    },
    {
        "versie": "1.0.0",
        "datum": "24 augustus 2026",
        "punten": [
            "Nieuwe kassa-module: tellen per coupure, afdracht/toevoeging boeken, kassa-geschiedenis",
            "Wekelijks overzicht: nieuwe pagina + opgemaakte maandagochtend-mail met logo",
            "Boekingen gekoppeld aan het echte ingelogde account i.p.v. een vrij in te typen naam",
            "Wegklikbare mededelingenbalk bovenaan de site, instelbaar door de beheerder",
            "Omzettrend op het dashboard en het verkooprapport",
        ],
    },
    {
        "versie": "0.4.0",
        "datum": "23 augustus 2026",
        "punten": [
            "Bestellen, ontvangen en leveringen inboeken per besteleenheid (bijv. kratten, dozen)",
            "Verkoopprijs vastgezet per telling, zodat latere prijswijzigingen historische omzet niet meer aantasten",
            "Inkoopprijzen, artikelcodes en besteleenheden bijgewerkt op basis van de leverancierslijst",
            "Subcategorieën onder hoofdcategorieën",
            "Zelf-registratie via e-mail, wachtwoord vergeten, en mailvoorkeuren per account",
            "Mobiele navigatie herzien, homescreen-icoon, eigen 404/500-paginas, favicons",
        ],
    },
    {
        "versie": "0.3.0",
        "datum": "22 augustus 2026",
        "punten": [
            "Categorieën als beheerbare lijst, filter/zoekbalk op de Producten-pagina",
            "Rollen en rechten voor accounts (beheerder/vrijwilliger)",
            "Uitgebreid voorraadoverzicht met waarde per categorie en PDF",
        ],
    },
    {
        "versie": "0.2.0",
        "datum": "21 augustus 2026",
        "punten": [
            "Automatische dagelijkse back-up, met terugzetten vanuit de app",
            "Prikbord (Bijzonderheden)",
            "Losse levering/factuur inboeken, controlescherm na de looplijst",
        ],
    },
    {
        "versie": "0.1.0",
        "datum": "20 augustus 2026",
        "punten": [
            "Eerste versie: producten, voorraad bijhouden, in-/uitboeken",
            "Inloggen en accountbeheer",
            "Voorraad tellen, ook via een looplijst voor onderweg met de telefoon",
            "Verkooprapport per periode (PDF), huisstijl s.v. Blauw-Geel 1915",
        ],
    },
]

OPEN_ENDPOINTS = {
    "login",
    "static",
    "favicon_ico",
    "wachtwoord_vergeten",
    "wachtwoord_instellen",
    # De publieke stempagina's hebben geen account nodig, bezoekers scannen
    # 'm via een QR-code of stemmen.kantineblauwgeel.nl, ze loggen nergens in.
    "stem_pagina",
    "stem_overzicht_publiek",
}

# Naam van het los cookie waarmee een anonieme stemmer wordt herkend (om
# dubbel stemmen op dezelfde stemvraag tegen te gaan). Bewust geen gebruik
# van de Flask-sessie zelf: die wordt bij inloggen geleegd, en stemmers zijn
# meestal niet eens ingelogd.
STEM_COOKIE = "stem_kiezer"

STEM_AFBEELDINGEN_MAP = BASE_DIR / "static" / "stem_afbeeldingen"
PRODUCT_AFBEELDINGEN_MAP = BASE_DIR / "static" / "product_afbeeldingen"
TOEGESTANE_AFBEELDING_EXTENSIES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_STEMOPTIES = 10


def sla_afbeelding_op(bestand, doelmap):
    """Slaat een geuploade afbeelding veilig op in doelmap (een willekeurige
    bestandsnaam, alleen bekende afbeeldingsextensies) en geeft de
    bestandsnaam terug. None als er niets bruikbaars is geupload."""
    if not bestand or not bestand.filename:
        return None
    extensie = Path(bestand.filename).suffix.lower()
    if extensie not in TOEGESTANE_AFBEELDING_EXTENSIES:
        return None
    doelmap.mkdir(parents=True, exist_ok=True)
    bestandsnaam = f"{secrets.token_hex(16)}{extensie}"
    bestand.save(doelmap / bestandsnaam)
    return bestandsnaam


def sla_stemoptie_afbeelding_op(bestand):
    return sla_afbeelding_op(bestand, STEM_AFBEELDINGEN_MAP)


def bewaar_bier(db, naam, afbeelding):
    """Bewaart een stemoptie-naam + foto in de bieren-bibliotheek zodat hij
    bij een volgende stemming hergebruikt kan worden. Bestond de naam al, dan
    wordt alleen de foto bijgewerkt (en enkel als er een nieuwe is)."""
    if not naam or not afbeelding:
        return
    db.execute(
        """INSERT INTO bieren (naam, afbeelding, aangemaakt_op) VALUES (?, ?, ?)
           ON CONFLICT(naam) DO UPDATE SET afbeelding = excluded.afbeelding""",
        (naam, afbeelding, now_str()),
    )

# Brute-force-bescherming op het inlogscherm: na dit aantal mislukte
# pogingen voor dezelfde gebruikersnaam wordt die naam tijdelijk geblokkeerd,
# ongeacht of het wachtwoord daarna wel klopt.
LOGIN_MAX_POGINGEN = 5
LOGIN_LOCKOUT_MINUTEN = 15

# Routes die alleen voor de rol 'beheerder' toegankelijk zijn. Vrijwilligers
# komen hier niet in -- zij kunnen de dagelijkse operatie doen (tellen,
# boeken, bestellijst, bijzonderheden) maar niet het assortiment, accounts,
# categorieën of back-ups beheren.
BEHEERDER_ENDPOINTS = {
    "accounts_lijst",
    "account_nieuw",
    "account_verwijderen",
    "account_rol_wijzigen",
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
        if "gebruiker_rol" not in session:
            # Sessie is aangemaakt voor rollen bestonden (of anderszins
            # verouderd) -- rol alsnog ophalen zodat je niet handmatig
            # hoeft uit/in te loggen na een update.
            db = get_db()
            gebruiker = db.execute(
                "SELECT rol FROM gebruikers WHERE id = ?", (session["gebruiker_id"],)
            ).fetchone()
            if gebruiker is None:
                session.clear()
                return redirect(url_for("login", next=request.path))
            session["gebruiker_rol"] = gebruiker["rol"]
        if request.endpoint in BEHEERDER_ENDPOINTS and session.get("gebruiker_rol") != "beheerder":
            flash("Deze pagina is alleen voor beheerders.", "error")
            return redirect(url_for("dashboard"))
        return None

    @app.context_processor
    def inject_nav():
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
        return {
            "nav_items": NAV_ITEMS,
            "actieve_nav": actieve_nav,
            "huidige_gebruiker": session.get("gebruiker_naam"),
            "huidige_gebruiker_rol": session.get("gebruiker_rol"),
            "css_versie": int((BASE_DIR / "static" / "style.css").stat().st_mtime),
            "site_banner_tekst": banner_tekst,
            "csrf_token": csrf_token,
        }

    @app.route("/favicon.ico")
    def favicon_ico():
        return send_from_directory(app.static_folder, "favicon.ico")

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
        return response

    @app.errorhandler(404)
    def pagina_niet_gevonden(fout):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def interne_fout(fout):
        return render_template("500.html"), 500

    register_routes(app)
    return app


def csv_response(bestandsnaam, kop, rijen):
    """Bouwt een CSV-downloadresponse. kop: lijst kolomnamen, rijen: lijst
    van lijsten/tuples in dezelfde volgorde. Puntkomma als scheidingsteken
    en een UTF-8 BOM vooraan, want dat is wat Excel met een Nederlandse
    landinstelling verwacht om het bestand meteen goed te openen."""
    buffer = io.StringIO()
    schrijver = csv.writer(buffer, delimiter=";")
    schrijver.writerow(kop)
    schrijver.writerows(rijen)
    return Response(
        "﻿" + buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={bestandsnaam}"},
    )


def format_datum(value):
    if not value:
        return ""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return dt.strftime("%d-%m-%Y %H:%M")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def now_datetime_local():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def csrf_token():
    """Geeft het CSRF-token voor de huidige sessie terug, en maakt er een aan
    als die nog niet bestaat. Wordt zowel gebruikt om het verborgen
    formuliersveld te vullen (via de context_processor) als om binnenkomende
    POSTs tegen te controleren (csrf_beschermen)."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def genereer_wachtwoord_token(db, gebruiker_id, geldig_uren):
    """Maakt een eenmalige, tijdelijke link-token om een wachtwoord in te
    stellen (gebruikt voor zowel account-activatie als wachtwoord-vergeten).
    Er wordt alleen een hash van de token opgeslagen -- niet de token zelf --
    zodat een gelekte database-backup geen bruikbare inlogtokens bevat."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    verloopt = (datetime.now() + timedelta(hours=geldig_uren)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        "UPDATE gebruikers SET reset_token_hash = ?, reset_token_verloopt = ? WHERE id = ?",
        (token_hash, verloopt, gebruiker_id),
    )
    db.commit()
    return token


def vind_gebruiker_bij_token(db, token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    gebruiker = db.execute(
        "SELECT * FROM gebruikers WHERE reset_token_hash = ?", (token_hash,)
    ).fetchone()
    if gebruiker is None or not gebruiker["reset_token_verloopt"]:
        return None
    verloopt = datetime.strptime(gebruiker["reset_token_verloopt"], "%Y-%m-%d %H:%M")
    if verloopt < datetime.now():
        return None
    return gebruiker


def is_ajax_verzoek():
    """Detecteert of dit verzoek via de JS-laag (fetch, zie base.html) is
    verstuurd i.p.v. een gewone formulier-submit -- zulke routes geven dan
    JSON terug in plaats van een redirect, zodat de pagina niet hoeft te
    herladen voor een simpele statuswijziging."""
    return request.headers.get("X-Requested-With") == "fetch"


def veilig_redirect_pad(pad, fallback):
    """Voorkomt een open redirect via de 'next'-parameter na het inloggen:
    alleen een pad op de eigen site wordt geaccepteerd. //evil.nl en
    /\\evil.nl worden door sommige browsers als protocol-relatieve URL naar
    een externe site geïnterpreteerd, dus die worden expliciet geweigerd."""
    if not pad or not pad.startswith("/") or pad.startswith("//") or pad.startswith("/\\"):
        return fallback
    return pad


def besteleenheid_naam(product):
    return product["besteleenheid"] or product["eenheid"]


def besteleenheid_factor(product):
    factor = product["besteleenheid_factor"] or 1
    return factor if factor > 0 else 1


def naar_besteleenheden(aantal_voorraadeenheden, product):
    """Rondt naar boven af naar hele besteleenheden (je bestelt geen halve krat)."""
    factor = besteleenheid_factor(product)
    return -(-max(0, aantal_voorraadeenheden) // factor)


def naar_voorraadeenheden(aantal_besteleenheden, product):
    return max(0, aantal_besteleenheden) * besteleenheid_factor(product)


def bewaar_subcategorie(db, categorie, subcategorie):
    """Registreert een nieuwe subcategorie automatisch zodra hij bij een
    product wordt ingevuld, zodat hij meteen ook bij andere producten te
    kiezen is -- zonder eerst naar Categorieën beheren te hoeven."""
    if not categorie or not subcategorie:
        return
    db.execute(
        "INSERT OR IGNORE INTO subcategorieen (categorie, naam) VALUES (?, ?)",
        (categorie, subcategorie),
    )


def categorienamen_zonder_verkoopprijsplicht(db):
    """Categorieën waarvoor een verkoopprijs niet verplicht is (bijv.
    fusten -- die worden nooit als geheel verkocht, alleen per glas
    getapt). Producten hierin mogen op € 0,00 staan zonder dat dit als
    ontbrekende prijs wordt gemeld."""
    return {
        r["naam"]
        for r in db.execute(
            "SELECT naam FROM categorieen WHERE verkoopprijs_verplicht = 0"
        ).fetchall()
    }


def bereken_trend(omzet_per_week, huidige_jaar, huidige_week):
    """Voortschrijdend gemiddelde + trendrichting op basis van volledig
    afgesloten weken (de lopende week telt niet mee, die is nog niet klaar).

    omzet_per_week: lijst met dicts (jaar, week, omzet, ...), nieuwste eerst.
    """
    afgeronde_weken = [
        w for w in omzet_per_week if (w["jaar"], w["week"]) != (huidige_jaar, huidige_week)
    ]
    chronologisch = list(reversed(afgeronde_weken))  # oud -> nieuw

    if len(chronologisch) < 2:
        return None

    recente = chronologisch[-4:]
    verwachting = sum(w["omzet"] for w in recente) / len(recente)

    n = len(chronologisch)
    xs = list(range(n))
    ys = [w["omzet"] for w in chronologisch]
    x_gem = sum(xs) / n
    y_gem = sum(ys) / n
    teller = sum((x - x_gem) * (y - y_gem) for x, y in zip(xs, ys))
    noemer = sum((x - x_gem) ** 2 for x in xs)
    richting_per_week = teller / noemer if noemer else 0

    if abs(richting_per_week) < 0.02 * (y_gem or 1):
        richting = "stabiel"
    elif richting_per_week > 0:
        richting = "stijgend"
    else:
        richting = "dalend"

    return {
        "verwachting": verwachting,
        "richting": richting,
        "richting_per_week": richting_per_week,
        "gebaseerd_op_weken": len(recente),
    }


def bereken_omzet_trend_periode(db, van, tot):
    """Omzet + best verkopende producten voor alle tellingen binnen een zelf
    gekozen periode -- gebruikt door het verkooprapport en het weekoverzicht.
    Rekent met de bevroren telling-prijs (tr.verkoopprijs), niet de actuele
    productprijs, zodat latere prijswijzigingen oude cijfers niet aanpassen."""
    tellingen = db.execute(
        """SELECT t.id, t.datum, t.naam,
                  COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
           FROM tellingen t
           LEFT JOIN telling_regels tr ON tr.telling_id = t.id
           WHERE t.datum >= ? AND t.datum <= ?
           GROUP BY t.id
           ORDER BY t.datum""",
        (f"{van} 00:00", f"{tot} 23:59"),
    ).fetchall()

    top_verkopers = []
    if tellingen:
        telling_ids = [t["id"] for t in tellingen]
        placeholders = ",".join("?" for _ in telling_ids)
        top_verkopers = db.execute(
            f"""SELECT p.naam AS product_naam, p.eenheid, p.categorie, p.subcategorie,
                       SUM(tr.verkocht) AS verkocht,
                       SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                FROM telling_regels tr
                JOIN producten p ON p.id = tr.product_id
                WHERE tr.telling_id IN ({placeholders})
                GROUP BY tr.product_id
                HAVING SUM(tr.verkocht) > 0
                ORDER BY omzet DESC
                LIMIT 6""",
            telling_ids,
        ).fetchall()

    max_omzet = max((t["omzet"] for t in tellingen), default=0)
    totale_omzet = sum(t["omzet"] for t in tellingen)

    # Thuiswedstrijden per telling-periode: elke balk vertegenwoordigt de
    # periode sinds de vorige telling (of 'van' voor de eerste balk in dit
    # overzicht -- een kleine benadering als de echte vorige telling buiten
    # de gekozen periode viel). Geeft een indicatie of een piek in omzet
    # samenvalt met een wedstrijd.
    wedstrijd_datums = [
        w["datum"]
        for w in db.execute(
            "SELECT datum FROM wedstrijden WHERE thuis = 1 AND datum >= ? AND datum <= ? ORDER BY datum",
            (van, tot),
        ).fetchall()
    ]

    balken = []
    vorige_datum = van
    eerste_balk = True
    for t in tellingen:
        periode_eind = t["datum"][:10]
        if eerste_balk:
            # Inclusief 'van' zelf: dat is de gekozen startdatum van de
            # periode, geen eerdere telling waarvan een wedstrijd al is
            # meegeteld.
            aantal_wedstrijden = sum(1 for d in wedstrijd_datums if vorige_datum <= d <= periode_eind)
            eerste_balk = False
        else:
            aantal_wedstrijden = sum(1 for d in wedstrijd_datums if vorige_datum < d <= periode_eind)
        balken.append(
            {
                "datum_kort": datetime.strptime(t["datum"], "%Y-%m-%d %H:%M").strftime("%d-%m"),
                "omzet": t["omzet"],
                "hoogte_pct": (t["omzet"] / max_omzet * 100) if max_omzet else 0,
                "thuiswedstrijden": aantal_wedstrijden,
            }
        )
        vorige_datum = periode_eind

    return {
        "balken": balken,
        "top_verkopers": top_verkopers,
        "totale_omzet": totale_omzet,
    }


def bereken_fust_verkopen(db, limiet=100):
    """Waarschijnlijke verkopen per fust, afgeleid uit de gewone
    voorraadtellingen: als een fust-product (glazen_per_fust > 0) minder
    wordt geteld dan de vorige keer, telt dat als lege fust(en). Aantal
    glazen en bedrag zijn een schatting op basis van glazen_per_fust en
    prijs_per_glas -- er is geen registratie per getapt glas, dus 'wanneer'
    is hier net zo precies als de tellingen zelf."""
    regels = db.execute(
        """SELECT t.datum, p.naam AS product_naam, tr.verkocht,
                  p.glazen_per_fust, p.prijs_per_glas
           FROM telling_regels tr
           JOIN tellingen t ON t.id = tr.telling_id
           JOIN producten p ON p.id = tr.product_id
           WHERE p.glazen_per_fust > 0 AND tr.verkocht > 0
           ORDER BY t.datum DESC, t.id DESC
           LIMIT ?""",
        (limiet,),
    ).fetchall()

    gebeurtenissen = []
    totaal_fusten = 0
    totaal_glazen = 0
    totaal_bedrag = 0.0
    for r in regels:
        glazen = r["verkocht"] * r["glazen_per_fust"]
        bedrag = glazen * r["prijs_per_glas"]
        gebeurtenissen.append(
            {
                "datum": r["datum"],
                "product_naam": r["product_naam"],
                "aantal_fusten": r["verkocht"],
                "glazen": glazen,
                "bedrag": bedrag,
            }
        )
        totaal_fusten += r["verkocht"]
        totaal_glazen += glazen
        totaal_bedrag += bedrag

    return {
        "gebeurtenissen": gebeurtenissen,
        "totaal_fusten": totaal_fusten,
        "totaal_glazen": totaal_glazen,
        "totaal_bedrag": totaal_bedrag,
    }


def bestel_suggesties(db):
    product_ids_in_open_bestelling = {
        row["product_id"]
        for row in db.execute(
            """SELECT br.product_id FROM bestelregels br
               JOIN bestellingen b ON b.id = br.bestelling_id
               WHERE b.status = 'besteld'"""
        ).fetchall()
    }
    return [
        p
        for p in db.execute(
            """SELECT * FROM producten
               WHERE actief = 1 AND voorraad < min_voorraad
               ORDER BY categorie, naam"""
        ).fetchall()
        if p["id"] not in product_ids_in_open_bestelling
    ]


def regels_per_bestelling(db, bestelling_ids):
    """Haalt de bestelregels voor meerdere bestellingen in één query op,
    gegroepeerd per bestelling_id -- voorkomt een aparte query per
    bestelling in een loop (bestellijst() toont dit al snel voor tien-tallen
    bestellingen tegelijk)."""
    if not bestelling_ids:
        return {}
    placeholders = ",".join("?" * len(bestelling_ids))
    per_bestelling = {}
    for regel in db.execute(
        f"""SELECT br.*, p.naam AS product_naam, p.eenheid,
                   p.besteleenheid, p.besteleenheid_factor
            FROM bestelregels br JOIN producten p ON p.id = br.product_id
            WHERE br.bestelling_id IN ({placeholders})""",
        bestelling_ids,
    ).fetchall():
        per_bestelling.setdefault(regel["bestelling_id"], []).append(regel)
    return per_bestelling


def bereken_week_overzicht(db, vandaag=None):
    """Overzicht van de meest recente volledig afgesloten week (maandag t/m
    zondag): omzet met vergelijking t.o.v. de week ervoor, top verkopers, en
    producten onder minimumvoorraad. Wordt zowel gebruikt voor de
    weekoverzicht-pagina als voor het wekelijkse e-mailtje (elke maandag)."""
    vandaag = vandaag or datetime.now().date()
    deze_week_maandag = vandaag - timedelta(days=vandaag.weekday())
    week_tot = deze_week_maandag - timedelta(days=1)
    week_van = week_tot - timedelta(days=6)
    vorige_week_tot = week_van - timedelta(days=1)
    vorige_week_van = vorige_week_tot - timedelta(days=6)

    huidige = bereken_omzet_trend_periode(db, week_van.isoformat(), week_tot.isoformat())
    vorige = bereken_omzet_trend_periode(
        db, vorige_week_van.isoformat(), vorige_week_tot.isoformat()
    )

    verschil_percentage = None
    if vorige["totale_omzet"] > 0:
        verschil_percentage = (
            (huidige["totale_omzet"] - vorige["totale_omzet"]) / vorige["totale_omzet"] * 100
        )

    open_bestellingen = db.execute(
        "SELECT * FROM bestellingen WHERE status = 'besteld' ORDER BY aangemaakt_op"
    ).fetchall()

    nieuwe_mededelingen = db.execute(
        "SELECT * FROM mededelingen WHERE datum >= ? AND datum <= ? ORDER BY id DESC",
        (f"{week_van.isoformat()} 00:00", f"{week_tot.isoformat()} 23:59"),
    ).fetchall()

    niet_verplicht_categorieen = categorienamen_zonder_verkoopprijsplicht(db)
    zonder_prijs = [
        p
        for p in db.execute(
            """SELECT * FROM producten
               WHERE actief = 1 AND (verkoopprijs = 0 OR inkoopprijs = 0)
               ORDER BY categorie, naam"""
        ).fetchall()
        if p["inkoopprijs"] == 0 or p["categorie"] not in niet_verplicht_categorieen
    ]

    return {
        "week_van": week_van,
        "week_tot": week_tot,
        "totale_omzet": huidige["totale_omzet"],
        "vorige_omzet": vorige["totale_omzet"],
        "verschil_percentage": verschil_percentage,
        "top_verkopers": huidige["top_verkopers"],
        "onder_minimum": bestel_suggesties(db),
        "open_bestellingen": open_bestellingen,
        "nieuwe_mededelingen": nieuwe_mededelingen,
        "zonder_prijs": zonder_prijs,
        "niet_verplicht_categorieen": niet_verplicht_categorieen,
    }


# (kolomnaam, waarde in euro's, weergavenaam) -- geen 1- en 2-centstukken,
# die worden bij contant afrekenen in Nederland toch afgerond op 5 cent.
KASSA_COUPURES = [
    ("aantal_50", 50.00, "€ 50"),
    ("aantal_20", 20.00, "€ 20"),
    ("aantal_10", 10.00, "€ 10"),
    ("aantal_5", 5.00, "€ 5"),
    ("aantal_2", 2.00, "€ 2"),
    ("aantal_1", 1.00, "€ 1"),
    ("aantal_050", 0.50, "€ 0,50"),
    ("aantal_020", 0.20, "€ 0,20"),
    ("aantal_010", 0.10, "€ 0,10"),
    ("aantal_005", 0.05, "€ 0,05"),
]


def bereken_kassa_coupure_bedrag(request_form):
    """Leest de aantallen per coupure uit een POST-formulier en telt het
    totaalbedrag op. Retourneert (aantallen-dict, totaalbedrag)."""
    aantallen = {}
    totaal = 0.0
    for kolom, waarde, _ in KASSA_COUPURES:
        try:
            aantal = max(0, int(request_form.get(kolom, "0") or 0))
        except ValueError:
            aantal = 0
        aantallen[kolom] = aantal
        totaal += aantal * waarde
    return aantallen, round(totaal, 2)


def bereken_kassa_stand(db):
    """Het laatst bekende (verwachte) bedrag in de kassa. Wordt direct
    bijgehouden in instellingen.kassa_stand -- elke afdracht/toevoeging past
    'm meteen aan, en elke telling zet 'm gelijk aan het getelde bedrag
    (zelfde patroon als producten.voorraad). Dat voorkomt dat je bij het
    afleiden via datums misgrijpt wanneer twee dingen binnen dezelfde minuut
    gebeuren (de datumvelden in deze app hebben geen secondeprecisie)."""
    rij = db.execute("SELECT kassa_stand FROM instellingen WHERE id = 1").fetchone()
    # Alleen afgesloten tellingen tellen mee -- een nog openstaande (concept)
    # telling heeft zijn bedrag nog niet in kassa_stand verrekend, dus die
    # mag hier niet als "laatste telling" worden aangezien.
    laatste_telling = db.execute(
        "SELECT * FROM kassa_tellingen WHERE afgesloten = 1 ORDER BY datum DESC, id DESC LIMIT 1"
    ).fetchone()
    return {
        "stand": round(rij["kassa_stand"] if rij else 0.0, 2),
        "laatste_telling": laatste_telling,
    }


def bereken_kassa_verschil_trend(db, limiet=20):
    """Verschil (te kort/te veel) van de laatste afgesloten kassatellingen,
    voor de trendgrafiek op de kassa-geschiedenis-pagina. Signaleert ook als
    het handmatig ingetypte PayPal-bedrag (contante_omzet) sterk afwijkt van
    de omzet die in diezelfde periode uit de voorraadtellingen volgt -- kan
    op een tikfout wijzen, of op een gemiste voorraadtelling. Alleen
    afgesloten tellingen: een nog open (concept) telling heeft geen
    definitief verschil."""
    ruw = db.execute(
        """SELECT id, datum, naam, contante_omzet, verschil FROM kassa_tellingen
           WHERE afgesloten = 1 ORDER BY datum DESC, id DESC LIMIT ?""",
        (limiet + 1,),
    ).fetchall()
    ruw = list(reversed(ruw))
    if not ruw:
        return {"balken": [], "max_verschil": 0}

    # Eén extra telling opgehaald (als die er is) puur om als startpunt van
    # de eerste getoonde periode te dienen -- anders zou de oudste balk hier
    # geen betrouwbare vergelijkingsomzet kunnen krijgen.
    heeft_context = len(ruw) > limiet
    tellingen = ruw[1:] if heeft_context else ruw

    voorraad_omzet = db.execute(
        """SELECT t.datum, COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
           FROM tellingen t LEFT JOIN telling_regels tr ON tr.telling_id = t.id
           WHERE t.datum > ? AND t.datum <= ?
           GROUP BY t.id""",
        (ruw[0]["datum"], tellingen[-1]["datum"]),
    ).fetchall()

    balken = []
    vorige_datum = ruw[0]["datum"] if heeft_context else None
    for kt in tellingen:
        verkoop_omzet = None
        if vorige_datum is not None:
            verkoop_omzet = sum(
                r["omzet"] for r in voorraad_omzet if vorige_datum < r["datum"] <= kt["datum"]
            )
        afwijkend = (
            verkoop_omzet is not None
            and verkoop_omzet > 0
            and abs(kt["contante_omzet"] - verkoop_omzet) > max(verkoop_omzet * 0.15, 25)
        )
        balken.append(
            {
                "id": kt["id"],
                "datum_kort": datetime.strptime(kt["datum"], "%Y-%m-%d %H:%M").strftime("%d-%m"),
                "verschil": kt["verschil"],
                "naam": kt["naam"],
                "contante_omzet": kt["contante_omzet"],
                "verkoop_omzet": verkoop_omzet,
                "afwijkend": afwijkend,
            }
        )
        vorige_datum = kt["datum"]

    max_verschil = max((abs(b["verschil"]) for b in balken), default=0)
    for balk in balken:
        balk["hoogte_pct"] = (abs(balk["verschil"]) / max_verschil * 100) if max_verschil else 0

    return {"balken": balken, "max_verschil": max_verschil}


def kassa_telling_is_zelf_goedgekeurd(telling):
    """Of de teller zijn eigen telling heeft goedgekeurd (mag, maar wordt
    apart getoond zodat dat niet verstopt blijft t.o.v. een onafhankelijke
    goedkeuring door iemand anders)."""
    return (
        telling["afgesloten"]
        and telling["gebruiker_id"] is not None
        and telling["gebruiker_id"] == telling["goedgekeurd_door_id"]
    )


def bereken_wedstrijd_geschiedenis(db, limiet=25):
    """De laatst gespeelde wedstrijden (alle teams, thuis en uit) --
    gedeeld tussen de Wedstrijden-pagina en Club instellingen."""
    return [
        {
            "datum_weergave": datetime.strptime(w["datum"], "%Y-%m-%d").strftime("%d-%m-%Y"),
            "team": w["team"],
            "omschrijving": w["omschrijving"],
            "thuis": w["thuis"],
        }
        for w in db.execute(
            "SELECT * FROM wedstrijden WHERE datum < ? ORDER BY datum DESC, team LIMIT ?",
            (date.today().isoformat(), limiet),
        ).fetchall()
    ]


def bereken_komende_thuiswedstrijden(db, dagen=14):
    """Groepeert de komende thuiswedstrijden per datum -- gevuld door
    agenda.py (de gekoppelde teamagenda's) -- samen met de weersverwachting
    van diezelfde dag (gevuld door weer.py), als indicatie hoe druk het kan
    worden: een thuiswedstrijd bij mooi weer trekt meer mensen dan bij
    regen. Rekent nog niets automatisch door in de omzetverwachting -- zie
    bereken_voorspelde_tekorten() voor waar dat wel gebeurt."""
    vandaag = date.today().isoformat()
    grens = (date.today() + timedelta(days=dagen)).isoformat()
    rijen = db.execute(
        """SELECT datum, team, omschrijving FROM wedstrijden
           WHERE thuis = 1 AND datum >= ? AND datum <= ?
           ORDER BY datum, team""",
        (vandaag, grens),
    ).fetchall()
    per_datum = {}
    for r in rijen:
        per_datum.setdefault(r["datum"], []).append(r)

    weer_per_datum = {
        w["datum"]: w
        for w in db.execute(
            "SELECT * FROM weer_voorspelling WHERE datum >= ? AND datum <= ?",
            (vandaag, grens),
        ).fetchall()
    }

    resultaat = []
    for datum, lijst in sorted(per_datum.items()):
        w = weer_per_datum.get(datum)
        resultaat.append(
            {
                "datum": datum,
                "datum_weergave": datetime.strptime(datum, "%Y-%m-%d").strftime("%d-%m-%Y"),
                "wedstrijden": lijst,
                "weer": (
                    {
                        "label": weer.weer_label(w["weercode"]),
                        "max_temp": w["max_temp"],
                        "neerslag_kans": w["neerslag_kans"],
                    }
                    if w
                    else None
                ),
            }
        )
    return resultaat


def bereken_voorspelde_tekorten(db, dagen_vooruit=7):
    """Schat welke producten waarschijnlijk uitverkocht raken in de komende
    `dagen_vooruit` dagen, ook als de voorraad nu nog boven het minimum
    zit -- in tegenstelling tot bestel_suggesties(), dat pas waarschuwt als
    het al te laat is. Combineert de gemiddelde historische verkoop per week
    met het aantal thuiswedstrijden en de weersverwachting in die periode.

    Dit is een eerste, simpele versie: met weinig telling-geschiedenis is de
    schatting grof. Hoe meer tellingen er bijkomen, hoe betrouwbaarder het
    gemiddelde per week wordt."""
    eerste_telling = db.execute("SELECT MIN(datum) AS datum FROM tellingen").fetchone()["datum"]
    if not eerste_telling:
        return []
    verstreken_weken = max(
        1.0,
        (datetime.now() - datetime.strptime(eerste_telling, "%Y-%m-%d %H:%M")).days / 7,
    )

    verkoop_per_product = {
        r["product_id"]: r["totaal_verkocht"]
        for r in db.execute(
            "SELECT product_id, SUM(verkocht) AS totaal_verkocht FROM telling_regels GROUP BY product_id"
        ).fetchall()
    }

    vandaag = date.today()
    grens = vandaag + timedelta(days=dagen_vooruit)
    aantal_wedstrijddagen = db.execute(
        """SELECT COUNT(DISTINCT datum) AS n FROM wedstrijden
           WHERE thuis = 1 AND datum >= ? AND datum <= ?""",
        (vandaag.isoformat(), grens.isoformat()),
    ).fetchone()["n"]

    weer_rijen = db.execute(
        "SELECT * FROM weer_voorspelling WHERE datum >= ? AND datum <= ?",
        (vandaag.isoformat(), grens.isoformat()),
    ).fetchall()
    weer_factor = 1.0
    if weer_rijen:
        gem_neerslag = sum(w["neerslag_kans"] for w in weer_rijen) / len(weer_rijen)
        gem_temp = sum(w["max_temp"] for w in weer_rijen) / len(weer_rijen)
        if gem_neerslag < 30 and gem_temp > 18:
            weer_factor = 1.15
        elif gem_neerslag > 60:
            weer_factor = 0.9

    # Elke thuiswedstrijddag telt als een fikse boost bovenop een gemiddelde
    # dag -- een ruwe aanname (30% meer verkoop per wedstrijddag), niet
    # afgeleid uit eigen historie omdat daar simpelweg nog te weinig
    # gekoppelde agenda- en omzetgegevens voor zijn.
    wedstrijd_factor = 1 + 0.3 * aantal_wedstrijddagen
    periode_factor = dagen_vooruit / 7

    reeds_gesignaleerd = {p["id"] for p in bestel_suggesties(db)}

    resultaat = []
    for p in db.execute("SELECT * FROM producten WHERE actief = 1").fetchall():
        if p["id"] in reeds_gesignaleerd:
            continue
        gem_per_week = verkoop_per_product.get(p["id"], 0) / verstreken_weken
        verwacht_verbruik = gem_per_week * periode_factor * wedstrijd_factor * weer_factor
        verwachte_voorraad = p["voorraad"] - verwacht_verbruik
        if verwacht_verbruik > 0 and verwachte_voorraad < 0:
            resultaat.append(
                {
                    "product": p,
                    "verwacht_verbruik": round(verwacht_verbruik),
                    "verwacht_tekort": round(-verwachte_voorraad),
                }
            )
    resultaat.sort(key=lambda x: x["verwacht_tekort"], reverse=True)
    return resultaat


def bereken_laatste_telling_status(db):
    """Status van de laatste voorraadtelling voor het statusblokje op het
    dashboard: groen binnen 7 dagen, rood daarboven (of als er nog nooit
    geteld is)."""
    laatste = db.execute("SELECT * FROM tellingen ORDER BY datum DESC, id DESC LIMIT 1").fetchone()
    if laatste is None:
        return {"laatste": None, "dagen_geleden": None, "ok": False}
    dagen_geleden = (datetime.now() - datetime.strptime(laatste["datum"], "%Y-%m-%d %H:%M")).days
    return {"laatste": laatste, "dagen_geleden": dagen_geleden, "ok": dagen_geleden <= 7}


def bereken_kassa_telling_status(db):
    """Status van het statusblokje 'Kassa tellen'. Twee regels:
    - Algemeen: minstens 1x per 7 dagen geteld -> groen.
    - Na een thuiswedstrijd: binnen 3 dagen daarna geteld -> groen; meer dan
      3 dagen verstreken zonder telling sinds die wedstrijd -> rood (gaat
      voor de algemene regel, want geld na een wedstrijd moet tijdig
      afgehandeld worden). Binnen de eerste 3 dagen na een wedstrijd zonder
      telling is het nog niet mis: neutraal.

    Staat de allerlaatste telling nog open (concept, nog niet afgesloten),
    dan gaat dat voor alle andere regels: oranje."""
    laatste_ooit = db.execute(
        "SELECT * FROM kassa_tellingen ORDER BY datum DESC, id DESC LIMIT 1"
    ).fetchone()
    if laatste_ooit is not None and not laatste_ooit["afgesloten"]:
        return {
            "status": "oranje",
            "tekst": "Concept, nog niet afgesloten",
            "laatste_kassatelling": laatste_ooit,
        }

    vandaag = date.today()
    laatste_wedstrijd = db.execute(
        "SELECT datum FROM wedstrijden WHERE thuis = 1 AND datum <= ? ORDER BY datum DESC LIMIT 1",
        (vandaag.isoformat(),),
    ).fetchone()
    laatste_kassatelling = db.execute(
        "SELECT * FROM kassa_tellingen WHERE afgesloten = 1 ORDER BY datum DESC, id DESC LIMIT 1"
    ).fetchone()

    dagen_sinds_telling = None
    if laatste_kassatelling is not None:
        dagen_sinds_telling = (
            datetime.now() - datetime.strptime(laatste_kassatelling["datum"], "%Y-%m-%d %H:%M")
        ).days

    wedstrijd_datum = None
    geteld_na_wedstrijd = False
    if laatste_wedstrijd is not None:
        wedstrijd_datum = datetime.strptime(laatste_wedstrijd["datum"], "%Y-%m-%d").date()
        geteld_na_wedstrijd = (
            laatste_kassatelling is not None
            and datetime.strptime(laatste_kassatelling["datum"], "%Y-%m-%d %H:%M").date()
            >= wedstrijd_datum
        )
        wedstrijd_deadline_gemist = (
            not geteld_na_wedstrijd and (vandaag - wedstrijd_datum).days > 3
        )
    else:
        wedstrijd_deadline_gemist = False

    if wedstrijd_deadline_gemist:
        status = "rood"
        tekst = f"Nog niet geteld sinds wedstrijd van {wedstrijd_datum.strftime('%d-%m')}"
    elif dagen_sinds_telling is not None and dagen_sinds_telling <= 7:
        status = "groen"
        tekst = (
            "Kassa geteld sinds laatste wedstrijd" if geteld_na_wedstrijd else "Recent geteld"
        )
    elif laatste_wedstrijd is not None and not geteld_na_wedstrijd:
        deadline = wedstrijd_datum + timedelta(days=3)
        status = "neutraal"
        tekst = f"Nog tijd tot {deadline.strftime('%d-%m')}"
    else:
        status = "rood"
        tekst = "Meer dan 7 dagen niet geteld" if laatste_kassatelling else "Nog nooit geteld"

    return {"status": status, "tekst": tekst, "laatste_kassatelling": laatste_kassatelling}


def bereken_bestelling_status(db):
    """Status van het statusblokje 'Bestelling inboeken'. Oranje zolang er
    nog een openstaande bestelling is (besteld, nog niet ontvangen) --
    gaat voor de andere regels. Anders: groen als de laatst ontvangen
    bestelling binnen 7 dagen was, rood daarboven (of als er nog nooit een
    bestelling ontvangen is)."""
    open_bestelling = db.execute(
        "SELECT * FROM bestellingen WHERE status = 'besteld' ORDER BY aangemaakt_op DESC LIMIT 1"
    ).fetchone()
    if open_bestelling is not None:
        return {"status": "oranje", "tekst": "Nog niet ingeboekt", "laatste_bestelling": open_bestelling}

    laatste_ontvangen = db.execute(
        "SELECT * FROM bestellingen WHERE status = 'ontvangen' ORDER BY ontvangen_op DESC LIMIT 1"
    ).fetchone()
    if laatste_ontvangen is None:
        return {"status": "rood", "tekst": "Nog nooit ontvangen", "laatste_bestelling": None}

    dagen_geleden = (
        datetime.now() - datetime.strptime(laatste_ontvangen["ontvangen_op"], "%Y-%m-%d %H:%M")
    ).days
    if dagen_geleden <= 7:
        status = "groen"
        tekst = f"{dagen_geleden} dag{'' if dagen_geleden == 1 else 'en'} geleden"
    else:
        status = "rood"
        tekst = "Meer dan 7 dagen niet ontvangen"

    return {"status": status, "tekst": tekst, "laatste_bestelling": laatste_ontvangen}


def vind_getagde_gebruikers(db, tekst):
    """Zoekt @naam-vermeldingen in tekst en matcht ze tegen bestaande
    gebruikersnamen (hoofdletterongevoelig). Geeft de bijbehorende
    gebruikersrijen terug, zonder duplicaten."""
    namen = {m.group(1).lower() for m in TAG_PATROON.finditer(tekst)}
    if not namen:
        return []
    gebruikers = db.execute("SELECT * FROM gebruikers").fetchall()
    gezien = set()
    resultaat = []
    for g in gebruikers:
        if g["naam"].lower() in namen and g["id"] not in gezien:
            gezien.add(g["id"])
            resultaat.append(g)
    return resultaat


def stuur_tag_notificaties(db, tekst, wie_plaatste, omschrijving, link):
    """Mailt elke getagde gebruiker (met een e-mailadres, en niet de
    plaatser zelf) een korte melding. Een mislukte mail mag het plaatsen
    van de mededeling/opmerking nooit laten mislukken -- stuur_mail() vangt
    dat zelf al af."""
    for gebruiker in vind_getagde_gebruikers(db, tekst):
        if gebruiker["naam"] == wie_plaatste or not gebruiker["email"]:
            continue
        mail.stuur_mail(
            f"Je bent getagd op het prikbord: {omschrijving}",
            f"{wie_plaatste or 'Iemand'} tagde je op het prikbord:\n\n"
            f"\"{tekst}\"\n\nBekijk het op {link}",
            naar=gebruiker["email"],
        )


def met_tags_filter(tekst):
    """Jinja-filter: rendert @naam-vermeldingen als een opvallend label. De
    tekst wordt eerst zelf ge-escaped (het staat verder los van autoescape,
    dus dat gebeurt hier handmatig) en pas daarna vervangen we de
    @vermeldingen door veilige, vaste HTML."""
    escaped = str(escape(tekst or ""))

    def vervang(match):
        return f'<span class="tag-mention">@{escape(match.group(1))}</span>'

    return Markup(TAG_PATROON.sub(vervang, escaped))


def stemming_is_open(stemvraag):
    """Een stemming is open als hij niet handmatig gesloten is EN de
    (optionele) einddatum nog niet is verstreken. sluit_op wordt bewaard
    als einde van die dag ("YYYY-MM-DD 23:59"), dus een gewone
    stringvergelijking met now_str() volstaat."""
    if not stemvraag["actief"]:
        return False
    if stemvraag["sluit_op"] and stemvraag["sluit_op"] < now_str():
        return False
    return True


def tel_stemmers(db, stemvraag_id):
    """Aantal unieke stemmers (niet het aantal uitgebrachte keuzes) -- bij
    stemvragen met aantal_keuzes > 1 brengt 1 stemmer meerdere stemmen uit,
    dus is dit de juiste noemer voor percentages in de uitslag."""
    return db.execute(
        "SELECT COUNT(DISTINCT kiezer_sleutel) AS n FROM stemmen WHERE stemvraag_id = ? AND afgekeurd = 0",
        (stemvraag_id,),
    ).fetchone()["n"]


def register_routes(app):
    # ---------- Inloggen / accounts ----------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "gebruiker_id" in session:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            wachtwoord = request.form.get("wachtwoord", "")
            db = get_db()

            poging = db.execute(
                "SELECT * FROM login_pogingen WHERE naam = ?", (naam,)
            ).fetchone()
            mislukte_pogingen = poging["mislukte_pogingen"] if poging else 0
            if poging and poging["geblokkeerd_tot"]:
                geblokkeerd_tot = datetime.strptime(
                    poging["geblokkeerd_tot"], "%Y-%m-%d %H:%M"
                )
                if geblokkeerd_tot > datetime.now():
                    resterend = max(
                        1, round((geblokkeerd_tot - datetime.now()).total_seconds() / 60)
                    )
                    flash(
                        f"Te veel mislukte inlogpogingen. Probeer het over ongeveer "
                        f"{resterend} minuut(en) opnieuw.",
                        "error",
                    )
                    return render_template("login.html")
                # Blokkade is verlopen -- weer met een schone lei beginnen.
                mislukte_pogingen = 0

            gebruiker = db.execute(
                "SELECT * FROM gebruikers WHERE naam = ?", (naam,)
            ).fetchone()
            if gebruiker and check_password_hash(gebruiker["wachtwoord_hash"], wachtwoord):
                db.execute("DELETE FROM login_pogingen WHERE naam = ?", (naam,))
                session.clear()
                session["gebruiker_id"] = gebruiker["id"]
                session["gebruiker_naam"] = gebruiker["naam"]
                session["gebruiker_rol"] = gebruiker["rol"]
                db.execute(
                    "UPDATE gebruikers SET laatste_login = ? WHERE id = ?",
                    (now_str(), gebruiker["id"]),
                )
                db.commit()
                volgende = veilig_redirect_pad(request.args.get("next"), url_for("dashboard"))
                return redirect(volgende)

            nieuw_aantal = mislukte_pogingen + 1
            nieuwe_blokkade = None
            if nieuw_aantal >= LOGIN_MAX_POGINGEN:
                nieuwe_blokkade = (
                    datetime.now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTEN)
                ).strftime("%Y-%m-%d %H:%M")
            if poging:
                db.execute(
                    """UPDATE login_pogingen
                       SET mislukte_pogingen = ?, laatste_poging = ?, geblokkeerd_tot = ?
                       WHERE naam = ?""",
                    (nieuw_aantal, now_str(), nieuwe_blokkade, naam),
                )
            else:
                db.execute(
                    """INSERT INTO login_pogingen
                       (naam, mislukte_pogingen, laatste_poging, geblokkeerd_tot)
                       VALUES (?, ?, ?, ?)""",
                    (naam, nieuw_aantal, now_str(), nieuwe_blokkade),
                )
            db.commit()

            if nieuwe_blokkade:
                flash(
                    f"Te veel mislukte inlogpogingen. Probeer het over ongeveer "
                    f"{LOGIN_LOCKOUT_MINUTEN} minuten opnieuw.",
                    "error",
                )
            else:
                flash("Onjuiste naam of wachtwoord.", "error")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Je bent uitgelogd.", "success")
        return redirect(url_for("login"))

    @app.route("/wachtwoord-vergeten", methods=["GET", "POST"])
    def wachtwoord_vergeten():
        if request.method == "POST":
            identificatie = request.form.get("naam_of_email", "").strip()
            db = get_db()
            gebruiker = db.execute(
                "SELECT * FROM gebruikers WHERE naam = ? OR email = ?",
                (identificatie, identificatie),
            ).fetchone()
            if gebruiker and gebruiker["email"]:
                token = genereer_wachtwoord_token(db, gebruiker["id"], geldig_uren=24)
                link = url_for("wachtwoord_instellen", token=token, _external=True)
                mail.stuur_mail(
                    "Kantine Beheer: wachtwoord opnieuw instellen",
                    f"Hoi {gebruiker['naam']},\n\n"
                    f"Er is een verzoek gedaan om je wachtwoord opnieuw in te stellen.\n"
                    f"Gebruik onderstaande link om een nieuw wachtwoord te kiezen "
                    f"(deze link is 24 uur geldig):\n\n"
                    f"{link}\n\n"
                    f"Heb je dit zelf niet aangevraagd? Dan kun je deze e-mail negeren.",
                    naar=gebruiker["email"],
                )
            flash(
                "Als dit account bestaat en er een e-mailadres bekend is, is er een "
                "e-mail met een link verstuurd.",
                "success",
            )
            return redirect(url_for("login"))

        return render_template("wachtwoord_vergeten.html")

    @app.route("/wachtwoord-instellen/<token>", methods=["GET", "POST"])
    def wachtwoord_instellen(token):
        db = get_db()
        gebruiker = vind_gebruiker_bij_token(db, token)
        if gebruiker is None:
            flash("Deze link is ongeldig of verlopen. Vraag een nieuwe aan.", "error")
            return redirect(url_for("wachtwoord_vergeten"))

        if request.method == "POST":
            nieuw = request.form.get("nieuw_wachtwoord", "")
            nieuw_herhaald = request.form.get("nieuw_wachtwoord_herhaald", "")
            if len(nieuw) < 4:
                flash("Wachtwoord moet minstens 4 tekens zijn.", "error")
            elif nieuw != nieuw_herhaald:
                flash("De wachtwoorden komen niet overeen.", "error")
            else:
                db.execute(
                    """UPDATE gebruikers
                       SET wachtwoord_hash = ?, reset_token_hash = NULL, reset_token_verloopt = NULL
                       WHERE id = ?""",
                    (generate_password_hash(nieuw, method="pbkdf2:sha256"), gebruiker["id"]),
                )
                db.execute(
                    "UPDATE gebruikers SET laatste_login = ? WHERE id = ?",
                    (now_str(), gebruiker["id"]),
                )
                db.commit()
                session.clear()
                session["gebruiker_id"] = gebruiker["id"]
                session["gebruiker_naam"] = gebruiker["naam"]
                session["gebruiker_rol"] = gebruiker["rol"]
                flash("Wachtwoord ingesteld. Je bent nu ingelogd.", "success")
                return redirect(url_for("dashboard"))

        return render_template("wachtwoord_instellen.html", gebruiker=gebruiker, token=token)

    @app.route("/accounts")
    def accounts_lijst():
        db = get_db()
        gebruikers = db.execute(
            "SELECT id, naam, email, rol, aangemaakt_op, laatste_login FROM gebruikers ORDER BY naam"
        ).fetchall()
        aantal_beheerders = db.execute(
            "SELECT COUNT(*) AS n FROM gebruikers WHERE rol = 'beheerder'"
        ).fetchone()["n"]
        return render_template(
            "accounts.html", gebruikers=gebruikers, aantal_beheerders=aantal_beheerders
        )

    @app.route("/accounts/nieuw", methods=["POST"])
    def account_nieuw():
        naam = request.form.get("naam", "").strip()
        email = request.form.get("email", "").strip()
        rol = request.form.get("rol", "vrijwilliger")
        if rol not in ("beheerder", "vrijwilliger"):
            rol = "vrijwilliger"
        db = get_db()

        if not naam or not email:
            flash("Naam en e-mailadres zijn verplicht.", "error")
        elif db.execute("SELECT id FROM gebruikers WHERE naam = ?", (naam,)).fetchone():
            flash(f"Er bestaat al een account met de naam '{naam}'.", "error")
        else:
            onbruikbaar_wachtwoord = generate_password_hash(
                secrets.token_hex(16), method="pbkdf2:sha256"
            )
            cursor = db.execute(
                """INSERT INTO gebruikers (naam, email, wachtwoord_hash, rol, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?)""",
                (naam, email, onbruikbaar_wachtwoord, rol, now_str()),
            )
            db.commit()
            token = genereer_wachtwoord_token(db, cursor.lastrowid, geldig_uren=72)
            link = url_for("wachtwoord_instellen", token=token, _external=True)
            mail.stuur_mail(
                "Welkom bij Kantine Beheer",
                f"Hoi {naam},\n\n"
                f"Er is een account voor je aangemaakt in het voorraadsysteem van de kantine.\n"
                f"Kies via onderstaande link je eigen wachtwoord (deze link is 72 uur geldig):\n\n"
                f"{link}\n\n"
                f"Je gebruikersnaam is: {naam}",
                naar=email,
            )
            flash(
                f"Account '{naam}' aangemaakt. Er is een e-mail verstuurd naar {email} "
                "om een wachtwoord in te stellen.",
                "success",
            )
        return redirect(url_for("accounts_lijst"))

    @app.route("/accounts/<int:gebruiker_id>/email", methods=["POST"])
    def account_email_wijzigen(gebruiker_id):
        db = get_db()
        email = request.form.get("email", "").strip()
        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        if gebruiker is None:
            flash("Account niet gevonden.", "error")
        else:
            db.execute(
                "UPDATE gebruikers SET email = ? WHERE id = ?", (email or None, gebruiker_id)
            )
            db.commit()
            flash(f"E-mailadres van '{gebruiker['naam']}' bijgewerkt.", "success")
        return redirect(url_for("accounts_lijst"))

    @app.route("/accounts/<int:gebruiker_id>/rol", methods=["POST"])
    def account_rol_wijzigen(gebruiker_id):
        db = get_db()
        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        if gebruiker is None:
            flash("Account niet gevonden.", "error")
            return redirect(url_for("accounts_lijst"))

        nieuwe_rol = "vrijwilliger" if gebruiker["rol"] == "beheerder" else "beheerder"
        if gebruiker["rol"] == "beheerder" and nieuwe_rol == "vrijwilliger":
            aantal_beheerders = db.execute(
                "SELECT COUNT(*) AS n FROM gebruikers WHERE rol = 'beheerder'"
            ).fetchone()["n"]
            if aantal_beheerders <= 1:
                flash(
                    "Dit is de laatste beheerder. Er moet altijd minstens één overblijven.",
                    "error",
                )
                return redirect(url_for("accounts_lijst"))

        db.execute("UPDATE gebruikers SET rol = ? WHERE id = ?", (nieuwe_rol, gebruiker_id))
        db.commit()
        flash(f"'{gebruiker['naam']}' is nu {nieuwe_rol}.", "success")
        return redirect(url_for("accounts_lijst"))

    @app.route("/accounts/<int:gebruiker_id>/verwijderen", methods=["POST"])
    def account_verwijderen(gebruiker_id):
        db = get_db()
        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        aantal = db.execute("SELECT COUNT(*) AS n FROM gebruikers").fetchone()["n"]
        if gebruiker is None:
            flash("Account niet gevonden.", "error")
        elif aantal <= 1:
            flash("Je kunt het laatste account niet verwijderen.", "error")
        elif gebruiker_id == session.get("gebruiker_id"):
            flash("Je kunt je eigen account niet verwijderen terwijl je bent ingelogd.", "error")
        elif gebruiker["rol"] == "beheerder" and db.execute(
            "SELECT COUNT(*) AS n FROM gebruikers WHERE rol = 'beheerder'"
        ).fetchone()["n"] <= 1:
            flash(
                "Dit is de laatste beheerder. Er moet altijd minstens één overblijven.",
                "error",
            )
        else:
            db.execute("DELETE FROM gebruikers WHERE id = ?", (gebruiker_id,))
            db.commit()
            flash("Account verwijderd.", "success")
        return redirect(url_for("accounts_lijst"))

    @app.route("/account/wachtwoord", methods=["GET", "POST"])
    def account_wachtwoord():
        if request.method == "POST":
            huidig = request.form.get("huidig_wachtwoord", "")
            nieuw = request.form.get("nieuw_wachtwoord", "")
            nieuw_herhaald = request.form.get("nieuw_wachtwoord_herhaald", "")
            db = get_db()
            gebruiker = db.execute(
                "SELECT * FROM gebruikers WHERE id = ?", (session["gebruiker_id"],)
            ).fetchone()

            if not check_password_hash(gebruiker["wachtwoord_hash"], huidig):
                flash("Huidig wachtwoord is onjuist.", "error")
            elif len(nieuw) < 4:
                flash("Nieuw wachtwoord moet minstens 4 tekens zijn.", "error")
            elif nieuw != nieuw_herhaald:
                flash("Nieuwe wachtwoorden komen niet overeen.", "error")
            else:
                db.execute(
                    "UPDATE gebruikers SET wachtwoord_hash = ? WHERE id = ?",
                    (generate_password_hash(nieuw, method="pbkdf2:sha256"), gebruiker["id"]),
                )
                db.commit()
                flash("Wachtwoord gewijzigd.", "success")
                return redirect(url_for("dashboard"))

        return render_template("account_wachtwoord.html")

    @app.route("/account/voorkeuren", methods=["GET", "POST"])
    def account_voorkeuren():
        db = get_db()
        gebruiker_id = session["gebruiker_id"]
        if request.method == "POST":
            db.execute(
                "UPDATE gebruikers SET mail_factuur = ?, mail_week_overzicht = ? WHERE id = ?",
                (
                    1 if request.form.get("mail_factuur") else 0,
                    1 if request.form.get("mail_week_overzicht") else 0,
                    gebruiker_id,
                ),
            )
            db.commit()
            flash("Voorkeuren opgeslagen.", "success")
            return redirect(url_for("account_voorkeuren"))

        gebruiker = db.execute(
            "SELECT * FROM gebruikers WHERE id = ?", (gebruiker_id,)
        ).fetchone()
        return render_template("account_voorkeuren.html", gebruiker=gebruiker)

    @app.route("/help")
    def help_pagina():
        return render_template(
            "help.html", huidige_versie=HUIDIGE_VERSIE, wijzigingen=WIJZIGINGEN
        )

    # ---------- Instellingen ----------

    @app.route("/instellingen", methods=["GET", "POST"])
    def instellingen_pagina():
        db = get_db()
        if request.method == "POST":
            notificatie_email = request.form.get("notificatie_email", "").strip()
            banner_tekst = request.form.get("banner_tekst", "").strip()
            db.execute(
                "UPDATE instellingen SET notificatie_email = ?, banner_tekst = ? WHERE id = 1",
                (notificatie_email or None, banner_tekst or None),
            )
            db.commit()
            flash("Instellingen opgeslagen.", "success")
            return redirect(url_for("instellingen_pagina"))

        rij = db.execute(
            "SELECT notificatie_email, banner_tekst FROM instellingen WHERE id = 1"
        ).fetchone()
        return render_template(
            "instellingen.html",
            notificatie_email=rij["notificatie_email"] if rij else None,
            banner_tekst=rij["banner_tekst"] if rij else None,
        )

    # ---------- Club instellingen (teamagenda's) ----------

    @app.route("/club-instellingen")
    def club_instellingen():
        db = get_db()
        feeds = db.execute("SELECT * FROM agenda_feeds ORDER BY id").fetchall()
        aantal_wedstrijden = db.execute(
            "SELECT COUNT(*) AS n FROM wedstrijden WHERE datum >= ?", (date.today().isoformat(),)
        ).fetchone()["n"]
        return render_template(
            "club_instellingen.html",
            feeds=feeds,
            aantal_wedstrijden=aantal_wedstrijden,
        )

    @app.route("/club-instellingen/toevoegen", methods=["POST"])
    def club_agenda_toevoegen():
        url = request.form.get("url", "").strip()
        if not url:
            flash("Vul een agenda-link in.", "error")
        else:
            db = get_db()
            db.execute("INSERT INTO agenda_feeds (url) VALUES (?)", (url,))
            db.commit()
            flash("Agenda-link toegevoegd. Klik op 'Nu verversen' om 'm op te halen.", "success")
        return redirect(url_for("club_instellingen"))

    @app.route("/club-instellingen/<int:feed_id>/verwijderen", methods=["POST"])
    def club_agenda_verwijderen(feed_id):
        db = get_db()
        db.execute("DELETE FROM agenda_feeds WHERE id = ?", (feed_id,))
        db.commit()
        flash("Agenda-link verwijderd.", "success")
        return redirect(url_for("club_instellingen"))

    @app.route("/club-instellingen/verversen", methods=["POST"])
    def club_agenda_verversen():
        aantal = agenda.ververs_wedstrijden(db_pad=app.config["DATABASE"])
        if aantal is None:
            flash("Geen agenda-links ingesteld om te verversen.", "error")
        else:
            flash(f"Agenda's ververst: {aantal} nieuwe wedstrijden toegevoegd.", "success")
        return redirect(url_for("club_instellingen"))

    @app.route("/club-instellingen/controleren", methods=["POST"])
    def club_agenda_controleren():
        db = get_db()
        urls = [r["url"] for r in db.execute("SELECT url FROM agenda_feeds").fetchall()]
        if not urls:
            flash("Geen agenda-links om te controleren.", "error")
        else:
            for resultaat in agenda.controleer_feeds(urls):
                if resultaat["ok"]:
                    flash(
                        f"{resultaat['team']}: bereikbaar, {resultaat['aantal']} wedstrijden gevonden.",
                        "success",
                    )
                else:
                    flash(f"Link mislukt ({resultaat['url']}): {resultaat['fout']}", "error")
        return redirect(url_for("club_instellingen"))

    # ---------- Back-ups ----------

    @app.route("/backups")
    def backups_lijst():
        backup_module.BACKUP_MAP.mkdir(exist_ok=True)
        bestanden = sorted(
            backup_module.BACKUP_MAP.glob("voorraad-*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        backups = [
            {
                "naam": b.name,
                "grootte_kb": round(b.stat().st_size / 1024, 1),
                "datum": datetime.fromtimestamp(b.stat().st_mtime).strftime(
                    "%d-%m-%Y %H:%M"
                ),
            }
            for b in bestanden
        ]
        return render_template("backups.html", backups=backups)

    @app.route("/backups/nu", methods=["POST"])
    def backup_nu():
        resultaat = backup_module.maak_backup()
        if resultaat is None:
            flash("Nog geen voorraad.db aanwezig om te back-uppen.", "error")
        else:
            flash(f"Back-up gemaakt: {resultaat.name}", "success")
        return redirect(url_for("backups_lijst"))

    @app.route("/backups/<bestandsnaam>/download")
    def backup_download(bestandsnaam):
        if not BACKUP_BESTANDSNAAM.match(bestandsnaam):
            flash("Ongeldige back-up.", "error")
            return redirect(url_for("backups_lijst"))
        return send_from_directory(
            backup_module.BACKUP_MAP, bestandsnaam, as_attachment=True
        )

    @app.route("/backups/<bestandsnaam>/herstellen", methods=["POST"])
    def backup_herstellen(bestandsnaam):
        if not BACKUP_BESTANDSNAAM.match(bestandsnaam):
            flash("Ongeldige back-up.", "error")
            return redirect(url_for("backups_lijst"))

        veiligheidskopie_naam = (
            f"voorraad-voor-herstel-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        )
        backup_module.maak_backup_met_naam(veiligheidskopie_naam)

        if backup_module.herstel_backup(bestandsnaam):
            flash(
                f"Database hersteld vanaf '{bestandsnaam}'. De staat van vlak "
                f"hiervoor is bewaard als '{veiligheidskopie_naam}', voor het "
                f"geval je dit ongedaan wilt maken.",
                "success",
            )
        else:
            flash("Herstellen is mislukt: back-up niet gevonden.", "error")
        return redirect(url_for("dashboard"))

    # ---------- Overzicht ----------

    def bereken_omzet_trend(db, aantal_dagen=8):
        """Omzet per dag (chronologisch, tellingen van dezelfde dag samengevoegd
        tot één balk) plus de best verkopende producten over die periode --
        gebruikt voor het trendgrafiekje op het dashboard. Rekent altijd met
        de bevroren telling-prijs (tr.verkoopprijs), niet de actuele
        productprijs, om dezelfde reden als het verkooprapport."""
        ruwe_dagen = db.execute(
            """SELECT date(t.datum) AS dag,
                      COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0) AS omzet
               FROM tellingen t
               LEFT JOIN telling_regels tr ON tr.telling_id = t.id
               GROUP BY dag
               ORDER BY dag DESC
               LIMIT ?""",
            (aantal_dagen,),
        ).fetchall()
        dagen = list(reversed(ruwe_dagen))

        top_verkopers = []
        if dagen:
            dag_lijst = [d["dag"] for d in dagen]
            placeholders = ",".join("?" for _ in dag_lijst)
            top_verkopers = db.execute(
                f"""SELECT p.naam AS product_naam, p.eenheid,
                           SUM(tr.verkocht) AS verkocht,
                           SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                    FROM telling_regels tr
                    JOIN producten p ON p.id = tr.product_id
                    JOIN tellingen t ON t.id = tr.telling_id
                    WHERE date(t.datum) IN ({placeholders})
                    GROUP BY tr.product_id
                    HAVING SUM(tr.verkocht) > 0
                    ORDER BY omzet DESC
                    LIMIT 6""",
                dag_lijst,
            ).fetchall()

        max_omzet = max((d["omzet"] for d in dagen), default=0)
        laatste_omzet = dagen[-1]["omzet"] if dagen else 0
        eerdere_omzetten = [d["omzet"] for d in dagen[:-1]]
        gemiddelde_omzet = (
            sum(eerdere_omzetten) / len(eerdere_omzetten) if eerdere_omzetten else 0
        )
        verschil_percentage = None
        if gemiddelde_omzet > 0:
            verschil_percentage = (laatste_omzet - gemiddelde_omzet) / gemiddelde_omzet * 100

        balken = [
            {
                "datum_kort": datetime.strptime(d["dag"], "%Y-%m-%d").strftime("%d-%m"),
                "omzet": d["omzet"],
                "hoogte_pct": (d["omzet"] / max_omzet * 100) if max_omzet else 0,
            }
            for d in dagen
        ]

        return {
            "balken": balken,
            "top_verkopers": top_verkopers,
            "laatste_omzet": laatste_omzet,
            "gemiddelde_omzet": gemiddelde_omzet,
            "verschil_percentage": verschil_percentage,
        }

    @app.route("/")
    def dashboard():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        laag = [p for p in producten if p["voorraad"] < p["min_voorraad"]]
        recente_mutaties = db.execute(
            """SELECT m.*, p.naam AS product_naam, p.eenheid
               FROM mutaties m JOIN producten p ON p.id = m.product_id
               ORDER BY m.id DESC LIMIT 8"""
        ).fetchall()
        open_bestellingen = db.execute(
            "SELECT COUNT(*) AS n FROM bestellingen WHERE status = 'besteld'"
        ).fetchone()["n"]
        omzet_trend = bereken_omzet_trend(db)
        komende_thuiswedstrijden = bereken_komende_thuiswedstrijden(db)
        return render_template(
            "dashboard.html",
            producten=producten,
            laag=laag,
            recente_mutaties=recente_mutaties,
            open_bestellingen=open_bestellingen,
            omzet_trend=omzet_trend,
            komende_thuiswedstrijden=komende_thuiswedstrijden,
            laatste_telling_status=bereken_laatste_telling_status(db),
            kassa_telling_status=bereken_kassa_telling_status(db),
            bestelling_status=bereken_bestelling_status(db),
        )

    def bereken_voorraadoverzicht(db):
        """Verzamelt alle cijfers voor het voorraadoverzicht -- gebruikt door
        zowel de webpagina als de PDF, zodat ze altijd hetzelfde tonen."""
        producten = db.execute("SELECT * FROM producten ORDER BY categorie, naam").fetchall()
        niet_verplicht = categorienamen_zonder_verkoopprijsplicht(db)

        totale_waarde = sum(p["voorraad"] * p["verkoopprijs"] for p in producten)
        zonder_voorraad = [p for p in producten if p["actief"] and p["voorraad"] == 0]
        onder_minimum = [p for p in producten if p["actief"] and p["voorraad"] < p["min_voorraad"]]
        zonder_prijs = [
            p for p in producten
            if p["actief"] and p["verkoopprijs"] == 0 and p["categorie"] not in niet_verplicht
        ]
        inactief_met_voorraad = [p for p in producten if not p["actief"] and p["voorraad"] > 0]

        per_categorie = {}
        for p in producten:
            c = per_categorie.setdefault(p["categorie"], {"aantal": 0, "waarde": 0.0, "subcats": {}})
            c["aantal"] += 1
            c["waarde"] += p["voorraad"] * p["verkoopprijs"]
            sub = c["subcats"].setdefault(p["subcategorie"], {"aantal": 0, "waarde": 0.0})
            sub["aantal"] += 1
            sub["waarde"] += p["voorraad"] * p["verkoopprijs"]

        def _subcategorie_lijst(info):
            # Alleen tonen als er binnen deze categorie echt subcategorieën in
            # gebruik zijn -- anders levert elke categorie een nietszeggende
            # "Overig 100%"-regel op.
            if not any(naam is not None for naam in info["subcats"]):
                return []
            return sorted(
                [
                    {
                        "naam": naam or "Overig",
                        "aantal": sub_info["aantal"],
                        "waarde": sub_info["waarde"],
                        "percentage": (sub_info["waarde"] / info["waarde"] * 100) if info["waarde"] else 0,
                    }
                    for naam, sub_info in info["subcats"].items()
                ],
                key=lambda x: x["waarde"],
                reverse=True,
            )

        categorie_lijst = sorted(
            [
                {
                    "naam": naam,
                    "aantal": info["aantal"],
                    "waarde": info["waarde"],
                    "percentage": (info["waarde"] / totale_waarde * 100) if totale_waarde else 0,
                    "subcategorieen": _subcategorie_lijst(info),
                }
                for naam, info in per_categorie.items()
            ],
            key=lambda x: x["waarde"],
            reverse=True,
        )

        top_waarde = sorted(
            producten, key=lambda p: p["voorraad"] * p["verkoopprijs"], reverse=True
        )[:10]

        laatste_tellingen = db.execute(
            """SELECT tr.product_id, MAX(t.datum) AS laatste_datum
               FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
               GROUP BY tr.product_id"""
        ).fetchall()
        laatste_per_product = {r["product_id"]: r["laatste_datum"] for r in laatste_tellingen}
        nooit_geteld = [p for p in producten if p["actief"] and p["id"] not in laatste_per_product]
        langst_niet_geteld = sorted(
            (
                {"product": p, "laatste_datum": laatste_per_product[p["id"]]}
                for p in producten
                if p["actief"] and p["id"] in laatste_per_product
            ),
            key=lambda x: x["laatste_datum"],
        )[:5]

        return {
            "producten": producten,
            "totale_waarde": totale_waarde,
            "aantal_producten": len(producten),
            "aantal_categorieen": len(per_categorie),
            "zonder_voorraad": zonder_voorraad,
            "onder_minimum": onder_minimum,
            "zonder_prijs": zonder_prijs,
            "inactief_met_voorraad": inactief_met_voorraad,
            "nooit_geteld": nooit_geteld,
            "categorie_lijst": categorie_lijst,
            "top_waarde": top_waarde,
            "langst_niet_geteld": langst_niet_geteld,
        }

    @app.route("/voorraadoverzicht")
    def voorraadoverzicht():
        db = get_db()
        return render_template(
            "voorraadoverzicht.html", **bereken_voorraadoverzicht(db)
        )

    @app.route("/voorraadoverzicht/pdf")
    def voorraadoverzicht_pdf_route():
        db = get_db()
        gegevens = bereken_voorraadoverzicht(db)
        pdf_bytes = voorraadoverzicht_pdf(gegevens)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=voorraadoverzicht.pdf"},
        )

    @app.route("/voorraadoverzicht/csv")
    def voorraadoverzicht_csv_route():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten ORDER BY categorie, subcategorie, naam"
        ).fetchall()
        rijen = [
            (
                p["artikelcode"] or "",
                p["naam"],
                p["categorie"],
                p["subcategorie"] or "",
                p["voorraad"],
                p["eenheid"],
                p["min_voorraad"],
                f"{p['verkoopprijs']:.2f}".replace(".", ","),
                f"{p['voorraad'] * p['verkoopprijs']:.2f}".replace(".", ","),
                "Ja" if p["actief"] else "Nee",
            )
            for p in producten
        ]
        return csv_response(
            "voorraadoverzicht.csv",
            ["Artikelcode", "Naam", "Categorie", "Subcategorie", "Voorraad", "Eenheid",
             "Minimum", "Verkoopprijs", "Waarde", "Actief"],
            rijen,
        )

    # ---------- Producten ----------

    @app.route("/producten")
    def producten_lijst():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten ORDER BY actief DESC, categorie, subcategorie, naam"
        ).fetchall()
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = db.execute(
            "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
        ).fetchall()
        return render_template(
            "producten.html",
            producten=producten,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
            niet_verplicht_categorieen=categorienamen_zonder_verkoopprijsplicht(db),
        )

    @app.route("/producten/minimumvoorraad", methods=["GET", "POST"])
    def producten_minimumvoorraad():
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            aangepast = 0
            for p in producten:
                waarde = request.form.get(f"min_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    nieuw_minimum = int(waarde)
                except ValueError:
                    continue
                if nieuw_minimum < 0:
                    continue
                db.execute(
                    "UPDATE producten SET min_voorraad = ? WHERE id = ?",
                    (nieuw_minimum, p["id"]),
                )
                aangepast += 1
            db.commit()
            flash(f"Minimumvoorraad bijgewerkt voor {aangepast} product(en).", "success")
            return redirect(url_for("producten_minimumvoorraad"))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY actief DESC, categorie, naam"
        ).fetchall()
        return render_template("producten_minimum.html", producten=producten)

    @app.route("/producten/besteleenheid", methods=["GET", "POST"])
    def producten_besteleenheid():
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            aangepast = 0
            for p in producten:
                eenheid_waarde = request.form.get(f"eenheid_{p['id']}", "").strip()
                factor_waarde = request.form.get(f"factor_{p['id']}", "").strip()
                if factor_waarde == "":
                    continue
                try:
                    nieuwe_factor = int(factor_waarde)
                except ValueError:
                    continue
                if nieuwe_factor < 1:
                    continue
                db.execute(
                    "UPDATE producten SET besteleenheid = ?, besteleenheid_factor = ? WHERE id = ?",
                    (eenheid_waarde or None, nieuwe_factor, p["id"]),
                )
                aangepast += 1
            db.commit()
            flash(f"Besteleenheid bijgewerkt voor {aangepast} product(en).", "success")
            return redirect(url_for("producten_besteleenheid"))

        producten = db.execute(
            "SELECT * FROM producten ORDER BY actief DESC, categorie, naam"
        ).fetchall()
        return render_template("producten_besteleenheid.html", producten=producten)

    @app.route("/producten/nieuw", methods=["GET", "POST"])
    def product_nieuw():
        db = get_db()
        if request.method == "POST":
            afbeelding = sla_afbeelding_op(request.files.get("afbeelding"), PRODUCT_AFBEELDINGEN_MAP)
            categorie = request.form["categorie"].strip() or "Overig"
            subcategorie = request.form.get("subcategorie", "").strip() or None
            bewaar_subcategorie(db, categorie, subcategorie)
            db.execute(
                """INSERT INTO producten
                   (artikelcode, naam, categorie, subcategorie, eenheid, voorraad, min_voorraad,
                    bestel_hoeveelheid, verkoopprijs, inkoopprijs, actief, besteleenheid,
                    besteleenheid_factor, opmerking, afbeelding, glazen_per_fust, prijs_per_glas)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.form.get("artikelcode", "").strip() or None,
                    request.form["naam"].strip(),
                    categorie,
                    subcategorie,
                    request.form["eenheid"].strip() or "stuks",
                    int(request.form["voorraad"] or 0),
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    float(request.form["verkoopprijs"] or 0),
                    float(request.form.get("inkoopprijs") or 0),
                    1 if request.form.get("actief") else 0,
                    request.form.get("besteleenheid", "").strip() or None,
                    int(request.form.get("besteleenheid_factor") or 1),
                    request.form.get("opmerking", "").strip(),
                    afbeelding,
                    int(request.form.get("glazen_per_fust") or 0),
                    float(request.form.get("prijs_per_glas") or 0),
                ),
            )
            db.commit()
            flash(f"Product '{request.form['naam']}' toegevoegd.", "success")
            return redirect(url_for("producten_lijst"))
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = [
            dict(r)
            for r in db.execute(
                "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
            ).fetchall()
        ]
        return render_template(
            "product_form.html",
            product=None,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
        )

    @app.route("/producten/<int:product_id>/bewerken", methods=["GET", "POST"])
    def product_bewerken(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))

        if request.method == "POST":
            nieuwe_verkoopprijs = float(request.form["verkoopprijs"] or 0)
            nieuwe_inkoopprijs = float(request.form.get("inkoopprijs") or 0)
            nieuwe_afbeelding = sla_afbeelding_op(request.files.get("afbeelding"), PRODUCT_AFBEELDINGEN_MAP)
            if nieuwe_afbeelding:
                afbeelding = nieuwe_afbeelding
            elif request.form.get("afbeelding_verwijderen"):
                afbeelding = None
            else:
                afbeelding = product["afbeelding"]
            datum = now_str()
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            for veld, oude_prijs, nieuwe_prijs in (
                ("verkoopprijs", product["verkoopprijs"], nieuwe_verkoopprijs),
                ("inkoopprijs", product["inkoopprijs"], nieuwe_inkoopprijs),
            ):
                if abs(oude_prijs - nieuwe_prijs) > 0.001:
                    db.execute(
                        """INSERT INTO prijs_geschiedenis
                           (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (product_id, veld, oude_prijs, nieuwe_prijs, datum, naam, gebruiker_id),
                    )

            categorie = request.form["categorie"].strip() or "Overig"
            subcategorie = request.form.get("subcategorie", "").strip() or None
            bewaar_subcategorie(db, categorie, subcategorie)
            db.execute(
                """UPDATE producten
                   SET artikelcode = ?, naam = ?, categorie = ?, subcategorie = ?, eenheid = ?,
                       voorraad = ?, min_voorraad = ?, bestel_hoeveelheid = ?, verkoopprijs = ?,
                       inkoopprijs = ?, actief = ?, besteleenheid = ?, besteleenheid_factor = ?,
                       opmerking = ?, afbeelding = ?, glazen_per_fust = ?, prijs_per_glas = ?
                   WHERE id = ?""",
                (
                    request.form.get("artikelcode", "").strip() or None,
                    request.form["naam"].strip(),
                    categorie,
                    subcategorie,
                    request.form["eenheid"].strip() or "stuks",
                    int(request.form["voorraad"] or 0),
                    int(request.form["min_voorraad"] or 0),
                    int(request.form["bestel_hoeveelheid"] or 0),
                    nieuwe_verkoopprijs,
                    nieuwe_inkoopprijs,
                    1 if request.form.get("actief") else 0,
                    request.form.get("besteleenheid", "").strip() or None,
                    int(request.form.get("besteleenheid_factor") or 1),
                    request.form.get("opmerking", "").strip(),
                    afbeelding,
                    int(request.form.get("glazen_per_fust") or 0),
                    float(request.form.get("prijs_per_glas") or 0),
                    product_id,
                ),
            )
            db.commit()
            flash(f"Product '{request.form['naam']}' bijgewerkt.", "success")
            return redirect(url_for("producten_lijst"))
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        subcategorieen = [
            dict(r)
            for r in db.execute(
                "SELECT categorie, naam FROM subcategorieen ORDER BY categorie, naam"
            ).fetchall()
        ]
        prijs_geschiedenis = db.execute(
            """SELECT * FROM prijs_geschiedenis WHERE product_id = ?
               ORDER BY datum DESC, id DESC""",
            (product_id,),
        ).fetchall()
        return render_template(
            "product_form.html",
            product=product,
            categorieen=categorieen,
            subcategorieen=subcategorieen,
            prijs_geschiedenis=prijs_geschiedenis,
        )

    @app.route("/producten/<int:product_id>/verwijderen", methods=["POST"])
    def product_verwijderen(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product:
            db.execute("DELETE FROM producten WHERE id = ?", (product_id,))
            db.commit()
            flash(f"Product '{product['naam']}' verwijderd.", "success")
        return redirect(url_for("producten_lijst"))

    # Endpoints waar het snel-toevoegen-formulier (pop-up) naar mag
    # terugsturen. Whitelist i.p.v. een vrije URL, om open redirects te voorkomen.
    TERUG_NAAR_ENDPOINTS = {
        "levering_inboeken": "levering_inboeken",
        "producten_lijst": "producten_lijst",
    }

    @app.route("/producten/snel-toevoegen", methods=["POST"])
    def product_snel_toevoegen():
        db = get_db()
        terug_naar = TERUG_NAAR_ENDPOINTS.get(
            request.form.get("terug_naar", ""), "producten_lijst"
        )
        naam = request.form.get("naam", "").strip()

        if not naam:
            flash("Naam is verplicht.", "error")
            return redirect(url_for(terug_naar))

        db.execute(
            """INSERT INTO producten
               (artikelcode, naam, categorie, eenheid, voorraad, min_voorraad,
                bestel_hoeveelheid, verkoopprijs, actief, besteleenheid,
                besteleenheid_factor, opmerking)
               VALUES (?, ?, ?, ?, 0, 0, 0, 0, 1, ?, ?, '')""",
            (
                request.form.get("artikelcode", "").strip() or None,
                naam,
                request.form.get("categorie", "").strip() or "Overig",
                request.form.get("eenheid", "").strip() or "stuks",
                request.form.get("besteleenheid", "").strip() or None,
                int(request.form.get("besteleenheid_factor") or 1),
            ),
        )
        db.commit()
        flash(f"Product '{naam}' toegevoegd. Vul hieronder het aantal in.", "success")
        return redirect(url_for(terug_naar))

    @app.route("/producten/<int:product_id>/actief", methods=["POST"])
    def product_actief_wisselen(product_id):
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Product niet gevonden."}), 404
            flash("Product niet gevonden.", "error")
            return redirect(url_for("producten_lijst"))
        nieuwe_status = 0 if product["actief"] else 1
        db.execute(
            "UPDATE producten SET actief = ? WHERE id = ?", (nieuwe_status, product_id)
        )
        db.commit()
        if is_ajax_verzoek():
            melding = (
                f"'{product['naam']}' is actief. Komt bij de volgende paginalaad weer bovenaan te staan."
                if nieuwe_status
                else f"'{product['naam']}' is inactief. Zakt bij de volgende paginalaad naar onderen."
            )
            return jsonify({"ok": True, "actief": nieuwe_status, "melding": melding})
        return redirect(url_for("producten_lijst"))

    @app.route("/categorieen", methods=["GET", "POST"])
    def categorieen_lijst():
        db = get_db()
        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            if not naam:
                flash("Vul een naam in voor de categorie.", "error")
            else:
                bestaat = db.execute(
                    "SELECT id FROM categorieen WHERE naam = ?", (naam,)
                ).fetchone()
                if bestaat:
                    flash(f"Categorie '{naam}' bestaat al.", "error")
                else:
                    db.execute("INSERT INTO categorieen (naam) VALUES (?)", (naam,))
                    db.commit()
                    flash(f"Categorie '{naam}' toegevoegd.", "success")
            return redirect(url_for("categorieen_lijst"))

        categorieen = db.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM producten WHERE categorie = c.naam) AS aantal_producten
               FROM categorieen c ORDER BY c.naam"""
        ).fetchall()
        subcategorieen = db.execute(
            """SELECT s.*, (SELECT COUNT(*) FROM producten
                             WHERE categorie = s.categorie AND subcategorie = s.naam) AS aantal_producten
               FROM subcategorieen s ORDER BY s.categorie, s.naam"""
        ).fetchall()
        subcategorieen_per_categorie = {}
        for s in subcategorieen:
            subcategorieen_per_categorie.setdefault(s["categorie"], []).append(s)
        return render_template(
            "categorieen.html",
            categorieen=categorieen,
            subcategorieen_per_categorie=subcategorieen_per_categorie,
        )

    @app.route("/categorieen/<int:categorie_id>/verwijderen", methods=["POST"])
    def categorie_verwijderen(categorie_id):
        db = get_db()
        categorie = db.execute(
            "SELECT * FROM categorieen WHERE id = ?", (categorie_id,)
        ).fetchone()
        if categorie is None:
            flash("Categorie niet gevonden.", "error")
            return redirect(url_for("categorieen_lijst"))
        in_gebruik = db.execute(
            "SELECT COUNT(*) AS n FROM producten WHERE categorie = ?", (categorie["naam"],)
        ).fetchone()["n"]
        if in_gebruik > 0:
            flash(
                f"Categorie '{categorie['naam']}' is nog in gebruik bij {in_gebruik} "
                "product(en) en kan niet verwijderd worden.",
                "error",
            )
            return redirect(url_for("categorieen_lijst"))
        db.execute("DELETE FROM categorieen WHERE id = ?", (categorie_id,))
        db.execute("DELETE FROM subcategorieen WHERE categorie = ?", (categorie["naam"],))
        db.commit()
        flash(f"Categorie '{categorie['naam']}' verwijderd.", "success")
        return redirect(url_for("categorieen_lijst"))

    @app.route("/categorieen/<int:categorie_id>/verkoopprijs-verplicht", methods=["POST"])
    def categorie_verkoopprijs_verplicht_wisselen(categorie_id):
        db = get_db()
        categorie = db.execute(
            "SELECT * FROM categorieen WHERE id = ?", (categorie_id,)
        ).fetchone()
        if categorie is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Categorie niet gevonden."}), 404
            flash("Categorie niet gevonden.", "error")
            return redirect(url_for("categorieen_lijst"))
        nieuwe_status = 0 if categorie["verkoopprijs_verplicht"] else 1
        db.execute(
            "UPDATE categorieen SET verkoopprijs_verplicht = ? WHERE id = ?",
            (nieuwe_status, categorie_id),
        )
        db.commit()
        if is_ajax_verzoek():
            melding = (
                "Verkoopprijs weer verplicht."
                if nieuwe_status
                else "Verkoopprijs niet meer verplicht voor deze categorie."
            )
            return jsonify({"ok": True, "verkoopprijs_verplicht": nieuwe_status, "melding": melding})
        return redirect(url_for("categorieen_lijst"))

    @app.route("/subcategorieen/nieuw", methods=["POST"])
    def subcategorie_nieuw():
        db = get_db()
        categorie = request.form.get("categorie", "").strip()
        naam = request.form.get("naam", "").strip()
        if not categorie or not naam:
            flash("Vul een categorie en een naam in voor de subcategorie.", "error")
        else:
            bestaat = db.execute(
                "SELECT id FROM subcategorieen WHERE categorie = ? AND naam = ?",
                (categorie, naam),
            ).fetchone()
            if bestaat:
                flash(f"Subcategorie '{naam}' bestaat al binnen '{categorie}'.", "error")
            else:
                db.execute(
                    "INSERT INTO subcategorieen (categorie, naam) VALUES (?, ?)",
                    (categorie, naam),
                )
                db.commit()
                flash(f"Subcategorie '{naam}' toegevoegd aan '{categorie}'.", "success")
        return redirect(url_for("categorieen_lijst"))

    @app.route("/subcategorieen/<int:subcategorie_id>/verwijderen", methods=["POST"])
    def subcategorie_verwijderen(subcategorie_id):
        db = get_db()
        subcategorie = db.execute(
            "SELECT * FROM subcategorieen WHERE id = ?", (subcategorie_id,)
        ).fetchone()
        if subcategorie is None:
            flash("Subcategorie niet gevonden.", "error")
            return redirect(url_for("categorieen_lijst"))
        in_gebruik = db.execute(
            "SELECT COUNT(*) AS n FROM producten WHERE categorie = ? AND subcategorie = ?",
            (subcategorie["categorie"], subcategorie["naam"]),
        ).fetchone()["n"]
        if in_gebruik > 0:
            flash(
                f"Subcategorie '{subcategorie['naam']}' is nog in gebruik bij {in_gebruik} "
                "product(en) en kan niet verwijderd worden.",
                "error",
            )
            return redirect(url_for("categorieen_lijst"))
        db.execute("DELETE FROM subcategorieen WHERE id = ?", (subcategorie_id,))
        db.commit()
        flash(f"Subcategorie '{subcategorie['naam']}' verwijderd.", "success")
        return redirect(url_for("categorieen_lijst"))

    # ---------- In / uit boeken ----------

    @app.route("/boeken", methods=["GET", "POST"])
    def boeken():
        db = get_db()
        if request.method == "POST":
            product_id = int(request.form["product_id"])
            mtype = request.form["type"]
            aantal = int(request.form["aantal"])
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            opmerking = request.form.get("opmerking", "").strip()

            product = db.execute(
                "SELECT * FROM producten WHERE id = ?", (product_id,)
            ).fetchone()

            if product is None or aantal <= 0:
                flash("Ongeldige boeking.", "error")
                return redirect(url_for("boeken"))

            delta = aantal if mtype == "in" else -aantal
            nieuwe_voorraad = product["voorraad"] + delta

            db.execute(
                "UPDATE producten SET voorraad = ? WHERE id = ?",
                (nieuwe_voorraad, product_id),
            )
            db.execute(
                """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_id, mtype, aantal, now_str(), naam, gebruiker_id, opmerking),
            )
            db.commit()

            if nieuwe_voorraad < 0:
                flash(
                    f"'{product['naam']}' geboekt, maar de voorraad staat nu op "
                    f"{nieuwe_voorraad}. Controleer de telling.",
                    "warning",
                )
            else:
                werkwoord = "bijgeboekt bij" if mtype == "in" else "afgeboekt van"
                flash(f"{aantal} {werkwoord} '{product['naam']}'.", "success")
            return redirect(url_for("boeken"))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        recente_mutaties = db.execute(
            """SELECT m.*, p.naam AS product_naam, p.eenheid
               FROM mutaties m JOIN producten p ON p.id = m.product_id
               ORDER BY m.id DESC LIMIT 15"""
        ).fetchall()
        return render_template(
            "boeken.html", producten=producten, recente_mutaties=recente_mutaties
        )

    @app.route("/leveringen/inboeken", methods=["GET", "POST"])
    def levering_inboeken():
        db = get_db()
        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            referentie = request.form.get("referentie", "").strip()
            datum_input = request.form.get("datum", "").strip()
            datum = datum_input.replace("T", " ") if datum_input else now_str()
            opmerking = (
                f"Levering ingeboekt ({referentie})" if referentie else "Levering ingeboekt"
            )

            producten = db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()

            geboekte_regels = []
            for p in producten:
                waarde = request.form.get(f"aantal_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    aantal_besteleenheden = int(waarde)
                except ValueError:
                    continue
                if aantal_besteleenheden <= 0:
                    continue
                aantal = naar_voorraadeenheden(aantal_besteleenheden, p)
                db.execute(
                    "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                    (aantal, p["id"]),
                )
                db.execute(
                    """INSERT INTO mutaties (product_id, type, aantal, datum, naam, gebruiker_id, opmerking)
                       VALUES (?, 'in', ?, ?, ?, ?, ?)""",
                    (p["id"], aantal, datum, naam, gebruiker_id, opmerking),
                )
                geboekte_regels.append((p, aantal, aantal_besteleenheden))

            if not geboekte_regels:
                flash("Geen aantallen ingevuld: er is niets ingeboekt.", "error")
                return redirect(url_for("levering_inboeken"))

            db.commit()
            flash(
                f"Levering ingeboekt: {len(geboekte_regels)} product(en) bijgewerkt.",
                "success",
            )

            regels_tekst = "\n".join(
                f"  - {p['naam']}: +{aantal_be} {besteleenheid_naam(p)} (= {aantal} {p['eenheid']})"
                for p, aantal, aantal_be in geboekte_regels
            )
            ontvangers = [
                r["email"]
                for r in db.execute(
                    """SELECT email FROM gebruikers
                       WHERE mail_factuur = 1 AND email IS NOT NULL AND email != ''"""
                ).fetchall()
            ]
            if not ontvangers:
                instelling = db.execute(
                    "SELECT notificatie_email FROM instellingen WHERE id = 1"
                ).fetchone()
                if instelling and instelling["notificatie_email"]:
                    ontvangers = [instelling["notificatie_email"]]

            onderwerp = f"Levering ingeboekt{f' ({referentie})' if referentie else ''}"
            tekst = (
                f"Er is een levering ingeboekt in het voorraadsysteem.\n\n"
                f"Datum: {format_datum(datum)}\n"
                f"Door: {naam or 'onbekend'}\n"
                f"Referentie: {referentie or '-'}\n\n"
                f"Producten:\n{regels_tekst}"
            )
            for ontvanger in ontvangers:
                mail.stuur_mail(onderwerp, tekst, naar=ontvanger)

            return redirect(url_for("boeken"))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        categorieen = db.execute(
            "SELECT naam FROM categorieen ORDER BY naam"
        ).fetchall()
        return render_template(
            "levering_inboeken.html",
            producten=producten,
            categorieen=categorieen,
            nu_datetime_local=now_datetime_local(),
        )

    # ---------- Voorraad tellen ----------

    def signaleer_afwijkende_telling(db, product_id, voorraad_voor, geteld, limiet=8):
        """Vergelijkt de mutatie (verkocht + correctie) van een nieuwe telling
        met het gemiddelde van de laatste tellingen van dit product, om een
        tikfout te kunnen signaleren voordat de telling wordt opgeslagen.
        Retourneert None als er te weinig geschiedenis is om iets zinnigs
        over te zeggen."""
        vorige = db.execute(
            """SELECT verkocht, correctie FROM telling_regels
               WHERE product_id = ? ORDER BY telling_id DESC LIMIT ?""",
            (product_id, limiet),
        ).fetchall()
        if len(vorige) < 3:
            return None
        gemiddelde = sum(r["verkocht"] + r["correctie"] for r in vorige) / len(vorige)
        mutatie_nu = abs(geteld - voorraad_voor)
        if mutatie_nu <= max(gemiddelde * 3, 6):
            return None
        return {"gemiddelde": gemiddelde, "mutatie_nu": mutatie_nu}

    def verwerk_telling(db, waarden, naam, opmerking, datum, gebruiker_id=None):
        """waarden: dict {product_id: geteld_aantal}. Maakt een telling aan,
        berekent per product het verschil met de huidige voorraad, en werkt
        voorraad + geschiedenis bij. Retourneert het nieuwe telling_id, of
        None als er niets te verwerken viel."""
        if not waarden:
            return None

        cur = db.execute(
            "INSERT INTO tellingen (datum, naam, gebruiker_id, opmerking) VALUES (?, ?, ?, ?)",
            (datum, naam, gebruiker_id, opmerking),
        )
        telling_id = cur.lastrowid

        for product_id, geteld in waarden.items():
            product = db.execute(
                "SELECT * FROM producten WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None:
                continue
            verschil = geteld - product["voorraad"]
            verkocht = max(0, -verschil)
            correctie = max(0, verschil)

            db.execute(
                """INSERT INTO telling_regels
                   (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht,
                    correctie, verkoopprijs)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    telling_id,
                    product_id,
                    product["voorraad"],
                    geteld,
                    verkocht,
                    correctie,
                    product["verkoopprijs"],
                ),
            )
            db.execute(
                "UPDATE producten SET voorraad = ? WHERE id = ?", (geteld, product_id)
            )
            if verkocht > 0:
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                       VALUES (?, 'uit', ?, ?, ?, ?, ?, ?)""",
                    (product_id, verkocht, datum, naam, gebruiker_id, f"Verkocht (telling #{telling_id})", telling_id),
                )
            elif correctie > 0:
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                       VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                    (product_id, correctie, datum, naam, gebruiker_id, f"Correctie (telling #{telling_id})", telling_id),
                )

        db.commit()
        return telling_id

    @app.route("/tellen", methods=["GET", "POST"])
    def tellen():
        db = get_db()
        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            opmerking = request.form.get("opmerking", "").strip()
            datum_input = request.form.get("datum", "").strip()
            datum = datum_input.replace("T", " ") if datum_input else now_str()

            producten = db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()

            waarden = {}
            for p in producten:
                waarde = request.form.get(f"geteld_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    geteld = int(waarde)
                except ValueError:
                    continue
                if geteld < 0:
                    continue
                waarden[p["id"]] = geteld

            telling_id = verwerk_telling(db, waarden, naam, opmerking, datum, gebruiker_id)
            if telling_id is None:
                flash("Geen aantallen ingevuld: er is niets geteld.", "error")
                return redirect(url_for("tellen"))

            flash(
                f"Telling #{telling_id} verwerkt: {len(waarden)} product(en) geteld.",
                "success",
            )
            return redirect(url_for("telling_detail", telling_id=telling_id))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        return render_template(
            "tellen.html",
            producten=producten,
            nu_datetime_local=now_datetime_local(),
        )

    LOOP_SESSIE_SLEUTELS = ("loop_fase", "loop_index", "loop_bar", "loop_hok")

    @app.route("/tellen/lopen/starten")
    def tellen_lopen_starten():
        for sleutel in LOOP_SESSIE_SLEUTELS:
            session.pop(sleutel, None)
        return redirect(url_for("tellen_lopen"))

    @app.route("/tellen/lopen", methods=["GET", "POST"])
    def tellen_lopen():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        if not producten:
            flash("Geen actieve producten om te tellen.", "error")
            return redirect(url_for("tellen"))
        totaal = len(producten)

        if request.method == "POST":
            actie = request.form.get("actie", "volgende")
            if actie == "stoppen":
                for sleutel in LOOP_SESSIE_SLEUTELS:
                    session.pop(sleutel, None)
                flash("Looplijst afgebroken, er is niets opgeslagen.", "error")
                return redirect(url_for("tellen"))

            fase = session.get("loop_fase", "bar")
            index = session.get("loop_index", 0)
            bar_waarden = session.get("loop_bar", {})
            hok_waarden = session.get("loop_hok", {})
            huidige_dict = bar_waarden if fase == "bar" else hok_waarden

            if 0 <= index < totaal:
                product_id = str(producten[index]["id"])
                waarde = request.form.get("geteld", "").strip()
                if waarde != "":
                    huidige_dict[product_id] = waarde
                elif product_id in huidige_dict:
                    del huidige_dict[product_id]

            if actie == "vorige":
                index -= 1
                if index < 0:
                    if fase == "hok":
                        fase = "bar"
                        index = totaal - 1
                    else:
                        index = 0
            else:
                index += 1
                if index >= totaal:
                    if fase == "bar":
                        fase = "hok"
                        index = 0
                    else:
                        # Bar en voorraadhok zijn allebei geteld: optellen en
                        # naar het controlescherm, nog niet meteen opslaan.
                        geparsed = {}
                        for p in producten:
                            pid_str = str(p["id"])
                            bar_tekst = bar_waarden.get(pid_str, "")
                            hok_tekst = hok_waarden.get(pid_str, "")
                            if bar_tekst == "" and hok_tekst == "":
                                continue
                            try:
                                bar_aantal = int(bar_tekst) if bar_tekst != "" else 0
                            except ValueError:
                                bar_aantal = 0
                            try:
                                hok_aantal = int(hok_tekst) if hok_tekst != "" else 0
                            except ValueError:
                                hok_aantal = 0
                            geteld_totaal = bar_aantal + hok_aantal
                            if geteld_totaal >= 0:
                                geparsed[pid_str] = geteld_totaal

                        if not geparsed:
                            for sleutel in LOOP_SESSIE_SLEUTELS:
                                session.pop(sleutel, None)
                            flash("Geen aantallen ingevuld: er is niets geteld.", "error")
                            return redirect(url_for("tellen"))

                        session["loop_review"] = geparsed
                        session.pop("loop_fase", None)
                        session.pop("loop_index", None)
                        session.modified = True
                        return redirect(url_for("tellen_lopen_controleren"))

            session["loop_fase"] = fase
            session["loop_index"] = index
            session["loop_bar"] = bar_waarden
            session["loop_hok"] = hok_waarden
            session.modified = True
            return redirect(url_for("tellen_lopen"))

        fase = session.get("loop_fase", "bar")
        index = session.get("loop_index", 0)
        if index >= totaal:
            index = 0
        bar_waarden = session.get("loop_bar", {})
        hok_waarden = session.get("loop_hok", {})
        huidig = producten[index]
        huidige_dict = bar_waarden if fase == "bar" else hok_waarden
        huidige_waarde = huidige_dict.get(str(huidig["id"]), "")
        bar_waarde_hint = bar_waarden.get(str(huidig["id"]), "") if fase == "hok" else None

        stap_nu = (0 if fase == "bar" else totaal) + index
        voortgang_percentage = round(stap_nu / (totaal * 2) * 100, 1)

        return render_template(
            "tellen_lopen.html",
            product=huidig,
            index=index,
            totaal=totaal,
            fase=fase,
            bar_waarde_hint=bar_waarde_hint,
            huidige_waarde=huidige_waarde,
            voortgang_percentage=voortgang_percentage,
        )

    @app.route("/tellen/lopen/controleren", methods=["GET", "POST"])
    def tellen_lopen_controleren():
        db = get_db()
        review = session.get("loop_review")
        if not review:
            return redirect(url_for("tellen"))

        if request.method == "POST":
            actie = request.form.get("actie", "bevestigen")
            if actie == "annuleren":
                for sleutel in list(LOOP_SESSIE_SLEUTELS) + ["loop_review"]:
                    session.pop(sleutel, None)
                flash("Looplijst afgebroken, er is niets opgeslagen.", "error")
                return redirect(url_for("tellen"))

            waarden = {}
            for product_id_str in review:
                tekst = request.form.get(f"totaal_{product_id_str}", "").strip()
                if tekst == "":
                    continue
                try:
                    aantal = int(tekst)
                except ValueError:
                    continue
                if aantal < 0:
                    continue
                waarden[int(product_id_str)] = aantal

            for sleutel in list(LOOP_SESSIE_SLEUTELS) + ["loop_review"]:
                session.pop(sleutel, None)

            telling_id = verwerk_telling(
                db,
                waarden,
                session.get("gebruiker_naam"),
                "Via looplijst geteld (bar + voorraadhok)",
                now_str(),
                session.get("gebruiker_id"),
            )
            if telling_id is None:
                flash("Geen aantallen ingevuld: er is niets geteld.", "error")
                return redirect(url_for("tellen"))
            flash(
                f"Telling #{telling_id} bevestigd: {len(waarden)} product(en) opgeslagen.",
                "success",
            )
            return redirect(url_for("telling_detail", telling_id=telling_id))

        bar_waarden = session.get("loop_bar", {})
        hok_waarden = session.get("loop_hok", {})
        regels = []
        for product_id_str, totaal in review.items():
            product = db.execute(
                "SELECT * FROM producten WHERE id = ?", (int(product_id_str),)
            ).fetchone()
            if product is None:
                continue
            regels.append(
                {
                    "product": product,
                    "bar": bar_waarden.get(product_id_str, "") or "0",
                    "hok": hok_waarden.get(product_id_str, "") or "0",
                    "totaal": totaal,
                    "afwijking": signaleer_afwijkende_telling(
                        db, product["id"], product["voorraad"], totaal
                    ),
                }
            )
        regels.sort(key=lambda r: (r["product"]["categorie"], r["product"]["naam"]))

        return render_template("tellen_lopen_controleren.html", regels=regels)

    @app.route("/tellingen")
    def tellingen_overzicht():
        db = get_db()
        tellingen = db.execute(
            """SELECT t.*,
                      (SELECT COUNT(*) FROM telling_regels WHERE telling_id = t.id) AS aantal_producten,
                      (SELECT COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0)
                         FROM telling_regels tr
                         WHERE tr.telling_id = t.id) AS omzet
               FROM tellingen t
               ORDER BY t.id DESC"""
        ).fetchall()

        # Per telling de regels erbij, voor de "Bekijken"-pop-up -- scheelt
        # een aparte pagina-navigatie voor een snel kijkje.
        regels_per_telling = {
            t["id"]: db.execute(
                """SELECT tr.*, p.naam AS product_naam, p.eenheid
                   FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
                   WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
                (t["id"],),
            ).fetchall()
            for t in tellingen
        }

        verkoop_regels = db.execute(
            """SELECT t.datum, tr.verkocht, tr.verkoopprijs
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
               WHERE tr.verkocht > 0"""
        ).fetchall()

        weken = {}
        for r in verkoop_regels:
            dt = datetime.strptime(r["datum"], "%Y-%m-%d %H:%M")
            jaar, week, _ = dt.isocalendar()
            sleutel = (jaar, week)
            if sleutel not in weken:
                maandag = dt - timedelta(days=dt.weekday())
                zondag = maandag + timedelta(days=6)
                weken[sleutel] = {
                    "jaar": jaar,
                    "week": week,
                    "van": maandag.strftime("%Y-%m-%d"),
                    "tot": zondag.strftime("%Y-%m-%d"),
                    "omzet": 0.0,
                }
            weken[sleutel]["omzet"] += r["verkocht"] * r["verkoopprijs"]

        omzet_per_week = sorted(
            weken.values(), key=lambda w: (w["jaar"], w["week"]), reverse=True
        )
        huidige_jaar, huidige_week, _ = datetime.now().isocalendar()
        trend = bereken_trend(omzet_per_week, huidige_jaar, huidige_week)

        return render_template(
            "tellingen_overzicht.html",
            tellingen=tellingen,
            regels_per_telling=regels_per_telling,
            omzet_per_week=omzet_per_week,
            huidige_jaar=huidige_jaar,
            huidige_week=huidige_week,
            trend=trend,
        )

    @app.route("/tellingen/gecombineerd/pdf")
    def tellingen_gecombineerd_pdf():
        """PDF van een zelf geselecteerde greep tellingen -- de regels worden
        per product bij elkaar opgeteld, net als bij het periode-verkooprapport
        (dat gebruikt een datumrange; dit gebruikt een losse selectie)."""
        ids = request.args.getlist("ids", type=int)
        if not ids:
            flash("Selecteer minstens één telling om te combineren.", "error")
            return redirect(url_for("tellingen_overzicht"))

        db = get_db()
        placeholders = ",".join("?" for _ in ids)
        regels = db.execute(
            f"""SELECT p.naam AS product_naam, p.categorie, p.eenheid,
                       SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                       SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                FROM telling_regels tr
                JOIN tellingen t ON t.id = tr.telling_id
                JOIN producten p ON p.id = tr.product_id
                WHERE tr.telling_id IN ({placeholders})
                GROUP BY tr.product_id
                ORDER BY p.categorie, p.naam""",
            ids,
        ).fetchall()
        grens = db.execute(
            f"SELECT MIN(datum) AS van, MAX(datum) AS tot FROM tellingen WHERE id IN ({placeholders})",
            ids,
        ).fetchone()

        pdf_bytes = periode_verkoop_pdf(
            format_datum(grens["van"]) if grens["van"] else "",
            format_datum(grens["tot"]) if grens["tot"] else "",
            regels,
        )
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-selectie-{len(ids)}-tellingen.pdf"
            },
        )

    @app.route("/tellingen/<int:telling_id>")
    def telling_detail(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Telling niet gevonden.", "error")
            return redirect(url_for("tellen"))

        regels = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        totaal_omzet = sum(r["verkocht"] * r["verkoopprijs"] for r in regels)
        besteladvies = bestel_suggesties(db)

        return render_template(
            "telling_detail.html",
            telling=telling,
            regels=regels,
            totaal_omzet=totaal_omzet,
            besteladvies=besteladvies,
        )

    @app.route("/tellingen/<int:telling_id>/pdf")
    def telling_pdf(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Telling niet gevonden.", "error")
            return redirect(url_for("tellen"))

        regels = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        vorige_telling = db.execute(
            "SELECT * FROM tellingen WHERE id < ? ORDER BY id DESC LIMIT 1",
            (telling_id,),
        ).fetchone()

        van = format_datum(vorige_telling["datum"]) if vorige_telling else "eerste telling"
        periode_tekst = f"Periode: {van}  t/m  {format_datum(telling['datum'])}"
        pdf_bytes = verkoop_pdf(telling_id, periode_tekst, regels)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-telling-{telling_id}.pdf"
            },
        )

    @app.route("/verkooprapport")
    def verkooprapport():
        van = request.args.get("van") or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        tot = request.args.get("tot") or datetime.now().strftime("%Y-%m-%d")
        db = get_db()
        omzet_trend = bereken_omzet_trend_periode(db, van, tot)
        return render_template(
            "verkooprapport.html", van=van, tot=tot, omzet_trend=omzet_trend
        )

    @app.route("/fusten")
    def fusten_overzicht():
        db = get_db()
        fust_producten = db.execute(
            "SELECT * FROM producten WHERE glazen_per_fust > 0 ORDER BY categorie, naam"
        ).fetchall()
        fust_verkopen = bereken_fust_verkopen(db)
        return render_template(
            "fusten.html", fust_producten=fust_producten, fust_verkopen=fust_verkopen
        )

    @app.route("/week-overzicht")
    def week_overzicht():
        db = get_db()
        overzicht = bereken_week_overzicht(db)
        return render_template("week_overzicht.html", overzicht=overzicht)

    @app.route("/wedstrijden")
    def wedstrijden_overzicht():
        db = get_db()
        komende_thuiswedstrijden = bereken_komende_thuiswedstrijden(db)
        wedstrijd_geschiedenis = bereken_wedstrijd_geschiedenis(db)
        return render_template(
            "wedstrijden.html",
            komende_thuiswedstrijden=komende_thuiswedstrijden,
            wedstrijd_geschiedenis=wedstrijd_geschiedenis,
        )

    @app.route("/verkooprapport/pdf")
    def verkooprapport_pdf_route():
        van = request.args.get("van", "").strip() or (
            datetime.now() - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        tot = request.args.get("tot", "").strip() or datetime.now().strftime("%Y-%m-%d")

        db = get_db()
        # Sommeert per regel verkocht * de destijds vastgezette prijs, i.p.v.
        # de huidige prijs van het product -- een periode kan meerdere
        # tellingen omvatten waartussen de prijs kan zijn gewijzigd.
        regels = db.execute(
            """SELECT p.naam AS product_naam, p.categorie, p.subcategorie, p.eenheid,
                      SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                      SUM(tr.verkocht * tr.verkoopprijs) AS omzet
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
               JOIN producten p ON p.id = tr.product_id
               WHERE t.datum >= ? AND t.datum <= ?
               GROUP BY tr.product_id
               ORDER BY p.categorie, p.naam""",
            (f"{van} 00:00", f"{tot} 23:59"),
        ).fetchall()

        pdf_bytes = periode_verkoop_pdf(format_datum(f"{van} 00:00"), format_datum(f"{tot} 23:59"), regels)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-{van}-tot-{tot}.pdf"
            },
        )

    @app.route("/verkooprapport/csv")
    def verkooprapport_csv_route():
        van = request.args.get("van", "").strip() or (
            datetime.now() - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        tot = request.args.get("tot", "").strip() or datetime.now().strftime("%Y-%m-%d")

        db = get_db()
        regels = db.execute(
            """SELECT p.naam AS product_naam, p.categorie, p.subcategorie, p.eenheid,
                      SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                      SUM(tr.verkocht * tr.verkoopprijs) AS omzet
               FROM telling_regels tr
               JOIN tellingen t ON t.id = tr.telling_id
               JOIN producten p ON p.id = tr.product_id
               WHERE t.datum >= ? AND t.datum <= ?
               GROUP BY tr.product_id
               ORDER BY p.categorie, p.naam""",
            (f"{van} 00:00", f"{tot} 23:59"),
        ).fetchall()
        rijen = [
            (
                r["product_naam"],
                r["categorie"],
                r["subcategorie"] or "",
                r["verkocht"],
                r["eenheid"],
                f"{r['omzet']:.2f}".replace(".", ","),
            )
            for r in regels
            if r["verkocht"] > 0
        ]
        return csv_response(
            f"verkooprapport-{van}-tot-{tot}.csv",
            ["Product", "Categorie", "Subcategorie", "Verkocht", "Eenheid", "Omzet"],
            rijen,
        )

    # ---------- Bestellijst ----------

    @app.route("/bestellijst")
    def bestellijst():
        db = get_db()

        suggesties = bestel_suggesties(db)

        # Producten die je zelf kunt toevoegen aan de "voorgesteld"-bestelling
        # (bijv. iets dat nog niet krap is, maar toch meebesteld moet worden).
        # Producten die al voorgesteld zijn of al op een openstaande bestelling
        # staan, hoeven hier niet nogmaals in de keuzelijst.
        suggestie_ids = {p["id"] for p in suggesties}
        product_ids_in_open_bestelling = {
            row["product_id"]
            for row in db.execute(
                """SELECT br.product_id FROM bestelregels br
                   JOIN bestellingen b ON b.id = br.bestelling_id
                   WHERE b.status = 'besteld'"""
            ).fetchall()
        }
        overige_producten = [
            p
            for p in db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()
            if p["id"] not in suggestie_ids and p["id"] not in product_ids_in_open_bestelling
        ]

        open_bestellingen = db.execute(
            "SELECT * FROM bestellingen WHERE status = 'besteld' ORDER BY id DESC"
        ).fetchall()
        recent_ontvangen = db.execute(
            """SELECT * FROM bestellingen WHERE status = 'ontvangen'
               ORDER BY id DESC LIMIT 5"""
        ).fetchall()
        regels_per_id = regels_per_bestelling(
            db, [b["id"] for b in open_bestellingen] + [b["id"] for b in recent_ontvangen]
        )
        open_bestellingen_met_regels = [
            (b, regels_per_id.get(b["id"], [])) for b in open_bestellingen
        ]
        recent_ontvangen_met_regels = [
            (b, regels_per_id.get(b["id"], [])) for b in recent_ontvangen
        ]

        return render_template(
            "bestellijst.html",
            suggesties=suggesties,
            overige_producten=overige_producten,
            voorspelde_tekorten=bereken_voorspelde_tekorten(db),
            open_bestellingen=open_bestellingen_met_regels,
            recent_ontvangen=recent_ontvangen_met_regels,
        )

    @app.route("/bestellijst/pdf")
    def bestellijst_pdf_route():
        db = get_db()
        suggesties = bestel_suggesties(db)
        pdf_bytes = bestellijst_pdf(suggesties)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=bestellijst.pdf"},
        )

    @app.route("/bestellijst/aanmaken", methods=["POST"])
    def bestelling_aanmaken():
        db = get_db()
        product_ids = request.form.getlist("product_id")
        besteld_door = session.get("gebruiker_naam")
        besteld_door_id = session.get("gebruiker_id")

        regels = []
        for pid in product_ids:
            aantal_besteleenheden = request.form.get(f"aantal_{pid}", "0")
            try:
                aantal_besteleenheden = int(aantal_besteleenheden)
            except ValueError:
                aantal_besteleenheden = 0
            if aantal_besteleenheden > 0:
                product = db.execute(
                    "SELECT * FROM producten WHERE id = ?", (int(pid),)
                ).fetchone()
                if product is None:
                    continue
                aantal = naar_voorraadeenheden(aantal_besteleenheden, product)
                if aantal > 0:
                    regels.append((int(pid), aantal))

        if not regels:
            flash("Geen producten geselecteerd voor de bestelling.", "error")
            return redirect(url_for("bestellijst"))

        cur = db.execute(
            """INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, besteld_door_id)
               VALUES ('besteld', ?, ?, ?)""",
            (now_str(), besteld_door, besteld_door_id),
        )
        bestelling_id = cur.lastrowid
        for product_id, aantal in regels:
            db.execute(
                """INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld)
                   VALUES (?, ?, ?)""",
                (bestelling_id, product_id, aantal),
            )
        db.commit()
        flash(f"Bestelling aangemaakt met {len(regels)} product(en).", "success")
        return redirect(url_for("bestellijst"))

    @app.route("/bestellijst/nieuw", methods=["GET", "POST"])
    def bestelling_nieuw():
        """Een factuur/bestelling handmatig klaarzetten -- los van de
        automatische lage-voorraad-suggesties. Voor als je al ergens hebt
        besteld (telefonisch, via een website) en dat vast wilt vastleggen,
        om 'm pas te boeken zodra de levering echt binnenkomt."""
        db = get_db()
        if request.method == "POST":
            referentie = request.form.get("referentie", "").strip()
            besteld_door = session.get("gebruiker_naam")
            besteld_door_id = session.get("gebruiker_id")

            producten = db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()
            regels = []
            for p in producten:
                waarde = request.form.get(f"aantal_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    aantal_besteleenheden = int(waarde)
                except ValueError:
                    continue
                if aantal_besteleenheden <= 0:
                    continue
                aantal = naar_voorraadeenheden(aantal_besteleenheden, p)
                if aantal > 0:
                    regels.append((p["id"], aantal))

            if not regels:
                flash("Geen aantallen ingevuld: er is niets klaargezet.", "error")
                return redirect(url_for("bestelling_nieuw"))

            cur = db.execute(
                """INSERT INTO bestellingen (status, aangemaakt_op, besteld_door, besteld_door_id, referentie)
                   VALUES ('besteld', ?, ?, ?, ?)""",
                (now_str(), besteld_door, besteld_door_id, referentie or None),
            )
            bestelling_id = cur.lastrowid
            for product_id, aantal in regels:
                db.execute(
                    """INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld)
                       VALUES (?, ?, ?)""",
                    (bestelling_id, product_id, aantal),
                )
            db.commit()
            flash(
                f"Bestelling #{bestelling_id} klaargezet met {len(regels)} product(en). "
                "Boek 'm in zodra de levering binnenkomt.",
                "success",
            )
            return redirect(url_for("bestellijst"))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        return render_template("bestelling_nieuw.html", producten=producten)

    @app.route("/bestellingen/<int:bestelling_id>/bewerken", methods=["GET", "POST"])
    def bestelling_bewerken(bestelling_id):
        """Past een al klaargezette bestelling aan -- bijv. na een verkeerde
        klik of gewijzigde aantallen -- zolang hij nog niet is ingeboekt.
        Vervangt de bestelregels net als bij het aanmaken, i.p.v. losse
        regels bij te werken, dat blijft zo het simpelst en het meest
        voorspelbaar."""
        db = get_db()
        bestelling = db.execute(
            "SELECT * FROM bestellingen WHERE id = ?", (bestelling_id,)
        ).fetchone()
        if bestelling is None:
            flash("Bestelling niet gevonden.", "error")
            return redirect(url_for("bestellijst"))
        if bestelling["status"] != "besteld":
            flash("Deze bestelling is al ingeboekt en kan niet meer bewerkt worden.", "error")
            return redirect(url_for("bestellijst"))

        # Ook inactieve producten meenemen als ze al op deze bestelling
        # stonden -- anders verdwijnt die regel stilletjes bij het opslaan.
        producten = db.execute(
            """SELECT * FROM producten
               WHERE actief = 1 OR id IN (SELECT product_id FROM bestelregels WHERE bestelling_id = ?)
               ORDER BY categorie, naam""",
            (bestelling_id,),
        ).fetchall()

        if request.method == "POST":
            referentie = request.form.get("referentie", "").strip()
            regels = []
            for p in producten:
                waarde = request.form.get(f"aantal_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    aantal_besteleenheden = int(waarde)
                except ValueError:
                    continue
                if aantal_besteleenheden <= 0:
                    continue
                aantal = naar_voorraadeenheden(aantal_besteleenheden, p)
                if aantal > 0:
                    regels.append((p["id"], aantal))

            if not regels:
                flash("Geen aantallen ingevuld: er is niets aangepast.", "error")
                return redirect(url_for("bestelling_bewerken", bestelling_id=bestelling_id))

            db.execute("DELETE FROM bestelregels WHERE bestelling_id = ?", (bestelling_id,))
            for product_id, aantal in regels:
                db.execute(
                    """INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld)
                       VALUES (?, ?, ?)""",
                    (bestelling_id, product_id, aantal),
                )
            db.execute(
                "UPDATE bestellingen SET referentie = ? WHERE id = ?",
                (referentie or None, bestelling_id),
            )
            db.commit()
            flash(f"Bestelling #{bestelling_id} bijgewerkt met {len(regels)} product(en).", "success")
            return redirect(url_for("bestellijst"))

        huidige_regels = db.execute(
            "SELECT product_id, aantal_besteld FROM bestelregels WHERE bestelling_id = ?",
            (bestelling_id,),
        ).fetchall()
        producten_bij_id = {p["id"]: p for p in producten}
        huidige_aantallen = {}
        for regel in huidige_regels:
            product = producten_bij_id.get(regel["product_id"])
            if product is None:
                continue
            huidige_aantallen[regel["product_id"]] = naar_besteleenheden(regel["aantal_besteld"], product)

        return render_template(
            "bestelling_nieuw.html",
            producten=producten,
            bestelling=bestelling,
            huidige_aantallen=huidige_aantallen,
        )

    @app.route("/bestellingen/<int:bestelling_id>/inboeken", methods=["GET", "POST"])
    def bestelling_inboeken(bestelling_id):
        db = get_db()
        bestelling = db.execute(
            "SELECT * FROM bestellingen WHERE id = ?", (bestelling_id,)
        ).fetchone()
        if bestelling is None:
            flash("Bestelling niet gevonden.", "error")
            return redirect(url_for("bestellijst"))

        regels = db.execute(
            """SELECT br.*, p.naam AS product_naam, p.eenheid, p.afbeelding,
                      p.besteleenheid, p.besteleenheid_factor
               FROM bestelregels br JOIN producten p ON p.id = br.product_id
               WHERE br.bestelling_id = ?""",
            (bestelling_id,),
        ).fetchall()

        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            was_al_ontvangen = bestelling["status"] == "ontvangen"
            aantal_manco = 0

            for regel in regels:
                binnen = bool(request.form.get(f"binnen_{regel['id']}"))
                if binnen:
                    aantal_str = request.form.get(f"ontvangen_{regel['id']}", "0")
                    try:
                        aantal_besteleenheden = max(0, int(aantal_str))
                    except ValueError:
                        aantal_besteleenheden = 0
                    aantal_ontvangen = naar_voorraadeenheden(aantal_besteleenheden, regel)
                    manco = 0
                else:
                    aantal_ontvangen = 0
                    manco = 1
                    aantal_manco += 1

                vorige_ontvangen = regel["aantal_ontvangen"] or 0
                delta = aantal_ontvangen - vorige_ontvangen

                db.execute(
                    "UPDATE bestelregels SET aantal_ontvangen = ?, manco = ? WHERE id = ?",
                    (aantal_ontvangen, manco, regel["id"]),
                )
                if delta != 0:
                    db.execute(
                        "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                        (delta, regel["product_id"]),
                    )

                # Mutatie voor deze regel opnieuw opbouwen, zodat de geschiedenis
                # ook na een correctie het actuele ontvangen aantal weerspiegelt.
                db.execute(
                    "DELETE FROM mutaties WHERE bestelling_id = ? AND product_id = ?",
                    (bestelling_id, regel["product_id"]),
                )
                if aantal_ontvangen > 0:
                    db.execute(
                        """INSERT INTO mutaties
                           (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, bestelling_id)
                           VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                        (
                            regel["product_id"],
                            aantal_ontvangen,
                            now_str(),
                            naam,
                            gebruiker_id,
                            "Ontvangen uit bestelling (aangepast)"
                            if was_al_ontvangen
                            else "Ontvangen uit bestelling",
                            bestelling_id,
                        ),
                    )

            # Producten die niet oorspronkelijk besteld waren, maar wel met
            # deze levering zijn meegekomen (bijv. de leverancier stuurde
            # spontaan iets extra's mee, of iets vergeten te bestellen).
            nieuwe_product_ids = request.form.getlist("nieuw_product_id", type=int)
            nieuwe_aantallen = request.form.getlist("nieuw_aantal")
            bestaande_product_ids = {r["product_id"] for r in regels}
            al_toegevoegd = set()
            aantal_extra = 0
            for product_id, waarde in zip(nieuwe_product_ids, nieuwe_aantallen):
                if product_id in bestaande_product_ids or product_id in al_toegevoegd:
                    continue
                al_toegevoegd.add(product_id)
                try:
                    aantal_besteleenheden = max(0, int(waarde))
                except ValueError:
                    aantal_besteleenheden = 0
                if aantal_besteleenheden <= 0:
                    continue
                product = db.execute(
                    "SELECT * FROM producten WHERE id = ?", (product_id,)
                ).fetchone()
                if product is None:
                    continue
                aantal_ontvangen = naar_voorraadeenheden(aantal_besteleenheden, product)

                db.execute(
                    """INSERT INTO bestelregels
                       (bestelling_id, product_id, aantal_besteld, aantal_ontvangen, manco)
                       VALUES (?, ?, 0, ?, 0)""",
                    (bestelling_id, product_id, aantal_ontvangen),
                )
                db.execute(
                    "UPDATE producten SET voorraad = voorraad + ? WHERE id = ?",
                    (aantal_ontvangen, product_id),
                )
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, bestelling_id)
                       VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                    (
                        product_id,
                        aantal_ontvangen,
                        now_str(),
                        naam,
                        gebruiker_id,
                        "Extra meegekomen bij bestelling (niet oorspronkelijk besteld)",
                        bestelling_id,
                    ),
                )
                aantal_extra += 1

            melding_extra = f", {aantal_extra} extra product(en) toegevoegd" if aantal_extra else ""
            melding_manco = f", {aantal_manco} product(en) manco" if aantal_manco else ""
            if was_al_ontvangen:
                db.commit()
                flash(f"Bestelling aangepast en voorraad bijgewerkt{melding_extra}{melding_manco}.", "success")
            else:
                db.execute(
                    "UPDATE bestellingen SET status = 'ontvangen', ontvangen_op = ? WHERE id = ?",
                    (now_str(), bestelling_id),
                )
                db.commit()
                flash(f"Bestelling ingeboekt en voorraad bijgewerkt{melding_extra}{melding_manco}.", "success")
            return redirect(url_for("bestellijst"))

        beschikbare_producten = db.execute(
            """SELECT * FROM producten WHERE actief = 1
               AND id NOT IN (SELECT product_id FROM bestelregels WHERE bestelling_id = ?)
               ORDER BY categorie, naam""",
            (bestelling_id,),
        ).fetchall()

        return render_template(
            "inboeken.html",
            bestelling=bestelling,
            regels=regels,
            beschikbare_producten=beschikbare_producten,
        )

    @app.route("/bestellingen/<int:bestelling_id>/verwijderen", methods=["POST"])
    def bestelling_verwijderen(bestelling_id):
        db = get_db()
        bestelling = db.execute(
            "SELECT * FROM bestellingen WHERE id = ?", (bestelling_id,)
        ).fetchone()
        if bestelling is None:
            flash("Bestelling niet gevonden.", "error")
            return redirect(url_for("bestellijst"))

        regels = db.execute(
            "SELECT * FROM bestelregels WHERE bestelling_id = ?", (bestelling_id,)
        ).fetchall()
        for regel in regels:
            ontvangen = regel["aantal_ontvangen"] or 0
            if ontvangen > 0:
                db.execute(
                    "UPDATE producten SET voorraad = voorraad - ? WHERE id = ?",
                    (ontvangen, regel["product_id"]),
                )

        db.execute("DELETE FROM mutaties WHERE bestelling_id = ?", (bestelling_id,))
        db.execute("DELETE FROM bestellingen WHERE id = ?", (bestelling_id,))
        db.commit()
        flash(f"Bestelling #{bestelling_id} verwijderd.", "success")
        return redirect(url_for("bestellijst"))

    # ---------- Geschiedenis ----------

    @app.route("/geschiedenis")
    def geschiedenis():
        db = get_db()
        product_id = request.args.get("product_id", type=int)

        query = """SELECT m.*, p.naam AS product_naam, p.eenheid
                    FROM mutaties m JOIN producten p ON p.id = m.product_id"""
        params = ()
        if product_id:
            query += " WHERE m.product_id = ?"
            params = (product_id,)
        query += " ORDER BY m.id DESC LIMIT 300"

        mutaties = db.execute(query, params).fetchall()
        producten = db.execute("SELECT id, naam FROM producten ORDER BY naam").fetchall()
        return render_template(
            "geschiedenis.html",
            mutaties=mutaties,
            producten=producten,
            gekozen_product_id=product_id,
        )

    # ---------- Bijzonderheden (prikbord) ----------

    @app.route("/bijzonderheden", methods=["GET", "POST"])
    def bijzonderheden():
        db = get_db()
        if request.method == "POST":
            tekst = request.form.get("tekst", "").strip()
            if not tekst:
                flash("Vul een tekst in.", "error")
                return redirect(url_for("bijzonderheden"))
            naam = session.get("gebruiker_naam")
            cur = db.execute(
                "INSERT INTO mededelingen (tekst, naam, datum, urgent) VALUES (?, ?, ?, ?)",
                (tekst, naam, now_str(), 1 if request.form.get("urgent") else 0),
            )
            db.commit()
            stuur_tag_notificaties(
                db, tekst, naam, "nieuwe mededeling", url_for("bijzonderheden", _external=True)
            )
            return redirect(url_for("bijzonderheden"))

        # Nog niet afgehandeld eerst (urgent bovenaan), afgehandelde
        # onderaan -- zodat het prikbord niet dichtslibt met opgeloste
        # dingen, maar ze ook niet spoorloos verdwijnen zoals bij
        # verwijderen.
        mededelingen = db.execute(
            "SELECT * FROM mededelingen ORDER BY afgehandeld ASC, urgent DESC, id DESC"
        ).fetchall()
        opmerkingen_per_mededeling = {}
        for regel in db.execute(
            "SELECT * FROM mededeling_opmerkingen ORDER BY id ASC"
        ).fetchall():
            opmerkingen_per_mededeling.setdefault(regel["mededeling_id"], []).append(regel)
        gebruikersnamen = [
            g["naam"] for g in db.execute("SELECT naam FROM gebruikers ORDER BY naam").fetchall()
        ]
        return render_template(
            "bijzonderheden.html",
            mededelingen=mededelingen,
            opmerkingen_per_mededeling=opmerkingen_per_mededeling,
            gebruikersnamen=gebruikersnamen,
        )

    @app.route("/bijzonderheden/<int:mededeling_id>/opmerking", methods=["POST"])
    def mededeling_opmerking_toevoegen(mededeling_id):
        db = get_db()
        mededeling = db.execute(
            "SELECT * FROM mededelingen WHERE id = ?", (mededeling_id,)
        ).fetchone()
        if mededeling is None:
            flash("Mededeling niet gevonden.", "error")
            return redirect(url_for("bijzonderheden"))
        tekst = request.form.get("tekst", "").strip()
        if not tekst:
            flash("Vul een tekst in.", "error")
            return redirect(url_for("bijzonderheden"))
        naam = session.get("gebruiker_naam")
        db.execute(
            "INSERT INTO mededeling_opmerkingen (mededeling_id, tekst, naam, gebruiker_id, datum) "
            "VALUES (?, ?, ?, ?, ?)",
            (mededeling_id, tekst, naam, session.get("gebruiker_id"), now_str()),
        )
        db.commit()
        stuur_tag_notificaties(
            db, tekst, naam, "reactie op een mededeling", url_for("bijzonderheden", _external=True)
        )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/verwijderen", methods=["POST"])
    def mededeling_verwijderen(mededeling_id):
        db = get_db()
        db.execute("DELETE FROM mededelingen WHERE id = ?", (mededeling_id,))
        db.commit()
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/afhandelen", methods=["POST"])
    def mededeling_afhandelen(mededeling_id):
        db = get_db()
        db.execute(
            """UPDATE mededelingen
               SET afgehandeld = 1, afgehandeld_door = ?, afgehandeld_op = ?
               WHERE id = ?""",
            (session.get("gebruiker_naam"), now_str(), mededeling_id),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgehandeld": 1,
                    "melding": "Afgehandeld. Zakt bij de volgende paginalaad naar onderen.",
                }
            )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/heropenen", methods=["POST"])
    def mededeling_heropenen(mededeling_id):
        db = get_db()
        db.execute(
            """UPDATE mededelingen
               SET afgehandeld = 0, afgehandeld_door = NULL, afgehandeld_op = NULL
               WHERE id = ?""",
            (mededeling_id,),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgehandeld": 0,
                    "melding": "Heropend. Komt bij de volgende paginalaad weer bovenaan te staan.",
                }
            )
        return redirect(url_for("bijzonderheden"))

    @app.route("/bijzonderheden/<int:mededeling_id>/pin-als-banner", methods=["POST"])
    def mededeling_pinnen_als_banner(mededeling_id):
        db = get_db()
        mededeling = db.execute(
            "SELECT * FROM mededelingen WHERE id = ?", (mededeling_id,)
        ).fetchone()
        if mededeling is None:
            flash("Mededeling niet gevonden.", "error")
            return redirect(url_for("bijzonderheden"))
        db.execute(
            "UPDATE instellingen SET banner_tekst = ? WHERE id = 1", (mededeling["tekst"],)
        )
        db.commit()
        flash("Mededeling als banner bovenaan de site gezet.", "success")
        return redirect(url_for("bijzonderheden"))

    # ---------- Stemmen ----------

    @app.route("/stemmen")
    def stemmen_overzicht():
        db = get_db()
        stemvragen = []
        for v in db.execute(
            "SELECT * FROM stemvragen ORDER BY actief DESC, id DESC"
        ).fetchall():
            aantal = db.execute(
                "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (v["id"],)
            ).fetchone()["n"]
            stemvragen.append({"vraag": v, "aantal_stemmen": aantal})
        return render_template("stemmen_overzicht.html", stemvragen=stemvragen)

    @app.route("/stemmen/nieuw", methods=["GET", "POST"])
    def stemvraag_nieuw():
        db = get_db()
        if request.method == "POST":
            titel = request.form.get("titel", "").strip()
            omschrijving = request.form.get("omschrijving", "").strip()
            sluit_op_datum = request.form.get("sluit_op", "").strip()
            sluit_op = f"{sluit_op_datum} 23:59" if sluit_op_datum else None
            toon_uitslag = 1 if request.form.get("toon_uitslag") else 0
            opmerking_toegestaan = 1 if request.form.get("opmerking_toegestaan") else 0
            aantal_keuzes = request.form.get("aantal_keuzes", type=int) or 1
            aantal_keuzes = max(1, min(aantal_keuzes, MAX_STEMOPTIES))
            regels = []
            for i in range(1, MAX_STEMOPTIES + 1):
                tekst = request.form.get(f"optie{i}", "").strip()
                if not tekst:
                    continue
                afbeelding = sla_stemoptie_afbeelding_op(request.files.get(f"afbeelding{i}"))
                if not afbeelding:
                    # Geen nieuwe upload: hergebruik de foto als deze naam al
                    # in de bieren-bibliotheek staat.
                    bekend = db.execute(
                        "SELECT afbeelding FROM bieren WHERE naam = ?", (tekst,)
                    ).fetchone()
                    if bekend:
                        afbeelding = bekend["afbeelding"]
                regels.append((tekst, afbeelding))
            if not titel:
                flash("Vul een titel/vraag in.", "error")
                return redirect(url_for("stemvraag_nieuw"))
            if len(regels) < 2:
                flash("Vul minstens 2 keuzes in.", "error")
                return redirect(url_for("stemvraag_nieuw"))
            cur = db.execute(
                """INSERT INTO stemvragen
                       (titel, omschrijving, aangemaakt_op, aangemaakt_door, sluit_op,
                        toon_uitslag, opmerking_toegestaan, aantal_keuzes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    titel, omschrijving or None, now_str(), session.get("gebruiker_naam"), sluit_op,
                    toon_uitslag, opmerking_toegestaan, aantal_keuzes,
                ),
            )
            stemvraag_id = cur.lastrowid
            for volgorde, (tekst, afbeelding) in enumerate(regels):
                db.execute(
                    "INSERT INTO stemopties (stemvraag_id, tekst, volgorde, afbeelding) VALUES (?, ?, ?, ?)",
                    (stemvraag_id, tekst, volgorde, afbeelding),
                )
                bewaar_bier(db, tekst, afbeelding)
            db.commit()
            flash("Stemming aangemaakt.", "success")
            return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))
        bieren = db.execute("SELECT * FROM bieren ORDER BY naam COLLATE NOCASE").fetchall()
        return render_template("stemvraag_form.html", max_stemopties=MAX_STEMOPTIES, bieren=bieren)

    @app.route("/stemmen/<int:stemvraag_id>")
    def stemvraag_detail(stemvraag_id):
        db = get_db()
        stemvraag = db.execute(
            "SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)
        ).fetchone()
        if stemvraag is None:
            flash("Stemming niet gevonden.", "error")
            return redirect(url_for("stemmen_overzicht"))
        opties = db.execute(
            """SELECT so.*,
                      (SELECT COUNT(*) FROM stemmen s WHERE s.stemoptie_id = so.id AND s.afgekeurd = 0) AS aantal
               FROM stemopties so WHERE so.stemvraag_id = ? ORDER BY so.volgorde""",
            (stemvraag_id,),
        ).fetchall()
        totaal_stemmen = sum(o["aantal"] for o in opties)
        totaal_stemmers = tel_stemmers(db, stemvraag_id)
        stemmen = db.execute(
            """SELECT s.*, so.tekst AS optie_tekst
               FROM stemmen s JOIN stemopties so ON so.id = s.stemoptie_id
               WHERE s.stemvraag_id = ? ORDER BY s.id DESC""",
            (stemvraag_id,),
        ).fetchall()
        stem_url = url_for("stem_pagina", stemvraag_id=stemvraag_id, _external=True)
        return render_template(
            "stemvraag_detail.html",
            stemvraag=stemvraag,
            opties=opties,
            totaal_stemmen=totaal_stemmen,
            totaal_stemmers=totaal_stemmers,
            stemmen=stemmen,
            stem_url=stem_url,
            qr_svg=qr.qr_svg(stem_url),
            max_stemopties=MAX_STEMOPTIES,
        )

    @app.route("/stemmen/<int:stemvraag_id>/poster.pdf")
    def stemvraag_poster_pdf(stemvraag_id):
        db = get_db()
        stemvraag = db.execute(
            "SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)
        ).fetchone()
        if stemvraag is None:
            flash("Stemming niet gevonden.", "error")
            return redirect(url_for("stemmen_overzicht"))
        stem_url = url_for("stem_pagina", stemvraag_id=stemvraag_id, _external=True)
        pdf_bytes = stemming_poster_pdf(stemvraag["titel"], qr.qr_png_bytes(stem_url))
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=stemming-{stemvraag_id}-poster.pdf"},
        )

    @app.route("/stemmen/stem/<int:stem_id>/afkeuren", methods=["POST"])
    def stem_afkeuren(stem_id):
        db = get_db()
        stem = db.execute("SELECT * FROM stemmen WHERE id = ?", (stem_id,)).fetchone()
        if stem is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Stem niet gevonden."}), 404
            flash("Stem niet gevonden.", "error")
            return redirect(url_for("stemmen_overzicht"))
        db.execute("UPDATE stemmen SET afgekeurd = 1 WHERE id = ?", (stem_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgekeurd": 1,
                    "melding": "Stem afgekeurd. Uitslag hierboven ververst bij de volgende paginalaad.",
                }
            )
        flash("Stem afgekeurd, telt niet meer mee in de uitslag.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stem["stemvraag_id"]))

    @app.route("/stemmen/stem/<int:stem_id>/goedkeuren", methods=["POST"])
    def stem_goedkeuren(stem_id):
        db = get_db()
        stem = db.execute("SELECT * FROM stemmen WHERE id = ?", (stem_id,)).fetchone()
        if stem is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Stem niet gevonden."}), 404
            flash("Stem niet gevonden.", "error")
            return redirect(url_for("stemmen_overzicht"))
        db.execute("UPDATE stemmen SET afgekeurd = 0 WHERE id = ?", (stem_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify(
                {
                    "ok": True,
                    "afgekeurd": 0,
                    "melding": "Stem telt weer mee. Uitslag hierboven ververst bij de volgende paginalaad.",
                }
            )
        flash("Stem telt weer mee.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stem["stemvraag_id"]))

    @app.route("/stemmen/<int:stemvraag_id>/sluiten", methods=["POST"])
    def stemvraag_sluiten(stemvraag_id):
        db = get_db()
        db.execute("UPDATE stemvragen SET actief = 0 WHERE id = ?", (stemvraag_id,))
        db.commit()
        flash("Stemming gesloten voor nieuwe stemmen.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))

    @app.route("/stemmen/<int:stemvraag_id>/heropenen", methods=["POST"])
    def stemvraag_heropenen(stemvraag_id):
        db = get_db()
        db.execute("UPDATE stemvragen SET actief = 1 WHERE id = ?", (stemvraag_id,))
        db.commit()
        flash("Stemming heropend.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))

    @app.route("/stemmen/<int:stemvraag_id>/einddatum", methods=["POST"])
    def stemvraag_einddatum_instellen(stemvraag_id):
        db = get_db()
        sluit_op_datum = request.form.get("sluit_op", "").strip()
        sluit_op = f"{sluit_op_datum} 23:59" if sluit_op_datum else None
        db.execute("UPDATE stemvragen SET sluit_op = ? WHERE id = ?", (sluit_op, stemvraag_id))
        db.commit()
        flash("Einddatum bijgewerkt." if sluit_op else "Einddatum verwijderd.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))

    @app.route("/stemmen/<int:stemvraag_id>/instellingen", methods=["POST"])
    def stemvraag_instellingen_bijwerken(stemvraag_id):
        db = get_db()
        toon_uitslag = 1 if request.form.get("toon_uitslag") else 0
        opmerking_toegestaan = 1 if request.form.get("opmerking_toegestaan") else 0
        aantal_keuzes = request.form.get("aantal_keuzes", type=int) or 1
        aantal_keuzes = max(1, min(aantal_keuzes, MAX_STEMOPTIES))
        db.execute(
            """UPDATE stemvragen SET toon_uitslag = ?, opmerking_toegestaan = ?, aantal_keuzes = ?
               WHERE id = ?""",
            (toon_uitslag, opmerking_toegestaan, aantal_keuzes, stemvraag_id),
        )
        db.commit()
        flash("Instellingen bijgewerkt.", "success")
        return redirect(url_for("stemvraag_detail", stemvraag_id=stemvraag_id))

    @app.route("/stemmen/<int:stemvraag_id>/verwijderen", methods=["POST"])
    def stemvraag_verwijderen(stemvraag_id):
        db = get_db()
        db.execute("DELETE FROM stemvragen WHERE id = ?", (stemvraag_id,))
        db.commit()
        flash("Stemming verwijderd.", "success")
        return redirect(url_for("stemmen_overzicht"))

    @app.route("/stemmen/bieren")
    def bieren_lijst():
        db = get_db()
        bieren = db.execute("SELECT * FROM bieren ORDER BY naam COLLATE NOCASE").fetchall()
        return render_template("bieren_lijst.html", bieren=bieren)

    @app.route("/stemmen/bieren/<int:bier_id>/verwijderen", methods=["POST"])
    def bier_verwijderen(bier_id):
        db = get_db()
        db.execute("DELETE FROM bieren WHERE id = ?", (bier_id,))
        db.commit()
        flash("Verwijderd uit de bibliotheek.", "success")
        return redirect(url_for("bieren_lijst"))

    # ---------- Publieke stempagina (geen account nodig) ----------

    @app.route("/stem")
    def stem_overzicht_publiek():
        db = get_db()
        stemvragen = db.execute(
            "SELECT * FROM stemvragen ORDER BY aangemaakt_op DESC"
        ).fetchall()
        stemvraag_ids = [v["id"] for v in stemvragen]

        # Eén query voor de opties + één voor de stemmersaantallen, i.p.v.
        # twee aparte queries per stemvraag -- deze pagina is publiek (geen
        # login nodig, bereikbaar via de QR-code) en groeit met elke
        # stemming die de club ooit organiseert.
        opties_per_vraag = {}
        stemmers_per_vraag = {}
        if stemvraag_ids:
            placeholders = ",".join("?" * len(stemvraag_ids))
            for regel in db.execute(
                f"""SELECT so.*,
                           (SELECT COUNT(*) FROM stemmen s WHERE s.stemoptie_id = so.id AND s.afgekeurd = 0) AS aantal
                    FROM stemopties so
                    WHERE so.stemvraag_id IN ({placeholders})
                    ORDER BY so.volgorde""",
                stemvraag_ids,
            ).fetchall():
                opties_per_vraag.setdefault(regel["stemvraag_id"], []).append(regel)

            for regel in db.execute(
                f"""SELECT stemvraag_id, COUNT(DISTINCT kiezer_sleutel) AS n
                    FROM stemmen
                    WHERE afgekeurd = 0 AND stemvraag_id IN ({placeholders})
                    GROUP BY stemvraag_id""",
                stemvraag_ids,
            ).fetchall():
                stemmers_per_vraag[regel["stemvraag_id"]] = regel["n"]

        stemmingen = [
            {
                "vraag": v,
                "open": stemming_is_open(v),
                "opties": opties_per_vraag.get(v["id"], []),
                "totaal_stemmers": stemmers_per_vraag.get(v["id"], 0),
            }
            for v in stemvragen
        ]
        return render_template("stem_overzicht_publiek.html", stemmingen=stemmingen)

    @app.route("/stem/<int:stemvraag_id>", methods=["GET", "POST"])
    def stem_pagina(stemvraag_id):
        db = get_db()
        stemvraag = db.execute(
            "SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)
        ).fetchone()
        if stemvraag is None:
            return render_template("stem_niet_gevonden.html"), 404

        kiezer_sleutel = request.cookies.get(STEM_COOKIE)
        nieuwe_cookie = None
        if not kiezer_sleutel:
            kiezer_sleutel = secrets.token_hex(16)
            nieuwe_cookie = kiezer_sleutel

        def _al_gestemd(naam=None):
            """Twee onafhankelijke controles op maar 1x stemmen: dit device
            (cookie) en, zodra er een naam is, deze naam -- zodat wissen van
            cookies niet als omweg werkt. Een afgekeurde stem telt niet mee,
            die mag opnieuw."""
            if db.execute(
                "SELECT 1 FROM stemmen WHERE stemvraag_id = ? AND kiezer_sleutel = ? AND afgekeurd = 0",
                (stemvraag_id, kiezer_sleutel),
            ).fetchone():
                return True
            if naam and db.execute(
                "SELECT 1 FROM stemmen WHERE stemvraag_id = ? AND lower(naam) = lower(?) AND afgekeurd = 0",
                (stemvraag_id, naam),
            ).fetchone():
                return True
            return False

        al_gestemd = _al_gestemd()
        ingevulde_naam = ""

        foutmelding = None
        if request.method == "POST":
            ingevulde_naam = request.form.get("naam", "").strip()
            if not stemming_is_open(stemvraag):
                foutmelding = "Deze stemming is gesloten."
            elif not ingevulde_naam:
                foutmelding = "Vul je naam in."
            elif _al_gestemd(ingevulde_naam):
                foutmelding = "Je hebt al gestemd, bedankt!"
                al_gestemd = True
            else:
                aantal_keuzes = stemvraag["aantal_keuzes"] or 1
                if aantal_keuzes > 1:
                    gekozen_ids = list(dict.fromkeys(request.form.getlist("optie_id", type=int)))
                else:
                    enkele_id = request.form.get("optie_id", type=int)
                    gekozen_ids = [enkele_id] if enkele_id else []
                geldige_ids = {
                    row["id"]
                    for row in db.execute(
                        "SELECT id FROM stemopties WHERE stemvraag_id = ?", (stemvraag_id,)
                    ).fetchall()
                }
                gekozen_ids = [i for i in gekozen_ids if i in geldige_ids]

                if not gekozen_ids:
                    foutmelding = "Kies eerst een van de opties." if aantal_keuzes == 1 else "Kies minstens 1 optie."
                elif len(gekozen_ids) > aantal_keuzes:
                    foutmelding = f"Kies maximaal {aantal_keuzes} opties."
                else:
                    opmerking = None
                    if stemvraag["opmerking_toegestaan"]:
                        opmerking = request.form.get("opmerking", "").strip() or None
                    db.execute(
                        "DELETE FROM stemmen WHERE stemvraag_id = ? AND kiezer_sleutel = ? "
                        "AND stemoptie_id NOT IN ({})".format(",".join("?" * len(gekozen_ids))),
                        (stemvraag_id, kiezer_sleutel, *gekozen_ids),
                    )
                    for optie_id in gekozen_ids:
                        db.execute(
                            """INSERT INTO stemmen (stemvraag_id, stemoptie_id, kiezer_sleutel, naam, opmerking, datum)
                               VALUES (?, ?, ?, ?, ?, ?)
                               ON CONFLICT(stemvraag_id, kiezer_sleutel, stemoptie_id) DO UPDATE SET
                                   naam = excluded.naam,
                                   opmerking = excluded.opmerking,
                                   afgekeurd = 0,
                                   datum = excluded.datum""",
                            (stemvraag_id, optie_id, kiezer_sleutel, ingevulde_naam, opmerking, now_str()),
                        )
                    db.commit()
                    al_gestemd = True

        opties = db.execute(
            """SELECT so.*,
                      (SELECT COUNT(*) FROM stemmen s WHERE s.stemoptie_id = so.id AND s.afgekeurd = 0) AS aantal
               FROM stemopties so WHERE so.stemvraag_id = ? ORDER BY so.volgorde""",
            (stemvraag_id,),
        ).fetchall()
        totaal_stemmen = sum(o["aantal"] for o in opties)
        totaal_stemmers = tel_stemmers(db, stemvraag_id)

        pagina = render_template(
            "stem_pagina.html",
            stemvraag=stemvraag,
            opties=opties,
            totaal_stemmen=totaal_stemmen,
            totaal_stemmers=totaal_stemmers,
            al_gestemd=al_gestemd,
            foutmelding=foutmelding,
            ingevulde_naam=ingevulde_naam,
        )
        respons = Response(pagina)
        if nieuwe_cookie:
            respons.set_cookie(
                STEM_COOKIE,
                nieuwe_cookie,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                secure=app.config.get("SESSION_COOKIE_SECURE", True),
                samesite="Lax",
            )
        return respons

    # ---------- Kassa ----------

    @app.route("/kassa/tellen", methods=["GET", "POST"])
    def kassa_tellen():
        db = get_db()
        if request.method == "POST":
            try:
                contante_omzet = round(
                    float(request.form.get("contante_omzet", "0").replace(",", ".")), 2
                )
            except ValueError:
                contante_omzet = 0.0
            opmerking = request.form.get("opmerking", "").strip()

            aantallen, geteld_bedrag = bereken_kassa_coupure_bedrag(request.form)
            kassa_stand = bereken_kassa_stand(db)
            verwacht_bedrag = round(kassa_stand["stand"] + contante_omzet, 2)
            verschil = round(geteld_bedrag - verwacht_bedrag, 2)

            cur = db.execute(
                """INSERT INTO kassa_tellingen
                   (datum, naam, gebruiker_id, verwacht_bedrag, contante_omzet,
                    geteld_bedrag, verschil, aantal_50, aantal_20, aantal_10,
                    aantal_5, aantal_2, aantal_1, aantal_050, aantal_020,
                    aantal_010, aantal_005, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now_str(),
                    session.get("gebruiker_naam"),
                    session.get("gebruiker_id"),
                    verwacht_bedrag,
                    contante_omzet,
                    geteld_bedrag,
                    verschil,
                    aantallen["aantal_50"],
                    aantallen["aantal_20"],
                    aantallen["aantal_10"],
                    aantallen["aantal_5"],
                    aantallen["aantal_2"],
                    aantallen["aantal_1"],
                    aantallen["aantal_050"],
                    aantallen["aantal_020"],
                    aantallen["aantal_010"],
                    aantallen["aantal_005"],
                    opmerking,
                ),
            )
            # Nog niet in instellingen.kassa_stand verrekenen -- dat gebeurt
            # pas bij het afsluiten, zodat de telling tot die tijd nog
            # aangepast kan worden zonder de lopende stand te verstoren.
            db.commit()
            flash(
                "Kassatelling opgeslagen als concept. Controleer de aantallen en sluit "
                "'m af zodra je klaar bent.",
                "success",
            )
            return redirect(url_for("kassa_telling_detail", telling_id=cur.lastrowid))

        kassa_stand = bereken_kassa_stand(db)
        return render_template(
            "kassa_tellen.html", kassa_stand=kassa_stand, coupures=KASSA_COUPURES
        )

    @app.route("/kassa/tellingen/<int:telling_id>")
    def kassa_telling_detail(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        kassa_stand = bereken_kassa_stand(db)
        return render_template(
            "kassa_telling_detail.html",
            telling=telling,
            coupures=KASSA_COUPURES,
            kassa_stand=kassa_stand,
            zelf_goedgekeurd=kassa_telling_is_zelf_goedgekeurd(telling),
        )

    @app.route("/kassa/tellingen/<int:telling_id>/heropenen", methods=["POST"])
    def kassa_telling_heropenen(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if not telling["afgesloten"]:
            flash("Deze kassatelling staat al open.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        # Alleen veilig als er sindsdien niets anders aan de kassa-stand
        # heeft gezeten (geen nieuwere telling afgesloten, geen afdracht of
        # toevoeging geboekt) -- anders zou heropenen die latere acties
        # ongedaan maken zonder dat de gebruiker dat doorheeft.
        kassa_stand = bereken_kassa_stand(db)
        if abs(kassa_stand["stand"] - telling["geteld_bedrag"]) > 0.001:
            flash(
                "Heropenen kan niet meer: er zijn hierna al andere kassa-acties geweest "
                "(een afdracht, toevoeging of nieuwere afgesloten telling).",
                "error",
            )
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        db.execute(
            """UPDATE kassa_tellingen
               SET afgesloten = 0, goedgekeurd_door_id = NULL, goedgekeurd_door = NULL,
                   goedgekeurd_op = NULL, goedkeuring_opmerking = NULL
               WHERE id = ?""",
            (telling_id,),
        )
        db.execute(
            "UPDATE instellingen SET kassa_stand = ? WHERE id = 1",
            (round(telling["verwacht_bedrag"] - telling["contante_omzet"], 2),),
        )
        db.commit()
        flash("Kassatelling heropend. Je kunt 'm weer aanpassen.", "success")
        return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

    @app.route("/kassa/tellingen/<int:telling_id>/omzet-corrigeren", methods=["POST"])
    def kassa_telling_omzet_corrigeren(telling_id):
        """Corrigeert alleen de contante omzet (bijv. geld dat per ongeluk als
        contant i.p.v. pin is aangeslagen) op een al goedgekeurde telling --
        ook als er sindsdien allang andere kassa-acties zijn geweest. Dat kan
        hier wel veilig, anders dan bij heropenen: de kassastand wordt bij
        goedkeuren altijd gelijkgezet aan het fysiek getelde bedrag, nooit aan
        dit cijfer, dus deze correctie raakt de kassastand of andere
        tellingen niet -- alleen het verwachte bedrag en verschil van déze
        telling worden opnieuw berekend."""
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if not telling["afgesloten"]:
            flash(
                "Deze kassatelling staat nog open als concept -- gebruik "
                "'Bewerken' om de contante omzet aan te passen.",
                "error",
            )
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        try:
            nieuwe_omzet = round(
                float(request.form.get("contante_omzet", "0").replace(",", ".")), 2
            )
        except ValueError:
            flash("Ongeldig bedrag.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        if abs(nieuwe_omzet - telling["contante_omzet"]) < 0.001:
            flash("Geen wijziging: dit is al de ingevulde contante omzet.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        stand_voor_deze_telling = round(telling["verwacht_bedrag"] - telling["contante_omzet"], 2)
        nieuw_verwacht_bedrag = round(stand_voor_deze_telling + nieuwe_omzet, 2)
        nieuw_verschil = round(telling["geteld_bedrag"] - nieuw_verwacht_bedrag, 2)
        opmerking = request.form.get("correctie_opmerking", "").strip()

        db.execute(
            """UPDATE kassa_tellingen
               SET contante_omzet = ?, verwacht_bedrag = ?, verschil = ?,
                   contante_omzet_voor_correctie = ?, contante_omzet_gecorrigeerd_door_id = ?,
                   contante_omzet_gecorrigeerd_door = ?, contante_omzet_gecorrigeerd_op = ?,
                   contante_omzet_correctie_opmerking = ?
               WHERE id = ?""",
            (
                nieuwe_omzet,
                nieuw_verwacht_bedrag,
                nieuw_verschil,
                telling["contante_omzet"],
                session.get("gebruiker_id"),
                session.get("gebruiker_naam"),
                now_str(),
                opmerking or None,
                telling_id,
            ),
        )
        db.commit()
        flash(
            f"Contante omzet gecorrigeerd van € {telling['contante_omzet']:.2f} naar "
            f"€ {nieuwe_omzet:.2f}. De kassastand en andere tellingen zijn niet aangepast.",
            "success",
        )
        return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

    @app.route("/kassa/tellingen/<int:telling_id>/bewerken", methods=["GET", "POST"])
    def kassa_telling_bewerken(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if telling["afgesloten"]:
            flash("Deze kassatelling is al afgesloten en kan niet meer aangepast worden.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        if request.method == "POST":
            try:
                contante_omzet = round(
                    float(request.form.get("contante_omzet", "0").replace(",", ".")), 2
                )
            except ValueError:
                contante_omzet = 0.0
            opmerking = request.form.get("opmerking", "").strip()

            aantallen, geteld_bedrag = bereken_kassa_coupure_bedrag(request.form)
            # Verwacht bedrag o.b.v. de huidige (afgesloten) stand -- deze
            # telling zelf telt daar nog niet in mee zolang hij open staat.
            kassa_stand = bereken_kassa_stand(db)
            verwacht_bedrag = round(kassa_stand["stand"] + contante_omzet, 2)
            verschil = round(geteld_bedrag - verwacht_bedrag, 2)

            db.execute(
                """UPDATE kassa_tellingen
                   SET verwacht_bedrag = ?, contante_omzet = ?, geteld_bedrag = ?,
                       verschil = ?, aantal_50 = ?, aantal_20 = ?, aantal_10 = ?,
                       aantal_5 = ?, aantal_2 = ?, aantal_1 = ?, aantal_050 = ?,
                       aantal_020 = ?, aantal_010 = ?, aantal_005 = ?, opmerking = ?
                   WHERE id = ?""",
                (
                    verwacht_bedrag,
                    contante_omzet,
                    geteld_bedrag,
                    verschil,
                    aantallen["aantal_50"],
                    aantallen["aantal_20"],
                    aantallen["aantal_10"],
                    aantallen["aantal_5"],
                    aantallen["aantal_2"],
                    aantallen["aantal_1"],
                    aantallen["aantal_050"],
                    aantallen["aantal_020"],
                    aantallen["aantal_010"],
                    aantallen["aantal_005"],
                    opmerking,
                    telling_id,
                ),
            )
            db.commit()
            flash("Kassatelling bijgewerkt.", "success")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        kassa_stand = bereken_kassa_stand(db)
        return render_template(
            "kassa_telling_bewerken.html",
            telling=telling,
            coupures=KASSA_COUPURES,
            kassa_stand=kassa_stand,
        )

    @app.route("/kassa/tellingen/<int:telling_id>/goedkeuren", methods=["POST"])
    def kassa_telling_goedkeuren(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if telling["afgesloten"]:
            flash("Deze kassatelling was al goedgekeurd.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))
        goedkeuring_opmerking = request.form.get("goedkeuring_opmerking", "").strip()
        db.execute(
            """UPDATE kassa_tellingen
               SET afgesloten = 1, goedgekeurd_door_id = ?, goedgekeurd_door = ?,
                   goedgekeurd_op = ?, goedkeuring_opmerking = ?
               WHERE id = ?""",
            (
                session.get("gebruiker_id"),
                session.get("gebruiker_naam"),
                now_str(),
                goedkeuring_opmerking or None,
                telling_id,
            ),
        )
        db.execute(
            "UPDATE instellingen SET kassa_stand = ? WHERE id = 1", (telling["geteld_bedrag"],)
        )
        db.commit()
        if telling["gebruiker_id"] is not None and telling["gebruiker_id"] == session.get("gebruiker_id"):
            flash("Kassatelling goedgekeurd. Je hebt je eigen telling goedgekeurd.", "success")
        else:
            flash("Kassatelling goedgekeurd.", "success")
        return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

    @app.route("/kassa/tellingen/<int:telling_id>/pdf")
    def kassa_telling_pdf(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        pdf_bytes = kassa_pdf(telling, KASSA_COUPURES)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=kassatelling-{telling_id}.pdf"
            },
        )

    @app.route("/kassa/geschiedenis")
    def kassa_geschiedenis():
        db = get_db()
        kassa_stand = bereken_kassa_stand(db)
        verschil_trend = bereken_kassa_verschil_trend(db)

        # Zelfde begrenzing als het gewone mutatie-overzicht (geschiedenis()):
        # zonder LIMIT blijft dit onbeperkt meegroeien met elke kassatelling
        # en elke afdracht/toevoeging ooit geboekt.
        tellingen = db.execute(
            "SELECT * FROM kassa_tellingen ORDER BY datum DESC, id DESC LIMIT 200"
        ).fetchall()
        mutaties = db.execute(
            "SELECT * FROM kassa_mutaties ORDER BY datum DESC, id DESC LIMIT 200"
        ).fetchall()

        tijdlijn = [{"soort": "telling", "datum": t["datum"], "item": t} for t in tellingen]
        tijdlijn += [{"soort": m["type"], "datum": m["datum"], "item": m} for m in mutaties]
        tijdlijn.sort(key=lambda r: r["datum"], reverse=True)

        return render_template(
            "kassa_geschiedenis.html",
            kassa_stand=kassa_stand,
            verschil_trend=verschil_trend,
            tijdlijn=tijdlijn
        )

    @app.route("/kassa/mutatie/nieuw", methods=["GET", "POST"])
    def kassa_mutatie_nieuw():
        db = get_db()
        if request.method == "POST":
            type_ = request.form.get("type", "").strip()
            if type_ not in ("afdracht", "toevoeging"):
                flash("Ongeldig type.", "error")
                return redirect(url_for("kassa_mutatie_nieuw"))
            try:
                bedrag = round(float(request.form.get("bedrag", "0").replace(",", ".")), 2)
            except ValueError:
                bedrag = 0.0
            if bedrag <= 0:
                flash("Vul een bedrag groter dan 0 in.", "error")
                return redirect(url_for("kassa_mutatie_nieuw"))
            ontvanger = request.form.get("ontvanger", "").strip()
            opmerking = request.form.get("opmerking", "").strip()

            db.execute(
                """INSERT INTO kassa_mutaties
                   (type, bedrag, datum, naam, gebruiker_id, ontvanger, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    type_,
                    bedrag,
                    now_str(),
                    session.get("gebruiker_naam"),
                    session.get("gebruiker_id"),
                    ontvanger,
                    opmerking,
                ),
            )
            delta = bedrag if type_ == "toevoeging" else -bedrag
            db.execute(
                "UPDATE instellingen SET kassa_stand = kassa_stand + ? WHERE id = 1",
                (delta,),
            )
            db.commit()
            werkwoord = "Afdracht" if type_ == "afdracht" else "Toevoeging"
            flash(f"{werkwoord} van € {bedrag:.2f} geboekt.", "success")
            return redirect(url_for("kassa_geschiedenis"))

        kassa_stand = bereken_kassa_stand(db)
        return render_template("kassa_mutatie_nieuw.html", kassa_stand=kassa_stand)


app = create_app()

if __name__ == "__main__":
    # Lokaal draait de app over gewone http, niet https -- met
    # SESSION_COOKIE_SECURE aan zou de browser de sessie-cookie dan nooit
    # terugsturen en zou inloggen niet werken.
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(debug=True, host="0.0.0.0", port=5050)
