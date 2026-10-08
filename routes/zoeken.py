import re

from flask import current_app, jsonify, render_template, request, session, url_for

from database import get_db
from helpers import heeft_sectie_toegang

MIN_TEKENS = 2
LIMIET_LIVE = 4
LIMIET_PAGINA = 25

_DATUM_VOLLEDIG = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")
_DATUM_KORT = re.compile(r"^(\d{1,2})-(\d{1,2})$")


def _like(term):
    """LIKE-patroon dat % en _ in de zoekterm letterlijk neemt (gebruik met ESCAPE '\\')."""
    veilig = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{veilig}%"


def _datum_patroon(term):
    """Een zoekterm als 03-10-2026 of 03-10 komt in de database als 2026-10-03
    voor: geef het patroon waarmee je in die datums kunt zoeken, of None."""
    m = _DATUM_VOLLEDIG.match(term)
    if m:
        dag, maand, jaar = m.groups()
        return f"{jaar}-{int(maand):02d}-{int(dag):02d}%"
    m = _DATUM_KORT.match(term)
    if m:
        dag, maand = m.groups()
        return f"%-{int(maand):02d}-{int(dag):02d}%"
    return None


def _nl_datum(tekst):
    jaar, maand, dag = tekst[:10].split("-")
    return f"{dag}-{maand}-{jaar}" + (f" {tekst[11:16]}" if len(tekst) >= 16 else "")


def _kort(tekst, lengte=90):
    tekst = " ".join((tekst or "").split())
    return tekst if len(tekst) <= lengte else tekst[: lengte - 1].rstrip() + "…"


