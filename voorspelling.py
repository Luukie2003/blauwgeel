"""Verkoopvoorspelling voor de kantine: wat gaat er de komende dagen verkocht
worden, welke producten raken op en hoeveel moet er besteld worden.

Hoe het werkt, in het kort
--------------------------
* Elke telling zegt per product hoeveel er verkocht is sinds de vorige keer
  dat dat product geteld werd. Zo'n stuk tijd noemen we hier een "periode"
  (per product, want niet elke telling bevat alle producten). Een telling is
  dus nooit "een week": ze komen op onregelmatige dagen. Daarom rekent dit
  model per dag in plaats van per week.
* Een dag in de kantine loopt van 12.00 uur tot 12.00 uur de volgende dag
  (een zaterdagse wedstrijd valt dan bij zaterdag, ook als er 's avonds nog
  gedronken wordt). Een periode van 3 dagen telt zo precies 3 dagen mee,
  met een telling om 14.00 uur ruim een dag niet-tellend.
* Per dag is de "drukte" 1 + effect(thuiswedstrijd) + effect(training) +
  effect(weer). De drie effecten starten bij een aanname (+30%, +20%,
  +-12%) en worden bijgeleerd uit de eigen tellingen: hoe meer data, hoe
  meer het model de aanname loslaat (Bayesiaans: aanname = voorkennis,
  strafterm in de doelfunctie).
* Per product volgt de verkoop een (over-gespreide) Poisson-verdeling met
  een eigen basissnelheid per dag. Die snelheid is een gewogen gemiddelde
  waarin recente periodes zwaarder tellen (halvering per 6 weken) en
  periodes waarin het product uitverkocht raakte (te lage verkoop) niet
  meetellen.
* Voor de komende dagen geeft dat per product een verwachte verkoop, een
  bandbreedte, de kans dat de voorraad niet toereikend is en een advies voor
  de bestelhoeveelheid. De nauwkeurigheid wordt gecontroleerd door het
  model steeds op het verleden los te laten (terugtoetsing).

Alles is gewoon Python (geen numpy), zodat het op de hosting zonder extra
pakketten draait.
"""

import math
from datetime import date, datetime, time, timedelta
from statistics import NormalDist

from helpers import TRAININGSDAG, bestel_suggesties

# ---- Aannames waar het model mee begint en wat het erbij leert ----
PRIOR = {"wedstrijd": 0.30, "training": 0.20, "weer": 0.12}
# Hoe zeker we van de aanname zijn (standaardafwijking van het effect). Hoe
# kleiner, hoe meer data er nodig is om ervan af te wijken.
ONZEKERHEID = {"wedstrijd": 0.5, "training": 0.35, "weer": 0.15}
GRENZEN = {"wedstrijd": (0.0, 1.5), "training": (0.0, 1.0), "weer": (-0.25, 0.5)}
EFFECT_NAMEN = {
    "wedstrijd": "Thuiswedstrijd",
    "training": "Trainingsavond",
    "weer": "Weer (mooi plus, regen min)",
}

DAG_BEGIN_UUR = 12  # een kantinedag loopt van 12.00 tot 12.00 uur
HALVERING_WEKEN = 6.0  # recente verkoop telt zwaarder
MAX_WEKEN_GESCHIEDENIS = 30  # oudere verkoop weegt toch bijna niets meer mee
MODEL_MAX_PRODUCTEN = 30  # alleen de best verkopende producten leren de effecten
MIN_RIJEN_PER_PRODUCT = 2
TERUGTOETS_START = 4  # pas terugtoetsen vanaf de 4e telling

MODEL_ONZEKERHEID_DAG = 0.12  # ruimte voor drukte die we niet kunnen voorspellen
DEKKING_SERVICENIVEAU = 0.9  # bestelling dekt de vraag in 9 van de 10 gevallen

_WEEKDAG = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
_WEEKDAG_KORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]


# ---------------------------------------------------------------------------
# Kalender: wat gebeurt er op welke dag?
# ---------------------------------------------------------------------------


