"""Systeemstatus: wanneer elke geplande taak op PythonAnywhere voor het laatst heeft gedraaid en gelukt is. Zo valt een
taak op die stilletjes mislukt (een agenda-link die niet meer werkt, een weerbericht dat niet binnenkomt) of die helemaal
niet meer draait. Alleen voor de systeembeheerder, het account dat eigenaar is (zie mail.systeembeheerder_adres): op
Beheer > Systeemstatus, bij 'Wat moet er nu?' en met één mail per probleem.

Elke taak meldt zich aan het eind met registreer(). Daarbij wordt ook gekeken of een ándere taak te lang niet gelukt is:
zolang er nog één taak draait (de bereikbaarheidscontrole draait elk uur), valt een stilgevallen taak dus op.

Gebruikt alleen de standaardbibliotheek: de taken draaien ook buiten de virtualenv."""

import tijdzone  # noqa: F401  (de tijden in Nederlandse tijd, net als in de app)

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import mail

BASE_DIR = Path(__file__).parent
DB_PAD = BASE_DIR / "voorraad.db"
SITE_URL = "https://www.kantineblauwgeel.nl"
TIJD = "%Y-%m-%d %H:%M"  # zoals now_str() in de app

# max_uren: hoe lang een taak niet gelukt mag zijn voordat het een probleem is. Voor een dagelijkse taak ruim twee
# dagen: één gemiste of mislukte keer (een storing bij Sportlink of Open-Meteo) is nog geen reden tot alarm, twee wel.
# eigen_waarschuwing: de back-up heeft al een eigen melding op het overzicht en eigen mails (zie backup.py); hier staat
# hij alleen voor het overzicht.
TAKEN = [
    {"sleutel": "backup", "naam": "Back-up", "hoe_vaak": "dagelijks", "max_uren": 50, "eigen_waarschuwing": True,
     "wat": "Een back-up van de database, gecontroleerd en als kopie gemaild; daarna opruimen en de opslag meten."},
    {"sleutel": "agenda", "naam": "Teamagenda's", "hoe_vaak": "dagelijks", "max_uren": 50,
     "wat": "De wedstrijden uit de agenda-links van Sportlink, voor de agenda, het programma op de tv en de prognose."},
    {"sleutel": "weer", "naam": "Weerbericht", "hoe_vaak": "dagelijks", "max_uren": 50,
     "wat": "De verwachting van Open-Meteo, voor de prognose."},
    {"sleutel": "weekoverzicht", "naam": "Weekoverzicht per mail", "hoe_vaak": "dagelijks", "max_uren": 50,
     "wat": "Op maandag de omzet van de week ervoor naar wie dat bij Mijn voorkeuren heeft aangevinkt."},
    {"sleutel": "bereikbaarheid", "naam": "Bereikbaarheid", "hoe_vaak": "elk uur", "max_uren": 3,
     "wat": "Kijkt of de site reageert en mailt bij een storing."},
]


def _tijd(nu=None):
    return (nu or datetime.now()).strftime(TIJD)


def _lees(tijd):
    return datetime.strptime(tijd, TIJD) if tijd else None


def leesbaar(tijd):
    """'2026-11-08 04:00' -> '8-11 04:00', voor in een mail."""
    t = _lees(tijd)
    return f"{t.day}-{t.month} {t:%H:%M}" if t else "nooit"


def zorg_voor_tabel(conn, nu=None):
    """De tabel, met een rij per taak. bekend_sinds is wanneer we de taak zijn gaan volgen: een taak die daarna nooit
    draait, valt zo ook op. Doet niets als alles er al is (draait bij het starten van de app en bij elke melding)."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS taak_status (
               sleutel TEXT PRIMARY KEY,
               bekend_sinds TEXT NOT NULL,
               laatst_gedraaid TEXT,
               laatst_gelukt TEXT,
               laatste_ok INTEGER,
               melding TEXT,
               gemeld_op TEXT)"""
    )
    tijd = _tijd(nu)
    conn.executemany(
        "INSERT OR IGNORE INTO taak_status (sleutel, bekend_sinds) VALUES (?, ?)", [(t["sleutel"], tijd) for t in TAKEN]
    )


