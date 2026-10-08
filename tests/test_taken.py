from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from conftest import stel_csrf_token_in as _csrf
from database import WACHTWOORD_HASH_METHODE
from helpers import bouw_taken


def _titels(taken):
    return [t["titel"] for t in taken]


def _schoon_beginnen(db):
    """De testdatabase heeft voorbeeldproducten die onder het minimum zitten; voor deze tests
    willen we alleen wat we zelf klaarzetten."""
    db.execute("UPDATE producten SET voorraad = 100, min_voorraad = 0")
    db.execute("UPDATE instellingen SET frituurvet_interval_dagen = 14 WHERE id = 1")
    db.commit()


def _recent_geteld(db):
    nu = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (nu,))
    db.execute(
        "INSERT INTO kassa_tellingen (datum, naam, afgesloten) VALUES (?, 'test', 1)", (nu,)
    )
    db.execute(
        "INSERT INTO frituurvet_vervangingen (datum, naam) VALUES (?, 'test')", (nu,)
    )
    db.commit()


def test_alles_bij_geeft_geen_taken(db):
    _schoon_beginnen(db)
    _recent_geteld(db)
    assert bouw_taken(db, "beheerder", "") == []


def test_nog_nooit_geteld_staat_bovenaan_als_dringend(db):
    _schoon_beginnen(db)
    taken = bouw_taken(db, "beheerder", "")
    assert taken[0]["titel"] == "Voorraad tellen" and taken[0]["urgent"]


def test_te_oude_telling_noemt_het_aantal_dagen(db):
    _schoon_beginnen(db)
    oud = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
    db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (oud,))
    db.commit()
    taken = bouw_taken(db, "beheerder", "")
    assert "10 dagen" in taken[0]["detail"]


def test_producten_onder_het_minimum_en_open_bestelling(db):
    _schoon_beginnen(db)
    _recent_geteld(db)
    db.execute("UPDATE producten SET voorraad = 1, min_voorraad = 10 WHERE id IN (SELECT id FROM producten LIMIT 2)")
    db.execute("INSERT INTO bestellingen (status, aangemaakt_op) VALUES ('besteld', '2026-10-06 22:30')")
    db.commit()

    titels = _titels(bouw_taken(db, "beheerder", ""))

    assert "2 producten onder het minimum" in titels
    assert "Bestelling inboeken" in titels


def test_open_kassatelling_en_frituurvet(db):
    _schoon_beginnen(db)
    nu = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (nu,))
    db.execute("INSERT INTO kassa_tellingen (datum, naam, afgesloten) VALUES (?, 'test', 0)", (nu,))
    db.commit()

    taken = bouw_taken(db, "beheerder", "")

    assert "Kassatelling afronden" in _titels(taken)
    assert "Frituurvet vervangen" in _titels(taken)
    assert next(t for t in taken if t["titel"] == "Kassatelling afronden")["kwargs"]["telling_id"]


def test_urgente_prikbordberichten_gaan_voor_gewone(db):
    _schoon_beginnen(db)
    _recent_geteld(db)
    db.execute("INSERT INTO mededelingen (tekst, naam, datum, urgent) VALUES ('a', 'x', '2026-10-01 10:00', 0)")
    assert _titels(bouw_taken(db, "beheerder", "")) == ["Prikbord: 1 open mededeling"]
    db.execute("INSERT INTO mededelingen (tekst, naam, datum, urgent) VALUES ('b', 'x', '2026-10-01 10:00', 1)")
    db.commit()
    taken = bouw_taken(db, "beheerder", "")
    assert taken[0]["urgent"] and "urgent" in taken[0]["titel"]


def test_taken_volgen_de_rechten_van_het_account(db):
    _schoon_beginnen(db)  # niets geteld, vet nooit vervangen, kassa nooit geteld

    keuken = _titels(bouw_taken(db, "vrijwilliger", "keuken"))
    assert keuken == ["Frituurvet vervangen"]

    kassa = _titels(bouw_taken(db, "vrijwilliger", "kassa"))
    assert "Kassa tellen" in kassa and "Voorraad tellen" not in kassa and "Frituurvet vervangen" not in kassa

    niets = _titels(bouw_taken(db, "vrijwilliger", ""))
    assert niets == []


def test_dashboard_toont_de_lijst_en_de_lege_toestand(ingelogde_client, db):
    _schoon_beginnen(db)
    pagina = ingelogde_client.get("/").data.decode()
    assert "Wat moet er nu?" in pagina and "Voorraad tellen" in pagina

    _recent_geteld(db)
    assert "Alles is bij" in ingelogde_client.get("/").data.decode()


def test_vrijwilliger_ziet_alleen_zijn_taken_op_het_dashboard(client, db):
    _schoon_beginnen(db)
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) "
        "VALUES ('kok', ?, 'vrijwilliger', 'keuken', '2026-01-01 10:00')",
        (generate_password_hash("geheim123", method=WACHTWOORD_HASH_METHODE),),
    )
    db.commit()
    client.post("/login", data={"naam": "kok", "wachtwoord": "geheim123", "csrf_token": _csrf(client)})
    pagina = client.get("/").data.decode()
    assert "Frituurvet vervangen" in pagina
    assert "Voorraad tellen" not in pagina.split("Wat moet er nu?")[1].split("statgrid")[0]
