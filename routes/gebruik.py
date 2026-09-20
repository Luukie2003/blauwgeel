from datetime import datetime, timedelta

from flask import render_template, request

from database import get_db

STANDAARD_PERIODE_DAGEN = 30


def _label(endpoint):
    """Leesbaar label van een endpoint-naam zonder een tweede, apart bij te
    houden lijst met labels (die zou net als NAV_ITEMS in app.py steeds
    opnieuw bijgewerkt moeten worden) -- de Nederlandse functienamen zijn
    zelf al voldoende leesbaar zodra de underscores weg zijn."""
    return endpoint.replace("_", " ").capitalize()


def bereken_gebruiksstatistieken(db, dagen=STANDAARD_PERIODE_DAGEN):
    """Overzicht van hoe de app wordt gebruikt, voor Club >
    Gebruiksstatistieken -- gebaseerd op paginabezoeken (zie
    log_paginabezoek in app.py), niet op een externe trackingdienst."""
    sinds = (datetime.now() - timedelta(days=dagen - 1)).strftime("%Y-%m-%d 00:00")

    ruwe_dagen = db.execute(
        """SELECT date(datum) AS dag, COUNT(*) AS aantal
           FROM paginabezoeken
           WHERE datum >= ?
           GROUP BY dag
           ORDER BY dag""",
        (sinds,),
    ).fetchall()
    aantal_per_dag = {rij["dag"]: rij["aantal"] for rij in ruwe_dagen}
    dag_reeks = [
        (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(dagen - 1, -1, -1)
    ]
    max_aantal = max(aantal_per_dag.values(), default=0)
    balken = [
        {
            "datum_kort": datetime.strptime(dag, "%Y-%m-%d").strftime("%d-%m"),
            "aantal": aantal_per_dag.get(dag, 0),
            "hoogte_pct": (aantal_per_dag.get(dag, 0) / max_aantal * 100) if max_aantal else 0,
        }
        for dag in dag_reeks
    ]

    totaal_bezoeken = sum(aantal_per_dag.values())

    top_functies_ruw = db.execute(
        """SELECT endpoint, COUNT(*) AS aantal
           FROM paginabezoeken
           WHERE datum >= ?
           GROUP BY endpoint
           ORDER BY aantal DESC
           LIMIT 15""",
        (sinds,),
    ).fetchall()
    top_functies = [
        {
            "label": _label(rij["endpoint"]),
            "aantal": rij["aantal"],
            "aandeel_pct": (rij["aantal"] / totaal_bezoeken * 100) if totaal_bezoeken else 0,
        }
        for rij in top_functies_ruw
    ]

    gebruik_per_account = db.execute(
        """SELECT g.naam AS naam, COUNT(*) AS aantal, MAX(pb.datum) AS laatste_bezoek
           FROM paginabezoeken pb
           JOIN gebruikers g ON g.id = pb.gebruiker_id
           WHERE pb.datum >= ?
           GROUP BY pb.gebruiker_id
           ORDER BY aantal DESC""",
        (sinds,),
    ).fetchall()

    anoniem_aantal = db.execute(
        """SELECT COUNT(*) AS n FROM paginabezoeken
           WHERE datum >= ? AND gebruiker_id IS NULL""",
        (sinds,),
    ).fetchone()["n"]

    weergave_ruw = db.execute(
        """SELECT weergave_modus, COUNT(*) AS aantal
           FROM paginabezoeken
           WHERE datum >= ?
           GROUP BY weergave_modus""",
        (sinds,),
    ).fetchall()
    weergave_verdeling = [
        {
            "modus": rij["weergave_modus"],
            "aantal": rij["aantal"],
            "aandeel_pct": (rij["aantal"] / totaal_bezoeken * 100) if totaal_bezoeken else 0,
        }
        for rij in weergave_ruw
    ]

    return {
        "dagen": dagen,
        "balken": balken,
        "totaal_bezoeken": totaal_bezoeken,
        "top_functies": top_functies,
        "gebruik_per_account": gebruik_per_account,
        "anoniem_aantal": anoniem_aantal,
        "weergave_verdeling": weergave_verdeling,
    }


def register_routes(app):
    @app.route("/gebruiksstatistieken")
    def gebruiksstatistieken():
        dagen = request.args.get("dagen", STANDAARD_PERIODE_DAGEN, type=int)
        if dagen not in (7, 30, 90):
            dagen = STANDAARD_PERIODE_DAGEN
        db = get_db()
        return render_template(
            "gebruiksstatistieken.html",
            statistieken=bereken_gebruiksstatistieken(db, dagen),
            gekozen_dagen=dagen,
        )
