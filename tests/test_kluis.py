from werkzeug.security import generate_password_hash

from app import bereken_kassalade_stand, bereken_kluis_stand
from conftest import stel_csrf_token_in as _csrf
from database import WACHTWOORD_HASH_METHODE

KOLOMMEN = [
    "aantal_50", "aantal_20", "aantal_10", "aantal_5", "aantal_2",
    "aantal_1", "aantal_050", "aantal_020", "aantal_010", "aantal_005",
]


def _coupure_data(csrf, **overrides):
    data = {"csrf_token": csrf}
    data.update({k: "0" for k in KOLOMMEN})
    data.update(overrides)
    return data


def _maak_concept_telling(client, bedrag_50=1):
    resp = client.post(
        "/kluis/tellen", data=_coupure_data(_csrf(client), aantal_50=str(bedrag_50))
    )
    assert resp.status_code == 302
    return int(resp.headers["Location"].rstrip("/").split("/")[-1])


def _kassalade_stand(db):
    return bereken_kassalade_stand(db)["stand"]


def _kluis_stand(db):
    return bereken_kluis_stand(db)["stand"]


def _wissel_naar_andere_gebruiker(client, db, naam="goedkeurder"):
    db.execute(
        "INSERT OR IGNORE INTO gebruikers (naam, wachtwoord_hash, rol, aangemaakt_op) "
        f"VALUES ('{naam}', 'x', 'beheerder', '2026-01-01 10:00')"
    )
    db.commit()
    gebruiker = db.execute("SELECT * FROM gebruikers WHERE naam = ?", (naam,)).fetchone()
    token = "test-csrf-token"
    with client.session_transaction() as sess:
        sess["gebruiker_id"] = gebruiker["id"]
        sess["gebruiker_naam"] = naam
        sess["gebruiker_rol"] = "beheerder"
        sess["csrf_token"] = token
    return token


def _keur_goed_als_ander(client, db, telling_id, opmerking=""):
    token = _wissel_naar_andere_gebruiker(client, db)
    return client.post(
        f"/kluis/tellingen/{telling_id}/goedkeuren",
        data={"csrf_token": token, "goedkeuring_opmerking": opmerking},
    )


