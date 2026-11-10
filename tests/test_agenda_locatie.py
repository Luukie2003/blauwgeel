"""Thuis of uit volgens de plek (agenda.py, THUIS_LOCATIE). Bij een 7-tegen-7-avond op ons veld staat Blauw-Geel in
twee van de drie wedstrijden als tweede ploeg, maar alle drie worden ze op Kooiweg 4 gespeeld. Geeft Sportlink een
locatie mee, dan beslist die; zonder locatie de volgorde van de ploegen, zoals eerst."""

import agenda

TEAM = "Blauw Geel'15 18+1"
THUIS = "Sportpark Coendersborg Kooiweg 4 9722BZ GRONINGEN"
ELDERS = "Sportpark De Kluiving Kluivingsweg 3 9605PA HARKSTEDE"
# Hetzelfde sportpark, maar het veld en de kantine van Oranje Nassau (Kooiweg 1) of Amicitia VMC (Kooiweg 3).
BUREN = "Sportpark Coendersborg Kooiweg 1 9722BZ GRONINGEN"


def _ics(*events):
    """events: (tijd 'HHMM', omschrijving, locatie of None)."""
    regels = ["BEGIN:VCALENDAR", f"X-WR-CALNAME:Voetbal.nl - {TEAM}"]
    for tijd, omschrijving, locatie in events:
        regels += ["BEGIN:VEVENT", f"DTSTART:20261113T{tijd}00", f"SUMMARY:{omschrijving}"]
        if locatie is not None:
            regels.append(f"LOCATION:{locatie}")
        regels.append("END:VEVENT")
    regels.append("END:VCALENDAR")
    return "\n".join(regels)


# Zoals de feed van 18+1 het op vrijdag 13 november 2026 gaf.
AVOND = _ics(
    ("1930", "Blauw Geel'15 18+1-FVV 18+2", THUIS),
    ("2000", "Harkstede 18+1-Blauw Geel'15 18+1", THUIS),
    ("2030", "HSC 18+1-Blauw Geel'15 18+1", THUIS),
)


def test_een_7_tegen_7_avond_op_ons_veld_is_drie_keer_thuis():
    assert [w["thuis"] for w in agenda._parse_ics(AVOND)] == [True, True, True]


def test_als_eerste_ploeg_maar_op_een_ander_veld_is_uit():
    assert agenda._parse_ics(_ics(("1930", "Blauw Geel'15 18+1-Harkstede 18+1", ELDERS)))[0]["thuis"] is False


def test_bij_de_buren_op_coendersborg_is_uit():
    wedstrijden = agenda._parse_ics(_ics(
        ("1300", "Oranje Nassau 6-Blauw Geel'15 2", BUREN),
        ("1500", "Amicitia VMC 7-Blauw Geel'15 3", BUREN.replace("Kooiweg 1", "Kooiweg 3")),
        ("1700", "Blauw Geel'15 2-Kooiweg FC 1", THUIS.replace("Kooiweg 4", "Kooiweg 40")),  # niet ons nummer
    ))
    assert [w["thuis"] for w in wedstrijden] == [False, False, False]


def test_zonder_locatie_beslist_de_volgorde_zoals_eerst():
    wedstrijden = agenda._parse_ics(_ics(
        ("1930", "Blauw Geel'15 18+1-FVV 18+2", None), ("2000", "HSC 18+1-Blauw Geel'15 18+1", None)))
    assert [w["thuis"] for w in wedstrijden] == [True, False]


def test_een_locatie_over_meer_regels():
    gevouwen = AVOND.replace(f"LOCATION:{THUIS}", "LOCATION:Sportpark Coenders\n borg Kooi\n weg 4 9722BZ GRONINGEN")
    assert all(w["thuis"] for w in agenda._parse_ics(gevouwen))


