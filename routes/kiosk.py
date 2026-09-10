import hashlib
import sqlite3
from datetime import date

from flask import flash, jsonify, redirect, render_template, request, url_for

import qr
from database import get_db
from helpers import (
    KIOSK_AFBEELDINGEN_MAP,
    KIOSK_SPONSOR_SJABLONEN,
    KIOSK_SPONSOR_SJABLOON_SLEUTELS,
    KIOSK_SPONSOR_SJABLOON_VOORBEELDEN,
    bereken_jaren_lid,
    bereken_komende_thuiswedstrijden,
    format_datum_kort,
    is_ajax_verzoek,
    now_str,
    sla_afbeelding_op,
    voeg_maanden_toe,
)

# De 3 mogelijke statussen voor een Club van 20-lid (zie
# kiosk_lid_status_wisselen) -- "niet_betaald" is bewust geen aparte
# aan/uit-vlag naast actief/inactief, maar een derde status: een lid dat nog
# niet betaald heeft, staat vanzelf niet meer als "actief" te boek totdat een
# beheerder 'm terugzet.
KIOSK_LID_STATUSSEN = {"actief", "inactief", "niet_betaald"}


def register_routes(app):
    def _voor_hash(waarde):
        """sqlite3.Row's eigen __repr__ toont een geheugenadres (verschilt
        dus bij elke nieuwe query, ook zonder inhoudelijke wijziging) --
        zet 'm daarom om naar een gewone tuple voor een stabiele repr()."""
        if isinstance(waarde, sqlite3.Row):
            return tuple(waarde)
        if isinstance(waarde, dict):
            return {k: _voor_hash(v) for k, v in waarde.items()}
        if isinstance(waarde, (list, tuple)):
            return [_voor_hash(v) for v in waarde]
        return waarde

    def _versie(*delen):
        """Compacte 'vingerafdruk' van wat er nu op een kiosk-scherm te zien
        zou zijn. De schermen pollen deze via /versie-endpoints en herladen
        zichzelf zodra 'ie verandert -- zo komt een prijswijziging, een
        nieuwe sponsor of een aangepaste instelling binnen enkele seconden
        door op de TV, zonder dat de hele pagina om de zoveel minuten voor
        niets hoeft te herladen."""
        ruw = "|".join(repr(_voor_hash(deel)) for deel in delen)
        return hashlib.md5(ruw.encode()).hexdigest()[:12]

    def _scherm_instellingen(db):
        return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()

    def _stream_instellingen(db):
        return db.execute("SELECT * FROM kiosk_stream WHERE id = 1").fetchone()

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
            # Inactief (lid dat gestopt is) blijft puur intern zichtbaar bij
            # Sponsoren & leden. Niet betaald blijft WEL op het scherm staan,
            # maar dan lichtrood -- juist als zichtbare herinnering om te
            # betalen, zie kiosk_lid_status_wisselen. sterren = 1 per
            # volledig jaar sinds de startdatum; extra_groot laat een naam
            # prominenter tonen (zie kiosk_lid_bewerken).
            leden = db.execute(
                """SELECT naam, startdatum, extra_groot, status FROM club_van_20_leden
                   WHERE status IN ('actief', 'niet_betaald') ORDER BY naam COLLATE NOCASE"""
            ).fetchall()
            namen = [
                {
                    "naam": r["naam"],
                    "sterren": bereken_jaren_lid(r["startdatum"]),
                    "extra_groot": bool(r["extra_groot"]),
                    "niet_betaald": r["status"] == "niet_betaald",
                }
                for r in leden
            ]
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
        acties = db.execute(
            """SELECT ka.*, p.naam AS product_naam FROM kiosk_acties ka
               JOIN producten p ON p.id = ka.product_id
               ORDER BY ka.id"""
        ).fetchall()
        return render_template(
            "kiosk_prijzen_instellingen.html",
            producten=producten,
            acties=acties,
            stream=_stream_instellingen(db),
        )

    @app.route("/kiosk/prijzen/stream/instellingen", methods=["POST"])
    def kiosk_stream_instellingen_opslaan():
        db = get_db()
        stream_url = request.form.get("stream_url", "").strip()
        actief = 1 if request.form.get("actief") else 0
        db.execute(
            "UPDATE kiosk_stream SET stream_url = ?, actief = ? WHERE id = 1",
            (stream_url or None, actief),
        )
        db.commit()
        flash("Livestream-instellingen opgeslagen.", "success")
        return redirect(url_for("kiosk_prijzen_instellingen"))

    @app.route("/kiosk/prijzen/stream/uitschakelen", methods=["POST"])
    def kiosk_stream_uitschakelen():
        """Zet de livestream automatisch uit zodra het prijzenscherm zelf
        signaleert dat de stream een fout geeft, stopt, of vastloopt (zie de
        video-events in kiosk_prijzen_scherm.html). Publiek endpoint zonder
        login, want het prijzenscherm zelf draait ook zonder account -- zie
        OPEN_ENDPOINTS in app.py. Zo hoeft een beheerder een vergeten
        stream niet zelf handmatig weer uit te zetten, en valt elk scherm
        dat de instellingen ophaalt vanzelf terug op de prijslijst."""
        db = get_db()
        db.execute("UPDATE kiosk_stream SET actief = 0 WHERE id = 1")
        db.commit()
        return jsonify({"ok": True})

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

    def _prijzen_categorieen(db):
        producten = db.execute(
            """SELECT * FROM producten
               WHERE actief = 1 AND toon_op_kiosk = 1
               ORDER BY categorie, naam"""
        ).fetchall()
        per_categorie = {}
        for p in producten:
            per_categorie.setdefault(p["categorie"], []).append(p)
        return sorted(per_categorie.items())

    def _acties_actief(db):
        """Actieve prijs-acties met de gegevens van het gekoppelde product --
        voor de korte, opvallende pop-up die af en toe over het
        prijzenscherm heen verschijnt (zie kiosk_prijzen_scherm.html).
        Gebruikt bewust de foto/prijs van het product zelf, geen losse
        afbeelding per actie."""
        return db.execute(
            """SELECT ka.id, ka.tekst, p.naam AS product_naam, p.verkoopprijs, p.afbeelding
               FROM kiosk_acties ka JOIN producten p ON p.id = ka.product_id
               WHERE ka.actief = 1
               ORDER BY ka.id"""
        ).fetchall()

    def _uitverkocht_namen(categorieen):
        return [p["naam"] for _, lijst in categorieen for p in lijst if p["kiosk_uitverkocht"]]

    def _prijzen_versie(categorieen, acties, stream):
        # Alleen de velden die daadwerkelijk op het scherm staan -- zo
        # triggert bijv. een gewijzigde voorraad (niet zichtbaar hier) geen
        # onnodige herlaadbeurt. Acties en de livestream tellen ook mee,
        # zodat een nieuwe/aangepaste actie of het aan-/uitzetten van de
        # stream het scherm net als de rest vanzelf bijwerkt.
        return _versie(
            [
                (
                    naam,
                    [(p["id"], p["naam"], p["verkoopprijs"], p["kiosk_uitverkocht"]) for p in lijst],
                )
                for naam, lijst in categorieen
            ],
            [(a["id"], a["tekst"], a["product_naam"], a["verkoopprijs"], a["afbeelding"]) for a in acties],
            (stream["stream_url"], stream["actief"]),
        )

    @app.route("/kiosk/prijzen")
    def kiosk_prijzen_scherm():
        db = get_db()
        categorieen = _prijzen_categorieen(db)
        acties = _acties_actief(db)
        stream = _stream_instellingen(db)
        # Simpele, JSON-vriendelijke vorm voor de pop-up-JS -- alleen wat er
        # daadwerkelijk getoond wordt, geen hele sqlite3.Row.
        acties_voor_scherm = [
            {
                "naam": a["product_naam"],
                "prijs": a["verkoopprijs"],
                "tekst": a["tekst"],
                "foto": a["afbeelding"],
            }
            for a in acties
        ]
        return render_template(
            "kiosk_prijzen_scherm.html",
            categorieen=categorieen,
            acties=acties_voor_scherm,
            versie=_prijzen_versie(categorieen, acties, stream),
            uitverkocht_namen=_uitverkocht_namen(categorieen),
            stream_url=stream["stream_url"] if stream["actief"] else None,
        )

    @app.route("/kiosk/prijzen/versie")
    def kiosk_prijzen_versie():
        db = get_db()
        categorieen = _prijzen_categorieen(db)
        acties = _acties_actief(db)
        stream = _stream_instellingen(db)
        return jsonify(
            {
                "versie": _prijzen_versie(categorieen, acties, stream),
                "uitverkocht": _uitverkocht_namen(categorieen),
            }
        )

    # ---------- Prijs-acties (onderdeel van het prijzenscherm) ----------

    def _actie_producten(db):
        """Actieve producten om als actie te kunnen kiezen -- de actie
        gebruikt daarna gewoon de foto/prijs van dat product, dus hier hoeft
        geen los uploadveld voor te komen."""
        return db.execute(
            "SELECT id, naam, categorie FROM producten WHERE actief = 1 ORDER BY categorie, naam"
        ).fetchall()

    @app.route("/kiosk/prijzen/acties")
    def kiosk_acties():
        db = get_db()
        acties = db.execute(
            """SELECT ka.*, p.naam AS product_naam, p.afbeelding AS product_afbeelding,
                      p.verkoopprijs AS product_verkoopprijs
               FROM kiosk_acties ka JOIN producten p ON p.id = ka.product_id
               ORDER BY ka.id"""
        ).fetchall()
        return render_template("kiosk_acties.html", acties=acties)

    @app.route("/kiosk/prijzen/acties/nieuw", methods=["GET", "POST"])
    def kiosk_actie_nieuw():
        db = get_db()
        if request.method == "POST":
            try:
                product_id = int(request.form.get("product_id") or 0)
            except ValueError:
                product_id = 0
            product = db.execute(
                "SELECT id FROM producten WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None:
                flash("Kies een geldig product.", "error")
            else:
                db.execute(
                    """INSERT INTO kiosk_acties (product_id, tekst, actief, aangemaakt_op)
                       VALUES (?, ?, ?, ?)""",
                    (
                        product_id,
                        request.form.get("tekst", "").strip() or None,
                        1 if request.form.get("actief") else 0,
                        now_str(),
                    ),
                )
                db.commit()
                flash("Actie toegevoegd.", "success")
                return redirect(url_for("kiosk_acties"))
        return render_template("kiosk_actie_form.html", actie=None, producten=_actie_producten(db))

    @app.route("/kiosk/prijzen/acties/<int:actie_id>/bewerken", methods=["GET", "POST"])
    def kiosk_actie_bewerken(actie_id):
        db = get_db()
        actie = db.execute("SELECT * FROM kiosk_acties WHERE id = ?", (actie_id,)).fetchone()
        if actie is None:
            flash("Actie niet gevonden.", "error")
            return redirect(url_for("kiosk_acties"))
        if request.method == "POST":
            try:
                product_id = int(request.form.get("product_id") or 0)
            except ValueError:
                product_id = 0
            product = db.execute(
                "SELECT id FROM producten WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None:
                flash("Kies een geldig product.", "error")
            else:
                db.execute(
                    "UPDATE kiosk_acties SET product_id = ?, tekst = ?, actief = ? WHERE id = ?",
                    (
                        product_id,
                        request.form.get("tekst", "").strip() or None,
                        1 if request.form.get("actief") else 0,
                        actie_id,
                    ),
                )
                db.commit()
                flash("Actie bijgewerkt.", "success")
                return redirect(url_for("kiosk_acties"))
        return render_template(
            "kiosk_actie_form.html", actie=actie, producten=_actie_producten(db)
        )

    @app.route("/kiosk/prijzen/acties/<int:actie_id>/verwijderen", methods=["POST"])
    def kiosk_actie_verwijderen(actie_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_acties WHERE id = ?", (actie_id,))
        db.commit()
        flash("Actie verwijderd.", "success")
        return redirect(url_for("kiosk_acties"))

    @app.route("/kiosk/prijzen/acties/<int:actie_id>/toon", methods=["POST"])
    def kiosk_actie_toon_wisselen(actie_id):
        """Los aan/uit-knopje per actie -- zelfde 1-tik-patroon als de
        product-schuifjes hierboven, zie de PDA-weergave van
        kiosk_prijzen_instellingen.html."""
        db = get_db()
        actie = db.execute(
            """SELECT ka.*, p.naam AS product_naam FROM kiosk_acties ka
               JOIN producten p ON p.id = ka.product_id WHERE ka.id = ?""",
            (actie_id,),
        ).fetchone()
        if actie is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Actie niet gevonden."}), 404
            flash("Actie niet gevonden.", "error")
            return redirect(url_for("kiosk_prijzen_instellingen"))
        nieuwe_status = 0 if actie["actief"] else 1
        db.execute("UPDATE kiosk_acties SET actief = ? WHERE id = ?", (nieuwe_status, actie_id))
        db.commit()
        if is_ajax_verzoek():
            melding = (
                f"Actie '{actie['product_naam']}' staat nu aan."
                if nieuwe_status
                else f"Actie '{actie['product_naam']}' staat nu uit."
            )
            return jsonify({"ok": True, "actief": nieuwe_status, "melding": melding})
        return redirect(url_for("kiosk_prijzen_instellingen"))

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
            "kiosk_sponsor_form.html",
            sponsor=None,
            sjablonen=KIOSK_SPONSOR_SJABLONEN,
            sjabloon_voorbeelden=KIOSK_SPONSOR_SJABLOON_VOORBEELDEN,
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
            "kiosk_sponsor_form.html",
            sponsor=sponsor,
            sjablonen=KIOSK_SPONSOR_SJABLONEN,
            sjabloon_voorbeelden=KIOSK_SPONSOR_SJABLOON_VOORBEELDEN,
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
            # Startdatum is altijd vandaag, de einddatum volgt automatisch
            # uit de ingestelde standaard looptijd (zie Kantine scherm
            # instellen) -- een beheerder hoeft dit dus nooit zelf uit te
            # rekenen.
            start = date.today().isoformat()
            looptijd = _scherm_instellingen(db)["club_van_20_looptijd_maanden"]
            eind = voeg_maanden_toe(start, looptijd)
            db.execute(
                """INSERT INTO club_van_20_leden
                   (naam, status, startdatum, einddatum, aangemaakt_op)
                   VALUES (?, 'actief', ?, ?, ?)""",
                (naam, start, eind, now_str()),
            )
            db.commit()
            flash(
                f"'{naam}' toegevoegd aan de Club van 20 (t/m {format_datum_kort(eind)}).",
                "success",
            )
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/sponsoren-leden/leden/<int:lid_id>/bewerken", methods=["GET", "POST"])
    def kiosk_lid_bewerken(lid_id):
        db = get_db()
        lid = db.execute(
            "SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)
        ).fetchone()
        if lid is None:
            flash("Lid niet gevonden.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        if request.method == "POST":
            naam = request.form.get("naam", "").strip()
            startdatum = request.form.get("startdatum", "").strip()
            einddatum = request.form.get("einddatum", "").strip()
            status = request.form.get("status", "").strip()
            if not naam or not startdatum or not einddatum or status not in KIOSK_LID_STATUSSEN:
                flash("Vul een naam, status, start- en einddatum in.", "error")
            else:
                db.execute(
                    """UPDATE club_van_20_leden
                       SET naam = ?, status = ?, startdatum = ?, einddatum = ?, extra_groot = ?
                       WHERE id = ?""",
                    (
                        naam,
                        status,
                        startdatum,
                        einddatum,
                        1 if request.form.get("extra_groot") else 0,
                        lid_id,
                    ),
                )
                db.commit()
                flash(f"'{naam}' bijgewerkt.", "success")
                return redirect(url_for("kiosk_sponsoren_leden"))
        return render_template("kiosk_lid_form.html", lid=lid)

    @app.route("/kiosk/sponsoren-leden/leden/<int:lid_id>/status", methods=["POST"])
    def kiosk_lid_status_wisselen(lid_id):
        db = get_db()
        lid = db.execute(
            "SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)
        ).fetchone()
        if lid is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Lid niet gevonden."}), 404
            flash("Lid niet gevonden.", "error")
            return redirect(url_for("kiosk_sponsoren_leden"))
        status = request.form.get("status", "").strip()
        if status not in KIOSK_LID_STATUSSEN:
            status = "actief"
        db.execute(
            "UPDATE club_van_20_leden SET status = ? WHERE id = ?", (status, lid_id)
        )
        db.commit()
        if is_ajax_verzoek():
            labels = {"actief": "Actief", "inactief": "Inactief", "niet_betaald": "Niet betaald"}
            return jsonify(
                {
                    "ok": True,
                    "status": status,
                    "melding": f"'{lid['naam']}' staat nu op '{labels[status]}'.",
                }
            )
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
                       club_van_20_looptijd_maanden = ?,
                       toon_wedstrijden = ?, wedstrijden_volgorde = ?
                   WHERE id = 1""",
                (
                    1 if request.form.get("toon_sponsoren") else 0,
                    _getal("sponsoren_volgorde", 1),
                    1 if request.form.get("toon_club_van_20") else 0,
                    _getal("club_van_20_volgorde", 2),
                    request.form.get("club_van_20_titel", "").strip() or "Club van 20",
                    max(1, _getal("club_van_20_namen_per_slide", 40)),
                    max(1, _getal("club_van_20_looptijd_maanden", 12)),
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
        slides = _bouw_slides(db)
        return render_template("kiosk_scherm.html", slides=slides, versie=_versie(slides))

    @app.route("/kiosk/scherm/versie")
    def kiosk_scherm_versie():
        db = get_db()
        return jsonify({"versie": _versie(_bouw_slides(db))})
