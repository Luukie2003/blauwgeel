"""De looplijst: product voor product tellen, met controlescherm."""

from flask import flash, redirect, render_template, request, session, url_for

from database import get_db
from helpers import now_str
from voorspelling import (
    telling_ver_van_verwachting,
    verwachte_verkoop_sinds_telling,
    verwachte_voorraad,
)
from routes.tellen.looplijst_opslag import loop_bewaren, loop_herstellen, loop_wissen
from routes.tellen.verwerken import signaleer_afwijkende_telling, verwerk_telling


def register_routes(app):
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
