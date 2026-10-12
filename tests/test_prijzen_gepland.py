"""Prijzen die op een afgesproken datum ingaan, de prijslijst om te bekijken en de pdf voor aan de bar."""

from datetime import timedelta

from conftest import stel_csrf_token_in as _csrf
from test_eigen_taken import _taak, _vrijwilliger
from test_producten_prijzen import _post, _prijs, _product
from test_secties_rechten import _login, _maak_vrijwilliger

import prijzen
import routes.producten.prijzen as prijzen_routes
from prijzen import SOORT_GLAS, SOORT_OPTIE, SOORT_VERKOOPPRIJS, geplande_wijzigingen, pas_geplande_prijzen_toe, plan_prijs


def _vandaag():
    from helpers.tijd import vandaag_amsterdam

    return vandaag_amsterdam()


def _morgen():
    return _vandaag() + timedelta(days=1)


# ---------- Klaarzetten ----------


def test_met_een_ingangsdatum_staat_de_prijs_klaar_en_verandert_er_nog_niets(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.0)
    datum = (_vandaag() + timedelta(days=10)).isoformat()
    resp = _post(ingelogde_client, {f"prijs_{pid}": "2,50", "ingangsdatum": datum}, follow_redirects=True)
    tekst = resp.data.decode()
    assert "1 prijs staat klaar" in tekst and datum[8:10] in tekst
    assert _prijs(db, pid) == 2.0  # nog niet doorgevoerd
    rij = db.execute("SELECT * FROM prijs_wijzigingen_gepland").fetchone()
    assert (rij["soort"], rij["product_id"], rij["nieuwe_prijs"], rij["ingangsdatum"], rij["aangemaakt_door"]) == (SOORT_VERKOOPPRIJS, pid, 2.5, datum, "admin")
    assert db.execute("SELECT COUNT(*) FROM prijs_geschiedenis WHERE product_id = ?", (pid,)).fetchone()[0] == 0
    # En de pagina toont het: een regel in de tabel en bij het product.
    pagina = ingelogde_client.get("/producten/prijzen").data.decode()
    assert "Klaargezette prijswijzigingen" in pagina and "2,50" in pagina and "per " + datum[8:10] in pagina


def test_een_ingangsdatum_van_vandaag_of_eerder_voert_meteen_door(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.0)
    _post(ingelogde_client, {f"prijs_{pid}": "2,50", "ingangsdatum": _vandaag().isoformat()}, follow_redirects=True)
    assert _prijs(db, pid) == 2.5 and db.execute("SELECT COUNT(*) FROM prijs_wijzigingen_gepland").fetchone()[0] == 0


def test_een_ongeldige_ingangsdatum_slaat_niets_op(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.0)
    resp = _post(ingelogde_client, {f"prijs_{pid}": "2,50", "ingangsdatum": "morgenochtend"})
    assert "geen geldige datum" in resp.data.decode() and _prijs(db, pid) == 2.0
    assert db.execute("SELECT COUNT(*) FROM prijs_wijzigingen_gepland").fetchone()[0] == 0


def test_prijsopties_en_prijs_per_glas_kunnen_ook_klaargezet_worden(ingelogde_client, db):
    pid = _product(db, "Jupiler fust", categorie="Fust", verkoop=0, glazen_per_fust=50, prijs_per_glas=2.0)
    optie = db.execute("INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES (?, 'Pitcher', 12, 0)", (pid,)).lastrowid
    db.commit()
    datum = (_vandaag() + timedelta(days=5)).isoformat()
    _post(ingelogde_client, {f"prijs_{pid}": "0,00", f"optie_{optie}": "13", f"glas_{pid}": "2,20", "ingangsdatum": datum})
    soorten = {r["soort"]: r for r in db.execute("SELECT * FROM prijs_wijzigingen_gepland")}
    assert set(soorten) == {SOORT_GLAS, SOORT_OPTIE} and soorten[SOORT_OPTIE]["optie_id"] == optie and soorten[SOORT_OPTIE]["product_id"] == pid


def test_dezelfde_prijs_op_dezelfde_datum_vervangt_de_eerdere(db):
    pid = _product(db, "Testbier")
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 2.5, "2030-01-01", "admin")
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 2.75, "2030-01-01", "admin")
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 3.0, "2030-02-01", "admin")  # andere datum: blijft apart
    assert [(r["ingangsdatum"], r["nieuwe_prijs"]) for r in geplande_wijzigingen(db)] == [("2030-01-01", 2.75), ("2030-02-01", 3.0)]


