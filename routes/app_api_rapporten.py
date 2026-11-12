"""De rapporten van de site in de app (2.11.0, eerst voor de tablet): dezelfde berekeningen als de pagina's bij Rapporten,
als één vorm die het rapportscherm van de app (RapportActivity) altijd zo laat zien:

    {"titel", "sub", "keuzes": [{"sleutel", "label", "actief"}], "delen": [deel]}

met als deel {"soort": "cijfers", "kop", "cijfers": [{"waarde", "label", "sub"}]}, {"soort": "lijst", "kop", "leeg",
"regels": [{"titel", "detail", "rechts", "kleur"}]} of {"soort": "tekst", "tekst"}. Met ?keuze=… kies je de periode
(de "keuzes"). Elk rapport heeft zijn eigen adres, met dezelfde rechten als zijn pagina op de site (rechten.py): verkoop,
week, seizoenen en seizoen in cijfers voor iedereen; marge, derving, niet-lopers en de bardiensten alleen voor beheerders.
Zware berekeningen gebeuren pas als je het rapport opent, net als op de site."""

from datetime import date, datetime, timedelta

from flask import jsonify, request

import seizoen_in_cijfers
from bardienstrapport import bereken_bardienstrapport
from club_van_20 import seizoen_kort, seizoen_van_datum
from database import get_db
from derving import bereken_derving
from helpers import bereken_omzet_trend_periode, bereken_week_overzicht
from helpers.tijd import vandaag_amsterdam
from marge import WEKEN_KEUZES as MARGE_WEKEN, bereken_marge, kies_weken as kies_marge_weken
from niet_lopers import WEKEN_KEUZES as NIET_LOPERS_WEKEN, bereken_niet_lopers, kies_weken as kies_niet_lopers_weken
from routes.bardienstrapport import _beschikbare_seizoenen
from seizoensrapport import bereken_seizoensrapport, seizoen_einde, seizoen_start

VERKOOP_DAGEN = (7, 30, 90, 365)
MAX_REGELS = 25


def _euro(bedrag, decimalen=0):
    if bedrag is None:
        return "–"
    tekst = f"{bedrag:,.{decimalen}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"€ {tekst}"


def _getal(n):
    return f"{n:,.0f}".replace(",", ".") if isinstance(n, (int, float)) else str(n)


def _aantal(n, enkel, meer):
    """'1 thuiswedstrijd', '3 thuiswedstrijden'."""
    return f"{_getal(n)} {enkel if n == 1 else meer}"


def _procent(p):
    return "–" if p is None else f"{p:.0f}%"


def _datum(d):
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return d
    return d.strftime("%d-%m-%Y") if isinstance(d, (date, datetime)) else ""


def _cijfers(kop, *cijfers):
    return {"soort": "cijfers", "kop": kop, "cijfers": [{"waarde": w, "label": label, "sub": sub} for w, label, sub in cijfers]}


def _lijst(kop, regels, leeg):
    return {"soort": "lijst", "kop": kop, "leeg": leeg, "regels": regels[:MAX_REGELS]}


def _regel(titel, detail=None, rechts=None, kleur=None):
    return {"titel": titel, "detail": detail, "rechts": rechts, "kleur": kleur}


def _leeg(titel, sub, tekst, keuzes=()):
    """Een rapport zonder gegevens (bijvoorbeeld nog geen tellingen): alleen de uitleg."""
    return {"titel": titel, "sub": sub, "keuzes": list(keuzes), "delen": [{"soort": "tekst", "tekst": tekst}]}


def _keuzes(opties, gekozen):
    return [{"sleutel": str(sleutel), "label": label, "actief": str(sleutel) == str(gekozen)} for sleutel, label in opties]


def _top_verkopers(rijen):
    return [_regel(r["product_naam"], " · ".join(x for x in (r["categorie"], f"{_getal(r['verkocht'])} {r['eenheid']}") if x),
                   _euro(r["omzet"])) for r in rijen]


