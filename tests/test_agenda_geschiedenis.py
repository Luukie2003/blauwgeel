import sqlite3

import agenda


def _nep_ics(wedstrijden):
    """Bouwt genoeg van een iCal-feed om _parse_ics tevreden te stellen."""
    regels = ["BEGIN:VCALENDAR", "X-WR-CALNAME:Voetbal.nl - Testteam"]
    for datum, omschrijving in wedstrijden:
        regels += [
            "BEGIN:VEVENT",
            f"DTSTART:{datum}T140000",
            f"SUMMARY:{omschrijving}",
            "END:VEVENT",
        ]
    regels.append("END:VCALENDAR")
    return "\n".join(regels)


def test_ververs_bewaart_gespeelde_wedstrijden(app, db, monkeypatch):
    """Regressietest voor de hoofdklacht: gespeelde wedstrijden mogen niet
    verdwijnen bij de volgende ververs-ronde."""
    db_pad = app.config["DATABASE"]
    db.execute("INSERT INTO agenda_feeds (url) VALUES ('https://voorbeeld.nl/feed.ics')")
    db.commit()

    ics_met_verleden_en_toekomst = _nep_ics(
        [("20200101", "Testteam-Oude Tegenstander"), ("20990101", "Testteam-Toekomstige Tegenstander")]
    )

    def nep_urlopen(url, timeout=None):
        class NepResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return ics_met_verleden_en_toekomst.encode("utf-8")

        return NepResponse()

    monkeypatch.setattr(agenda, "urlopen", nep_urlopen)

    aantal_eerste_ronde = agenda.ververs_wedstrijden(db_pad=db_pad)
    assert aantal_eerste_ronde == 2

    conn = sqlite3.connect(db_pad)
    conn.row_factory = sqlite3.Row
    rijen = conn.execute("SELECT * FROM wedstrijden").fetchall()
    assert len(rijen) == 2
    datums = {r["datum"] for r in rijen}
    assert "2020-01-01" in datums  # de "gespeelde" wedstrijd is niet weggefilterd
    assert "2099-01-01" in datums

    # Tweede ronde met dezelfde feed-inhoud: geen nieuwe/dubbele rijen.
    aantal_tweede_ronde = agenda.ververs_wedstrijden(db_pad=db_pad)
    assert aantal_tweede_ronde == 0
    assert conn.execute("SELECT COUNT(*) FROM wedstrijden").fetchone()[0] == 2
    conn.close()


def test_parse_ics_haalt_lokale_aanvangstijd_eruit():
    """_nep_ics bouwt een DTSTART zonder Z-suffix (T140000) -- net als een
    KNVB/Sportlink-feed zonder expliciete tijdzone, al lokale (Amsterdamse)
    tijd te lezen."""
    wedstrijden = agenda._parse_ics(_nep_ics([("20260920", "Testteam-Tegenstander")]))
    assert wedstrijden[0]["tijd"] == "14:00"


def test_parse_ics_zonder_tijd_geeft_none():
    """Een 'hele dag'-agenda-item (DTSTART;VALUE=DATE, geen T-tijdstip) heeft
    geen aanvangstijd."""
    ics = (
        "BEGIN:VCALENDAR\nX-WR-CALNAME:Voetbal.nl - Testteam\n"
        "BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260920\nSUMMARY:Testteam-Tegenstander\nEND:VEVENT\n"
        "END:VCALENDAR"
    )
    wedstrijden = agenda._parse_ics(ics)
    assert wedstrijden[0]["tijd"] is None


def test_parse_ics_utc_tijd_wordt_omgezet_naar_amsterdam():
    """Een Z-suffix betekent UTC -- moet omgezet worden naar Europe/Amsterdam
    (in de zomer UTC+2, dus 12:00 UTC wordt 14:00 lokaal)."""
    ics = (
        "BEGIN:VCALENDAR\nX-WR-CALNAME:Voetbal.nl - Testteam\n"
        "BEGIN:VEVENT\nDTSTART:20260620T120000Z\nSUMMARY:Testteam-Tegenstander\nEND:VEVENT\n"
        "END:VCALENDAR"
    )
    wedstrijden = agenda._parse_ics(ics)
    assert wedstrijden[0]["datum"] == "2026-06-20"
    assert wedstrijden[0]["tijd"] == "14:00"


def test_ververs_vult_tijd_alsnog_in_bij_bestaande_wedstrijd(app, db, monkeypatch):
    """Een wedstrijd die al bekend was zonder tijd (bijv. van vóór deze
    functie bestond) moet bij een volgende ververs-ronde alsnog zijn tijd
    krijgen -- INSERT OR IGNORE raakt een bestaande rij anders niet aan."""
    db_pad = app.config["DATABASE"]
    db.execute("INSERT INTO agenda_feeds (url) VALUES ('https://voorbeeld.nl/feed.ics')")
    db.execute(
        """INSERT INTO wedstrijden (team, datum, omschrijving, thuis)
           VALUES ('Testteam', '2099-01-01', 'Testteam-Tegenstander', 1)"""
    )
    db.commit()

    ics = _nep_ics([("20990101", "Testteam-Tegenstander")])

    def nep_urlopen(url, timeout=None):
        class NepResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return ics.encode("utf-8")

        return NepResponse()

    monkeypatch.setattr(agenda, "urlopen", nep_urlopen)
    agenda.ververs_wedstrijden(db_pad=db_pad)

    conn = sqlite3.connect(db_pad)
    conn.row_factory = sqlite3.Row
    rij = conn.execute("SELECT * FROM wedstrijden WHERE datum = '2099-01-01'").fetchone()
    assert rij["tijd"] == "14:00"
    conn.close()