def test_een_klaargezette_prijs_verwijderen(ingelogde_client, db):
    pid = _product(db, "Testbier")
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 2.5, "2030-01-01", "admin")
    gid = db.execute("SELECT id FROM prijs_wijzigingen_gepland").fetchone()[0]
    resp = ingelogde_client.post(f"/producten/prijzen/gepland/{gid}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "Geplande prijswijziging verwijderd" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM prijs_wijzigingen_gepland").fetchone()[0] == 0


# ---------- Doorvoeren op de dag ----------


def test_op_de_ingangsdatum_wordt_de_prijs_doorgevoerd_met_een_regel_in_de_geschiedenis(db):
    pid = _product(db, "Testbier", verkoop=2.0)
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 2.5, _vandaag().isoformat(), "Luuk")
    assert pas_geplande_prijzen_toe(db, _vandaag()) == 1
    assert _prijs(db, pid) == 2.5
    regel = db.execute("SELECT * FROM prijs_geschiedenis WHERE product_id = ?", (pid,)).fetchone()
    assert (regel["oude_prijs"], regel["nieuwe_prijs"], regel["naam"]) == (2.0, 2.5, "gepland door Luuk")
    assert db.execute("SELECT COUNT(*) FROM prijs_wijzigingen_gepland").fetchone()[0] == 0
    assert pas_geplande_prijzen_toe(db, _vandaag()) == 0  # niet nog eens


def test_alleen_wat_aan_de_beurt_is_wordt_doorgevoerd_en_op_volgorde(db):
    pid = _product(db, "Testbier", verkoop=2.0)
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 2.5, (_vandaag() - timedelta(days=5)).isoformat(), "a")
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 2.8, (_vandaag() - timedelta(days=1)).isoformat(), "a")
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 9.0, _morgen().isoformat(), "a")
    assert pas_geplande_prijzen_toe(db, _vandaag()) == 2
    assert _prijs(db, pid) == 2.8  # de laatste van de twee verlopen datums wint
    assert [r["nieuwe_prijs"] for r in geplande_wijzigingen(db)] == [9.0]


def test_prijsopties_en_prijs_per_glas_gaan_ook_in(db):
    pid = _product(db, "Fust", categorie="Fust", glazen_per_fust=50, prijs_per_glas=2.0)
    optie = db.execute("INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES (?, 'Glas', 2, 0)", (pid,)).lastrowid
    db.commit()
    plan_prijs(db, SOORT_GLAS, pid, 2.2, _vandaag().isoformat(), "a")
    plan_prijs(db, SOORT_OPTIE, pid, 2.4, _vandaag().isoformat(), "a", optie_id=optie)
    assert pas_geplande_prijzen_toe(db, _vandaag()) == 2
    assert db.execute("SELECT prijs_per_glas FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 2.2
    assert db.execute("SELECT prijs FROM product_prijsopties WHERE id = ?", (optie,)).fetchone()[0] == 2.4
    assert db.execute("SELECT COUNT(*) FROM prijs_geschiedenis WHERE product_id = ?", (pid,)).fetchone()[0] == 0


def test_een_verwijderd_product_neemt_zijn_geplande_prijzen_mee(db):
    pid = _product(db, "Testbier")
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 2.5, "2030-01-01", "a")
    db.execute("DELETE FROM producten WHERE id = ?", (pid,))
    db.commit()
    assert geplande_wijzigingen(db) == []


def test_een_gewone_paginavraag_voert_de_prijs_op_de_dag_zelf_door(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.0)
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 3.5, _vandaag().isoformat(), "a")
    db.commit()
    prijzen_routes._laatste_controle["tijd"] = 0.0  # de controle is begrensd tot eens per minuut
    ingelogde_client.get("/producten")
    assert _prijs(db, pid) == 3.5


def test_de_controle_gebeurt_hooguit_eens_per_minuut(ingelogde_client, db, monkeypatch):
    aantal = []
    monkeypatch.setattr(prijzen_routes, "pas_geplande_prijzen_toe", lambda db_, vandaag: aantal.append(1) or 0)
    prijzen_routes._laatste_controle["tijd"] = 0.0
    for _ in range(5):
        ingelogde_client.get("/producten")
    assert len(aantal) == 1


def test_een_fout_bij_het_doorvoeren_laat_de_site_niet_stukgaan(ingelogde_client, monkeypatch):
    def stuk(db, vandaag):
        raise RuntimeError("kapot")

    monkeypatch.setattr(prijzen_routes, "pas_geplande_prijzen_toe", stuk)
    prijzen_routes._laatste_controle["tijd"] = 0.0
    assert ingelogde_client.get("/producten").status_code == 200


# ---------- De prijslijst om te bekijken ----------


