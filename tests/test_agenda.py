"""Start > Agenda: de komende weken in de kantine per dag."""

from datetime import date, timedelta

from test_secties_rechten import _login, _maak_vrijwilliger

from activiteiten import bouw_agenda


def _dagen(weken):
    return {d["datum"]: d for w in weken for d in w["dagen"]}


def test_de_agenda_zet_alles_per_dag_bij_elkaar(db):
    maandag = date(2026, 10, 19)
    db.execute("UPDATE instellingen SET verkoopdagen = '2,5' WHERE id = 1")
    db.execute("INSERT INTO wedstrijden (team, datum, tijd, omschrijving, thuis) VALUES ('Za1', '2026-10-24', '14:30', 'BG Za1 - Gruno 6', 1)")
    db.execute("INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('Za2', '2026-10-24', 'Uit wedstrijd', 0)")
    db.execute("INSERT INTO evenementen (datum, naam, soort, groep, aangemaakt_op) VALUES ('2026-10-25', 'UC Lunch', 'rustig', 'UC', 'x')")
    db.execute("INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op) VALUES ('2026-10-24', '13:00', '17:00', 'Piet en Kees', 'x')")
    db.execute("INSERT INTO verkoop_uitzonderingen (datum, open, opmerking) VALUES ('2026-10-21', 0, 'Herfstvakantie')")
    db.execute("INSERT INTO weer_voorspelling (datum, max_temp, neerslag_kans, weercode) VALUES ('2026-10-24', 16, 10, 1)")
    db.commit()

    dagen = _dagen(bouw_agenda(db, maandag, 7))

    assert set(dagen) == {"2026-10-21", "2026-10-24", "2026-10-25"}  # maandag, dinsdag enz. zonder iets blijven weg
    woensdag, zaterdag, zondag = dagen["2026-10-21"], dagen["2026-10-24"], dagen["2026-10-25"]
    assert not woensdag["open"] and woensdag["dicht_op_vaste_dag"] and woensdag["uitzondering_tekst"] == "Herfstvakantie"
    assert zaterdag["open"] and [w["omschrijving"] for w in zaterdag["wedstrijden"]] == ["BG Za1 - Gruno 6"]  # alleen thuis
    assert zaterdag["bardiensten"][0]["namen"] == "Piet en Kees" and zaterdag["weer"]["max_temp"] == 16
    assert zondag["open"] and zondag["evenementen"][0]["groep"] == "UC"  # een evenement maakt de dag open


def test_de_agendapagina_voor_iedereen(client, db):
    from helpers.tijd import vandaag_amsterdam

    morgen = vandaag_amsterdam() + timedelta(days=1)
    db.execute("INSERT INTO evenementen (datum, naam, soort, groep, aangemaakt_op) VALUES (?, 'UC Lunch', 'rustig', 'UC', 'x')", (morgen.isoformat(),))
    db.commit()
    _maak_vrijwilliger(db, "kok", "keuken")  # geen voorraadsectie: wel de agenda, geen omzet
    _login(client, "kok")
    tekst = client.get("/agenda").data.decode()
    assert "UC Lunch" in tekst and "morgen" in tekst and "rustig" in tekst
    assert "agenda/omzet" not in tekst and 'href="/agenda"' in tekst
    assert client.get("/agenda/omzet", follow_redirects=True).request.path != "/agenda/omzet"  # mag de omzet niet zien


def test_de_omzet_per_dag_komt_apart(ingelogde_client, db, monkeypatch):
    from datetime import date as d

    monkeypatch.setattr("routes.activiteiten.maak_prognose", lambda db, dagen: {
        "beschikbaar": True, "dagen_overzicht": [{"datum": d(2026, 10, 24), "open": True, "omzet": 812.4},
                                                 {"datum": d(2026, 10, 25), "open": False, "omzet": 0}]})
    tekst = ingelogde_client.get("/agenda/omzet").data.decode()
    assert 'id="agenda-omzet"' in tekst and "2026-10-24" in tekst and "812" in tekst and "2026-10-25" not in tekst
    assert 'data-lazy-bron="/agenda/omzet?dagen=21"' in ingelogde_client.get("/agenda").data.decode()
    assert db.execute("SELECT COUNT(*) FROM paginabezoeken WHERE endpoint = 'agenda_omzet'").fetchone()[0] == 0


def test_de_melding_op_het_overzicht_wijst_naar_de_agenda(ingelogde_client, db):
    from helpers.tijd import vandaag_amsterdam

    db.execute("INSERT INTO evenementen (datum, naam, soort, aangemaakt_op) VALUES (?, 'Jeugdtoernooi', 'druk', 'x')",
               ((vandaag_amsterdam() + timedelta(days=2)).isoformat(),))
    db.commit()
    tekst = ingelogde_client.get("/").data.decode()
    blok = tekst[tekst.index("Jeugdtoernooi") - 300: tekst.index("Jeugdtoernooi")]
    assert 'href="/agenda"' in blok
