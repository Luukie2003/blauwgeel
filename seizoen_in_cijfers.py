"""Seizoen in cijfers: het seizoen tot nu toe (vanaf 1 juli) in een paar leuke getallen, voor een pagina bij Rapporten
en twee dia's op de Kantine-tv. Bewust zonder bedragen: de tv hangt in de kantine.

De verkoop aan de bar komt uit voorspelling.verdeling(), net als in het seizoensrapport: de verkoop tussen twee
tellingen, verdeeld over de verkoopdagen. Binnen een periode is dat een schatting (de drukste dag dus ook), maar de
totalen kloppen met de tellingen. Een fust telt als het aantal glazen dat erin zit (glazen_per_fust). De keuken telt
apart (keuken_tellingen).

Het rekenen gebeurt niet bij het tonen: ververs() bewaart de uitkomst in seizoen_cijfers en rekent alleen opnieuw na
een nieuwe telling of op een nieuwe dag. Het voorverwarmen na een paginabezoek (voorspelling_opwarmen) en de pagina
zelf roepen ververs() aan; de tv leest alleen wat er bewaard is (lees)."""

import json
import re
from datetime import datetime

from club_van_20 import seizoen_kort, seizoen_van_datum
from helpers.tijd import datum_lang
from seizoensrapport import seizoen_start
from voorspelling import verdeling

AANTAL_TOP_BAR = 5
AANTAL_TOP_KEUKEN = 3
MAX_TEGELS_TV = 6

# Wat er op de tv kan staan (2.14.0): elk getal, de drukste dag en de dia met de toppers. Bij Kantine-tv > Diashow zet
# je ze apart aan of uit; bewaard is wat UIT staat (kiosk_scherm_instellingen.seizoen_verborgen), zodat iets nieuws
# vanzelf meedoet.
ONDERDELEN = [
    ("bar", "Keer iets aan de bar"),
    ("getapt", "Glazen getapt"),
    ("keuken", "Kroketten (of iets uit de keuken)"),
    ("thuis", "Thuiswedstrijden"),
    ("tellingen", "Tellingen"),
    ("frituurvet", "Keer vers frituurvet"),
    ("stemmen", "Stemmen uitgebracht"),
    ("drukste", "De drukste dag"),
    ("toppers", "De dia met de toppers van de bar en de keuken"),
]
_SLEUTELS = {sleutel for sleutel, _ in ONDERDELEN}


def _getal(n):
    """1234 -> '1.234'."""
    return f"{n:,}".replace(",", ".")


def _zonder_fust(naam):
    """'Fust Hertog Jan' -> 'Hertog Jan': op de tv gaat het om het bier, niet om het vat."""
    kaal = re.sub(r"^\s*fust\s+", "", naam or "", flags=re.IGNORECASE).strip()
    return kaal or naam


def _tegel(sleutel, getal, enkelvoud, meervoud=None, sub=None):
    return {"sleutel": sleutel, "getal": getal, "tekst": _getal(getal),
            "label": enkelvoud if getal == 1 else (meervoud or enkelvoud), "sub": sub}


def _sleutel_van(tegel):
    """De sleutel van een tegel; een uitkomst die nog van voor 2.14.0 bewaard is, heeft er geen: dan uit het label."""
    if tegel.get("sleutel"):
        return tegel["sleutel"]
    label = tegel.get("label", "")
    for stuk, sleutel in (("bar", "bar"), ("getapt", "getapt"), ("kroket", "keuken"), ("keuken", "keuken"),
                          ("thuiswedstrijd", "thuis"), ("telling", "tellingen"), ("frituurvet", "frituurvet"),
                          ("stem", "stemmen")):
        if stuk in label:
            return sleutel
    return None


def verborgen_uit(tekst):
    """'drukste,stemmen' (zoals bewaard) -> {'drukste', 'stemmen'}; onbekende stukken vallen weg."""
    return {s.strip() for s in str(tekst or "").split(",") if s.strip() in _SLEUTELS}


def verborgen_tekst(getoond):
    """De aangevinkte onderdelen uit het formulier -> wat er uit staat, zoals het bewaard wordt (of None)."""
    uit = [sleutel for sleutel, _ in ONDERDELEN if sleutel not in set(getoond)]
    return ",".join(uit) or None


