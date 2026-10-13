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


def _percentiel(waarden, fractie):
    waarden = sorted(waarden)
    return waarden[min(len(waarden) - 1, int(fractie * len(waarden)))] if waarden else None


def _snelheid(db, sinds):
    """De traagste pagina's (mediaan en de 10% traagste bezoeken) en wat er los van een paginabezoek traag was."""
    per_pagina = {}
    for r in db.execute(
        """SELECT endpoint, duur_ms FROM paginabezoeken
           WHERE datum >= ? AND duur_ms IS NOT NULL AND COALESCE(soort, '') != 'bot'""",
        (sinds,),
    ).fetchall():
        per_pagina.setdefault(r["endpoint"], []).append(r["duur_ms"])
    paginas = sorted(
        (
            {"label": _label(e), "aantal": len(d), "mediaan": _percentiel(d, 0.5), "p90": _percentiel(d, 0.9)}
            for e, d in per_pagina.items()
            if len(d) >= 3
        ),
        key=lambda x: -x["mediaan"],
    )[:12]
    traag = [
        {"label": _label(r["endpoint"]), "aantal": r["aantal"], "gemiddeld": round(r["gemiddeld"]), "langste": r["langste"]}
        for r in db.execute(
            """SELECT endpoint, COUNT(*) AS aantal, AVG(duur_ms) AS gemiddeld, MAX(duur_ms) AS langste
               FROM trage_verzoeken WHERE datum >= ? GROUP BY endpoint ORDER BY aantal DESC, langste DESC LIMIT 10""",
            (sinds,),
        ).fetchall()
    ]
    return {"snelheid": paginas, "trage_verzoeken": traag}


def _inloggen(db, sinds):
    """Hoe vaak de inlogpagina is geopend, en door wie: een mens die niet (meer) ingelogd was, een mens die zelf naar
    de inlogpagina ging, of een programma (zoekmachine, linkvoorbeeld). Bezoeken van voor 1.45.0 hebben nog geen soort."""
    tellers = {"doorverwezen": 0, "direct": 0, "bot": 0, "onbekend": 0}
    for r in db.execute(
        """SELECT COALESCE(soort, 'onbekend') AS soort, COUNT(*) AS n FROM paginabezoeken
           WHERE datum >= ? AND endpoint = 'login' GROUP BY soort""",
        (sinds,),
    ).fetchall():
        tellers[r["soort"] if r["soort"] in tellers else "onbekend"] += r["n"]
    bots_totaal = db.execute(
        "SELECT COUNT(*) FROM paginabezoeken WHERE datum >= ? AND soort = 'bot'", (sinds,)
    ).fetchone()[0]
    return {**tellers, "totaal": sum(tellers.values()), "bots_totaal": bots_totaal}


def bereken_gebruiksstatistieken(db, dagen=STANDAARD_PERIODE_DAGEN):
    """Overzicht van hoe de app wordt gebruikt, voor Club >
    Gebruiksstatistieken -- gebaseerd op paginabezoeken (zie
    log_paginabezoek in app.py), niet op een externe trackingdienst."""
    sinds = (datetime.now() - timedelta(days=dagen - 1)).strftime("%Y-%m-%d 00:00")

    ruwe_dagen = db.execute(
        """SELECT date(datum) AS dag, COUNT(*) AS aantal
           FROM paginabezoeken
           WHERE datum >= ? AND COALESCE(soort, '') != 'bot'
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
           WHERE datum >= ? AND COALESCE(soort, '') != 'bot'
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
           WHERE pb.datum >= ? AND COALESCE(pb.soort, '') != 'bot'
           GROUP BY pb.gebruiker_id
           ORDER BY aantal DESC""",
        (sinds,),
    ).fetchall()

    anoniem_aantal = db.execute(
        """SELECT COUNT(*) AS n FROM paginabezoeken
           WHERE datum >= ? AND gebruiker_id IS NULL AND COALESCE(soort, '') != 'bot'""",
        (sinds,),
    ).fetchone()["n"]

    weergave_ruw = db.execute(
        """SELECT weergave_modus, COUNT(*) AS aantal
           FROM paginabezoeken
           WHERE datum >= ? AND COALESCE(soort, '') != 'bot'
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
        **_snelheid(db, sinds),
        "inloggen": _inloggen(db, sinds),
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
