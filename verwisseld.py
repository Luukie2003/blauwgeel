"""Zijn twee smaken bij het tellen door elkaar gehaald? Van de ene Bozu staat er meer dan kan, van de andere minder dan
verwacht: dan is er waarschijnlijk een doos bij de verkeerde smaak geteld. Twee producten horen bij elkaar als ze dezelfde
categorie en hetzelfde merk hebben (of hetzelfde eerste woord in de naam, zoals 'Bozu'). Het is een vraag, geen oordeel.

Op het controlescherm van de looplijst (vooraf, met het voorspelmodel) en bij de telling zelf (achteraf, met het gewone
tempo uit eerdere tellingen; ook voor een telling van de handterminal)."""

from datetime import datetime, timedelta

from voorraadduur import verkoop_per_week

MIN_VERSCHIL = 3  # kleiner is gewoon een telfoutje
MIN_VERHOUDING = 0.4  # het kleinste van de twee verschillen ten opzichte van het grootste
_ALGEMEEN = {"fles", "flesje", "fust", "blik", "blikje", "los", "de", "het"}


def _familie(product):
    woorden = [w for w in product["naam"].lower().replace("-", " ").split() if w not in _ALGEMEEN]
    merk = (product["merk"] or "").strip().lower()
    naam = merk or (woorden[0] if woorden else "")
    return ((product["categorie"] or "").lower(), naam) if naam else None


def _paren(kandidaten):
    """kandidaten: [{"id", "naam", "familie", "verschil"}], verschil > 0 = te veel geteld, < 0 = te weinig. De paren die
    het best bij elkaar passen: [{"meer", "minder" (kandidaten), "aantal"}]; elk product zit in hooguit één paar."""
    mogelijk = []
    for a in kandidaten:
        for b in kandidaten:
            if a["familie"] is None or a["familie"] != b["familie"] or a["verschil"] < MIN_VERSCHIL or -b["verschil"] < MIN_VERSCHIL:
                continue
            klein, groot = sorted((a["verschil"], -b["verschil"]))
            if klein / groot >= MIN_VERHOUDING:
                mogelijk.append((klein / groot, klein, a, b))
    mogelijk.sort(key=lambda m: (-m[0], -m[1], m[2]["naam"], m[3]["naam"]))
    gehad, paren = set(), []
    for _, klein, a, b in mogelijk:
        if a["id"] in gehad or b["id"] in gehad:
            continue
        gehad |= {a["id"], b["id"]}
        paren.append({"meer": a, "minder": b, "aantal": round(klein)})
    return paren


def op_controlescherm(regels):
    """Vooraf: zet bij de regels van de looplijst (controle_regels) "verwisseld": None of {"met", "meer", "aantal"}. Te veel
    is meer dan er volgens de app ligt; te weinig is onder de marge van wat er verwacht wordt."""
    kandidaten = []
    for r in regels:
        p, v = r["product"], r["verwacht"]
        verschil = 0
        if r["totaal"] > p["voorraad"]:
            verschil = r["totaal"] - (v["verwacht"] if v else p["voorraad"])
        elif v and r["totaal"] < v["laag"]:
            verschil = r["totaal"] - v["verwacht"]
        kandidaten.append({"id": p["id"], "naam": p["naam"], "familie": _familie(p), "verschil": verschil})
    per_id = {}
    for paar in _paren(kandidaten):
        per_id[paar["meer"]["id"]] = {"met": paar["minder"]["naam"], "meer": True, "aantal": paar["aantal"]}
        per_id[paar["minder"]["id"]] = {"met": paar["meer"]["naam"], "meer": False, "aantal": paar["aantal"]}
    for r in regels:
        r["verwisseld"] = per_id.get(r["product"]["id"])
    return regels


def bij_telling(db, telling):
    """Achteraf, voor één telling: de paren (zie _paren), met per product hoeveel er te veel of te weinig is. Wat er gewoon
    verkocht wordt, komt uit de tellingen ervoor (voorraadduur) en de tijd sinds de vorige keer dat het geteld is."""
    moment = datetime.fromisoformat(telling["datum"])
    tempo = verkoop_per_week(db, moment - timedelta(minutes=1))
    kandidaten = []
    for r in db.execute(
        """SELECT tr.product_id AS id, tr.verkocht, tr.correctie, p.naam, p.merk, p.categorie,
                  (SELECT MAX(t2.datum) FROM telling_regels r2 JOIN tellingen t2 ON t2.id = r2.telling_id
                   WHERE r2.product_id = tr.product_id AND t2.datum < ?) AS vorige
           FROM telling_regels tr JOIN producten p ON p.id = tr.product_id WHERE tr.telling_id = ?""",
        (telling["datum"], telling["id"]),
    ).fetchall():
        if r["vorige"] is None or r["id"] not in tempo:
            continue
        verwacht = tempo[r["id"]] * (moment - datetime.fromisoformat(r["vorige"])).total_seconds() / 604800
        # Te veel: er stond meer dan volgens de app kan. Te weinig: ruim meer weg dan gewoon (anderhalf keer, en 3 extra).
        verschil = 0
        if r["correctie"] > 0:
            verschil = r["correctie"]
        elif r["verkocht"] > verwacht * 1.5 + MIN_VERSCHIL:
            verschil = verwacht - r["verkocht"]
        kandidaten.append({"id": r["id"], "naam": r["naam"], "familie": _familie(r), "verschil": verschil})
    return _paren(kandidaten)
