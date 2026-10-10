"""De dia "Welkom nieuwe leden": hoe minder namen, hoe groter alles."""

from test_club_van_20 import HUIDIG, _alleen_club_van_20, _bijdrage, _lid, _zet

from club_van_20 import bouw_slides
from club_van_20.scherm import nieuw_maat
from helpers import vandaag_amsterdam


def _nieuwe_leden(db, namen):
    for naam in namen:
        _bijdrage(db, _lid(db, naam), HUIDIG, betaald_op=vandaag_amsterdam().isoformat())


def _dia(db):
    instellingen = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    return [s for s in bouw_slides(db, instellingen) if s["type"] == "club_van_20_nieuw"]


def test_hoe_minder_namen_hoe_groter():
    maten = [nieuw_maat(aantal) for aantal in range(1, 13)]
    for kleiner, groter in zip(maten[1:], maten):
        assert kleiner["letter"] <= groter["letter"] and kleiner["kop"] <= groter["kop"]
    assert maten[0]["letter"] >= 150  # 1 nieuw lid vult bijna het scherm
    assert maten[-1]["letter"] <= 60  # 12 namen (het maximum, ook met lange namen op 2 regels) passen nog
    assert nieuw_maat(30) == nieuw_maat(12)  # boven het maximum blijft de kleinste maat


def test_de_dia_krijgt_de_maat_van_het_aantal_namen(db):
    _alleen_club_van_20(db)
    _nieuwe_leden(db, ["Een"])
    [een] = _dia(db)
    assert een["maat"] == nieuw_maat(1)

    _nieuwe_leden(db, [f"Lid {i}" for i in range(14)])
    [veel] = _dia(db)
    assert len(veel["namen"]) == 12 and veel["maat"] == nieuw_maat(12)  # nooit meer dan 12 op een dia


def test_het_scherm_zet_de_maat_en_geeft_lange_namen_twee_regels(client, db):
    _alleen_club_van_20(db)
    _zet(db, club_van_20_toon_onbetaald=0)
    _nieuwe_leden(db, ["Jan de Vries", "Installatiebedrijf Wolters"])

    tekst = client.get("/kiosk/scherm").data.decode()

    deel = tekst.split("slide-club_van_20_nieuw")[1].split("slide-club_van_20_")[0]
    maat = nieuw_maat(2)
    assert f"--nieuw-letter: {maat['letter']}" in deel and f"--nieuw-kop: {maat['kop']}" in deel
    assert deel.count("c20-bordje--goud") == 2
    assert deel.count("c20-bordje--lang") == 1  # alleen "Installatiebedrijf Wolters": groter dan 16 tekens