def wedstrijd_gewicht(aantal):
    """Drukte-gewicht van een dag met 'aantal' thuiswedstrijden: de eerste telt
    voor 1, elke extra voor 0,25 erbij (met een maximum van 4 wedstrijden)."""
    if aantal <= 0:
        return 0.0
    return 1.0 + 0.25 * (min(aantal, 4) - 1)


def weer_score(max_temp, neerslag_kans):
    """+1 bij mooi weer (warm en droog), -1 bij regen, anders 0. None als er
    geen weergegevens zijn."""
    if max_temp is None or neerslag_kans is None:
        return None
    if neerslag_kans >= 60:
        return -1.0
    if max_temp >= 18 and neerslag_kans < 30:
        return 1.0
    return 0.0


def lees_kalender(db, van, tot):
    """{datum: {wedstrijden, training, weer}} voor van t/m tot (date-objecten).
    Wedstrijden komen uit de gekoppelde teamagenda's, het weer uit de
    opgeslagen weergeschiedenis (laatst bekende verwachting per dag) en voor
    de komende dagen uit de actuele verwachting."""
    wedstrijden = {
        r["datum"]: r["n"]
        for r in db.execute(
            """SELECT datum, COUNT(*) AS n FROM wedstrijden
               WHERE thuis = 1 AND datum >= ? AND datum <= ? GROUP BY datum""",
            (van.isoformat(), tot.isoformat()),
        ).fetchall()
    }
    weer = {}
    for tabel in ("weer_historie", "weer_voorspelling"):  # voorspelling wint (vers)
        try:
            rijen = db.execute(
                f"SELECT datum, max_temp, neerslag_kans FROM {tabel} WHERE datum >= ? AND datum <= ?",
                (van.isoformat(), tot.isoformat()),
            ).fetchall()
        except Exception:  # tabel bestaat nog niet (oude database)
            rijen = []
        for r in rijen:
            weer[r["datum"]] = weer_score(r["max_temp"], r["neerslag_kans"])
    kalender = {}
    dag = van
    while dag <= tot:
        iso = dag.isoformat()
        kalender[dag] = {
            "wedstrijden": wedstrijden.get(iso, 0),
            "training": dag.weekday() == TRAININGSDAG,
            "weer": weer.get(iso),
        }
        dag += timedelta(days=1)
    return kalender


def _dag_venster(dag):
    begin = datetime.combine(dag, time(DAG_BEGIN_UUR, 0))
    return begin, begin + timedelta(days=1)


def blootstelling(start, einde, kalender):
    """Hoeveel 'dag-equivalent' een periode bevat, opgesplitst:
    D = dagen, M = wedstrijddagen (gewogen), T = trainingsavonden, S = weerscore
    (mooi +, regen -), W = dagen waarvan het weer bekend is. Een dag telt
    mee naar rato van hoeveel van zijn 12-12-venster in de periode valt."""
    D = M = T = S = W = 0.0
    dag = (start - timedelta(hours=DAG_BEGIN_UUR)).date()
    while True:
        d_begin, d_eind = _dag_venster(dag)
        if d_begin >= einde:
            break
        deel = (min(einde, d_eind) - max(start, d_begin)).total_seconds() / 86400
        if deel > 0:
            k = kalender.get(dag) or {"wedstrijden": 0, "training": False, "weer": None}
            D += deel
            M += deel * wedstrijd_gewicht(k["wedstrijden"])
            T += deel * (1.0 if k["training"] else 0.0)
            if k["weer"] is not None:
                S += deel * k["weer"]
                W += deel
        dag += timedelta(days=1)
    return {"D": D, "M": M, "T": T, "S": S, "W": W}


def drukte(b, effecten):
    """Aantal 'normale dagen' dat deze blootstelling waard is."""
    return b["D"] + effecten["wedstrijd"] * b["M"] + effecten["training"] * b["T"] + effecten["weer"] * b["S"]


# ---------------------------------------------------------------------------
# Data uit de tellingen
# ---------------------------------------------------------------------------


