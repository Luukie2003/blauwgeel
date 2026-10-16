"""Het voorspelmodel, deel 2: de verkoop per periode uit de tellingen lezen, de effecten en de overspreiding daaruit
leren, de kansrekening (negatief-binomiaal) en de terugtoetsing. Zie voorspelling/__init__.py."""

import math
from datetime import datetime, timedelta
from statistics import NormalDist

from voorspelling.basis import (
    aanname,
    blootstelling,
    drukte,
    grenzen,
    HALVERING_WEKEN,
    MAX_WEKEN_GESCHIEDENIS,
    MIN_RIJEN_PER_PRODUCT,
    MODEL_MAX_PRODUCTEN,
    onzekerheid,
    PRIOR,
    TEAM_PREFIX,
    TERUGTOETS_START,
)


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
            [r["b"].get("E", 0.0) for r in lijst],
            [r["b"].get("R", 0.0) for r in lijst],
            [r["b"].get("G") or {} for r in lijst],
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
    a, b, c, f, g = effecten["wedstrijd"], effecten["training"], effecten["weer"], effecten["evenement"], effecten["rustig"]
    afwijking = 0.0
    for ws, vs, ds, ms, ts, ss, evs, rs, gs in voorbewerkt:
        es = [
            max(0.0, d + a * m + b * t + c * s + f * ev + g * r
                + (sum(effecten.get(groep, 0.0) * deel for groep, deel in gr.items()) if gr else 0.0))
            for d, m, t, s, ev, r, gr in zip(ds, ms, ts, ss, evs, rs, gs)
        ]
        noemer = sum(w * e for w, e in zip(ws, es))
        if noemer <= 1e-9:
            continue
        r = sum(w * v for w, v in zip(ws, vs)) / noemer
        for w, v, e in zip(ws, vs, es):
            afwijking += w * _halve_afwijking(v, r * e, k)
    straf = sum(0.5 * ((effecten[n] - aanname(n)) / onzekerheid(n)) ** 2 for n in effecten)
    return afwijking + straf


def _leer_effecten(rijen, k, vrij, ronden=4):
    """Coordinate descent per effect, met de aannames als startpunt: eerst een
    grof raster over het hele toegestane bereik, daarna steeds fijner rond de
    beste waarde. 'vrij' bepaalt welke effecten data hebben om van te leren;
    de rest blijft bij de aanname."""
    voorbewerkt = _voorbewerk(rijen)
    effecten = {**PRIOR, **{naam: aanname(naam) for naam in vrij}}
    beste = _doelfunctie(voorbewerkt, effecten, k)
    for ronde in range(ronden):
        veranderd = False
        for naam in vrij:
            if not vrij[naam]:
                continue
            laag, hoog = grenzen(naam)
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
        "evenement": sum(r["w"] * r["b"].get("E", 0.0) for r in leer_rijen),
        "rustig": sum(r["w"] * r["b"].get("R", 0.0) for r in leer_rijen),
    }
    # De bijstelling per groep (zie basis.GROEP_PREFIX): alleen voor groepen die in de tellingen voorkomen.
    for r in leer_rijen:
        for groep, deel in (r["b"].get("G") or {}).items():
            informatie[groep] = informatie.get(groep, 0.0) + r["w"] * deel
    # Een team is alleen te onderscheiden van 'een thuiswedstrijd' als er ook thuiswedstrijddagen zonder dat team zijn;
    # anders (één team, of een team dat altijd speelt) leert alleen het effect van een thuiswedstrijd.
    for team in [n for n in informatie if n.startswith(TEAM_PREFIX)]:
        zonder = sum(r["w"] * max(0.0, r["b"].get("MD", 0.0) - (r["b"].get("G") or {}).get(team, 0.0)) for r in leer_rijen)
        if zonder <= 0.3:
            del informatie[team]
    vrij = {n: informatie.get(n, 0.0) > 0.3 for n in [*PRIOR, *(n for n in informatie if n not in PRIOR)]}
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