def bereken(db, nu=None):
    """De getallen van het lopende seizoen tot en met vandaag: {'seizoen', 'kort', 'van', 'tot', 'cijfers' (tegels:
    getal, tekst, label, sub), 'drukste_dag', 'top_bar', 'top_keuken'}. None zolang er dit seizoen nog niets is."""
    nu = nu or datetime.now()
    vandaag = nu.date()
    seizoen = seizoen_van_datum(vandaag)
    begin = seizoen_start(seizoen)
    van, tot = begin.isoformat(), vandaag.isoformat()

    # De bar: wat er dit seizoen per product verkocht is, en de omzet per dag (alleen om de drukste dag te vinden).
    per_product, per_dag = {}, {}
    data = verdeling(db, nu)
    if data:
        for dag, regels in data["producten"].items():
            if begin <= dag <= vandaag:
                for pid, (aantal, _euro) in regels.items():
                    per_product[pid] = per_product.get(pid, 0.0) + aantal
        per_dag = {dag: omzet for dag, omzet in data["omzet"].items() if begin <= dag <= vandaag and omzet > 0}

    producten = {r["id"]: r for r in db.execute("SELECT id, naam, eenheid, glazen_per_fust FROM producten")}
    bar, fusten, glazen = [], 0.0, 0.0
    for pid, aantal in per_product.items():
        p = producten.get(pid)
        if p is None or aantal <= 0:
            continue
        if (p["glazen_per_fust"] or 0) > 0:
            fusten += aantal
            glazen += aantal * p["glazen_per_fust"]
            bar.append({"naam": _zonder_fust(p["naam"]), "aantal": round(aantal * p["glazen_per_fust"]), "eenheid": "glazen"})
        else:
            bar.append({"naam": p["naam"], "aantal": round(aantal), "eenheid": p["eenheid"] or "stuks"})
    bar = sorted((b for b in bar if b["aantal"] > 0), key=lambda b: (-b["aantal"], b["naam"]))

    keuken = [
        {"naam": r["naam"], "aantal": r["aantal"], "eenheid": r["eenheid"] or "stuks"}
        for r in db.execute(
            """SELECT p.naam, p.eenheid, SUM(r.verkocht) AS aantal
               FROM keuken_telling_regels r
               JOIN keuken_tellingen t ON t.id = r.telling_id
               JOIN producten p ON p.id = r.product_id
               WHERE t.begintelling = 0 AND substr(t.datum, 1, 10) BETWEEN ? AND ?
               GROUP BY r.product_id HAVING SUM(r.verkocht) > 0
               ORDER BY aantal DESC, p.naam""",
            (van, tot),
        )
    ]
    kroketten = sum(k["aantal"] for k in keuken if "kroket" in k["naam"].lower())

    def aantal(sql):
        return db.execute(sql, (van, tot)).fetchone()[0] or 0

    thuis = aantal("""SELECT COUNT(*) FROM wedstrijden
                      WHERE thuis = 1 AND afgelast = 0 AND substr(datum, 1, 10) BETWEEN ? AND ?""")
    tellingen = aantal("SELECT COUNT(*) FROM tellingen WHERE substr(datum, 1, 10) BETWEEN ? AND ?") + aantal(
        "SELECT COUNT(*) FROM keuken_tellingen WHERE substr(datum, 1, 10) BETWEEN ? AND ?"
    )
    tellers = db.execute(
        """SELECT COUNT(DISTINCT naam) FROM (
               SELECT naam, datum FROM tellingen UNION ALL SELECT naam, datum FROM keuken_tellingen)
           WHERE COALESCE(naam, '') != '' AND substr(datum, 1, 10) BETWEEN ? AND ?""",
        (van, tot),
    ).fetchone()[0]
    frituurvet = aantal("SELECT COUNT(*) FROM frituurvet_vervangingen WHERE substr(datum, 1, 10) BETWEEN ? AND ?")
    stemmen = aantal("SELECT COUNT(*) FROM stemmen WHERE afgekeurd = 0 AND substr(datum, 1, 10) BETWEEN ? AND ?")

    cijfers = []
    totaal_bar = sum(b["aantal"] for b in bar)
    if totaal_bar:
        cijfers.append(_tegel("bar", totaal_bar, "keer iets aan de bar", sub="glazen, flesjes en snacks samen"))
    if round(glazen):
        fusten_rond = round(fusten)
        sub = f"uit {_getal(fusten_rond)} {'fust' if fusten_rond == 1 else 'fusten'}" if fusten_rond else None
        cijfers.append(_tegel("getapt", round(glazen), "glas getapt", "glazen getapt", sub=sub))
    if kroketten:
        cijfers.append(_tegel("keuken", kroketten, "kroket", "kroketten", sub="uit de keuken"))
    elif keuken:
        cijfers.append(_tegel("keuken", sum(k["aantal"] for k in keuken), "keer iets uit de keuken",
                              sub=f"het meest: {keuken[0]['naam']}"))
    if thuis:
        cijfers.append(_tegel("thuis", thuis, "thuiswedstrijd", "thuiswedstrijden"))
    if tellingen:
        sub = f"door {tellers} {'vrijwilliger' if tellers == 1 else 'vrijwilligers'}" if tellers else None
        cijfers.append(_tegel("tellingen", tellingen, "telling", "tellingen", sub=sub))
    if frituurvet:
        cijfers.append(_tegel("frituurvet", frituurvet, "keer vers frituurvet"))
    if stemmen:
        cijfers.append(_tegel("stemmen", stemmen, "stem uitgebracht", "stemmen uitgebracht"))

    drukste = None
    if per_dag:
        dag = max(per_dag, key=lambda d: (per_dag[d], d))
        wedstrijden = [
            r["omschrijving"]
            for r in db.execute(
                """SELECT omschrijving FROM wedstrijden
                   WHERE thuis = 1 AND afgelast = 0 AND substr(datum, 1, 10) = ? ORDER BY tijd, omschrijving""",
                (dag.isoformat(),),
            )
        ]
        drukste = {"datum": dag.isoformat(), "tekst": datum_lang(dag), "wedstrijden": wedstrijden}

    if not (cijfers or drukste or bar or keuken):
        return None
    for regel in bar + keuken:
        regel["tekst"] = _getal(regel["aantal"])
    return {
        "seizoen": seizoen,
        "kort": seizoen_kort(seizoen),
        "van": van,
        "tot": tot,
        "cijfers": cijfers,
        "drukste_dag": drukste,
        "top_bar": bar[:AANTAL_TOP_BAR],
        "top_keuken": keuken[:AANTAL_TOP_KEUKEN],
    }