def _parse(datum):
    return datetime.strptime(datum, "%Y-%m-%d %H:%M")


def lees_rijen(db, nu):
    """Eén rij per product per telling: wat is er verkocht in de periode sinds
    het vorige keer dat dit product geteld werd. De eerste telling van een
    product is alleen een nulmeting. Periodes zonder enige verkoop in die hele
    telling (bijv. een nulmeting of een dag waarop alles dicht was) tellen niet mee."""
    sinds = (nu - timedelta(weeks=MAX_WEKEN_GESCHIEDENIS)).strftime("%Y-%m-%d %H:%M")
    tellingen = db.execute(
        "SELECT id, datum FROM tellingen WHERE datum >= ? ORDER BY datum, id", (sinds,)
    ).fetchall()
    if len(tellingen) < 2:
        return [], tellingen
    datum_van = {t["id"]: _parse(t["datum"]) for t in tellingen}
    regels = db.execute(
        f"""SELECT telling_id, product_id, verkocht, geteld_aantal, verkoopprijs
            FROM telling_regels
            WHERE telling_id IN ({",".join("?" * len(datum_van))})""",
        list(datum_van),
    ).fetchall()
    per_product = {}
    for r in regels:
        per_product.setdefault(r["product_id"], []).append(r)
    totaal_per_telling = {}
    for r in regels:
        totaal_per_telling[r["telling_id"]] = totaal_per_telling.get(r["telling_id"], 0) + max(0, r["verkocht"])

    rijen = []
    for pid, lijst in per_product.items():
        lijst.sort(key=lambda r: (datum_van[r["telling_id"]], r["telling_id"]))
        for vorige, huidige in zip(lijst, lijst[1:]):
            start, einde = datum_van[vorige["telling_id"]], datum_van[huidige["telling_id"]]
            if einde <= start or totaal_per_telling.get(huidige["telling_id"], 0) <= 0:
                continue
            rijen.append(
                {
                    "pid": pid,
                    "tid": huidige["telling_id"],
                    "start": start,
                    "einde": einde,
                    "V": max(0, huidige["verkocht"]),
                    "afgekapt": huidige["geteld_aantal"] <= 0 and huidige["verkocht"] > 0,
                    "prijs": huidige["verkoopprijs"] or 0.0,
                }
            )
    return rijen, tellingen


def _gewicht(einde, nu):
    weken = max(0.0, (nu - einde).total_seconds() / (7 * 86400))
    return 0.5 ** (weken / HALVERING_WEKEN)


def _voeg_blootstelling_toe(rijen, kalender, nu):
    """Rekent per unieke periode de blootstelling uit (veel producten delen
    dezelfde periode) en zet gewicht + blootstelling in elke rij."""
    cache = {}
    for r in rijen:
        sleutel = (r["start"], r["einde"])
        if sleutel not in cache:
            cache[sleutel] = blootstelling(r["start"], r["einde"], kalender)
        r["b"] = cache[sleutel]
        r["w"] = _gewicht(r["einde"], nu)
    return rijen


# ---------------------------------------------------------------------------
# Leren van de effecten
# ---------------------------------------------------------------------------


def _snelheden(rijen, effecten):
    """Basissnelheid per product (per normale dag): gewogen verkoop gedeeld
    door gewogen blootstelling. Afgekapte periodes (uitverkocht) tellen niet
    mee, tenzij er voor dat product niets anders is."""
    per_product = {}
    for r in rijen:
        per_product.setdefault(r["pid"], []).append(r)
    snelheid = {}
    for pid, lijst in per_product.items():
        goed = [r for r in lijst if not r["afgekapt"]] or lijst
        teller = sum(r["w"] * r["V"] for r in goed)
        noemer = sum(r["w"] * drukte(r["b"], effecten) for r in goed)
        snelheid[pid] = teller / noemer if noemer > 1e-9 else 0.0
    return snelheid


