"""Merkanalyse (Rapporten, beheerders): alles over één merk bij elkaar, bijvoorbeeld voor een gesprek met de vertegenwoordiger.
Wat het verkoopt (per smaak, per maand, tegenover de rest van de categorie), wat het oplevert, hoe de leveringen liepen,
hoeveel er ligt, en wat een betere prijs of gratis dozen per seizoen zou schelen. Plus de gesprekspunten die uit de cijfers
volgen.

Een merk is wat bij het product als merk is ingevuld, of anders het eerste woord van de naam ('Bozu Peach': Bozu). De
bedragen komen uit hetzelfde rapport als Inkoop en verkoop (inkoop_verkoop.bereken_inkoop_verkoop), maar dan netto: wat er
bij een latere telling meer stond dan de app verwachtte (een telfout, vaak een verwisselde smaak), is eerder ten onrechte
als verkocht geteld en gaat er weer af. Zo klopt het met wat er is ingekocht en wat er nog ligt. Btw en statiegeld zitten er
niet in: de verkoopprijs is wat de klant betaalt, de inkoopprijs wat bij het product staat."""

from datetime import date, timedelta

from helpers.producten import besteleenheid_factor, besteleenheid_naam
from inkoop_verkoop import LANG_WEKEN, bereken_inkoop_verkoop, is_correctie
from productkaart import KEUKEN_CATEGORIE

SEIZOEN_WEKEN = 40  # zoveel weken per seizoen is de kantine ongeveer open; op de pagina aan te passen
_ALGEMEEN = {"fles", "flesje", "fust", "blik", "blikje", "los", "de", "het"}
KORTINGEN = (0.50, 1.00, 1.50)  # euro per doos
GRATIS = (20, 10)  # 1 doos gratis op zoveel
NAGEKOMEN_DAGEN = 14
TREND_PER_WEEK = 10  # onder zoveel per week zegt een stijging of daling niets


def merk_van(product):
    """Het merk van een product, of None: het ingevulde merk, anders het eerste woord van de naam dat iets zegt."""
    if (product["merk"] or "").strip():
        return product["merk"].strip()
    woorden = [w for w in product["naam"].replace("-", " ").split() if w.lower() not in _ALGEMEEN]
    return woorden[0] if woorden else None


def merken(db):
    """De merken om uit te kiezen, op naam: elk ingevuld merk, en elk eerste woord dat bij minstens twee producten staat."""
    groepen = {}
    for p in db.execute("SELECT naam, merk, categorie FROM producten WHERE categorie != ?", (KEUKEN_CATEGORIE,)).fetchall():
        naam = merk_van(p)
        if naam:
            g = groepen.setdefault(naam.lower(), {"naam": naam, "aantal": 0, "ingevuld": False})
            g["aantal"] += 1
            g["ingevuld"] = g["ingevuld"] or bool((p["merk"] or "").strip())
    return sorted((g["naam"] for g in groepen.values() if g["ingevuld"] or g["aantal"] >= 2), key=str.lower)


# Verkocht min wat er bij dezelfde telling te veel stond, behalve de eerste keer dat het product geteld is (dan is alles nieuw).
_NETTO = """(tr.verkocht - CASE WHEN tr.correctie > 0 AND EXISTS (
                SELECT 1 FROM telling_regels r2 JOIN tellingen t2 ON t2.id = r2.telling_id
                WHERE r2.product_id = tr.product_id AND t2.datum < t.datum) THEN tr.correctie ELSE 0 END)"""


def _netto(r):
    """Een productregel van Inkoop en verkoop, netto (zie bovenaan): verkocht, omzet, winst, marge en het tempo."""
    verkocht, omzet = r["verkocht"] - r["telverschil"], r["omzet"] - r["telverschil_waarde"]
    winst = omzet - verkocht * r["inkoop_stuk"] if r["heeft_inkoop"] else None
    per_week = r["per_week"] * verkocht / r["verkocht"] if r["per_week"] and r["verkocht"] else r["per_week"]
    return {**r, "verkocht": verkocht, "omzet": omzet, "winst": winst, "per_week": per_week,
            "marge_pct": winst / omzet * 100 if winst is not None and omzet > 0 else None,
            "weken_voorraad": r["voorraad"] / per_week if per_week and per_week > 0 else None}


