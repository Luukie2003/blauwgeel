"""Fase D: laadtijden en trage verzoeken in de gebruiksstatistieken, het foutenoverzicht, wie de inlogpagina opent en
robots.txt."""

from conftest import stel_csrf_token_in as _csrf

import app as app_module
from bezoeken import is_bot, soort_bezoek
from foutenlog import recente_open_fouten

GOOGLE = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
TELEFOON = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"


# ---------- Wie opent de inlogpagina ----------


def test_bots_en_mensen_uit_elkaar():
    assert is_bot(GOOGLE) and is_bot("curl/8.4") and is_bot("") and not is_bot(TELEFOON)
    assert soort_bezoek("login", TELEFOON, "/tellen") == "doorverwezen"
    assert soort_bezoek("login", TELEFOON, None) == "direct"
    assert soort_bezoek("login", GOOGLE, None) == "bot"
    assert soort_bezoek("dashboard", TELEFOON) is None


def test_bezoeken_aan_de_inlogpagina_krijgen_een_soort(client, db):
    client.get("/login", headers={"User-Agent": GOOGLE})
    client.get("/tellen", headers={"User-Agent": TELEFOON}, follow_redirects=True)  # niet ingelogd: naar /login?next=
    client.get("/login", headers={"User-Agent": TELEFOON})
    soorten = [r[0] for r in db.execute("SELECT soort FROM paginabezoeken WHERE endpoint = 'login' ORDER BY id")]
    assert soorten == ["bot", "doorverwezen", "direct"]


def test_bots_tellen_niet_mee_in_de_statistiek(ingelogde_client, client, db):
    for _ in range(3):
        client.get("/login", headers={"User-Agent": GOOGLE})
    tekst = ingelogde_client.get("/gebruiksstatistieken").data.decode()
    assert "door een zoekmachine of ander programma" in tekst and "<strong>3</strong> keer door een zoekmachine" in tekst
    assert "In totaal kwamen er 3 bezoeken van programma" in tekst


def test_robots_txt_houdt_zoekmachines_buiten_het_beheer(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200 and resp.mimetype == "text/plain"
    assert "Disallow: /" in resp.data.decode() and "Allow: /club-van-20/doe-mee" in resp.data.decode()


# ---------- Laadtijden ----------


def test_de_laadtijd_wordt_bij_een_bezoek_bewaard(ingelogde_client, db):
    ingelogde_client.get("/producten")
    duur = db.execute("SELECT duur_ms FROM paginabezoeken WHERE endpoint = 'producten_lijst' ORDER BY id DESC").fetchone()[0]
    assert duur is not None and duur >= 0


def test_een_traag_deel_van_een_pagina_wordt_apart_bewaard(ingelogde_client, db, monkeypatch):
    monkeypatch.setattr(app_module, "TRAAG_MS", 0)  # alles telt als traag
    ingelogde_client.get("/tellingen/cijfers")
    assert db.execute("SELECT COUNT(*) FROM trage_verzoeken WHERE endpoint = 'tellingen_cijfers'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM paginabezoeken WHERE endpoint = 'tellingen_cijfers'").fetchone()[0] == 0


def test_de_statistiek_toont_de_snelheid(ingelogde_client, db):
    for duur in (100, 200, 300, 5000):
        db.execute("INSERT INTO paginabezoeken (endpoint, weergave_modus, datum, duur_ms) VALUES ('tellen', 'desktop', datetime('now', 'localtime'), ?)", (duur,))
    db.execute("INSERT INTO trage_verzoeken (endpoint, duur_ms, datum) VALUES ('prognose_resultaat', 4200, datetime('now', 'localtime'))")
    db.commit()
    tekst = ingelogde_client.get("/gebruiksstatistieken").data.decode()
    assert "Snelheid" in tekst and "Tellen" in tekst and "Prognose resultaat" in tekst and "4,2 s" in tekst


# ---------- Foutmeldingen ----------


def _app_met_kapotte_pagina(app):
    app.config.update(PROPAGATE_EXCEPTIONS=False, FOUTMELDING_MAIL=False)

    @app.route("/kapot")
    def kapot():
        raise ZeroDivisionError("door nul gedeeld")

    client = app.test_client()
    client.post("/login", data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": _csrf(client)})
    return client


def test_een_serverfout_komt_in_het_foutenoverzicht(app, db):
    client = _app_met_kapotte_pagina(app)
    for _ in range(2):
        assert client.get("/kapot?token=geheim").status_code == 500
    fout = db.execute("SELECT * FROM fouten").fetchone()
    assert fout["aantal"] == 2 and fout["fouttype"] == "ZeroDivisionError" and fout["pad"] == "/kapot"
    assert "door nul gedeeld" in fout["melding"] and "geheim" not in (fout["pad"] + (fout["technisch"] or ""))
    assert recente_open_fouten(db) == 1


def test_foutmeldingen_bekijken_en_oplossen(app, db):
    client = _app_met_kapotte_pagina(app)
    client.get("/kapot")
    assert "1 foutmelding deze week" in client.get("/").data.decode()
    tekst = client.get("/fouten").data.decode()
    assert "ZeroDivisionError" in tekst and "door nul gedeeld" in tekst
    fout_id = db.execute("SELECT id FROM fouten").fetchone()[0]
    client.post(f"/fouten/{fout_id}/opgelost", data={"csrf_token": _csrf(client)})
    assert "Geen open foutmeldingen" in client.get("/fouten").data.decode()
    client.get("/kapot")  # komt hij terug, dan staat hij weer open
    assert tuple(db.execute("SELECT opgelost, aantal FROM fouten WHERE id = ?", (fout_id,)).fetchone()) == (0, 2)
