"""Aanmelden voor de Club van 20 via de publieke pagina.

Iemand scant de QR-code, komt op de algemene Club van 20-pagina en kan vanaf
het ingestelde aftelmoment (zie aftelmoment() in club_van_20.py) op de knop
bovenaan om zich aan te melden: betalen via de Mollie-link of contant aan de
bar (dan geeft de aanmelder aan wie er bardienst had), de eigen naam (ter
controle van de betaling) en het gewenste naambordje.

Dat wordt een concept in club_van_20_aanmeldingen. Pas als een beheerder de
betaling heeft gecontroleerd en de aanmelding goedkeurt (routes/
aanmeldingen.py) wordt het een lid + betaalde bijdrage, en komt het bordje op
het kantine scherm. Een aanmelding van een bestaand lid (verlengen) wordt aan
dat lid gekoppeld in plaats van een dubbel lid aan te maken.
"""

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta

import mail
from club_van_20 import AMSTERDAM, DAGNAMEN, MAANDNAMEN, aftelmoment, sla_bijdrage_op
from helpers import heeft_sectie_toegang

# Naambordjes in de administratie zijn nu hooguit 22 tekens ("Van Dort & Bos
# Incasso"), de helft blijft onder de 12. Tot 16 tekens past een bordje op het
# scherm op één regel, daarboven krimpt de naam en wordt 'ie over twee regels
# verdeeld (zie "lang" in zichtbare_leden). 24 is dus ruim genoeg voor elke
# bestaande naam en houdt het leesbaar; zelf aan te passen bij de instellingen.
STANDAARD_MAX_TEKENS = 24
MAX_NAAM_TEKENS = 60
MAX_BARDIENST_TEKENS = 60

AANMELD_BETAALWIJZEN = {
    "mollie": "Online betalen (iDEAL via Mollie)",
    "contant": "Contant aan de bar",
}

# Vloedbeveiliging: op een avond in de kantine scannen veel mensen vanaf
# hetzelfde wifi-netwerk (dus hetzelfde IP-adres), dus per IP ruim. Echt
# misbruik wordt vooral tegengehouden door de handmatige goedkeuring.
MAX_PER_UUR_PER_IP = 30
MAX_OPENSTAAND = 300
DUBBEL_BINNEN_DAGEN = 7


def nu_amsterdam():
    return datetime.now(AMSTERDAM)


def max_tekens(instellingen):
    try:
        return max(5, min(60, int(instellingen["club_van_20_bordje_max_tekens"])))
    except (TypeError, ValueError):
        return STANDAARD_MAX_TEKENS


def aanmelden_status(instellingen, nu=None):
    """Is aanmelden via de site open? {'aan', 'open', 'opent_ms', 'opent_label'}.
    'aan' = de hoofdschakelaar; 'open' = ook het aftelmoment is voorbij (of er
    is er geen ingesteld); 'opent_*' alleen zolang het moment nog komt."""
    nu = nu or nu_amsterdam()
    aan = bool(instellingen["club_van_20_aanmelden_aan"])
    moment = aftelmoment(instellingen)
    wacht = moment is not None and nu < moment
    status = {
        "aan": aan,
        "open": aan and not wacht,
        "opent_ms": int(moment.timestamp() * 1000) if wacht else None,
        "opent_label": None,
    }
    if wacht:
        status["opent_label"] = (
            f"{DAGNAMEN[moment.weekday()]} {moment.day} {MAANDNAMEN[moment.month - 1]}, {moment:%H:%M}"
        )
    return status


# ---------- Invoer schoonmaken en controleren ----------


def schoon_tekst(waarde):
    """Eén regel zonder stuurtekens, met enkele spaties, zonder spaties
    aan de randen."""
    waarde = re.sub(r"\s+", " ", waarde or "")  # tab/enter wordt een spatie
    waarde = "".join(c for c in waarde if unicodedata.category(c) not in ("Cc", "Cf", "Cs"))
    return re.sub(r" +", " ", waarde).strip()


