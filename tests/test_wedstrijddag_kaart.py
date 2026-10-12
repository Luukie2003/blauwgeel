"""De kaart 'Thuiswedstrijd' op het overzicht: verwachte omzet en bestel-advies voor de komende thuiswedstrijd."""

from datetime import datetime, timedelta

from conftest import stel_csrf_token_in as _csrf  # noqa: F401
from test_secties_rechten import _login, _maak_vrijwilliger
from test_voorspelling import _bouw_geschiedenis, _product

KAART = "/dashboard/wedstrijddag"


def _vandaag():
    from helpers.tijd import vandaag_amsterdam

    return vandaag_amsterdam()


def _wedstrijd(db, dagen_vooruit, omschrijving="ZA 1 - Tegenstander", afgelast=0):
    datum = (_vandaag() + timedelta(days=dagen_vooruit)).isoformat()
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis, afgelast) VALUES ('ZA 1', ?, ?, 1, ?)", (datum, omschrijving, afgelast)
    )
    db.commit()
    return datum


def _geschiedenis(db, voorraad=30):
    pid = _product(db, "Pils krat", voorraad=voorraad, factor=24, besteleenheid="krat")
    _bouw_geschiedenis(
        db, {pid: 40},
        tijdstippen=[datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=7 * (6 - i)) for i in range(7)],
        open_dagen="0,1,2,3,4,5,6",  # elke dag open: dan telt ook de dag van de wedstrijd mee in de prognose
    )
    return pid


def test_zonder_thuiswedstrijd_in_de_komende_dagen_is_de_kaart_leeg(ingelogde_client, db):
    _wedstrijd(db, 10)  # te ver weg
    assert ingelogde_client.get(KAART).data.decode().strip() == ""


def test_een_afgelaste_wedstrijd_telt_niet(ingelogde_client, db):
    _wedstrijd(db, 2, afgelast=1)
    assert ingelogde_client.get(KAART).data.decode().strip() == ""


def test_de_kaart_toont_de_eerstvolgende_wedstrijd(ingelogde_client, db):
    _wedstrijd(db, 4, "ZA 2 - Later")
    _wedstrijd(db, 2, "ZA 1 - Eerst")
    tekst = ingelogde_client.get(KAART).data.decode()
    assert "Thuiswedstrijd" in tekst and "ZA 1 - Eerst" in tekst and "ZA 2 - Later" not in tekst
    assert "<html" not in tekst  # alleen de kaart


def test_morgen_en_vandaag_staan_er_als_woord(ingelogde_client, db):
    _wedstrijd(db, 1)
    assert "Thuiswedstrijd morgen" in ingelogde_client.get(KAART).data.decode()
    db.execute("DELETE FROM wedstrijden")
    _wedstrijd(db, 0)
    assert "Thuiswedstrijd vandaag" in ingelogde_client.get(KAART).data.decode()


def test_de_kaart_toont_de_verwachte_omzet_van_die_dag(ingelogde_client, db):
    _geschiedenis(db)
    _wedstrijd(db, 2)
    tekst = ingelogde_client.get(KAART).data.decode()
    assert "Verwachte omzet die dag" in tekst and "&euro;" in tekst


def test_dringend_als_er_binnen_drie_dagen_een_wedstrijd_is_en_er_iets_op_raakt(ingelogde_client, db):
    _geschiedenis(db, voorraad=3)  # bijna op
    _wedstrijd(db, 2)
    tekst = ingelogde_client.get(KAART).data.decode()
    assert "Bestel nu" in tekst and "Pils krat" in tekst and "Naar de bestellijst" in tekst and "btn-geel" in tekst


def test_niet_dringend_als_de_wedstrijd_nog_ver_weg_is(ingelogde_client, db):
    _geschiedenis(db, voorraad=3)
    _wedstrijd(db, 5)
    tekst = ingelogde_client.get(KAART).data.decode()
    assert "Pils krat" in tekst and "Bestel nu" not in tekst


def test_alles_goed_als_er_niets_te_bestellen_is(ingelogde_client, db):
    _geschiedenis(db, voorraad=500)
    db.execute("UPDATE producten SET min_voorraad = 0")  # de testdatabase heeft al producten onder het minimum
    db.commit()
    _wedstrijd(db, 2)
    assert "Alles ziet er goed uit" in ingelogde_client.get(KAART).data.decode()


def test_een_kapot_voorspelmodel_laat_de_kaart_niet_stukgaan(ingelogde_client, db, monkeypatch):
    import routes.dashboard as dashboard_routes

    def stuk(db, dagen=7, **kw):
        raise RuntimeError("kapot")

    monkeypatch.setattr(dashboard_routes, "maak_prognose", stuk)
    _wedstrijd(db, 2)
    resp = ingelogde_client.get(KAART)
    assert resp.status_code == 200 and "Thuiswedstrijd" in resp.data.decode()


def test_het_overzicht_heeft_een_plek_voor_de_kaart_voor_wie_de_voorraad_mag_zien(ingelogde_client, app, db):
    assert f'data-lazy-bron="{KAART}"' in ingelogde_client.get("/").data.decode()
    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    keuken = app.test_client()
    _login(keuken, "keukenhulp")
    assert KAART not in keuken.get("/").data.decode()
    assert "niet beschikbaar voor jouw account" in keuken.get(KAART, follow_redirects=True).data.decode()


def test_de_kaart_vraagt_inloggen_en_telt_niet_als_paginabezoek(client, ingelogde_client, db):
    voor = db.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0]
    ingelogde_client.get(KAART)
    assert db.execute("SELECT COUNT(*) FROM paginabezoeken").fetchone()[0] == voor


def test_zonder_inloggen_wordt_de_kaart_niet_getoond(app):
    assert app.test_client().get(KAART).status_code == 302
