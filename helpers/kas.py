"""Kassalade en kluis: stand, trend en status van tellingen."""

from datetime import date, datetime, timedelta


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


def bereken_kassalade_stand(db):
    """Het laatst bekende (verwachte) bedrag in de kassalade. Wordt direct
    bijgehouden in instellingen.kassalade_stand -- elke afdracht/toevoeging
    past 'm meteen aan, en elke telling zet 'm gelijk aan het getelde bedrag
    (zelfde patroon als producten.voorraad). Dat voorkomt dat je bij het
    afleiden via datums misgrijpt wanneer twee dingen binnen dezelfde minuut
    gebeuren (de datumvelden in deze app hebben geen secondeprecisie)."""
    rij = db.execute("SELECT kassalade_stand FROM instellingen WHERE id = 1").fetchone()
    # Alleen afgesloten tellingen tellen mee -- een nog openstaande (concept)
    # telling heeft zijn bedrag nog niet in kassalade_stand verrekend, dus
    # die mag hier niet als "laatste telling" worden aangezien.
    laatste_telling = db.execute(
        "SELECT * FROM kassa_tellingen WHERE afgesloten = 1 ORDER BY datum DESC, id DESC LIMIT 1"
    ).fetchone()
    return {
        "stand": round(rij["kassalade_stand"] if rij else 0.0, 2),
        "laatste_telling": laatste_telling,
    }


def bereken_kluis_stand(db):
    """Zelfde soort afgeleide stand als bereken_kassalade_stand, maar dan
    voor de kluis: bijgehouden in instellingen.kluis_stand, aangepast door
    kassalade<->kluis-overboekingen (kassa_mutaties), stortingen/opnames
    naar extern (kluis_mutaties) en afgesloten kluis_tellingen."""
    rij = db.execute("SELECT kluis_stand FROM instellingen WHERE id = 1").fetchone()
    laatste_telling = db.execute(
        "SELECT * FROM kluis_tellingen WHERE afgesloten = 1 ORDER BY datum DESC, id DESC LIMIT 1"
    ).fetchone()
    return {
        "stand": round(rij["kluis_stand"] if rij else 0.0, 2),
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


def bereken_kluis_verschil_trend(db, limiet=20):
    """Verschil per afgesloten kluistelling, voor dezelfde soort
    trendgrafiek als bereken_kassa_verschil_trend. Eenvoudiger dan die
    functie: de kluis heeft geen eigen omzet om tegen te vergelijken, dus
    hier is geen "afwijkend"-signalering nodig -- alleen het verschil
    zelf."""
    tellingen = db.execute(
        """SELECT id, datum, naam, verschil FROM kluis_tellingen
           WHERE afgesloten = 1 ORDER BY datum DESC, id DESC LIMIT ?""",
        (limiet,),
    ).fetchall()
    tellingen = list(reversed(tellingen))
    if not tellingen:
        return {"balken": [], "max_verschil": 0}

    balken = [
        {
            "id": kt["id"],
            "datum_kort": datetime.strptime(kt["datum"], "%Y-%m-%d %H:%M").strftime("%d-%m"),
            "verschil": kt["verschil"],
            "naam": kt["naam"],
        }
        for kt in tellingen
    ]

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
        "SELECT datum FROM wedstrijden WHERE thuis = 1 AND afgelast = 0 AND datum <= ? ORDER BY datum DESC LIMIT 1",
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
