import hashlib
import json
import sqlite3
from datetime import date, timedelta

from flask import flash, jsonify, redirect, render_template, request, url_for

import qr
from database import get_db
from helpers import (
    HEX_KLEUR_PATROON,
    KIOSK_AFBEELDINGEN_MAP,
    KIOSK_ELEMENT_TYPES,
    KIOSK_OVERGANG_SLEUTELS,
    KIOSK_OVERGANGEN,
    KIOSK_SPONSOR_SJABLOON_AANGEPAST,
    KIOSK_SPONSOR_SJABLONEN,
    KIOSK_SPONSOR_SJABLOON_SLEUTELS,
    KIOSK_SPONSOR_SJABLOON_VOORBEELDEN,
    KIOSK_TEKST_GROOTTE_SLEUTELS,
    KIOSK_TEKST_GROOTTES,
    KIOSK_TIJD_PATROON,
    KIOSK_UITLIJNINGEN,
    bepaal_tegenstander,
    bereken_jaren_lid,
    bereken_komende_thuiswedstrijden,
    format_datum_kort,
    is_ajax_verzoek,
    is_trainingsavond,
    now_str,
    sla_afbeelding_op,
    vandaag_amsterdam,
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

    def _prijzen_instellingen(db):
        return db.execute("SELECT * FROM kiosk_prijzen_instellingen WHERE id = 1").fetchone()

    def _sponsor_slide(s, eigen_sjablonen, producten_bij_id=None):
        """Bouwt de slide-dict voor 1 sponsor-/mededelingrij. Bij
        sjabloon == 'aangepast' wordt het gekoppelde zelfgebouwde sjabloon
        (kiosk_sjablonen_custom) verrijkt met de eigen titel/tekst/foto van
        deze sponsor; is dat sjabloon inmiddels verwijderd, dan levert deze
        sponsor gewoon geen slide op (zelfde 'leeg blok'-filosofie als de
        rest van _bouw_slides). Een 'prijs'-element krijgt hier zijn inhoud
        vers uit producten_bij_id -- dat gebeurt bij elke opbouw opnieuw
        (elke paginalaad/versiepoll), dus een latere prijswijziging van het
        gekoppelde product komt vanzelf door, net als de rest van het scherm."""
        slide = {
            "type": "sponsor",
            "duur": s["weergave_duur_seconden"],
            "sjabloon": s["sjabloon"],
            "titel": s["titel"],
            "tekst": s["tekst"],
            "afbeelding": s["afbeelding"],
            "overgang": s["overgang"],
            "tekst_grootte": s["tekst_grootte"],
            "achtergrond_afbeelding": s["achtergrond_afbeelding"],
        }
        if s["sjabloon"] != KIOSK_SPONSOR_SJABLOON_AANGEPAST:
            return slide
        sjabloon = eigen_sjablonen.get(s["custom_sjabloon_id"])
        if sjabloon is None:
            return None
        producten_bij_id = producten_bij_id or {}
        elementen = []
        for element in json.loads(sjabloon["elementen"]):
            element = dict(element)
            if element.get("type") == "foto":
                element["inhoud"] = s["afbeelding"]
            elif element.get("type") == "titel":
                element["inhoud"] = s["titel"]
            elif element.get("type") == "tekst":
                element["inhoud"] = s["tekst"]
            elif element.get("type") == "prijs":
                product = producten_bij_id.get(element.get("product_id"))
                element["inhoud"] = (
                    ("€ " + f"{product['verkoopprijs']:.2f}".replace(".", ",")) if product else None
                )
            elementen.append(element)
        slide.update(
            {
                "custom_achtergrond_kleur": sjabloon["achtergrond_kleur"],
                "custom_achtergrond_afbeelding": sjabloon["achtergrond_afbeelding"],
                "custom_overlay_donker": bool(sjabloon["overlay_donker"]),
                "elementen": elementen,
            }
        )
        return slide

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
            # Eigen sjablonen alvast allemaal ophalen (klein aantal, geen
            # N+1 nodig) zodat _sponsor_slide er per sponsor zo 1 uit kan
            # pakken zonder telkens een losse query.
            eigen_sjablonen = {
                r["id"]: r for r in db.execute("SELECT * FROM kiosk_sjablonen_custom").fetchall()
            }
            producten_bij_id = {
                r["id"]: r
                for r in db.execute("SELECT id, verkoopprijs FROM producten").fetchall()
            }
            slides = [
                slide
                for s in sponsoren
                if (slide := _sponsor_slide(s, eigen_sjablonen, producten_bij_id)) is not None
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

    # De kolom die de zichtbaarheid van een product op het prijzenscherm
    # bepaalt hangt af van het dagtype (zie DAG_KOLOM hieronder) -- normaal
    # blijft het bestaande toon_op_kiosk, trainingsavond heeft z'n eigen
    # kolom zodat een club op trainingsavonden een kleinere/andere selectie
    # kan tonen zonder de normale instelling te verliezen.
    DAG_KOLOM = {
        "normaal": "toon_op_kiosk",
        "trainingsavond": "toon_op_kiosk_trainingsavond",
    }

    def _dag_uit_request(bron):
        dag = bron.get("dag", "normaal")
        return dag if dag in DAG_KOLOM else "normaal"

    @app.route("/kiosk/prijzen/instellingen", methods=["GET", "POST"])
    def kiosk_prijzen_instellingen():
        db = get_db()
        if request.method == "POST":
            dag = _dag_uit_request(request.form)
            kolom = DAG_KOLOM[dag]
            producten = db.execute("SELECT id FROM producten").fetchall()
            for p in producten:
                getoond = 1 if request.form.get(f"toon_{p['id']}") else 0
                db.execute(
                    f"UPDATE producten SET {kolom} = ? WHERE id = ?", (getoond, p["id"])
                )
            db.commit()
            flash("Prijzenscherm-selectie opgeslagen.", "success")
            return redirect(url_for("kiosk_prijzen_instellingen", dag=dag))

        dag = _dag_uit_request(request.args)
        kolom = DAG_KOLOM[dag]
        producten = db.execute(
            f"SELECT *, {kolom} AS toon_op_kiosk_huidig FROM producten "
            "WHERE actief = 1 ORDER BY categorie, naam"
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
            instellingen=_scherm_instellingen(db),
            prijzen_instellingen=_prijzen_instellingen(db),
            gekozen_dag=dag,
            categorie_kolommen_namen=_verdeel_namen_over_kolommen(
                _alle_kiosk_categorie_namen(db), _categorie_kolommen_indeling(db)
            ),
            alle_producten=_sjabloon_producten(db),
            uitgelicht=_uitgelicht_product(db),
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

    def _prijzen_categorieen(db, dag="normaal", uitgelicht_product_id=None):
        # dag bepaalt welke zichtbaarheidskolom geldt (zie DAG_KOLOM
        # hierboven) -- dag komt hier nooit rechtstreeks van een gebruiker,
        # alleen via _dag_uit_request (die 'm al tegen DAG_KOLOM valideert)
        # of via het automatische is_trainingsavond()-onderscheid hieronder,
        # dus de kolomnaam is altijd één van de twee vaste, hardcoded namen.
        kolom = DAG_KOLOM.get(dag, "toon_op_kiosk")
        producten = db.execute(
            f"""SELECT * FROM producten
               WHERE actief = 1 AND {kolom} = 1
               ORDER BY categorie, naam"""
        ).fetchall()
        opties_per_product = {}
        for optie in db.execute(
            "SELECT * FROM product_prijsopties ORDER BY product_id, volgorde, id"
        ).fetchall():
            opties_per_product.setdefault(optie["product_id"], []).append(optie)

        per_categorie = {}
        for p in producten:
            if uitgelicht_product_id is not None and p["id"] == uitgelicht_product_id:
                # Dit product wordt al apart, groot en los van zijn categorie
                # getoond (zie _uitgelicht_product) -- niet nog eens hier.
                continue
            # kiosk_categorie is een optionele override, alleen voor de
            # indeling op dit scherm -- de echte categorie (tellen,
            # rapportage) blijft ongemoeid. Handig voor een product met
            # prijsopties (bijv. een fust in categorie 'Telling') dat je
            # liever onder een bestaande verkoopcategorie toont, bijv.
            # 'Bier'.
            weergave_categorie = p["kiosk_categorie"] or p["categorie"]
            opties = opties_per_product.get(p["id"])
            if opties:
                # Een fust-achtig product wordt zelf niet in zijn geheel
                # verkocht: i.p.v. de eigen verkoopprijs tonen we de losse
                # porties die eruit getapt/geschonken worden (bijv. pitcher
                # of glas, zie product_form.html). Is het hele product als
                # uitverkocht gemarkeerd (leeg fust), dan geldt dat voor elke
                # portie ervan.
                for optie in opties:
                    per_categorie.setdefault(weergave_categorie, []).append(
                        {
                            "id": optie["id"],
                            "naam": optie["naam"],
                            # Los van "naam" (de portienaam, bijv. "Klein
                            # glas") bewaard voor _uitverkocht_namen hieronder
                            # -- die moet het onderliggende product tonen
                            # (bijv. "Jupiler"), niet de portienaam.
                            "product_naam": p["naam"],
                            "verkoopprijs": optie["prijs"],
                            "kiosk_uitverkocht": p["kiosk_uitverkocht"],
                        }
                    )
            else:
                per_categorie.setdefault(weergave_categorie, []).append(p)
        # Op naam sorteren binnen de groep: door de kiosk_categorie-override
        # kunnen producten uit verschillende echte categorieën in dezelfde
        # groep belanden, in een andere volgorde dan de SQL ORDER BY hierboven
        # (die op de ECHTE categorie sorteert) garandeert.
        for lijst in per_categorie.values():
            lijst.sort(key=lambda p: p["naam"].lower())
        return sorted(per_categorie.items())

    def _uitgelicht_product(db):
        """Het door de beheerder gekozen 'uitgelicht'-product (bijv. Snack
        van de week, zie kiosk_prijzen_instellingen.html) -- groot en
        omlijnd getoond op het prijzenscherm, los van zijn eigen categorie.
        None als er niets gekozen is, of het gekozen product inmiddels
        verwijderd/gedeactiveerd is (dan verdwijnt de kaart gewoon, net als
        de rest van dit scherm bij een leeg blok -- zie _bouw_slides)."""
        instellingen = _prijzen_instellingen(db)
        product_id = instellingen["uitgelicht_product_id"]
        if product_id is None:
            return None
        p = db.execute(
            "SELECT id, naam, verkoopprijs, kiosk_uitverkocht FROM producten WHERE id = ? AND actief = 1",
            (product_id,),
        ).fetchone()
        if p is None:
            return None
        return {
            "titel": instellingen["uitgelicht_titel"],
            "product_id": p["id"],
            "naam": p["naam"],
            "verkoopprijs": p["verkoopprijs"],
            "kiosk_uitverkocht": p["kiosk_uitverkocht"],
        }

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
        # Bij prijsopties (fust-achtige producten, zie hierboven) is "naam"
        # de portienaam (bijv. "Klein glas"); voor de uitverkocht-popup moet
        # het onderliggende product getoond worden ("product_naam", bijv.
        # "Jupiler"), en maar 1x per product, ook al zijn er meerdere
        # uitverkochte porties van hetzelfde product.
        namen = []
        for _, lijst in categorieen:
            for p in lijst:
                if not p["kiosk_uitverkocht"]:
                    continue
                naam = p["product_naam"] if "product_naam" in p.keys() else p["naam"]
                if naam not in namen:
                    namen.append(naam)
        return namen

    def _bardiensten_vandaag(db):
        """Bardiensten rond vandaag, op datum+tijd gesorteerd -- geen
        wekelijks terugkerend rooster, dus alleen echte datums tellen mee
        (zie kiosk_bardienst hieronder voor de planning zelf). Haalt bewust
        ook gisteren en morgen op (serverdatum) i.p.v. alleen exact vandaag:
        de server draait op UTC terwijl het scherm in Europe/Amsterdam
        staat, dus rond middernacht kan de serverdatum een paar uur
        achterlopen op de kloktijd van de kantine zelf. Welke dienst nu
        precies actief is (en het afhandelen van een dienst die middernacht
        overschrijdt, bijv. 22:00-01:00) wordt daarom client-side bepaald
        met de eigen klok van het scherm, zie kiosk_prijzen_scherm.html."""
        vandaag = date.today()
        return db.execute(
            "SELECT * FROM kiosk_bardiensten WHERE datum BETWEEN ? AND ? ORDER BY datum, start_tijd",
            ((vandaag - timedelta(days=1)).isoformat(), (vandaag + timedelta(days=1)).isoformat()),
        ).fetchall()

    def _bardiensten_voor_scherm(bardiensten):
        return [
            {"datum": b["datum"], "start_tijd": b["start_tijd"], "eind_tijd": b["eind_tijd"], "namen": b["namen"]}
            for b in bardiensten
        ]

    def _dag_type_vandaag():
        """'trainingsavond' of 'normaal' -- bepaalt welke productselectie het
        prijzenscherm nu toont (zie DAG_KOLOM/_prijzen_categorieen).
        vandaag_amsterdam() i.p.v. date.today() (serverdatum, UTC) om
        dezelfde reden als _bardienst_uit_formulier hieronder: anders wisselt
        de selectie een paar uur te vroeg/laat rond middernacht."""
        return "trainingsavond" if is_trainingsavond(vandaag_amsterdam()) else "normaal"

    def _wedstrijddag_welkom_wedstrijden(db):
        """Eigen thuiswedstrijden vandaag, voor de welkomstbanner/-popup op
        het prijzenscherm (instelling: zie kiosk_wedstrijddag_welkom_instellingen)
        -- lege lijst als de banner uitstaat of er niets gepland staat.
        Op tijd gesorteerd (onbekende tijd/"hele dag" achteraan) zodat de
        client precies weet in welke volgorde de wedstrijden vandaag
        plaatsvinden -- de client bepaalt met die volgorde en de eigen klok
        welk tijdvak nu actief is (zie werkWedstrijddagWelkomBij() in
        kiosk_prijzen_scherm.html), net als bij de bardienst-balk en om
        dezelfde reden: geen servertijdzone-afhankelijkheid."""
        instellingen = _prijzen_instellingen(db)
        if not instellingen["wedstrijddag_welkom_actief"]:
            return []
        vandaag = vandaag_amsterdam().isoformat()
        wedstrijden = db.execute(
            """SELECT tijd, omschrijving FROM wedstrijden
               WHERE thuis = 1 AND datum = ?
               ORDER BY tijd IS NULL, tijd, team""",
            (vandaag,),
        ).fetchall()
        resultaat = []
        gezien = set()
        for w in wedstrijden:
            naam = bepaal_tegenstander(w["omschrijving"])
            if not naam or naam in gezien:
                continue
            gezien.add(naam)
            resultaat.append({"tijd": w["tijd"], "tegenstander": naam})
        return resultaat

    def _eerstvolgende_bekende_tegenstander(db):
        """Voor de testknop bij de wedstrijddag-welkomstmelding (zie
        kiosk_wedstrijddag_welkom_testen) -- toont daar een echte naam i.p.v.
        het kale "Tegenstander"-placeholder, ook als er vandaag geen eigen
        thuiswedstrijd gepland staat (de test moet altijd werken, los van de
        instelling/datum, dus geen 'wedstrijddag_welkom_actief'-check zoals
        bij _wedstrijddag_welkom_wedstrijden hierboven). Pakt de eerste
        aankomende thuiswedstrijd waarvan de tegenstander uit de omschrijving
        te herleiden is; None als er niets (meer) gepland staat."""
        vandaag = vandaag_amsterdam().isoformat()
        wedstrijden = db.execute(
            """SELECT omschrijving FROM wedstrijden
               WHERE thuis = 1 AND datum >= ?
               ORDER BY datum, tijd IS NULL, tijd""",
            (vandaag,),
        ).fetchall()
        for w in wedstrijden:
            naam = bepaal_tegenstander(w["omschrijving"])
            if naam:
                return naam
        return None

    def _categorie_kolommen_indeling(db):
        """Leest de opgeslagen kolomindeling (zie kiosk_prijzen_instellingen.html,
        de sleep-interface) -- {"1": [...namen], "2": [...], "3": [...]}.
        Onherkenbare/kapotte inhoud (zou hier nooit moeten voorkomen, alleen
        via _categorie_kolommen_opslaan hieronder geschreven) valt terug op
        een lege indeling i.p.v. de pagina te laten crashen."""
        ruw = _prijzen_instellingen(db)["categorie_kolommen"]
        try:
            data = json.loads(ruw)
        except (TypeError, ValueError):
            data = {}
        return {
            kolom: [naam for naam in data.get(kolom, []) if isinstance(naam, str)]
            for kolom in ("1", "2", "3")
        }

    def _alle_kiosk_categorie_namen(db):
        """Alle categorie-koppen die op het prijzenscherm kunnen voorkomen,
        op normale dagen én trainingsavonden samen -- zodat de sleep-indeling
        ook categorieën toont die vandaag toevallig niet in beeld zijn (bijv.
        een trainingsavond-only categorie), en die niet pas verschijnen op
        het moment dat ze voor het eerst zichtbaar worden."""
        namen = set()
        for dag in DAG_KOLOM:
            for naam, _ in _prijzen_categorieen(db, dag):
                namen.add(naam)
        return sorted(namen, key=str.lower)

    def _verdeel_namen_over_kolommen(namen, indeling):
        """Kern van de kolomindeling: verdeelt een lijst categorienamen over
        de 3 vaste kolommen volgens de opgeslagen (gesleepte) indeling. Een
        naam die er niet in voorkomt -- nieuw, of nog nooit gesleept --
        belandt achteraan in kolom 1, zodat 'ie zichtbaar blijft i.p.v. te
        verdwijnen totdat iemand 'm een plek geeft. Gebruikt voor zowel de
        sleep-interface (alleen namen, zie kiosk_prijzen_instellingen) als
        het prijzenscherm zelf (naam + producten, zie _verdeel_over_kolommen
        hieronder)."""
        beschikbaar = set(namen)
        geplaatst = set()
        kolommen = []
        for kolom in ("1", "2", "3"):
            lijst = [
                naam
                for naam in indeling.get(kolom, [])
                if naam in beschikbaar and naam not in geplaatst
            ]
            geplaatst.update(lijst)
            kolommen.append(lijst)
        for naam in namen:
            if naam not in geplaatst:
                kolommen[0].append(naam)
        return kolommen

    def _verdeel_over_kolommen(categorieen, indeling):
        bij_naam = dict(categorieen)
        namen_per_kolom = _verdeel_namen_over_kolommen(
            [naam for naam, _ in categorieen], indeling
        )
        return [[(naam, bij_naam[naam]) for naam in namen] for namen in namen_per_kolom]

    def _prijzen_versie(categorieen, acties, bardiensten, wedstrijden_vandaag, indeling, uitgelicht, *extra):
        # Alleen de velden die daadwerkelijk op het scherm staan -- zo
        # triggert bijv. een gewijzigde voorraad (niet zichtbaar hier) geen
        # onnodige herlaadbeurt. Acties, de bardiensten van vandaag, de
        # thuiswedstrijden van vandaag, de kolomindeling en het uitgelichte
        # product tellen ook mee, zodat een wijziging daaraan het scherm net
        # als de rest vanzelf bijwerkt. *extra is puur om /kiosk/tv (zie
        # kiosk_tv) een eigen versie-'namespace' te geven, zodat het
        # wisselen tussen prijzen/dia's ook zonder inhoudelijke wijziging
        # als een update gezien wordt.
        return _versie(
            [
                (
                    naam,
                    [(p["id"], p["naam"], p["verkoopprijs"], p["kiosk_uitverkocht"]) for p in lijst],
                )
                for naam, lijst in categorieen
            ],
            [(a["id"], a["tekst"], a["product_naam"], a["verkoopprijs"], a["afbeelding"]) for a in acties],
            [(b["id"], b["datum"], b["start_tijd"], b["eind_tijd"], b["namen"]) for b in bardiensten],
            [(w["tijd"], w["tegenstander"]) for w in wedstrijden_vandaag],
            indeling,
            (
                uitgelicht["titel"],
                uitgelicht["product_id"],
                uitgelicht["naam"],
                uitgelicht["verkoopprijs"],
                uitgelicht["kiosk_uitverkocht"],
            )
            if uitgelicht
            else None,
            *extra,
        )

    def _prijzen_render_kwargs(db, versie_url, extra_versie=None):
        """Gedeelde render-context voor zowel /kiosk/prijzen als de
        prijzen-stand van /kiosk/tv (zie kiosk_tv) -- 1 plek voor de opbouw
        zodat beide altijd exact hetzelfde renderen."""
        uitgelicht = _uitgelicht_product(db)
        categorieen = _prijzen_categorieen(
            db,
            _dag_type_vandaag(),
            uitgelicht_product_id=uitgelicht["product_id"] if uitgelicht else None,
        )
        acties = _acties_actief(db)
        bardiensten = _bardiensten_vandaag(db)
        wedstrijden_vandaag = _wedstrijddag_welkom_wedstrijden(db)
        indeling = _categorie_kolommen_indeling(db)
        acties_voor_scherm = [
            {
                "naam": a["product_naam"],
                "prijs": a["verkoopprijs"],
                "tekst": a["tekst"],
                "foto": a["afbeelding"],
            }
            for a in acties
        ]
        extra = (extra_versie,) if extra_versie else ()
        instellingen = _prijzen_instellingen(db)
        return {
            "categorieen_kolommen": _verdeel_over_kolommen(categorieen, indeling),
            "acties": acties_voor_scherm,
            "uitgelicht": uitgelicht,
            "versie": _prijzen_versie(
                categorieen, acties, bardiensten, wedstrijden_vandaag, indeling, uitgelicht, *extra
            ),
            "versie_url": versie_url,
            "uitverkocht_namen": _uitverkocht_namen(categorieen),
            "bardiensten_vandaag": _bardiensten_voor_scherm(bardiensten),
            "wedstrijden_vandaag": wedstrijden_vandaag,
            "wedstrijddag_welkom_tekst": instellingen["wedstrijddag_welkom_tekst"],
            "wedstrijddag_test": instellingen["wedstrijddag_test_teller"],
        }

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
        uitgelicht = _uitgelicht_product(db)
        categorieen = _prijzen_categorieen(
            db,
            _dag_type_vandaag(),
            uitgelicht_product_id=uitgelicht["product_id"] if uitgelicht else None,
        )
        acties = _acties_actief(db)
        bardiensten = _bardiensten_vandaag(db)
        return jsonify(
            {
                "versie": _prijzen_versie(
                    categorieen,
                    acties,
                    bardiensten,
                    _wedstrijddag_welkom_wedstrijden(db),
                    _categorie_kolommen_indeling(db),
                    uitgelicht,
                ),
                "uitverkocht": _uitverkocht_namen(categorieen),
                "wedstrijddag_test": _prijzen_instellingen(db)["wedstrijddag_test_teller"],
                "wedstrijddag_test_tegenstander": _eerstvolgende_bekende_tegenstander(db),
            }
        )

    # ---------- Bardienst (onderdeel van het prijzenscherm) ----------

    def _bardienst_uit_formulier():
        datum = request.form.get("datum", "").strip()
        try:
            date.fromisoformat(datum)
        except ValueError:
            # vandaag_amsterdam() i.p.v. date.today() (serverdatum, UTC op
            # deze hosting) -- anders komt een lege/ongeldige datum rond
            # middernacht een dag te vroeg te staan, precies de bug die de
            # bardienst-datumfix van 16 september 2026 al voor het scherm
            # oploste.
            datum = vandaag_amsterdam().isoformat()
        start_tijd = request.form.get("start_tijd", "").strip()
        if not KIOSK_TIJD_PATROON.match(start_tijd):
            start_tijd = "00:00"
        eind_tijd = request.form.get("eind_tijd", "").strip()
        if not KIOSK_TIJD_PATROON.match(eind_tijd):
            eind_tijd = "23:59"
        return {
            "datum": datum,
            "start_tijd": start_tijd,
            "eind_tijd": eind_tijd,
            "namen": request.form.get("namen", "").strip(),
        }

    @app.route("/kiosk/prijzen/bardienst")
    def kiosk_bardienst():
        db = get_db()
        bardiensten = db.execute(
            "SELECT * FROM kiosk_bardiensten ORDER BY datum, start_tijd"
        ).fetchall()
        return render_template(
            "kiosk_bardienst.html", bardiensten=bardiensten, vandaag=vandaag_amsterdam().isoformat()
        )

    @app.route("/api/tablet/bardiensten")
    def api_tablet_bardiensten():
        """JSON-lijst voor de kiosk-tablet-app (los project, zie
        android-apps/tablet) -- schrijven gaat via dezelfde routes hieronder
        (nieuw/bewerken/verwijderen), die bij is_ajax_verzoek() JSON i.p.v.
        een redirect teruggeven."""
        db = get_db()
        bardiensten = db.execute(
            "SELECT * FROM kiosk_bardiensten ORDER BY datum, start_tijd"
        ).fetchall()
        return jsonify(
            {
                "bardiensten": [
                    {
                        "id": b["id"],
                        "datum": b["datum"],
                        "start_tijd": b["start_tijd"],
                        "eind_tijd": b["eind_tijd"],
                        "namen": b["namen"],
                    }
                    for b in bardiensten
                ]
            }
        )

    @app.route("/kiosk/prijzen/bardienst/nieuw", methods=["POST"])
    def kiosk_bardienst_nieuw():
        gegevens = _bardienst_uit_formulier()
        if not gegevens["namen"]:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Vul in wie er bardienst heeft."})
            flash("Vul in wie er bardienst heeft.", "error")
            return redirect(url_for("kiosk_bardienst"))
        db = get_db()
        db.execute(
            """INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op)
               VALUES (?, ?, ?, ?, ?)""",
            (gegevens["datum"], gegevens["start_tijd"], gegevens["eind_tijd"], gegevens["namen"], now_str()),
        )
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Bardienst toegevoegd.", "success")
        return redirect(url_for("kiosk_bardienst"))

    @app.route("/kiosk/prijzen/bardienst/<int:bardienst_id>/bewerken", methods=["GET", "POST"])
    def kiosk_bardienst_bewerken(bardienst_id):
        db = get_db()
        bardienst = db.execute(
            "SELECT * FROM kiosk_bardiensten WHERE id = ?", (bardienst_id,)
        ).fetchone()
        if bardienst is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Bardienst niet gevonden."}), 404
            flash("Bardienst niet gevonden.", "error")
            return redirect(url_for("kiosk_bardienst"))

        if request.method == "POST":
            gegevens = _bardienst_uit_formulier()
            if not gegevens["namen"]:
                if is_ajax_verzoek():
                    return jsonify({"ok": False, "fout": "Vul in wie er bardienst heeft."})
                flash("Vul in wie er bardienst heeft.", "error")
                return redirect(url_for("kiosk_bardienst_bewerken", bardienst_id=bardienst_id))
            db.execute(
                """UPDATE kiosk_bardiensten
                   SET datum = ?, start_tijd = ?, eind_tijd = ?, namen = ?
                   WHERE id = ?""",
                (
                    gegevens["datum"],
                    gegevens["start_tijd"],
                    gegevens["eind_tijd"],
                    gegevens["namen"],
                    bardienst_id,
                ),
            )
            db.commit()
            if is_ajax_verzoek():
                return jsonify({"ok": True})
            flash("Bardienst bijgewerkt.", "success")
            return redirect(url_for("kiosk_bardienst"))
        return render_template("kiosk_bardienst_form.html", bardienst=bardienst)

    @app.route("/kiosk/prijzen/bardienst/<int:bardienst_id>/verwijderen", methods=["POST"])
    def kiosk_bardienst_verwijderen(bardienst_id):
        db = get_db()
        db.execute("DELETE FROM kiosk_bardiensten WHERE id = ?", (bardienst_id,))
        db.commit()
        if is_ajax_verzoek():
            return jsonify({"ok": True})
        flash("Bardienst verwijderd.", "success")
        return redirect(url_for("kiosk_bardienst"))

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

    @app.route("/api/tablet/acties")
    def api_tablet_acties():
        """JSON-lijst voor de kiosk-tablet-app (los project, zie
        android-apps/tablet) -- "producten" hierin zijn de actieve producten
        waaruit gekozen kan worden bij het aanmaken/bewerken van een actie
        (zie _actie_producten hierboven). Schrijven gaat via de routes
        hieronder (nieuw/bewerken/verwijderen/toon), die bij
        is_ajax_verzoek() JSON i.p.v. een redirect teruggeven."""
        db = get_db()
        acties = db.execute(
            """SELECT ka.*, p.naam AS product_naam
               FROM kiosk_acties ka JOIN producten p ON p.id = ka.product_id
               ORDER BY ka.id"""
        ).fetchall()
        return jsonify(
            {
                "acties": [
                    {
                        "id": a["id"],
                        "product_id": a["product_id"],
                        "product_naam": a["product_naam"],
                        "tekst": a["tekst"] or "",
                        "actief": bool(a["actief"]),
                    }
                    for a in acties
                ],
                "producten": [
                    {"id": p["id"], "naam": p["naam"], "categorie": p["categorie"]}
                    for p in _actie_producten(db)
                ],
            }
        )

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
                if is_ajax_verzoek():
                    return jsonify({"ok": False, "fout": "Kies een geldig product."})
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
                if is_ajax_verzoek():
                    return jsonify({"ok": True})
                flash("Actie toegevoegd.", "success")
                return redirect(url_for("kiosk_acties"))
        return render_template("kiosk_actie_form.html", actie=None, producten=_actie_producten(db))

    @app.route("/kiosk/prijzen/acties/<int:actie_id>/bewerken", methods=["GET", "POST"])
    def kiosk_actie_bewerken(actie_id):
        db = get_db()
        actie = db.execute("SELECT * FROM kiosk_acties WHERE id = ?", (actie_id,)).fetchone()
        if actie is None:
            if is_ajax_verzoek():
                return jsonify({"ok": False, "fout": "Actie niet gevonden."}), 404
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
                if is_ajax_verzoek():
                    return jsonify({"ok": False, "fout": "Kies een geldig product."})
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
                if is_ajax_verzoek():
                    return jsonify({"ok": True})
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
        if is_ajax_verzoek():
            return jsonify({"ok": True})
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
        return render_template(
            "kiosk_sponsoren_leden.html",
            sponsoren=sponsoren,
            leden=leden,
            sjabloon_labels=dict(KIOSK_SPONSOR_SJABLONEN),
            sjablonen_custom=sjablonen_custom,
            aantal_elementen_per_sjabloon=aantal_elementen_per_sjabloon,
            gebruik_per_sjabloon=gebruik_per_sjabloon,
            instellingen=_scherm_instellingen(db),
        )

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
            if is_ajax_verzoek():
                return jsonify({"ok": True, "melding": "Instellingen voor het kantine scherm opgeslagen."})
            flash("Instellingen voor het kantine scherm opgeslagen.", "success")
            return redirect(url_for("kiosk_sponsoren_leden"))

        # Geen eigen pagina meer -- de instellingen staan nu op hetzelfde
        # scherm als de dia's zelf (zie kiosk_sponsoren_leden), dus een GET
        # hierheen (bijv. een oude bladwijzer) stuurt gewoon door.
        return redirect(url_for("kiosk_sponsoren_leden"))

    @app.route("/kiosk/scherm")
    def kiosk_scherm():
        db = get_db()
        slides = _bouw_slides(db)
        return render_template(
            "kiosk_scherm.html",
            slides=slides,
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
        uitgelicht = _uitgelicht_product(db)
        categorieen = _prijzen_categorieen(
            db,
            _dag_type_vandaag(),
            uitgelicht_product_id=uitgelicht["product_id"] if uitgelicht else None,
        )
        acties = _acties_actief(db)
        bardiensten = _bardiensten_vandaag(db)
        return jsonify(
            {
                "versie": _prijzen_versie(
                    categorieen,
                    acties,
                    bardiensten,
                    _wedstrijddag_welkom_wedstrijden(db),
                    _categorie_kolommen_indeling(db),
                    uitgelicht,
                    "tv",
                ),
                "uitverkocht": _uitverkocht_namen(categorieen),
                "wedstrijddag_test": _prijzen_instellingen(db)["wedstrijddag_test_teller"],
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
