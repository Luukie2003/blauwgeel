"""De bestellijst nalopen in de app (1.73.0): per product het aantal colli bevestigen (gecontroleerd), dat bewaren zodat
het na uitloggen nog staat, de ronde afsluiten bij het klaarzetten, en het overzicht voor de leverancier."""

from test_app_api import _post, app_client  # noqa: F401 (fixture)
from test_bestellen_per_leverancier import _bij, _leverancier
from test_bestelvoorstel import _product, prognose  # noqa: F401 (fixture)

import bestelvoorstel


def _controleer(client, pid, eenheden):
    return _post(client, "/api/app/bestellijst/controleren", product_id=pid, eenheden=eenheden)


def test_bevestigen_bewaart_het_aantal_als_gecontroleerd(app_client, db):  # noqa: F811
    pid = _product(db, "Cola Controle", voorraad=0, minimum=5, factor=24, besteleenheid="tray")
    antwoord = _controleer(app_client, pid, 2).get_json()
    assert antwoord["gekozen"] == 2 and antwoord["gecontroleerd"] is True and antwoord["melding"] == "Cola Controle: 2 tray."
    keuze = bestelvoorstel.bijstellingen(db)[pid]
    assert (keuze["eenheden"], keuze["gecontroleerd"]) == (2, 1)

    # Na opnieuw inloggen (of op een ander toestel) staat het er nog: de bestellijst geeft het mee.
    regel = next(p for p in app_client.get("/api/app/bestellijst").get_json()["bestellen"] if p["id"] == pid)
    assert (regel["gekozen"], regel["gecontroleerd"]) == (2, True) and regel["gekozen_door"]
    assert "&#10003; gecontroleerd" in app_client.get("/bestellijst").get_data(as_text=True)  # ook op de site

    # Niet bestellen is ook een besluit (gecontroleerd); terug naar het advies niet meer.
    assert _controleer(app_client, pid, 0).get_json()["melding"] == "Cola Controle: niet bestellen."
    assert bestelvoorstel.bijstellingen(db)[pid]["gecontroleerd"] == 1
    assert _controleer(app_client, pid, None).get_json()["gecontroleerd"] is False
    assert pid not in bestelvoorstel.bijstellingen(db)

    assert _controleer(app_client, pid, -1).status_code == 400
    assert _controleer(app_client, 999999, 1).status_code == 404


def test_ook_een_extra_product_op_niet_bestellen_blijft_zichtbaar(app_client, db):  # noqa: F811
    pid = _product(db, "Chips Erbij", voorraad=50, minimum=5)
    _controleer(app_client, pid, 0)
    regel = next(p for p in app_client.get("/api/app/bestellijst").get_json()["gekozen"] if p["id"] == pid)
    assert (regel["gekozen"], regel["gecontroleerd"]) == (0, True)


def test_een_aantal_bij_het_product_is_niet_meer_gecontroleerd(app_client, db, prognose):  # noqa: F811
    pid = _product(db, "Sinas Controle", voorraad=0, minimum=5)
    _controleer(app_client, pid, 2)
    _post(app_client, f"/api/app/producten/{pid}/bestelaantal", eenheden=3)
    keuze = bestelvoorstel.bijstellingen(db)[pid]
    assert (keuze["eenheden"], keuze["gecontroleerd"]) == (3, 0)


def test_klaarzetten_sluit_de_controle_af(app_client, db):  # noqa: F811
    besteld = _product(db, "Bier Controle", voorraad=0, minimum=5)
    niet = _product(db, "Wijn Controle", voorraad=0, minimum=5)
    elders = _product(db, "Ranja Elders", voorraad=50)
    _controleer(app_client, besteld, 2)
    _controleer(app_client, niet, 0)
    bestelvoorstel.zet_bestelaantal(db, elders, 3)  # bij het product gekozen, niet gecontroleerd
    _post(app_client, "/api/app/bestellijst/bestellen", aantallen={str(besteld): 2}, verzoek_id="controle-1")
    over = bestelvoorstel.bijstellingen(db)
    assert besteld not in over and niet not in over and over[elders]["eenheden"] == 3


def test_overzicht_van_een_klaargezette_bestelling(app_client, db):  # noqa: F811
    sligro = _leverancier(db, "Sligro Overzicht", klantnummer="123456")
    cola = _product(db, "Cola Overzicht", voorraad=0, factor=24, besteleenheid="tray")
    _bij(db, cola, sligro)
    antwoord = _post(app_client, "/api/app/bestellijst/bestellen", aantallen={str(cola): 2}, verzoek_id="overzicht-1").get_json()
    bid = antwoord["bestellingen"][0]["id"]

    o = app_client.get(f"/api/app/bestellingen/{bid}").get_json()
    assert (o["leverancier"], o["klantnummer"], o["status"]) == ("Sligro Overzicht", "123456", "besteld")
    assert o["regels"] == [{"naam": "Cola Overzicht", "artikelcode": f"A{cola}", "eenheden": 2, "besteleenheid": "tray",
                            "stuks": 48, "eenheid": "stuks", "factor": 24}]
    assert "klantnummer 123456" in o["tekst"] and "2 tray Cola Overzicht (48 stuks)" in o["tekst"]
    assert o["uiterst_tekst"]  # besteldagen dinsdag en donderdag, vóór 16.00 uur
    assert app_client.get("/api/app/bestellingen/999999").status_code == 404

    # Onderweg op de bestellijst: met de leverancier, in colli.
    b = next(x for x in app_client.get("/api/app/bestellijst").get_json()["onderweg"] if x["id"] == bid)
    assert b["leverancier"] == "Sligro Overzicht" and b["regels"] == [{"product": "Cola Overzicht", "aantal": 2, "eenheid": "tray"}]