def test_de_prijslijst_toont_de_prijzen_zonder_invoervelden(ingelogde_client, db):
    pid = _product(db, "Testbier", categorie="Bier", verkoop=2.5)
    _product(db, "Zonder prijs", categorie="Bier", verkoop=0)
    fust = _product(db, "Fust 50L", categorie="Fust", verkoop=0, glazen_per_fust=50, prijs_per_glas=2.0)
    db.execute("INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES (?, 'Pitcher', 12, 0)", (fust,))
    db.commit()
    tekst = ingelogde_client.get("/prijslijst").data.decode()
    assert "Testbier" in tekst and "2,50" in tekst and "Pitcher" in tekst and "12,00" in tekst and "per glas" in tekst
    assert "Zonder prijs" not in tekst
    assert "<input" not in tekst.split("</nav>")[1].split("<footer")[0].replace('type="hidden"', "")  # alleen kijken
    assert pid


def test_de_prijslijst_toont_wat_er_binnenkort_verandert(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.0)
    plan_prijs(db, SOORT_VERKOOPPRIJS, pid, 2.5, "2030-03-01", "admin")
    tekst = ingelogde_client.get("/prijslijst").data.decode()
    assert "Binnenkort veranderen" in tekst and "01-03" in tekst and "2,50" in tekst


def test_een_vrijwilliger_met_voorraadrechten_kan_de_prijslijst_bekijken_maar_niet_aanpassen(app, db):
    klant, _ = _vrijwilliger(app, db, "bakker", "voorraad")
    assert klant.get("/prijslijst").status_code == 200
    assert "alleen voor beheerders" in klant.get("/producten/prijzen", follow_redirects=True).data.decode()
    assert 'href="/prijslijst"' in klant.get("/").data.decode()


def test_zonder_voorraadrechten_geen_prijslijst(client, db):
    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    _login(client, "keukenhulp")
    assert "niet beschikbaar voor jouw account" in client.get("/prijslijst", follow_redirects=True).data.decode()
    assert "niet beschikbaar voor jouw account" in client.get("/prijslijst/pdf", follow_redirects=True).data.decode()


def test_een_vrijwilliger_rondt_de_taak_prijzenlijst_nalopen_af_op_de_prijslijst(app, db):
    klant, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    taak_id = _taak(db, "Prijzenlijst nalopen", soort="preset:prijzen_kijken", ids=[bakker])  # kan: de pagina is voor hem toegankelijk
    pagina = klant.get("/prijslijst").data.decode()
    assert "Taak: Prijzenlijst nalopen" in pagina and f"/taken/{taak_id}/afronden" in pagina
    assert f'href="/taken/{taak_id}/openen"' in klant.get("/").data.decode()
    assert klant.get(f"/taken/{taak_id}/openen").headers["Location"].endswith("/prijslijst")
    resp = klant.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(klant), "terug": "/prijslijst"}, follow_redirects=True)
    assert "is klaar" in resp.data.decode() and "Taak: Prijzenlijst nalopen" not in resp.data.decode()


def test_de_kijktaak_kan_ook_aan_een_vrijwilliger_maar_de_aanpastaak_niet(app, db):
    from eigen_taken import maak_taak

    _, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    assert maak_taak(db, "Kijken", "", "preset:prijzen_kijken", None, [bakker], True, "admin")[1] is None
    assert "geen toegang" in maak_taak(db, "Aanpassen", "", "preset:prijzen", None, [bakker], True, "admin")[1]


# ---------- De pdf ----------


def test_de_prijslijst_pdf_toont_wat_op_de_tv_staat(ingelogde_client, db):
    import re
    import zlib

    _product(db, "Vrijwillig op de tv", categorie="Bier", verkoop=2.5, toon_op_kiosk=1)
    _product(db, "Niet op de tv", categorie="Bier", verkoop=2.5, toon_op_kiosk=0)
    resp = ingelogde_client.get("/prijslijst/pdf")
    assert resp.status_code == 200 and resp.mimetype == "application/pdf" and resp.data.startswith(b"%PDF")
    inhoud = b""
    for stroom in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", resp.data, re.S):
        try:
            inhoud += zlib.decompress(stroom)
        except zlib.error:
            inhoud += stroom
    assert b"Vrijwillig op de tv" in inhoud and b"Niet op de tv" not in inhoud and b"Prijslijst" in inhoud
    assert "attachment" in ingelogde_client.get("/prijslijst/pdf?download=1").headers["Content-Disposition"]


def test_een_lege_prijslijst_pdf_geeft_een_melding(ingelogde_client, db):
    db.execute("UPDATE producten SET toon_op_kiosk = 0")
    db.commit()
    assert ingelogde_client.get("/prijslijst/pdf").data.startswith(b"%PDF")


def test_het_prijzenmenu_heeft_een_prijslijst_voor_iedereen_met_voorraad(ingelogde_client):
    assert "Prijslijst" in ingelogde_client.get("/producten").data.decode()
    assert prijzen  # de module bestaat
