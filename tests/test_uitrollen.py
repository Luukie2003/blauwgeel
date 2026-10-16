import json
import os
import subprocess
import time

import pytest

import uitrollen

GEHEIM = "g" * 48

GIT_OMGEVING = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.nl", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.nl",
}


def _git(map_, *args):
    return subprocess.run(["git", *args], cwd=map_, env=GIT_OMGEVING, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repos(tmp_path):
    """Een 'GitHub' (origin), een 'server'-kopie en een 'laptop'-kopie, allemaal lokaal."""
    origin, server, laptop = tmp_path / "origin.git", tmp_path / "server", tmp_path / "laptop"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(laptop)], check=True, capture_output=True)
    (laptop / "app.txt").write_text("1")
    _git(laptop, "add", "."); _git(laptop, "commit", "-m", "een"); _git(laptop, "push", "-u", "origin", "HEAD:main")
    subprocess.run(["git", "clone", str(origin), str(server)], check=True, capture_output=True)
    return {"origin": origin, "server": server, "laptop": laptop}


def _nieuwe_commit(laptop, bestand="app.txt", tekst="2"):
    (laptop / bestand).write_text(tekst)
    _git(laptop, "add", "."); _git(laptop, "commit", "-m", "nog een"); _git(laptop, "push", "origin", "HEAD:main")


# ---------- Handtekening ----------


def test_handtekening_klopt_en_verloopt():
    body = b'{"actie": "bijwerken"}'
    nu = 1_000_000
    handtekening = uitrollen.maak_handtekening(GEHEIM, nu, body)

    assert uitrollen.controleer_handtekening(GEHEIM, nu, handtekening, body, nu=nu + 10)
    assert not uitrollen.controleer_handtekening(GEHEIM, nu, handtekening, body, nu=nu + 400)  # te oud
    assert not uitrollen.controleer_handtekening(GEHEIM, nu, handtekening, body, nu=nu - 400)  # uit de toekomst
    assert not uitrollen.controleer_handtekening("een-ander-geheim" * 4, nu, handtekening, body, nu=nu)
    assert not uitrollen.controleer_handtekening(GEHEIM, nu, handtekening, b"{}", nu=nu)  # andere body
    assert not uitrollen.controleer_handtekening(GEHEIM, nu + 1, handtekening, body, nu=nu)  # ander tijdstip
    assert not uitrollen.controleer_handtekening(GEHEIM, "geen-getal", handtekening, body, nu=nu)
    assert not uitrollen.controleer_handtekening(GEHEIM, nu, None, body, nu=nu)


def test_geheim_moet_lang_genoeg_zijn(tmp_path):
    pad = tmp_path / "geheim.txt"
    assert uitrollen.lees_geheim(pad) is None  # bestaat niet
    pad.write_text("kort\n")
    assert uitrollen.lees_geheim(pad) is None
    pad.write_text(GEHEIM + "\n")
    assert uitrollen.lees_geheim(pad) == GEHEIM


# ---------- Code ophalen ----------


def test_nieuwe_code_wordt_opgehaald(repos):
    _nieuwe_commit(repos["laptop"])

    resultaat = uitrollen.werk_code_bij(repos["server"])

    assert resultaat["ok"] and resultaat["gewijzigd"]
    assert resultaat["oud"] != resultaat["nieuw"]
    assert (repos["server"] / "app.txt").read_text() == "2"
    assert resultaat["pakketten"] is None  # niets aan de pakketten veranderd: niets installeren


def test_niets_nieuws_is_geen_wijziging(repos):
    resultaat = uitrollen.werk_code_bij(repos["server"])
    assert resultaat["ok"] and not resultaat["gewijzigd"]


@pytest.fixture
def pakketten(monkeypatch):
    """Vervangt het echte installeren (internet!) door een nep die bijhoudt of hij is aangeroepen."""
    aanroepen = []
    uitkomst = {"gelukt": True}

    def nep(repo):
        aanroepen.append(repo)
        return uitkomst["gelukt"], "nep-uitvoer"

    monkeypatch.setattr(uitrollen, "installeer_pakketten", nep)
    return {"aanroepen": aanroepen, "uitkomst": uitkomst}


@pytest.mark.parametrize("bestand", ["requirements-vast.txt", "requirements.txt"])
def test_gewijzigde_pakketten_worden_geinstalleerd(repos, pakketten, bestand):
    _nieuwe_commit(repos["laptop"], bestand, "Flask==9.9.9")

    resultaat = uitrollen.werk_code_bij(repos["server"])

    assert resultaat["ok"] and resultaat["gewijzigd"] and resultaat["pakketten"] == "geinstalleerd"
    assert pakketten["aanroepen"] == [repos["server"]]


