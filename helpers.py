"""Gedeelde hulpfuncties en -constantes voor de routes in routes/.

Mag zelf nooit iets uit app.py of routes/ importeren -- alleen andersom --
zodat er geen cirkelvuil kan ontstaan (zelfde patroon als database.py)."""

import csv
import hashlib
import io
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Response, request, session
from markupsafe import Markup, escape

import mail
import weer

BASE_DIR = Path(__file__).parent

# Voor het @taggen van gebruikers in mededelingen/opmerkingen op het
# prikbord. Gebruikersnamen bevatten in de praktijk geen spaties, dus een
# eenvoudige woordmatch is genoeg.
TAG_PATROON = re.compile(r"@([A-Za-z0-9_.\-]+)")

WEERGAVE_TELEFOON_PATROON = re.compile(r"iPhone|iPod|Android.+Mobile", re.IGNORECASE)

STEM_AFBEELDINGEN_MAP = BASE_DIR / "static" / "stem_afbeeldingen"
PRODUCT_AFBEELDINGEN_MAP = BASE_DIR / "static" / "product_afbeeldingen"
TOEGESTANE_AFBEELDING_EXTENSIES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

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


def dagdeel_groet():
    """'Goedemorgen'/'Goedemiddag'/'Goedenavond' op basis van het huidige
    tijdstip, voor de begroeting op het handterminal-startscherm."""
    uur = datetime.now().hour
    if uur < 12:
        return "Goedemorgen"
    if uur < 18:
        return "Goedemiddag"
    return "Goedenavond"


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



# Fijnmazige rechten voor vrijwilligers: naast de rol (beheerder/vrijwilliger)
# heeft elk account een los aan/uit-vinkje per sectie. Beheerders hebben altijd
# overal toegang, ongeacht wat er in hun secties-kolom staat -- die kolom doet
# er voor hen simpelweg niet toe. "Algemeen" (dashboard, bijzonderheden e.d.)
# heeft bewust geen sectie: dat blijft voor iedereen zichtbaar, zoals nu.
SECTIES = ["voorraad", "kassa", "keuken", "stemmen"]
SECTIE_LABELS = {
    "voorraad": "Voorraad",
    "kassa": "Kassa",
    "keuken": "Keuken",
    "stemmen": "Stemmen",
}


def secties_lijst(secties_tekst):
    """Zet de opgeslagen 'voorraad,kassa'-tekst om in een set van geldige
    sectiesleutels. Onbekende/verouderde waarden worden genegeerd."""
    if not secties_tekst:
        return set()
    return {s for s in secties_tekst.split(",") if s in SECTIES}


def heeft_sectie_toegang(rol, secties_tekst, sectie):
    if rol == "beheerder":
        return True
    return sectie in secties_lijst(secties_tekst)


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


def bereken_frituurvet_status(db):
    """Status van het statusblokje 'Frituurvet': groen zolang de laatste
    vervanging binnen het ingestelde aantal dagen (instellingen tabel,
    standaard 14) valt, rood daarboven of als er nog nooit een vervanging
    is gelogd."""
    interval = db.execute(
        "SELECT frituurvet_interval_dagen FROM instellingen WHERE id = 1"
    ).fetchone()["frituurvet_interval_dagen"]
    laatste = db.execute(
        "SELECT * FROM frituurvet_vervangingen ORDER BY datum DESC, id DESC LIMIT 1"
    ).fetchone()
    if laatste is None:
        return {"laatste": None, "dagen_geleden": None, "interval": interval, "ok": False}
    dagen_geleden = (datetime.now() - datetime.strptime(laatste["datum"], "%Y-%m-%d %H:%M")).days
    return {
        "laatste": laatste,
        "dagen_geleden": dagen_geleden,
        "interval": interval,
        "ok": dagen_geleden <= interval,
    }


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


def bepaal_weergave_modus():
    """'pda' of 'desktop'. Het weergave-cookie (per toestel/browser, geen
    accountinstelling) wint altijd zodra het gezet is -- ook als iemand
    'm handmatig heeft omgezet. Pas als het cookie nog volledig ontbreekt
    (allereerste bezoek op dit toestel) wordt er op basis van de
    User-Agent geraden, en zet beveiligingsheaders() dat resultaat meteen
    vast in een cookie zodat het daarna 'onthouden' blijft."""
    cookie_waarde = request.cookies.get("weergave")
    if cookie_waarde in ("pda", "desktop"):
        return cookie_waarde
    return "pda" if WEERGAVE_TELEFOON_PATROON.search(request.headers.get("User-Agent", "")) else "desktop"