def _vingerafdruk(db, nu):
    """Verandert na elke nieuwe telling (bar of keuken) en elke dag: dan rekenen we opnieuw."""
    bar = db.execute("SELECT MAX(id) FROM tellingen").fetchone()[0]
    keuken = db.execute("SELECT MAX(id) FROM keuken_tellingen").fetchone()[0]
    return f"{nu.date().isoformat()}|{bar}|{keuken}"


def ververs(db, nu=None):
    """Rekent opnieuw als er sinds de vorige keer een telling bij is gekomen of het een nieuwe dag is, en bewaart de
    uitkomst. Geeft de bewaarde uitkomst terug (zie lees)."""
    nu = nu or datetime.now()
    seizoen = seizoen_van_datum(nu.date())
    vingerafdruk = _vingerafdruk(db, nu)
    rij = db.execute("SELECT vingerafdruk FROM seizoen_cijfers WHERE seizoen = ?", (seizoen,)).fetchone()
    if rij is None or rij["vingerafdruk"] != vingerafdruk:
        db.execute(
            """INSERT INTO seizoen_cijfers (seizoen, vingerafdruk, berekend_op, gegevens) VALUES (?, ?, ?, ?)
               ON CONFLICT(seizoen) DO UPDATE SET vingerafdruk = excluded.vingerafdruk,
                   berekend_op = excluded.berekend_op, gegevens = excluded.gegevens""",
            (seizoen, vingerafdruk, nu.strftime("%Y-%m-%d %H:%M"), json.dumps(bereken(db, nu))),
        )
        db.commit()
    return lees(db, nu)


def lees(db, nu=None):
    """De bewaarde uitkomst van het lopende seizoen, zonder te rekenen (voor de tv), met 'berekend_op' erbij. None als
    er (nog) niets bewaard is of er dit seizoen nog niets te tonen is."""
    seizoen = seizoen_van_datum((nu or datetime.now()).date())
    rij = db.execute("SELECT berekend_op, gegevens FROM seizoen_cijfers WHERE seizoen = ?", (seizoen,)).fetchone()
    gegevens = json.loads(rij["gegevens"]) if rij else None
    if not gegevens:
        return None
    return {**gegevens, "berekend_op": rij["berekend_op"]}


def tv_slides(cijfers, duur, verborgen=()):
    """De dia's voor de Kantine-tv: de getallen met de drukste dag, en de toppers van de bar en de keuken. verborgen: de
    onderdelen die uit staan (zie ONDERDELEN)."""
    verborgen = set(verborgen)
    tegels = [t for t in cijfers["cijfers"] if _sleutel_van(t) not in verborgen]
    drukste = None if "drukste" in verborgen else cijfers["drukste_dag"]
    slides = []
    if tegels or drukste:
        slides.append({"type": "seizoen_cijfers", "duur": duur, "kort": cijfers["kort"],
                       "cijfers": tegels[:MAX_TEGELS_TV], "drukste_dag": drukste})
    if cijfers["top_bar"] and "toppers" not in verborgen:
        slides.append({"type": "seizoen_top", "duur": duur, "kort": cijfers["kort"],
                       "top_bar": cijfers["top_bar"], "top_keuken": cijfers["top_keuken"]})
    return slides