def zoek_alles(db, term, rol, secties, nav_items, limiet):
    """Zoekt in alles waar dit account bij mag en geeft een lijst groepen terug:
    [{"titel": ..., "resultaten": [{"titel", "detail", "url"}], "meer": bool}].
    Een groep waar niets in gevonden is, komt er niet in."""
    term = term.strip()
    if len(term) < MIN_TEKENS:
        return []
    patroon = _like(term)
    datum = _datum_patroon(term)
    groepen = []

    def toevoegen(titel, rijen, maak_resultaat):
        rijen = list(rijen)
        if rijen:
            groepen.append(
                {
                    "titel": titel,
                    "resultaten": [maak_resultaat(r) for r in rijen[:limiet]],
                    "meer": len(rijen) > limiet,
                }
            )

    def mag(sectie):
        return heeft_sectie_toegang(rol, secties, sectie)

    # Tellingen (voorraad, kassa en kluis) zoek je op teller, opmerking en datum.
    voorwaarden = "naam LIKE :p ESCAPE '\\' OR opmerking LIKE :p ESCAPE '\\'" + (" OR datum LIKE :d" if datum else "")

    # Pagina's van de app zelf ("kassa tellen", "back-ups", ...)
    laag = term.lower()
    toevoegen(
        "Pagina's",
        [i for i in nav_items if laag in i["label"].lower() or laag in i["groep"].lower()],
        lambda i: {"titel": i["label"], "detail": i["groep"], "url": url_for(i["url_endpoint"])},
    )

    if mag("voorraad"):
        toevoegen(
            "Producten",
            db.execute(
                """SELECT id, naam, categorie, subcategorie, voorraad, eenheid, actief FROM producten
                   WHERE naam LIKE :p ESCAPE '\\' OR artikelcode LIKE :p ESCAPE '\\'
                      OR categorie LIKE :p ESCAPE '\\' OR subcategorie LIKE :p ESCAPE '\\'
                   ORDER BY actief DESC, (naam NOT LIKE :begin ESCAPE '\\'), naam
                   LIMIT :max""",
                {"p": patroon, "begin": _like(term)[1:], "max": limiet + 1},
            ).fetchall(),
            lambda r: {
                "titel": r["naam"],
                "detail": f"{r['categorie']} · {r['voorraad']} {r['eenheid']}" + ("" if r["actief"] else " · inactief"),
                "url": url_for("product_detail", product_id=r["id"]),
            },
        )
        toevoegen(
            "Tellingen",
            db.execute(
                f"SELECT id, datum, naam, opmerking FROM tellingen WHERE {voorwaarden} ORDER BY datum DESC LIMIT :max",
                {"p": patroon, "d": datum, "max": limiet + 1},
            ).fetchall(),
            lambda r: {
                "titel": f"Telling {_nl_datum(r['datum'])}",
                "detail": " · ".join(x for x in (f"door {r['naam']}" if r["naam"] else "", _kort(r["opmerking"], 60)) if x),
                "url": url_for("telling_detail", telling_id=r["id"]),
            },
        )

    if mag("kassa"):
        toevoegen(
            "Kassatellingen",
            db.execute(
                f"""SELECT id, datum, naam, opmerking FROM kassa_tellingen
                    WHERE {voorwaarden} ORDER BY datum DESC LIMIT :max""",
                {"p": patroon, "d": datum, "max": limiet + 1},
            ).fetchall(),
            lambda r: {
                "titel": f"Kassatelling {_nl_datum(r['datum'])}",
                "detail": " · ".join(x for x in (f"door {r['naam']}" if r["naam"] else "", _kort(r["opmerking"], 60)) if x),
                "url": url_for("kassa_telling_detail", telling_id=r["id"]),
            },
        )

    if rol == "beheerder":
        toevoegen(
            "Kluistellingen",
            db.execute(
                f"""SELECT id, datum, naam, opmerking FROM kluis_tellingen
                    WHERE {voorwaarden} ORDER BY datum DESC LIMIT :max""",
                {"p": patroon, "d": datum, "max": limiet + 1},
            ).fetchall(),
            lambda r: {
                "titel": f"Kluistelling {_nl_datum(r['datum'])}",
                "detail": " · ".join(x for x in (f"door {r['naam']}" if r["naam"] else "", _kort(r["opmerking"], 60)) if x),
                "url": url_for("kluis_telling_detail", telling_id=r["id"]),
            },
        )

    # Het prikbord is voor iedereen.
    toevoegen(
        "Prikbord",
        db.execute(
            """SELECT id, tekst, naam, datum FROM mededelingen
               WHERE tekst LIKE :p ESCAPE '\\' OR naam LIKE :p ESCAPE '\\'
               ORDER BY datum DESC LIMIT :max""",
            {"p": patroon, "max": limiet + 1},
        ).fetchall(),
        lambda r: {
            "titel": _kort(r["tekst"], 80),
            "detail": f"{r['naam'] or 'Onbekend'} · {_nl_datum(r['datum'])}",
            "url": url_for("bijzonderheden") + f"#mededeling-{r['id']}",
        },
    )

    if mag("club_van_20"):
        toevoegen(
            "Club van 20",
            db.execute(
                """SELECT id, naam, voornaam, achternaam, team FROM club_van_20_leden
                   WHERE naam LIKE :p ESCAPE '\\' OR voornaam LIKE :p ESCAPE '\\'
                      OR achternaam LIKE :p ESCAPE '\\' OR team LIKE :p ESCAPE '\\'
                   ORDER BY naam LIMIT :max""",
                {"p": patroon, "max": limiet + 1},
            ).fetchall(),
            lambda r: {
                "titel": r["naam"],
                "detail": " · ".join(
                    x for x in (" ".join(y for y in (r["voornaam"], r["achternaam"]) if y), r["team"]) if x
                ),
                "url": url_for("club_van_20_lid_bewerken", lid_id=r["id"]),
            },
        )

    if mag("stemmen"):
        toevoegen(
            "Stemmingen",
            db.execute(
                """SELECT id, titel, omschrijving FROM stemvragen
                   WHERE titel LIKE :p ESCAPE '\\' OR omschrijving LIKE :p ESCAPE '\\'
                   ORDER BY aangemaakt_op DESC LIMIT :max""",
                {"p": patroon, "max": limiet + 1},
            ).fetchall(),
            lambda r: {
                "titel": r["titel"],
                "detail": _kort(r["omschrijving"], 70),
                "url": url_for("stemvraag_detail", stemvraag_id=r["id"]),
            },
        )

    if rol == "beheerder":
        toevoegen(
            "Accounts",
            db.execute(
                """SELECT id, naam, email, rol FROM gebruikers
                   WHERE naam LIKE :p ESCAPE '\\' OR email LIKE :p ESCAPE '\\'
                   ORDER BY naam LIMIT :max""",
                {"p": patroon, "max": limiet + 1},
            ).fetchall(),
            lambda r: {
                "titel": r["naam"],
                "detail": " · ".join(x for x in (r["rol"], r["email"]) if x),
                "url": url_for("accounts_lijst"),
            },
        )
    return groepen


def _zoek_voor_deze_gebruiker(term, limiet):
    nav_items = current_app.extensions["zichtbare_nav_items"]()
    return zoek_alles(
        get_db(), term, session.get("gebruiker_rol"), session.get("gebruiker_secties"), nav_items, limiet
    )


def register_routes(app):

    @app.route("/zoeken")
    def zoeken():
        term = request.args.get("q", "").strip()
        groepen = _zoek_voor_deze_gebruiker(term, LIMIET_PAGINA)
        return render_template(
            "zoeken.html",
            term=term,
            groepen=groepen,
            te_kort=0 < len(term) < MIN_TEKENS,
            totaal=sum(len(g["resultaten"]) for g in groepen),
        )

    @app.route("/zoeken/live")
    def zoeken_live():
        term = request.args.get("q", "").strip()
        groepen = _zoek_voor_deze_gebruiker(term, LIMIET_LIVE)
        return jsonify({"groepen": groepen, "alle_url": url_for("zoeken", q=term)})
