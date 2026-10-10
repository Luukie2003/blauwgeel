"""Importeren (Excel/CSV/plakken) en exporteren van de Club van 20-spreadsheet."""

import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from helpers import now_str, vandaag_amsterdam
from club_van_20.administratie import BIJDRAGE_STATUS_LABELS, sla_bijdrage_op
from club_van_20.seizoenen import SEIZOEN_STARTMAAND, normaliseer_seizoen


# ---------- Importeren uit de spreadsheet ----------

_KOLOM_NAMEN = {
    "voornaam": "voornaam",
    "achternaam": "achternaam",
    "team": "team",
    "naambordje": "naam",
    "naam": "naam",
    "telefoon": "telefoon",
    "tel": "telefoon",
    "telefoonnummer": "telefoon",
    "e-mail": "email",
    "email": "email",
    "betaald door": "betaald_door",
    "notitie": "notitie",
    "opmerking": "notitie",
}


_STATUS_KOLOM = re.compile(r"^\s*status\s+(.+)$", re.IGNORECASE)


_STATUS_UIT_TEKST = {
    "niet gevraagd": "niet_gevraagd",
    "gevraagd": "gevraagd",
    "toegezegd": "toegezegd",
    "betaald": "betaald",
    "stopt": "afgezegd",
    "afgezegd": "afgezegd",
    "gestopt": "afgezegd",
}


def _schoon(waarde):
    waarde = (waarde or "").strip()
    return "" if waarde in ("?", "-", "–") else waarde


def _bedrag(waarde):
    """'20', '€20,00', '1.840' -> float; None bij leeg/'-'/onleesbaar."""
    tekst = (waarde or "").replace("€", "").replace(" ", "").strip()
    if not tekst or tekst in ("-", "–", "?"):
        return None
    if "," in tekst and "." in tekst:
        tekst = tekst.replace(".", "").replace(",", ".")
    elif "," in tekst:
        tekst = tekst.replace(",", ".")
    try:
        return float(tekst)
    except ValueError:
        return None


def _lees_csv(tekst):
    regels = [r for r in tekst.splitlines() if r.strip()]
    if not regels:
        return []
    proef = "\n".join(regels[:10])
    try:
        dialect = csv.Sniffer().sniff(proef, delimiters=",;\t")
        scheiding = dialect.delimiter
    except csv.Error:
        scheiding = max(",;\t", key=proef.count)
    return list(csv.reader(io.StringIO(tekst.lstrip("﻿")), delimiter=scheiding))


MAX_XLSX_XML_BYTES = 30 * 1024 * 1024


_XLSX_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _xlsx_xml(z, pad):
    """Een XML-onderdeel uit het xlsx-zipbestand, met een grens aan de
    uitgepakte grootte (zipbom) en zonder DTD/entiteiten (een bewust
    kwaadaardig bestand kan met geneste entiteiten de server vastzetten)."""
    if z.getinfo(pad).file_size > MAX_XLSX_XML_BYTES:
        raise ValueError("Het Excel-bestand is te groot.")
    data = z.read(pad)
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("Dit Excel-bestand bevat niet-ondersteunde onderdelen.")
    return ET.fromstring(data)


