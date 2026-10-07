"""Importeren van de Club van 20-spreadsheet met een keuze per lid: in het voorbeeld vink je aan
welke leden meegaan; wat je niet aanvinkt blijft precies zoals het in de app staat."""

import re

from conftest import stel_csrf_token_in as _csrf
from test_club_van_20 import _bijdrage, _lid

from club_van_20 import import_rij_overzicht, parse_import

KOP = "Voornaam,Achternaam,Team,Naambordje,2025-2026,2026-2027,Status 2026-2027"
CSV = "\n".join(
    [
        KOP,
        "Nieuw,Lid,Za1,Nieuw Lidje,20,,",  # bestaat nog niet
        "Jan,Jansen,,Jantje,20,20,Betaald",  # bestaat, krijgt 2026-27 erbij
        "Piet,Pieters,,Pietje,,,Gevraagd",  # bestaat, app heeft betaald voor 2026-27: conflict
        "Klaas,Bakker,,Klaasje,20,,",  # bestaat, verder niets nieuws
    ]
)


def _stel_in(db):
    jantje = _lid(db, "Jantje")
    _bijdrage(db, jantje, "2025-2026")
    pietje = _lid(db, "Pietje")
    _bijdrage(db, pietje, "2026-2027")  # in de app al betaald (bijv. via de website)
    klaasje = _lid(db, "Klaasje")
    _bijdrage(db, klaasje, "2025-2026")
    # Namen staan al in de app, zodat er niets aangevuld hoeft te worden.
    for lid, voornaam, achternaam in ((jantje, "Jan", "Jansen"), (pietje, "Piet", "Pieters"), (klaasje, "Klaas", "Bakker")):
        db.execute(
            "UPDATE club_van_20_leden SET voornaam = ?, achternaam = ? WHERE id = ?", (voornaam, achternaam, lid)
        )
    db.commit()
    return jantje, pietje, klaasje


def _soorten(db):
    return [o["soort"] for o in import_rij_overzicht(db, parse_import(CSV)["rijen"])]


def test_overzicht_per_lid_nieuw_wijziging_conflict_of_niets(db):
    _stel_in(db)
    overzicht = import_rij_overzicht(db, parse_import(CSV)["rijen"])
    assert [o["soort"] for o in overzicht] == ["nieuw", "wijziging", "conflict", "niets"]
    assert overzicht[0]["regels"] == ["2025-2026: betaald €20"]
    assert overzicht[1]["regels"] == ["2026-2027: betaald €20"]
    assert overzicht[2]["regels"] == ["2026-2027: betaald €20 → gevraagd"]
    assert overzicht[3]["regels"] == []


def test_overzicht_vult_lege_velden_aan_en_meldt_dat(db):
    lid = _lid(db, "Jantje")  # zonder voornaam, achternaam en team
    _bijdrage(db, lid, "2025-2026")
    rij = parse_import(f"{KOP}\nJan,Jansen,Za1,Jantje,20,,")["rijen"]
    overzicht = import_rij_overzicht(db, rij)[0]
    assert overzicht["soort"] == "wijziging" and overzicht["regels"] == ["vult aan: voornaam, achternaam, team"]


def test_hogere_betaling_van_hetzelfde_lid_is_een_wijziging_en_geen_conflict_bij_aanvullen_van_status(db):
    lid = _lid(db, "Jantje")
    _bijdrage(db, lid, "2026-2027", status="gevraagd", bedrag=0)
    rij = parse_import(f"{KOP}\nJan,Jansen,,Jantje,,20,Betaald")["rijen"]
    assert import_rij_overzicht(db, rij)[0]["soort"] == "wijziging"  # gevraagd wordt betaald: gewoon voortgang
    db.execute("UPDATE club_van_20_bijdragen SET status = 'betaald', bedrag = 20 WHERE lid_id = ?", (lid,))
    db.commit()
    rij = parse_import(f"{KOP}\nJan,Jansen,,Jantje,,15,Betaald")["rijen"]
    assert import_rij_overzicht(db, rij)[0]["soort"] == "conflict"  # ander bedrag dan wat de app heeft


