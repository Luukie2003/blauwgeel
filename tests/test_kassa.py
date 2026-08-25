from datetime import datetime, timedelta

from app import bereken_kassa_stand
from conftest import stel_csrf_token_in as _csrf

KOLOMMEN = [
    "aantal_50", "aantal_20", "aantal_10", "aantal_5", "aantal_2",
    "aantal_1", "aantal_050", "aantal_020", "aantal_010", "aantal_005",
]


def _maak_concept_telling(client, bedrag_50=1, contante_omzet="0"):
    data = {"csrf_token": _csrf(client), "contante_omzet": contante_omzet}
    data.update({k: "0" for k in KOLOMMEN})
    data["aantal_50"] = str(bedrag_50)
    resp = client.post("/kassa/tellen", data=data, follow_redirects=False)
    assert resp.status_code == 302
    return int(resp.headers["Location"].rstrip("/").split("/")[-1])


def _stand(db):
    return bereken_kassa_stand(db)["stand"]


def _wissel_naar_andere_gebruiker(client, db, naam="goedkeurder"):
    """Vier-ogen-principe: de teller mag zijn eigen telling niet meteen
    zelf goedkeuren, dus voor tests die dat wel willen (om iets anders te
    testen) is een tweede sessie nodig."""
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
        f"/kassa/tellingen/{telling_id}/goedkeuren",
        data={"csrf_token": token, "goedkeuring_opmerking": opmerking},
    )


class TestKassaLevenscyclus:
    def test_concept_telling_raakt_de_kassa_stand_nog_niet(self, ingelogde_client, db):
        _maak_concept_telling(ingelogde_client, bedrag_50=1)  # 50 euro geteld
        assert _stand(db) == 0.0

    def test_goedkeuren_zet_kassa_stand_gelijk_aan_geteld_bedrag(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        assert _stand(db) == 50.0

    def test_goedkeuren_kan_niet_dubbel(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        # de tweede keer goedkeuren mag de stand niet nogmaals verrekenen
        assert _stand(db) == 50.0

    def test_goedgekeurde_telling_kan_niet_meer_bewerkt_worden(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)

        resp = ingelogde_client.get(
            f"/kassa/tellingen/{telling_id}/bewerken", follow_redirects=True
        )
        assert "al afgesloten".encode() in resp.data

    def test_bewerken_past_open_telling_aan(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)  # 50 euro
        data = {"csrf_token": _csrf(ingelogde_client), "contante_omzet": "0"}
        data.update({k: "0" for k in KOLOMMEN})
        data["aantal_20"] = "2"  # nu 40 euro i.p.v. 50
        resp = ingelogde_client.post(f"/kassa/tellingen/{telling_id}/bewerken", data=data)
        assert resp.status_code == 302

        resp = ingelogde_client.get(f"/kassa/tellingen/{telling_id}")
        assert "€ 40".encode() in resp.data

    def test_heropenen_zet_kassa_stand_terug_en_maakt_weer_bewerkbaar(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        assert _stand(db) == 50.0

        resp = ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/heropenen", data={"csrf_token": "test-csrf-token"}
        )
        assert resp.status_code == 302
        assert _stand(db) == 0.0

        resp = ingelogde_client.get(f"/kassa/tellingen/{telling_id}/bewerken")
        assert resp.status_code == 200

    def test_heropenen_wist_goedkeuring_gegevens(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id, opmerking="Klopt helemaal")
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        assert telling["goedgekeurd_door"] == "goedkeurder"
        assert telling["goedkeuring_opmerking"] == "Klopt helemaal"

        token = _csrf(ingelogde_client)
        ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/heropenen", data={"csrf_token": token}
        )
        telling = db.execute(
            "SELECT * FROM kassa_tellingen WHERE id = ?", (telling_id,)
        ).fetchone()
        assert telling["goedgekeurd_door"] is None
        assert telling["goedgekeurd_op"] is None
        assert telling["goedkeuring_opmerking"] is None

    def test_heropenen_geblokkeerd_na_latere_mutatie(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id)

        # daarna nog een toevoeging boeken -- verandert de kassa-stand
        token = _csrf(ingelogde_client)
        ingelogde_client.post(
            "/kassa/mutatie/nieuw",
            data={
                "csrf_token": token,
                "type": "toevoeging",
                "bedrag": "5",
                "ontvanger": "",
                "opmerking": "",
            },
        )
        assert _stand(db) == 55.0

        resp = ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/heropenen",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert "kan niet meer".encode() in resp.data
        assert _stand(db) == 55.0  # de geblokkeerde poging heeft niets veranderd

    def test_heropenen_van_nog_open_telling_wordt_geweigerd(self, ingelogde_client):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        resp = ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/heropenen",
            data={"csrf_token": _csrf(ingelogde_client)},
            follow_redirects=True,
        )
        assert "staat al open".encode() in resp.data

    def test_pdf_download_werkt_voor_open_en_gesloten_telling(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        resp = ingelogde_client.get(f"/kassa/tellingen/{telling_id}/pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"

        _keur_goed_als_ander(ingelogde_client, db, telling_id)
        resp = ingelogde_client.get(f"/kassa/tellingen/{telling_id}/pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"

    def test_afdracht_verlaagt_kassa_stand(self, ingelogde_client, db):
        ingelogde_client.post(
            "/kassa/mutatie/nieuw",
            data={
                "csrf_token": _csrf(ingelogde_client),
                "type": "afdracht",
                "bedrag": "10",
                "ontvanger": "penningmeester",
                "opmerking": "",
            },
        )
        assert _stand(db) == -10.0


class TestKassaVierOgenPrincipe:
    def test_teller_kan_eigen_telling_niet_meteen_goedkeuren(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        resp = ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/goedkeuren",
            data={"csrf_token": _csrf(ingelogde_client)},
            follow_redirects=True,
        )
        assert "niet goedkeuren".encode() in resp.data
        assert _stand(db) == 0.0  # geblokkeerd, dus niets verrekend

    def test_andere_gebruiker_mag_direct_goedkeuren(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        resp = _keur_goed_als_ander(ingelogde_client, db, telling_id)
        assert resp.status_code == 302
        assert _stand(db) == 50.0

    def test_teller_mag_na_wachtdagen_alsnog_zelf_goedkeuren(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        oude_datum = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d %H:%M")
        db.execute(
            "UPDATE kassa_tellingen SET datum = ? WHERE id = ?", (oude_datum, telling_id)
        )
        db.commit()

        resp = ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/goedkeuren",
            data={"csrf_token": _csrf(ingelogde_client)},
        )
        assert resp.status_code == 302
        assert _stand(db) == 50.0

    def test_goedkeuring_opmerking_en_naam_worden_getoond(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        _keur_goed_als_ander(ingelogde_client, db, telling_id, opmerking="Coupures dubbel gecheckt")

        resp = ingelogde_client.get(f"/kassa/tellingen/{telling_id}")
        assert "goedkeurder".encode() in resp.data
        assert "Coupures dubbel gecheckt".encode() in resp.data
