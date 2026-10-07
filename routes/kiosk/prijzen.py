"""Prijzenscherm: de Kiosk-hub, de instellingen, de publieke schermen en hun versie-polls."""

import json

from flask import flash, jsonify, redirect, render_template, request, url_for

import qr
from database import get_db
from helpers import is_ajax_verzoek
from routes.kiosk.acties import _actie_producten
from routes.kiosk.gedeeld import _prijzen_instellingen, _scherm_instellingen
from routes.kiosk.prijzen_gegevens import (
    _acties_actief,
    _alle_kiosk_categorie_namen,
    _bardiensten_vandaag,
    _categorie_kolommen_indeling,
    _eerstvolgende_bekende_tegenstander,
    _prijzen_categorieen,
    _prijzen_render_kwargs,
    _prijzen_sponsoren,
    _prijzen_versie,
    _uitgelicht_product,
    _uitverkocht_namen,
    _verdeel_namen_over_kolommen,
    _wedstrijddag_welkom_wedstrijden,
)
from routes.kiosk.sponsoren_sjablonen import _sjabloon_producten


def register_routes(app):
    # ---------- Hub ----------

    @app.route("/kiosk")
    def kiosk_hub():
        db = get_db()
        prijzen_url = url_for("kiosk_prijzen_scherm", _external=True)
        scherm_url = url_for("kiosk_scherm", _external=True)
        tv_url = url_for("kiosk_tv", _external=True)
        return render_template(
            "kiosk_hub.html",
            prijzen_url=prijzen_url,
            scherm_url=scherm_url,
            tv_url=tv_url,
            prijzen_qr_svg=qr.qr_svg(prijzen_url),
            scherm_qr_svg=qr.qr_svg(scherm_url),
            tv_qr_svg=qr.qr_svg(tv_url),
            instellingen=_scherm_instellingen(db),
        )

    # ---------- Onderdeel 1: Prijzenscherm ----------

    @app.route("/kiosk/prijzen/instellingen", methods=["GET", "POST"])
    def kiosk_prijzen_instellingen():
        db = get_db()
        if request.method == "POST":
            producten = db.execute("SELECT id FROM producten").fetchall()
            updates = [
                (1 if request.form.get(f"toon_{p['id']}") else 0, p["id"]) for p in producten
            ]
            db.executemany("UPDATE producten SET toon_op_kiosk = ? WHERE id = ?", updates)
            db.commit()
            flash("Prijzenscherm-selectie opgeslagen.", "success")
            return redirect(url_for("kiosk_prijzen_instellingen"))

        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()
        acties = db.execute(
            """SELECT ka.*, p.naam AS product_naam FROM kiosk_acties ka
               JOIN producten p ON p.id = ka.product_id
               ORDER BY ka.id"""
        ).fetchall()
        prijzen_instellingen = _prijzen_instellingen(db)
        return render_template(
            "kiosk_prijzen_instellingen.html",
            producten=producten,
            acties=acties,
            instellingen=_scherm_instellingen(db),
            prijzen_instellingen=prijzen_instellingen,
            categorie_kolommen_namen=_verdeel_namen_over_kolommen(
                _alle_kiosk_categorie_namen(db), _categorie_kolommen_indeling(db, prijzen_instellingen)
            ),
            alle_producten=_sjabloon_producten(db),
            uitgelicht=_uitgelicht_product(db, prijzen_instellingen),
        )

    @app.route("/kiosk/prijzen/wedstrijddag-welkom", methods=["POST"])
    def kiosk_wedstrijddag_welkom_instellingen():
        db = get_db()
        tekst = request.form.get("wedstrijddag_welkom_tekst", "").strip()
        db.execute(
            """UPDATE kiosk_prijzen_instellingen
               SET wedstrijddag_welkom_actief = ?, wedstrijddag_welkom_tekst = ?
               WHERE id = 1""",
            (1 if request.form.get("wedstrijddag_welkom_actief") else 0, tekst or "Welkom {tegenstander}!"),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Wedstrijddag-welkomstmelding opgeslagen.", "success")
        return redirect(url_for("kiosk_prijzen_instellingen"))

    @app.route("/kiosk/prijzen/wedstrijddag-welkom/test", methods=["POST"])
    def kiosk_wedstrijddag_welkom_testen():
        """Laat de welkomstmelding 1x schermvullend zien op het (al open
        staande) prijzenscherm, los van of er nu echt een thuiswedstrijd is
        -- puur om de tekst/stijl te controleren zonder op een echte
        wedstrijddag te hoeven wachten. Werkt door een teller op te hogen
        die het scherm zelf al met zijn gewone 10s-versiepoll binnenhaalt
        (zie kiosk_prijzen_versie/kiosk_tv_versie hierboven en de JS in
        kiosk_prijzen_scherm.html) -- geen aparte polling-mechaniek nodig."""
        db = get_db()
        db.execute(
            "UPDATE kiosk_prijzen_instellingen SET wedstrijddag_test_teller = wedstrijddag_test_teller + 1 WHERE id = 1"
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Testmelding verstuurd naar het prijzenscherm.", "success")
        return redirect(url_for("kiosk_prijzen_instellingen"))

    @app.route("/api/tablet/wedstrijddag-welkom")
    def api_tablet_wedstrijddag_welkom():
        """JSON-versie voor de kiosk-tablet-app (los project, zie
        android-apps/tablet). Opslaan gaat via
        kiosk_wedstrijddag_welkom_instellingen hierboven."""
        instellingen = _prijzen_instellingen(get_db())
        return jsonify(
            {
                "actief": bool(instellingen["wedstrijddag_welkom_actief"]),
                "tekst": instellingen["wedstrijddag_welkom_tekst"],
            }
        )

    @app.route("/kiosk/prijzen/categorie-kolommen", methods=["POST"])
    def kiosk_categorie_kolommen_instellingen():
        """Slaat de gesleepte kolomindeling op (zie kiosk_prijzen_instellingen.html)
        -- 1 verborgen JSON-veld met de 3 kolommen, i.p.v. losse velden per
        categorie, want het aantal categorieën en hun namen staan niet vooraf
        vast."""
        db = get_db()
        try:
            data = json.loads(request.form.get("indeling", "{}"))
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        schoon = {
            kolom: [naam for naam in data.get(kolom, []) if isinstance(naam, str)]
            for kolom in ("1", "2", "3")
        }
        db.execute(
            "UPDATE kiosk_prijzen_instellingen SET categorie_kolommen = ? WHERE id = 1",
            (json.dumps(schoon),),
        )
        db.commit()
        flash("Indeling van het prijzenscherm opgeslagen.", "success")
        return redirect(url_for("kiosk_prijzen_instellingen"))

    @app.route("/kiosk/prijzen/uitgelicht", methods=["POST"])
    def kiosk_uitgelicht_product_instellingen():
        """Slaat het 'uitgelicht'-product op (zie _uitgelicht_product) -- een
        leeg product-veld zet de kaart weer uit."""
        db = get_db()
        ruw_id = request.form.get("product_id", "").strip()
        product_id = int(ruw_id) if ruw_id.isdigit() else None
        titel = request.form.get("titel", "").strip()
        db.execute(
            """UPDATE kiosk_prijzen_instellingen
               SET uitgelicht_product_id = ?, uitgelicht_titel = ?
               WHERE id = 1""",
            (product_id, titel or "Snack van de week"),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Uitgelicht product opgeslagen.", "success")
        return redirect(url_for("kiosk_prijzen_instellingen"))

    @app.route("/api/tablet/uitgelicht")
    def api_tablet_uitgelicht():
        """JSON-versie voor de kiosk-tablet-app (los project, zie
        android-apps/tablet) -- "huidig" is precies _uitgelicht_product,
        "producten" dezelfde actieve-productenlijst als bij een prijs-actie
        (zie _actie_producten hierboven). Opslaan gaat via
        kiosk_uitgelicht_product_instellingen hierboven."""
        db = get_db()
        return jsonify(
            {
                "huidig": _uitgelicht_product(db),
                "producten": [
                    {"id": p["id"], "naam": p["naam"], "categorie": p["categorie"]}
                    for p in _actie_producten(db)
                ],
            }
        )

    @app.route("/kiosk/prijzen/product/<int:product_id>/toon", methods=["POST"])
    def kiosk_product_toon_wisselen(product_id):
        """Los aan/uit-schuifje per product (zie kiosk_prijzen_instellingen.html
        in de PDA-weergave) -- hetzelfde toon_op_kiosk-veld als de
        bulk-checklist hierboven, maar dan met 1 tik i.p.v. eerst aanvinken
        en dan Opslaan."""
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Product niet gevonden."}), 404
            flash("Product niet gevonden.", "error")
            return redirect(url_for("kiosk_prijzen_instellingen"))
        nieuwe_status = 0 if product["toon_op_kiosk"] else 1
        db.execute(
            "UPDATE producten SET toon_op_kiosk = ? WHERE id = ?", (nieuwe_status, product_id)
        )
        db.commit()
        if is_ajax_verzoek():
            melding = (
                f"'{product['naam']}' staat nu op het prijzenscherm."
                if nieuwe_status
                else f"'{product['naam']}' staat niet meer op het prijzenscherm."
            )
            return jsonify({"ok": True, "toon_op_kiosk": nieuwe_status, "melding": melding})
        return redirect(url_for("kiosk_prijzen_instellingen"))

    @app.route("/kiosk/prijzen/product/<int:product_id>/uitverkocht", methods=["POST"])
    def kiosk_product_uitverkocht_wisselen(product_id):
        """Losse UITVERKOCHT-knop per product (PDA-weergave van de Kiosk-
        pagina) -- puur een snelle markering voor het prijzenscherm, raakt
        de echte voorraad of actief-status niet aan."""
        db = get_db()
        product = db.execute(
            "SELECT * FROM producten WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Product niet gevonden."}), 404
            flash("Product niet gevonden.", "error")
            return redirect(url_for("kiosk_prijzen_instellingen"))
        nieuwe_status = 0 if product["kiosk_uitverkocht"] else 1
        db.execute(
            "UPDATE producten SET kiosk_uitverkocht = ? WHERE id = ?", (nieuwe_status, product_id)
        )
        db.commit()
        if is_ajax_verzoek():
            melding = (
                f"'{product['naam']}' staat als uitverkocht op het prijzenscherm."
                if nieuwe_status
                else f"'{product['naam']}' is weer beschikbaar op het prijzenscherm."
            )
            return jsonify(
                {"ok": True, "kiosk_uitverkocht": nieuwe_status, "melding": melding}
            )
        return redirect(url_for("kiosk_prijzen_instellingen"))

    @app.route("/kiosk/prijzen")
    def kiosk_prijzen_scherm():
        db = get_db()
        return render_template(
            "kiosk_prijzen_scherm.html",
            **_prijzen_render_kwargs(db, url_for("kiosk_prijzen_versie")),
        )

    @app.route("/kiosk/prijzen/versie")
    def kiosk_prijzen_versie():
        db = get_db()
        instellingen = _prijzen_instellingen(db)
        uitgelicht = _uitgelicht_product(db, instellingen)
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
                    _wedstrijddag_welkom_wedstrijden(db, instellingen),
                    _categorie_kolommen_indeling(db, instellingen),
                    uitgelicht,
                    sponsoren=_prijzen_sponsoren(db),
                ),
                "uitverkocht": _uitverkocht_namen(categorieen),
                "wedstrijddag_test": instellingen["wedstrijddag_test_teller"],
                "wedstrijddag_test_tegenstander": _eerstvolgende_bekende_tegenstander(db),
            }
        )
