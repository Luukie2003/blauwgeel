from flask import Response, flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import (
    bereken_kassalade_stand,
    bereken_kluis_stand,
    bereken_voorspelde_tekorten,
    besteleenheid_factor,
    besteleenheid_naam,
    bestel_suggesties,
    heeft_sectie_toegang,
    naar_besteleenheden,
    now_str,
)
from pdf import compacte_uitdraai_pdf
from seizoensrapport import bereken_seizoensrapport
from voorspelling import maak_prognose

ONDERDELEN = ("kas", "kluis", "voorraad", "bestellijst", "prognose", "seizoenen")
PROGNOSE_DAGEN = 7

AANTAL_RECENTE_MUTATIES = 4


def _toegestane_onderdelen():
    """Welke onderdelen deze gebruiker op de uitdraai mag zetten -- volgt de
    bestaande rechten: kassa en voorraad via hun sectie, de kluis is (net als
    de kluispagina's zelf) alleen voor beheerders."""
    rol = session.get("gebruiker_rol")
    secties = session.get("gebruiker_secties")
    return {
        "kas": heeft_sectie_toegang(rol, secties, "kassa"),
        "kluis": rol == "beheerder",
        "voorraad": heeft_sectie_toegang(rol, secties, "voorraad"),
        "bestellijst": heeft_sectie_toegang(rol, secties, "voorraad"),
        "prognose": heeft_sectie_toegang(rol, secties, "voorraad"),
        # Net als het seizoensrapport zelf (Rapporten) voor iedereen.
        "seizoenen": True,
    }


def _telling_samenvatting(telling):
    if telling is None:
        return None
    return {
        "datum": telling["datum"],
        "naam": telling["naam"],
        "verwacht": telling["verwacht_bedrag"],
        "geteld": telling["geteld_bedrag"],
        "verschil": telling["verschil"],
        "goedgekeurd_door": telling["goedgekeurd_door"],
    }


def bouw_kas_gegevens(db):
    stand = bereken_kassalade_stand(db)
    mutaties = db.execute(
        "SELECT * FROM kassa_mutaties ORDER BY datum DESC, id DESC LIMIT ?",
        (AANTAL_RECENTE_MUTATIES,),
    ).fetchall()
    open_telling = db.execute(
        "SELECT COUNT(*) AS n FROM kassa_tellingen WHERE afgesloten = 0"
    ).fetchone()["n"]
    return {
        "stand": stand["stand"],
        "laatste_telling": _telling_samenvatting(stand["laatste_telling"]),
        "open_tellingen": open_telling,
        # afdracht = kassalade -> kluis, toevoeging = kluis -> kassalade
        "mutaties": [
            {
                "datum": m["datum"],
                "omschrijving": "Afdracht naar kluis" if m["type"] == "afdracht" else "Toevoeging uit kluis",
                "bedrag": -m["bedrag"] if m["type"] == "afdracht" else m["bedrag"],
            }
            for m in mutaties
        ],
    }


def bouw_kluis_gegevens(db):
    stand = bereken_kluis_stand(db)
    kluis_mutaties = db.execute(
        "SELECT * FROM kluis_mutaties ORDER BY datum DESC, id DESC LIMIT ?",
        (AANTAL_RECENTE_MUTATIES,),
    ).fetchall()
    overboekingen = db.execute(
        "SELECT * FROM kassa_mutaties ORDER BY datum DESC, id DESC LIMIT ?",
        (AANTAL_RECENTE_MUTATIES,),
    ).fetchall()
    open_telling = db.execute(
        "SELECT COUNT(*) AS n FROM kluis_tellingen WHERE afgesloten = 0"
    ).fetchone()["n"]
    # Vanuit de kluis gezien: een afdracht uit de kassalade komt erbij, een
    # storting (naar de bank/penningmeester) of opname gaat erbij of eraf.
    regels = []
    for m in overboekingen:
        if m["type"] == "afdracht":
            regels.append((m["datum"], "Afdracht uit kassalade", m["bedrag"]))
        else:
            regels.append((m["datum"], "Toevoeging aan kassalade", -m["bedrag"]))
    for m in kluis_mutaties:
        if m["type"] == "opname":
            regels.append((m["datum"], "Opname", m["bedrag"]))
        else:
            regels.append((m["datum"], "Storting", -m["bedrag"]))
    regels.sort(key=lambda r: r[0], reverse=True)
    return {
        "stand": stand["stand"],
        "laatste_telling": _telling_samenvatting(stand["laatste_telling"]),
        "open_tellingen": open_telling,
        "mutaties": [
            {"datum": datum, "omschrijving": omschrijving, "bedrag": bedrag}
            for datum, omschrijving, bedrag in regels[:AANTAL_RECENTE_MUTATIES]
        ],
    }


