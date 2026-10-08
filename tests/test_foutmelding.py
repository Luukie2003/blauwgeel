import pytest

from foutmelding import Melder, maak_rapport, masker_pad, vingerafdruk


def _fout(tekst="kapot"):
    try:
        raise ValueError(tekst)
    except ValueError as fout:
        return fout


def _context(**extra):
    return {
        "endpoint": "dashboard", "methode": "GET", "pad": "/", "gebruiker": "Luuk",
        "versie": "1.33.0", "commit": "abc1234", **extra,
    }


def test_pad_wordt_zonder_geheimen_getoond():
    assert masker_pad("/wachtwoord-instellen/AbCdEfGhIjKlMnOpQrStUvWx12345") == "/wachtwoord-instellen/…"
    assert masker_pad("/zoeken?q=geheim&token=abcdefghijklmnopqrstuvwxyz") == "/zoeken"
    assert masker_pad("/producten/12/bewerken") == "/producten/12/bewerken"
    assert masker_pad(None) == ""


def test_rapport_bevat_pagina_gebruiker_versie_en_foutmelding():
    onderwerp, tekst = maak_rapport(_fout("iets stuk"), **_context(pad="/tellen?x=1"))
    assert "ValueError" in onderwerp and "/tellen" in onderwerp
    assert "?" not in tekst.split("Pagina:")[1].splitlines()[0]  # geen query string
    assert "Luuk" in tekst and "1.33.0" in tekst and "abc1234" in tekst
    assert "ValueError: iets stuk" in tekst


def test_dezelfde_fout_wordt_een_uur_lang_niet_opnieuw_gemeld():
    melder = Melder()
    fout = _fout()
    vinger = vingerafdruk(fout)
    assert melder.mag_melden(vinger, nu=1000)
    assert not melder.mag_melden(vinger, nu=1000 + 1800)
    assert melder.mag_melden(vinger, nu=1000 + 3700)


def test_nooit_meer_dan_het_maximum_per_uur():
    melder = Melder(max_per_uur=3)
    assert all(melder.mag_melden(f"fout{i}", nu=100 + i) for i in range(3))
    assert not melder.mag_melden("fout-4", nu=200)
    assert melder.mag_melden("fout-5", nu=100 + 3700)  # een uur later weer ruimte


def test_meld_verstuurt_en_een_mislukte_mail_veroorzaakt_geen_tweede_fout(capsys):
    verstuurd = []
    assert Melder().meld(_fout(), lambda o, t: verstuurd.append((o, t)), op_achtergrond=False, **_context())
    assert len(verstuurd) == 1

    def kapot(onderwerp, tekst):
        raise OSError("smtp weg")

    assert Melder().meld(_fout(), kapot, op_achtergrond=False, **_context())
    assert "versturen mislukt" in capsys.readouterr().out


# ---------- Via de echte app ----------


@pytest.fixture
def mails(app, monkeypatch):
    verstuurd = []
    monkeypatch.setattr("mail.stuur_mail", lambda onderwerp, tekst, naar=None, **kw: verstuurd.append((onderwerp, tekst, naar)) or True)
    monkeypatch.setattr(Melder, "meld", _meld_synchroon(Melder.meld))
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.config["FOUTMELDING_MAIL"] = True
    return verstuurd


def _meld_synchroon(echt):
    def wrapper(self, fout, versturen, **kw):
        kw["op_achtergrond"] = False
        return echt(self, fout, versturen, **kw)

    return wrapper


@pytest.fixture
def fout_routes(app):
    """Pagina's die altijd crashen. Moeten bestaan vóór het eerste verzoek aan de app, dus deze
    fixture moet vóór de client in de argumenten van een test staan."""

    @app.route("/_boem")
    def boem():
        raise RuntimeError("test-explosie")

    @app.route("/_boem2")
    def boem2():
        raise RuntimeError("stil")


def test_een_serverfout_geeft_de_foutpagina_en_een_mail(fout_routes, ingelogde_client, mails, db):
    db.execute("UPDATE instellingen SET notificatie_email = 'beheer@club.nl' WHERE id = 1")
    db.commit()

    resp = ingelogde_client.get("/_boem?geheim=1")

    assert resp.status_code == 500
    assert len(mails) == 1
    onderwerp, tekst, naar = mails[0]
    assert "RuntimeError" in onderwerp and "test-explosie" in tekst
    assert naar == "beheer@club.nl"
    assert "geheim=1" not in tekst
    assert "admin" in tekst  # wie er was ingelogd

    ingelogde_client.get("/_boem")  # dezelfde fout meteen weer: niet nog eens melden
    assert len(mails) == 1


def test_een_gewone_404_of_weigering_geeft_geen_mail(ingelogde_client, mails):
    assert ingelogde_client.get("/bestaat-niet").status_code == 404
    assert mails == []


def test_tijdens_de_tests_wordt_standaard_niet_gemaild(fout_routes, ingelogde_client, app, monkeypatch):
    verstuurd = []
    monkeypatch.setattr("mail.stuur_mail", lambda *a, **k: verstuurd.append(a) or True)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    assert ingelogde_client.get("/_boem2").status_code == 500
    assert verstuurd == []
