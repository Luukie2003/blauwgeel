from datetime import date

from conftest import stel_csrf_token_in as _csrf

from app import (
    bereken_kassa_coupure_bedrag,
    bereken_omzet_trend_periode,
    bereken_trend,
    besteleenheid_factor,
    besteleenheid_naam,
    naar_besteleenheden,
    naar_voorraadeenheden,
)


def _product(besteleenheid=None, factor=1, eenheid="Fles"):
    return {"besteleenheid": besteleenheid, "besteleenheid_factor": factor, "eenheid": eenheid}


class TestBesteleenheden:
    def test_naam_valt_terug_op_eenheid_zonder_besteleenheid(self):
        assert besteleenheid_naam(_product(besteleenheid=None)) == "Fles"

    def test_naam_gebruikt_besteleenheid_indien_gezet(self):
        assert besteleenheid_naam(_product(besteleenheid="Krat")) == "Krat"

    def test_factor_valt_terug_op_1_bij_lege_waarde(self):
        assert besteleenheid_factor(_product(factor=None)) == 1

    def test_factor_valt_terug_op_1_bij_nul_of_negatief(self):
        assert besteleenheid_factor(_product(factor=0)) == 1
        assert besteleenheid_factor(_product(factor=-5)) == 1

    def test_naar_besteleenheden_rondt_naar_boven_af(self):
        krat = _product(factor=24)
        assert naar_besteleenheden(25, krat) == 2  # net over een volle krat
        assert naar_besteleenheden(24, krat) == 1
        assert naar_besteleenheden(1, krat) == 1
        assert naar_besteleenheden(0, krat) == 0

    def test_naar_besteleenheden_kan_niet_negatief_worden(self):
        assert naar_besteleenheden(-10, _product(factor=24)) == 0

    def test_naar_voorraadeenheden_vermenigvuldigt_met_factor(self):
        krat = _product(factor=24)
        assert naar_voorraadeenheden(2, krat) == 48
        assert naar_voorraadeenheden(0, krat) == 0

    def test_naar_voorraadeenheden_kan_niet_negatief_worden(self):
        assert naar_voorraadeenheden(-3, _product(factor=24)) == 0


class TestKassaCoupureBedrag:
    def test_telt_coupures_correct_op(self):
        form = {"aantal_50": "1", "aantal_20": "2", "aantal_010": "3"}
        aantallen, totaal = bereken_kassa_coupure_bedrag(form)
        assert totaal == 50 + 40 + 0.30
        assert aantallen["aantal_50"] == 1
        assert aantallen["aantal_005"] == 0

    def test_negeert_negatieve_en_ongeldige_invoer(self):
        form = {"aantal_50": "-3", "aantal_20": "abc"}
        aantallen, totaal = bereken_kassa_coupure_bedrag(form)
        assert aantallen["aantal_50"] == 0
        assert aantallen["aantal_20"] == 0
        assert totaal == 0.0

    def test_lege_form_geeft_nul(self):
        _, totaal = bereken_kassa_coupure_bedrag({})
        assert totaal == 0.0


class TestBerekenTrend:
    def test_minder_dan_twee_afgeronde_weken_geeft_none(self):
        weken = [{"jaar": 2026, "week": 10, "omzet": 100}]
        assert bereken_trend(weken, huidige_jaar=2026, huidige_week=10) is None

    def test_negeert_de_nog_lopende_week(self):
        weken = [
            {"jaar": 2026, "week": 10, "omzet": 999},  # lopende week, telt niet mee
            {"jaar": 2026, "week": 9, "omzet": 100},
            {"jaar": 2026, "week": 8, "omzet": 100},
        ]
        resultaat = bereken_trend(weken, huidige_jaar=2026, huidige_week=10)
        assert resultaat is not None
        assert resultaat["verwachting"] == 100

    def test_herkent_stijgende_trend(self):
        weken = [
            {"jaar": 2026, "week": 4, "omzet": 400},
            {"jaar": 2026, "week": 3, "omzet": 300},
            {"jaar": 2026, "week": 2, "omzet": 200},
            {"jaar": 2026, "week": 1, "omzet": 100},
        ]
        resultaat = bereken_trend(weken, huidige_jaar=2026, huidige_week=5)
        assert resultaat["richting"] == "stijgend"

    def test_herkent_dalende_trend(self):
        weken = [
            {"jaar": 2026, "week": 4, "omzet": 100},
            {"jaar": 2026, "week": 3, "omzet": 200},
            {"jaar": 2026, "week": 2, "omzet": 300},
            {"jaar": 2026, "week": 1, "omzet": 400},
        ]
        resultaat = bereken_trend(weken, huidige_jaar=2026, huidige_week=5)
        assert resultaat["richting"] == "dalend"

    def test_herkent_stabiele_trend(self):
        weken = [
            {"jaar": 2026, "week": 4, "omzet": 100},
            {"jaar": 2026, "week": 3, "omzet": 99},
            {"jaar": 2026, "week": 2, "omzet": 101},
            {"jaar": 2026, "week": 1, "omzet": 100},
        ]
        resultaat = bereken_trend(weken, huidige_jaar=2026, huidige_week=5)
        assert resultaat["richting"] == "stabiel"


class TestOmzetTrendPeriode:
    def test_top_verkopers_bevat_alle_verkochte_producten(self, ingelogde_client, db):
        """Regressietest: HAVING verkocht > 0 (met een bare alias) liet
        SQLite alle producten behalve één laten vallen, ook als ze duidelijk
        verkocht waren. HAVING SUM(tr.verkocht) > 0 is de fix."""
        producten = db.execute(
            "SELECT * FROM producten WHERE actief = 1 LIMIT 2"
        ).fetchall()
        assert len(producten) == 2
        for p in producten:
            db.execute("UPDATE producten SET voorraad = 20 WHERE id = ?", (p["id"],))
        db.commit()

        ingelogde_client.post(
            "/tellen",
            data={
                "csrf_token": _csrf(ingelogde_client),
                f"geteld_{producten[0]['id']}": "5",  # 15 verkocht
                f"geteld_{producten[1]['id']}": "18",  # 2 verkocht
            },
        )

        vandaag = date.today().isoformat()
        resultaat = bereken_omzet_trend_periode(db, vandaag, vandaag)
        verkochte_namen = {r["product_naam"] for r in resultaat["top_verkopers"]}
        assert producten[0]["naam"] in verkochte_namen
        assert producten[1]["naam"] in verkochte_namen
