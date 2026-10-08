"""Seizoenen van de Club van 20: 1 juli t/m 30 juni, opgeslagen als "2026-2027"."""

import re
from datetime import date

from helpers import vandaag_amsterdam


SEIZOEN_STARTMAAND = 7


SEIZOEN_PATROON = re.compile(r"^\s*(\d{4})\s*[-/]\s*(\d{2}|\d{4})\s*$")


# ---------- Seizoenen ----------


def seizoen_van_datum(datum=None):
    """"2026-2027" voor elke datum van 1 juli 2026 t/m 30 juni 2027. datum
    mag een date, een ISO-tekst (YYYY-MM-DD...) of None (= vandaag) zijn."""
    if datum is None:
        datum = vandaag_amsterdam()
    elif isinstance(datum, str):
        datum = date.fromisoformat(datum[:10])
    begin = datum.year if datum.month >= SEIZOEN_STARTMAAND else datum.year - 1
    return f"{begin}-{begin + 1}"


def huidig_seizoen():
    return seizoen_van_datum(None)


def verschuif_seizoen(seizoen, stappen):
    """verschuif_seizoen("2026-2027", -1) == "2025-2026"."""
    begin = int(seizoen[:4]) + stappen
    return f"{begin}-{begin + 1}"


def normaliseer_seizoen(tekst):
    """Accepteert "2023-2024", "2023/2024" en "2023-24"; geeft "2023-2024"
    terug, of None als het geen (aaneensluitend) seizoen is."""
    m = SEIZOEN_PATROON.match(tekst or "")
    if not m:
        return None
    begin = int(m.group(1))
    eind = m.group(2)
    eind = int(eind) if len(eind) == 4 else int(str(begin)[:2] + eind)
    if eind != begin + 1:
        return None
    return f"{begin}-{eind}"


def seizoen_kort(seizoen):
    """"2026-2027" -> "26/27", voor smalle tabelkoppen."""
    return f"{seizoen[2:4]}/{seizoen[7:9]}"


def alle_seizoenen(db):
    """Alle seizoenen waarin iets is vastgelegd, plus het huidige -- oudste
    eerst, zodat de overzichtstabel dezelfde volgorde heeft als de oude
    spreadsheet (2023-2024, 2024-2025, ...)."""
    seizoenen = {
        r["seizoen"]
        for r in db.execute("SELECT DISTINCT seizoen FROM club_van_20_bijdragen").fetchall()
    }
    seizoenen.add(huidig_seizoen())
    return sorted(seizoenen)
