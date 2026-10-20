"""Timers op de tv-schermen: "Gehaktballen klaar over 12:30" linksonder op elk scherm (de prijzenlijst, de dia's, het
wisselscherm en elke gekoppelde tv).

Starten, verlengen en weghalen gaat op de site (Timer, ook in de tablet-app) en op de handterminal. Een timer telt af;
is hij klaar, dan staat er "Klaar!" tot iemand hem weghaalt, of tot een kwartier later. De schermen krijgen de timers
mee met de vraag die ze toch al elke 5 seconden stellen (/kiosk/welkom, zie templates/_kiosk_timer.html), als het
aantal seconden dat nog over is: een tv waarvan de klok niet goed staat, telt zo toch goed af.

De laatst gebruikte duur per naam is de standaard voor de volgende keer: zet je de gehaktballen één keer op 12
minuten, dan staat de knop daarna op 12 minuten."""

from datetime import datetime, timedelta

STANDAARD_NAAM = "Gehaktballen"
STANDAARD_MINUTEN = 15
KLAAR_ZICHTBAAR_MINUTEN = 15
MAX_MINUTEN = 240
MAX_VOORSTELLEN = 4
FORMAAT = "%Y-%m-%d %H:%M:%S"


def _tekst(moment):
    return moment.strftime(FORMAAT)


def _moment(tekst):
    return datetime.strptime(tekst, FORMAAT)


def schoon_naam(naam):
    naam = " ".join(str(naam or "").split())[:30]
    return naam[:1].upper() + naam[1:]


def schoon_minuten(minuten):
    """Een geheel aantal minuten van 1 t/m 240, of None."""
    try:
        minuten = int(str(minuten).strip())
    except (TypeError, ValueError):
        return None
    return minuten if 1 <= minuten <= MAX_MINUTEN else None


def start(db, naam, minuten, door=None, nu=None):
    """Start een timer. Geeft (id, None) of (None, foutmelding)."""
    nu = nu or datetime.now()
    naam = schoon_naam(naam)
    minuten = schoon_minuten(minuten)
    if not naam:
        return None, "Waar is de timer voor? Bijvoorbeeld 'Gehaktballen'."
    if minuten is None:
        return None, f"Kies een tijd van 1 tot {MAX_MINUTEN} minuten."
    timer_id = db.execute(
        "INSERT INTO kiosk_timers (naam, minuten, gestart_op, klaar_om, gestart_door) VALUES (?, ?, ?, ?, ?)",
        (naam, minuten, _tekst(nu), _tekst(nu + timedelta(minutes=minuten)), door),
    ).lastrowid
    db.commit()
    return timer_id, None


def stop(db, timer_id, nu=None):
    """Haalt de timer weg (van de tv's). Geeft de naam, of None als hij er al niet meer stond."""
    nu = nu or datetime.now()
    rij = db.execute("SELECT naam FROM kiosk_timers WHERE id = ? AND gestopt_op IS NULL", (timer_id,)).fetchone()
    if rij is None:
        return None
    db.execute("UPDATE kiosk_timers SET gestopt_op = ? WHERE id = ?", (_tekst(nu), timer_id))
    db.commit()
    return rij["naam"]


def verleng(db, timer_id, minuten=5, nu=None):
    """Er komen minuten bij; een timer die al klaar was, telt weer af vanaf nu. Geeft de naam, of None."""
    nu = nu or datetime.now()
    minuten = schoon_minuten(minuten) or 5
    rij = db.execute("SELECT naam, klaar_om FROM kiosk_timers WHERE id = ? AND gestopt_op IS NULL", (timer_id,)).fetchone()
    if rij is None:
        return None
    klaar_om = max(_moment(rij["klaar_om"]), nu) + timedelta(minutes=minuten)
    db.execute("UPDATE kiosk_timers SET klaar_om = ? WHERE id = ?", (_tekst(klaar_om), timer_id))
    db.commit()
    return rij["naam"]


def actieve(db, nu=None):
    """De timers die op de tv's staan: nog bezig, of hooguit een kwartier klaar en niet weggehaald."""
    nu = nu or datetime.now()
    rijen = db.execute(
        "SELECT * FROM kiosk_timers WHERE gestopt_op IS NULL AND klaar_om >= ? ORDER BY klaar_om, id",
        (_tekst(nu - timedelta(minutes=KLAAR_ZICHTBAAR_MINUTEN)),),
    ).fetchall()
    uit = []
    for r in rijen:
        resterend = int((_moment(r["klaar_om"]) - nu).total_seconds())
        uit.append({
            "id": r["id"],
            "naam": r["naam"],
            "minuten": r["minuten"],
            "resterend": resterend,
            "totaal": int((_moment(r["klaar_om"]) - _moment(r["gestart_op"])).total_seconds()),
            "klaar": resterend <= 0,
            "klaar_om": r["klaar_om"][11:16],
            "gestart_door": r["gestart_door"],
        })
    return uit


def voor_scherm(db, nu=None):
    """Wat een tv-scherm nodig heeft: naam, hoeveel seconden er nog over zijn (negatief: al zo lang klaar) en hoe lang
    hij in totaal duurt (voor het ringetje dat leegloopt)."""
    return [{"id": t["id"], "naam": t["naam"], "resterend": t["resterend"], "totaal": t["totaal"]} for t in actieve(db, nu)]


def voorstellen(db):
    """Snelknoppen: de laatst gebruikte timers met hun laatste duur, met de gehaktballen als die er nog niet bij staan."""
    rijen = db.execute(
        """SELECT naam, minuten FROM kiosk_timers t
           WHERE id = (SELECT MAX(id) FROM kiosk_timers WHERE naam = t.naam COLLATE NOCASE)
           ORDER BY id DESC LIMIT ?""",
        (MAX_VOORSTELLEN,),
    ).fetchall()
    uit = [{"naam": r["naam"], "minuten": r["minuten"]} for r in rijen]
    if not any(v["naam"].lower() == STANDAARD_NAAM.lower() for v in uit):
        uit = ([{"naam": STANDAARD_NAAM, "minuten": STANDAARD_MINUTEN}] + uit)[:MAX_VOORSTELLEN]
    return uit