def _verkoop():
    dagen = request.args.get("keuze", type=int)
    dagen = dagen if dagen in VERKOOP_DAGEN else 30
    tot = datetime.now()
    van = tot - timedelta(days=dagen)
    trend = bereken_omzet_trend_periode(get_db(), van.strftime("%Y-%m-%d"), tot.strftime("%Y-%m-%d"))
    perioden = [
        _regel(f"Telling tot {b['datum_kort']}",
               " · ".join(x for x in (_aantal(b["aantal_dagen"], "dag", "dagen"),
                                      _aantal(b["thuiswedstrijden"], "thuiswedstrijd", "thuiswedstrijden") if b["thuiswedstrijden"] else None,
                                      _aantal(b["trainingsavonden"], "trainingsavond", "trainingsavonden") if b.get("trainingsavonden") else None)
                          if x),
               _euro(b["omzet"]))
        for b in reversed(trend["balken"])
    ]
    return {
        "titel": "Verkoop",
        "sub": f"{_datum(van)} t/m {_datum(tot)}, uit de tellingen",
        "keuzes": _keuzes([(7, "7 dagen"), (30, "30 dagen"), (90, "90 dagen"), (365, "Jaar")], dagen),
        "delen": [
            _cijfers("In deze periode", (_euro(trend["totale_omzet"]), "omzet", None), (_getal(len(trend["balken"])), "tellingen", None)),
            _lijst("Best verkocht", _top_verkopers(trend["top_verkopers"]), "In deze periode is er niets verkocht."),
            _lijst("Per telling", perioden, "Geen tellingen in deze periode."),
        ],
    }


def _week():
    o = bereken_week_overzicht(get_db())
    verschil = o.get("verschil_percentage")
    onder = [_regel(p["naam"], p["categorie"], f"{_getal(p['voorraad'])} / min {_getal(p['min_voorraad'])} {p['eenheid']}", "rood")
             for p in o.get("onder_minimum", [])]
    return {
        "titel": "Weekoverzicht",
        "sub": f"{_datum(o['week_van'])} t/m {_datum(o['week_tot'])}",
        "keuzes": [],
        "delen": [
            _cijfers("Deze week", (_euro(o["totale_omzet"]), "omzet", None), (_euro(o["vorige_omzet"]), "de week ervoor", None),
                     ((f"{verschil:+.0f}%" if verschil is not None else "–"), "verschil", None)),
            _lijst("Best verkocht", _top_verkopers(o.get("top_verkopers", [])), "Deze week is er niets verkocht."),
            _lijst("Onder het minimum", onder, "Alles zit boven het minimum."),
        ],
    }


def _seizoenen():
    rapport = bereken_seizoensrapport(get_db())
    if not rapport:
        return _leeg("Omzet per seizoen", "", "Nog geen omzet: die komt uit de tellingen.")
    seizoenen = rapport["seizoenen"]
    huidig = next((s for s in seizoenen if s["is_huidig"]), seizoenen[0] if seizoenen else None)
    delen = []
    if huidig:
        delen.append(_cijfers(f"Seizoen {huidig['seizoen']}", (_euro(huidig["omzet"]), "omzet tot nu", None),
                              (_euro(huidig["per_verkoopdag"]), "per verkoopdag", None),
                              (_getal(huidig["verkoopdagen"]), "verkoopdagen", None),
                              (_getal(huidig["thuiswedstrijden"]), "thuiswedstrijden", None)))
        delen.append(_lijst("Toppers dit seizoen", [_regel(p["naam"], f"{_getal(p['aantal'])}×", _euro(p.get("omzet")))
                                                     for p in huidig.get("top_producten", [])], "Nog niets verkocht dit seizoen."))
    delen.append(_lijst("Per seizoen", [
        _regel(f"Seizoen {s['seizoen']}" + (" (nu)" if s["is_huidig"] else ""),
               " · ".join(x for x in (_aantal(s["verkoopdagen"], "verkoopdag", "verkoopdagen"), f"{_euro(s['per_verkoopdag'])} per dag") if x),
               _euro(s["omzet"]))
        for s in seizoenen
    ], "Nog geen seizoenen."))
    return {"titel": "Omzet per seizoen", "sub": f"Tot en met {_datum(rapport['peildatum'])}", "keuzes": [], "delen": delen}