def test_voorbeeld_toont_vinkjes_en_zet_conflict_standaard_uit(ingelogde_client, db):
    _stel_in(db)
    tekst = ingelogde_client.post(
        "/club-van-20/importeren", data={"csrf_token": _csrf(ingelogde_client), "tekst": CSV}
    ).data.decode()

    vakjes = re.findall(r'<input type="checkbox" form="import-bevestig" name="kies" value="(\d+)"[^>]*?(checked)?>', tekst, re.S)
    assert [(v, bool(c)) for v, c in vakjes] == [("0", True), ("1", True), ("2", False), ("3", False)]
    assert "Wat verandert" in tekst and "2026-2027: betaald €20 → gevraagd" in tekst
    assert 'name="kies_aanwezig" value="1"' in tekst and "let op" in tekst


def _bevestig(client, **extra):
    return client.post(
        "/club-van-20/importeren", data={"csrf_token": _csrf(client), "tekst": CSV, "bevestig": "1", **extra}
    )


def _naam_bestaat(db, naam):
    return db.execute("SELECT 1 FROM club_van_20_leden WHERE naam = ?", (naam,)).fetchone() is not None


def _bedragen(db, naam):
    return {
        r["seizoen"]: (r["status"], r["bedrag"])
        for r in db.execute(
            """SELECT b.* FROM club_van_20_bijdragen b JOIN club_van_20_leden l ON l.id = b.lid_id
               WHERE l.naam = ?""",
            (naam,),
        )
    }


def test_alleen_aangevinkte_leden_worden_geimporteerd(ingelogde_client, db):
    _stel_in(db)
    resp = _bevestig(ingelogde_client, kies_aanwezig="1", kies=["1"])  # alleen Jantje

    assert resp.status_code == 302
    assert not _naam_bestaat(db, "Nieuw Lidje")  # niet aangevinkt: niet aangemaakt
    assert _bedragen(db, "Jantje")["2026-2027"] == ("betaald", 20)  # wel bijgewerkt
    assert _bedragen(db, "Pietje")["2026-2027"][0] == "betaald"  # niet aangevinkt: onaangetast


def test_een_conflict_gaat_alleen_mee_als_je_het_zelf_aanvinkt(ingelogde_client, db):
    _stel_in(db)
    _bevestig(ingelogde_client, kies_aanwezig="1", kies=["0", "1", "3"])
    assert _bedragen(db, "Pietje")["2026-2027"][0] == "betaald"  # het conflict is gewoon overgeslagen
    assert _naam_bestaat(db, "Nieuw Lidje")

    _bevestig(ingelogde_client, kies_aanwezig="1", kies=["2"])
    assert _bedragen(db, "Pietje")["2026-2027"][0] == "gevraagd"  # bewust aangevinkt


def test_zonder_aangevinkte_leden_gebeurt_er_niets(ingelogde_client, db):
    _stel_in(db)
    aantal = db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"]
    resp = _bevestig(ingelogde_client, kies_aanwezig="1")
    assert resp.status_code == 200  # blijft op het voorbeeld, met een melding
    assert "geen leden aangevinkt" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == aantal


def test_oud_formulier_zonder_keuze_importeert_alles_zoals_voorheen(ingelogde_client, db):
    _stel_in(db)
    resp = _bevestig(ingelogde_client)
    assert resp.status_code == 302
    assert _naam_bestaat(db, "Nieuw Lidje") and _bedragen(db, "Pietje")["2026-2027"][0] == "gevraagd"


def test_onbekende_of_ongeldige_keuzes_worden_genegeerd_en_leden_buiten_het_bestand_blijven(ingelogde_client, db):
    handmatig = _lid(db, "Handmatig Toegevoegd")
    _bijdrage(db, handmatig, "2026-2027")
    _stel_in(db)
    _bevestig(ingelogde_client, kies_aanwezig="1", kies=["0", "99", "abc", "-1"])
    assert _naam_bestaat(db, "Nieuw Lidje")
    assert _naam_bestaat(db, "Handmatig Toegevoegd")
    assert _bedragen(db, "Handmatig Toegevoegd") == {"2026-2027": ("betaald", 20)}


def test_melding_noemt_hoeveel_leden_zijn_overgeslagen(ingelogde_client, db):
    _stel_in(db)
    resp = _bevestig(ingelogde_client, kies_aanwezig="1", kies=["0", "1"])
    tekst = ingelogde_client.get(resp.headers["Location"]).data.decode()
    assert "Import klaar: 1 nieuwe leden, 1 bijgewerkt, 2 leden uit het bestand overgeslagen." in tekst
