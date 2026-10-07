"""Sponsoren, mededelingen en de sjabloonbouwer voor de dia's."""

import json

from flask import flash, redirect, render_template, request, url_for

from club_van_20 import bereken_club_van_20_status
from database import get_db
from helpers import (
    HEX_KLEUR_PATROON,
    KIOSK_AFBEELDINGEN_MAP,
    KIOSK_ELEMENT_TYPES,
    KIOSK_OVERGANGEN,
    KIOSK_OVERGANG_SLEUTELS,
    KIOSK_SPONSOR_SJABLONEN,
    KIOSK_SPONSOR_SJABLOON_AANGEPAST,
    KIOSK_SPONSOR_SJABLOON_SLEUTELS,
    KIOSK_SPONSOR_SJABLOON_VOORBEELDEN,
    KIOSK_TEKST_GROOTTES,
    KIOSK_TEKST_GROOTTE_SLEUTELS,
    KIOSK_UITLIJNINGEN,
    MOTM_RESULTATEN,
    now_str,
    sla_afbeelding_op,
)
from routes.kiosk.dia_gegevens import _motm_teams, _stand_poules, _stand_teams
from routes.kiosk.gedeeld import _scherm_instellingen


def _sponsor_uit_formulier():
    sjabloon = request.form.get("sjabloon", "").strip()
    custom_sjabloon_id = None
    if sjabloon == KIOSK_SPONSOR_SJABLOON_AANGEPAST:
        db = get_db()
        try:
            gekozen_id = int(request.form.get("custom_sjabloon_id") or 0)
        except ValueError:
            gekozen_id = 0
        bestaat = db.execute(
            "SELECT 1 FROM kiosk_sjablonen_custom WHERE id = ?", (gekozen_id,)
        ).fetchone()
        if bestaat:
            custom_sjabloon_id = gekozen_id
        else:
            sjabloon = KIOSK_SPONSOR_SJABLONEN[0][0]
    elif sjabloon not in KIOSK_SPONSOR_SJABLOON_SLEUTELS:
        sjabloon = KIOSK_SPONSOR_SJABLONEN[0][0]
    try:
        duur = int(request.form.get("weergave_duur_seconden") or 8)
    except ValueError:
        duur = 8
    try:
        volgorde = int(request.form.get("volgorde") or 0)
    except ValueError:
        volgorde = 0
    overgang = request.form.get("overgang", "").strip()
    if overgang not in KIOSK_OVERGANG_SLEUTELS:
        overgang = "fade"
    tekst_grootte = request.form.get("tekst_grootte", "").strip()
    if tekst_grootte not in KIOSK_TEKST_GROOTTE_SLEUTELS:
        tekst_grootte = "normaal"
    return {
        "sjabloon": sjabloon,
        "custom_sjabloon_id": custom_sjabloon_id,
        "titel": request.form.get("titel", "").strip() or None,
        "tekst": request.form.get("tekst", "").strip() or None,
        "weergave_duur_seconden": max(2, duur),
        "volgorde": volgorde,
        "actief": 1 if request.form.get("actief") else 0,
        "overgang": overgang,
        "tekst_grootte": tekst_grootte,
    }


def _sjablonen_custom_context(db):
    """Eigen sjablonen in 2 vormen voor kiosk_sponsor_form.html: de rijen
    zelf (voor de dropdown) en een JSON-veilige lijst (voor het
    client-side live voorbeeld, dat een sqlite3.Row niet met |tojson
    kan serialiseren)."""
    rijen = db.execute(
        "SELECT * FROM kiosk_sjablonen_custom ORDER BY naam COLLATE NOCASE"
    ).fetchall()
    json_lijst = [
        {
            "id": r["id"],
            "naam": r["naam"],
            "achtergrond_kleur": r["achtergrond_kleur"],
            "achtergrond_afbeelding": r["achtergrond_afbeelding"],
            "overlay_donker": bool(r["overlay_donker"]),
            "elementen": json.loads(r["elementen"]),
        }
        for r in rijen
    ]
    return rijen, json_lijst


# ---------- Onderdeel 2b: Eigen sjablonen (drag-and-drop bouwer) ----------

def _sjabloon_producten(db):
    """Producten voor de product-kiezer bij een 'prijs'-element (zie
    KIOSK_ELEMENT_TYPES) -- inclusief de huidige prijs, zodat de bouwer
    al een levensechte live-preview kan tonen. Platte dicts (i.p.v.
    sqlite3.Row) omdat dit rechtstreeks als JSON naar de pagina gaat."""
    rijen = db.execute(
        "SELECT id, naam, verkoopprijs FROM producten WHERE actief = 1 ORDER BY naam"
    ).fetchall()
    return [{"id": r["id"], "naam": r["naam"], "verkoopprijs": r["verkoopprijs"]} for r in rijen]