def _seizoen_in_cijfers():
    c = seizoen_in_cijfers.ververs(get_db())
    if not c:
        return _leeg("Seizoen in cijfers", "", "Nog geen cijfers: die komen uit de tellingen van dit seizoen.")
    delen = [_cijfers(f"Seizoen {c.get('kort') or seizoen_kort(seizoen_van_datum(vandaag_amsterdam()))}",
                      *[(x["tekst"], x["label"], x.get("sub")) for x in c.get("cijfers", [])])]
    if c.get("drukste_dag"):
        delen.append({"soort": "tekst", "tekst": f"De drukste dag: {c['drukste_dag']['tekst']}."})
    delen.append(_lijst("Toppers van de bar", [_regel(t["naam"], None, f"{t['tekst']} {t['eenheid']}") for t in c.get("top_bar", [])],
                        "Nog niets geteld."))
    delen.append(_lijst("Toppers van de keuken", [_regel(t["naam"], None, f"{t['tekst']} {t['eenheid']}") for t in c.get("top_keuken", [])],
                        "Nog niets geteld."))
    return {"titel": "Seizoen in cijfers", "sub": "Een schatting uit de tellingen, zonder bedragen", "keuzes": [], "delen": delen}


def _marge():
    weken = kies_marge_weken(request.args.get("keuze"))
    r = bereken_marge(get_db(), weken, vandaag_amsterdam())
    t = r["totaal"]

    def product(p):
        return _regel(p["naam"], f"{p['categorie']} · {_getal(p['aantal'])} {p['eenheid']} · {_euro(p['omzet'])}",
                      _procent(p.get("marge_pct")), "rood" if (p.get("marge_pct") or 0) < 30 else None)

    return {
        "titel": "Marge",
        "sub": f"Sinds {_datum(r['vanaf'])}",
        "keuzes": _keuzes([(w, f"{w} weken") for w in MARGE_WEKEN], weken),
        "delen": [
            _cijfers("In deze periode", (_euro(t["omzet"]), "omzet", None), (_euro(t["winst"]), "winst", None),
                     (_procent(t.get("marge_pct")), "marge", "op wat een inkoopprijs heeft")),
            _lijst("Per categorie", [_regel(c["naam"], f"omzet {_euro(c['omzet'])} · winst {_euro(c['winst'])}", _procent(c.get("marge_pct")))
                                     for c in r["categorieen"]], "Nog geen verkoop."),
            _lijst("Laagste marge", [product(p) for p in r["laagste"]], "Geen producten met een lage marge."),
            _lijst("Hoogste marge", [product(p) for p in r["beste"]], "Nog geen verkoop met een inkoopprijs."),
            _lijst("Zonder inkoopprijs", [_regel(p["naam"], p["categorie"], _euro(p["omzet"])) for p in r["zonder_inkoop"] if p["omzet"]],
                   "Alles wat verkocht is, heeft een inkoopprijs."),
        ],
    }


def _derving():
    weken = kies_marge_weken(request.args.get("keuze"))
    r = bereken_derving(get_db(), weken, vandaag_amsterdam())
    return {
        "titel": "Derving",
        "sub": f"Sinds {_datum(r['vanaf'])}: wat zonder te verkopen uit de voorraad verdween",
        "keuzes": _keuzes([(w, f"{w} weken") for w in MARGE_WEKEN], weken),
        "delen": [
            _cijfers("In deze periode", (_euro(r["totaal"]["waarde"], 2), "waarde", None), (_getal(r["totaal"]["boekingen"]), "boekingen", None)),
            _lijst("Per reden", [_regel(x["naam"], f"{_aantal(x['boekingen'], 'boeking', 'boekingen')} · {_getal(x['stuks'])} stuks", _euro(x["waarde"], 2))
                                 for x in r["per_reden"]], "Niets weggegooid of verloren."),
            _lijst("Per product", [_regel(x["naam"], f"{_aantal(x['boekingen'], 'boeking', 'boekingen')} · {_getal(x['stuks'])} {x['eenheid']}", _euro(x["waarde"], 2))
                                   for x in r["per_product"]], "Niets weggegooid of verloren."),
            _lijst("Laatste boekingen", [_regel(m.get("product_naam") or m.get("naam") or "", " · ".join(x for x in (
                _datum(m.get("datum")), m.get("reden_naam"), m.get("opmerking")) if x), f"{_getal(m['aantal'])} {m.get('eenheid') or ''}".strip())
                for m in r["recent"]], "Geen boekingen."),
        ],
    }


