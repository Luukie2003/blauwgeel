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


class TestKassaLevenscyclus:
    def test_concept_telling_raakt_de_kassa_stand_nog_niet(self, ingelogde_client, db):
        _maak_concept_telling(ingelogde_client, bedrag_50=1)  # 50 euro geteld
        assert _stand(db) == 0.0

    def test_afsluiten_zet_kassa_stand_gelijk_aan_geteld_bedrag(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/afsluiten",
            data={"csrf_token": _csrf(ingelogde_client)},
        )
        assert _stand(db) == 50.0

    def test_afsluiten_kan_niet_dubbel(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        token = _csrf(ingelogde_client)
        ingelogde_client.post(f"/kassa/tellingen/{telling_id}/afsluiten", data={"csrf_token": token})
        ingelogde_client.post(f"/kassa/tellingen/{telling_id}/afsluiten", data={"csrf_token": token})
        # de tweede keer afsluiten mag de stand niet nogmaals verrekenen
        assert _stand(db) == 50.0

    def test_afgesloten_telling_kan_niet_meer_bewerkt_worden(self, ingelogde_client):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        token = _csrf(ingelogde_client)
        ingelogde_client.post(f"/kassa/tellingen/{telling_id}/afsluiten", data={"csrf_token": token})

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
        token = _csrf(ingelogde_client)
        ingelogde_client.post(f"/kassa/tellingen/{telling_id}/afsluiten", data={"csrf_token": token})
        assert _stand(db) == 50.0

        resp = ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/heropenen", data={"csrf_token": token}
        )
        assert resp.status_code == 302
        assert _stand(db) == 0.0

        resp = ingelogde_client.get(f"/kassa/tellingen/{telling_id}/bewerken")
        assert resp.status_code == 200

    def test_heropenen_geblokkeerd_na_latere_mutatie(self, ingelogde_client, db):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        token = _csrf(ingelogde_client)
        ingelogde_client.post(f"/kassa/tellingen/{telling_id}/afsluiten", data={"csrf_token": token})

        # daarna nog een toevoeging boeken -- verandert de kassa-stand
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

    def test_pdf_download_werkt_voor_open_en_gesloten_telling(self, ingelogde_client):
        telling_id = _maak_concept_telling(ingelogde_client, bedrag_50=1)
        resp = ingelogde_client.get(f"/kassa/tellingen/{telling_id}/pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"

        ingelogde_client.post(
            f"/kassa/tellingen/{telling_id}/afsluiten",
            data={"csrf_token": _csrf(ingelogde_client)},
        )
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
