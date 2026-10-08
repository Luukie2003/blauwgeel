from jinja2 import TemplateNotFound

from app import create_app


def test_alle_sjablonen_zijn_te_compileren(app):
    """Een syntaxfout in een sjabloon dat zelden gebruikt wordt, valt anders pas op als iemand die
    pagina opent."""
    fouten = []
    for naam in app.jinja_env.list_templates():
        try:
            app.jinja_env.get_template(naam)
        except Exception as fout:
            fouten.append(f"{naam}: {fout}")
    assert not fouten, "\n".join(fouten)


def _niet_van_schijf(omgeving, sjabloon):
    raise TemplateNotFound(f"{sjabloon} (van schijf lezen mag niet meer)")


def test_voorgeladen_sjablonen_worden_niet_meer_van_schijf_gelezen(tmp_path, monkeypatch):
    """Zo draait een proces dat nog niet is herstart na een nieuwe uitrol op oude code én oude
    sjablonen, in plaats van een nieuw sjabloon te lezen dat naar onbekende routes verwijst."""
    app = create_app(database_path=str(tmp_path / "x.db"), admin_wachtwoord="x", sjablonen_voorladen=True)
    assert app.jinja_env.auto_reload is False
    assert len(app.jinja_env.cache) >= len(app.jinja_env.list_templates())

    # Dezelfde lader houden (de cache onthoudt sjablonen per lader), maar lezen van schijf verbieden.
    monkeypatch.setattr(app.jinja_env.loader, "get_source", _niet_van_schijf)
    with app.test_request_context("/"):
        from flask import render_template

        assert "404" in render_template("404.html")


def test_zonder_voorladen_blijft_het_lui_laden(tmp_path):
    app = create_app(database_path=str(tmp_path / "y.db"), admin_wachtwoord="x")
    assert len(app.jinja_env.cache or {}) < len(app.jinja_env.list_templates())
