"""Bestellijst nalopen en het besteloverzicht op de site (2.8.0), zoals op de handterminal: per product het aantal colli
kiezen en afvinken (gedeeld met de handterminal), ook zonder telling producten erbij zetten, klaarzetten wat afgevinkt
is, en daarna het overzicht om in de webshop van de leverancier in te vullen."""

from conftest import stel_csrf_token_in as _csrf
from test_bestellen_per_leverancier import _bij, _leverancier
from test_bestelvoorstel import _product

import bestellen
import bestelvoorstel


def _keuken(db, naam):
    pid = _product(db, naam, voorraad=0, minimum=10)
    db.execute("UPDATE producten SET categorie = 'Keuken' WHERE id = ?", (pid,))
    db.commit()
    return pid


def _afvinken(client, pid, eenheden, csrf=True):
    kop = {"X-CSRF-Token": _csrf(client)} if csrf else {}
    return client.post("/bestellijst/nalopen/controleren", json={"product_id": pid, "eenheden": eenheden}, headers=kop)


def _regel(lijst, pid):
    return next(r for r in lijst["te_bestellen"] + lijst["overig"] if r["id"] == pid)


# ---------- Wat er op de lijst staat ----------


def test_onder_het_minimum_bij_te_bestellen_en_de_rest_om_erbij_te_zetten(ingelogde_client, db):
    laag = _product(db, "Cola Nalopen", voorraad=4, minimum=30, factor=24, besteleenheid="tray")
    genoeg = _product(db, "Sinas Nalopen", voorraad=50, minimum=10)
    uit = _product(db, "Ranja Nalopen", voorraad=0, minimum=0)
    db.execute("UPDATE producten SET actief = 0 WHERE id = ?", (uit,))
    db.commit()
    friet = _keuken(db, "Friet Nalopen")

    lijst = bestellen.nalooplijst(db)
    r = _regel(lijst, laag)
    # 26 stuks tot het minimum: 2 tray, nog niet afgevinkt.
    assert (r["soort"], r["aantal"], r["standaard"], r["colli"], r["gecontroleerd"]) == ("laag", 2, 2, "tray", False)
    assert _regel(lijst, genoeg)["soort"] == "overig" and _regel(lijst, genoeg)["aantal"] == 0
    alle = {r["id"] for r in lijst["te_bestellen"] + lijst["overig"]}
    assert uit not in alle and friet not in alle  # niet actief, en de keuken koopt zelf in

    pagina = ingelogde_client.get("/bestellijst/nalopen").data.decode()
    assert f'data-id="{laag}" data-soort="laag"' in pagina and f'data-id="{genoeg}" data-soort="overig"' in pagina
    assert "Friet Nalopen" not in pagina and "Klaarzetten" in pagina
    assert "Nalopen en klaarzetten" in ingelogde_client.get("/bestellijst").data.decode()


def test_niet_geleverd_en_zelf_gekozen_staan_ook_bij_te_bestellen(db):
    manco = _product(db, "Bier Manco Nalopen", voorraad=40, minimum=10, factor=24, besteleenheid="krat")
    gekozen = _product(db, "Chips Gekozen Nalopen", voorraad=40, minimum=10)
    niet = _product(db, "Wijn Niet Nalopen", voorraad=40, minimum=10)
    bid = db.execute("INSERT INTO bestellingen (status, aangemaakt_op, ontvangen_op) VALUES ('ontvangen', '2026-11-01', '2026-11-03')").lastrowid
    db.execute("INSERT INTO bestelregels (bestelling_id, product_id, aantal_besteld, aantal_ontvangen) VALUES (?, ?, 48, 24)", (bid, manco))
    db.commit()
    bestelvoorstel.zet_bestelaantal(db, gekozen, 3, "Piet")  # bij het product gekozen
    bestelvoorstel.zet_bestelaantal(db, niet, 0, "Piet", gecontroleerd=True)  # op de handterminal: niet bestellen

    lijst = bestellen.nalooplijst(db)
    m, g, n = _regel(lijst, manco), _regel(lijst, gekozen), _regel(lijst, niet)
    assert (m["soort"], m["aantal"], m["tekort"], m["bestellingen"]) == ("manco", 1, 24, [bid])
    assert (g["soort"], g["aantal"], g["vast"], g["gecontroleerd"], g["door"]) == ("gekozen", 3, True, False, "Piet")
    assert (n["soort"], n["aantal"], n["gecontroleerd"]) == ("gekozen", 0, True)


# ---------- Afvinken, gedeeld met de handterminal ----------


def test_afvinken_op_de_site_staat_ook_op_de_handterminal(ingelogde_client, db):
    pid = _product(db, "Fanta Afvinken", voorraad=0, minimum=12, factor=12, besteleenheid="tray")
    antwoord = _afvinken(ingelogde_client, pid, 2)
    assert antwoord.status_code == 200
    data = antwoord.get_json()
    assert (data["gekozen"], data["gecontroleerd"]) == (2, True) and data["door"]
    regel = next(p for p in ingelogde_client.get("/api/app/bestellijst").get_json()["bestellen"] if p["id"] == pid)
    assert (regel["gekozen"], regel["gecontroleerd"]) == (2, True)

    # Niet bestellen is ook afgevinkt; null is weer het voorstel.
    assert _afvinken(ingelogde_client, pid, 0).get_json()["gecontroleerd"] is True
    assert bestelvoorstel.bijstellingen(db)[pid]["eenheden"] == 0
    assert _afvinken(ingelogde_client, pid, None).get_json()["gecontroleerd"] is False
    assert pid not in bestelvoorstel.bijstellingen(db)