def valideer_aanmelding(form, instellingen, mollie_beschikbaar):
    """(waarden, fouten): de schoongemaakte invoer en per veld een foutmelding
    in gewoon Nederlands. fouten is leeg als alles klopt."""
    maximum = max_tekens(instellingen)
    waarden = {
        "betaalwijze": (form.get("betaalwijze") or "").strip(),
        "naam": schoon_tekst(form.get("naam")),
        "bordje": schoon_tekst(form.get("bordje")),
        "bardienst": schoon_tekst(form.get("bardienst")),
    }
    fouten = {}
    toegestaan = ["contant"] + (["mollie"] if mollie_beschikbaar else [])
    if waarden["betaalwijze"] not in toegestaan:
        fouten["betaalwijze"] = "Kies hoe je betaalt."
        waarden["betaalwijze"] = ""
    if len(waarden["naam"]) < 2:
        fouten["naam"] = "Vul je naam in."
    elif len(waarden["naam"]) > MAX_NAAM_TEKENS:
        fouten["naam"] = f"Je naam mag hooguit {MAX_NAAM_TEKENS} tekens zijn."
    if not waarden["bordje"]:
        fouten["bordje"] = "Vul in wat er op het bordje moet komen."
    elif len(waarden["bordje"]) > maximum:
        fouten["bordje"] = f"Het bordje mag hooguit {maximum} tekens zijn (nu {len(waarden['bordje'])})."
    elif not any(c.isalnum() for c in waarden["bordje"]):
        fouten["bordje"] = "Het bordje moet minstens een letter of cijfer bevatten."
    if waarden["betaalwijze"] == "contant":
        if len(waarden["bardienst"]) < 2:
            fouten["bardienst"] = "Vul in wie er bardienst had toen je betaalde."
        elif len(waarden["bardienst"]) > MAX_BARDIENST_TEKENS:
            fouten["bardienst"] = "Dat is te lang, alleen de naam of namen graag."
    else:
        waarden["bardienst"] = ""
    return waarden, fouten


def ip_hash(ip, geheim):
    return hashlib.sha256(f"{geheim}|{ip}".encode()).hexdigest()[:20]


