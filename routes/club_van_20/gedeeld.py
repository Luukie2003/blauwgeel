"""Kleine hulpfuncties die de Club van 20-pagina's delen."""

from datetime import date, datetime

from flask import request

from club_van_20 import AFTEL_FORMAAT, huidig_seizoen, normaliseer_seizoen


LID_VELDEN = ("voornaam", "achternaam", "team", "telefoon", "email", "notitie")


def _instellingen(db):
    return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()


def _bedrag(waarde):
    try:
        return float((waarde or "").replace(",", ".")) if (waarde or "").strip() else None
    except ValueError:
        return None


def _getal(veld, standaard):
    try:
        return int(request.form.get(veld) or standaard)
    except ValueError:
        return standaard


def _veilige_link(waarde):
    """Alleen http(s)-links: de betaallink komt als knop op de publieke
    pagina, dus geen javascript:- of andere vreemde schema's."""
    waarde = (waarde or "").strip()
    return waarde if waarde.lower().startswith(("https://", "http://")) else None


def _aftelmoment(waarde):
    """datetime-local uit het formulier ("2026-10-05T00:00"), of None als
    het leeg of onleesbaar is."""
    try:
        return datetime.strptime((waarde or "").strip(), AFTEL_FORMAAT).strftime(AFTEL_FORMAAT)
    except ValueError:
        return None


def _datum(waarde):
    """date-veld uit het formulier ("2026-10-18"), of None als het leeg of
    onleesbaar is."""
    try:
        return date.fromisoformat((waarde or "").strip()).isoformat()
    except ValueError:
        return None


def _gekozen_seizoen(waarde):
    return normaliseer_seizoen(waarde or "") or huidig_seizoen()


def _teams(db):
    return [
        r["team"]
        for r in db.execute(
            """SELECT DISTINCT team FROM club_van_20_leden
               WHERE team IS NOT NULL AND team != '' ORDER BY team COLLATE NOCASE"""
        ).fetchall()
    ]


def _lid_of_404(db, lid_id):
    return db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