def _voorbewerk(rijen):
    """Zet de rijen per product om in kale lijsten, zodat de doelfunctie (die
    honderden keren draait) niet steeds in dicts hoeft te zoeken."""
    per_product = {}
    for r in rijen:
        per_product.setdefault(r["pid"], []).append(r)
    return [
        (
            [r["w"] for r in lijst],
            [r["V"] for r in lijst],
            [r["b"]["D"] for r in lijst],
            [r["b"]["M"] for r in lijst],
            [r["b"]["T"] for r in lijst],
            [r["b"]["S"] for r in lijst],
        )
        for lijst in per_product.values()
    ]


def _doelfunctie(voorbewerkt, effecten, dispersie):
    """Gewogen Poisson-afwijking van alle producten (gedeeld door de
    dispersie) plus de strafterm voor het afwijken van de aannames."""
    a, b, c = effecten["wedstrijd"], effecten["training"], effecten["weer"]
    afwijking = 0.0
    for ws, vs, ds, ms, ts, ss in voorbewerkt:
        es = [d + a * m + b * t + c * s for d, m, t, s in zip(ds, ms, ts, ss)]
        noemer = sum(w * e for w, e in zip(ws, es))
        if noemer <= 1e-9:
            continue
        r = sum(w * v for w, v in zip(ws, vs)) / noemer
        for w, v, e in zip(ws, vs, es):
            mu = r * e
            if mu <= 1e-9:
                afwijking += w * v * 10.0
            elif v > 0:
                afwijking += w * (v * math.log(v / mu) - v + mu)
            else:
                afwijking += w * mu
    straf = sum(0.5 * ((effecten[k] - PRIOR[k]) / ONZEKERHEID[k]) ** 2 for k in PRIOR)
    return afwijking / dispersie + straf


def _leer_effecten(rijen, dispersie, vrij, ronden=4):
    """Coordinate descent per effect, met de aannames als startpunt: eerst een
    grof raster over het hele toegestane bereik, daarna steeds fijner rond de
    beste waarde. 'vrij' bepaalt welke effecten data hebben om van te leren;
    de rest blijft bij de aanname."""
    voorbewerkt = _voorbewerk(rijen)
    effecten = dict(PRIOR)
    beste = _doelfunctie(voorbewerkt, effecten, dispersie)
    for ronde in range(ronden):
        veranderd = False
        for naam in PRIOR:
            if not vrij[naam]:
                continue
            laag, hoog = GRENZEN[naam]
            if ronde == 0:
                kandidaten = [laag + i * (hoog - laag) / 20 for i in range(21)]
            else:
                stap = (hoog - laag) / (20 * 3 ** ronde)
                kandidaten = [effecten[naam] + i * stap for i in range(-5, 6)]
            for waarde in kandidaten:
                waarde = min(hoog, max(laag, waarde))
                proef = dict(effecten, **{naam: waarde})
                score = _doelfunctie(voorbewerkt, proef, dispersie)
                if score < beste - 1e-9:
                    beste, effecten, veranderd = score, proef, True
        if not veranderd and ronde >= 1:
            break
    return effecten


def _schat_dispersie(rijen, effecten, snelheid):
    """Hoeveel meer de verkoop schommelt dan een zuivere Poisson (>= 1)."""
    pearson, n = 0.0, 0
    for r in rijen:
        mu = snelheid.get(r["pid"], 0.0) * drukte(r["b"], effecten)
        if mu >= 1.0:
            pearson += (r["V"] - mu) ** 2 / mu
            n += 1
    aantal_producten = len(snelheid)
    vrijheidsgraden = n - aantal_producten - len(PRIOR)
    if vrijheidsgraden < 5:
        return 2.0
    return min(8.0, max(1.0, pearson / vrijheidsgraden))