class TestKluisLevenscyclus:
    def test_concept_telling_raakt_de_kluis_stand_nog_niet(self, ingelogde_client, db):
        _maak_concept_telling(ingelogde_client, bedrag_50=1)  # 50 euro geteld
        assert _kluis_stand(db) == 0.0

    def test_goedkeuren_zet_kluis_stand_gelijk_aan_geteld_bedrag(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        assert _kluis_stand(db) == 50.0

    def test_goedkeuren_kan_niet_dubbel(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        assert _kluis_stand(db) == 50.0

    def test_goedgekeurde_telling_kan_niet_meer_bewerkt_worden(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)

        resp = ingelogde_client.get(
            f"/kluis/tellingen/{telling_id}/bewerken", follow_redirects=True
        )
        assert "al afgesloten".encode() in resp.data

    def test_bewerken_past_open_telling_aan(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)  # 50 euro
        data = _coupure_data(_csrf(ingelogde_client), aantal_20="2")  # nu 40 euro i.p.v. 50
        resp = ingelogde_client.post(f"/kluis/tellingen/{telling_id}/bewerken", data=data)
        assert resp.status_code == 302

        resp = ingelogde_client.get(f"/kluis/tellingen/{telling_id}")
        assert "€ 40".encode() in resp.data

    def test_heropenen_zet_kluis_stand_terug_en_maakt_weer_bewerkbaar(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        assert _kluis_stand(db) == 50.0

        resp = ingelogde_client.post(
            f"/kluis/tellingen/{telling_id}/heropenen", data={"csrf_token": "test-csrf-token"}
        )
        assert resp.status_code == 302
        assert _kluis_stand(db) == 0.0

        resp = ingelogde_client.get(f"/kluis/tellingen/{telling_id}/bewerken")
        assert resp.status_code == 200

    def test_heropenen_geblokkeerd_na_latere_mutatie(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)

        token = _csrf(ingelogde_client)
        ingelogde_client.post(
            "/kluis/mutatie/nieuw",
            data={"csrf_token": token, "type": "storting", "bedrag": "5", "ontvanger": "", "opmerking": ""},
        )
        assert _kluis_stand(db) == 55.0

        resp = ingelogde_client.post(
            f"/kluis/tellingen/{telling_id}/heropenen",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert "kan niet meer".encode() in resp.data
        assert _kluis_stand(db) == 55.0

    def test_heropenen_van_nog_open_telling_wordt_geweigerd(self, ingelogde_client):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        resp = ingelogde_client.post(
            f"/kluis/tellingen/{telling_id}/heropenen",
            data={"csrf_token": _csrf(ingelogde_client)},
            follow_redirects=True,
        )
        assert "staat al open".encode() in resp.data

    def test_coupures_corrigeren_past_kluis_stand_aan_als_meest_recent(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)  # 50 geteld
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        assert _kluis_stand(db) == 50.0

        resp = ingelogde_client.post(
            f"/kluis/tellingen/{telling_id}/telling-corrigeren",
            data=_coupure_data(_csrf(ingelogde_client), aantal_50="2"),  # nu 100
        )
        assert resp.status_code == 302
        assert _kluis_stand(db) == 100.0

        telling = db.execute("SELECT * FROM kluis_tellingen WHERE id = ?", (telling_id,)).fetchone()
        assert telling["geteld_bedrag"] == 100.0
        assert telling["geteld_bedrag_voor_correctie"] == 50.0


class TestKluisMutaties:
    def test_storting_verhoogt_alleen_kluis_stand(self, ingelogde_client, db):
        ingelogde_client.post(
            "/kluis/mutatie/nieuw",
            data={
                "csrf_token": _csrf(ingelogde_client),
                "type": "storting",
                "bedrag": "100",
                "ontvanger": "Bank",
                "opmerking": "Openingsbalans",
            },
        )
        assert _kluis_stand(db) == 100.0
        assert _kassalade_stand(db) == 0.0  # kassalade blijft ongemoeid

    def test_opname_verlaagt_alleen_kluis_stand(self, ingelogde_client, db):
        ingelogde_client.post(
            "/kluis/mutatie/nieuw",
            data={"csrf_token": _csrf(ingelogde_client), "type": "storting", "bedrag": "100", "ontvanger": "", "opmerking": ""},
        )
        ingelogde_client.post(
            "/kluis/mutatie/nieuw",
            data={
                "csrf_token": _csrf(ingelogde_client),
                "type": "opname",
                "bedrag": "40",
                "ontvanger": "Bank",
                "opmerking": "",
            },
        )
        assert _kluis_stand(db) == 60.0
        assert _kassalade_stand(db) == 0.0

    def test_afdracht_en_toevoeging_raken_de_kluis_stand_niet_via_kluis_mutaties(self, ingelogde_client, db):
        """De kassalade<->kluis-overboeking loopt via /kassa/mutatie/nieuw
        (kassa_mutaties), niet via /kluis/mutatie/nieuw (kluis_mutaties) --
        de twee tabellen zijn strikt gescheiden."""
        ingelogde_client.post(
            "/kassa/mutatie/nieuw",
            data={"csrf_token": _csrf(ingelogde_client), "type": "afdracht", "bedrag": "10", "ontvanger": "", "opmerking": ""},
        )
        assert db.execute("SELECT COUNT(*) AS n FROM kluis_mutaties").fetchone()["n"] == 0
        assert _kluis_stand(db) == 10.0

    def test_mutatie_corrigeren_past_kluis_stand_aan(self, ingelogde_client, db):
        token = _csrf(ingelogde_client)
        ingelogde_client.post(
            "/kluis/mutatie/nieuw",
            data={"csrf_token": token, "type": "storting", "bedrag": "10", "ontvanger": "", "opmerking": ""},
        )
        mutatie = db.execute("SELECT * FROM kluis_mutaties ORDER BY id DESC LIMIT 1").fetchone()
        assert _kluis_stand(db) == 10.0

        resp = ingelogde_client.post(
            f"/kluis/mutaties/{mutatie['id']}/corrigeren",
            data={"csrf_token": token, "bedrag": "15"},
        )
        assert resp.status_code == 302
        assert _kluis_stand(db) == 15.0

        mutatie_na = db.execute("SELECT * FROM kluis_mutaties WHERE id = ?", (mutatie["id"],)).fetchone()
        assert mutatie_na["bedrag"] == 15.0
        assert mutatie_na["bedrag_voor_correctie"] == 10.0

    def test_mutatie_corrigeren_raakt_kluis_stand_niet_na_latere_telling(self, ingelogde_client, db):
        token = _csrf(ingelogde_client)
        ingelogde_client.post(
            "/kluis/mutatie/nieuw",
            data={"csrf_token": token, "type": "storting", "bedrag": "10", "ontvanger": "", "opmerking": ""},
        )
        mutatie = db.execute("SELECT * FROM kluis_mutaties ORDER BY id DESC LIMIT 1").fetchone()
        db.execute("UPDATE kluis_mutaties SET datum = '2020-01-01 10:00' WHERE id = ?", (mutatie["id"],))
        db.commit()

        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)  # 50 geteld
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        assert _kluis_stand(db) == 50.0

        resp = ingelogde_client.post(
            f"/kluis/mutaties/{mutatie['id']}/corrigeren",
            data={"csrf_token": _csrf(ingelogde_client), "bedrag": "25"},
        )
        assert resp.status_code == 302
        assert _kluis_stand(db) == 50.0  # ongewijzigd


def _maak_vrijwilliger(db, naam, secties):
    db.execute(
        "INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, aangemaakt_op) "
        "VALUES (?, ?, 'vrijwilliger', ?, '2026-01-01 10:00')",
        (naam, generate_password_hash("test1234", method=WACHTWOORD_HASH_METHODE), secties),
    )
    db.commit()


def _login(client, naam):
    csrf = _csrf(client)
    resp = client.post(
        "/login", data={"naam": naam, "wachtwoord": "test1234", "csrf_token": csrf}
    )
    assert resp.status_code == 302
    return csrf


class TestKluisRechten:
    def test_vrijwilliger_met_kassa_sectie_wordt_geweerd_uit_kluis(self, client, db):
        _maak_vrijwilliger(db, "kassa_vrijwilliger", "kassa")
        _login(client, "kassa_vrijwilliger")

        for pad in ("/kluis/tellen", "/kluis/geschiedenis", "/kluis/mutatie/nieuw"):
            resp = client.get(pad, follow_redirects=True)
            assert resp.status_code == 200
            assert b"alleen voor beheerders" in resp.data

    def test_vrijwilliger_met_kassa_sectie_mag_nog_gewoon_bij_afdracht_toevoeging(self, client, db):
        _maak_vrijwilliger(db, "kassa_vrijwilliger2", "kassa")
        _login(client, "kassa_vrijwilliger2")

        resp = client.get("/kassa/mutatie/nieuw")
        assert resp.status_code == 200

    def test_beheerder_mag_wel_bij_kluis(self, ingelogde_client):
        resp = ingelogde_client.get("/kluis/tellen")
        assert resp.status_code == 200

    def test_kluis_groep_verschijnt_niet_in_zijbalk_voor_vrijwilliger(self, client, db):
        _maak_vrijwilliger(db, "kassa_vrijwilliger3", "kassa")
        _login(client, "kassa_vrijwilliger3")

        resp = client.get("/")
        assert resp.status_code == 200
        assert b'href="/kluis/tellen"' not in resp.data

    def test_kluis_groep_verschijnt_in_zijbalk_voor_beheerder(self, ingelogde_client):
        resp = ingelogde_client.get("/")
        assert resp.status_code == 200
        assert b'href="/kluis/tellen"' in resp.data
