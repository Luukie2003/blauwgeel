"""Omzet per seizoen naast elkaar (1 juli t/m 30 juni): totaal, per maand, per
verkoopdag en tot dezelfde datum als nu -- zodat je dit seizoen eerlijk kunt
vergelijken met de vorige.

Rekent met voorspelling.verdeling(): de omzet van elke periode tussen twee
tellingen is daar over de dagen verdeeld waarop is verkocht, dus het maakt niet
uit op welke dagen er geteld is, en de som klopt altijd met de tellingen."""

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


def _procentueel_verschil(nu, eerder):
    """+12.5 als 'nu' 12,5% hoger is dan 'eerder'; None zonder bruikbare vergelijking."""
    if not eerder or eerder <= 0:
        return None
    return (nu - eerder) / eerder * 100


def bereken_seizoensrapport(db, nu=None):
    """Zie de moduledocstring. Geeft None zolang er geen telling is."""
    nu = nu or datetime.now()
    data = verdeling(db, nu)
    if data is None:
        return None
    vandaag = nu.date()
    huidig = seizoen_van_datum(vandaag)
    dag_in_seizoen_nu = (vandaag - seizoen_start(huidig)).days
    eerste, laatste = data["eerste"].date(), data["laatste"].date()

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

    for dag, omzet in data["omzet"].items():
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

    # Het huidige seizoen altijd tonen, ook als er nog niets verkocht is.
    record(huidig)

    wedstrijd_rijen = db.execute(
        "SELECT datum FROM wedstrijden WHERE thuis = 1 AND afgelast = 0"
    ).fetchall()
    wedstrijd_datums = [r["datum"][:10] for r in wedstrijd_rijen]

    lijst = []
    for seizoen in sorted(seizoenen):
        rec = seizoenen[seizoen]
        start, einde = seizoen_start(seizoen), seizoen_einde(seizoen)
        rec["is_huidig"] = seizoen == huidig
        rec["per_verkoopdag"] = rec["omzet"] / rec["verkoopdagen"] if rec["verkoopdagen"] else 0.0
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
        # Hoe volledig is dit seizoen gedekt door tellingen? Een seizoen waarin
        # de eerste telling pas in oktober viel, kun je niet eerlijk met een
        # volledig seizoen vergelijken.
        rec["gegevens_vanaf"] = eerste if eerste > start else None
        rec["gegevens_tot"] = laatste if laatste < min(einde, vandaag) and not rec["is_huidig"] else None
        rec["volledig"] = rec["gegevens_vanaf"] is None and rec["gegevens_tot"] is None
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

    peildatum = vandaag
    return {
        "seizoenen": lijst,
        "huidig": huidig,
        "peildatum": peildatum,
        "maanden": [(m, MAANDNAMEN[m - 1]) for m in MAANDEN_IN_SEIZOEN],
        "eerste_telling": eerste,
        "laatste_telling": laatste,
    }