def pas_model_aan(rijen, licht=False):
    """Leert de drie effecten + de dispersie uit de rijen. Geeft ook terug
    hoeveel er per effect te leren viel (voor de uitleg). 'licht' = sneller en
    minder precies (voor de terugtoetsing, die het vaak achter elkaar doet)."""
    # Alleen de best verkopende producten sturen het leren (sneller, en de
    # zeldzame producten zijn te ruis-gevoelig om iets over drukte te zeggen).
    totaal = {}
    for r in rijen:
        totaal[r["pid"]] = totaal.get(r["pid"], 0.0) + r["w"] * r["V"]
    kandidaten = [
        pid for pid, t in sorted(totaal.items(), key=lambda x: -x[1])
        if sum(1 for r in rijen if r["pid"] == pid and not r["afgekapt"]) >= MIN_RIJEN_PER_PRODUCT
    ][:MODEL_MAX_PRODUCTEN]
    leer_rijen = [r for r in rijen if r["pid"] in set(kandidaten) and not r["afgekapt"]]

    informatie = {
        "wedstrijd": sum(r["w"] * r["b"]["M"] for r in leer_rijen),
        "training": sum(r["w"] * r["b"]["T"] for r in leer_rijen),
        "weer": sum(r["w"] * abs(r["b"]["S"]) for r in leer_rijen),
    }
    vrij = {k: informatie[k] > 0.3 for k in PRIOR}
    effecten = dict(PRIOR)
    dispersie = 2.0
    if leer_rijen and any(vrij.values()):
        for _ in range(1 if licht else 2):
            effecten = _leer_effecten(leer_rijen, dispersie, vrij, ronden=3 if licht else 4)
            if not licht:
                dispersie = _schat_dispersie(leer_rijen, effecten, _snelheden(leer_rijen, effecten))
    elif leer_rijen:
        dispersie = _schat_dispersie(leer_rijen, effecten, _snelheden(leer_rijen, effecten))
    return effecten, dispersie, informatie


# ---------------------------------------------------------------------------
# Kansrekening: negatief-binomiaal (Poisson met extra spreiding)
# ---------------------------------------------------------------------------


def _nb_parameters(mu, var):
    if var <= mu * (1 + 1e-9):
        return None  # gewone Poisson
    r = mu * mu / (var - mu)
    return r, r / (r + mu)


def _cdf_stappen(mu, var):
    """Genereert (k, P(D <= k)) voor k = 0, 1, 2, ... voor Poisson/neg-bin."""
    params = _nb_parameters(mu, var)
    if params is None:
        pmf = math.exp(-mu)
        k = 0
        cdf = pmf
        while True:
            yield k, min(1.0, cdf)
            pmf *= mu / (k + 1)
            k += 1
            cdf += pmf
    else:
        r, p = params
        pmf = math.exp(r * math.log(p))
        k = 0
        cdf = pmf
        while True:
            yield k, min(1.0, cdf)
            pmf *= (k + r) / (k + 1) * (1 - p)
            k += 1
            cdf += pmf


def kans_meer_dan(mu, var, drempel):
    """P(vraag > drempel)."""
    if mu <= 0:
        return 0.0
    drempel = max(0, int(drempel))
    if mu > 250:
        return max(0.0, 1.0 - NormalDist(mu, math.sqrt(max(var, mu))).cdf(drempel + 0.5))
    if drempel > mu + 12 * math.sqrt(max(var, mu)) + 20:
        return 0.0
    for k, cdf in _cdf_stappen(mu, var):
        if k >= drempel:
            return max(0.0, 1.0 - cdf)
    return 0.0


def kwantiel(mu, var, q):
    """Kleinste aantal k met P(vraag <= k) >= q."""
    if mu <= 0:
        return 0
    if mu > 250:
        return max(0, int(math.ceil(NormalDist(mu, math.sqrt(max(var, mu))).inv_cdf(q) - 0.5)))
    for k, cdf in _cdf_stappen(mu, var):
        if cdf >= q or k > mu + 40 * math.sqrt(max(var, mu)) + 100:
            return k
    return 0


# ---------------------------------------------------------------------------
# Terugtoetsen: hoe goed zou het model het verleden hebben voorspeld?
# ---------------------------------------------------------------------------


