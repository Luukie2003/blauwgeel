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