def test_afvinken_weigert_wat_niet_klopt(ingelogde_client, db):
    pid = _product(db, "Spa Weigeren", voorraad=0, minimum=12)
    for fout in (-1, 1000, True, "2", 1.5):
        assert _afvinken(ingelogde_client, pid, fout).status_code == 400, fout
    assert _afvinken(ingelogde_client, 999999, 1).status_code == 404
    assert _afvinken(ingelogde_client, _keuken(db, "Kroket Weigeren"), 1).status_code == 400
    # Zonder csrf-token gebeurt er niets.
    assert _afvinken(ingelogde_client, pid, 3, csrf=False).status_code == 302
    assert pid not in bestelvoorstel.bijstellingen(db)


# ---------- Klaarzetten en het besteloverzicht ----------


def test_klaarzetten_opent_het_besteloverzicht_voor_de_webshop(ingelogde_client, db):
    sligro = _leverancier(db, "Sligro Webshop", klantnummer="778899")
    db.execute("UPDATE leveranciers SET website = 'www.sligro.nl', bestelwijze = 'Via de webshop' WHERE id = ?", (sligro,))
    cola = _product(db, "Cola Webshop", voorraad=0, minimum=24, factor=24, besteleenheid="tray")
    sinas = _product(db, "Sinas Webshop", voorraad=50, minimum=10)
    friet = _keuken(db, "Friet Webshop")
    _bij(db, cola, sligro)
    _afvinken(ingelogde_client, cola, 2)
    _afvinken(ingelogde_client, sinas, 1)

    resp = ingelogde_client.post("/bestellijst/aanmaken", data={
        "csrf_token": _csrf(ingelogde_client), "van": "nalopen", "product_id": [cola, sinas, friet],
        f"aantal_{cola}": "2", f"aantal_{sinas}": "1", f"aantal_{friet}": "4",
    })
    assert resp.status_code == 302 and "/bestellingen/overzicht?id=" in resp.headers["Location"]
    ids = [r["id"] for r in db.execute("SELECT id FROM bestellingen ORDER BY id").fetchall()]
    assert len(ids) == 2  # Sligro, en zonder leverancier; de friet niet
    assert db.execute("SELECT COUNT(*) FROM bestelregels WHERE product_id = ?", (friet,)).fetchone()[0] == 0
    assert bestelvoorstel.bijstellingen(db) == {}  # de ronde is voorbij

    pagina = ingelogde_client.get(resp.headers["Location"]).data.decode()
    assert "Nu bij de leverancier bestellen" in pagina and "<h2>Sligro Webshop</h2>" in pagina
    assert "778899" in pagina and 'href="https://www.sligro.nl"' in pagina and "Via de webshop" in pagina
    assert f"A{cola}" in pagina and '<span class="cs-colli-getal">2</span> tray' in pagina and "48 stuks" in pagina
    assert "Uiterlijk bestellen" in pagina and "Levering inboeken" in pagina and "Zonder leverancier" in pagina
    assert "klantnummer 778899" in pagina  # de tekst om te kopiëren


def test_niets_afgevinkt_terug_naar_nalopen(ingelogde_client):
    resp = ingelogde_client.post("/bestellijst/aanmaken", data={"csrf_token": _csrf(ingelogde_client), "van": "nalopen"})
    assert resp.headers["Location"].endswith("/bestellijst/nalopen")


def test_het_besteloverzicht_zonder_keuze_toont_wat_klaarstaat(ingelogde_client, db):
    cola = _product(db, "Cola Klaar", voorraad=0)
    open_id, _ = bestellen.maak_bestelling(db, {cola: 2})
    binnen_id, _ = bestellen.maak_bestelling(db, {cola: 1})
    db.execute("UPDATE bestellingen SET status = 'ontvangen' WHERE id = ?", (binnen_id,))
    db.commit()

    alles = ingelogde_client.get("/bestellingen/overzicht").data.decode()
    assert f"Bestelling #{open_id}" in alles and f"Bestelling #{binnen_id}" not in alles
    een = ingelogde_client.get(f"/bestellingen/overzicht?id={binnen_id}").data.decode()
    assert f"Bestelling #{binnen_id}" in een and "Ingeboekt" in een and "Levering inboeken" not in een
    assert "Deze bestelling bestaat niet meer" in ingelogde_client.get("/bestellingen/overzicht?id=999999").data.decode()
    assert f'href="/bestellingen/overzicht?id={open_id}"' in ingelogde_client.get("/bestellijst").data.decode()


def test_webadres_van_een_leverancier():
    assert bestellen.webadres("www.sligro.nl") == "https://www.sligro.nl"
    assert bestellen.webadres(" https://www.makro.nl/bestellen ") == "https://www.makro.nl/bestellen"
    for fout in (None, "", "javascript:alert(1)", "sligro .nl", "data:text/html,x"):
        assert bestellen.webadres(fout) is None, fout