def terugtoetsen(rijen, nu):
    """Voor elke telling vanaf de 4e: leer alleen van wat toen al bekend was,
    voorspel de omzet van die telling en vergelijk met de werkelijkheid. Als
    maatstaf staat ernaast een 'naieve' voorspelling: de gemiddelde dagverkoop
    per product tot dan toe, zonder iets van wedstrijden, training of weer te
    weten. Geeft None als er te weinig tellingen zijn."""
    tellingen = sorted({(r["einde"], r["tid"]) for r in rijen})
    if len(tellingen) <= TERUGTOETS_START:
        return None
    afwijkingen_model, afwijkingen_naief = [], []
    try:
        for einde, tid in tellingen[TERUGTOETS_START:][-8:]:
            trein = [r for r in rijen if r["einde"] < einde]
            toets = [r for r in rijen if r["tid"] == tid]
            werkelijk = sum(r["V"] * r["prijs"] for r in toets)
            producten_in_trein = len({r["pid"] for r in trein})
            if werkelijk <= 0 or len(trein) < 8 or len(toets) < max(1, 0.5 * producten_in_trein):
                continue  # te weinig om iets zinnigs over te zeggen (bijv. een telling van 1 product)
            for r in trein:
                r["w"] = _gewicht(r["einde"], einde)
            effecten, _, _ = pas_model_aan(trein, licht=True)
            snelheid = _snelheden(trein, effecten)
            naief_teller, naief_noemer = {}, {}
            for r in trein:
                naief_teller[r["pid"]] = naief_teller.get(r["pid"], 0.0) + r["w"] * r["V"]
                naief_noemer[r["pid"]] = naief_noemer.get(r["pid"], 0.0) + r["w"] * r["b"]["D"]
            voorspeld = naief = 0.0
            for r in toets:
                if r["pid"] not in snelheid:
                    continue
                voorspeld += snelheid[r["pid"]] * drukte(r["b"], effecten) * r["prijs"]
                dagsnelheid = naief_teller[r["pid"]] / naief_noemer[r["pid"]] if naief_noemer[r["pid"]] > 1e-9 else 0.0
                naief += dagsnelheid * r["b"]["D"] * r["prijs"]
            werkelijk_vergelijkbaar = sum(r["V"] * r["prijs"] for r in toets if r["pid"] in snelheid)
            if werkelijk_vergelijkbaar <= 0:
                continue
            afwijkingen_model.append(abs(voorspeld - werkelijk_vergelijkbaar) / werkelijk_vergelijkbaar)
            afwijkingen_naief.append(abs(naief - werkelijk_vergelijkbaar) / werkelijk_vergelijkbaar)
    finally:
        for r in rijen:
            r["w"] = _gewicht(r["einde"], nu)  # gewichten terugzetten
    if not afwijkingen_model:
        return None
    mape_model = sum(afwijkingen_model) / len(afwijkingen_model)
    mape_naief = sum(afwijkingen_naief) / len(afwijkingen_naief)
    return {
        "aantal": len(afwijkingen_model),
        "mape_model": mape_model,
        "mape_naief": mape_naief,
        "verbetering": (mape_naief - mape_model) / mape_naief if mape_naief > 1e-9 else 0.0,
    }


# ---------------------------------------------------------------------------
# De prognose zelf
# ---------------------------------------------------------------------------


def _status(waarnemingen_dagen, drempels=(3, 8)):
    if waarnemingen_dagen < drempels[0]:
        return "aanname"
    if waarnemingen_dagen < drempels[1]:
        return "deels"
    return "geleerd"


def _waargenomen_dagen(rijen, kalender, soort):
    """Op hoeveel verschillende dagen kon het model dit effect waarnemen?"""
    dagen = set()
    for r in rijen:
        dag = (r["start"] - timedelta(hours=DAG_BEGIN_UUR)).date()
        while _dag_venster(dag)[0] < r["einde"]:
            k = kalender.get(dag)
            if k:
                if (soort == "wedstrijd" and k["wedstrijden"]) or (soort == "training" and k["training"]) or (
                    soort == "weer" and k["weer"] not in (None, 0.0)
                ):
                    dagen.add(dag)
            dag += timedelta(days=1)
    return len(dagen)


