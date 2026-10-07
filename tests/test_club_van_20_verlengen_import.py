"""Een Excel van de penningmeester met 'Status 2026-2027 = Betaald': de import ziet wie dit
seizoen verlengd heeft, ook als de bedragkolom een expliciete 0 heeft (het geld stond al in
een eerder seizoen), en het voorbeeld zet dat bovenaan op een rij."""

import re

from conftest import stel_csrf_token_in as _csrf
from test_club_van_20 import _bijdrage, _lid

from club_van_20 import import_rij_overzicht, parse_import, verlengingen_overzicht

KOP = "Voornaam,Achternaam,Team,Naambordje,2025-2026,2026-2027,Status 2026-2027"
CSV = "\n".join(
    [
        KOP,
        "Jan,Jansen,,Jantje,,20,Betaald",  # echt bedrag, nog niet in de app
        "Piet,Pieters,,Pietje,20,0,Betaald",  # vooruitbetaald: verlengd met 0 in de bedragkolom
        "Klaas,Bakker,,Klaasje,,20,Betaald",  # staat in de app al op betaald
        "Marie,Mulder,,Marietje,20,,Niet gevraagd",  # niet verlengd
        "Nieuw,Lid,,Nieuw Lidje,,20,Betaald",  # nog geen lid
    ]
)


def _stel_in(db):
    for naam in ("Jantje", "Pietje", "Klaasje", "Marietje"):
        lid = _lid(db, naam)
        _bijdrage(db, lid, "2025-2026")
        if naam == "Klaasje":
            _bijdrage(db, lid, "2026-2027")
    db.commit()


def _bedragen(db, naam):
    return {
        r["seizoen"]: (r["status"], r["bedrag"])
        for r in db.execute(
            """SELECT b.* FROM club_van_20_bijdragen b JOIN club_van_20_leden l ON l.id = b.lid_id
               WHERE l.naam = ?""",
            (naam,),
        )
    }


def test_betaald_met_expliciete_nul_telt_als_verlengd_met_bedrag_nul():
    rijen = {r["naam"]: r for r in parse_import(CSV)["rijen"]}
    assert rijen["Pietje"]["bijdragen"]["2026-2027"] == {"status": "betaald", "bedrag": 0, "nul_betaald": True}
    assert rijen["Jantje"]["bijdragen"]["2026-2027"] == {"status": "betaald", "bedrag": 20}


def test_een_nul_zonder_status_betaald_blijft_geen_betaling():
    rijen = parse_import(f"{KOP}\nJan,Jansen,,Jantje,,0,Niet gevraagd")["rijen"]
    assert "2026-2027" not in rijen[0]["bijdragen"]


def test_verlengingen_overzicht_verdeelt_de_betaalde_leden(db):
    _stel_in(db)
    rijen = parse_import(CSV)["rijen"]
    v = verlengingen_overzicht(db, rijen, "2026-2027")
    assert v["totaal"] == 4
    assert v["wordt_betaald"] == ["Jantje", "Pietje"]
    assert v["al_betaald"] == ["Klaasje"]
    assert v["nieuw"] == ["Nieuw Lidje"]
    assert v["rijen"] == [0, 1, 4]  # alleen wie nog verlengd moet worden


def test_voorbeeld_toont_de_samenvatting_en_de_knop(ingelogde_client, db):
    _stel_in(db)
    tekst = ingelogde_client.post(
        "/club-van-20/importeren", data={"csrf_token": _csrf(ingelogde_client), "tekst": CSV}
    ).data.decode()
    assert "Verlengd voor 2026-2027 volgens dit bestand: 4 leden" in tekst
    assert "Alleen de 3 leden aanvinken die nog verlengd moeten worden" in tekst
    assert "betaald (€0 in het bestand)" in tekst
    rijen = re.findall(r'data-verlengd="(\d)"', tekst)
    assert rijen == ["1", "1", "0", "0", "1"]


def test_import_zet_verlengers_op_betaald_en_laat_de_rest_staan(ingelogde_client, db):
    _stel_in(db)
    resp = ingelogde_client.post(
        "/club-van-20/importeren",
        data={"csrf_token": _csrf(ingelogde_client), "tekst": CSV, "bevestig": "1", "kies_aanwezig": "1",
              "kies": ["0", "1", "4"]},
    )
    assert resp.status_code == 302
    assert _bedragen(db, "Jantje")["2026-2027"] == ("betaald", 20)
    assert _bedragen(db, "Pietje")["2026-2027"] == ("betaald", 0)  # verlengd, geen dubbel geld in de totalen
    assert _bedragen(db, "Nieuw Lidje")["2026-2027"] == ("betaald", 20)
    assert "2026-2027" not in _bedragen(db, "Marietje")  # niet verlengd: onaangetast


def test_een_lid_dat_in_de_app_al_betaald_heeft_wordt_niet_op_nul_gezet(db):
    lid = _lid(db, "Pietje")
    _bijdrage(db, lid, "2026-2027")  # in de app betaald €20
    rij = parse_import(f"{KOP}\nPiet,Pieters,,Pietje,20,0,Betaald")["rijen"]
    overzicht = import_rij_overzicht(db, rij)[0]
    assert overzicht["soort"] == "wijziging"  # alleen 2025-2026 en de namen komen erbij
    assert not any("2026-2027" in regel for regel in overzicht["regels"])  # de betaling van dit seizoen blijft
    assert verlengingen_overzicht(db, rij, "2026-2027")["al_betaald"] == ["Pietje"]
