"""Start > Agenda: wat er de komende weken in de kantine gebeurt, per dag op één plek.

Per dag: of de kantine open is (de vaste verkoopdagen en de uitzonderingen), de thuiswedstrijden (uit de gekoppelde
teamagenda's), de evenementen (Prognose > Evenementen), de bardiensten (Kantine-tv > Bardienst), de trainingsavond en
het weer. De verwachte omzet per dag komt uit het voorspelmodel en haalt de pagina apart op (zie routes/activiteiten.py),
want dat rekent op de server soms enkele seconden."""

from datetime import timedelta

import weer
from helpers.omzet import TRAININGSDAG
from voorspelling.basis import dag_is_open, lees_verkoopdagen, lees_wedstrijddagen

DAG_NAMEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MAAND_NAMEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
               "november", "december"]
DAGEN_KEUZES = (14, 21, 28)
STANDAARD_DAGEN = 21


def kies_dagen(waarde):
    try:
        dagen = int(waarde)
    except (TypeError, ValueError):
        return STANDAARD_DAGEN
    return dagen if dagen in DAGEN_KEUZES else STANDAARD_DAGEN


def _per_datum(rijen):
    uitkomst = {}
    for r in rijen:
        uitkomst.setdefault(r["datum"], []).append(r)
    return uitkomst


def bouw_agenda(db, vandaag, dagen=STANDAARD_DAGEN):
    """[{'week', 'van', 'tot', 'dagen': [...]}]: per week de dagen waarop er iets is (de kantine open, een wedstrijd,
    een evenement of een bardienst, of een vaste verkoopdag die dicht is). Een dag zonder iets blijft weg."""
    tot = vandaag + timedelta(days=dagen - 1)
    van_iso, tot_iso = vandaag.isoformat(), tot.isoformat()
    weekdagen, uitzonderingen = lees_verkoopdagen(db)
    wedstrijddagen = lees_wedstrijddagen(db)
    opmerkingen = {
        r["datum"]: r["opmerking"]
        for r in db.execute("SELECT datum, opmerking FROM verkoop_uitzonderingen WHERE datum >= ? AND datum <= ?", (van_iso, tot_iso))
    }
    wedstrijden = _per_datum(db.execute(
        """SELECT datum, tijd, team, omschrijving, afgelast FROM wedstrijden
           WHERE thuis = 1 AND datum >= ? AND datum <= ? ORDER BY datum, COALESCE(tijd, ''), team""",
        (van_iso, tot_iso),
    ).fetchall())
    evenementen = _per_datum(db.execute(
        """SELECT datum, naam, COALESCE(soort, 'druk') AS soort, groep FROM evenementen
           WHERE datum >= ? AND datum <= ? ORDER BY datum, id""",
        (van_iso, tot_iso),
    ).fetchall())
    bardiensten = _per_datum(db.execute(
        "SELECT datum, start_tijd, eind_tijd, namen FROM kiosk_bardiensten WHERE datum >= ? AND datum <= ? ORDER BY datum, start_tijd",
        (van_iso, tot_iso),
    ).fetchall())
    weer_per_dag = {
        w["datum"]: w
        for w in db.execute("SELECT * FROM weer_voorspelling WHERE datum >= ? AND datum <= ?", (van_iso, tot_iso)).fetchall()
    }

    weken = []
    for i in range(dagen):
        dag = vandaag + timedelta(days=i)
        iso = dag.isoformat()
        vast_open = dag.weekday() in weekdagen
        thuis = any(not w["afgelast"] for w in wedstrijden.get(iso, []))
        open_ = dag_is_open(dag, weekdagen, uitzonderingen, wedstrijddagen, thuis) or iso in evenementen
        w = weer_per_dag.get(iso)
        regel = {
            "datum": iso,
            "dag": dag,
            "weekdag": DAG_NAMEN[dag.weekday()],
            "datum_tekst": f"{dag.day} {MAAND_NAMEN[dag.month - 1]}",
            "vandaag": dag == vandaag,
            "morgen": dag == vandaag + timedelta(days=1),
            "open": open_,
            # Afwijkend van de vaste dagen: een gesloten vaste verkoopdag, of een extra open dag.
            "uitzondering": None if iso not in uitzonderingen else ("dicht" if not uitzonderingen[iso] else "open"),
            "uitzondering_tekst": opmerkingen.get(iso),
            "dicht_op_vaste_dag": vast_open and not open_,
            "wedstrijden": wedstrijden.get(iso, []),
            "evenementen": evenementen.get(iso, []),
            "bardiensten": bardiensten.get(iso, []),
            "training": open_ and dag.weekday() == TRAININGSDAG,
            "weer": {"label": weer.weer_label(w["weercode"]), "icoon": weer.weer_icoon(w["weercode"]),
                     "max_temp": w["max_temp"], "neerslag_kans": w["neerslag_kans"]} if w else None,
        }
        if not (open_ or regel["wedstrijden"] or regel["bardiensten"] or regel["dicht_op_vaste_dag"]):
            continue
        jaar, week, _ = dag.isocalendar()
        if not weken or weken[-1]["week"] != week:
            maandag = dag - timedelta(days=dag.weekday())
            weken.append({"week": week, "jaar": jaar, "van": maandag, "tot": maandag + timedelta(days=6), "dagen": []})
        weken[-1]["dagen"].append(regel)
    return weken
