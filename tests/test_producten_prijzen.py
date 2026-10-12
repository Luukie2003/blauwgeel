"""Producten > Prijzen aanpassen: alle verkoopprijzen in één keer nalopen en opslaan."""

import re

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger


def _product(db, naam, categorie="Bier", verkoop=2.0, inkoop=1.0, actief=1, **extra):
    kolommen = {"naam": naam, "categorie": categorie, "eenheid": "Fles", "verkoopprijs": verkoop, "inkoopprijs": inkoop, "actief": actief}
    kolommen.update(extra)
    cur = db.execute(
        f"INSERT INTO producten ({', '.join(kolommen)}) VALUES ({', '.join('?' for _ in kolommen)})", list(kolommen.values())
    )
    db.commit()
    return cur.lastrowid


def _prijs(db, pid):
    return db.execute("SELECT verkoopprijs FROM producten WHERE id = ?", (pid,)).fetchone()[0]


def _post(client, data, **kw):
    return client.post("/producten/prijzen", data={"csrf_token": _csrf(client), **data}, **kw)


def test_de_pagina_toont_voor_elk_product_een_prijsveld(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.5)
    tekst = ingelogde_client.get("/producten/prijzen").data.decode()
    assert re.search(rf'name="prijs_{pid}"[^>]*value="2,50"', tekst)
    assert "Prijzen aanpassen" in tekst and "Alles opslaan" in tekst


def test_producten_pagina_heeft_een_knop_naar_de_prijzen(ingelogde_client):
    tekst = ingelogde_client.get("/producten").data.decode()
    assert 'href="/producten/prijzen"' in tekst


def test_een_gewijzigde_prijs_wordt_opgeslagen_en_gelogd(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.0)
    resp = _post(ingelogde_client, {f"prijs_{pid}": "2,75"}, follow_redirects=True)
    assert "1 prijs aangepast" in resp.data.decode()
    assert _prijs(db, pid) == 2.75
    regel = db.execute("SELECT * FROM prijs_geschiedenis WHERE product_id = ?", (pid,)).fetchone()
    assert (regel["veld"], regel["oude_prijs"], regel["nieuwe_prijs"], regel["naam"]) == ("verkoopprijs", 2.0, 2.75, "admin")


def test_meerdere_prijzen_in_een_keer(ingelogde_client, db):
    a, b, c = _product(db, "A", verkoop=2.0), _product(db, "B", verkoop=3.0), _product(db, "C", verkoop=4.0)
    resp = _post(ingelogde_client, {f"prijs_{a}": "2.20", f"prijs_{b}": "3,30", f"prijs_{c}": "4.00"}, follow_redirects=True)
    assert "2 prijzen aangepast" in resp.data.decode()
    assert (_prijs(db, a), _prijs(db, b), _prijs(db, c)) == (2.2, 3.3, 4.0)
    assert db.execute("SELECT COUNT(*) FROM prijs_geschiedenis WHERE product_id IN (?, ?, ?)", (a, b, c)).fetchone()[0] == 2


def test_niets_gewijzigd_zegt_dat_en_logt_niets(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.0)
    resp = _post(ingelogde_client, {f"prijs_{pid}": "2,00"}, follow_redirects=True)
    assert "Geen prijzen gewijzigd" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM prijs_geschiedenis WHERE product_id = ?", (pid,)).fetchone()[0] == 0


@pytest.mark.parametrize("onzin", ["abc", "-1", "", "1e9", "2,5,5"])
def test_een_ongeldig_bedrag_slaat_niets_op(ingelogde_client, db, onzin):
    goed, fout = _product(db, "Goed", verkoop=2.0), _product(db, "Fout", verkoop=3.0)
    resp = _post(ingelogde_client, {f"prijs_{goed}": "9,99", f"prijs_{fout}": onzin})
    tekst = resp.data.decode()
    assert resp.status_code == 200 and "Er is niets opgeslagen" in tekst and "Fout:" in tekst
    assert (_prijs(db, goed), _prijs(db, fout)) == (2.0, 3.0)  # ook de goede wijziging is niet opgeslagen
    assert re.search(rf'name="prijs_{goed}"[^>]*value="9,99"', tekst)  # wat je intikte blijft staan