def te_veel_aanmeldingen(db, ip_h):
    """Vloedbeveiliging: te veel vanaf één IP in het laatste uur, of te veel
    onbehandelde aanmeldingen in totaal."""
    sinds = (nu_amsterdam() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    per_ip = db.execute(
        "SELECT COUNT(*) AS n FROM club_van_20_aanmeldingen WHERE ip_hash = ? AND aangemaakt_op >= ?",
        (ip_h, sinds),
    ).fetchone()["n"]
    openstaand = aantal_openstaand(db)
    return per_ip >= MAX_PER_UUR_PER_IP or openstaand >= MAX_OPENSTAAND


def maak_aanmelding(db, waarden, seizoen, bedrag, ip_h):
    """Slaat een aanmelding op. Dezelfde persoon met hetzelfde bordje die nog
    openstaat (dubbel op 'versturen' geklikt, of de pagina nog eens
    ingevuld) wordt niet nog eens toegevoegd. Geeft (id, is_nieuw)."""
    sinds = (nu_amsterdam() - timedelta(days=DUBBEL_BINNEN_DAGEN)).strftime("%Y-%m-%d %H:%M")
    bestaand = db.execute(
        """SELECT id FROM club_van_20_aanmeldingen
           WHERE status = 'nieuw' AND lower(naam) = lower(?) AND lower(bordje) = lower(?)
             AND aangemaakt_op >= ?""",
        (waarden["naam"], waarden["bordje"], sinds),
    ).fetchone()
    if bestaand:
        return bestaand["id"], False
    nu = nu_amsterdam()
    cursor = db.execute(
        """INSERT INTO club_van_20_aanmeldingen
               (seizoen, naam, bordje, betaalwijze, bardienst, bedrag, status, datum,
                aangemaakt_op, ip_hash)
           VALUES (?, ?, ?, ?, ?, ?, 'nieuw', ?, ?, ?)""",
        (
            seizoen,
            waarden["naam"],
            waarden["bordje"],
            waarden["betaalwijze"],
            waarden["bardienst"] or None,
            bedrag,
            nu.date().isoformat(),
            nu.strftime("%Y-%m-%d %H:%M"),
            ip_h,
        ),
    )
    db.commit()
    return cursor.lastrowid, True


def bardienst_suggesties(db):
    """Namen van de ingeplande bardiensten van de afgelopen week tot en met
    vandaag, als hulp bij het invullen (de aanmelder typt het ook gewoon
    zelf)."""
    nu = nu_amsterdam().date()
    rijen = db.execute(
        "SELECT namen FROM kiosk_bardiensten WHERE datum BETWEEN ? AND ? ORDER BY datum DESC",
        ((nu - timedelta(days=7)).isoformat(), nu.isoformat()),
    ).fetchall()
    gezien = []
    for r in rijen:
        for deel in re.split(r",|&|\ben\b|/", r["namen"] or ""):
            naam = schoon_tekst(deel)
            if naam and naam.lower() not in (g.lower() for g in gezien):
                gezien.append(naam)
    return gezien[:20]


# ---------- Beheer ----------


def aantal_openstaand(db):
    return db.execute(
        "SELECT COUNT(*) AS n FROM club_van_20_aanmeldingen WHERE status = 'nieuw'"
    ).fetchone()["n"]


def splits_naam(naam):
    """"Jan van der Berg" -> ("Jan", "van der Berg"). Eén woord is een
    voornaam."""
    delen = schoon_tekst(naam).split(" ", 1)
    return delen[0], (delen[1] if len(delen) > 1 else "")


def bestaand_lid_voor(db, aanmelding):
    """Het lid dat deze aanmelding waarschijnlijk is (verlengen): zelfde
    naambordje, of dezelfde voor- en achternaam. Anders None."""
    lid = db.execute(
        "SELECT * FROM club_van_20_leden WHERE lower(naam) = lower(?) ORDER BY status = 'inactief', id LIMIT 1",
        (aanmelding["bordje"],),
    ).fetchone()
    if lid is not None:
        return lid
    return db.execute(
        """SELECT * FROM club_van_20_leden
           WHERE lower(trim(coalesce(voornaam, '') || ' ' || coalesce(achternaam, ''))) = lower(?)
           ORDER BY status = 'inactief', id LIMIT 1""",
        (aanmelding["naam"],),
    ).fetchone()


def keur_goed(db, aanmelding, gegevens, gebruiker, standaard_bedrag):
    """Maakt van een openstaande aanmelding een lid (of koppelt 'm aan een
    bestaand lid) met een betaalde bijdrage. 'gegevens': bordje, modus
    ('nieuw'|'bestaand'), lid_id, bordje_aanpassen, voornaam, achternaam,
    team, telefoon, email, bedrag, betaalwijze, betaald_op. Geeft (lid_id,
    foutmelding of None)."""
    bordje = schoon_tekst(gegevens.get("bordje")) or aanmelding["bordje"]
    modus = gegevens.get("modus")
    velden = {k: schoon_tekst(gegevens.get(k)) for k in ("voornaam", "achternaam", "team", "telefoon", "email")}
    if modus == "bestaand":
        lid = db.execute(
            "SELECT * FROM club_van_20_leden WHERE id = ?", (gegevens.get("lid_id") or 0,)
        ).fetchone()
        if lid is None:
            return None, "Dat bestaande lid bestaat niet meer."
        # Alleen lege velden aanvullen, wat al in de administratie staat blijft.
        for veld, waarde in velden.items():
            if waarde and not (lid[veld] or "").strip():
                db.execute(f"UPDATE club_van_20_leden SET {veld} = ? WHERE id = ?", (waarde, lid["id"]))
        if gegevens.get("bordje_aanpassen") and bordje.lower() != lid["naam"].lower():
            if db.execute(
                "SELECT 1 FROM club_van_20_leden WHERE lower(naam) = lower(?) AND id != ?", (bordje, lid["id"])
            ).fetchone():
                return None, f"Er is al een lid met naambordje '{bordje}'."
            db.execute("UPDATE club_van_20_leden SET naam = ? WHERE id = ?", (bordje, lid["id"]))
        if lid["status"] == "inactief":
            db.execute("UPDATE club_van_20_leden SET status = 'actief' WHERE id = ?", (lid["id"],))
        lid_id = lid["id"]
    else:
        if db.execute("SELECT 1 FROM club_van_20_leden WHERE lower(naam) = lower(?)", (bordje,)).fetchone():
            return None, (
                f"Er is al een lid met naambordje '{bordje}'. Kies 'Bestaand lid verlengen' "
                "of pas het bordje aan."
            )
        cursor = db.execute(
            """INSERT INTO club_van_20_leden
                   (naam, voornaam, achternaam, team, telefoon, email, status, startdatum, aangemaakt_op)
               VALUES (?, ?, ?, ?, ?, ?, 'actief', ?, ?)""",
            (
                bordje,
                velden["voornaam"] or None,
                velden["achternaam"] or None,
                velden["team"] or None,
                velden["telefoon"] or None,
                velden["email"] or None,
                aanmelding["datum"],
                nu_amsterdam().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        lid_id = cursor.lastrowid
    betaalwijze = gegevens.get("betaalwijze") or aanmelding["betaalwijze"]
    notitie = "Aangemeld via de website"
    if aanmelding["betaalwijze"] == "contant" and aanmelding["bardienst"]:
        notitie += f"; contant aan de bar, bardienst: {aanmelding['bardienst']}"
    sla_bijdrage_op(
        db,
        lid_id,
        aanmelding["seizoen"],
        "betaald",
        bedrag=gegevens.get("bedrag") or aanmelding["bedrag"],
        betaald_door=aanmelding["naam"],
        betaalwijze=betaalwijze,
        notitie=notitie,
        standaard_bedrag=standaard_bedrag,
        gebruiker=gebruiker,
        betaald_op=gegevens.get("betaald_op") or aanmelding["datum"],
    )
    db.execute(
        """UPDATE club_van_20_aanmeldingen
           SET status = 'goedgekeurd', lid_id = ?, behandeld_door = ?, behandeld_op = ?
           WHERE id = ?""",
        (lid_id, gebruiker, nu_amsterdam().strftime("%Y-%m-%d %H:%M"), aanmelding["id"]),
    )
    db.commit()
    return lid_id, None


def wijs_af(db, aanmelding_id, reden, gebruiker):
    db.execute(
        """UPDATE club_van_20_aanmeldingen
           SET status = 'afgewezen', opmerking = ?, behandeld_door = ?, behandeld_op = ?
           WHERE id = ? AND status = 'nieuw'""",
        (schoon_tekst(reden) or None, gebruiker, nu_amsterdam().strftime("%Y-%m-%d %H:%M"), aanmelding_id),
    )
    db.commit()


# ---------- Melding aan de beheerders ----------


def melding_ontvangers(db):
    """E-mailadressen die een melding krijgen bij een nieuwe aanmelding:
    accounts die dat bij Mijn voorkeuren hebben aangevinkt (en bij de Club
    van 20 mogen), anders -- net als bij een ingeboekte levering -- het
    algemene meldingsadres uit de instellingen."""
    ontvangers = [
        r["email"]
        for r in db.execute(
            """SELECT email, rol, secties FROM gebruikers
               WHERE mail_club_aanmelding = 1 AND actief = 1
                 AND email IS NOT NULL AND email != ''"""
        ).fetchall()
        if heeft_sectie_toegang(r["rol"], r["secties"], "club_van_20")
    ]
    if not ontvangers:
        instelling = db.execute("SELECT notificatie_email FROM instellingen WHERE id = 1").fetchone()
        if instelling and instelling["notificatie_email"]:
            ontvangers = [instelling["notificatie_email"]]
    return ontvangers


def stuur_melding_nieuwe_aanmelding(db, waarden, link):
    """Mailt de beheerders dat er een aanmelding wacht. Mag een aanmelding
    nooit laten mislukken: wie zich aanmeldt heeft daar niets aan te merken
    als de mail niet aankomt, de aanmelding staat dan gewoon in de lijst."""
    try:
        ontvangers = melding_ontvangers(db)
        if not ontvangers:
            return
        wachtend = aantal_openstaand(db)
        betaling = AANMELD_BETAALWIJZEN.get(waarden["betaalwijze"], waarden["betaalwijze"])
        regels = [
            "Er is een nieuwe aanmelding voor de Club van 20.",
            "",
            f"Bordje: {waarden['bordje']}",
            f"Naam: {waarden['naam']}",
            f"Betaling: {betaling}",
        ]
        if waarden.get("bardienst"):
            regels.append(f"Bardienst: {waarden['bardienst']}")
        regels += [
            "",
            "Controleer de betaling en keur de aanmelding goed (of wijs af):",
            link,
            "",
            f"Er {'wacht' if wachtend == 1 else 'wachten'} nu {wachtend} "
            f"{'aanmelding' if wachtend == 1 else 'aanmeldingen'} op goedkeuring.",
        ]
        onderwerp = f"Nieuwe Club van 20-aanmelding: {waarden['bordje']}"
        for ontvanger in ontvangers:
            mail.stuur_mail(onderwerp, "\n".join(regels), naar=ontvanger)
    except Exception as fout:  # noqa: BLE001 -- zie docstring
        print(f"[aanmelding] Melding versturen mislukt: {fout}")