def test_zonder_wijziging_in_de_pakketten_wordt_er_niets_geinstalleerd(repos, pakketten):
    _nieuwe_commit(repos["laptop"], "app.txt", "3")
    assert uitrollen.werk_code_bij(repos["server"])["pakketten"] is None
    assert pakketten["aanroepen"] == []


def test_mislukt_het_installeren_dan_gaat_de_code_terug(repos, pakketten):
    pakketten["uitkomst"]["gelukt"] = False
    voor = _git(repos["server"], "rev-parse", "HEAD")
    _nieuwe_commit(repos["laptop"], "requirements-vast.txt", "Flask==9.9.9")

    resultaat = uitrollen.werk_code_bij(repos["server"])

    assert not resultaat["ok"] and resultaat["pakketten"] == "mislukt" and resultaat["teruggedraaid"]
    assert not resultaat["gewijzigd"]
    assert _git(repos["server"], "rev-parse", "HEAD") == voor  # de server draait weer de oude code
    assert not (repos["server"] / "requirements-vast.txt").exists()
    assert "nep-uitvoer" in resultaat["uitvoer"]


def test_pip_commando_past_zich_aan_de_omgeving_aan(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.prefix", "/een/venv")
    monkeypatch.setattr("sys.base_prefix", "/een/venv")  # geen virtualenv
    zonder_venv = uitrollen.maak_pip_commando(tmp_path, python="python3.13")
    assert zonder_venv[:4] == ["python3.13", "-m", "pip", "install"] and "--user" in zonder_venv
    assert zonder_venv[-1] == str(tmp_path / "requirements-vast.txt")

    monkeypatch.setattr("sys.prefix", "/een/venv")
    monkeypatch.setattr("sys.base_prefix", "/systeem/python")  # wel in een virtualenv
    assert "--user" not in uitrollen.maak_pip_commando(tmp_path, python="python3.13")


def test_pull_overschrijft_nooit_lokale_geschiedenis(repos):
    # De server heeft een eigen, niet-gepushte commit: dan geen merge, en melden dat het mislukt.
    (repos["server"] / "lokaal.txt").write_text("x")
    _git(repos["server"], "add", "."); _git(repos["server"], "commit", "-m", "lokaal")
    voor = _git(repos["server"], "rev-parse", "HEAD")
    _nieuwe_commit(repos["laptop"])

    resultaat = uitrollen.werk_code_bij(repos["server"])

    assert not resultaat["ok"]
    assert _git(repos["server"], "rev-parse", "HEAD") == voor


def test_herstart_raakt_het_wsgi_bestand_aan(tmp_path):
    wsgi = tmp_path / "x_wsgi.py"
    wsgi.write_text("")
    os.utime(wsgi, (1, 1))

    assert uitrollen.herstart_web_app(wsgi)
    assert wsgi.stat().st_mtime > 1_000_000
    assert not uitrollen.herstart_web_app(tmp_path / "bestaat-niet.py")


# ---------- Het endpoint ----------


def _verzoek(client, geheim=GEHEIM, tijdstip=None, body=b'{"actie": "bijwerken"}', handtekening=None):
    tijdstip = int(time.time()) if tijdstip is None else tijdstip
    return client.post(
        "/uitrollen",
        data=body,
        content_type="application/json",
        headers={
            "X-Uitrol-Tijd": str(tijdstip),
            "X-Uitrol-Handtekening": handtekening or uitrollen.maak_handtekening(geheim, tijdstip, body),
        },
    )


@pytest.fixture
def geheim_aan(monkeypatch, tmp_path):
    pad = tmp_path / "uitrol_geheim.txt"
    pad.write_text(GEHEIM)
    monkeypatch.setattr(uitrollen, "GEHEIM_BESTAND", pad)


def test_endpoint_is_uitgeschakeld_zonder_geheim(client, monkeypatch, tmp_path):
    monkeypatch.setattr(uitrollen, "GEHEIM_BESTAND", tmp_path / "bestaat-niet.txt")
    assert _verzoek(client).status_code == 404


def test_endpoint_weigert_een_foute_of_verlopen_handtekening(client, geheim_aan):
    assert _verzoek(client, geheim="x" * 48).status_code == 403
    assert _verzoek(client, tijdstip=int(time.time()) - 3600).status_code == 403
    assert _verzoek(client, handtekening="sha256=00").status_code == 403
    assert client.post("/uitrollen").status_code == 403  # zonder headers


def test_endpoint_weigert_een_te_grote_body(client, geheim_aan):
    assert _verzoek(client, body=b"x" * 5000).status_code == 403


def test_endpoint_vraagt_geen_login_en_geen_csrf(client, geheim_aan, repos, monkeypatch):
    monkeypatch.setattr(uitrollen, "BASE_DIR", repos["server"])
    herstarts = []
    monkeypatch.setattr(uitrollen, "herstart_web_app", lambda *a: herstarts.append(1) or True)
    _nieuwe_commit(repos["laptop"])

    resp = _verzoek(client)
    resp.close()

    assert resp.status_code == 200
    antwoord = json.loads(resp.data)
    assert antwoord["ok"] and antwoord["gewijzigd"]
    assert herstarts == [1]  # pas na het antwoord, en alleen bij nieuwe code


def test_endpoint_herstart_niet_als_er_niets_nieuws_is(client, geheim_aan, repos, monkeypatch):
    monkeypatch.setattr(uitrollen, "BASE_DIR", repos["server"])
    herstarts = []
    monkeypatch.setattr(uitrollen, "herstart_web_app", lambda *a: herstarts.append(1) or True)

    resp = _verzoek(client)
    resp.close()

    assert resp.status_code == 200 and not json.loads(resp.data)["gewijzigd"]
    assert herstarts == []


def test_endpoint_herstart_niet_als_het_installeren_mislukt(client, geheim_aan, repos, pakketten, monkeypatch):
    monkeypatch.setattr(uitrollen, "BASE_DIR", repos["server"])
    herstarts = []
    monkeypatch.setattr(uitrollen, "herstart_web_app", lambda *a: herstarts.append(1) or True)
    pakketten["uitkomst"]["gelukt"] = False
    _nieuwe_commit(repos["laptop"], "requirements-vast.txt", "Flask==9.9.9")

    resp = _verzoek(client)
    resp.close()

    assert resp.status_code == 500
    assert json.loads(resp.data)["teruggedraaid"] is True
    assert herstarts == []


def test_mislukte_pull_geeft_een_foutmelding_zonder_herstart(client, geheim_aan, repos, monkeypatch):
    monkeypatch.setattr(uitrollen, "BASE_DIR", repos["server"])
    herstarts = []
    monkeypatch.setattr(uitrollen, "herstart_web_app", lambda *a: herstarts.append(1) or True)
    (repos["server"] / "lokaal.txt").write_text("x")
    _git(repos["server"], "add", "."); _git(repos["server"], "commit", "-m", "lokaal")
    _nieuwe_commit(repos["laptop"])

    resp = _verzoek(client)
    resp.close()

    assert resp.status_code == 500 and not json.loads(resp.data)["ok"]
    assert herstarts == []


# ---------- Status ----------


def test_status_is_openbaar_en_toont_versie_en_commit(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    antwoord = resp.get_json()
    assert set(antwoord) == {"versie", "commit"}
    assert antwoord["versie"].count(".") == 2


def test_status_telt_niet_mee_in_de_gebruiksstatistieken(ingelogde_client, db):
    ingelogde_client.get("/status")
    assert db.execute("SELECT COUNT(*) AS n FROM paginabezoeken WHERE endpoint = 'status_pagina'").fetchone()["n"] == 0


# ---------- Rooktest na het ophalen ----------


def _nep_rooktest(monkeypatch, uitkomst):
    aanroepen = []
    monkeypatch.setattr(uitrollen, "draai_rooktest", lambda repo, db: aanroepen.append(db) or uitkomst)
    return aanroepen


def test_een_geslaagde_rooktest_laat_de_nieuwe_code_staan(repos, monkeypatch):
    aanroepen = _nep_rooktest(monkeypatch, {"afgerond": True, "paginas": 120, "doorverwezen": 9, "fouten": [], "duur": 4.2})
    _nieuwe_commit(repos["laptop"])
    resultaat = uitrollen.werk_code_bij(repos["server"], rooktest_database="/data/voorraad.db")
    assert resultaat["ok"] and resultaat["gewijzigd"] and not resultaat["teruggedraaid"]
    assert aanroepen == ["/data/voorraad.db"] and resultaat["rooktest"]["paginas"] == 120


def test_fouten_in_de_rooktest_zetten_de_vorige_versie_terug(repos, monkeypatch):
    _nep_rooktest(monkeypatch, {"afgerond": True, "paginas": 40, "doorverwezen": 0, "fouten": ["/rapporten/marge: HTTP 500"]})
    _nieuwe_commit(repos["laptop"])
    resultaat = uitrollen.werk_code_bij(repos["server"], rooktest_database="/data/voorraad.db")
    assert not resultaat["ok"] and resultaat["teruggedraaid"] and not resultaat["gewijzigd"]
    assert resultaat["nieuw"] == resultaat["oud"] and (repos["server"] / "app.txt").read_text() == "1"
    assert "/rapporten/marge: HTTP 500" in resultaat["uitvoer"]


def test_een_rooktest_die_niet_kon_draaien_houdt_de_uitrol_niet_tegen(repos, monkeypatch):
    _nep_rooktest(monkeypatch, {"afgerond": False, "paginas": 0, "doorverwezen": 0, "fouten": ["duurde langer dan 150 s"]})
    _nieuwe_commit(repos["laptop"])
    resultaat = uitrollen.werk_code_bij(repos["server"], rooktest_database="/data/voorraad.db")
    assert resultaat["ok"] and resultaat["gewijzigd"]


def test_zonder_nieuwe_code_geen_rooktest(repos, monkeypatch):
    aanroepen = _nep_rooktest(monkeypatch, {"afgerond": True, "fouten": []})
    uitrollen.werk_code_bij(repos["server"], rooktest_database="/data/voorraad.db")
    assert aanroepen == []


def test_de_echte_rooktest_op_een_kopie_van_de_database(app, db, monkeypatch):
    import mail
    import rooktest

    monkeypatch.setattr(mail, "MAIL_BESCHIKBAAR", False)
    voor = db.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0]

    uitkomst = rooktest.draai(app.config["DATABASE"])

    assert uitkomst["afgerond"] and uitkomst["fouten"] == [] and uitkomst["paginas"] > 80
    assert db.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0] == voor  # de echte database is niet aangeraakt