def test_velden_die_niet_in_het_formulier_zitten_blijven_ongemoeid(ingelogde_client, db):
    a, b = _product(db, "A", verkoop=2.0), _product(db, "B", verkoop=3.0)
    _post(ingelogde_client, {f"prijs_{a}": "2,50"})
    assert (_prijs(db, a), _prijs(db, b)) == (2.5, 3.0)


def test_prijsopties_en_prijs_per_glas_worden_ook_aangepast(ingelogde_client, db):
    pid = _product(db, "Jupiler fust", categorie="Fust", verkoop=0, glazen_per_fust=50, prijs_per_glas=2.0)
    optie = db.execute("INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES (?, 'Pitcher', 12, 0)", (pid,)).lastrowid
    db.commit()
    tekst = ingelogde_client.get("/producten/prijzen").data.decode()
    assert f'name="optie_{optie}"' in tekst and f'name="glas_{pid}"' in tekst

    resp = _post(ingelogde_client, {f"prijs_{pid}": "0,00", f"optie_{optie}": "13", f"glas_{pid}": "2,20"}, follow_redirects=True)
    assert "2 prijzen aangepast" in resp.data.decode()
    assert db.execute("SELECT prijs FROM product_prijsopties WHERE id = ?", (optie,)).fetchone()[0] == 13
    assert db.execute("SELECT prijs_per_glas FROM producten WHERE id = ?", (pid,)).fetchone()[0] == 2.2
    assert db.execute("SELECT COUNT(*) FROM prijs_geschiedenis WHERE product_id = ?", (pid,)).fetchone()[0] == 0  # alleen de verkoopprijs wordt bijgehouden


def test_producten_zonder_verkoopprijs_staan_standaard_verborgen(ingelogde_client, db):
    db.execute("UPDATE categorieen SET verkoopprijs_verplicht = 0 WHERE naam = 'Telling'")
    db.commit()
    zonder = _product(db, "Ingrediënt", categorie="Telling", verkoop=0)
    met = _product(db, "Frisdrank", categorie="Bier", verkoop=1.5)
    tekst = ingelogde_client.get("/producten/prijzen").data.decode()
    assert re.search(rf'data-product="{zonder}"', tekst) and re.search(r'data-zonder-prijs="1"[^>]*data-product="%d"' % zonder, tekst)
    assert re.search(r'data-zonder-prijs="0"[^>]*data-product="%d"' % met, tekst)


def test_de_marge_en_het_gereedschap_voor_alles_tegelijk_staan_op_de_pagina(ingelogde_client):
    tekst = ingelogde_client.get("/producten/prijzen").data.decode()
    assert "gr-toepassen" in tekst and "Alles terugzetten" in tekst and "Marge" in tekst


def test_het_staat_in_het_logboek(ingelogde_client, db):
    pid = _product(db, "Testbier", verkoop=2.0)
    _post(ingelogde_client, {f"prijs_{pid}": "2,10"})
    assert db.execute("SELECT actie FROM logboek WHERE endpoint = 'producten_prijzen'").fetchone()[0] == "Verkoopprijzen in bulk gewijzigd"


def test_alleen_beheerders_en_het_menu(client, db):
    _maak_vrijwilliger(db, "vrijwilliger", "voorraad")
    _login(client, "vrijwilliger")
    assert "alleen voor beheerders" in client.get("/producten/prijzen", follow_redirects=True).data.decode()
    resp = client.post("/producten/prijzen", data={"csrf_token": _csrf(client)}, follow_redirects=True)
    assert "alleen voor beheerders" in resp.data.decode()
    assert 'href="/producten/prijzen"' not in client.get("/").data.decode()


def test_beheerder_ziet_prijzen_aanpassen_in_het_menu(ingelogde_client):
    assert re.search(r'href="/producten/prijzen"[^>]*>\s*Prijzen aanpassen', ingelogde_client.get("/").data.decode())
