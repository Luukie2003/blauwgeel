from flask import flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import (
    KASSA_COUPURES,
    bereken_kassa_coupure_bedrag,
    bereken_kluis_stand,
    bereken_kluis_verschil_trend,
    kassa_telling_is_zelf_goedgekeurd,
    now_str,
)


def register_routes(app):

    @app.route("/kluis/tellen", methods=["GET", "POST"])
    def kluis_tellen():
        db = get_db()
        if request.method == "POST":
            opmerking = request.form.get("opmerking", "").strip()

            aantallen, geteld_bedrag = bereken_kassa_coupure_bedrag(request.form)
            kluis_stand = bereken_kluis_stand(db)
            # Geen contante omzet zoals bij de kassalade: de kluis heeft geen
            # eigen inkomsten, het verwachte bedrag is gewoon de bekende stand.
            verwacht_bedrag = kluis_stand["stand"]
            verschil = round(geteld_bedrag - verwacht_bedrag, 2)

            cur = db.execute(
                """INSERT INTO kluis_tellingen
                   (datum, naam, gebruiker_id, verwacht_bedrag, geteld_bedrag,
                    verschil, aantal_50, aantal_20, aantal_10, aantal_5,
                    aantal_2, aantal_1, aantal_050, aantal_020, aantal_010,
                    aantal_005, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now_str(),
                    session.get("gebruiker_naam"),
                    session.get("gebruiker_id"),
                    verwacht_bedrag,
                    geteld_bedrag,
                    verschil,
                    aantallen["aantal_50"],
                    aantallen["aantal_20"],
                    aantallen["aantal_10"],
                    aantallen["aantal_5"],
                    aantallen["aantal_2"],
                    aantallen["aantal_1"],
                    aantallen["aantal_050"],
                    aantallen["aantal_020"],
                    aantallen["aantal_010"],
                    aantallen["aantal_005"],
                    opmerking,
                ),
            )
            # Nog niet in instellingen.kluis_stand verrekenen -- dat gebeurt
            # pas bij het afsluiten, zelfde patroon als kassa_tellen.
            db.commit()
            flash(
                "Kluistelling opgeslagen als concept. Controleer de aantallen en sluit "
                "'m af zodra je klaar bent.",
                "success",
            )
            return redirect(url_for("kluis_telling_detail", telling_id=cur.lastrowid))

        kluis_stand = bereken_kluis_stand(db)
        return render_template(
            "kluis_tellen.html", kluis_stand=kluis_stand, coupures=KASSA_COUPURES
        )

    @app.route("/kluis/tellingen/<int:telling_id>")
    def kluis_telling_detail(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kluis_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kluistelling niet gevonden.", "error")
            return redirect(url_for("kluis_geschiedenis"))
        kluis_stand = bereken_kluis_stand(db)
        return render_template(
            "kluis_telling_detail.html",
            telling=telling,
            coupures=KASSA_COUPURES,
            kluis_stand=kluis_stand,
            zelf_goedgekeurd=kassa_telling_is_zelf_goedgekeurd(telling),
        )

    @app.route("/kluis/tellingen/<int:telling_id>/heropenen", methods=["POST"])
    def kluis_telling_heropenen(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kluis_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kluistelling niet gevonden.", "error")
            return redirect(url_for("kluis_geschiedenis"))
        if not telling["afgesloten"]:
            flash("Deze kluistelling staat al open.", "error")
            return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

        # Zelfde veiligheidsgrens als kassa_telling_heropenen: alleen
        # mogelijk zolang er sindsdien niets anders aan de kluisstand heeft
        # gezeten (geen storting, opname, kassalade-overboeking of nieuwere
        # afgesloten telling).
        kluis_stand = bereken_kluis_stand(db)
        if abs(kluis_stand["stand"] - telling["geteld_bedrag"]) > 0.001:
            flash(
                "Heropenen kan niet meer: er zijn hierna al andere kluis-acties geweest "
                "(een storting, opname, overboeking vanuit de kassalade of nieuwere "
                "afgesloten telling).",
                "error",
            )
            return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

        db.execute(
            """UPDATE kluis_tellingen
               SET afgesloten = 0, goedgekeurd_door_id = NULL, goedgekeurd_door = NULL,
                   goedgekeurd_op = NULL, goedkeuring_opmerking = NULL
               WHERE id = ?""",
            (telling_id,),
        )
        db.execute(
            "UPDATE instellingen SET kluis_stand = ? WHERE id = 1",
            (telling["verwacht_bedrag"],),
        )
        db.commit()
        flash("Kluistelling heropend. Je kunt 'm weer aanpassen.", "success")
        return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

    @app.route("/kluis/tellingen/<int:telling_id>/telling-corrigeren", methods=["GET", "POST"])
    def kluis_telling_coupures_corrigeren(telling_id):
        """Corrigeert het fysiek getelde bedrag (de coupure-aantallen) op een
        al goedgekeurde kluistelling -- zelfde patroon als
        kassa_telling_coupures_corrigeren. Raakt de kluisstand alleen als
        deze telling nog steeds de meest recente stand-bepalende
        gebeurtenis is."""
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kluis_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kluistelling niet gevonden.", "error")
            return redirect(url_for("kluis_geschiedenis"))
        if not telling["afgesloten"]:
            flash(
                "Deze kluistelling staat nog open als concept — gebruik "
                "'Bewerken' om de aantallen aan te passen.",
                "error",
            )
            return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

        if request.method == "POST":
            aantallen, nieuw_geteld_bedrag = bereken_kassa_coupure_bedrag(request.form)
            if abs(nieuw_geteld_bedrag - telling["geteld_bedrag"]) < 0.001:
                flash("Geen wijziging: dit is al het getelde bedrag.", "error")
                return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

            oud_geteld_bedrag = telling["geteld_bedrag"]
            nieuw_verschil = round(nieuw_geteld_bedrag - telling["verwacht_bedrag"], 2)
            opmerking = request.form.get("correctie_opmerking", "").strip()

            db.execute(
                """UPDATE kluis_tellingen
                   SET aantal_50 = ?, aantal_20 = ?, aantal_10 = ?, aantal_5 = ?,
                       aantal_2 = ?, aantal_1 = ?, aantal_050 = ?, aantal_020 = ?,
                       aantal_010 = ?, aantal_005 = ?, geteld_bedrag = ?, verschil = ?,
                       geteld_bedrag_voor_correctie = ?, geteld_bedrag_gecorrigeerd_door_id = ?,
                       geteld_bedrag_gecorrigeerd_door = ?, geteld_bedrag_gecorrigeerd_op = ?,
                       geteld_bedrag_correctie_opmerking = ?
                   WHERE id = ?""",
                (
                    aantallen["aantal_50"],
                    aantallen["aantal_20"],
                    aantallen["aantal_10"],
                    aantallen["aantal_5"],
                    aantallen["aantal_2"],
                    aantallen["aantal_1"],
                    aantallen["aantal_050"],
                    aantallen["aantal_020"],
                    aantallen["aantal_010"],
                    aantallen["aantal_005"],
                    nieuw_geteld_bedrag,
                    nieuw_verschil,
                    oud_geteld_bedrag,
                    session.get("gebruiker_id"),
                    session.get("gebruiker_naam"),
                    now_str(),
                    opmerking or None,
                    telling_id,
                ),
            )

            kluis_stand = bereken_kluis_stand(db)
            kluis_stand_aangepast = abs(kluis_stand["stand"] - oud_geteld_bedrag) < 0.001
            if kluis_stand_aangepast:
                db.execute(
                    "UPDATE instellingen SET kluis_stand = ? WHERE id = 1",
                    (nieuw_geteld_bedrag,),
                )
            db.commit()

            melding = (
                f"Getelde bedrag gecorrigeerd van € {oud_geteld_bedrag:.2f} naar "
                f"€ {nieuw_geteld_bedrag:.2f}."
            )
            melding += (
                " De kluisstand is meteen aangepast."
                if kluis_stand_aangepast
                else " De kluisstand is niet aangepast, want er is inmiddels al een "
                "latere kluis-actie geweest die zijn eigen stand heeft vastgesteld."
            )
            flash(melding, "success")
            return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

        return render_template(
            "kluis_telling_coupures_corrigeren.html", telling=telling, coupures=KASSA_COUPURES
        )

    @app.route("/kluis/tellingen/<int:telling_id>/bewerken", methods=["GET", "POST"])
    def kluis_telling_bewerken(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kluis_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kluistelling niet gevonden.", "error")
            return redirect(url_for("kluis_geschiedenis"))
        if telling["afgesloten"]:
            flash("Deze kluistelling is al afgesloten en kan niet meer aangepast worden.", "error")
            return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

        if request.method == "POST":
            opmerking = request.form.get("opmerking", "").strip()

            aantallen, geteld_bedrag = bereken_kassa_coupure_bedrag(request.form)
            # Verwacht bedrag o.b.v. de huidige (afgesloten) stand -- deze
            # telling zelf telt daar nog niet in mee zolang hij open staat.
            kluis_stand = bereken_kluis_stand(db)
            verwacht_bedrag = kluis_stand["stand"]
            verschil = round(geteld_bedrag - verwacht_bedrag, 2)

            db.execute(
                """UPDATE kluis_tellingen
                   SET verwacht_bedrag = ?, geteld_bedrag = ?, verschil = ?,
                       aantal_50 = ?, aantal_20 = ?, aantal_10 = ?, aantal_5 = ?,
                       aantal_2 = ?, aantal_1 = ?, aantal_050 = ?, aantal_020 = ?,
                       aantal_010 = ?, aantal_005 = ?, opmerking = ?
                   WHERE id = ?""",
                (
                    verwacht_bedrag,
                    geteld_bedrag,
                    verschil,
                    aantallen["aantal_50"],
                    aantallen["aantal_20"],
                    aantallen["aantal_10"],
                    aantallen["aantal_5"],
                    aantallen["aantal_2"],
                    aantallen["aantal_1"],
                    aantallen["aantal_050"],
                    aantallen["aantal_020"],
                    aantallen["aantal_010"],
                    aantallen["aantal_005"],
                    opmerking,
                    telling_id,
                ),
            )
            db.commit()
            flash("Kluistelling bijgewerkt.", "success")
            return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

        kluis_stand = bereken_kluis_stand(db)
        return render_template(
            "kluis_telling_bewerken.html",
            telling=telling,
            coupures=KASSA_COUPURES,
            kluis_stand=kluis_stand,
        )

    @app.route("/kluis/tellingen/<int:telling_id>/goedkeuren", methods=["POST"])
    def kluis_telling_goedkeuren(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kluis_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kluistelling niet gevonden.", "error")
            return redirect(url_for("kluis_geschiedenis"))
        if telling["afgesloten"]:
            flash("Deze kluistelling was al goedgekeurd.", "error")
            return redirect(url_for("kluis_telling_detail", telling_id=telling_id))
        goedkeuring_opmerking = request.form.get("goedkeuring_opmerking", "").strip()
        db.execute(
            """UPDATE kluis_tellingen
               SET afgesloten = 1, goedgekeurd_door_id = ?, goedgekeurd_door = ?,
                   goedgekeurd_op = ?, goedkeuring_opmerking = ?
               WHERE id = ?""",
            (
                session.get("gebruiker_id"),
                session.get("gebruiker_naam"),
                now_str(),
                goedkeuring_opmerking or None,
                telling_id,
            ),
        )
        db.execute(
            "UPDATE instellingen SET kluis_stand = ? WHERE id = 1", (telling["geteld_bedrag"],)
        )
        db.commit()
        if telling["gebruiker_id"] is not None and telling["gebruiker_id"] == session.get("gebruiker_id"):
            flash("Kluistelling goedgekeurd. Je hebt je eigen telling goedgekeurd.", "success")
        else:
            flash("Kluistelling goedgekeurd.", "success")
        return redirect(url_for("kluis_telling_detail", telling_id=telling_id))

    @app.route("/kluis/geschiedenis")
    def kluis_geschiedenis():
        db = get_db()
        kluis_stand = bereken_kluis_stand(db)
        verschil_trend = bereken_kluis_verschil_trend(db)

        tellingen = db.execute(
            "SELECT * FROM kluis_tellingen ORDER BY datum DESC, id DESC LIMIT 200"
        ).fetchall()
        mutaties = db.execute(
            "SELECT * FROM kluis_mutaties ORDER BY datum DESC, id DESC LIMIT 200"
        ).fetchall()
        # De kassalade<->kluis-overboekingen (afdracht/toevoeging) staan in
        # kassa_mutaties en worden hier alleen ter info getoond -- boeken en
        # corrigeren blijft bij Kassa geschiedenis, waar ze ook ontstaan.
        overboekingen = db.execute(
            "SELECT * FROM kassa_mutaties ORDER BY datum DESC, id DESC LIMIT 200"
        ).fetchall()

        tijdlijn = [{"soort": "telling", "datum": t["datum"], "item": t} for t in tellingen]
        tijdlijn += [{"soort": m["type"], "datum": m["datum"], "item": m} for m in mutaties]
        tijdlijn += [
            {"soort": "overboeking", "richting": m["type"], "datum": m["datum"], "item": m}
            for m in overboekingen
        ]
        tijdlijn.sort(key=lambda r: r["datum"], reverse=True)

        return render_template(
            "kluis_geschiedenis.html",
            kluis_stand=kluis_stand,
            verschil_trend=verschil_trend,
            tijdlijn=tijdlijn,
        )

    @app.route("/kluis/mutatie/nieuw", methods=["GET", "POST"])
    def kluis_mutatie_nieuw():
        db = get_db()
        if request.method == "POST":
            type_ = request.form.get("type", "").strip()
            if type_ not in ("storting", "opname"):
                flash("Ongeldig type.", "error")
                return redirect(url_for("kluis_mutatie_nieuw"))
            try:
                bedrag = round(float(request.form.get("bedrag", "0").replace(",", ".")), 2)
            except ValueError:
                bedrag = 0.0
            if bedrag <= 0:
                flash("Vul een bedrag groter dan 0 in.", "error")
                return redirect(url_for("kluis_mutatie_nieuw"))
            ontvanger = request.form.get("ontvanger", "").strip()
            opmerking = request.form.get("opmerking", "").strip()

            db.execute(
                """INSERT INTO kluis_mutaties
                   (type, bedrag, datum, naam, gebruiker_id, ontvanger, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    type_,
                    bedrag,
                    now_str(),
                    session.get("gebruiker_naam"),
                    session.get("gebruiker_id"),
                    ontvanger,
                    opmerking,
                ),
            )
            delta = bedrag if type_ == "storting" else -bedrag
            db.execute(
                "UPDATE instellingen SET kluis_stand = kluis_stand + ? WHERE id = 1",
                (delta,),
            )
            db.commit()
            werkwoord = "Storting" if type_ == "storting" else "Opname"
            flash(f"{werkwoord} van € {bedrag:.2f} geboekt.", "success")
            return redirect(url_for("kluis_geschiedenis"))

        kluis_stand = bereken_kluis_stand(db)
        return render_template("kluis_mutatie_nieuw.html", kluis_stand=kluis_stand)

    @app.route("/kluis/mutaties/<int:mutatie_id>/corrigeren", methods=["POST"])
    def kluis_mutatie_corrigeren(mutatie_id):
        """Corrigeert het bedrag van een al geboekte storting/opname, bijv.
        een tikfout -- zelfde patroon als kassa_mutatie_corrigeren: de
        kluisstand wordt alleen aangepast als er sindsdien nog geen
        kluistelling is afgesloten."""
        db = get_db()
        mutatie = db.execute(
            "SELECT * FROM kluis_mutaties WHERE id = ?", (mutatie_id,)
        ).fetchone()
        if mutatie is None:
            flash("Kluismutatie niet gevonden.", "error")
            return redirect(url_for("kluis_geschiedenis"))

        try:
            nieuw_bedrag = round(
                float(request.form.get("bedrag", "0").replace(",", ".")), 2
            )
        except ValueError:
            flash("Ongeldig bedrag.", "error")
            return redirect(url_for("kluis_geschiedenis"))
        if nieuw_bedrag <= 0:
            flash("Vul een bedrag groter dan 0 in.", "error")
            return redirect(url_for("kluis_geschiedenis"))
        if abs(nieuw_bedrag - mutatie["bedrag"]) < 0.001:
            flash("Geen wijziging: dit is al het ingevulde bedrag.", "error")
            return redirect(url_for("kluis_geschiedenis"))

        oud_bedrag = mutatie["bedrag"]
        db.execute(
            """UPDATE kluis_mutaties
               SET bedrag = ?, bedrag_voor_correctie = ?, gecorrigeerd_door_id = ?,
                   gecorrigeerd_door = ?, gecorrigeerd_op = ?
               WHERE id = ?""",
            (
                nieuw_bedrag,
                oud_bedrag,
                session.get("gebruiker_id"),
                session.get("gebruiker_naam"),
                now_str(),
                mutatie_id,
            ),
        )

        latere_telling = db.execute(
            "SELECT COUNT(*) AS n FROM kluis_tellingen WHERE afgesloten = 1 AND datum > ?",
            (mutatie["datum"],),
        ).fetchone()["n"]
        kluis_stand_aangepast = latere_telling == 0
        if kluis_stand_aangepast:
            delta = nieuw_bedrag - oud_bedrag
            if mutatie["type"] == "opname":
                delta = -delta
            db.execute(
                "UPDATE instellingen SET kluis_stand = kluis_stand + ? WHERE id = 1",
                (delta,),
            )
        db.commit()

        werkwoord = "Storting" if mutatie["type"] == "storting" else "Opname"
        melding = f"{werkwoord} gecorrigeerd van € {oud_bedrag:.2f} naar € {nieuw_bedrag:.2f}."
        melding += (
            " De kluisstand is meteen aangepast."
            if kluis_stand_aangepast
            else " De kluisstand is niet aangepast, want er is inmiddels al een "
            "latere kluistelling afgesloten die zijn eigen stand heeft vastgesteld."
        )
        flash(melding, "success")
        return redirect(url_for("kluis_geschiedenis"))
