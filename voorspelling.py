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
* Er wordt niet elke dag verkocht: standaard alleen op woensdag en zaterdag
  (instelbaar, met uitzonderingen per datum, zie lees_verkoopdagen). Op een
  gesloten dag is de verwachte verkoop 0 en telt hij niet mee in de
  blootstelling van een periode.
* Per open dag is de "drukte" 1 + effect(thuiswedstrijd) + effect(training) +
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

VERKOOPDAGEN_STANDAARD = (2, 5)  # woensdag en zaterdag (maandag = 0)
_LEGE_DAG = {"wedstrijden": 0, "training": False, "weer": None, "open": True}


def lees_verkoopdagen(db):
    """(weekdagen, uitzonderingen): de weekdagen waarop standaard verkocht wordt
    (maandag = 0) en {datum-tekst: True/False} voor losse datums die daarvan
    afwijken (True = wel open, False = dicht). Zonder instelling: woensdag
    en zaterdag."""
    tekst = None
    try:
        rij = db.execute("SELECT verkoopdagen FROM instellingen WHERE id = 1").fetchone()
        tekst = rij["verkoopdagen"] if rij else None
    except Exception:  # kolom bestaat nog niet (oude database)
        pass
    dagen = {int(x) for x in (tekst or "").split(",") if x.strip().isdigit() and 0 <= int(x) <= 6}
    try:
        uitzonderingen = {
            r["datum"]: bool(r["open"]) for r in db.execute("SELECT datum, open FROM verkoop_uitzonderingen")
        }
    except Exception:  # tabel bestaat nog niet
        uitzonderingen = {}
    return (dagen or set(VERKOOPDAGEN_STANDAARD)), uitzonderingen