def rijen_uit_xlsx(data):
    """Leest het ledenblad uit een .xlsx (zonder extra bibliotheek, een xlsx is
    een zipbestand met XML). Kiest het blad "Ledenlijst" als dat er is, anders
    het eerste zichtbare blad met een kolom "Naambordje" of "Voornaam"; een
    verborgen blad (bijv. een oude versie van de lijst) telt nooit mee. Geeft
    de rijen als lijst van lijsten tekst, net als de CSV-lezer. ValueError met
    een leesbare melding als het geen bruikbaar Excel-bestand is."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        wb = _xlsx_xml(z, "xl/workbook.xml")
        rels = _xlsx_xml(z, "xl/_rels/workbook.xml.rels")
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ValueError("Dit lijkt geen geldig Excel-bestand (.xlsx).")
    doel = {r.get("Id"): r.get("Target") for r in rels}
    gedeeld = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in _xlsx_xml(z, "xl/sharedStrings.xml").findall("m:si", _XLSX_NS):
            gedeeld.append("".join(t.text or "" for t in si.iter("{%s}t" % _XLSX_NS["m"])))

    def kolom(ref):
        n = 0
        for ch in re.match(r"[A-Z]+", ref).group(0):
            n = n * 26 + ord(ch) - 64
        return n - 1

    def blad_rijen(pad):
        rijen = []
        for row in _xlsx_xml(z, pad).iter("{%s}row" % _XLSX_NS["m"]):
            cellen = {}
            for c in row.findall("m:c", _XLSX_NS):
                v = c.find("m:v", _XLSX_NS)
                soort = c.get("t")
                if soort == "s" and v is not None:
                    waarde = gedeeld[int(v.text)]
                elif soort == "inlineStr":
                    waarde = "".join(x.text or "" for x in c.iter("{%s}t" % _XLSX_NS["m"]))
                elif v is not None and v.text is not None:
                    waarde = v.text
                else:
                    continue
                cellen[kolom(c.get("r"))] = waarde
            rijen.append([cellen.get(i, "") for i in range(max(cellen) + 1)] if cellen else [])
        return rijen

    kandidaten = []
    for sh in wb.find("m:sheets", _XLSX_NS):
        if sh.get("state") in ("hidden", "veryHidden"):
            continue
        doelpad = doel.get(sh.get("{%s}id" % _XLSX_NS["r"]), "")
        pad = "xl/" + doelpad.lstrip("/").replace("xl/", "", 1)
        if pad not in z.namelist():
            continue
        kandidaten.append((sh.get("name", ""), pad))
    # "Ledenlijst" eerst, daarna de rest in bladvolgorde.
    kandidaten.sort(key=lambda k: k[0].strip().lower() != "ledenlijst")
    for _, pad in kandidaten:
        rijen = blad_rijen(pad)
        for rij in rijen[:15]:
            cellen = {c.strip().lower() for c in rij}
            if "naambordje" in cellen or "voornaam" in cellen:
                return rijen
    raise ValueError("Geen blad met een kolom 'Naambordje' of 'Voornaam' gevonden in dit Excel-bestand.")


def rijen_naar_csv(rijen):
    """Zet rijen om naar puntkomma-gescheiden tekst -- zo gaat een Excel-
    bestand door dezelfde voorbeeld- en bevestigstappen als een plak- of
    CSV-import."""
    buffer = io.StringIO()
    schrijver = csv.writer(buffer, delimiter=";", lineterminator="\n")
    for rij in rijen:
        schrijver.writerow(rij)
    return buffer.getvalue()


def parse_import(tekst, standaard_bedrag=20):
    """Leest een export van de Club van 20-spreadsheet (CSV, of rechtstreeks
    geplakt uit Google Sheets/Excel = tab-gescheiden). Herkent de kolommen op
    hun kop: Voornaam, Achternaam, Team, Naambordje, een kolom per seizoen
    ("2023-2024") met het betaalde bedrag, "Status 2026-2027" en "Betaald
    door". Regels boven de kop (zoals "Totale opbrengst") worden
    overgeslagen. Geeft {'rijen', 'seizoenen', 'waarschuwingen', 'fout'}."""
    rijen_ruw = _lees_csv(tekst or "")
    kop_index = None
    for i, rij in enumerate(rijen_ruw):
        cellen = {c.strip().lower() for c in rij}
        if "naambordje" in cellen or "voornaam" in cellen:
            kop_index = i
            break
    if kop_index is None:
        return {
            "rijen": [],
            "seizoenen": [],
            "waarschuwingen": [],
            "fout": "Geen kopregel gevonden -- er moet een kolom 'Naambordje' of 'Voornaam' in staan.",
        }

    kop = [c.strip() for c in rijen_ruw[kop_index]]
    velden = {}
    seizoen_kolommen = {}
    status_kolommen = {}
    for idx, naam in enumerate(kop):
        sleutel = naam.lower()
        if sleutel in _KOLOM_NAMEN and _KOLOM_NAMEN[sleutel] not in velden:
            velden[_KOLOM_NAMEN[sleutel]] = idx
            continue
        seizoen = normaliseer_seizoen(naam)
        if seizoen:
            seizoen_kolommen[seizoen] = idx
            continue
        m = _STATUS_KOLOM.match(naam)
        if m and normaliseer_seizoen(m.group(1)):
            status_kolommen[normaliseer_seizoen(m.group(1))] = idx

    # "Betaald door" hoort bij het seizoen van de statuskolom (zo staat het
    # in de spreadsheet), of anders bij het laatste seizoen.
    alle = sorted(set(seizoen_kolommen) | set(status_kolommen))
    betaald_door_seizoen = max(status_kolommen) if status_kolommen else (alle[-1] if alle else None)

    def cel(rij, idx):
        return rij[idx] if idx is not None and idx < len(rij) else ""

    rijen = []
    waarschuwingen = []
    gezien = {}
    for regelnr, rij in enumerate(rijen_ruw[kop_index + 1 :], start=kop_index + 2):
        if not any(c.strip() for c in rij):
            continue
        voornaam = _schoon(cel(rij, velden.get("voornaam")))
        achternaam = _schoon(cel(rij, velden.get("achternaam")))
        naam = _schoon(cel(rij, velden.get("naam")))
        if not naam:
            naam = " ".join(d for d in (voornaam, achternaam) if d)
            if naam:
                waarschuwingen.append(f"Regel {regelnr}: geen naambordje, '{naam}' gebruikt.")
        if not naam:
            waarschuwingen.append(f"Regel {regelnr}: geen naam of naambordje, overgeslagen.")
            continue
        sleutel = naam.lower()
        if sleutel in gezien:
            gezien[sleutel] += 1
            nieuwe_naam = f"{naam} ({gezien[sleutel]})"
            waarschuwingen.append(
                f"Regel {regelnr}: naambordje '{naam}' komt vaker voor, geïmporteerd als '{nieuwe_naam}'."
            )
            naam = nieuwe_naam
        else:
            gezien[sleutel] = 1

        bijdragen = {}
        for seizoen in alle:
            ruw = cel(rij, seizoen_kolommen.get(seizoen))
            bedrag = _bedrag(ruw)
            status_tekst = _schoon(cel(rij, status_kolommen.get(seizoen))).lower()
            status = _STATUS_UIT_TEKST.get(status_tekst)
            if bedrag and bedrag > 0:
                bijdragen[seizoen] = {"status": "betaald", "bedrag": bedrag}
            elif status in ("gevraagd", "toegezegd", "afgezegd"):
                bijdragen[seizoen] = {"status": status, "bedrag": 0}
            elif status == "betaald" and not ruw.strip():
                # Alleen "Betaald" zonder bedragkolom: standaardbedrag.
                bijdragen[seizoen] = {"status": "betaald", "bedrag": standaard_bedrag}
            elif status == "betaald" and bedrag == 0:
                # "Betaald" met expliciet 0 in de bedragkolom: de penningmeester
                # rekent dit lid als verlengd, maar het geld stond al in een
                # eerder seizoen (bijv. vooruitbetaald). Verlengd dus, met bedrag
                # 0 zodat de totalen niets dubbel tellen.
                bijdragen[seizoen] = {"status": "betaald", "bedrag": 0, "nul_betaald": True}
        betaald_door = _schoon(cel(rij, velden.get("betaald_door")))
        if betaald_door and betaald_door_seizoen:
            bijdragen.setdefault(betaald_door_seizoen, {"status": "niet_gevraagd", "bedrag": 0})
            bijdragen[betaald_door_seizoen]["betaald_door"] = betaald_door

        rijen.append(
            {
                "naam": naam,
                "voornaam": voornaam,
                "achternaam": achternaam,
                "team": _schoon(cel(rij, velden.get("team"))).rstrip("?").strip(),
                "telefoon": _schoon(cel(rij, velden.get("telefoon"))),
                "email": _schoon(cel(rij, velden.get("email"))),
                "notitie": _schoon(cel(rij, velden.get("notitie"))),
                "bijdragen": bijdragen,
            }
        )
    return {"rijen": rijen, "seizoenen": alle, "waarschuwingen": waarschuwingen, "fout": None}


def _bijdrage_ongewijzigd(bestaande, b):
    """True als de import voor dit seizoen niets verandert aan wat er al staat
    (zelfde status en bedrag) -- dan blijft de bestaande bijdrage met al haar
    details (betaalwijze, notitie) ongemoeid."""
    if b.get("nul_betaald") and bestaande is not None and bestaande["status"] == "betaald":
        return True  # de app heeft dit lid al op betaald, met een echt bedrag: dat blijft
    return (
        bestaande is not None
        and bestaande["status"] == b["status"]
        and (b["status"] != "betaald" or abs((bestaande["bedrag"] or 0) - (b.get("bedrag") or 0)) < 0.005)
        and not b.get("betaald_door")
    )


def import_samenvatting(db, rijen):
    """Wat de import zou doen, voor het voorbeeld: nieuwe leden, en per
    bijdrage of die nieuw, gewijzigd of ongewijzigd is -- zodat je vooraf ziet
    of een grote import (bijv. met jaren historie erbij) alleen aanvult of
    ook bestaande betalingen aanpast."""
    bestaand = {
        r["naam"].lower(): r["id"] for r in db.execute("SELECT id, naam FROM club_van_20_leden").fetchall()
    }
    huidige = {
        (r["lid_id"], r["seizoen"]): r for r in db.execute("SELECT * FROM club_van_20_bijdragen").fetchall()
    }
    samenvatting = {"nieuwe_leden": 0, "bestaande_leden": 0, "nieuw": 0, "gewijzigd": 0, "ongewijzigd": 0, "wijzigingen": []}
    for rij in rijen:
        lid_id = bestaand.get(rij["naam"].lower())
        samenvatting["bestaande_leden" if lid_id else "nieuwe_leden"] += 1
        for seizoen, b in rij["bijdragen"].items():
            if b["status"] == "niet_gevraagd" and not b.get("betaald_door"):
                continue
            huidig = huidige.get((lid_id, seizoen)) if lid_id else None
            if huidig is None:
                samenvatting["nieuw"] += 1
            elif _bijdrage_ongewijzigd(huidig, b):
                samenvatting["ongewijzigd"] += 1
            else:
                samenvatting["gewijzigd"] += 1
                samenvatting["wijzigingen"].append(
                    f"{rij['naam']} {seizoen}: {BIJDRAGE_STATUS_LABELS[huidig['status']].lower()}"
                    f"{' €%g' % huidig['bedrag'] if huidig['status'] == 'betaald' else ''} → "
                    f"{BIJDRAGE_STATUS_LABELS[b['status']].lower()}"
                    f"{' €%g' % b['bedrag'] if b['status'] == 'betaald' else ''}"
                )
    return samenvatting


def _bijdrage_tekst(b):
    """Korte tekst voor een bijdrage in het importvoorbeeld, bijv. "betaald €20"."""
    tekst = BIJDRAGE_STATUS_LABELS[b["status"]].lower()
    if b["status"] == "betaald":
        # b is een regel uit de import (dict) of uit de database (sqlite Row, zonder .get)
        nul = isinstance(b, dict) and b.get("nul_betaald")
        tekst += " (€0 in het bestand)" if nul else " €%g" % (b["bedrag"] or 0)
    return tekst


def import_rij_overzicht(db, rijen):
    """Per rij uit de import (zelfde volgorde) wat er voor dat lid zou gebeuren,
    zodat je in het voorbeeld per lid kunt kiezen of 'ie meegaat:
    {'soort', 'regels'}. soort is 'nieuw' (lid bestaat nog niet), 'wijziging'
    (bestaand lid krijgt een nieuwe of aangepaste betaling, of lege velden
    aangevuld), 'conflict' (een bestaande betaling van 'betaald' wordt
    anders: een andere status of een ander bedrag) of 'niets' (er verandert
    niets). Een conflict staat in het voorbeeld standaard niet aangevinkt:
    daar kan de app nieuwer zijn dan het bestand."""
    leden = {r["naam"].lower(): r for r in db.execute("SELECT * FROM club_van_20_leden").fetchall()}
    huidige = {
        (r["lid_id"], r["seizoen"]): r for r in db.execute("SELECT * FROM club_van_20_bijdragen").fetchall()
    }
    uitkomst = []
    for rij in rijen:
        lid = leden.get(rij["naam"].lower())
        regels = []
        conflict = False
        if lid is not None:
            aanvullen = [
                veld
                for veld in ("voornaam", "achternaam", "team", "telefoon", "email", "notitie")
                if rij[veld] and not (lid[veld] or "").strip()
            ]
            if aanvullen:
                regels.append("vult aan: " + ", ".join(aanvullen))
        for seizoen, b in rij["bijdragen"].items():
            if b["status"] == "niet_gevraagd" and not b.get("betaald_door"):
                continue
            huidig = huidige.get((lid["id"], seizoen)) if lid is not None else None
            if huidig is None:
                regels.append(f"{seizoen}: {_bijdrage_tekst(b)}")
            elif not _bijdrage_ongewijzigd(huidig, b):
                regels.append(f"{seizoen}: {_bijdrage_tekst(huidig)} → {_bijdrage_tekst(b)}")
                if huidig["status"] == "betaald" and (
                    b["status"] != "betaald" or abs((huidig["bedrag"] or 0) - (b.get("bedrag") or 0)) >= 0.005
                ):
                    conflict = True
        if lid is None:
            soort = "nieuw"
        elif conflict:
            soort = "conflict"
        elif regels:
            soort = "wijziging"
        else:
            soort = "niets"
        uitkomst.append({"soort": soort, "regels": regels})
    return uitkomst


def verlengingen_overzicht(db, rijen, seizoen):
    """Wie volgens het bestand voor `seizoen` betaald heeft (= verlengd), voor het
    voorbeeld van de import: {'seizoen', 'totaal', 'al_betaald', 'wordt_betaald',
    'nieuw', 'rijen'}. 'al_betaald' zijn leden die in de app al op betaald staan,
    'wordt_betaald' bestaande leden die de import op betaald zet, 'nieuw' leden die
    er nog niet zijn (namen), 'rijen' de volgnummers (in `rijen`) van de leden die de
    import nog moet verlengen (dus 'wordt_betaald' en 'nieuw', niet 'al_betaald')."""
    leden = {r["naam"].lower(): r["id"] for r in db.execute("SELECT id, naam FROM club_van_20_leden").fetchall()}
    betaald = {
        r["lid_id"]
        for r in db.execute(
            "SELECT lid_id FROM club_van_20_bijdragen WHERE seizoen = ? AND status = 'betaald'", (seizoen,)
        ).fetchall()
    }
    uitkomst = {"seizoen": seizoen, "totaal": 0, "al_betaald": [], "wordt_betaald": [], "nieuw": [], "rijen": []}
    for index, rij in enumerate(rijen):
        b = rij["bijdragen"].get(seizoen)
        if not b or b["status"] != "betaald":
            continue
        lid_id = leden.get(rij["naam"].lower())
        if lid_id is None:
            soort = "nieuw"
        elif lid_id in betaald:
            soort = "al_betaald"
        else:
            soort = "wordt_betaald"
        uitkomst[soort].append(rij["naam"])
        if soort != "al_betaald":
            uitkomst["rijen"].append(index)
        uitkomst["totaal"] += 1
    return uitkomst


def voer_import_uit(db, rijen, gebruiker=None, standaard_bedrag=20):
    """Zet geparste rijen (zie parse_import) in de database. Een lid met
    hetzelfde naambordje (hoofdletterongevoelig) wordt bijgewerkt i.p.v.
    dubbel aangemaakt. Bij zo'n bestaand lid worden alleen LEGE velden
    (team, telefoon, ...) aangevuld: wat in de app is aangepast (bijv. een
    team dat inmiddels O23 heet) blijft staan. De seizoenen uit de import
    overschrijven wat er voor die seizoenen stond, behalve een bijdrage die
    al dezelfde status en hetzelfde bedrag heeft (die blijft met al haar
    details -- betaalwijze, notitie -- ongemoeid); andere seizoenen blijven
    ongemoeid. Geeft (aantal nieuw, aantal bijgewerkt)."""
    bestaand = {
        r["naam"].lower(): r["id"]
        for r in db.execute("SELECT id, naam FROM club_van_20_leden").fetchall()
    }
    nieuw = bijgewerkt = 0
    vandaag = vandaag_amsterdam().isoformat()
    for rij in rijen:
        lid_id = bestaand.get(rij["naam"].lower())
        if lid_id is None:
            cursor = db.execute(
                """INSERT INTO club_van_20_leden
                       (naam, voornaam, achternaam, team, telefoon, email, notitie,
                        status, startdatum, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'actief', ?, ?)""",
                (
                    rij["naam"],
                    rij["voornaam"] or None,
                    rij["achternaam"] or None,
                    rij["team"] or None,
                    rij["telefoon"] or None,
                    rij["email"] or None,
                    rij["notitie"] or None,
                    vandaag,
                    now_str(),
                ),
            )
            lid_id = cursor.lastrowid
            bestaand[rij["naam"].lower()] = lid_id
            nieuw += 1
        else:
            # Alleen lege velden aanvullen: de app is leidend, de import
            # vult gaten.
            huidig = db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
            for veld in ("voornaam", "achternaam", "team", "telefoon", "email", "notitie"):
                if rij[veld] and not (huidig[veld] or "").strip():
                    db.execute(
                        f"UPDATE club_van_20_leden SET {veld} = ? WHERE id = ?", (rij[veld], lid_id)
                    )
            bijgewerkt += 1
        for seizoen, b in rij["bijdragen"].items():
            bestaande = db.execute(
                "SELECT status, bedrag FROM club_van_20_bijdragen WHERE lid_id = ? AND seizoen = ?",
                (lid_id, seizoen),
            ).fetchone()
            if _bijdrage_ongewijzigd(bestaande, b):
                continue
            sla_bijdrage_op(
                db,
                lid_id,
                seizoen,
                b["status"],
                bedrag=b.get("bedrag"),
                betaald_door=b.get("betaald_door"),
                standaard_bedrag=standaard_bedrag,
                gebruiker=gebruiker,
                # Historische seizoenen: geen "vandaag" als betaaldatum,
                # anders lijkt iedereen ineens een nieuw lid.
                betaald_op=f"{seizoen[:4]}-{SEIZOEN_STARTMAAND:02d}-01",
                nul_toegestaan=bool(b.get("nul_betaald")),
                melding=False,  # oude gegevens inlezen is geen nieuw lid op het scherm
            )
    return nieuw, bijgewerkt