def _per_maand(db, ids, vanaf):
    """[{"maand" ('2026-11'), "verkocht": {product_id: aantal}, "totaal"}], oudste eerst."""
    maanden = {}
    for r in db.execute(
        f"""SELECT substr(t.datum, 1, 7) AS maand, tr.product_id, SUM({_NETTO}) AS aantal
            FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
            WHERE t.datum >= ? AND tr.product_id IN ({','.join('?' * len(ids))}) GROUP BY 1, 2""",
        (vanaf, *ids),
    ).fetchall():
        maanden.setdefault(r["maand"], {})[r["product_id"]] = r["aantal"] or 0
    return [{"maand": m, "verkocht": v, "totaal": sum(v.values())} for m, v in sorted(maanden.items())]


def _trend(db, ids, vandaag, weken):
    """{product_id: (per week in de eerste helft van de periode, per week in de tweede helft)}, uit de tellingen."""
    midden = (vandaag - timedelta(weeks=weken / 2)).strftime("%Y-%m-%d 00:00")
    vanaf = (vandaag - timedelta(weeks=weken)).strftime("%Y-%m-%d 00:00")
    eerste = db.execute("SELECT MIN(datum) FROM tellingen").fetchone()[0]
    if not eerste or eerste > midden:
        return {}
    weken_voor = max(1.0, (vandaag - timedelta(weeks=weken / 2) - max(_dag(vanaf), _dag(eerste))).days / 7)
    uit = {}
    for r in db.execute(
        f"""SELECT tr.product_id, SUM(CASE WHEN t.datum < ? THEN {_NETTO} ELSE 0 END) AS voor,
                   SUM(CASE WHEN t.datum >= ? THEN {_NETTO} ELSE 0 END) AS na
            FROM telling_regels tr JOIN tellingen t ON t.id = tr.telling_id
            WHERE t.datum >= ? AND tr.product_id IN ({','.join('?' * len(ids))}) GROUP BY 1""",
        (midden, midden, vanaf, *ids),
    ).fetchall():
        uit[r["product_id"]] = ((r["voor"] or 0) / weken_voor, (r["na"] or 0) / (weken / 2))
    return uit


def _dag(tekst):
    return date.fromisoformat(tekst[:10])


