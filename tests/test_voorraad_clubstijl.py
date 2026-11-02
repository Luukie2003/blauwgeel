"""Het onderdeel Voorraad in de clubstijl (2.1): wat er op de computer bij is gekomen, en dat de handterminal-weergave
zijn eigen opmaak houdt."""

from datetime import date

from helpers import format_dag_lang


def test_dag_lang_noemt_het_jaar_alleen_als_het_niet_dit_jaar_is():
    vandaag = date(2026, 11, 2)
    assert format_dag_lang("2026-10-27 18:37", vandaag) == "dinsdag 27 oktober"
    assert format_dag_lang("2025-10-27", vandaag) == "maandag 27 oktober 2025"
    assert format_dag_lang("", vandaag) == ""


def _boeking(db, datum, opmerking=""):
    product = db.execute("SELECT id FROM producten WHERE actief = 1 LIMIT 1").fetchone()
    db.execute(
        "INSERT INTO mutaties (product_id, type, aantal, datum, naam, opmerking) VALUES (?, 'in', 3, ?, 'Test', ?)",
        (product["id"], datum, opmerking),
    )
    db.commit()


def test_mutatieoverzicht_per_dag_met_een_streep_bij_een_correctie(ingelogde_client, db):
    _boeking(db, "2026-10-27 18:37")
    _boeking(db, "2026-10-28 09:15", "Correctie (telling #5)")
    tekst = ingelogde_client.get("/geschiedenis").data.decode()
    assert "dinsdag 27 oktober" in tekst and "woensdag 28 oktober" in tekst
    assert tekst.index("woensdag 28 oktober") < tekst.index("dinsdag 27 oktober")  # de nieuwste bovenaan
    assert "rij-waarschuwing" in tekst


def test_tellingen_linken_naar_de_telling(ingelogde_client, db):
    telling_id = db.execute("INSERT INTO tellingen (datum, naam) VALUES ('2026-10-27 22:00', 'Test')").lastrowid
    db.commit()
    tekst = ingelogde_client.get("/tellingen").data.decode()
    assert f'href="/tellingen/{telling_id}"' in tekst
    assert "dinsdag 27 oktober" in ingelogde_client.get("/tellen").data.decode()  # de laatste telling bij de titel


def test_tellen_en_levering_tellen_wat_er_is_ingevuld(ingelogde_client):
    for pad, voorvoegsel in (("/tellen", "geteld_"), ("/leveringen/inboeken", "aantal_")):
        tekst = ingelogde_client.get(pad).data.decode()
        assert f'data-teller="{voorvoegsel}"' in tekst and "data-teller-uitkomst" in tekst and "cs-verzendbalk" in tekst


def test_boeken_op_de_computer_met_de_grote_in_uit_keuze(ingelogde_client):
    tekst = ingelogde_client.get("/boeken").data.decode()
    assert 'class="cs-inuit"' in tekst and 'class="toggle-type"' not in tekst
    ingelogde_client.get("/weergave/pda")
    tekst = ingelogde_client.get("/boeken").data.decode()
    assert 'class="toggle-type"' in tekst and "cs-inuit" not in tekst
