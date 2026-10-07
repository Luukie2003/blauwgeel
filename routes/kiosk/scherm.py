"""Dia's-scherm: instellingen, standen, Man of the Match en het scherm/de tv zelf."""

import json

from flask import flash, jsonify, redirect, render_template, request, url_for

from database import get_db
from helpers import (
    MOTM_RESULTATEN,
    bewaar_club_logo,
    club_van_team_naam,
    is_ajax_verzoek,
    motm_resultaat_klopt,
    sla_club_logo_op,
)
from routes.kiosk.dia_gegevens import (
    _bouw_slides,
    _motm_teams,
    _stand_poule_sleutels,
    _unieke_poule_sleutel,
)
from routes.kiosk.gedeeld import _prijzen_instellingen, _scherm_instellingen, _versie
from routes.kiosk.prijzen_gegevens import (
    _acties_actief,
    _bardiensten_vandaag,
    _categorie_kolommen_indeling,
    _eerstvolgende_bekende_tegenstander,
    _prijzen_categorieen,
    _prijzen_render_kwargs,
    _prijzen_sponsoren,
    _prijzen_versie,
    _uitgelicht_product,
    _uitverkocht_namen,
    _wedstrijddag_welkom_wedstrijden,
)


def register_routes(app):
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
                       toon_wedstrijden = ?, wedstrijden_volgorde = ?,
                       wedstrijden_duur_seconden = ?,
                       toon_standen = ?, standen_volgorde = ?, standen_duur_seconden = ?,
                       toon_motm = ?, motm_volgorde = ?, motm_duur_seconden = ?, motm_titel = ?
                   WHERE id = 1""",
                (
                    1 if request.form.get("toon_sponsoren") else 0,
                    _getal("sponsoren_volgorde", 1),
                    1 if request.form.get("toon_club_van_20") else 0,
                    _getal("club_van_20_volgorde", 2),
                    1 if request.form.get("toon_wedstrijden") else 0,
                    _getal("wedstrijden_volgorde", 3),
                    max(3, _getal("wedstrijden_duur_seconden", 10)),
                    1 if request.form.get("toon_standen") else 0,
                    _getal("standen_volgorde", 4),
                    max(3, _getal("standen_duur_seconden", 10)),
                    1 if request.form.get("toon_motm") else 0,
                    _getal("motm_volgorde", 5),
                    max(3, _getal("motm_duur_seconden", 10)),
                    request.form.get("motm_titel", "").strip() or "Man of de match van vorig weekend!",
                ),
            )
            db.commit()
            if is_ajax_verzoek():
                return jsonify({"ok": True, "melding": "Instellingen voor het kantine scherm opgeslagen."})
            flash("Instellingen voor het kantine scherm opgeslagen.", "success")
            return redirect(url_for("kiosk_sponsoren_leden"))

        # Geen eigen pagina meer -- de instellingen staan nu op hetzelfde
        # scherm als de dia's zelf (zie kiosk_sponsoren_leden), dus een GET
        # hierheen (bijv. een oude bladwijzer) stuurt gewoon door.
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/standen/team-nieuw", methods=["POST"])
    def kiosk_stand_team_nieuw():
        db = get_db()
        poule = request.form.get("poule", "")
        if poule not in _stand_poule_sleutels(db):
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Onbekend team."}), 404
            flash("Onbekend team.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        naam = request.form.get("naam", "").strip()
        if not naam:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Vul een clubnaam in."}), 400
            flash("Vul een clubnaam in.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        club = club_van_team_naam(naam)
        # Nieuw logo geupload? Gebruik dat. Anders: staat er al 1 geregistreerd
        # voor deze club (bijv. via een ander team/poule), hergebruik die.
        afbeelding = sla_club_logo_op(request.files.get("logo"))
        if not afbeelding:
            bekend = db.execute(
                "SELECT afbeelding FROM kiosk_club_logos WHERE club = ?", (club,)
            ).fetchone()
            if bekend:
                afbeelding = bekend["afbeelding"]
        volgende = db.execute(
            "SELECT COALESCE(MAX(volgorde), -1) + 1 AS volgende FROM kiosk_stand_teams WHERE poule = ?",
            (poule,),
        ).fetchone()["volgende"]
        db.execute(
            "INSERT INTO kiosk_stand_teams (poule, naam, club, volgorde) VALUES (?, ?, ?, ?)",
            (poule, naam, club, volgende),
        )
        bewaar_club_logo(db, club, afbeelding)
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash(f"'{naam}' toegevoegd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/standen/team/<int:team_id>/verwijderen", methods=["POST"])
    def kiosk_stand_team_verwijderen(team_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_stand_teams WHERE id = ?", (team_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Team verwijderd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/standen/team/<int:team_id>/eigen-team", methods=["POST"])
    def kiosk_stand_team_eigen_wisselen(team_id):
        """Markeert dit team als de vereniging zelf (voor de uitlichting op
        de dia, zie kiosk_scherm.html) -- ten hoogste 1 per poule, dus de
        rest van dezelfde poule gaat eerst weer uit."""
        db = get_db()
        team = db.execute("SELECT * FROM kiosk_stand_teams WHERE id = ?", (team_id,)).fetchone()
        if team is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Team niet gevonden."}), 404
            flash("Team niet gevonden.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        nieuwe_status = 0 if team["eigen_team"] else 1
        db.execute("UPDATE kiosk_stand_teams SET eigen_team = 0 WHERE poule = ?", (team["poule"],))
        db.execute("UPDATE kiosk_stand_teams SET eigen_team = ? WHERE id = ?", (nieuwe_status, team_id))
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash(
            f"'{team['naam']}' is nu het eigen team." if nieuwe_status else f"'{team['naam']}' is geen eigen team meer.",
            "success",
        )
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/standen/<poule>/volgorde", methods=["POST"])
    def kiosk_stand_volgorde_opslaan(poule):
        db = get_db()
        if poule not in _stand_poule_sleutels(db):
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Onbekend team."}), 404
            flash("Onbekend team.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        # Titel van de poule zelf komt ook in dezelfde submit mee (het kopje
        # boven de sleeplijst is een tekstveld, zie kiosk_sponsoren_leden.html).
        poule_titel = request.form.get("poule_titel", "").strip()
        if poule_titel:
            db.execute(
                "UPDATE kiosk_stand_poules SET titel = ? WHERE sleutel = ?", (poule_titel, poule)
            )
        try:
            volgorde_ids = json.loads(request.form.get("volgorde") or "[]")
        except ValueError:
            volgorde_ids = []
        for index, team_id in enumerate(volgorde_ids):
            db.execute(
                "UPDATE kiosk_stand_teams SET volgorde = ? WHERE id = ? AND poule = ?",
                (index, team_id, poule),
            )
        # W/GL/V per team komen in dezelfde submit mee (zie de sleeplijst op
        # kiosk_sponsoren_leden.html) -- 1 "Opslaan"-knop voor zowel de
        # volgorde als de bijgewerkte stand, i.p.v. 2 losse acties.
        try:
            statistieken = json.loads(request.form.get("statistieken") or "{}")
        except ValueError:
            statistieken = {}

        def _getal(waarde):
            try:
                return max(0, int(waarde))
            except (TypeError, ValueError):
                return 0

        for team_id, s in statistieken.items():
            db.execute(
                """UPDATE kiosk_stand_teams SET gewonnen = ?, gelijk = ?, verloren = ?
                   WHERE id = ? AND poule = ?""",
                (_getal(s.get("w")), _getal(s.get("gl")), _getal(s.get("v")), team_id, poule),
            )
        # Teamnaam aanpassen komt in dezelfde submit mee (het naamveld op de
        # sleeplijst is nu een tekstveld i.p.v. statische tekst) -- club volgt
        # opnieuw uit de (mogelijk aangepaste) naam, zodat het logo-register
        # gewoon blijft kloppen. Leeg laten negeert de wijziging.
        try:
            namen = json.loads(request.form.get("namen") or "{}")
        except ValueError:
            namen = {}
        for team_id, naam in namen.items():
            naam = (naam or "").strip()
            if not naam:
                continue
            db.execute(
                "UPDATE kiosk_stand_teams SET naam = ?, club = ? WHERE id = ? AND poule = ?",
                (naam, club_van_team_naam(naam), team_id, poule),
            )
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Stand opgeslagen.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/standen/club-logo", methods=["POST"])
    def kiosk_club_logo_opslaan():
        """Los van het toevoegen van een team: een logo later alsnog
        toevoegen of vervangen voor een club die al in 1 of meer poules
        staat -- werkt meteen door voor elk team van die club, in elke
        poule (zie _club_logo/_stand_team_weergave hierboven)."""
        db = get_db()
        club = request.form.get("club", "").strip()
        if not club:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Onbekende club."}), 400
            flash("Onbekende club.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        afbeelding = sla_club_logo_op(request.files.get("logo"))
        if not afbeelding:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Kies een afbeelding om te uploaden."}), 400
            flash("Kies een afbeelding om te uploaden.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        bewaar_club_logo(db, club, afbeelding)
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash(f"Logo voor '{club}' opgeslagen.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/standen/poule-nieuw", methods=["POST"])
    def kiosk_stand_poule_nieuw():
        db = get_db()
        titel = request.form.get("titel", "").strip()
        if not titel:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Vul een titel in."}), 400
            flash("Vul een titel in.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        sleutel = _unieke_poule_sleutel(db, titel)
        volgende = db.execute(
            "SELECT COALESCE(MAX(volgorde), -1) + 1 AS volgende FROM kiosk_stand_poules"
        ).fetchone()["volgende"]
        db.execute(
            "INSERT INTO kiosk_stand_poules (sleutel, titel, volgorde) VALUES (?, ?, ?)",
            (sleutel, titel, volgende),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash(f"Poule '{titel}' toegevoegd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/standen/poule/<poule>/verwijderen", methods=["POST"])
    def kiosk_stand_poule_verwijderen(poule):
        db = get_db()
        db.execute("DELETE FROM kiosk_stand_teams WHERE poule = ?", (poule,))
        db.execute("DELETE FROM kiosk_stand_poules WHERE sleutel = ?", (poule,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Poule verwijderd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/motm/team-nieuw", methods=["POST"])
    def kiosk_motm_team_nieuw():
        db = get_db()
        team = request.form.get("team", "").strip()
        if not team:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Vul een teamnaam in."}), 400
            flash("Vul een teamnaam in.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        volgende = db.execute(
            "SELECT COALESCE(MAX(volgorde), -1) + 1 AS volgende FROM kiosk_motm"
        ).fetchone()["volgende"]
        db.execute("INSERT INTO kiosk_motm (team, volgorde) VALUES (?, ?)", (team, volgende))
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash(f"'{team}' toegevoegd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/motm/team/<int:team_id>/verwijderen", methods=["POST"])
    def kiosk_motm_team_verwijderen(team_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_motm WHERE id = ?", (team_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Team verwijderd.", "success")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm/motm/volgorde", methods=["POST"])
    def kiosk_motm_volgorde_opslaan():
        """1 knop voor zowel de volgorde als de bijgewerkte MOTM-namen, zelfde
        opzet als kiosk_stand_volgorde_opslaan hierboven."""
        db = get_db()
        try:
            volgorde_ids = json.loads(request.form.get("volgorde") or "[]")
        except ValueError:
            volgorde_ids = []
        for index, team_id in enumerate(volgorde_ids):
            db.execute("UPDATE kiosk_motm SET volgorde = ? WHERE id = ?", (index, team_id))
        try:
            spelers = json.loads(request.form.get("spelers") or "{}")
        except ValueError:
            spelers = {}
        for team_id, speler in spelers.items():
            db.execute(
                "UPDATE kiosk_motm SET speler = ? WHERE id = ?",
                ((speler or "").strip() or None, team_id),
            )
        try:
            uitslagen = json.loads(request.form.get("uitslagen") or "{}")
        except ValueError:
            uitslagen = {}
        for team_id, uitslag in uitslagen.items():
            db.execute(
                "UPDATE kiosk_motm SET uitslag = ? WHERE id = ?",
                ((uitslag or "").strip() or None, team_id),
            )
        try:
            resultaten = json.loads(request.form.get("resultaten") or "{}")
        except ValueError:
            resultaten = {}
        for team_id, resultaat in resultaten.items():
            resultaat = (resultaat or "").strip().lower()
            db.execute(
                "UPDATE kiosk_motm SET resultaat = ? WHERE id = ?",
                (resultaat if resultaat in MOTM_RESULTATEN else None, team_id),
            )
        try:
            tegenstanders = json.loads(request.form.get("tegenstanders") or "{}")
        except ValueError:
            tegenstanders = {}
        for team_id, tegenstander in tegenstanders.items():
            db.execute(
                "UPDATE kiosk_motm SET tegenstander = ? WHERE id = ?",
                ((tegenstander or "").strip() or None, team_id),
            )
        # Teamnaam aanpassen komt in dezelfde submit mee, zelfde opzet als
        # kiosk_stand_volgorde_opslaan hierboven -- leeg laten negeert de
        # wijziging.
        try:
            teamnamen = json.loads(request.form.get("teamnamen") or "{}")
        except ValueError:
            teamnamen = {}
        for team_id, team in teamnamen.items():
            team = (team or "").strip()
            if not team:
                continue
            db.execute("UPDATE kiosk_motm SET team = ? WHERE id = ?", (team, team_id))
        db.commit()
        # Een uitslag die niet past bij het gekozen resultaat (bijv. "2-2" bij
        # gewonnen) wordt toch bewaard, maar je krijgt er een melding bij.
        waarschuwingen = [
            f"{r['team']}: de uitslag {r['uitslag']} past niet bij '{MOTM_RESULTATEN[r['resultaat']].lower()}', "
            "dus de dia toont 'm zoals je 'm hebt ingevuld."
            for r in _motm_teams(db)
            if r["resultaat"] in MOTM_RESULTATEN and not motm_resultaat_klopt(r["uitslag"], r["resultaat"])
        ]
        if is_ajax_verzoek():
            return jsonify({"ok": True, "waarschuwingen": waarschuwingen})
        flash("Man of the Match opgeslagen.", "success")
        for tekst in waarschuwingen:
            flash(tekst, "warning")
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm")
    def kiosk_scherm():
        db = get_db()
        slides = _bouw_slides(db)
        return render_template(
            "kiosk_scherm.html",
            slides=slides,
            sponsors_elke=_scherm_instellingen(db)["sponsors_elke_dias"],
            versie=_versie(slides),
            versie_url=url_for("kiosk_scherm_versie"),
        )

    @app.route("/kiosk/scherm/versie")
    def kiosk_scherm_versie():
        db = get_db()
        return jsonify({"versie": _versie(_bouw_slides(db))})

    # ---------- Gedeeld scherm: 1 fysiek scherm wisselen tussen prijzen/dia's ----------
    # Losstaand van de 2 vaste schermen hierboven (die blijven ongewijzigd
    # werken voor wie 2 fysieke TV's heeft) -- /kiosk/tv is een extra,
    # optionele derde weergave voor wie (nog) maar 1 scherm heeft en daarop
    # met een knop wil wisselen zonder de Chromecast zelf aan te raken.

    @app.route("/kiosk/tv")
    def kiosk_tv():
        db = get_db()
        instellingen = _scherm_instellingen(db)
        if instellingen["actief_tv_scherm"] == "dias":
            slides = _bouw_slides(db)
            return render_template(
                "kiosk_scherm.html",
                slides=slides,
                sponsors_elke=instellingen["sponsors_elke_dias"],
                versie=_versie("tv", slides),
                versie_url=url_for("kiosk_tv_versie"),
            )
        return render_template(
            "kiosk_prijzen_scherm.html",
            **_prijzen_render_kwargs(db, url_for("kiosk_tv_versie"), extra_versie="tv"),
        )

    @app.route("/kiosk/tv/versie")
    def kiosk_tv_versie():
        db = get_db()
        instellingen = _scherm_instellingen(db)
        if instellingen["actief_tv_scherm"] == "dias":
            return jsonify({"versie": _versie("tv", _bouw_slides(db))})
        prijzen_instellingen = _prijzen_instellingen(db)
        uitgelicht = _uitgelicht_product(db, prijzen_instellingen)
        categorieen = _prijzen_categorieen(
            db, uitgelicht_product_id=uitgelicht["product_id"] if uitgelicht else None
        )
        acties = _acties_actief(db)
        bardiensten = _bardiensten_vandaag(db)
        return jsonify(
            {
                "versie": _prijzen_versie(
                    categorieen,
                    acties,
                    bardiensten,
                    _wedstrijddag_welkom_wedstrijden(db, prijzen_instellingen),
                    _categorie_kolommen_indeling(db, prijzen_instellingen),
                    uitgelicht,
                    "tv",
                    sponsoren=_prijzen_sponsoren(db),
                ),
                "uitverkocht": _uitverkocht_namen(categorieen),
                "wedstrijddag_test": prijzen_instellingen["wedstrijddag_test_teller"],
                "wedstrijddag_test_tegenstander": _eerstvolgende_bekende_tegenstander(db),
            }
        )

    @app.route("/kiosk/tv/wisselen", methods=["POST"])
    def kiosk_tv_wisselen():
        db = get_db()
        instellingen = _scherm_instellingen(db)
        nieuwe_modus = "dias" if instellingen["actief_tv_scherm"] == "prijzen" else "prijzen"
        db.execute(
            "UPDATE kiosk_scherm_instellingen SET actief_tv_scherm = ? WHERE id = 1", (nieuwe_modus,)
        )
        db.commit()
        melding = (
            "Gedeeld scherm toont nu de dia's."
            if nieuwe_modus == "dias"
            else "Gedeeld scherm toont nu de prijzenlijst."
        )
        if is_ajax_verzoek():
            return jsonify({"ok": True, "modus": nieuwe_modus, "melding": melding})
        flash(melding, "success")
        return redirect(request.referrer or url_for("kiosk_hub"))