def _sjabloon_elementen_uit_formulier():
    """Parseert en valideert de door de bouwer opgestuurde elementen_json
    (zie kiosk_sjabloon_bouwer.html). Ongeldige of onbekende velden per
    element worden stilzwijgend teruggezet op een veilige standaard i.p.v.
    het hele sjabloon te laten mislukken -- alleen echt kapotte JSON of
    een niet-lijst levert een lege elementenlijst op."""
    try:
        ruw = json.loads(request.form.get("elementen_json") or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(ruw, list):
        return []

    def _percentage(waarde, standaard):
        try:
            getal = float(waarde)
        except (TypeError, ValueError):
            return standaard
        return max(0.0, min(100.0, getal))

    elementen = []
    for item in ruw:
        if not isinstance(item, dict):
            continue
        type_ = item.get("type")
        if type_ not in KIOSK_ELEMENT_TYPES:
            continue
        kleur = item.get("kleur", "")
        if not isinstance(kleur, str) or not HEX_KLEUR_PATROON.match(kleur):
            kleur = "#ffffff"
        uitlijning = item.get("uitlijning")
        if uitlijning not in KIOSK_UITLIJNINGEN:
            uitlijning = "links"
        lettergrootte = item.get("lettergrootte")
        if lettergrootte not in KIOSK_TEKST_GROOTTE_SLEUTELS:
            lettergrootte = "normaal"
        product_id = None
        if type_ == "prijs":
            try:
                product_id = int(item.get("product_id"))
            except (TypeError, ValueError):
                product_id = None
        elementen.append(
            {
                "type": type_,
                "x": _percentage(item.get("x"), 5.0),
                "y": _percentage(item.get("y"), 5.0),
                "breedte": _percentage(item.get("breedte"), 30.0),
                "hoogte": _percentage(item.get("hoogte"), 20.0),
                "kleur": kleur,
                "uitlijning": uitlijning,
                "lettergrootte": lettergrootte,
                "inhoud": str(item.get("inhoud") or "") if type_ == "vrije_tekst" else None,
                "product_id": product_id,
            }
        )
    return elementen


def register_routes(app):
    # ---------- Onderdeel 2: Sponsoren/leden beheren ----------

    @app.route("/kiosk/sponsoren-leden")
    def kiosk_sponsoren_leden():
        db = get_db()
        sponsoren = db.execute("SELECT * FROM kiosk_sponsoren ORDER BY volgorde, id").fetchall()
        club_van_20 = bereken_club_van_20_status(db)
        sjablonen_custom = db.execute(
            "SELECT * FROM kiosk_sjablonen_custom ORDER BY naam COLLATE NOCASE"
        ).fetchall()
        gebruik_per_sjabloon = dict(
            db.execute(
                """SELECT custom_sjabloon_id, COUNT(*) AS n FROM kiosk_sponsoren
                   WHERE custom_sjabloon_id IS NOT NULL GROUP BY custom_sjabloon_id"""
            ).fetchall()
        )
        aantal_elementen_per_sjabloon = {
            s["id"]: len(json.loads(s["elementen"])) for s in sjablonen_custom
        }
        instellingen = _scherm_instellingen(db)
        return render_template(
            "kiosk_sponsoren_leden.html",
            sponsoren=sponsoren,
            club_van_20=club_van_20,
            sjabloon_labels=dict(KIOSK_SPONSOR_SJABLONEN),
            sjablonen_custom=sjablonen_custom,
            aantal_elementen_per_sjabloon=aantal_elementen_per_sjabloon,
            gebruik_per_sjabloon=gebruik_per_sjabloon,
            instellingen=instellingen,
            stand_poules=_stand_poules(db),
            stand_teams={p["sleutel"]: _stand_teams(db, p["sleutel"]) for p in _stand_poules(db)},
            club_logos={
                r["club"]: r["afbeelding"] for r in db.execute("SELECT club, afbeelding FROM kiosk_club_logos").fetchall()
            },
            motm_teams=_motm_teams(db),
            motm_resultaten=MOTM_RESULTATEN,
        )

    @app.route("/kiosk/sponsoren-leden/sponsoren/nieuw", methods=["GET", "POST"])
    def kiosk_sponsor_nieuw():
        db = get_db()
        if request.method == "POST":
            gegevens = _sponsor_uit_formulier()
            afbeelding = sla_afbeelding_op(request.files.get("afbeelding"), KIOSK_AFBEELDINGEN_MAP)
            achtergrond_afbeelding = None
            if gegevens["sjabloon"] == "mededeling_groot":
                achtergrond_afbeelding = sla_afbeelding_op(
                    request.files.get("achtergrond_afbeelding"), KIOSK_AFBEELDINGEN_MAP
                )
            db.execute(
                """INSERT INTO kiosk_sponsoren
                   (sjabloon, custom_sjabloon_id, titel, tekst, afbeelding,
                    achtergrond_afbeelding, overgang, tekst_grootte,
                    weergave_duur_seconden, volgorde, actief, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    gegevens["sjabloon"],
                    gegevens["custom_sjabloon_id"],
                    gegevens["titel"],
                    gegevens["tekst"],
                    afbeelding,
                    achtergrond_afbeelding,
                    gegevens["overgang"],
                    gegevens["tekst_grootte"],
                    gegevens["weergave_duur_seconden"],
                    gegevens["volgorde"],
                    gegevens["actief"],
                    now_str(),
                ),
            )
            db.commit()
            flash("Sponsor toegevoegd.", "success")
            return redirect(url_for("kiosk_sponsoren_leden"))
        sjablonen_custom, sjablonen_custom_json = _sjablonen_custom_context(db)
        return render_template(
            "kiosk_sponsor_form.html",
            sponsor=None,
            sjablonen=KIOSK_SPONSOR_SJABLONEN,
            sjabloon_voorbeelden=KIOSK_SPONSOR_SJABLOON_VOORBEELDEN,
            sjablonen_custom=sjablonen_custom,
            sjablonen_custom_json=sjablonen_custom_json,
            overgangen=KIOSK_OVERGANGEN,
            tekst_groottes=KIOSK_TEKST_GROOTTES,
            producten=_sjabloon_producten(db),
        )

    @app.route("/kiosk/sponsoren-leden/sponsoren/<int:sponsor_id>/bewerken", methods=["GET", "POST"])
    def kiosk_sponsor_bewerken(sponsor_id):
        db = get_db()
        sponsor = db.execute(
            "SELECT * FROM kiosk_sponsoren WHERE id = ?", (sponsor_id,)
        ).fetchone()
        if sponsor is None:
            flash("Sponsor niet gevonden.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))

        if request.method == "POST":
            gegevens = _sponsor_uit_formulier()
            nieuwe_afbeelding = sla_afbeelding_op(
                request.files.get("afbeelding"), KIOSK_AFBEELDINGEN_MAP
            )
            if nieuwe_afbeelding:
                afbeelding = nieuwe_afbeelding
            elif request.form.get("afbeelding_verwijderen"):
                afbeelding = None
            else:
                afbeelding = sponsor["afbeelding"]

            achtergrond_afbeelding = None
            if gegevens["sjabloon"] == "mededeling_groot":
                nieuwe_achtergrond = sla_afbeelding_op(
                    request.files.get("achtergrond_afbeelding"), KIOSK_AFBEELDINGEN_MAP
                )
                if nieuwe_achtergrond:
                    achtergrond_afbeelding = nieuwe_achtergrond
                elif request.form.get("achtergrond_afbeelding_verwijderen"):
                    achtergrond_afbeelding = None
                else:
                    achtergrond_afbeelding = sponsor["achtergrond_afbeelding"]

            db.execute(
                """UPDATE kiosk_sponsoren
                   SET sjabloon = ?, custom_sjabloon_id = ?, titel = ?, tekst = ?,
                       afbeelding = ?, achtergrond_afbeelding = ?, overgang = ?,
                       tekst_grootte = ?, weergave_duur_seconden = ?, volgorde = ?,
                       actief = ?
                   WHERE id = ?""",
                (
                    gegevens["sjabloon"],
                    gegevens["custom_sjabloon_id"],
                    gegevens["titel"],
                    gegevens["tekst"],
                    afbeelding,
                    achtergrond_afbeelding,
                    gegevens["overgang"],
                    gegevens["tekst_grootte"],
                    gegevens["weergave_duur_seconden"],
                    gegevens["volgorde"],
                    gegevens["actief"],
                    sponsor_id,
                ),
            )
            db.commit()
            flash("Sponsor bijgewerkt.", "success")
            return redirect(url_for("kiosk_sponsoren_leden"))
        sjablonen_custom, sjablonen_custom_json = _sjablonen_custom_context(db)
        return render_template(
            "kiosk_sponsor_form.html",
            sponsor=sponsor,
            sjablonen=KIOSK_SPONSOR_SJABLONEN,
            sjabloon_voorbeelden=KIOSK_SPONSOR_SJABLOON_VOORBEELDEN,
            sjablonen_custom=sjablonen_custom,
            sjablonen_custom_json=sjablonen_custom_json,
            overgangen=KIOSK_OVERGANGEN,
            tekst_groottes=KIOSK_TEKST_GROOTTES,
            producten=_sjabloon_producten(db),
        )

    @app.route("/kiosk/sponsoren-leden/sponsoren/<int:sponsor_id>/verwijderen", methods=["POST"])
    def kiosk_sponsor_verwijderen(sponsor_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_sponsoren WHERE id = ?", (sponsor_id,))
        db.commit()
        flash("Sponsor verwijderd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/sponsoren-leden/sjablonen/nieuw", methods=["GET", "POST"])
    def kiosk_sjabloon_nieuw():
        db = get_db()
        if request.method == "POST":
            naam = request.form.get("naam", "").strip() or "Naamloos sjabloon"
            achtergrond_kleur = request.form.get("achtergrond_kleur", "").strip()
            if not HEX_KLEUR_PATROON.match(achtergrond_kleur):
                achtergrond_kleur = "#0f1f4d"
            achtergrond_afbeelding = sla_afbeelding_op(
                request.files.get("achtergrond_afbeelding"), KIOSK_AFBEELDINGEN_MAP
            )
            db.execute(
                """INSERT INTO kiosk_sjablonen_custom
                   (naam, achtergrond_kleur, achtergrond_afbeelding, overlay_donker,
                    elementen, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    naam,
                    achtergrond_kleur,
                    achtergrond_afbeelding,
                    1 if request.form.get("overlay_donker") else 0,
                    json.dumps(_sjabloon_elementen_uit_formulier()),
                    now_str(),
                ),
            )
            db.commit()
            flash("Sjabloon opgeslagen.", "success")
            return redirect(url_for("kiosk_sponsoren_leden"))
        return render_template(
            "kiosk_sjabloon_bouwer.html",
            sjabloon=None,
            sjabloon_elementen=[],
            tekst_groottes=KIOSK_TEKST_GROOTTES,
            producten=_sjabloon_producten(db),
        )

    @app.route("/kiosk/sponsoren-leden/sjablonen/<int:sjabloon_id>/bewerken", methods=["GET", "POST"])
    def kiosk_sjabloon_bewerken(sjabloon_id):
        db = get_db()
        sjabloon = db.execute(
            "SELECT * FROM kiosk_sjablonen_custom WHERE id = ?", (sjabloon_id,)
        ).fetchone()
        if sjabloon is None:
            flash("Sjabloon niet gevonden.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))

        if request.method == "POST":
            naam = request.form.get("naam", "").strip() or "Naamloos sjabloon"
            achtergrond_kleur = request.form.get("achtergrond_kleur", "").strip()
            if not HEX_KLEUR_PATROON.match(achtergrond_kleur):
                achtergrond_kleur = "#0f1f4d"
            nieuwe_achtergrond = sla_afbeelding_op(
                request.files.get("achtergrond_afbeelding"), KIOSK_AFBEELDINGEN_MAP
            )
            if nieuwe_achtergrond:
                achtergrond_afbeelding = nieuwe_achtergrond
            elif request.form.get("achtergrond_afbeelding_verwijderen"):
                achtergrond_afbeelding = None
            else:
                achtergrond_afbeelding = sjabloon["achtergrond_afbeelding"]
            db.execute(
                """UPDATE kiosk_sjablonen_custom
                   SET naam = ?, achtergrond_kleur = ?, achtergrond_afbeelding = ?,
                       overlay_donker = ?, elementen = ?
                   WHERE id = ?""",
                (
                    naam,
                    achtergrond_kleur,
                    achtergrond_afbeelding,
                    1 if request.form.get("overlay_donker") else 0,
                    json.dumps(_sjabloon_elementen_uit_formulier()),
                    sjabloon_id,
                ),
            )
            db.commit()
            flash("Sjabloon bijgewerkt.", "success")
            return redirect(url_for("kiosk_sponsoren_leden"))
        return render_template(
            "kiosk_sjabloon_bouwer.html",
            sjabloon=sjabloon,
            sjabloon_elementen=json.loads(sjabloon["elementen"]),
            tekst_groottes=KIOSK_TEKST_GROOTTES,
            producten=_sjabloon_producten(db),
        )

    @app.route("/kiosk/sponsoren-leden/sjablonen/<int:sjabloon_id>/verwijderen", methods=["POST"])
    def kiosk_sjabloon_verwijderen(sjabloon_id):
        db = get_db()
        db.execute(
            """UPDATE kiosk_sponsoren SET sjabloon = 'afbeelding_volledig', custom_sjabloon_id = NULL
               WHERE custom_sjabloon_id = ?""",
            (sjabloon_id,),
        )
        db.execute("DELETE FROM kiosk_sjablonen_custom WHERE id = ?", (sjabloon_id,))
        db.commit()
        flash("Sjabloon verwijderd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))