def test_een_wedstrijd_die_er_al_stond_wordt_alsnog_thuis(app, db, monkeypatch):
    # Eerder binnengekomen met de oude regel: Harkstede en HSC als uitwedstrijd.
    for omschrijving, thuis in [("Blauw Geel'15 18+1-FVV 18+2", 1), ("Harkstede 18+1-Blauw Geel'15 18+1", 0),
                                ("HSC 18+1-Blauw Geel'15 18+1", 0)]:
        db.execute("INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES (?, '2026-11-13', ?, ?)",
                   (TEAM, omschrijving, thuis))
    db.execute("INSERT INTO agenda_feeds (url, team) VALUES ('https://sportlink.test/ical-team', ?)", (TEAM,))
    db.commit()
    monkeypatch.setattr(agenda, "haal_feed_op", lambda url: (TEAM, agenda._parse_ics(AVOND)))

    assert agenda.ververs_wedstrijden(db_pad=app.config["DATABASE"]) == 0  # niets nieuws, wel bijgewerkt
    rijen = db.execute("SELECT thuis, tijd FROM wedstrijden WHERE datum = '2026-11-13' ORDER BY tijd").fetchall()
    assert [(r["thuis"], r["tijd"]) for r in rijen] == [(1, "19:30"), (1, "20:00"), (1, "20:30")]


def test_een_zelf_toegevoegde_uitwedstrijd_blijft_staan(app, db, monkeypatch):
    db.execute("""INSERT INTO wedstrijden (team, datum, omschrijving, thuis, handmatig)
                  VALUES (?, '2026-11-13', 'HSC 18+1-Blauw Geel''15 18+1', 0, 1)""", (TEAM,))
    db.execute("INSERT INTO agenda_feeds (url, team) VALUES ('https://sportlink.test/ical-team', ?)", (TEAM,))
    db.commit()
    feed = _ics(("2000", "Harkstede 18+1-Blauw Geel'15 18+1", ELDERS), ("2030", "HSC 18+1-Blauw Geel'15 18+1", THUIS))
    monkeypatch.setattr(agenda, "haal_feed_op", lambda url: (TEAM, agenda._parse_ics(feed)))
    agenda.ververs_wedstrijden(db_pad=app.config["DATABASE"])
    # De echte thuiswedstrijd van die dag vervangt de handmatige plaatshouder (zie _vervang_handmatige_wedstrijden).
    rijen = db.execute("SELECT omschrijving, thuis, handmatig FROM wedstrijden WHERE datum = '2026-11-13' ORDER BY omschrijving").fetchall()
    assert [tuple(r) for r in rijen] == [("HSC 18+1-Blauw Geel'15 18+1", 1, 0), ("Harkstede 18+1-Blauw Geel'15 18+1", 0, 0)]


# ---------- De dia Komende thuiswedstrijden ----------


def _thuis(db, dag, tijd, omschrijving, team=TEAM):
    db.execute("INSERT INTO wedstrijden (team, datum, tijd, omschrijving, thuis) VALUES (?, ?, ?, ?, 1)",
               (team, dag.isoformat(), tijd, omschrijving))


def test_de_tv_dia_toont_de_tijden_op_volgorde(client, db):
    from datetime import timedelta
    from helpers import vandaag_amsterdam

    dag = vandaag_amsterdam() + timedelta(days=2)
    for tijd, omschrijving in [("20:30", "HSC 18+1-Blauw Geel'15 18+1"), ("19:30", "Blauw Geel'15 18+1-FVV 18+2"),
                               ("20:00", "Harkstede 18+1-Blauw Geel'15 18+1")]:
        _thuis(db, dag, tijd, omschrijving)
    db.execute("UPDATE kiosk_scherm_instellingen SET toon_wedstrijden = 1")
    db.commit()
    tekst = client.get("/kiosk/scherm").data.decode()
    posities = [tekst.index(f'<span class="wedstrijd-tijd">{tijd}</span>') for tijd in ("19:30", "20:00", "20:30")]
    assert posities == sorted(posities)


def test_hooguit_vier_dagen_en_compact_bij_veel_wedstrijden(client, db):
    from datetime import timedelta
    from helpers import vandaag_amsterdam

    eerste = vandaag_amsterdam() + timedelta(days=1)
    for d in range(6):
        for n in range(2):
            _thuis(db, eerste + timedelta(days=d), f"1{n}:00", f"Blauw Geel'15 {d}{n}-Tegenstander {n}")
    db.execute("UPDATE kiosk_scherm_instellingen SET toon_wedstrijden = 1")
    db.commit()
    tekst = client.get("/kiosk/scherm").data.decode()
    assert tekst.count('class="wedstrijd-dag') == 4 and "wedstrijden-lijst--vol" in tekst