def maak_prognose(db, dagen=7, nu=None, serviceniveau=DEKKING_SERVICENIVEAU):
    """De complete prognose voor de komende 'dagen' dagen vanaf 'nu'. Zie de
    moduledocstring voor hoe het werkt. Geeft {"beschikbaar": False, ...} als er
    nog te weinig tellingen zijn."""
    nu = nu or datetime.now()
    dagen = max(1, min(int(dagen), 28))
    rijen, tellingen = lees_rijen(db, nu)
    if not rijen:
        return {
            "beschikbaar": False,
            "reden": "Er zijn minstens twee tellingen nodig om te kunnen voorspellen "
            f"(nu {len(tellingen)}). Na de volgende telling verschijnt de prognose.",
            "dagen": dagen,
        }

    eind = nu + timedelta(days=dagen)
    kalender = lees_kalender(
        db,
        min(r["start"] for r in rijen).date() - timedelta(days=2),
        eind.date() + timedelta(days=2),
    )
    _voeg_blootstelling_toe(rijen, kalender, nu)
    effecten, dispersie, informatie = pas_model_aan(rijen)
    snelheid = _snelheden(rijen, effecten)

    # --- blootstelling in het voorspelvenster, ook per dag voor het overzicht
    venster = blootstelling(nu, eind, kalender)
    E_h = drukte(venster, effecten)
    dagen_overzicht = []
    dag = (nu - timedelta(hours=DAG_BEGIN_UUR)).date()
    while _dag_venster(dag)[0] < eind:
        d_begin, d_eind = _dag_venster(dag)
        deel = (min(eind, d_eind) - max(nu, d_begin)).total_seconds() / 86400
        if deel > 0.05:
            k = kalender.get(dag) or {"wedstrijden": 0, "training": False, "weer": None}
            m = 1 + effecten["wedstrijd"] * wedstrijd_gewicht(k["wedstrijden"]) + effecten["training"] * (
                1.0 if k["training"] else 0.0
            ) + effecten["weer"] * (k["weer"] or 0.0)
            dagen_overzicht.append(
                {
                    "datum": dag,
                    "weekdag": _WEEKDAG[dag.weekday()],
                    "weekdag_kort": _WEEKDAG_KORT[dag.weekday()],
                    "deel": min(1.0, deel),
                    "wedstrijden": k["wedstrijden"],
                    "training": k["training"],
                    "weer_score": k["weer"],
                    "drukte": m,
                    "weekend": dag.weekday() >= 5,
                }
            )
        dag += timedelta(days=1)

    # --- per product
    producten = {p["id"]: p for p in db.execute("SELECT * FROM producten WHERE actief = 1").fetchall()}
    op_bestellijst = {p["id"] for p in bestel_suggesties(db)}
    onderweg = {
        r["product_id"]: r["aantal"]
        for r in db.execute(
            """SELECT br.product_id, SUM(br.aantal_besteld) AS aantal FROM bestelregels br
               JOIN bestellingen b ON b.id = br.bestelling_id
               WHERE b.status = 'besteld' GROUP BY br.product_id"""
        ).fetchall()
    }
    rijen_per_product = {}
    for r in rijen:
        rijen_per_product.setdefault(r["pid"], []).append(r)
    gewicht_blootstelling = {
        pid: sum(r["w"] * drukte(r["b"], effecten) for r in lijst if not r["afgekapt"]) or
        sum(r["w"] * drukte(r["b"], effecten) for r in lijst)
        for pid, lijst in rijen_per_product.items()
    }

    uitkomst, omzet_gem, omzet_var = [], 0.0, 0.0
    for pid, snel in snelheid.items():
        product = producten.get(pid)
        if product is None or snel <= 0:
            continue
        mu = snel * E_h
        rel_snelheid_var = dispersie / max(snel * gewicht_blootstelling[pid], 1e-9)
        var = dispersie * mu + (mu ** 2) * (rel_snelheid_var + MODEL_ONZEKERHEID_DAG ** 2 / dagen + 0.05 ** 2)
        voorraad = max(0, product["voorraad"])
        kans = kans_meer_dan(mu, var, voorraad)
        q90 = kwantiel(mu, var, serviceniveau)
        q10 = kwantiel(mu, var, 0.1)
        tekort_na_dekking = max(0, q90 - voorraad - onderweg.get(pid, 0))
        factor = max(1, product["besteleenheid_factor"] or 1)
        eenheden = -(-tekort_na_dekking // factor) if tekort_na_dekking else 0
        per_dag = mu / dagen if dagen else 0
        omzet_gem += mu * product["verkoopprijs"]
        omzet_var += (product["verkoopprijs"] ** 2) * var
        aantal_waarnemingen = len(rijen_per_product[pid])
        uitkomst.append(
            {
                "product": product,
                "voorraad": voorraad,
                "verwacht": mu,
                "laag": q10,
                "hoog": q90,
                "kans_tekort": kans,
                "dekking_dagen": (voorraad / per_dag) if per_dag > 1e-9 else None,
                "status": "urgent" if kans >= 0.5 else "let_op" if kans >= 0.2 else "ok",
                "advies_stuks": eenheden * factor if factor > 1 else tekort_na_dekking,
                "advies_eenheden": eenheden if factor > 1 else None,
                "besteleenheid": product["besteleenheid"] if factor > 1 else None,
                "besteleenheid_factor": factor,
                "al_op_bestellijst": pid in op_bestellijst,
                "onderweg": onderweg.get(pid, 0),
                "waarnemingen": aantal_waarnemingen,
                "weinig_data": aantal_waarnemingen < 3,
                "per_dag": per_dag,
            }
        )
    volgorde = {"urgent": 0, "let_op": 1, "ok": 2}
    uitkomst.sort(key=lambda x: (volgorde[x["status"]], -x["kans_tekort"], x["product"]["categorie"], x["product"]["naam"]))

    sigma_totaal = math.sqrt(omzet_var + (0.1 * omzet_gem) ** 2)
    totaal = {
        "omzet": omzet_gem,
        "laag": max(0.0, omzet_gem - 1.2816 * sigma_totaal),
        "hoog": omzet_gem + 1.2816 * sigma_totaal,
        "gewone_dag": (omzet_gem / E_h) if E_h > 1e-9 else 0.0,
    }
    for d in dagen_overzicht:
        d["omzet"] = totaal["gewone_dag"] * d["drukte"] * d["deel"]
    drukste = max(dagen_overzicht, key=lambda d: d["omzet"], default=None)

    effect_lijst = []
    for sleutel in ("wedstrijd", "training", "weer"):
        waargenomen = _waargenomen_dagen(rijen, kalender, sleutel)
        effect_lijst.append(
            {
                "sleutel": sleutel,
                "naam": EFFECT_NAMEN[sleutel],
                "waarde": effecten[sleutel],
                "aanname": PRIOR[sleutel],
                "waargenomen_dagen": waargenomen,
                "status": _status(waargenomen) if informatie[sleutel] > 0.3 else "aanname",
            }
        )
    eerste = min(r["start"] for r in rijen)
    return {
        "beschikbaar": True,
        "nu": nu,
        "dagen": dagen,
        "dagen_overzicht": dagen_overzicht,
        "drukste_dag": drukste,
        "totaal": totaal,
        "producten": uitkomst,
        "samenvatting": {
            "urgent": sum(1 for p in uitkomst if p["status"] == "urgent"),
            "let_op": sum(1 for p in uitkomst if p["status"] == "let_op"),
            "producten": len(uitkomst),
        },
        "model": {
            "effecten": effect_lijst,
            "dispersie": dispersie,
            "aantal_tellingen": len(tellingen),
            "aantal_producten_in_model": len(snelheid),
            "eerste_datum": eerste,
            "weken_data": (nu - eerste).total_seconds() / (7 * 86400),
            "nauwkeurigheid": terugtoetsen(rijen, nu),
        },
    }
