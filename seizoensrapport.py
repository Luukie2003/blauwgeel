"""Omzet per seizoen naast elkaar (1 juli t/m 30 juni): totaal, per maand, per
verkoopdag en tot dezelfde datum als nu -- zodat je dit seizoen eerlijk kunt
vergelijken met de vorige.

Rekent met voorspelling.verdeling(): de omzet van elke periode tussen twee
tellingen is daar over de dagen verdeeld waarop is verkocht, dus het maakt niet
uit op welke dagen er geteld is, en de som klopt altijd met de tellingen.

Voor de tijd vóór de eerste telling kan de omzet per maand met de hand worden ingevuld
(tabel omzet_historie). Zulke maandtotalen worden alleen gebruikt voor maanden waarvoor de
tellingen niets (of minder) opleveren; tellingen gaan altijd voor."""

import calendar
from datetime import date, datetime

from club_van_20 import MAANDNAMEN, seizoen_kort, seizoen_van_datum, verschuif_seizoen
from voorspelling import verdeling

# Een seizoen loopt van juli t/m juni.
MAANDEN_IN_SEIZOEN = [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6]
AANTAL_TOP_PRODUCTEN = 5


def seizoen_start(seizoen):
    return date(int(seizoen[:4]), 7, 1)


def seizoen_einde(seizoen):
    return date(int(seizoen[:4]) + 1, 6, 30)


def maand_grenzen(seizoen, maand):
    """(eerste dag, laatste dag) van die maand binnen dit seizoen."""
    jaar = int(seizoen[:4]) + (0 if maand >= 7 else 1)
    return date(jaar, maand, 1), date(jaar, maand, calendar.monthrange(jaar, maand)[1])


def _procentueel_verschil(nu, eerder):
    """+12.5 als 'nu' 12,5% hoger is dan 'eerder'; None zonder bruikbare vergelijking."""
    if not eerder or eerder <= 0:
        return None
    return (nu - eerder) / eerder * 100


def lees_historie(db):
    """{(seizoen, maand): omzet} uit de met de hand ingevulde maandtotalen."""
    try:
        rijen = db.execute("SELECT seizoen, maand, omzet FROM omzet_historie").fetchall()
    except Exception:  # tabel bestaat nog niet (oude database)
        return {}
    return {(r["seizoen"], r["maand"]): r["omzet"] for r in rijen}