def analyse(db, merk, weken, vandaag, seizoen_weken=SEIZOEN_WEKEN):
    """Alles voor de pagina en de pdf, of None als het merk niet bestaat. Zie de sleutels onderaan."""
    alle = {p["id"]: dict(p) for p in db.execute("SELECT * FROM producten").fetchall()}
    ids = [pid for pid, p in alle.items() if p["categorie"] != KEUKEN_CATEGORIE and (merk_van(p) or "").lower() == (merk or "").lower()]
    if not ids:
        return None
    rapport = bereken_inkoop_verkoop(db, weken, vandaag)
    regels = [_netto(r) for r in rapport["producten"]]
    per_id = {r["id"]: r for r in regels}
    vanaf = rapport["vanaf"] + " 00:00"
    trend = _trend(db, ids, vandaag, weken)
    eigen = [per_id[pid] for pid in ids if pid in per_id]
    omzet = sum(r["omzet"] for r in eigen)
    verkocht = sum(r["verkocht"] for r in eigen)
    inkoop = sum(r["inkoop_waarde"] for r in eigen)
    met_inkoop = [r for r in eigen if r["heeft_inkoop"]]
    winst = sum(r["winst"] for r in met_inkoop)
    omzet_met_inkoop = sum(r["omzet"] for r in met_inkoop)

    producten = []
    for r in sorted(eigen, key=lambda r: (-r["verkocht"], r["naam"].lower())):
        p = alle[r["id"]]
        factor = besteleenheid_factor(p)
        voor, na = trend.get(r["id"], (None, None))
        producten.append({
            **r, "kort": _kort(r["naam"], merk), "gearchiveerd": bool(p["gearchiveerd"]), "factor": factor,
            "doos": besteleenheid_naam(p) if factor > 1 else p["eenheid"],
            "inkoop_doos": r["inkoop_stuk"] * factor, "verkoopprijs": p["verkoopprijs"], "minimum": p["min_voorraad"] or 0,
            "aandeel": r["verkocht"] / verkocht * 100 if verkocht else 0.0, "voor": voor, "na": na,
            "verschil_pct": (na - voor) / voor * 100 if voor and voor >= 1 and na is not None else None,
        })

    # De rest van de categorie(ën) van het merk, om mee te vergelijken.
    categorieen = {alle[pid]["categorie"] for pid in ids}
    in_categorie = [r for r in regels if r["categorie"] in categorieen]
    andere = sorted((r for r in in_categorie if r["id"] not in set(ids) and r["verkocht"] > 0), key=lambda r: -r["verkocht"])
    omzet_categorie = sum(r["omzet"] for r in in_categorie)
    omzet_totaal = sum(r["omzet"] for r in regels)
    per_merk = {}
    for r in regels:
        naam = merk_van(alle[r["id"]]) or r["naam"]
        g = per_merk.setdefault(naam.lower(), [naam, 0.0])
        g[1] += r["omzet"]
    rang = sorted(per_merk.values(), key=lambda g: -g[1])
    plek = next((i + 1 for i, g in enumerate(rang) if g[0].lower() == merk.lower()), None)

    # Leveringen: alleen de regels van dit merk.
    leveringen = []
    for b in db.execute(
        f"""SELECT b.id, b.ontvangen_op, br.product_id, br.aantal_besteld, br.aantal_ontvangen
            FROM bestellingen b JOIN bestelregels br ON br.bestelling_id = b.id
            WHERE b.status = 'ontvangen' AND b.ontvangen_op >= ? AND br.product_id IN ({','.join('?' * len(ids))})
            ORDER BY b.ontvangen_op DESC, b.id DESC, br.id""",
        (vanaf, *ids),
    ).fetchall():
        gekregen = b["aantal_ontvangen"] if b["aantal_ontvangen"] is not None else b["aantal_besteld"]
        verschil = gekregen - b["aantal_besteld"]
        leveringen.append({"bestelling_id": b["id"], "datum": b["ontvangen_op"][:10], "naam": _kort(alle[b["product_id"]]["naam"], merk),
                           "besteld": b["aantal_besteld"], "geleverd": gekregen, "verschil": verschil,
                           "nagekomen": _nagekomen(db, b["product_id"], b["ontvangen_op"], -verschil) if verschil < 0 else None})
    prijzen = [
        {"naam": _kort(alle[r["product_id"]]["naam"], merk), "datum": r["datum"][:10], "veld": r["veld"], "oud": r["oude_prijs"], "nieuw": r["nieuwe_prijs"]}
        for r in db.execute(
            f"SELECT * FROM prijs_geschiedenis WHERE product_id IN ({','.join('?' * len(ids))}) ORDER BY datum DESC, id DESC LIMIT 12", ids
        ).fetchall()
    ]

    # Het volume per seizoen: het tempo van deze periode, doorgetrokken over zoveel weken als de kantine open is.
    verkoopweken = rapport["verkoopweken"]
    factoren = {p["factor"] for p in producten if p["verkocht"] > 0}
    doos = factoren.pop() if len(factoren) == 1 else None
    dozen = verkocht / doos / verkoopweken * seizoen_weken if doos and verkoopweken else None
    doosprijs = None
    if doos and met_inkoop and sum(r["verkocht"] for r in met_inkoop):
        doosprijs = sum(r["verkocht"] * r["inkoop_stuk"] for r in met_inkoop) / sum(r["verkocht"] for r in met_inkoop) * doos
    scenario = []
    if dozen and doosprijs:
        scenario = [{"wat": f"€ {k:.2f} per doos korting".replace(".", ","), "scheelt": dozen * k} for k in KORTINGEN]
        scenario += [{"wat": f"1 doos gratis op {n} gekochte dozen", "scheelt": dozen / (n + 1) * doosprijs} for n in GRATIS]

    uit = {
        "merk": next((m for m in (merk_van(alle[pid]) for pid in ids)), merk), "weken": weken, "vanaf": rapport["vanaf"],
        "laatste_telling": rapport["laatste_telling"], "verkoopweken": verkoopweken, "seizoen_weken": seizoen_weken,
        "producten": producten, "andere": andere[:6], "categorieen": sorted(categorieen),
        "totaal": {
            "omzet": omzet, "verkocht": verkocht, "inkoop": inkoop, "inkoop_stuks": sum(r["inkoop"] for r in eigen),
            "winst": winst if met_inkoop else None, "marge_pct": winst / omzet_met_inkoop * 100 if omzet_met_inkoop > 0 else None,
            "per_week": verkocht / verkoopweken if verkoopweken else None,
            "aandeel": omzet / omzet_totaal * 100 if omzet_totaal else None,
            "aandeel_categorie": omzet / omzet_categorie * 100 if omzet_categorie else None,
            "plek": plek, "van": len(rang), "voorraad": sum(r["voorraad"] for r in eigen),
            "voorraad_waarde": sum(r["voorraad_waarde"] for r in eigen), "onderweg": sum(r["onderweg"] for r in eigen),
            "telverschil": sum(r["telverschil"] for r in eigen),
        },
        "per_maand": _per_maand(db, ids, vanaf), "leveringen": leveringen,
        "afwijkend": [v for v in leveringen if v["verschil"]], "prijzen": prijzen,
        "volume": {"doos": doos, "dozen": dozen, "doosprijs": doosprijs, "inkoop": dozen * doosprijs if dozen and doosprijs else None,
                   "scenario": scenario},
    }
    uit["punten"] = gesprekspunten(uit)
    return uit