def test_de_rooktest_vindt_een_kapotte_pagina(app, monkeypatch):
    import app as app_module
    import mail
    import rooktest

    monkeypatch.setattr(mail, "MAIL_BESCHIKBAAR", False)
    echte_create_app = app_module.create_app

    def met_kapotte_pagina(**kwargs):
        nieuwe = echte_create_app(**kwargs)

        @nieuwe.route("/kapot")
        def kapot():
            raise ZeroDivisionError("door nul gedeeld")

        return nieuwe

    monkeypatch.setattr(app_module, "create_app", met_kapotte_pagina)
    uitkomst = rooktest.draai(app.config["DATABASE"])
    assert uitkomst["afgerond"] and any("/kapot: ZeroDivisionError" in f for f in uitkomst["fouten"])


def test_draai_rooktest_zonder_script_is_niet_afgerond(tmp_path):
    assert uitrollen.draai_rooktest(tmp_path, tmp_path / "x.db")["afgerond"] is False


def test_de_rooktest_opent_ook_paginas_met_een_nummer(app, db, monkeypatch):
    """Een productpagina die alleen met echte gegevens stukgaat, wordt ook gevonden."""
    import app as app_module
    import mail
    import rooktest

    monkeypatch.setattr(mail, "MAIL_BESCHIKBAAR", False)
    pid = db.execute("SELECT id FROM producten WHERE actief = 1 ORDER BY id LIMIT 1").fetchone()[0]
    echte_create_app = app_module.create_app

    def met_kapotte_productpagina(**kwargs):
        nieuwe = echte_create_app(**kwargs)

        @nieuwe.route("/kapot/<int:product_id>")
        def kapot_product(product_id):
            raise ValueError(f"product {product_id}")

        return nieuwe

    monkeypatch.setattr(app_module, "create_app", met_kapotte_productpagina)
    uitkomst = rooktest.draai(app.config["DATABASE"])
    assert uitkomst["afgerond"] and any(f"/kapot/{pid}: ValueError" in f for f in uitkomst["fouten"])


def test_voorbeelden_voor_paginas_met_een_nummer(app, db):
    import rooktest

    with app.app_context():
        urls = [url for _, url in rooktest.te_openen_met_nummer(app, db)]
    pid = db.execute("SELECT id FROM producten WHERE actief = 1 ORDER BY id LIMIT 1").fetchone()[0]
    assert f"/producten/{pid}" in urls and f"/producten/{pid}/verkoop" in urls
    assert not any("wachtwoord-instellen" in u or "/api/barcode/" in u for u in urls)