def bereken_seizoensrapport(db, nu=None):
    """Zie de moduledocstring. Geeft None zolang er geen telling en geen ingevulde omzet is."""
    nu = nu or datetime.now()
    data = verdeling(db, nu)
    historie = lees_historie(db)
    if data is None and not historie:
        return None
    vandaag = nu.date()
    huidig = seizoen_van_datum(vandaag)
    dag_in_seizoen_nu = (vandaag - seizoen_start(huidig)).days
    eerste = data["eerste"].date() if data else None
    laatste = data["laatste"].date() if data else None

    producten = {
        r["id"]: (r["naam"], r["categorie"])
        for r in db.execute("SELECT id, naam, categorie FROM producten").fetchall()
    }

    seizoenen = {}

    def record(seizoen):
        return seizoenen.setdefault(
            seizoen,
            {
                "seizoen": seizoen,
                "kort": seizoen_kort(seizoen),
                "omzet": 0.0,
                "verkoopdagen": 0,
                "tot_nu": 0.0,
                "maanden": {m: 0.0 for m in MAANDEN_IN_SEIZOEN},
                "producten": {},
            },
        )

    for dag, omzet in (data["omzet"].items() if data else ()):
        seizoen = seizoen_van_datum(dag)
        rec = record(seizoen)
        rec["omzet"] += omzet
        if omzet > 0:
            rec["verkoopdagen"] += 1
        rec["maanden"][dag.month] += omzet
        if (dag - seizoen_start(seizoen)).days <= dag_in_seizoen_nu:
            rec["tot_nu"] += omzet
        for pid, (aantal, euro) in data["producten"].get(dag, {}).items():
            regel = rec["producten"].setdefault(pid, [0.0, 0.0])
            regel[0] += aantal
            regel[1] += euro

    # Het huidige seizoen altijd tonen, ook als er nog niets verkocht is, en seizoenen waarvan
    # alleen maandtotalen zijn ingevuld.
    record(huidig)
    for seizoen, _maand in historie:
        record(seizoen)

    # De met de hand ingevulde maanden: alleen waar de tellingen niets of minder opleveren.
    for seizoen, rec in seizoenen.items():
        rec["maanden_tellingen"] = dict(rec["maanden"])
        rec["handmatige_maanden"] = set()
        for maand in MAANDEN_IN_SEIZOEN:
            ingevuld = historie.get((seizoen, maand))
            if not ingevuld or ingevuld <= 0:
                continue
            maand_begin, maand_eind = maand_grenzen(seizoen, maand)
            uit_tellingen = rec["maanden"][maand]
            # Alleen maanden die niet (helemaal) door tellingen gedekt zijn: voor de eerste telling,
            # of waar de tellingen niets opleverden. Zo komt omzet nooit dubbel in de totalen.
            voor_de_tellingen = eerste is None or maand_eind < eerste or (maand_begin <= eerste <= maand_eind)
            if uit_tellingen <= 0 or (voor_de_tellingen and ingevuld > uit_tellingen):
                rec["omzet"] += ingevuld - uit_tellingen
                rec["maanden"][maand] = ingevuld
                rec["handmatige_maanden"].add(maand)
                # "Tot dezelfde datum": een ingevulde maand telt helemaal mee als hij voor het
                # punt in het seizoen van nu ligt, voor het deel van de maand als hij erdoorheen loopt.
                begin_offset = (maand_begin - seizoen_start(seizoen)).days
                eind_offset = (maand_eind - seizoen_start(seizoen)).days
                if eind_offset <= dag_in_seizoen_nu:
                    aandeel = 1.0
                elif begin_offset > dag_in_seizoen_nu:
                    aandeel = 0.0
                else:
                    aandeel = (dag_in_seizoen_nu - begin_offset + 1) / (eind_offset - begin_offset + 1)
                rec["tot_nu"] += (ingevuld - uit_tellingen) * aandeel

    wedstrijd_rijen = db.execute(
        "SELECT datum FROM wedstrijden WHERE thuis = 1 AND afgelast = 0"
    ).fetchall()
    wedstrijd_datums = [r["datum"][:10] for r in wedstrijd_rijen]

    lijst = []
    for seizoen in sorted(seizoenen):
        rec = seizoenen[seizoen]
        start, einde = seizoen_start(seizoen), seizoen_einde(seizoen)
        rec["is_huidig"] = seizoen == huidig
        rec["per_verkoopdag"] = _omzet_uit_tellingen(rec) / rec["verkoopdagen"] if rec["verkoopdagen"] else 0.0
        tot = min(einde, vandaag)
        rec["thuiswedstrijden"] = sum(
            1 for d in wedstrijd_datums if start.isoformat() <= d <= tot.isoformat()
        )
        top = sorted(rec["producten"].items(), key=lambda kv: kv[1][1], reverse=True)
        rec["top_producten"] = [
            {"naam": producten.get(pid, ("(verwijderd product)", ""))[0], "aantal": round(aantal), "omzet": euro}
            for pid, (aantal, euro) in top[:AANTAL_TOP_PRODUCTEN]
            if euro > 0
        ]
        # Hoe volledig is dit seizoen? Een seizoen waarin de eerste telling pas in oktober viel, kun
        # je niet eerlijk met een volledig seizoen vergelijken -- tenzij de maanden ervoor met de
        # hand zijn ingevuld.
        rec["gegevens_vanaf"] = None
        if eerste is not None and start < eerste <= einde:
            ontbrekend = [
                m for m in MAANDEN_IN_SEIZOEN
                if maand_grenzen(seizoen, m)[0] < eerste and (seizoen, m) not in historie
            ]
            if ontbrekend:
                rec["gegevens_vanaf"] = eerste
        rec["gegevens_tot"] = (
            laatste if laatste is not None and laatste < min(einde, vandaag) and not rec["is_huidig"] else None
        )
        rec["volledig"] = rec["gegevens_vanaf"] is None and rec["gegevens_tot"] is None
        rec["alleen_ingevuld"] = bool(rec["handmatige_maanden"]) and rec["verkoopdagen"] == 0
        del rec["producten"]
        lijst.append(rec)

    for i, rec in enumerate(lijst):
        vorige = lijst[i - 1] if i else None
        # Een lopend seizoen is nog niet af: dat vergelijk je met het vorige tot
        # dezelfde datum (zie tot_nu_verschil_met_huidig), niet met het hele seizoen.
        sluit_aan = vorige and vorige["seizoen"] == verschuif_seizoen(rec["seizoen"], -1)
        rec["verschil_vorig_seizoen"] = (
            _procentueel_verschil(rec["omzet"], vorige["omzet"]) if sluit_aan and not rec["is_huidig"] else None
        )

    huidig_rec = next(r for r in lijst if r["is_huidig"])
    for rec in lijst:
        rec["tot_nu_verschil_met_huidig"] = (
            None if rec["is_huidig"] else _procentueel_verschil(huidig_rec["tot_nu"], rec["tot_nu"])
        )

    return {
        "seizoenen": lijst,
        "huidig": huidig,
        "peildatum": vandaag,
        "maanden": [(m, MAANDNAMEN[m - 1]) for m in MAANDEN_IN_SEIZOEN],
        "eerste_telling": eerste,
        "laatste_telling": laatste,
        "heeft_ingevulde_maanden": any(r["handmatige_maanden"] for r in lijst),
    }


def _omzet_uit_tellingen(rec):
    """De omzet van de maanden die uit tellingen komen (voor 'gemiddeld per verkoopdag': ingevulde
    maanden hebben geen verkoopdagen, die zouden het gemiddelde opblazen)."""
    return sum(bedrag for maand, bedrag in rec["maanden"].items() if maand not in rec["handmatige_maanden"])