def dag_is_open(dag, weekdagen, uitzonderingen):
    """Wordt er op deze datum (date) verkocht?"""
    return uitzonderingen.get(dag.isoformat(), dag.weekday() in weekdagen)


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
    """{datum: {wedstrijden, training, weer, open}} voor van t/m tot (date-objecten).
    Wedstrijden komen uit de gekoppelde teamagenda's, het weer uit de
    opgeslagen weergeschiedenis (laatst bekende verwachting per dag) en voor
    de komende dagen uit de actuele verwachting."""
    wedstrijden = {
        r["datum"]: r["n"]
        for r in db.execute(
            """SELECT datum, COUNT(*) AS n FROM wedstrijden
               WHERE thuis = 1 AND afgelast = 0 AND datum >= ? AND datum <= ? GROUP BY datum""",
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
    weekdagen, uitzonderingen = lees_verkoopdagen(db)
    kalender = {}
    dag = van
    while dag <= tot:
        iso = dag.isoformat()
        open_ = dag_is_open(dag, weekdagen, uitzonderingen)
        kalender[dag] = {
            "wedstrijden": wedstrijden.get(iso, 0),
            "training": dag.weekday() == TRAININGSDAG,
            "weer": weer.get(iso),
            "open": open_,
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
    mee naar rato van hoeveel van zijn 12-12-venster in de periode valt. Een dag
    waarop niet verkocht wordt (zie lees_verkoopdagen) telt helemaal niet mee."""
    D = M = T = S = W = 0.0
    dag = (start - timedelta(hours=DAG_BEGIN_UUR)).date()
    while True:
        d_begin, d_eind = _dag_venster(dag)
        if d_begin >= einde:
            break
        deel = (min(einde, d_eind) - max(start, d_begin)).total_seconds() / 86400
        k = kalender.get(dag) or _LEGE_DAG
        if deel > 0 and k.get("open", True):
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


def lees_rijen(db, nu, weken=MAX_WEKEN_GESCHIEDENIS, eerste_meenemen=False):
    """Eén rij per product per telling: wat is er verkocht in de periode sinds
    het vorige keer dat dit product geteld werd. De eerste telling van een
    product is alleen een nulmeting. Periodes zonder enige verkoop in die hele
    telling (bijv. een nulmeting of een dag waarop alles dicht was) tellen niet mee.
    Met eerste_meenemen=True (voor het verdelen van omzet over dagen) telt de
    eerste telling van een product met verkoop ook mee, als periode vanaf de
    telling ervoor; dat is voor de weekomzet nodig om niets te missen, niet voor
    het leren van snelheden."""
    sinds = (nu - timedelta(weeks=weken)).strftime("%Y-%m-%d %H:%M")
    tellingen = db.execute(
        "SELECT id, datum FROM tellingen WHERE datum >= ? ORDER BY datum, id", (sinds,)
    ).fetchall()
    if len(tellingen) < 2:
        return [], tellingen
    datum_van = {t["id"]: _parse(t["datum"]) for t in tellingen}
    positie = {t["id"]: i for i, t in enumerate(tellingen)}
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
        if eerste_meenemen:
            eerste = lijst[0]
            i = positie[eerste["telling_id"]]
            if i > 0 and eerste["verkocht"] > 0:
                start, einde = datum_van[tellingen[i - 1]["id"]], datum_van[eerste["telling_id"]]
                if einde > start and totaal_per_telling.get(eerste["telling_id"], 0) > 0:
                    rijen.append(
                        {
                            "pid": pid,
                            "tid": eerste["telling_id"],
                            "start": start,
                            "einde": einde,
                            "V": max(0, eerste["verkocht"]),
                            "afgekapt": eerste["geteld_aantal"] <= 0,
                            "prijs": eerste["verkoopprijs"] or 0.0,
                            "eerste": True,
                        }
                    )
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
    # Een periode zonder enige open dag zegt niets over de snelheid per open dag
    # (er is dan verkocht op een dag die als gesloten staat, bijvoorbeeld een
    # evenement): buiten het model laten. Voor de weekomzet blijft de verkoop wel
    # meetellen, zie verdeling().
    rijen[:] = [r for r in rijen if r["b"]["D"] > 1e-9]
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


def _halve_afwijking(v, mu, k):
    """Halve negatief-binomiale afwijking tussen waargenomen v en verwacht mu,
    met relatieve overspreiding k (variantie = mu + k*mu^2). Voor grote
    aantallen telt een gemiste voorspelling zo veel minder zwaar dan bij een
    gewone Poisson, want daar is de dag-tot-dag-schommeling groter dan wat
    Poisson aanneemt."""
    if mu <= 1e-9:
        return v * 10.0  # voorspeld 0 maar toch verkocht: flink straffen
    if k < 1e-6:
        return (v * math.log(v / mu) if v > 0 else 0.0) - v + mu
    eerste = v * math.log(v / mu) if v > 0 else 0.0
    return eerste - (v + 1.0 / k) * math.log((1 + k * v) / (1 + k * mu))


def _doelfunctie(voorbewerkt, effecten, k):
    """Gewogen afwijking van alle producten plus de strafterm voor het
    afwijken van de aannames."""
    a, b, c = effecten["wedstrijd"], effecten["training"], effecten["weer"]
    afwijking = 0.0
    for ws, vs, ds, ms, ts, ss in voorbewerkt:
        es = [d + a * m + b * t + c * s for d, m, t, s in zip(ds, ms, ts, ss)]
        noemer = sum(w * e for w, e in zip(ws, es))
        if noemer <= 1e-9:
            continue
        r = sum(w * v for w, v in zip(ws, vs)) / noemer
        for w, v, e in zip(ws, vs, es):
            afwijking += w * _halve_afwijking(v, r * e, k)
    straf = sum(0.5 * ((effecten[n] - PRIOR[n]) / ONZEKERHEID[n]) ** 2 for n in PRIOR)
    return afwijking + straf


def _leer_effecten(rijen, k, vrij, ronden=4):
    """Coordinate descent per effect, met de aannames als startpunt: eerst een
    grof raster over het hele toegestane bereik, daarna steeds fijner rond de
    beste waarde. 'vrij' bepaalt welke effecten data hebben om van te leren;
    de rest blijft bij de aanname."""
    voorbewerkt = _voorbewerk(rijen)
    effecten = dict(PRIOR)
    beste = _doelfunctie(voorbewerkt, effecten, k)
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
                score = _doelfunctie(voorbewerkt, proef, k)
                if score < beste - 1e-9:
                    beste, effecten, veranderd = score, proef, True
        if not veranderd and ronde >= 1:
            break
    return effecten


START_OVERSPREIDING = 0.15


def _schat_overspreiding(rijen, effecten, snelheid):
    """Hoeveel meer de verkoop schommelt dan een zuivere Poisson, uitgedrukt
    als relatieve overspreiding k (variantie = mu + k*mu^2), via de
    momentenmethode. Een kantine heeft rustige en drukke weken die je niet
    kunt voorspellen; dat zit hierin. Staat tussen 0,002 en 1,5."""
    teller = noemer = 0.0
    n = 0
    for r in rijen:
        mu = snelheid.get(r["pid"], 0.0) * drukte(r["b"], effecten)
        if mu > 1e-9:
            teller += r["w"] * ((r["V"] - mu) ** 2 - mu)
            noemer += r["w"] * mu ** 2
            n += 1
    if n < 15 or noemer <= 1e-9:
        return START_OVERSPREIDING
    return min(1.5, max(0.002, teller / noemer))


def pas_model_aan(rijen, licht=False):
    """Leert de drie effecten + de overspreiding uit de rijen. Geeft ook terug
    hoeveel er per effect te leren viel (voor de uitleg). 'licht' = sneller en
    minder precies (voor de terugtoetsing, die het vaak achter elkaar doet)."""
    # Alleen de best verkopende producten sturen het leren (sneller, en de
    # zeldzame producten zijn te ruis-gevoelig om iets over drukte te zeggen).
    totaal = {}
    for r in rijen:
        totaal[r["pid"]] = totaal.get(r["pid"], 0.0) + r["w"] * r["V"]
    rijen_per_product = {}
    for r in rijen:
        if not r["afgekapt"]:
            rijen_per_product[r["pid"]] = rijen_per_product.get(r["pid"], 0) + 1
    kandidaten = {
        pid
        for pid, _ in sorted(totaal.items(), key=lambda x: -x[1])
        if rijen_per_product.get(pid, 0) >= MIN_RIJEN_PER_PRODUCT
    }
    kandidaten = set(list(sorted(kandidaten, key=lambda pid: -totaal[pid]))[:MODEL_MAX_PRODUCTEN])
    leer_rijen = [r for r in rijen if r["pid"] in kandidaten and not r["afgekapt"]]

    informatie = {
        "wedstrijd": sum(r["w"] * r["b"]["M"] for r in leer_rijen),
        "training": sum(r["w"] * r["b"]["T"] for r in leer_rijen),
        "weer": sum(r["w"] * abs(r["b"]["S"]) for r in leer_rijen),
    }
    vrij = {n: informatie[n] > 0.3 for n in PRIOR}
    effecten = dict(PRIOR)
    k = START_OVERSPREIDING
    if leer_rijen:
        for _ in range(2 if licht else 3):
            if any(vrij.values()):
                effecten = _leer_effecten(leer_rijen, k, vrij, ronden=3 if licht else 4)
            k = _schat_overspreiding(leer_rijen, effecten, _snelheden(leer_rijen, effecten))
    return effecten, k, informatie


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
    def mediaan(waarden):
        gesorteerd = sorted(waarden)
        midden = len(gesorteerd) // 2
        return gesorteerd[midden] if len(gesorteerd) % 2 else (gesorteerd[midden - 1] + gesorteerd[midden]) / 2

    # De mediaan is eerlijker dan het gemiddelde: een enkele uitschieter (een
    # uitzonderlijk stille of drukke week) trekt het gemiddelde anders omhoog.
    mape_model, mape_naief = mediaan(afwijkingen_model), mediaan(afwijkingen_naief)
    return {
        "aantal": len(afwijkingen_model),
        "mape_model": mape_model,
        "mape_naief": mape_naief,
        "gemiddeld_model": sum(afwijkingen_model) / len(afwijkingen_model),
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
            if k and k.get("open", True):
                if (soort == "wedstrijd" and k["wedstrijden"]) or (soort == "training" and k["training"]) or (
                    soort == "weer" and k["weer"] not in (None, 0.0)
                ):
                    dagen.add(dag)
            dag += timedelta(days=1)
    return len(dagen)


def _gemeenschappelijke_schommeling(rijen, effecten, snelheid):
    """Hoe ver de totale omzet van een telling gemiddeld van de verwachting
    zit, als fractie. Dat is de schommeling die alle producten tegelijk raakt
    (een stille of een drukke week) en die je niet per product kunt wegmiddelen.
    Staat tussen 0,10 en 0,70; zonder genoeg tellingen 0,30."""
    per_telling = {}
    for r in rijen:
        mu = snelheid.get(r["pid"], 0.0) * drukte(r["b"], effecten) * r["prijs"]
        groep = per_telling.setdefault(r["tid"], [0.0, 0.0, 0, 0.0])
        groep[0] += r["V"] * r["prijs"]
        groep[1] += mu
        groep[2] += 1
        groep[3] = max(groep[3], r["w"])
    afwijkingen = [
        (((waar - verwacht) / verwacht) ** 2, w)
        for waar, verwacht, n, w in per_telling.values()
        if n >= 5 and verwacht > 1e-9
    ]
    if len(afwijkingen) < 3:
        return 0.30
    gemiddeld = sum(a * w for a, w in afwijkingen) / sum(w for _, w in afwijkingen)
    return min(0.70, max(0.10, math.sqrt(gemiddeld) * 1.15))


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
    effecten, overspreiding, informatie = pas_model_aan(rijen)
    snelheid = _snelheden(rijen, effecten)
    sigma_gemeenschappelijk = _gemeenschappelijke_schommeling(rijen, effecten, snelheid)

    # --- blootstelling in het voorspelvenster, ook per dag voor het overzicht
    venster = blootstelling(nu, eind, kalender)
    E_h = drukte(venster, effecten)
    dagen_overzicht = []
    dag = (nu - timedelta(hours=DAG_BEGIN_UUR)).date()
    while _dag_venster(dag)[0] < eind:
        d_begin, d_eind = _dag_venster(dag)
        deel = (min(eind, d_eind) - max(nu, d_begin)).total_seconds() / 86400
        if deel > 0.05:
            kenmerken = kalender.get(dag) or _LEGE_DAG
            open_ = kenmerken.get("open", True)
            m = 1 + effecten["wedstrijd"] * wedstrijd_gewicht(kenmerken["wedstrijden"]) + effecten["training"] * (
                1.0 if kenmerken["training"] else 0.0
            ) + effecten["weer"] * (kenmerken["weer"] or 0.0)
            if not open_:
                m = 0.0  # gesloten: er wordt niets verkocht
            dagen_overzicht.append(
                {
                    "open": open_,
                    "datum": dag,
                    "weekdag": _WEEKDAG[dag.weekday()],
                    "weekdag_kort": _WEEKDAG_KORT[dag.weekday()],
                    "deel": min(1.0, deel),
                    "wedstrijden": kenmerken["wedstrijden"],
                    "training": kenmerken["training"],
                    "weer_score": kenmerken["weer"],
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
    gewicht_som = {
        pid: sum(r["w"] for r in lijst if not r["afgekapt"]) or sum(r["w"] for r in lijst)
        for pid, lijst in rijen_per_product.items()
    }
    gewicht_blootstelling = {
        pid: sum(r["w"] * drukte(r["b"], effecten) for r in lijst if not r["afgekapt"]) or
        sum(r["w"] * drukte(r["b"], effecten) for r in lijst)
        for pid, lijst in rijen_per_product.items()
    }

    uitkomst, omzet_gem, omzet_toeval = [], 0.0, 0.0
    for pid, snel in snelheid.items():
        product = producten.get(pid)
        if product is None or snel <= 0:
            continue
        mu = snel * E_h
        # Onzekerheid: gewone toevalsspreiding (Poisson) + de extra schommeling
        # tussen periodes (overspreiding) + onzekerheid over de snelheid zelf.
        rel_snelheid_var = 1.0 / max(snel * gewicht_blootstelling[pid], 1e-9) + overspreiding / max(gewicht_som[pid], 1.0)
        var = mu + (mu ** 2) * (overspreiding + rel_snelheid_var + 0.03 ** 2)
        voorraad = max(0, product["voorraad"])
        aanwezig = voorraad + onderweg.get(pid, 0)  # voorraad plus wat al besteld is
        kans = kans_meer_dan(mu, var, aanwezig)
        status = "urgent" if kans >= 0.5 else "let_op" if kans >= 0.2 else "ok"
        q90 = kwantiel(mu, var, serviceniveau)
        q10 = kwantiel(mu, var, 0.1)
        # Alleen adviseren als er echt een risico is; voor de rest "voldoende".
        tekort_na_dekking = max(0, q90 - aanwezig) if status != "ok" else 0
        factor = max(1, product["besteleenheid_factor"] or 1)
        eenheden = -(-tekort_na_dekking // factor) if tekort_na_dekking else 0
        per_dag = mu / dagen if dagen else 0
        omzet_gem += mu * product["verkoopprijs"]
        omzet_toeval += (product["verkoopprijs"] ** 2) * mu
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
                "status": status,
                "nu_op": voorraad == 0,
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

    # Totale omzet: toeval per product + de schommeling die alle producten
    # tegelijk raakt (een stille of drukke week), die uit de eigen tellingen komt.
    relatief = math.sqrt((omzet_toeval / omzet_gem ** 2 if omzet_gem > 0 else 0.0) + sigma_gemeenschappelijk ** 2)
    sigma_ln = math.sqrt(math.log(1 + relatief ** 2))  # log-normaal: nooit onder nul
    totaal = {
        "omzet": omzet_gem,
        "laag": omzet_gem * math.exp(-1.2816 * sigma_ln),
        "hoog": omzet_gem * math.exp(1.2816 * sigma_ln),
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
    nauwkeurigheid = terugtoetsen(rijen, nu)
    weken_data = (nu - eerste).total_seconds() / (7 * 86400)
    if len(tellingen) < 15 or weken_data < 8 or nauwkeurigheid is None:
        betrouwbaarheid = "laag"
    elif nauwkeurigheid["mape_model"] < 0.25:
        betrouwbaarheid = "goed"
    elif nauwkeurigheid["mape_model"] < 0.45:
        betrouwbaarheid = "redelijk"
    else:
        betrouwbaarheid = "laag"
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
            "overspreiding": overspreiding,
            "sigma_gemeenschappelijk": sigma_gemeenschappelijk,
            "aantal_tellingen": len(tellingen),
            "aantal_producten_in_model": len(snelheid),
            "eerste_datum": eerste,
            "weken_data": weken_data,
            "nauwkeurigheid": nauwkeurigheid,
            "betrouwbaarheid": betrouwbaarheid,
        },
    }


def wedstrijden_op_gesloten_dagen(db, nu=None, weken_terug=8, dagen_vooruit=21):
    """Thuiswedstrijden op een dag waarop standaard niet verkocht wordt en waar nog
    niets over is vastgelegd: [{"datum", "weekdag", "wedstrijden": [omschrijving],
    "toekomst"}]. De pagina vraagt dan of er die dag toch verkocht wordt, want een
    wedstrijd op bijvoorbeeld zondag levert meestal wel omzet op."""
    nu = nu or datetime.now()
    weekdagen, uitzonderingen = lees_verkoopdagen(db)
    van = nu.date() - timedelta(weeks=weken_terug)
    tot = nu.date() + timedelta(days=dagen_vooruit)
    per_datum = {}
    for r in db.execute(
        "SELECT datum, omschrijving FROM wedstrijden WHERE thuis = 1 AND afgelast = 0 AND datum >= ? AND datum <= ? ORDER BY datum, id",
        (van.isoformat(), tot.isoformat()),
    ).fetchall():
        per_datum.setdefault(r["datum"], []).append(r["omschrijving"] or "Thuiswedstrijd")
    uitkomst = []
    for iso, lijst in sorted(per_datum.items()):
        dag = date.fromisoformat(iso)
        if iso in uitzonderingen or dag.weekday() in weekdagen:
            continue
        uitkomst.append(
            {"datum": dag, "weekdag": _WEEKDAG[dag.weekday()], "wedstrijden": lijst, "toekomst": dag >= nu.date()}
        )
    return uitkomst


# ---------------------------------------------------------------------------
# Wat zou er nu in het schap moeten staan? (voor de looplijst)
# ---------------------------------------------------------------------------

MIN_WAARNEMINGEN_VERWACHTING = 3  # eerder zegt het model te weinig over één product
_VERWACHT_CACHE = {}  # (database, telling, kwartier) -> uitkomst; de looplijst vraagt dit bij elk product
_VERWACHT_CACHE_MAX = 4


def verwachte_verkoop_sinds_telling(db, nu=None):
    """Per product: hoeveel er volgens het model verkocht is sinds de laatste
    telling van dat product, met een ruime marge. De geregistreerde voorraad
    is namelijk de stand van de laatste telling plus wat er sindsdien is
    ingeboekt; de verkoop ertussen weet de app pas bij de volgende telling.
    Daarmee kan de looplijst tonen wat er ongeveer in het schap hoort te staan
    en een telling die daar ver naast zit laten controleren.

    Geeft {product_id: {"verwacht", "laag", "hoog", "ruim_laag", "ruim_hoog",
    "sinds", "waarnemingen"}}; leeg zolang er te weinig tellingen zijn. Het
    resultaat wordt kort bewaard (het model aanpassen kost wat rekentijd en de
    looplijst vraagt het voor elk product opnieuw)."""
    nu = nu or datetime.now()
    laatste = db.execute(
        "SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS laatste FROM tellingen"
    ).fetchone()
    sleutel = (db.execute("PRAGMA database_list").fetchone()[2], laatste["n"], laatste["laatste"], int(nu.timestamp() // 900))
    if sleutel in _VERWACHT_CACHE:
        return _VERWACHT_CACHE[sleutel]

    uitkomst = {}
    rijen, _ = lees_rijen(db, nu)
    if rijen:
        kalender = lees_kalender(
            db, min(r["start"] for r in rijen).date() - timedelta(days=2), nu.date() + timedelta(days=2)
        )
        _voeg_blootstelling_toe(rijen, kalender, nu)
        effecten, overspreiding, _informatie = pas_model_aan(rijen)
        snelheid = _snelheden(rijen, effecten)
        rijen_per_product = {}
        for r in rijen:
            rijen_per_product.setdefault(r["pid"], []).append(r)
        laatste_telling = {
            r["product_id"]: _parse(r["laatste"])
            for r in db.execute(
                """SELECT tr.product_id, MAX(t.datum) AS laatste
                   FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
                   GROUP BY tr.product_id"""
            ).fetchall()
        }
        for pid, snel in snelheid.items():
            sinds = laatste_telling.get(pid)
            lijst = rijen_per_product[pid]
            if snel <= 0 or sinds is None or sinds >= nu or len(lijst) < MIN_WAARNEMINGEN_VERWACHTING:
                continue
            gewicht_som = sum(r["w"] for r in lijst if not r["afgekapt"]) or sum(r["w"] for r in lijst)
            gewicht_blootstelling = sum(
                r["w"] * drukte(r["b"], effecten) for r in lijst if not r["afgekapt"]
            ) or sum(r["w"] * drukte(r["b"], effecten) for r in lijst)
            mu = snel * drukte(blootstelling(sinds, nu, kalender), effecten)
            rel_snelheid_var = 1.0 / max(snel * gewicht_blootstelling, 1e-9) + overspreiding / max(gewicht_som, 1.0)
            var = mu + (mu ** 2) * (overspreiding + rel_snelheid_var + 0.03 ** 2)
            uitkomst[pid] = {
                "verwacht": mu,
                "laag": kwantiel(mu, var, 0.1),
                "hoog": kwantiel(mu, var, 0.9),
                "ruim_laag": kwantiel(mu, var, 0.02),
                "ruim_hoog": kwantiel(mu, var, 0.98),
                "sinds": sinds,
                "waarnemingen": len(lijst),
            }
    if len(_VERWACHT_CACHE) >= _VERWACHT_CACHE_MAX:
        _VERWACHT_CACHE.clear()
    _VERWACHT_CACHE[sleutel] = uitkomst
    return uitkomst


def verwachte_voorraad(verwachting, voorraad):
    """Wat er ongeveer in het schap hoort te staan: {"verwacht", "laag", "hoog"}
    (aantallen, nooit onder 0), of None zonder bruikbare verwachting."""
    if not verwachting:
        return None
    return {
        "verwacht": max(0, round(voorraad - verwachting["verwacht"])),
        "laag": max(0, voorraad - verwachting["hoog"]),
        "hoog": max(0, voorraad - verwachting["laag"]),
    }


def telling_ver_van_verwachting(verwachting, voorraad, geteld):
    """'minder' of 'meer' als het getelde aantal ruim buiten de verwachting
    valt (ruimer dan de gewone marge, en alleen bij een merkbaar verschil),
    anders None. 'minder' kan een telfout zijn, of verlies; 'meer' wijst vaak op
    een levering die nog niet is ingeboekt."""
    if not verwachting:
        return None
    verwacht = verwachting["verwacht"]
    slack = max(2, 0.25 * verwacht)
    if geteld < voorraad - verwachting["ruim_hoog"] - slack:
        return "minder"
    if geteld > voorraad - verwachting["ruim_laag"] + slack:
        return "meer"
    return None


# ---------------------------------------------------------------------------
# Omzet per week, ook als je niet elke week op dezelfde dag telt
# ---------------------------------------------------------------------------


def _dagdrukte(dag, kalender, effecten):
    kenmerken = kalender.get(dag) or {
        "wedstrijden": 0, "training": dag.weekday() == TRAININGSDAG, "weer": None, "open": True,
    }
    if not kenmerken.get("open", True):
        return 0.0  # gesloten: daar wordt niets verkocht
    return (
        1.0
        + effecten["wedstrijd"] * wedstrijd_gewicht(kenmerken["wedstrijden"])
        + effecten["training"] * (1.0 if kenmerken["training"] else 0.0)
        + effecten["weer"] * (kenmerken["weer"] or 0.0)
    )


def verdeling(db, nu=None):
    """Verdeelt de verkoop van elke periode tussen twee tellingen over de dagen
    waarin die verkocht is, waarbij een drukke dag (thuiswedstrijd, training,
    mooi weer) zwaarder weegt dan een gewone. Zo is de verkoop van een telling
    van vrijdag tot woensdag netjes over dat weekend en de dagen erna verdeeld,
    ongeacht op welke dagen je telt. Binnen een periode is dat een schatting,
    maar de som klopt altijd met de tellingen.

    Geeft {"omzet": {datum: euro}, "producten": {datum: {product_id: [aantal,
    euro]}}, "eerste": datetime, "laatste": datetime} (eerste/laatste = de
    eerste en laatste telling), of None als er nog geen telling is."""
    nu = nu or datetime.now()
    rijen, tellingen = lees_rijen(db, nu, weken=520, eerste_meenemen=True)
    if not tellingen:
        return None
    eerste, laatste = _parse(tellingen[0]["datum"]), _parse(tellingen[-1]["datum"])
    uitkomst = {"omzet": {}, "producten": {}, "eerste": eerste, "laatste": laatste}
    if not rijen:
        return uitkomst
    kalender = lees_kalender(
        db, min(r["start"] for r in rijen).date() - timedelta(days=2), laatste.date() + timedelta(days=2)
    )
    # De effecten komen uit de recente tellingen (zoals de prognose); oudere perioden
    # worden daarmee verdeeld.
    recent = [
        r for r in rijen if r["einde"] >= nu - timedelta(weeks=MAX_WEKEN_GESCHIEDENIS) and not r.get("eerste")
    ]
    _voeg_blootstelling_toe(recent, kalender, nu)
    effecten = pas_model_aan(recent)[0] if recent else dict(PRIOR)

    gewichten_per_periode = {}
    for r in rijen:
        sleutel = (r["start"], r["einde"])
        if sleutel not in gewichten_per_periode:
            gewichten, delen = {}, {}
            dag = (r["start"] - timedelta(hours=DAG_BEGIN_UUR)).date()
            while _dag_venster(dag)[0] < r["einde"]:
                d_begin, d_eind = _dag_venster(dag)
                deel = (min(r["einde"], d_eind) - max(r["start"], d_begin)).total_seconds() / 86400
                if deel > 0:
                    delen[dag] = deel
                    gewichten[dag] = deel * _dagdrukte(dag, kalender, effecten)
                dag += timedelta(days=1)
            totaal = sum(gewichten.values())
            if totaal <= 0 and delen:
                # Geen enkele open dag in deze periode, maar er is wel verkocht (bijvoorbeeld
                # een evenement op een gesloten dag): gelijk verdelen, zodat de omzet nooit verdwijnt.
                gewichten, totaal = dict(delen), sum(delen.values())
            gewichten_per_periode[sleutel] = {d: g / totaal for d, g in gewichten.items()} if totaal > 0 else {}
        for dag, aandeel in gewichten_per_periode[sleutel].items():
            if aandeel <= 0:
                continue  # gesloten dag: geen verkoop
            omzet = r["V"] * r["prijs"] * aandeel
            uitkomst["omzet"][dag] = uitkomst["omzet"].get(dag, 0.0) + omzet
            regel = uitkomst["producten"].setdefault(dag, {}).setdefault(r["pid"], [0.0, 0.0])
            regel[0] += r["V"] * aandeel
            regel[1] += omzet
    return uitkomst


def omzet_per_dag(db, nu=None):
    """({datum: omzet}, eerste telling, laatste telling), zie verdeling()."""
    data = verdeling(db, nu)
    if data is None:
        return {}, None, None
    return data["omzet"], data["eerste"], data["laatste"]


def _week_status(maandag, eerste, laatste):
    """'compleet' als de tellingen de hele week dekken, 'begin' als de eerste
    telling pas midden in de week viel en 'loopt_nog' als de laatste telling
    vóór het einde van de week ligt. Een week loopt in de kantine van maandag
    12.00 uur tot maandag 12.00 uur; een telling na maandag 00.00 uur telt als
    'tot en met zondag', want daartussen verkoopt niemand meer iets."""
    venster_begin = datetime.combine(maandag, time(DAG_BEGIN_UUR, 0))
    venster_eind = venster_begin + timedelta(days=7)
    if eerste > venster_begin:
        return "begin"
    if laatste < venster_eind - timedelta(hours=DAG_BEGIN_UUR):
        return "loopt_nog"
    return "compleet"


def omzet_per_week(db, nu=None):
    """Omzet per kalenderweek (maandag t/m zondag), nieuwste week eerst, uit
    verdeling(). Per week staat erbij of alle dagen gedekt zijn door tellingen
    (zie _week_status). Alleen complete weken zijn bruikbaar voor een trend."""
    data = verdeling(db, nu)
    if data is None:
        return []
    eerste, laatste = data["eerste"], data["laatste"]
    weken = {}
    for dag, omzet in data["omzet"].items():
        jaar, week, _ = dag.isocalendar()
        weken[(jaar, week)] = weken.get((jaar, week), 0.0) + omzet
    # Ook de weken waarin wel geteld is maar niets verkocht (bijv. alleen de nulmeting).
    dag = eerste.date()
    while dag <= laatste.date():
        jaar, week, _ = dag.isocalendar()
        weken.setdefault((jaar, week), 0.0)
        dag += timedelta(days=7)
    resultaat = []
    for (jaar, week), omzet in weken.items():
        maandag = date.fromisocalendar(jaar, week, 1)
        status = _week_status(maandag, eerste, laatste)
        resultaat.append(
            {
                "jaar": jaar,
                "week": week,
                "van": maandag.isoformat(),
                "tot": (maandag + timedelta(days=6)).isoformat(),
                "omzet": omzet,
                "status": status,
                # Voor bereken_trend: alleen volledig gedekte weken tellen mee.
                "afwijkende_periode": status != "compleet",
                "geteld_tot": laatste,
            }
        )
    resultaat.sort(key=lambda w: (w["jaar"], w["week"]), reverse=True)
    return resultaat


def week_samenvatting(db, maandag, nu=None, data=None):
    """Omzet en best verkopende producten van de week die begint op 'maandag'
    (een date), uit verdeling(): dus de verkoop van die week zelf, ook als er
    op andere dagen geteld is. Geeft None als er geen tellingen zijn."""
    data = data or verdeling(db, nu)
    if data is None:
        return None
    dagen = [maandag + timedelta(days=i) for i in range(7)]
    omzet = sum(data["omzet"].get(d, 0.0) for d in dagen)
    per_product = {}
    for d in dagen:
        for pid, (aantal, euro) in data["producten"].get(d, {}).items():
            regel = per_product.setdefault(pid, [0.0, 0.0])
            regel[0] += aantal
            regel[1] += euro
    top = []
    for pid, (aantal, euro) in sorted(per_product.items(), key=lambda x: -x[1][1])[:6]:
        if aantal < 0.5:
            continue
        p = db.execute(
            "SELECT naam, eenheid, categorie, subcategorie FROM producten WHERE id = ?", (pid,)
        ).fetchone()
        if p:
            top.append(
                {
                    "product_naam": p["naam"],
                    "eenheid": p["eenheid"],
                    "categorie": p["categorie"],
                    "subcategorie": p["subcategorie"],
                    "verkocht": int(round(aantal)),
                    "omzet": euro,
                }
            )
    return {
        "omzet": omzet,
        "top_verkopers": top,
        "status": _week_status(maandag, data["eerste"], data["laatste"]),
        "geteld_tot": data["laatste"],
    }