def overzicht(conn, nu=None):
    """Per taak (in de volgorde van TAKEN) de gegevens uit TAKEN, plus:
    stand: 'ok', 'mislukt' (de laatste keer mislukt, maar nog binnen de marge), 'probleem' (te lang niet gelukt, of
    nooit gedraaid sinds we hem volgen) of 'wacht' (nog niet gedraaid, maar dat kan nog);
    tekst: de stand in woorden; laatst_gedraaid, laatst_gelukt, melding (wat de taak de laatste keer meldde), gemeld_op."""
    nu = nu or datetime.now()
    rijen = {
        rij[0]: rij
        for rij in conn.execute(
            "SELECT sleutel, bekend_sinds, laatst_gedraaid, laatst_gelukt, laatste_ok, melding, gemeld_op FROM taak_status"
        )
    }
    uitkomst = []
    for taak in TAKEN:
        rij = rijen.get(taak["sleutel"])
        bekend_sinds, gedraaid, gelukt, laatste_ok, melding, gemeld_op = tuple(rij)[1:] if rij else (None,) * 6
        marge = timedelta(hours=taak["max_uren"])
        if gelukt and nu - _lees(gelukt) <= marge:
            stand, tekst = ("ok", "In orde") if laatste_ok else ("mislukt", "Laatste keer mislukt")
        elif not (gelukt or bekend_sinds) or nu - _lees(gelukt or bekend_sinds) <= marge:
            stand, tekst = ("mislukt", "Laatste keer mislukt") if gedraaid else ("wacht", "Nog niet gedraaid")
        elif gelukt:
            stand, tekst = "probleem", f"Niet gelukt sinds {leesbaar(gelukt)}"
        else:
            stand, tekst = "probleem", "Nog nooit gelukt" if gedraaid else "Draait niet"
        uitkomst.append({**taak, "stand": stand, "tekst": tekst, "laatst_gedraaid": gedraaid, "laatst_gelukt": gelukt,
                         "melding": melding, "gemeld_op": gemeld_op})
    return uitkomst


def problemen(conn, nu=None):
    """De taken die nu een probleem zijn en geen eigen waarschuwing hebben: voor 'Wat moet er nu?' en de mail."""
    return [t for t in overzicht(conn, nu) if t["stand"] == "probleem" and not t.get("eigen_waarschuwing")]


def registreer(sleutel, ok, melding="", db_pad=None, nu=None):
    """Legt vast dat taak 'sleutel' net heeft gedraaid (ok: gelukt) en wat hij meldt, en mailt daarna de
    systeembeheerder over taken die nu een probleem zijn (zie meld_problemen). Gooit nooit een uitzondering en maakt
    nooit een lege database aan: de taak zelf is belangrijker dan zijn melding."""
    try:
        conn = sqlite3.connect(f"{Path(db_pad or DB_PAD).resolve().as_uri()}?mode=rw", uri=True)
        try:
            zorg_voor_tabel(conn, nu)
            tijd = _tijd(nu)
            conn.execute(
                "UPDATE taak_status SET laatst_gedraaid = ?, laatste_ok = ?, melding = ? WHERE sleutel = ?",
                (tijd, 1 if ok else 0, (melding or "")[:500], sleutel),
            )
            if ok:
                # Weer gelukt: een volgend probleem met deze taak krijgt weer een mail.
                conn.execute(
                    "UPDATE taak_status SET laatst_gelukt = ?, gemeld_op = NULL WHERE sleutel = ?", (tijd, sleutel)
                )
            conn.commit()
            meld_problemen(conn, nu)
        finally:
            conn.close()
    except Exception as fout:
        print(f"[taakstatus] Vastleggen van '{sleutel}' mislukt: {fout}")


def meld_problemen(conn, nu=None):
    """Eén mail aan de systeembeheerder over de taken die nu een probleem zijn en waarover nog niet is gemaild. Daarna
    niet opnieuw, tot de taak weer gelukt is. Lukt het mailen niet, dan de volgende keer opnieuw. Geeft de gemelde
    taken terug."""
    nieuw = [t for t in problemen(conn, nu) if not t["gemeld_op"]]
    if not nieuw:
        return []
    if len(nieuw) == 1:
        onderwerp = f"Kantine Beheer: {nieuw[0]['naam']} {nieuw[0]['tekst'].lower()}"
        regels = ["Een geplande taak van Kantine Beheer werkt niet goed:", ""]
    else:
        onderwerp = f"Kantine Beheer: {len(nieuw)} geplande taken met een probleem"
        regels = ["Deze geplande taken van Kantine Beheer werken niet goed:", ""]
    for t in nieuw:
        regels.append(f"- {t['naam']} ({t['hoe_vaak']}): {t['tekst'].lower()}.")
        if t["melding"]:
            regels.append(f"  De laatste keer ({leesbaar(t['laatst_gedraaid'])}): {t['melding']}")
    regels += [
        "",
        f"Bekijk de systeemstatus: {SITE_URL}/beheer/systeemstatus",
        "",
        "Je krijgt deze mail één keer per probleem; zodra de taak weer lukt, staat hij weer op groen. "
        "Deze mail gaat alleen naar de systeembeheerder.",
    ]
    if not mail.stuur_mail(onderwerp, "\n".join(regels), naar=mail.systeembeheerder_adres(conn)):
        return []
    tijd = _tijd(nu)
    conn.executemany("UPDATE taak_status SET gemeld_op = ? WHERE sleutel = ?", [(tijd, t["sleutel"]) for t in nieuw])
    conn.commit()
    return nieuw
