from flask import Response, flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import (
    KASSA_COUPURES,
    bereken_kassa_coupure_bedrag,
    bereken_kassa_verschil_trend,
    bereken_kassalade_stand,
    bereken_kluis_stand,
    kassa_telling_is_zelf_goedgekeurd,
    now_str,
)
from pdf import kassa_pdf


def register_routes(app):

    @app.route("/kassa/tellen", methods=["GET", "POST"])
    def kassa_tellen():
        db = get_db()
        if request.method == "POST":
            try:
                contante_omzet = round(
                    float(request.form.get("contante_omzet", "0").replace(",", ".")), 2
                )
            except ValueError:
                contante_omzet = 0.0
            opmerking = request.form.get("opmerking", "").strip()

            aantallen, geteld_bedrag = bereken_kassa_coupure_bedrag(request.form)
            kassalade_stand = bereken_kassalade_stand(db)
            verwacht_bedrag = round(kassalade_stand["stand"] + contante_omzet, 2)
            verschil = round(geteld_bedrag - verwacht_bedrag, 2)

            cur = db.execute(
                """INSERT INTO kassa_tellingen
                   (datum, naam, gebruiker_id, verwacht_bedrag, contante_omzet,
                    geteld_bedrag, verschil, aantal_50, aantal_20, aantal_10,
                    aantal_5, aantal_2, aantal_1, aantal_050, aantal_020,
                    aantal_010, aantal_005, opmerking)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now_str(),
                    session.get("gebruiker_naam"),
                    session.get("gebruiker_id"),
                    verwacht_bedrag,
                    contante_omzet,
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
            # Nog niet in instellingen.kassalade_stand verrekenen -- dat gebeurt
            # pas bij het afsluiten, zodat de telling tot die tijd nog
            # aangepast kan worden zonder de lopende stand te verstoren.
            db.commit()
            flash(
                "Kassatelling opgeslagen als concept. Controleer de aantallen en sluit "
                "'m af zodra je klaar bent.",
                "success",
            )
            return redirect(url_for("kassa_telling_detail", telling_id=cur.lastrowid))

        kassalade_stand = bereken_kassalade_stand(db)
        return render_template(
            "kassa_tellen.html", kassalade_stand=kassalade_stand, coupures=KASSA_COUPURES
        )

    @app.route("/kassa/tellingen/<int:telling_id>")
    def kassa_telling_detail(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        kassalade_stand = bereken_kassalade_stand(db)
        return render_template(
            "kassa_telling_detail.html",
            telling=telling,
            coupures=KASSA_COUPURES,
            kassalade_stand=kassalade_stand,
            zelf_goedgekeurd=kassa_telling_is_zelf_goedgekeurd(telling),
        )

    @app.route("/kassa/tellingen/<int:telling_id>/heropenen", methods=["POST"])
    def kassa_telling_heropenen(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if not telling["afgesloten"]:
            flash("Deze kassatelling staat al open.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        # Alleen veilig als er sindsdien niets anders aan de kassa-stand
        # heeft gezeten (geen nieuwere telling afgesloten, geen afdracht of
        # toevoeging geboekt) -- anders zou heropenen die latere acties
        # ongedaan maken zonder dat de gebruiker dat doorheeft.
        kassalade_stand = bereken_kassalade_stand(db)
        if abs(kassalade_stand["stand"] - telling["geteld_bedrag"]) > 0.001:
            flash(
                "Heropenen kan niet meer: er zijn hierna al andere kassa-acties geweest "
                "(een afdracht, toevoeging of nieuwere afgesloten telling).",
                "error",
            )
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        db.execute(
            """UPDATE kassa_tellingen
               SET afgesloten = 0, goedgekeurd_door_id = NULL, goedgekeurd_door = NULL,
                   goedgekeurd_op = NULL, goedkeuring_opmerking = NULL
               WHERE id = ?""",
            (telling_id,),
        )
        db.execute(
            "UPDATE instellingen SET kassalade_stand = ? WHERE id = 1",
            (round(telling["verwacht_bedrag"] - telling["contante_omzet"], 2),),
        )
        db.commit()
        flash("Kassatelling heropend. Je kunt 'm weer aanpassen.", "success")
        return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

    @app.route("/kassa/tellingen/<int:telling_id>/omzet-corrigeren", methods=["POST"])
    def kassa_telling_omzet_corrigeren(telling_id):
        """Corrigeert alleen de contante omzet (bijv. geld dat per ongeluk als
        contant i.p.v. pin is aangeslagen) op een al goedgekeurde telling --
        ook als er sindsdien allang andere kassa-acties zijn geweest. Dat kan
        hier wel veilig, anders dan bij heropenen: de kassastand wordt bij
        goedkeuren altijd gelijkgezet aan het fysiek getelde bedrag, nooit aan
        dit cijfer, dus deze correctie raakt de kassastand of andere
        tellingen niet -- alleen het verwachte bedrag en verschil van déze
        telling worden opnieuw berekend."""
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if not telling["afgesloten"]:
            flash(
                "Deze kassatelling staat nog open als concept — gebruik "
                "'Bewerken' om de contante omzet aan te passen.",
                "error",
            )
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        try:
            nieuwe_omzet = round(
                float(request.form.get("contante_omzet", "0").replace(",", ".")), 2
            )
        except ValueError:
            flash("Ongeldig bedrag.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        if abs(nieuwe_omzet - telling["contante_omzet"]) < 0.001:
            flash("Geen wijziging: dit is al de ingevulde contante omzet.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        stand_voor_deze_telling = round(telling["verwacht_bedrag"] - telling["contante_omzet"], 2)
        nieuw_verwacht_bedrag = round(stand_voor_deze_telling + nieuwe_omzet, 2)
        nieuw_verschil = round(telling["geteld_bedrag"] - nieuw_verwacht_bedrag, 2)
        opmerking = request.form.get("correctie_opmerking", "").strip()

        db.execute(
            """UPDATE kassa_tellingen
               SET contante_omzet = ?, verwacht_bedrag = ?, verschil = ?,
                   contante_omzet_voor_correctie = ?, contante_omzet_gecorrigeerd_door_id = ?,
                   contante_omzet_gecorrigeerd_door = ?, contante_omzet_gecorrigeerd_op = ?,
                   contante_omzet_correctie_opmerking = ?
               WHERE id = ?""",
            (
                nieuwe_omzet,
                nieuw_verwacht_bedrag,
                nieuw_verschil,
                telling["contante_omzet"],
                session.get("gebruiker_id"),
                session.get("gebruiker_naam"),
                now_str(),
                opmerking or None,
                telling_id,
            ),
        )
        db.commit()
        flash(
            f"Contante omzet gecorrigeerd van € {telling['contante_omzet']:.2f} naar "
            f"€ {nieuwe_omzet:.2f}. De kassastand en andere tellingen zijn niet aangepast.",
            "success",
        )
        return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

    @app.route("/kassa/tellingen/<int:telling_id>/telling-corrigeren", methods=["GET", "POST"])
    def kassa_telling_coupures_corrigeren(telling_id):
        """Corrigeert het fysiek getelde bedrag (de coupure-aantallen) op een
        al goedgekeurde telling -- bijv. een miswelging die pas veel later
        opvalt. Anders dan de contante-omzet-correctie kan dit wél de
        kassastand raken (die wordt bij goedkeuren gelijkgezet aan precies
        dit bedrag), dus die wordt alleen meegenomen als deze telling nog
        steeds de meest recente stand-bepalende gebeurtenis is -- exact
        dezelfde voorwaarde als bij heropenen. Is dat niet meer zo (er is
        alweer een latere telling geweest die zelf een eigen, onafhankelijke
        fysieke telling was), dan wordt alleen déze telling zelf gecorrigeerd
        en blijft de kassastand -- terecht -- ongemoeid."""
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if not telling["afgesloten"]:
            flash(
                "Deze kassatelling staat nog open als concept — gebruik "
                "'Bewerken' om de aantallen aan te passen.",
                "error",
            )
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        if request.method == "POST":
            aantallen, nieuw_geteld_bedrag = bereken_kassa_coupure_bedrag(request.form)
            if abs(nieuw_geteld_bedrag - telling["geteld_bedrag"]) < 0.001:
                flash("Geen wijziging: dit is al het getelde bedrag.", "error")
                return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

            oud_geteld_bedrag = telling["geteld_bedrag"]
            nieuw_verschil = round(nieuw_geteld_bedrag - telling["verwacht_bedrag"], 2)
            opmerking = request.form.get("correctie_opmerking", "").strip()

            db.execute(
                """UPDATE kassa_tellingen
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

            kassalade_stand = bereken_kassalade_stand(db)
            kassalade_stand_aangepast = abs(kassalade_stand["stand"] - oud_geteld_bedrag) < 0.001
            if kassalade_stand_aangepast:
                db.execute(
                    "UPDATE instellingen SET kassalade_stand = ? WHERE id = 1",
                    (nieuw_geteld_bedrag,),
                )
            db.commit()

            melding = (
                f"Getelde bedrag gecorrigeerd van € {oud_geteld_bedrag:.2f} naar "
                f"€ {nieuw_geteld_bedrag:.2f}."
            )
            melding += (
                " De kassastand is meteen aangepast."
                if kassalade_stand_aangepast
                else " De kassastand is niet aangepast, want er is inmiddels al een "
                "latere kassa-actie geweest die zijn eigen stand heeft vastgesteld."
            )
            flash(melding, "success")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        return render_template(
            "kassa_telling_coupures_corrigeren.html", telling=telling, coupures=KASSA_COUPURES
        )

    @app.route("/kassa/tellingen/<int:telling_id>/bewerken", methods=["GET", "POST"])
    def kassa_telling_bewerken(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if telling["afgesloten"]:
            flash("Deze kassatelling is al afgesloten en kan niet meer aangepast worden.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        if request.method == "POST":
            try:
                contante_omzet = round(
                    float(request.form.get("contante_omzet", "0").replace(",", ".")), 2
                )
            except ValueError:
                contante_omzet = 0.0
            opmerking = request.form.get("opmerking", "").strip()

            aantallen, geteld_bedrag = bereken_kassa_coupure_bedrag(request.form)
            # Verwacht bedrag o.b.v. de huidige (afgesloten) stand -- deze
            # telling zelf telt daar nog niet in mee zolang hij open staat.
            kassalade_stand = bereken_kassalade_stand(db)
            verwacht_bedrag = round(kassalade_stand["stand"] + contante_omzet, 2)
            verschil = round(geteld_bedrag - verwacht_bedrag, 2)

            db.execute(
                """UPDATE kassa_tellingen
                   SET verwacht_bedrag = ?, contante_omzet = ?, geteld_bedrag = ?,
                       verschil = ?, aantal_50 = ?, aantal_20 = ?, aantal_10 = ?,
                       aantal_5 = ?, aantal_2 = ?, aantal_1 = ?, aantal_050 = ?,
                       aantal_020 = ?, aantal_010 = ?, aantal_005 = ?, opmerking = ?
                   WHERE id = ?""",
                (
                    verwacht_bedrag,
                    contante_omzet,
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
            flash("Kassatelling bijgewerkt.", "success")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

        kassalade_stand = bereken_kassalade_stand(db)
        return render_template(
            "kassa_telling_bewerken.html",
            telling=telling,
            coupures=KASSA_COUPURES,
            kassalade_stand=kassalade_stand,
        )

    @app.route("/kassa/tellingen/<int:telling_id>/goedkeuren", methods=["POST"])
    def kassa_telling_goedkeuren(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if telling["afgesloten"]:
            flash("Deze kassatelling was al goedgekeurd.", "error")
            return redirect(url_for("kassa_telling_detail", telling_id=telling_id))
        goedkeuring_opmerking = request.form.get("goedkeuring_opmerking", "").strip()
        db.execute(
            """UPDATE kassa_tellingen
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
            "UPDATE instellingen SET kassalade_stand = ? WHERE id = 1", (telling["geteld_bedrag"],)
        )
        db.commit()
        if telling["gebruiker_id"] is not None and telling["gebruiker_id"] == session.get("gebruiker_id"):
            flash("Kassatelling goedgekeurd. Je hebt je eigen telling goedgekeurd.", "success")
        else:
            flash("Kassatelling goedgekeurd.", "success")
        return redirect(url_for("kassa_telling_detail", telling_id=telling_id))

    @app.route("/kassa/tellingen/<int:telling_id>/pdf")
    def kassa_telling_pdf(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Kassatelling niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        pdf_bytes = kassa_pdf(telling, KASSA_COUPURES)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=kassatelling-{telling_id}.pdf"
            },
        )

    @app.route("/kassa/geschiedenis")
    def kassa_geschiedenis():
        db = get_db()
        kassalade_stand = bereken_kassalade_stand(db)
        kluis_stand = bereken_kluis_stand(db)
        verschil_trend = bereken_kassa_verschil_trend(db)

        # Zelfde begrenzing als het gewone mutatie-overzicht (geschiedenis()):
        # zonder LIMIT blijft dit onbeperkt meegroeien met elke kassatelling
        # en elke afdracht/toevoeging ooit geboekt.
        tellingen = db.execute(
            "SELECT * FROM kassa_tellingen ORDER BY datum DESC, id DESC LIMIT 200"
        ).fetchall()
        mutaties = db.execute(
            "SELECT * FROM kassa_mutaties ORDER BY datum DESC, id DESC LIMIT 200"
        ).fetchall()

        tijdlijn = [{"soort": "telling", "datum": t["datum"], "item": t} for t in tellingen]
        tijdlijn += [{"soort": m["type"], "datum": m["datum"], "item": m} for m in mutaties]
        tijdlijn.sort(key=lambda r: r["datum"], reverse=True)

        return render_template(
            "kassa_geschiedenis.html",
            kassalade_stand=kassalade_stand,
            kluis_stand=kluis_stand,
            verschil_trend=verschil_trend,
            tijdlijn=tijdlijn
        )

    @app.route("/kassa/mutatie/nieuw", methods=["GET", "POST"])
    def kassa_mutatie_nieuw():
        db = get_db()
        if request.method == "POST":
            type_ = request.form.get("type", "").strip()
            if type_ not in ("afdracht", "toevoeging"):
                flash("Ongeldig type.", "error")
                return redirect(url_for("kassa_mutatie_nieuw"))
            try:
                bedrag = round(float(request.form.get("bedrag", "0").replace(",", ".")), 2)
            except ValueError:
                bedrag = 0.0
            if bedrag <= 0:
                flash("Vul een bedrag groter dan 0 in.", "error")
                return redirect(url_for("kassa_mutatie_nieuw"))
            ontvanger = request.form.get("ontvanger", "").strip()
            opmerking = request.form.get("opmerking", "").strip()

            db.execute(
                """INSERT INTO kassa_mutaties
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
            # Een afdracht/toevoeging is een gesloten overboeking tussen
            # kassalade en kluis: delta is al +bedrag voor toevoeging (naar
            # de kassalade) / -bedrag voor afdracht (uit de kassalade), dus
            # de kluis krijgt precies het spiegelbeeld.
            delta = bedrag if type_ == "toevoeging" else -bedrag
            db.execute(
                "UPDATE instellingen SET kassalade_stand = kassalade_stand + ? WHERE id = 1",
                (delta,),
            )
            db.execute(
                "UPDATE instellingen SET kluis_stand = kluis_stand - ? WHERE id = 1",
                (delta,),
            )
            db.commit()
            werkwoord = "Afdracht" if type_ == "afdracht" else "Toevoeging"
            flash(f"{werkwoord} van € {bedrag:.2f} geboekt.", "success")
            return redirect(url_for("kassa_geschiedenis"))

        kassalade_stand = bereken_kassalade_stand(db)
        kluis_stand = bereken_kluis_stand(db)
        return render_template(
            "kassa_mutatie_nieuw.html", kassalade_stand=kassalade_stand, kluis_stand=kluis_stand
        )

    @app.route("/kassa/mutaties/<int:mutatie_id>/corrigeren", methods=["POST"])
    def kassa_mutatie_corrigeren(mutatie_id):
        """Corrigeert het bedrag van een al geboekte afdracht/toevoeging,
        bijv. een tikfout. In tegenstelling tot de tellingen-correcties werkt
        een mutatie via een lopend saldo (elke mutatie telt rechtstreeks bij
        de kassalade- en kluisstand op of af), dus een foutief bedrag telt
        gewoon mee totdat een latere afgesloten telling de stand weer op een
        eigen, onafhankelijke fysieke telling zet. Daarom wordt elke stand
        hier alleen aangepast als er voor díe pot sindsdien nog geen telling
        is afgesloten -- staat de fout al 'achter' zo'n telling, dan is 'ie
        daar al vanzelf uit verdwenen en zou corrigeren die juist weer fout
        maken. Kassalade en kluis worden onafhankelijk van elkaar beoordeeld:
        het is heel normaal dat de ene pot inmiddels wel opnieuw geteld is en
        de andere nog niet."""
        db = get_db()
        mutatie = db.execute(
            "SELECT * FROM kassa_mutaties WHERE id = ?", (mutatie_id,)
        ).fetchone()
        if mutatie is None:
            flash("Kassamutatie niet gevonden.", "error")
            return redirect(url_for("kassa_geschiedenis"))

        try:
            nieuw_bedrag = round(
                float(request.form.get("bedrag", "0").replace(",", ".")), 2
            )
        except ValueError:
            flash("Ongeldig bedrag.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if nieuw_bedrag <= 0:
            flash("Vul een bedrag groter dan 0 in.", "error")
            return redirect(url_for("kassa_geschiedenis"))
        if abs(nieuw_bedrag - mutatie["bedrag"]) < 0.001:
            flash("Geen wijziging: dit is al het ingevulde bedrag.", "error")
            return redirect(url_for("kassa_geschiedenis"))

        oud_bedrag = mutatie["bedrag"]
        db.execute(
            """UPDATE kassa_mutaties
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

        # Kassalade-delta: +bedrag voor toevoeging, -bedrag voor afdracht
        # (zelfde teken als bij het aanmaken). De kluis-delta is telkens het
        # spiegelbeeld daarvan.
        kassalade_delta = nieuw_bedrag - oud_bedrag
        if mutatie["type"] == "afdracht":
            kassalade_delta = -kassalade_delta

        latere_kassalade_telling = db.execute(
            "SELECT COUNT(*) AS n FROM kassa_tellingen WHERE afgesloten = 1 AND datum > ?",
            (mutatie["datum"],),
        ).fetchone()["n"]
        kassalade_stand_aangepast = latere_kassalade_telling == 0
        if kassalade_stand_aangepast:
            db.execute(
                "UPDATE instellingen SET kassalade_stand = kassalade_stand + ? WHERE id = 1",
                (kassalade_delta,),
            )

        latere_kluis_telling = db.execute(
            "SELECT COUNT(*) AS n FROM kluis_tellingen WHERE afgesloten = 1 AND datum > ?",
            (mutatie["datum"],),
        ).fetchone()["n"]
        kluis_stand_aangepast = latere_kluis_telling == 0
        if kluis_stand_aangepast:
            db.execute(
                "UPDATE instellingen SET kluis_stand = kluis_stand - ? WHERE id = 1",
                (kassalade_delta,),
            )
        db.commit()

        werkwoord = "Afdracht" if mutatie["type"] == "afdracht" else "Toevoeging"
        melding = f"{werkwoord} gecorrigeerd van € {oud_bedrag:.2f} naar € {nieuw_bedrag:.2f}."
        if kassalade_stand_aangepast and kluis_stand_aangepast:
            melding += " De kassalade- en kluisstand zijn meteen aangepast."
        elif kassalade_stand_aangepast:
            melding += (
                " De kassaladestand is meteen aangepast, maar de kluisstand niet: "
                "daar is inmiddels al een latere telling afgesloten die zijn eigen "
                "stand heeft vastgesteld."
            )
        elif kluis_stand_aangepast:
            melding += (
                " De kluisstand is meteen aangepast, maar de kassaladestand niet: "
                "daar is inmiddels al een latere telling afgesloten die zijn eigen "
                "stand heeft vastgesteld."
            )
        else:
            melding += (
                " Geen van beide standen is aangepast, want er is inmiddels al een "
                "latere telling afgesloten die zijn eigen stand heeft vastgesteld."
            )
        flash(melding, "success")
        return redirect(url_for("kassa_geschiedenis"))