def _niet_lopers():
    weken = kies_niet_lopers_weken(request.args.get("keuze"))
    u = bereken_niet_lopers(get_db(), weken, vandaag_amsterdam())

    def regel(r):
        laatst = r.get("laatst_verkocht")
        return _regel(r["naam"], " · ".join(x for x in (r["categorie"], f"laatst verkocht {_datum(laatst)}" if laatst else "nooit verkocht") if x),
                      f"{_getal(r['voorraad'])} {r['eenheid']}")

    return {
        "titel": "Niet-lopers",
        "sub": f"Wat er sinds {_datum(u['vanaf'])} niet verkocht is, terwijl het op voorraad ligt",
        "keuzes": _keuzes([(w, f"{w} weken") for w in NIET_LOPERS_WEKEN], weken),
        "delen": [
            _cijfers("Op de plank", (_getal(len(u["niet_lopers"])), "niet-lopers", None), (_euro(u["waarde"]), "voorraadwaarde", "tegen inkoop")),
            _lijst("Niet verkocht", [regel(r) for r in u["niet_lopers"]], "Alles wat op voorraad ligt, is verkocht."),
            _lijst("Niet geteld", [regel(r) for r in u["niet_geteld"]], "Alles is geteld."),
        ],
    }


def _bardiensten():
    db = get_db()
    vandaag = vandaag_amsterdam()
    huidig = seizoen_van_datum(vandaag)
    seizoenen = _beschikbare_seizoenen(db, huidig)
    keuze = request.args.get("keuze", huidig)
    if keuze == "90":
        vanaf, tot, titel = vandaag - timedelta(days=89), vandaag, "De laatste 90 dagen"
    else:
        keuze = keuze if keuze in seizoenen else huidig
        vanaf, tot, titel = seizoen_start(keuze), min(seizoen_einde(keuze), vandaag), f"Seizoen {keuze}"
    r = bereken_bardienstrapport(db, vanaf, tot)
    keuzes = _keuzes([("90", "90 dagen")] + [(s, s) for s in seizoenen], keuze)
    if not r:
        return _leeg("Omzet per bardienst", titel, "Nog geen bardiensten met omzet in deze periode.", keuzes)
    return {
        "titel": "Omzet per bardienst",
        "sub": titel,
        "keuzes": keuzes,
        "delen": [
            _cijfers(titel, (_getal(r["aantal_diensten"]), "diensten", None), (_euro(r["gemiddelde_per_dienst"]), "per dienst", "gemiddeld")),
            _lijst("Per persoon", [_regel(p["naam"], f"{_aantal(p['diensten'], 'dienst', 'diensten')} · {_euro(p.get('per_uur'))} per uur",
                                          _euro(p.get("per_dienst"))) for p in r["personen"]], "Nog geen diensten met omzet."),
            _lijst("Laatste diensten", [_regel(", ".join(d["namen"]) if isinstance(d.get("namen"), list) else (d.get("namen") or ""),
                                               " · ".join(x for x in (_datum(d.get("datum")), d.get("tijd")) if x), _euro(d.get("omzet")))
                                        for d in r["recente_diensten"]], "Nog geen diensten."),
        ],
    }


def register_routes(app):

    @app.route("/api/app/rapporten/verkoop")
    def api_app_rapport_verkoop():
        return jsonify(_verkoop())

    @app.route("/api/app/rapporten/week")
    def api_app_rapport_week():
        return jsonify(_week())

    @app.route("/api/app/rapporten/seizoenen")
    def api_app_rapport_seizoenen():
        return jsonify(_seizoenen())

    @app.route("/api/app/rapporten/seizoen-in-cijfers")
    def api_app_rapport_seizoen_in_cijfers():
        return jsonify(_seizoen_in_cijfers())

    @app.route("/api/app/rapporten/marge")
    def api_app_rapport_marge():
        return jsonify(_marge())

    @app.route("/api/app/rapporten/derving")
    def api_app_rapport_derving():
        return jsonify(_derving())

    @app.route("/api/app/rapporten/niet-lopers")
    def api_app_rapport_niet_lopers():
        return jsonify(_niet_lopers())

    @app.route("/api/app/rapporten/bardiensten")
    def api_app_rapport_bardiensten():
        return jsonify(_bardiensten())
