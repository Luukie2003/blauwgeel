from app import app as module_app
from conftest import stel_csrf_token_in as _csrf
from routes.logboek import LOGBOEK_ACTIES
from test_accounts import _maak_tweede_beheerder, _maak_vrijwilliger


def _regels(db):
    return db.execute("SELECT * FROM logboek ORDER BY id").fetchall()


def test_alle_gelogde_endpoints_bestaan():
    """Een typfout of hernoemde route zou stilletjes niets meer loggen."""
    endpoints = {r.endpoint for r in module_app.url_map.iter_rules()}
    onbekend = set(LOGBOEK_ACTIES) - endpoints
    assert not onbekend, f"Onbekende endpoints in LOGBOEK_ACTIES: {onbekend}"


def test_inloggen_komt_in_het_logboek(ingelogde_client, db):
    regels = _regels(db)
    assert [r["endpoint"] for r in regels] == ["login"]
    assert regels[0]["gebruiker_naam"] == "admin"


def test_rol_wijzigen_wordt_gelogd_met_de_melding_als_omschrijving(ingelogde_client, db):
    gebruiker_id = _maak_vrijwilliger(db, "pietje")
    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/rol",
        data={"csrf_token": _csrf(ingelogde_client), "rol": "beheerder"},
    )
    assert resp.status_code == 302
    laatste = _regels(db)[-1]
    assert laatste["endpoint"] == "account_rol_wijzigen"
    assert laatste["actie"] == "Rol gewijzigd"
    assert laatste["gebruiker_naam"] == "admin"
    assert "pietje" in laatste["omschrijving"]


def test_mislukte_actie_wordt_niet_gelogd(ingelogde_client, db):
    aantal_voor = len(_regels(db))
    resp = ingelogde_client.post(
        "/accounts/9999/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert len(_regels(db)) == aantal_voor


def test_actie_die_om_rechten_wordt_geweigerd_wordt_niet_gelogd(client, db):
    _maak_vrijwilliger(db, "vrijwilliger", "test1234")
    token = _csrf(client)
    client.post("/login", data={"naam": "vrijwilliger", "wachtwoord": "test1234", "csrf_token": token})
    voor = len([r for r in _regels(db) if r["endpoint"] != "login"])
    doel = _maak_tweede_beheerder(db)
    client.post(f"/accounts/{doel}/verwijderen", data={"csrf_token": _csrf(client)})
    na = len([r for r in _regels(db) if r["endpoint"] != "login"])
    assert voor == na
    assert db.execute("SELECT id FROM gebruikers WHERE id = ?", (doel,)).fetchone() is not None


def test_logboekpagina_alleen_voor_beheerders(ingelogde_client, client, db):
    pagina = ingelogde_client.get("/logboek")
    assert pagina.status_code == 200
    assert b"<td>Ingelogd</td>" in pagina.data


def test_logboekpagina_geweigerd_voor_vrijwilliger(client, db):
    _maak_vrijwilliger(db, "vrijwilliger", "test1234")
    token = _csrf(client)
    client.post("/login", data={"naam": "vrijwilliger", "wachtwoord": "test1234", "csrf_token": token})
    resp = client.get("/logboek")
    assert resp.status_code == 302


def test_filter_op_gebruiker(ingelogde_client, db):
    db.execute(
        "INSERT INTO logboek (datum, gebruiker_naam, endpoint, actie, omschrijving) "
        "VALUES (strftime('%Y-%m-%d %H:%M','now','localtime'), 'karin', 'backup_nu', 'Back-up gemaakt', 'Back-up gemaakt: x.db')"
    )
    db.commit()
    alles = ingelogde_client.get("/logboek").data.decode()
    gefilterd = ingelogde_client.get("/logboek?gebruiker=karin").data.decode()
    assert "Back-up gemaakt: x.db" in alles
    assert "Back-up gemaakt: x.db" in gefilterd
    assert "<td>Ingelogd</td>" not in gefilterd


# ---------- Export ----------


def _vul_logboek(db, aantal=3, details="Rol van 'pietje' gewijzigd"):
    for i in range(aantal):
        db.execute(
            "INSERT INTO logboek (datum, gebruiker_naam, endpoint, actie, omschrijving) "
            "VALUES (strftime('%Y-%m-%d %H:%M','now','localtime'), ?, 'account_rol_wijzigen', 'Rol gewijzigd', ?)",
            ("karin" if i % 2 else "piet", f"{details} {i}"),
        )
    db.commit()


def test_csv_export_volgt_het_filter(ingelogde_client, db):
    _vul_logboek(db, 4)
    tekst = ingelogde_client.get("/logboek/csv?dagen=30&gebruiker=karin").data.decode("utf-8-sig")
    assert tekst.startswith("Moment;Wie;Actie;Details")
    assert tekst.count("Rol gewijzigd") == 2
    assert ";piet;" not in tekst


def test_pdf_export_met_veel_en_lange_regels(ingelogde_client, db):
    _vul_logboek(db, 120, details="Een lange omschrijving " * 12)
    resp = ingelogde_client.get("/logboek/pdf")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")


def test_pdf_export_zonder_regels(ingelogde_client, db):
    db.execute("DELETE FROM logboek")
    db.commit()
    resp = ingelogde_client.get("/logboek/pdf?dagen=7")
    assert resp.status_code == 200 and resp.data.startswith(b"%PDF")


def test_export_is_alleen_voor_beheerders(client, db):
    _maak_vrijwilliger(db, "vrijwilliger", "test1234")
    client.post("/login", data={"naam": "vrijwilliger", "wachtwoord": "test1234", "csrf_token": _csrf(client)})
    assert client.get("/logboek/csv").status_code == 302
    assert client.get("/logboek/pdf").status_code == 302