def _nagekomen(db, product_id, ontvangen_op, tekort):
    """Wat er na een te kleine levering alsnog los is binnengeboekt (zonder bestelling, binnen NAGEKOMEN_DAGEN dagen):
    {"aantal", "datum"}, of None."""
    tot = (_dag(ontvangen_op) + timedelta(days=NAGEKOMEN_DAGEN)).isoformat() + " 23:59"
    rijen = [
        m for m in db.execute(
            """SELECT aantal, datum, opmerking FROM mutaties WHERE product_id = ? AND type = 'in' AND telling_id IS NULL
                 AND bestelling_id IS NULL AND datum >= ? AND datum <= ? ORDER BY datum""",
            (product_id, ontvangen_op[:10], tot),
        ).fetchall() if not is_correctie(m["opmerking"])
    ]
    aantal = min(tekort, sum(m["aantal"] for m in rijen))
    return {"aantal": aantal, "datum": rijen[0]["datum"][:10]} if aantal > 0 else None


def _kort(naam, merk):
    """'Bozu Peach' bij merk Bozu: 'Peach'."""
    kort = naam[len(merk):].strip(" -") if naam.lower().startswith(merk.lower()) else naam
    return kort or naam


def gesprekspunten(a):
    """Wat er uit de cijfers volgt voor het gesprek: [{"titel", "tekst"}]. Alleen wat echt in de cijfers zit."""
    t, punten = a["totaal"], []

    def euro(x):
        return f"€ {x:,.0f}".replace(",", ".")

    def nl(x, d=0):
        return f"{x:.{d}f}".replace(".", ",")

    lopend = [p for p in a["producten"] if p["actief"] and not p["gearchiveerd"]]
    if t["aandeel"] and t["plek"]:
        tekst = f"{a['merk']} is goed voor {nl(t['aandeel'])}% van de omzet (nummer {t['plek']} van de merken)"
        if t["aandeel_categorie"]:
            tekst += f" en {nl(t['aandeel_categorie'])}% van {' en '.join(a['categorieen'])}"
        punten.append({"titel": "Hoe belangrijk dit merk is", "tekst": tekst + "."})
    ander = [r for r in a["andere"] if r["marge_pct"] is not None and r["omzet"] > 0]
    if t["marge_pct"] is not None and ander:
        tekst = f"{a['merk']} {nl(t['marge_pct'])}%, tegen " + ", ".join(f"{r['naam']} {nl(r['marge_pct'])}%" for r in ander[:3]) + "."
        beter = t["marge_pct"] > max(r["marge_pct"] for r in ander)
        punten.append({"titel": "De marge naast de rest",
                       "tekst": tekst + (" Dit merk levert het meeste op: reden om het groot te houden, niet om ermee te stoppen." if beter
                                         else " Andere merken leveren per euro omzet meer op: dat mag je noemen.")})
    v = a["volume"]
    if v["dozen"] and v["scenario"]:
        punten.append({"titel": "Vraag een prijsafspraak op volume",
                       "tekst": f"In dit tempo zijn het ongeveer {nl(v['dozen'])} dozen per seizoen van {a['seizoen_weken']} weken, zo'n "
                                f"{euro(v['inkoop'])} inkoop. {v['scenario'][1]['wat']} scheelt dan {euro(v['scenario'][1]['scheelt'])}."})
    traag = [p for p in lopend if p["weken_voorraad"] is not None and p["weken_voorraad"] >= LANG_WEKEN * 1.5 and p["voorraad"] >= p["factor"]]
    for p in traag:
        punten.append({"titel": f"{p['kort']} loopt traag: ruilen of een actie",
                       "tekst": f"Er staan er {p['voorraad']} ({nl(p['weken_voorraad'])} weken), bij {nl(p['per_week'], 1)} per week. Vraag of "
                                "ongeopende dozen geruild kunnen worden voor een smaak die wel loopt, of om steun voor een actie."})
    beste = [p for p in lopend if p["verkocht"] > 0][:2]
    if len(lopend) > 1 and beste:
        namen = " en ".join(p["kort"] for p in beste)
        punten.append({"titel": f"{namen} {'trekken' if len(beste) > 1 else 'trekt'} het merk",
                       "tekst": f"Samen {nl(sum(p['aandeel'] for p in beste))}% van wat er verkocht wordt. Daar zit de ruimte voor een volumeafspraak."})
    traag_ids = {p["id"] for p in traag}
    for p in lopend:
        if (p["id"] not in traag_ids and p["verschil_pct"] is not None and abs(p["verschil_pct"]) >= 30
                and max(p["voor"], p["na"]) >= TREND_PER_WEEK):
            richting = "groeit" if p["verschil_pct"] > 0 else "zakt terug"
            punten.append({"titel": f"{p['kort']} {richting}",
                           "tekst": f"Van {nl(p['voor'])} naar {nl(p['na'])} per week (eerste tegen tweede helft van de periode; drukke dagen tellen mee). "
                                    + ("Vraag of de levering dat bijhoudt." if p["verschil_pct"] > 0 else "Vraag wat ze elders zien, en wat ze ertegen doen.")})
    tekort = [f for f in a["afwijkend"] if f["verschil"] < 0]
    echt = [f for f in tekort if not f["nagekomen"] or f["nagekomen"]["aantal"] < -f["verschil"]]
    later = [f for f in tekort if f not in echt]
    if a["leveringen"]:
        goed = len(a["leveringen"]) - len(a["afwijkend"])
        if a["afwijkend"]:
            tekst = f"{goed} van de {len(a['leveringen'])} bestelregels kwamen binnen zoals besteld."
            if echt:
                tekst += " Te weinig: " + ", ".join(f"{f['naam']} {f['geleverd']} van {f['besteld']} ({f['datum'][8:]}-{f['datum'][5:7]})" for f in echt[:4]) + "."
            if later:
                tekst += " Later alsnog los binnengekomen: " + ", ".join(f"{f['naam']} {f['nagekomen']['aantal']}" for f in later[:3]) + "."
            extra = [f for f in a["afwijkend"] if f["verschil"] > 0 and f["besteld"] == 0]
            if extra:
                tekst += " Niet besteld, wel geleverd: " + ", ".join(f"{f['naam']} {f['geleverd']} ({f['datum'][8:]}-{f['datum'][5:7]})" for f in extra[:3]) + "."
            punten.append({"titel": "Leveringen weken af", "tekst": tekst + " Ligt dat bij het merk of bij de groothandel?"})
    weg = [p for p in a["producten"] if p["gearchiveerd"] or not p["actief"]]
    if weg:
        punten.append({"titel": "Niet meer in het assortiment",
                       "tekst": f"{', '.join(p['kort'] for p in weg)} (nog {sum(p['verkocht'] for p in weg)} verkocht in deze periode). Komt er iets voor terug?"})
    return punten


# Vragen die niet uit de cijfers komen, maar in zo'n gesprek wel horen.
VRAGEN = (
    "Lopen acties en bonussen rechtstreeks via jullie of via de groothandel, en wat is er dit seizoen nog mogelijk?",
    "Kunnen jullie zorgen voor een koelkast, barmateriaal of een tv-dia voor op de schermen?",
    "Welke nieuwe smaken of seizoenssmaken komen eraan, en kunnen we daar een proefdoos van krijgen?",
    "Wat doen jullie bij een evenement of een toernooi: proeverij, gratis dozen, retour van wat overblijft?",
    "Hoe lang zijn de blikken houdbaar vanaf levering, en ruilen jullie dozen die bijna over de datum zijn?",
    "Wat vragen andere sportkantines voor een blik, en wat verwachten jullie volgend jaar van de inkoopprijs?",
)
