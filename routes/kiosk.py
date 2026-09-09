from flask import flash, redirect, render_template, request, url_for

import qr
from database import get_db
from helpers import (
    KIOSK_AFBEELDINGEN_MAP,
    KIOSK_SPONSOR_SJABLONEN,
    KIOSK_SPONSOR_SJABLOON_SLEUTELS,
    bereken_komende_thuiswedstrijden,
    now_str,
    sla_afbeelding_op,
)


def register_routes(app):
    def _scherm_instellingen(db):
        return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()

    def _bouw_slides(db):
        """Bouwt de geordende lijst slides voor het kantine scherm, op basis
        van kiosk_scherm_instellingen: elke slide is een dict met minstens
        'type' en 'duur' (seconden weergavetijd), plus type-specifieke
        velden. Een blok (sponsoren/club van 20/wedstrijden) dat uitstaat of
        toevallig leeg is, levert gewoon geen slides op -- dan draait de
        diashow vanzelf zonder lege pagina."""
        instellingen = _scherm_instellingen(db)
        blokken = []

        if instellingen["toon_sponsoren"]:
            sponsoren = db.execute(
                "SELECT * FROM kiosk_sponsoren WHERE actief = 1 ORDER BY volgorde, id"
            ).fetchall()
            slides = [
                {
                    "type": "sponsor",
                    "duur": s["weergave_duur_seconden"],
                    "sjabloon": s["sjabloon"],
                    "titel": s["titel"],
                    "tekst": s["tekst"],
                    "afbeelding": s["afbeelding"],
                }
                for s in sponsoren
            ]
            if slides:
                blokken.append((instellingen["sponsoren_volgorde"], slides))

        if instellingen["toon_club_van_20"]:
            leden = db.execute(
                "SELECT naam FROM club_van_20_leden ORDER BY naam COLLATE NOCASE"
            ).fetchall()
            namen = [r["naam"] for r in leden]
            per_slide = max(1, instellingen["club_van_20_namen_per_slide"])
            groepen = [namen[i : i + per_slide] for i in range(0, len(namen), per_slide)]
            slides = [
                {
                    "type": "club_van_20",
                    "duur": 10,
                    "titel": instellingen["club_van_20_titel"],
                    "namen": groep,
                    "pagina": f"{idx + 1}/{len(groepen)}" if len(groepen) > 1 else None,
                }
                for idx, groep in enumerate(groepen)
            ]
            if slides:
                blokken.append((instellingen["club_van_20_volgorde"], slides))

        if instellingen["toon_wedstrijden"]:
            komende = bereken_komende_thuiswedstrijden(db)
            if komende:
                blokken.append(
                    (
                        instellingen["wedstrijden_volgorde"],
                        [{"type": "wedstrijden", "duur": 10, "dagen": komende}],
                    )
                )

        blokken.sort(key=lambda blok: blok[0])
        return [slide for _, slides in blokken for slide in slides]

    # ---------- Hub ----------

    @app.route("/kiosk")
    def kiosk_hub():
        prijzen_url = url_for("kiosk_prijzen_scherm", _external=True)
        scherm_url = url_for("kiosk_scherm", _external=True)
        return render_template(
            "kiosk_hub.html",
            prijzen_url=prijzen_url,
            scherm_url=scherm_url,
            prijzen_qr_svg=qr.qr_svg(prijzen_url),
            scherm_qr_svg=qr.qr_svg(scherm_url),
        )

    # ---------- Onderdeel 1: Prijzenscherm ----------

    @app.route("/kiosk/prijzen/instellingen", methods=["GET", "POST"])
    def kiosk_prijzen_instellingen():
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            for p in producten:
                getoond = 1 if request.form.get(f"toon_{p['id']}") else 0
                db.execute(
                    "UPDATE producten SET toon_op_kiosk = ? WHERE id = ?", (getoond, p["id"])
                )
            db.commit()
            flash("Prijzenscherm-selectie opgeslagen.", "success")
            return redirect(url_for("kiosk_prijzen_instellingen"))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        return render_template("kiosk_prijzen_instellingen.html", producten=producten)

    @app.route("/kiosk/prijzen")
    def kiosk_prijzen_scherm():
        db = get_db()
        producten = db.execute(
            """SELECT * FROM producten
               WHERE actief = 1 AND toon_op_kiosk = 1
               ORDER BY categorie, naam"""
        ).fetchall()
        per_categorie = {}
        for p in producten:
            per_categorie.setdefault(p["categorie"], []).append(p)
        return render_template(
            "kiosk_prijzen_scherm.html",
            categorieen=sorted(per_categorie.items()),
        )

    # ---------- Onderdeel 2: Sponsoren/leden beheren ----------

    @app.route("/kiosk/sponsoren-leden")
    def kiosk_sponsoren_leden():
        db = get_db()
        sponsoren = db.execute("SELECT * FROM kiosk_sponsoren ORDER BY volgorde, id").fetchall()
        leden = db.execute(
            "SELECT * FROM club_van_20_leden ORDER BY naam COLLATE NOCASE"
        ).fetchall()
        return render_template(
            "kiosk_sponsoren_leden.html",
            sponsoren=sponsoren,
            leden=leden,
            sjabloon_labels=dict(KIOSK_SPONSOR_SJABLONEN),
        )

    def _sponsor_uit_formulier():
        sjabloon = request.form.get("sjabloon", "").strip()
        if sjabloon not in KIOSK_SPONSOR_SJABLOON_SLEUTELS:
            sjabloon = KIOSK_SPONSOR_SJABLONEN[0][0]
        try:
            duur = int(request.form.get("weergave_duur_seconden") or 8)
        except ValueError:
            duur = 8
        try:
            volgorde = int(request.form.get("volgorde") or 0)
        except ValueError:
            volgorde = 0
        return {
            "sjabloon": sjabloon,
            "titel": request.form.get("titel", "").strip() or None,
            "tekst": request.form.get("tekst", "").strip() or None,
            "weergave_duur_seconden": max(2, duur),
            "volgorde": volgorde,
            "actief": 1 if request.form.get("actief") else 0,
        }

    @app.route("/kiosk/sponsoren-leden/sponsoren/nieuw", methods=["GET", "POST"])
    def kiosk_sponsor_nieuw():
        if request.method == "POST":
            db = get_db()
            gegevens = _sponsor_uit_formulier()
            afbeelding = sla_afbeelding_op(request.files.get("afbeelding"), KIOSK_AFBEELDINGEN_MAP)
            db.execute(
                """INSERT INTO kiosk_sponsoren
                   (sjabloon, titel, tekst, afbeelding, weergave_duur_seconden,
                    volgorde, actief, aangemaakt_op)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    gegevens["sjabloon"],
                    gegevens["titel"],
                    gegevens["tekst"],
                    afbeelding,
                    gegevens["weergave_duur_seconden"],
                    gegevens["volgorde"],
                    gegevens["actief"],
                    now_str(),
                ),
            )
            db.commit()
            flash("Sponsor toegevoegd.", "success")
            return redirect(url_for("kiosk_sponsoren_leden"))
        return render_template(
            "kiosk_sponsor_form.html", sponsor=None, sjablonen=KIOSK_SPONSOR_SJABLONEN
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
            db.execute(
                """UPDATE kiosk_sponsoren
                   SET sjabloon = ?, titel = ?, tekst = ?, afbeelding = ?,
                       weergave_duur_seconden = ?, volgorde = ?, actief = ?
                   WHERE id = ?""",
                (
                    gegevens["sjabloon"],
                    gegevens["titel"],
                    gegevens["tekst"],
                    afbeelding,
                    gegevens["weergave_duur_seconden"],
                    gegevens["volgorde"],
                    gegevens["actief"],
                    sponsor_id,
                ),
            )
            db.commit()
            flash("Sponsor bijgewerkt.", "success")
            return redirect(url_for("kiosk_sponsoren_leden"))
        return render_template(
            "kiosk_sponsor_form.html", sponsor=sponsor, sjablonen=KIOSK_SPONSOR_SJABLONEN
        )

    @app.route("/kiosk/sponsoren-leden/sponsoren/<int:sponsor_id>/verwijderen", methods=["POST"])
    def kiosk_sponsor_verwijderen(sponsor_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_sponsoren WHERE id = ?", (sponsor_id,))
        db.commit()
        flash("Sponsor verwijderd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/sponsoren-leden/leden/nieuw", methods=["POST"])
    def kiosk_lid_nieuw():
        naam = request.form.get("naam", "").strip()
        if not naam:
            flash("Vul een naam in.", "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO club_van_20_leden (naam, aangemaakt_op) VALUES (?, ?)",
                (naam, now_str()),
            )
            db.commit()
            flash(f"'{naam}' toegevoegd aan de Club van 20.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/sponsoren-leden/leden/<int:lid_id>/verwijderen", methods=["POST"])
    def kiosk_lid_verwijderen(lid_id):
        db = get_db()
        db.execute("DELETE FROM club_van_20_leden WHERE id = ?", (lid_id,))
        db.commit()
        flash("Lid verwijderd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    # ---------- Onderdeel 3: Kantine scherm ----------

    @app.route("/kiosk/scherm/instellingen", methods=["GET", "POST"])
    def kiosk_scherm_instellingen():
        db = get_db()
        if request.method == "POST":

            def _getal(veld, standaard):
                try:
                    return int(request.form.get(veld) or standaard)
                except ValueError:
                    return standaard

            db.execute(
                """UPDATE kiosk_scherm_instellingen
                   SET toon_sponsoren = ?, sponsoren_volgorde = ?,
                       toon_club_van_20 = ?, club_van_20_volgorde = ?,
                       club_van_20_titel = ?, club_van_20_namen_per_slide = ?,
                       toon_wedstrijden = ?, wedstrijden_volgorde = ?
                   WHERE id = 1""",
                (
                    1 if request.form.get("toon_sponsoren") else 0,
                    _getal("sponsoren_volgorde", 1),
                    1 if request.form.get("toon_club_van_20") else 0,
                    _getal("club_van_20_volgorde", 2),
                    request.form.get("club_van_20_titel", "").strip() or "Club van 20",
                    max(1, _getal("club_van_20_namen_per_slide", 40)),
                    1 if request.form.get("toon_wedstrijden") else 0,
                    _getal("wedstrijden_volgorde", 3),
                ),
            )
            db.commit()
            flash("Instellingen voor het kantine scherm opgeslagen.", "success")
            return redirect(url_for("kiosk_scherm_instellingen"))

        return render_template(
            "kiosk_scherm_instellingen.html", instellingen=_scherm_instellingen(db)
        )

    @app.route("/kiosk/scherm")
    def kiosk_scherm():
        db = get_db()
        return render_template("kiosk_scherm.html", slides=_bouw_slides(db))
