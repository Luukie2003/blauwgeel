"""Omzettrends en het weekoverzicht."""

from datetime import datetime, timedelta

from helpers.producten import bestel_suggesties, categorienamen_zonder_verkoopprijsplicht


def bereken_trend(omzet_per_week, huidige_jaar, huidige_week):
    """Voortschrijdend gemiddelde + trendrichting op basis van volledig
    afgesloten weken (de lopende week telt niet mee, die is nog niet klaar).
    Weken met een 'afwijkende_periode' (geteld op een ongebruikelijke dag,
    waardoor de periode veel korter of langer dan een week was) tellen ook
    niet mee -- die zouden de trend anders vervuilen met een schijnbare
    piek of dal die alleen door de teldag komt, niet door de verkoop.

    omzet_per_week: lijst met dicts (jaar, week, omzet, ...), nieuwste eerst.
    """
    afgeronde_weken = [
        w
        for w in omzet_per_week
        if (w["jaar"], w["week"]) != (huidige_jaar, huidige_week) and not w.get("afwijkende_periode")
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


TRAININGSDAG = 2  # woensdag (maandag=0) -- alle teams trainen op dezelfde vaste avond


def _aantal_dagen_met_weekdag(van, tot, weekdag, inclusief_van=True):
    """Telt hoeveel dagen met de gegeven weekdag (0=maandag) er vallen tussen
    'van' en 'tot' (date-strings 'YYYY-MM-DD', 'tot' inclusief). Gebruikt
    voor trainingsavonden, net zoals wedstrijden uit de 'wedstrijden'-tabel
    komen -- maar omdat elk team op dezelfde avond traint is daar geen
    losse tabel met agendadata voor nodig."""
    start = datetime.strptime(van, "%Y-%m-%d").date()
    eind = datetime.strptime(tot, "%Y-%m-%d").date()
    dag = start if inclusief_van else start + timedelta(days=1)
    aantal = 0
    while dag <= eind:
        if dag.weekday() == weekdag:
            aantal += 1
        dag += timedelta(days=1)
    return aantal


def bereken_omzet_trend_periode(db, van, tot):
    """Omzet + best verkopende producten voor alle tellingen binnen een zelf
    gekozen periode -- gebruikt door het verkooprapport en het weekoverzicht.
    Rekent met de bevroren telling-prijs (tr.verkoopprijs), niet de actuele
    productprijs, zodat latere prijswijzigingen oude cijfers niet aanpassen.

    Elke balk representeert de periode sinds de vorige telling, die niet
    per se een week beslaat (dat hangt af van wanneer er geteld is). Om
    balken van sterk wisselende lengte niet stilzwijgend als gelijkwaardige
    'weken' te laten ogen, krijgt elke balk ook het aantal dagen, de omzet
    per dag, en een 'periode_afwijkend'-vlag (korter dan 5 of langer dan 9
    dagen) mee."""
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
            "SELECT datum FROM wedstrijden WHERE thuis = 1 AND afgelast = 0 AND datum >= ? AND datum <= ? ORDER BY datum",
            (van, tot),
        ).fetchall()
    ]

    # Voor de periodelengte/trainingsavonden van de eerste balk telt de
    # écht vorige telling (ook als die vóór 'van' viel), niet 'van' zelf --
    # anders lijkt elke eerste balk in een vast weekvenster (zoals het
    # weekoverzicht dat gebruikt) systematisch te kort, puur omdat 'van' nu
    # eenmaal de gekozen kalendergrens is en niet de vorige teldatum.
    # Wedstrijden blijven wel vanaf 'van' geteld: een gemiste wedstrijd vlak
    # voor 'van' is een verwaarloosbare afwijking voor die indicator.
    werkelijke_vorige_telling = db.execute(
        "SELECT datum FROM tellingen WHERE datum < ? ORDER BY datum DESC LIMIT 1",
        (f"{van} 00:00",),
    ).fetchone()
    periode_start = werkelijke_vorige_telling["datum"][:10] if werkelijke_vorige_telling else van

    balken = []
    vorige_datum = van
    vorige_periode_start = periode_start
    eerste_balk = True
    for t in tellingen:
        periode_eind = t["datum"][:10]
        if eerste_balk:
            # Inclusief 'van' zelf: dat is de gekozen startdatum van de
            # periode, geen eerdere telling waarvan een wedstrijd al is
            # meegeteld.
            aantal_wedstrijden = sum(1 for d in wedstrijd_datums if vorige_datum <= d <= periode_eind)
            aantal_trainingsavonden = _aantal_dagen_met_weekdag(
                vorige_periode_start, periode_eind, TRAININGSDAG, inclusief_van=True
            )
            eerste_balk = False
        else:
            aantal_wedstrijden = sum(1 for d in wedstrijd_datums if vorige_datum < d <= periode_eind)
            aantal_trainingsavonden = _aantal_dagen_met_weekdag(
                vorige_periode_start, periode_eind, TRAININGSDAG, inclusief_van=False
            )
        aantal_dagen = (
            datetime.strptime(periode_eind, "%Y-%m-%d").date()
            - datetime.strptime(vorige_periode_start, "%Y-%m-%d").date()
        ).days
        balken.append(
            {
                "datum_kort": datetime.strptime(t["datum"], "%Y-%m-%d %H:%M").strftime("%d-%m"),
                "omzet": t["omzet"],
                "hoogte_pct": (t["omzet"] / max_omzet * 100) if max_omzet else 0,
                "thuiswedstrijden": aantal_wedstrijden,
                "trainingsavonden": aantal_trainingsavonden,
                "aantal_dagen": aantal_dagen,
                "omzet_per_dag": t["omzet"] / max(aantal_dagen, 1),
                "periode_afwijkend": aantal_dagen < 5 or aantal_dagen > 9,
            }
        )
        vorige_datum = periode_eind
        vorige_periode_start = periode_eind

    return {
        "balken": balken,
        "top_verkopers": top_verkopers,
        "totale_omzet": totale_omzet,
        "bevat_afwijkende_periode": any(b["periode_afwijkend"] for b in balken),
    }


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
    afwijkende_periode = huidige["bevat_afwijkende_periode"] or vorige["bevat_afwijkende_periode"]
    geteld_tot = None

    # Liever de omzet van de week zelf dan de som van de tellingen die in die
    # week gedaan zijn: wie niet op vaste dagen telt (bijv. woensdag, vrijdag en
    # soms maandag) krijgt anders een week die een andere periode beslaat.
    # voorspelling.week_samenvatting verdeelt de omzet van elke telling over de
    # dagen waarin die verkocht is.
    from voorspelling import verdeling, week_samenvatting

    try:
        nu = datetime.combine(vandaag, datetime.min.time()).replace(hour=12)
        data = verdeling(db, nu)
        deze = week_samenvatting(db, week_van, data=data) if data else None
        eerdere = week_samenvatting(db, vorige_week_van, data=data) if data else None
    except Exception as fout:  # het weekoverzicht mag nooit stuk gaan door de verdeling
        print(f"[weekoverzicht] verdeling mislukt, terugval op tellingdatums: {fout}")
        deze = eerdere = None
    if deze is not None and eerdere is not None and deze["omzet"] + eerdere["omzet"] > 0:
        huidige = dict(huidige, totale_omzet=deze["omzet"], top_verkopers=deze["top_verkopers"])
        vorige = dict(vorige, totale_omzet=eerdere["omzet"])
        # Alleen waarschuwen als de tellingen de week niet helemaal dekken.
        afwijkende_periode = deze["status"] != "compleet" or eerdere["status"] == "loopt_nog"
        geteld_tot = deze["geteld_tot"]

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
        # True als de tellingen de week niet helemaal dekken (bijv. de laatste
        # telling was vóór zondag) -- de omzetvergelijking kan daardoor
        # vertekend zijn.
        "afwijkende_periode": afwijkende_periode,
        # Wanneer er voor het laatst geteld is, als de week niet helemaal gedekt is.
        "geteld_tot": geteld_tot,
        "top_verkopers": huidige["top_verkopers"],
        "onder_minimum": bestel_suggesties(db),
        "open_bestellingen": open_bestellingen,
        "nieuwe_mededelingen": nieuwe_mededelingen,
        "zonder_prijs": zonder_prijs,
        "niet_verplicht_categorieen": niet_verplicht_categorieen,
    }