def bouw_voorraad_gegevens(db):
    producten = db.execute(
        "SELECT naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs FROM producten "
        "WHERE actief = 1 ORDER BY categorie, naam"
    ).fetchall()
    categorieen = {}
    for p in producten:
        categorieen.setdefault(p["categorie"], []).append(
            {
                "naam": p["naam"],
                "eenheid": p["eenheid"],
                "voorraad": p["voorraad"],
                "minimum": p["min_voorraad"],
                "laag": p["voorraad"] < p["min_voorraad"],
            }
        )
    return {
        "categorieen": [{"naam": naam, "producten": lijst} for naam, lijst in categorieen.items()],
        "aantal_producten": len(producten),
        "aantal_laag": sum(1 for p in producten if p["voorraad"] < p["min_voorraad"]),
        "totale_waarde": sum(p["voorraad"] * p["verkoopprijs"] for p in producten),
    }


def _bestel_tekst(product, hoeveelheid):
    """"2 krat (48 flesjes)" -- afgerond op hele besteleenheden."""
    aantal = naar_besteleenheden(hoeveelheid, product)
    tekst = f"{aantal} {besteleenheid_naam(product)}"
    factor = besteleenheid_factor(product)
    if factor > 1:
        tekst += f" ({aantal * factor} {product['eenheid']})"
    return tekst


def bouw_bestellijst_gegevens(db):
    nu = []
    for p in bestel_suggesties(db):
        tekort = p["bestel_hoeveelheid"] if p["bestel_hoeveelheid"] > 0 else max(0, p["min_voorraad"] - p["voorraad"])
        nu.append(
            {
                "naam": p["naam"],
                "voorraad": f"{p['voorraad']} {p['eenheid']}",
                "minimum": f"{p['min_voorraad']} {p['eenheid']}",
                "bestel": _bestel_tekst(p, tekort),
            }
        )
    tekorten = []
    for t in bereken_voorspelde_tekorten(db, dagen_vooruit=PROGNOSE_DAGEN):
        p = t["product"]
        tekorten.append(
            {
                "naam": p["naam"],
                "voorraad": f"{p['voorraad']} {p['eenheid']}",
                "kans": f"{round(t['kans_tekort'] * 100)}%",
                "bestel": _bestel_tekst(p, t["advies_stuks"]) if t["advies_stuks"] else "-",
            }
        )
    return {"nu": nu, "tekorten": tekorten, "dagen": PROGNOSE_DAGEN}


def bouw_prognose_gegevens(db):
    prognose = maak_prognose(db, dagen=PROGNOSE_DAGEN)
    if not prognose["beschikbaar"]:
        return {"beschikbaar": False, "reden": prognose["reden"]}
    dagen = []
    for d in prognose["dagen_overzicht"]:
        opmerkingen = []
        if d["wedstrijden"]:
            opmerkingen.append(f"{d['wedstrijden']} thuiswedstrijd" + ("en" if d["wedstrijden"] > 1 else ""))
        if d["training"]:
            opmerkingen.append("training")
        dagen.append(
            {
                "dag": f"{d['weekdag'].capitalize()} {d['datum'].day}-{d['datum'].month}",
                "open": d["open"],
                "omzet": d["omzet"],
                "opmerking": ", ".join(opmerkingen),
            }
        )
    risico = [
        {
            "naam": p["product"]["naam"],
            "voorraad": f"{p['voorraad']} {p['product']['eenheid']}",
            "kans": f"{round(p['kans_tekort'] * 100)}%",
            "status": p["status"],
        }
        for p in prognose["producten"]
        if p["status"] in ("urgent", "let_op")
    ]
    return {
        "beschikbaar": True,
        "dagen_aantal": PROGNOSE_DAGEN,
        "omzet": prognose["totaal"]["omzet"],
        "laag": prognose["totaal"]["laag"],
        "hoog": prognose["totaal"]["hoog"],
        "betrouwbaarheid": prognose["model"]["betrouwbaarheid"],
        "dagen": dagen,
        "risico": risico,
    }


def register_routes(app):

    @app.route("/rapporten/uitdraai")
    def compacte_uitdraai():
        return render_template("compacte_uitdraai.html", toegestaan=_toegestane_onderdelen())

    @app.route("/rapporten/uitdraai/pdf")
    def compacte_uitdraai_pdf_route():
        toegestaan = _toegestane_onderdelen()
        gekozen = [onderdeel for onderdeel in ONDERDELEN if request.args.get(onderdeel) and toegestaan[onderdeel]]
        if not gekozen:
            flash("Kies minstens één onderdeel voor de uitdraai.", "error")
            return redirect(url_for("compacte_uitdraai"))

        db = get_db()
        pdf_bytes = compacte_uitdraai_pdf(
            kas=bouw_kas_gegevens(db) if "kas" in gekozen else None,
            kluis=bouw_kluis_gegevens(db) if "kluis" in gekozen else None,
            voorraad=bouw_voorraad_gegevens(db) if "voorraad" in gekozen else None,
            bestellijst=bouw_bestellijst_gegevens(db) if "bestellijst" in gekozen else None,
            prognose=bouw_prognose_gegevens(db) if "prognose" in gekozen else None,
            seizoenen={"rapport": bereken_seizoensrapport(db)} if "seizoenen" in gekozen else None,
            moment=now_str(),
        )
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": "inline; filename=compacte-uitdraai.pdf"},
        )
