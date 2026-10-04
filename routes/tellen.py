import json
from datetime import datetime, timedelta

from flask import Response, flash, g, redirect, render_template, request, session, url_for

from database import get_db
from voorspelling import (
    maak_prognose,
    telling_ver_van_verwachting,
    verwachte_verkoop_sinds_telling,
    verwachte_voorraad,
)
from voorspelling import omzet_per_week as omzet_per_week_berekend
from helpers import (
    bereken_trend,
    bestel_suggesties,
    format_datum,
    now_datetime_local,
    now_str,
    verwerk_auto_inactief,
)
from pdf import periode_verkoop_pdf, verkoop_pdf


def register_routes(app):

    def signaleer_afwijkende_telling(db, product_id, voorraad_voor, geteld, limiet=8):
        """Vergelijkt de mutatie (verkocht + correctie) van een nieuwe telling
        met het gemiddelde van de laatste tellingen van dit product, om een
        tikfout te kunnen signaleren voordat de telling wordt opgeslagen.
        Retourneert None als er te weinig geschiedenis is om iets zinnigs
        over te zeggen."""
        vorige = db.execute(
            """SELECT verkocht, correctie FROM telling_regels
               WHERE product_id = ? ORDER BY telling_id DESC LIMIT ?""",
            (product_id, limiet),
        ).fetchall()
        if len(vorige) < 3:
            return None
        gemiddelde = sum(r["verkocht"] + r["correctie"] for r in vorige) / len(vorige)
        mutatie_nu = abs(geteld - voorraad_voor)
        if mutatie_nu <= max(gemiddelde * 3, 6):
            return None
        return {"gemiddelde": gemiddelde, "mutatie_nu": mutatie_nu}

    def verwerk_telling(db, waarden, naam, opmerking, datum, gebruiker_id=None):
        """waarden: dict {product_id: geteld_aantal}. Maakt een telling aan,
        berekent per product het verschil met de huidige voorraad, en werkt
        voorraad + geschiedenis bij. Retourneert het nieuwe telling_id, of
        None als er niets te verwerken viel."""
        if not waarden:
            return None

        cur = db.execute(
            "INSERT INTO tellingen (datum, naam, gebruiker_id, opmerking) VALUES (?, ?, ?, ?)",
            (datum, naam, gebruiker_id, opmerking),
        )
        telling_id = cur.lastrowid

        # Alle geteld producten in 1 keer ophalen i.p.v. per product een losse
        # SELECT (was een N+1: bij een volledige telling van bijv. 150
        # producten scheelt dit ~150 queries).
        plekhouders = ",".join("?" * len(waarden))
        producten_bij_id = {
            p["id"]: p
            for p in db.execute(
                f"SELECT * FROM producten WHERE id IN ({plekhouders})", tuple(waarden.keys())
            ).fetchall()
        }

        for product_id, geteld in waarden.items():
            product = producten_bij_id.get(product_id)
            if product is None:
                continue
            verschil = geteld - product["voorraad"]
            verkocht = max(0, -verschil)
            correctie = max(0, verschil)

            db.execute(
                """INSERT INTO telling_regels
                   (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht,
                    correctie, verkoopprijs)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    telling_id,
                    product_id,
                    product["voorraad"],
                    geteld,
                    verkocht,
                    correctie,
                    product["verkoopprijs"],
                ),
            )
            db.execute(
                "UPDATE producten SET voorraad = ? WHERE id = ?", (geteld, product_id)
            )
            gedeactiveerd = verwerk_auto_inactief(db, product_id, geteld)
            if gedeactiveerd:
                flash(f"'{gedeactiveerd}' is automatisch op inactief gezet (voorraad op 0).", "warning")
            if verkocht > 0:
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                       VALUES (?, 'uit', ?, ?, ?, ?, ?, ?)""",
                    (product_id, verkocht, datum, naam, gebruiker_id, f"Verkocht (telling #{telling_id})", telling_id),
                )
            elif correctie > 0:
                db.execute(
                    """INSERT INTO mutaties
                       (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                       VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                    (product_id, correctie, datum, naam, gebruiker_id, f"Correctie (telling #{telling_id})", telling_id),
                )

        db.commit()
        return telling_id

    @app.route("/tellen", methods=["GET", "POST"])
    def tellen():
        db = get_db()
        if request.method == "POST":
            naam = session.get("gebruiker_naam")
            gebruiker_id = session.get("gebruiker_id")
            opmerking = request.form.get("opmerking", "").strip()
            datum_input = request.form.get("datum", "").strip()
            datum = datum_input.replace("T", " ") if datum_input else now_str()

            producten = db.execute(
                "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
            ).fetchall()

            waarden = {}
            for p in producten:
                waarde = request.form.get(f"geteld_{p['id']}", "").strip()
                if waarde == "":
                    continue
                try:
                    geteld = int(waarde)
                except ValueError:
                    continue
                if geteld < 0:
                    continue
                waarden[p["id"]] = geteld

            telling_id = verwerk_telling(db, waarden, naam, opmerking, datum, gebruiker_id)
            if telling_id is None:
                flash("Geen aantallen ingevuld: er is niets geteld.", "error")
                return redirect(url_for("tellen"))

            flash(
                f"Telling #{telling_id} verwerkt: {len(waarden)} product(en) geteld.",
                "success",
            )
            return redirect(url_for("telling_detail", telling_id=telling_id))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        return render_template(
            "tellen.html",
            producten=producten,
            nu_datetime_local=now_datetime_local(),
            loop_onderbroken=loop_onderbroken(db, len(producten)),
        )

    LOOP_SESSIE_SLEUTELS = ("loop_fase", "loop_index", "loop_bar", "loop_hok")
    LOOP_BEWAREN_DAGEN = 3  # een onderbroken looplijst blijft zo lang bewaard

    # ---------- Looplijst bewaren, zodat je 'm kunt pauzeren en later oppakken ----------
    # De stand staat tijdens het lopen in de sessie (zie hieronder) en wordt bij
    # elke stap ook in de database bewaard: zo overleeft 'ie een vergrendelde
    # telefoon, uitloggen of een ander toestel.

    def loop_bewaren(db):
        gebruiker_id = session.get("gebruiker_id")
        review = session.get("loop_review")
        if gebruiker_id is None or (review is None and "loop_fase" not in session):
            return
        db.execute(
            """INSERT OR REPLACE INTO loop_voortgang
                   (gebruiker_id, fase, indx, bar, hok, review, bijgewerkt_op)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                gebruiker_id,
                session.get("loop_fase", "bar"),
                session.get("loop_index", 0),
                json.dumps(session.get("loop_bar", {})),
                json.dumps(session.get("loop_hok", {})),
                json.dumps(review) if review is not None else None,
                now_str(),
            ),
        )
        db.commit()

    def loop_wissen(db):
        """Alles van de looplijst weg: sessie en bewaarde stand."""
        for sleutel in list(LOOP_SESSIE_SLEUTELS) + ["loop_review"]:
            session.pop(sleutel, None)
        gebruiker_id = session.get("gebruiker_id")
        if gebruiker_id is not None:
            db.execute("DELETE FROM loop_voortgang WHERE gebruiker_id = ?", (gebruiker_id,))
            db.commit()

    def _bewaarde_loop(db):
        """De bewaarde stand van deze gebruiker, of None (ook als 'ie verlopen is)."""
        gebruiker_id = session.get("gebruiker_id")
        if gebruiker_id is None:
            return None
        rij = db.execute("SELECT * FROM loop_voortgang WHERE gebruiker_id = ?", (gebruiker_id,)).fetchone()
        if rij is None:
            return None
        try:
            bijgewerkt = datetime.strptime(rij["bijgewerkt_op"], "%Y-%m-%d %H:%M")
        except ValueError:
            bijgewerkt = datetime.now()
        if datetime.now() - bijgewerkt > timedelta(days=LOOP_BEWAREN_DAGEN):
            db.execute("DELETE FROM loop_voortgang WHERE gebruiker_id = ?", (gebruiker_id,))
            db.commit()
            return None
        return rij

    def loop_herstellen(db):
        """Zet de bewaarde stand terug in de sessie. True als er iets was."""
        rij = _bewaarde_loop(db)
        if rij is None:
            return False
        session["loop_bar"] = json.loads(rij["bar"])
        session["loop_hok"] = json.loads(rij["hok"])
        if rij["review"] is not None:
            session["loop_review"] = json.loads(rij["review"])
            session.pop("loop_fase", None)
            session.pop("loop_index", None)
        else:
            session["loop_fase"] = rij["fase"]
            session["loop_index"] = rij["indx"]
        session.modified = True
        return True

    def loop_onderbroken(db, totaal):
        """Beschrijving van een lopende of onderbroken looplijst voor de
        tellen-pagina, of None."""
        rij = _bewaarde_loop(db)
        bijgewerkt = rij["bijgewerkt_op"] if rij else None
        if session.get("loop_review") is not None:
            return {"in_controle": True, "fase": None, "nummer": None, "totaal": totaal, "bijgewerkt_op": bijgewerkt}
        if "loop_fase" in session:
            return {"in_controle": False, "fase": session.get("loop_fase", "bar"),
                    "nummer": session.get("loop_index", 0) + 1, "totaal": totaal, "bijgewerkt_op": bijgewerkt}
        if rij is None:
            return None
        return {"in_controle": rij["review"] is not None, "fase": rij["fase"], "nummer": rij["indx"] + 1,
                "totaal": totaal, "bijgewerkt_op": bijgewerkt}

    @app.route("/tellen/lopen/starten")
    def tellen_lopen_starten():
        loop_wissen(get_db())
        return redirect(url_for("tellen_lopen"))

    @app.route("/tellen/lopen/hervatten")
    def tellen_lopen_hervatten():
        """Pakt een onderbroken looplijst weer op waar je was."""
        db = get_db()
        if session.get("loop_review") is None and "loop_fase" not in session and not loop_herstellen(db):
            flash("Er is geen looplijst om mee verder te gaan.", "error")
            return redirect(url_for("tellen"))
        if session.get("loop_review") is not None:
            return redirect(url_for("tellen_lopen_controleren"))
        return redirect(url_for("tellen_lopen"))

    @app.route("/tellen/lopen", methods=["GET", "POST"])
    def tellen_lopen():
        db = get_db()
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        if not producten:
            flash("Geen actieve producten om te tellen.", "error")
            return redirect(url_for("tellen"))
        totaal = len(producten)

        # Sessie kwijt (uitgelogd, nieuw toestel) maar wel iets bewaard: pak dat op.
        if session.get("loop_review") is None and "loop_fase" not in session:
            loop_herstellen(db)
            if session.get("loop_review") is not None:
                return redirect(url_for("tellen_lopen_controleren"))

        if request.method == "POST":
            actie = request.form.get("actie", "volgende")
            if actie == "stoppen":
                loop_wissen(db)
                flash("Looplijst afgebroken, er is niets opgeslagen.", "error")
                return redirect(url_for("tellen"))

            fase = session.get("loop_fase", "bar")
            index = session.get("loop_index", 0)
            bar_waarden = session.get("loop_bar", {})
            hok_waarden = session.get("loop_hok", {})
            huidige_dict = bar_waarden if fase == "bar" else hok_waarden

            if 0 <= index < totaal:
                product_id = str(producten[index]["id"])
                waarde = request.form.get("geteld", "").strip()
                if waarde != "":
                    huidige_dict[product_id] = waarde
                elif product_id in huidige_dict:
                    del huidige_dict[product_id]

            if actie == "pauzeren":
                # Wat er is ingevuld bewaren en later verder: de stand blijft staan.
                session["loop_fase"] = fase
                session["loop_index"] = index
                session["loop_bar"] = bar_waarden
                session["loop_hok"] = hok_waarden
                session.modified = True
                loop_bewaren(db)
                flash("Looplijst gepauzeerd. Je kunt later op deze pagina doorgaan waar je was.", "success")
                return redirect(url_for("tellen"))

            if actie == "vorige":
                index -= 1
                if index < 0:
                    if fase == "hok":
                        fase = "bar"
                        index = totaal - 1
                    else:
                        index = 0
            else:
                index += 1
                if index >= totaal:
                    if fase == "bar":
                        fase = "hok"
                        index = 0
                    else:
                        # Bar en voorraadhok zijn allebei geteld: optellen en
                        # naar het controlescherm, nog niet meteen opslaan.
                        geparsed = {}
                        for p in producten:
                            pid_str = str(p["id"])
                            bar_tekst = bar_waarden.get(pid_str, "")
                            hok_tekst = hok_waarden.get(pid_str, "")
                            if bar_tekst == "" and hok_tekst == "":
                                continue
                            try:
                                bar_aantal = int(bar_tekst) if bar_tekst != "" else 0
                            except ValueError:
                                bar_aantal = 0
                            try:
                                hok_aantal = int(hok_tekst) if hok_tekst != "" else 0
                            except ValueError:
                                hok_aantal = 0
                            geteld_totaal = bar_aantal + hok_aantal
                            if geteld_totaal >= 0:
                                geparsed[pid_str] = geteld_totaal

                        if not geparsed:
                            loop_wissen(db)
                            flash("Geen aantallen ingevuld: er is niets geteld.", "error")
                            return redirect(url_for("tellen"))

                        session["loop_review"] = geparsed
                        session["loop_bar"] = bar_waarden
                        session["loop_hok"] = hok_waarden
                        session.pop("loop_fase", None)
                        session.pop("loop_index", None)
                        session.modified = True
                        loop_bewaren(db)
                        return redirect(url_for("tellen_lopen_controleren"))

            session["loop_fase"] = fase
            session["loop_index"] = index
            session["loop_bar"] = bar_waarden
            session["loop_hok"] = hok_waarden
            session.modified = True
            loop_bewaren(db)
            return redirect(url_for("tellen_lopen"))

        fase = session.get("loop_fase", "bar")
        index = session.get("loop_index", 0)
        if index >= totaal:
            index = 0
        bar_waarden = session.get("loop_bar", {})
        hok_waarden = session.get("loop_hok", {})
        huidig = producten[index]
        huidige_dict = bar_waarden if fase == "bar" else hok_waarden
        huidige_waarde = huidige_dict.get(str(huidig["id"]), "")
        bar_waarde_hint = bar_waarden.get(str(huidig["id"]), "") if fase == "hok" else None

        stap_nu = (0 if fase == "bar" else totaal) + index
        voortgang_percentage = round(stap_nu / (totaal * 2) * 100, 1)

        # Wat er ongeveer in het schap hoort te staan (bar en voorraadhok samen),
        # als hulp om een telfout meteen op te merken. Mag de looplijst nooit stuk maken.
        try:
            verwacht = verwachte_voorraad(
                verwachte_verkoop_sinds_telling(db).get(huidig["id"]), huidig["voorraad"]
            )
        except Exception as fout:
            print(f"[voorspelling] verwachte voorraad mislukt: {fout}")
            verwacht = None

        return render_template(
            "tellen_lopen.html",
            product=huidig,
            verwacht=verwacht,
            index=index,
            totaal=totaal,
            fase=fase,
            bar_waarde_hint=bar_waarde_hint,
            huidige_waarde=huidige_waarde,
            voortgang_percentage=voortgang_percentage,
        )

    @app.route("/tellen/lopen/controleren", methods=["GET", "POST"])
    def tellen_lopen_controleren():
        db = get_db()
        review = session.get("loop_review")
        if not review:
            loop_herstellen(db)
            review = session.get("loop_review")
        if not review:
            return redirect(url_for("tellen"))

        if request.method == "POST":
            actie = request.form.get("actie", "bevestigen")
            if actie == "annuleren":
                loop_wissen(db)
                flash("Looplijst afgebroken, er is niets opgeslagen.", "error")
                return redirect(url_for("tellen"))

            waarden = {}
            for product_id_str in review:
                tekst = request.form.get(f"totaal_{product_id_str}", "").strip()
                if tekst == "":
                    continue
                try:
                    aantal = int(tekst)
                except ValueError:
                    continue
                if aantal < 0:
                    continue
                waarden[int(product_id_str)] = aantal

            loop_wissen(db)

            telling_id = verwerk_telling(
                db,
                waarden,
                session.get("gebruiker_naam"),
                "Via looplijst geteld (bar + voorraadhok)",
                now_str(),
                session.get("gebruiker_id"),
            )
            if telling_id is None:
                flash("Geen aantallen ingevuld: er is niets geteld.", "error")
                return redirect(url_for("tellen"))
            flash(
                f"Telling #{telling_id} bevestigd: {len(waarden)} product(en) opgeslagen.",
                "success",
            )
            return redirect(url_for("telling_detail", telling_id=telling_id))

        bar_waarden = session.get("loop_bar", {})
        hok_waarden = session.get("loop_hok", {})
        try:
            verwachting = verwachte_verkoop_sinds_telling(db)
        except Exception as fout:
            print(f"[voorspelling] verwachte voorraad mislukt: {fout}")
            verwachting = {}
        regels = []
        for product_id_str, totaal in review.items():
            product = db.execute(
                "SELECT * FROM producten WHERE id = ?", (int(product_id_str),)
            ).fetchone()
            if product is None:
                continue
            verwacht_nu = verwachte_voorraad(verwachting.get(product["id"]), product["voorraad"])
            regels.append(
                {
                    "product": product,
                    "bar": bar_waarden.get(product_id_str, "") or "0",
                    "hok": hok_waarden.get(product_id_str, "") or "0",
                    "totaal": totaal,
                    "afwijking": signaleer_afwijkende_telling(
                        db, product["id"], product["voorraad"], totaal
                    ),
                    "verwacht": verwacht_nu,
                    "model_afwijking": telling_ver_van_verwachting(
                        verwachting.get(product["id"]), product["voorraad"], totaal
                    ),
                }
            )
        regels.sort(key=lambda r: (r["product"]["categorie"], r["product"]["naam"]))

        return render_template("tellen_lopen_controleren.html", regels=regels)

    @app.route("/tellingen")
    def tellingen_overzicht():
        db = get_db()
        tellingen = db.execute(
            """SELECT t.*,
                      (SELECT COUNT(*) FROM telling_regels WHERE telling_id = t.id) AS aantal_producten,
                      (SELECT COALESCE(SUM(tr.verkocht * tr.verkoopprijs), 0)
                         FROM telling_regels tr
                         WHERE tr.telling_id = t.id) AS omzet
               FROM tellingen t
               ORDER BY t.id DESC"""
        ).fetchall()

        # Per telling de regels erbij, voor de "Bekijken"-pop-up -- scheelt
        # een aparte pagina-navigatie voor een snel kijkje.
        regels_per_telling = {
            t["id"]: db.execute(
                """SELECT tr.*, p.naam AS product_naam, p.eenheid
                   FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
                   WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
                (t["id"],),
            ).fetchall()
            for t in tellingen
        }

        # Omzet per week: de omzet van elke telling wordt verdeeld over de dagen die
        # erbij horen (zie voorspelling.omzet_per_week), dus het maakt niet uit
        # op welke dagen je telt. Alleen volledig gedekte weken tellen mee voor
        # de trend.
        omzet_per_week = omzet_per_week_berekend(db)
        huidige_jaar, huidige_week, _ = datetime.now().isocalendar()
        trend = bereken_trend(omzet_per_week, huidige_jaar, huidige_week)
        try:
            prognose = maak_prognose(db, dagen=7)
        except Exception as fout:  # het tellingenoverzicht mag nooit stuk gaan door de voorspelling
            print(f"[voorspelling] mislukt: {fout}")
            prognose = None

        return render_template(
            "pda_tellingen.html" if g.get("weergave_modus") == "pda" else "tellingen_overzicht.html",
            tellingen=tellingen,
            regels_per_telling=regels_per_telling,
            omzet_per_week=omzet_per_week,
            huidige_jaar=huidige_jaar,
            huidige_week=huidige_week,
            trend=trend,
            prognose=prognose,
        )

    @app.route("/tellingen/gecombineerd/pdf")
    def tellingen_gecombineerd_pdf():
        """PDF van een zelf geselecteerde greep tellingen -- de regels worden
        per product bij elkaar opgeteld, net als bij het periode-verkooprapport
        (dat gebruikt een datumrange; dit gebruikt een losse selectie)."""
        ids = request.args.getlist("ids", type=int)
        if not ids:
            flash("Selecteer minstens één telling om te combineren.", "error")
            return redirect(url_for("tellingen_overzicht"))

        db = get_db()
        placeholders = ",".join("?" for _ in ids)
        regels = db.execute(
            f"""SELECT p.naam AS product_naam, p.categorie, p.eenheid,
                       SUM(tr.verkocht) AS verkocht, SUM(tr.correctie) AS correctie,
                       SUM(tr.verkocht * tr.verkoopprijs) AS omzet
                FROM telling_regels tr
                JOIN tellingen t ON t.id = tr.telling_id
                JOIN producten p ON p.id = tr.product_id
                WHERE tr.telling_id IN ({placeholders})
                GROUP BY tr.product_id
                ORDER BY p.categorie, p.naam""",
            ids,
        ).fetchall()
        grens = db.execute(
            f"SELECT MIN(datum) AS van, MAX(datum) AS tot FROM tellingen WHERE id IN ({placeholders})",
            ids,
        ).fetchone()

        pdf_bytes = periode_verkoop_pdf(
            format_datum(grens["van"]) if grens["van"] else "",
            format_datum(grens["tot"]) if grens["tot"] else "",
            regels,
        )
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-selectie-{len(ids)}-tellingen.pdf"
            },
        )

    @app.route("/tellingen/<int:telling_id>")
    def telling_detail(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Telling niet gevonden.", "error")
            return redirect(url_for("tellen"))

        regels = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        totaal_omzet = sum(r["verkocht"] * r["verkoopprijs"] for r in regels)
        besteladvies = bestel_suggesties(db)

        return render_template(
            "pda_telling_detail.html" if g.get("weergave_modus") == "pda" else "telling_detail.html",
            telling=telling,
            regels=regels,
            totaal_omzet=totaal_omzet,
            besteladvies=besteladvies,
        )

    @app.route("/tellingen/regels/<int:regel_id>/corrigeren", methods=["POST"])
    def telling_regel_corrigeren(regel_id):
        """Corrigeert het geteld aantal (en dus verkocht/correctie) van 1
        productregel binnen een eerder afgeronde telling -- bijv. omdat er
        iets over het hoofd is gezien bij het tellen (een krat die nog in de
        koelkast stond). Raakt bewust nooit de actuele voorraad: die had je
        al apart via boeken in/uit rechtgezet. Dit corrigeert alleen het
        historische verkocht/correctie-cijfer (en daarmee de omzetcijfers)
        van deze ene telling."""
        db = get_db()
        regel = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid, t.datum AS telling_datum
               FROM telling_regels tr
               JOIN producten p ON p.id = tr.product_id
               JOIN tellingen t ON t.id = tr.telling_id
               WHERE tr.id = ?""",
            (regel_id,),
        ).fetchone()
        if regel is None:
            flash("Tellingregel niet gevonden.", "error")
            return redirect(url_for("tellen"))

        try:
            nieuw_geteld = int(request.form.get("geteld_aantal", ""))
        except (TypeError, ValueError):
            flash("Vul een geldig aantal in.", "error")
            return redirect(url_for("telling_detail", telling_id=regel["telling_id"]))
        if nieuw_geteld < 0:
            flash("Aantal kan niet negatief zijn.", "error")
            return redirect(url_for("telling_detail", telling_id=regel["telling_id"]))

        opmerking = request.form.get("correctie_opmerking", "").strip()
        naam = session.get("gebruiker_naam")
        gebruiker_id = session.get("gebruiker_id")

        verschil = nieuw_geteld - regel["voorraad_voor"]
        nieuw_verkocht = max(0, -verschil)
        nieuw_correctie = max(0, verschil)

        db.execute(
            """UPDATE telling_regels
               SET geteld_aantal_voor_correctie = ?,
                   gecorrigeerd_door_id = ?,
                   gecorrigeerd_door = ?,
                   gecorrigeerd_op = ?,
                   correctie_opmerking = ?,
                   geteld_aantal = ?,
                   verkocht = ?,
                   correctie = ?
               WHERE id = ?""",
            (
                regel["geteld_aantal"],
                gebruiker_id,
                naam,
                now_str(),
                opmerking,
                nieuw_geteld,
                nieuw_verkocht,
                nieuw_correctie,
                regel_id,
            ),
        )

        # De mutatie die destijds voor dit product bij deze telling is
        # aangemaakt moet meeveranderen, anders blijft de geschiedenis het
        # oude (foute) verkocht/correctie-cijfer tonen.
        db.execute(
            "DELETE FROM mutaties WHERE telling_id = ? AND product_id = ?",
            (regel["telling_id"], regel["product_id"]),
        )
        if nieuw_verkocht > 0:
            db.execute(
                """INSERT INTO mutaties
                   (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                   VALUES (?, 'uit', ?, ?, ?, ?, ?, ?)""",
                (
                    regel["product_id"],
                    nieuw_verkocht,
                    regel["telling_datum"],
                    naam,
                    gebruiker_id,
                    f"Verkocht (telling #{regel['telling_id']}, gecorrigeerd)",
                    regel["telling_id"],
                ),
            )
        elif nieuw_correctie > 0:
            db.execute(
                """INSERT INTO mutaties
                   (product_id, type, aantal, datum, naam, gebruiker_id, opmerking, telling_id)
                   VALUES (?, 'in', ?, ?, ?, ?, ?, ?)""",
                (
                    regel["product_id"],
                    nieuw_correctie,
                    regel["telling_datum"],
                    naam,
                    gebruiker_id,
                    f"Correctie (telling #{regel['telling_id']}, gecorrigeerd)",
                    regel["telling_id"],
                ),
            )
        db.commit()

        flash(
            f"Telling voor '{regel['product_naam']}' gecorrigeerd: {regel['geteld_aantal']} → "
            f"{nieuw_geteld} {regel['eenheid']} geteld.",
            "success",
        )
        return redirect(url_for("telling_detail", telling_id=regel["telling_id"]))

    @app.route("/tellingen/<int:telling_id>/pdf")
    def telling_pdf(telling_id):
        db = get_db()
        telling = db.execute(
            "SELECT * FROM tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        if telling is None:
            flash("Telling niet gevonden.", "error")
            return redirect(url_for("tellen"))

        regels = db.execute(
            """SELECT tr.*, p.naam AS product_naam, p.eenheid
               FROM telling_regels tr JOIN producten p ON p.id = tr.product_id
               WHERE tr.telling_id = ? ORDER BY p.categorie, p.naam""",
            (telling_id,),
        ).fetchall()
        vorige_telling = db.execute(
            "SELECT * FROM tellingen WHERE id < ? ORDER BY id DESC LIMIT 1",
            (telling_id,),
        ).fetchone()

        van = format_datum(vorige_telling["datum"]) if vorige_telling else "eerste telling"
        periode_tekst = f"Periode: {van}  t/m  {format_datum(telling['datum'])}"
        pdf_bytes = verkoop_pdf(telling_id, periode_tekst, regels)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=verkooprapport-telling-{telling_id}.pdf"
            },
        )

