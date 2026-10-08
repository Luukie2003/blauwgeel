"""Omzet per bardienst en per persoon.

Gebaseerd op de bardienstplanning van de Kantine-tv (kiosk_bardiensten) en de omzet
per dag uit voorspelling.verdeling(). Omzet per dag is een schatting (de tellingen
liggen niet op dagen vast), dus dit zegt iets over een heel seizoen of een paar maanden,
nooit over één avond.

Een dienst op een wedstrijddag levert vanzelf meer op dan een dienst op een gewone
dinsdag. Daarom staat er ook een gecorrigeerde omzet: de omzet gedeeld door hoeveel
drukker het model die dag verwachtte (wedstrijd, training, weer), dus wat de dienst op een
gewone dag zou hebben opgeleverd."""

import re
from datetime import date, datetime, timedelta

from voorspelling import verdeling

_NAAM_SCHEIDING = re.compile(r"\s*(?:&|,|/|\+|;|\ben\b|\bplus\b)\s*", re.IGNORECASE)
MAX_RECENTE_DIENSTEN = 15


def splits_namen(tekst):
    """"Luuk & Femke" -> ["Luuk", "Femke"]; lege stukjes vallen weg."""
    return [n.strip() for n in _NAAM_SCHEIDING.split(tekst or "") if n.strip()]


def _uren(start_tijd, eind_tijd):
    """Duur van een dienst in uren; een dienst over middernacht (22:00-01:00) telt door."""
    s = datetime.strptime(start_tijd, "%H:%M")
    e = datetime.strptime(eind_tijd, "%H:%M")
    if e <= s:
        e += timedelta(days=1)
    return (e - s).total_seconds() / 3600


def bereken_bardienstrapport(db, vanaf, tot, nu=None):
    """Zie de moduledocstring. vanaf/tot zijn dates (inclusief). Geeft None zolang er geen
    tellingen zijn."""
    data = verdeling(db, nu)
    if data is None:
        return None
    eerste, laatste = data["eerste"].date(), data["laatste"].date()
    diensten = db.execute(
        "SELECT * FROM kiosk_bardiensten WHERE datum BETWEEN ? AND ? ORDER BY datum, start_tijd",
        (vanaf.isoformat(), tot.isoformat()),
    ).fetchall()

    per_dag = {}
    for d in diensten:
        per_dag.setdefault(date.fromisoformat(d["datum"]), []).append(d)

    personen = {}
    detail = []
    zonder_gegevens = 0
    for dag, lijst in per_dag.items():
        if dag < eerste or dag > laatste or dag not in data["omzet"]:
            # Geen tellingen die deze dag dekken, of er is die dag niets verkocht (dicht).
            zonder_gegevens += len(lijst)
            continue
        dag_omzet = data["omzet"][dag]
        drukte = data["drukte"].get(dag) or 1.0
        totale_uren = sum(_uren(d["start_tijd"], d["eind_tijd"]) for d in lijst) or 1.0
        for d in lijst:
            uren = _uren(d["start_tijd"], d["eind_tijd"])
            # Meerdere diensten op 1 dag: de omzet van die dag naar duur verdelen.
            omzet = dag_omzet * uren / totale_uren
            namen = splits_namen(d["namen"])
            detail.append(
                {
                    "datum": dag,
                    "tijd": f"{d['start_tijd']}-{d['eind_tijd']}",
                    "namen": d["namen"],
                    "uren": uren,
                    "omzet": omzet,
                    "gecorrigeerd": omzet / drukte,
                    "drukte": drukte,
                }
            )
            for naam in namen:
                p = personen.setdefault(
                    naam.casefold(),
                    {"naam": naam, "diensten": 0, "uren": 0.0, "omzet": 0.0, "gecorrigeerd": 0.0},
                )
                p["diensten"] += 1
                p["uren"] += uren
                p["omzet"] += omzet
                p["gecorrigeerd"] += omzet / drukte

    lijst = []
    for p in personen.values():
        p["per_dienst"] = p["omzet"] / p["diensten"]
        p["per_uur"] = p["omzet"] / p["uren"] if p["uren"] else 0.0
        p["gecorrigeerd_per_dienst"] = p["gecorrigeerd"] / p["diensten"]
        lijst.append(p)
    lijst.sort(key=lambda p: p["per_dienst"], reverse=True)

    detail.sort(key=lambda r: (r["datum"], r["tijd"]), reverse=True)
    gemiddelde = sum(r["omzet"] for r in detail) / len(detail) if detail else 0.0
    return {
        "personen": lijst,
        "recente_diensten": detail[:MAX_RECENTE_DIENSTEN],
        "aantal_diensten": len(detail),
        "zonder_gegevens": zonder_gegevens,
        "gemiddelde_per_dienst": gemiddelde,
        "vanaf": vanaf,
        "tot": tot,
    }
