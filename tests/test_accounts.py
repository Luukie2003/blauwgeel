from conftest import stel_csrf_token_in as _csrf


def _maak_tweede_beheerder(db):
    db.execute(
        """INSERT INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op)
           VALUES ('tweede', 'onbruikbaar', 'beheerder', '2026-01-01 10:00')"""
    )
    db.commit()
    return db.execute("SELECT id FROM gebruikers WHERE naam = 'tweede'").fetchone()["id"]


def test_verwijderen_van_account_met_boekingsgeschiedenis_geeft_nette_foutmelding(
    ingelogde_client, db
):
    """mutaties.gebruiker_id heeft bewust geen ON DELETE CASCADE (die
    geschiedenis mag nooit stilzwijgend verdwijnen) -- verwijderen van zo'n
    account moet dus netjes geweigerd worden i.p.v. een 500
    (sqlite3.IntegrityError)."""
    gebruiker_id = _maak_tweede_beheerder(db)
    product = db.execute("SELECT id FROM producten LIMIT 1").fetchone()
    db.execute(
        "INSERT INTO mutaties (product_id, type, aantal, datum, gebruiker_id) "
        "VALUES (?, 'in', 1, '2026-01-01', ?)",
        (product["id"], gebruiker_id),
    )
    db.commit()

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    nog_aanwezig = db.execute(
        "SELECT id FROM gebruikers WHERE id = ?", (gebruiker_id,)
    ).fetchone()
    assert nog_aanwezig is not None

    vervolg = ingelogde_client.get(resp.headers["Location"])
    assert "kan niet verwijderd worden" in vervolg.data.decode()


def test_verwijderen_van_account_met_bestelgeschiedenis_geeft_nette_foutmelding(
    ingelogde_client, db
):
    gebruiker_id = _maak_tweede_beheerder(db)
    db.execute(
        "INSERT INTO bestellingen (status, aangemaakt_op, besteld_door_id) "
        "VALUES ('besteld', '2026-01-01 10:00', ?)",
        (gebruiker_id,),
    )
    db.commit()

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    nog_aanwezig = db.execute(
        "SELECT id FROM gebruikers WHERE id = ?", (gebruiker_id,)
    ).fetchone()
    assert nog_aanwezig is not None


def test_verwijderen_van_account_zonder_geschiedenis_werkt_nog_gewoon(ingelogde_client, db):
    gebruiker_id = _maak_tweede_beheerder(db)

    resp = ingelogde_client.post(
        f"/accounts/{gebruiker_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302

    weg = db.execute("SELECT id FROM gebruikers WHERE id = ?", (gebruiker_id,)).fetchone()
    assert weg is None
