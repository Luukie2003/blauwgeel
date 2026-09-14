from datetime import date, timedelta

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
from helpers import bereken_week_overzicht


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

    def test_negeert_weken_met_afwijkende_periode(self):
        """Een week die geteld is op een ongebruikelijke dag (bijv. vrijdag
        i.p.v. de gebruikelijke maandag) krijgt een veel te korte of lange
        periode -- die moet de trend niet vervuilen met een schijnbare
        piek/dal die alleen door de teldag komt."""
        weken = [
            {"jaar": 2026, "week": 4, "omzet": 100},
            {"jaar": 2026, "week": 3, "omzet": 100},
            # Deze week zou de trend naar 'stijgend' trekken als hij meetelde.
            {"jaar": 2026, "week": 2, "omzet": 5000, "afwijkende_periode": True},
            {"jaar": 2026, "week": 1, "omzet": 100},
        ]
        resultaat = bereken_trend(weken, huidige_jaar=2026, huidige_week=5)
        assert resultaat["richting"] == "stabiel"
        assert resultaat["gebaseerd_op_weken"] == 3  # de afwijkende week telt niet mee


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

    def _maak_telling(self, db, product_id, verkocht, datum):
        cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (datum,))
        telling_id = cur.lastrowid
        product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()
        db.execute(
            """INSERT INTO telling_regels
               (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telling_id, product_id, verkocht + 5, 5, verkocht, 2.0),
        )
        db.commit()
        return telling_id

    def test_periodelengte_en_omzet_per_dag(self, db):
        product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
        # 2024-01-01 is een maandag; de telling valt 6 dagen later (zondag),
        # dus een gebruikelijke weeklengte -- niet afwijkend.
        self._maak_telling(db, product["id"], verkocht=70, datum="2024-01-07 12:00")

        resultaat = bereken_omzet_trend_periode(db, "2024-01-01", "2024-01-07")
        balk = resultaat["balken"][0]
        assert balk["aantal_dagen"] == 6
        assert balk["omzet_per_dag"] == balk["omzet"] / 6
        assert balk["periode_afwijkend"] is False
        assert resultaat["bevat_afwijkende_periode"] is False

    def test_korte_periode_wordt_als_afwijkend_gemarkeerd(self, db):
        product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
        # Slechts 3 dagen na 'van' geteld (bijv. maandag ipv de gebruikelijke
        # vrijdag) -- veel korter dan een gebruikelijke week.
        self._maak_telling(db, product["id"], verkocht=10, datum="2024-01-04 12:00")

        resultaat = bereken_omzet_trend_periode(db, "2024-01-01", "2024-01-04")
        balk = resultaat["balken"][0]
        assert balk["aantal_dagen"] == 3
        assert balk["periode_afwijkend"] is True
        assert resultaat["bevat_afwijkende_periode"] is True

    def test_toont_trainingsavonden_in_periode(self, db):
        product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
        # 2024-01-01 (maandag) t/m 2024-01-04 (donderdag) bevat precies één
        # woensdag (2024-01-03) -- de vaste trainingsavond van alle teams.
        self._maak_telling(db, product["id"], verkocht=10, datum="2024-01-04 12:00")

        resultaat = bereken_omzet_trend_periode(db, "2024-01-01", "2024-01-04")
        assert resultaat["balken"][0]["trainingsavonden"] == 1

    def test_geen_trainingsavond_buiten_periode(self, db):
        product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
        # 2024-01-01 (maandag) t/m 2024-01-02 (dinsdag) bevat geen woensdag.
        self._maak_telling(db, product["id"], verkocht=10, datum="2024-01-02 12:00")

        resultaat = bereken_omzet_trend_periode(db, "2024-01-01", "2024-01-02")
        assert resultaat["balken"][0]["trainingsavonden"] == 0

    def test_eerste_balk_gebruikt_echte_vorige_telling_voor_periodelengte(self, db):
        """Als de eerste telling binnen een venster (zoals het weekoverzicht
        dat gebruikt) een echte, oudere telling heeft die er precies een
        week aan voorafging, mag die balk niet als 'afwijkend' gelden --
        ook al ligt die oudere telling zelf buiten het gekozen venster."""
        product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
        self._maak_telling(db, product["id"], verkocht=50, datum="2023-12-25 09:00")  # maandag
        self._maak_telling(db, product["id"], verkocht=60, datum="2024-01-01 09:00")  # maandag erna

        # Venster begint pas op 2024-01-01 zelf -- de telling van 2023-12-25
        # valt hier dus buiten, maar telt wel mee voor de periodelengte.
        resultaat = bereken_omzet_trend_periode(db, "2024-01-01", "2024-01-07")
        balk = resultaat["balken"][0]
        assert balk["aantal_dagen"] == 7
        assert balk["periode_afwijkend"] is False


class TestWeekOverzicht:
    def _maak_telling(self, db, product_id, verkocht, datum):
        cur = db.execute("INSERT INTO tellingen (datum, naam) VALUES (?, 'test')", (datum,))
        telling_id = cur.lastrowid
        product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()
        db.execute(
            """INSERT INTO telling_regels
               (telling_id, product_id, voorraad_voor, geteld_aantal, verkocht, verkoopprijs)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telling_id, product_id, verkocht + 5, 5, verkocht, 2.0),
        )
        db.commit()

    def test_geen_waarschuwing_bij_gebruikelijke_weeklengte(self, db):
        product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
        # Vier tellingen, telkens precies een week uit elkaar op maandag.
        for datum in ("2023-12-18", "2023-12-25", "2024-01-01", "2024-01-08"):
            self._maak_telling(db, product["id"], 50, f"{datum} 09:00")

        overzicht = bereken_week_overzicht(db, vandaag=date(2024, 1, 8))
        assert overzicht["afwijkende_periode"] is False

    def test_waarschuwing_bij_afwijkende_teldag(self, db):
        product = db.execute("SELECT * FROM producten WHERE actief = 1 LIMIT 1").fetchone()
        for datum in ("2023-12-18", "2023-12-25", "2024-01-01"):
            self._maak_telling(db, product["id"], 50, f"{datum} 09:00")
        # Deze keer op vrijdag geteld i.p.v. de gebruikelijke maandag --
        # maar 4 dagen na de vorige telling, een veel kortere periode.
        self._maak_telling(db, product["id"], 30, "2024-01-05 09:00")

        overzicht = bereken_week_overzicht(db, vandaag=date(2024, 1, 8))
        assert overzicht["afwijkende_periode"] is True
