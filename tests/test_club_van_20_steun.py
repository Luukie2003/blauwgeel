"""De "Leden? Steun de club!"-dia: wie dit seizoen nog niet betaald heeft maar eerder wel."""

from conftest import stel_csrf_token_in as _csrf
from test_club_van_20 import HUIDIG, TWEE_TERUG, VORIG, _alleen_club_van_20, _bijdrage, _lid, _zet

from club_van_20 import bouw_slides, onbetaalde_leden, verschuif_seizoen


def _instellingen(db):
    return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()


def _steun(db, qr_svg=None):
    return [s for s in bouw_slides(db, _instellingen(db), qr_svg=qr_svg) if s["type"] == "club_van_20_onbetaald"]


def _leden(db):
    _bijdrage(db, _lid(db, "Betaalt Nu"), HUIDIG)
    _bijdrage(db, _lid(db, "Vorig Seizoen"), VORIG)
    _bijdrage(db, _lid(db, "Twee Terug"), TWEE_TERUG)
    _bijdrage(db, _lid(db, "Lang Weg"), verschuif_seizoen(HUIDIG, -4))
    _lid(db, "Nooit Betaald")
    _bijdrage(db, _lid(db, "Gestopt", status="inactief"), VORIG)
    zegt_af = _lid(db, "Zegt Af")
    _bijdrage(db, zegt_af, VORIG)
    _bijdrage(db, zegt_af, HUIDIG, status="afgezegd")


def test_alleen_wie_eerder_wel_en_nu_niet_betaald_heeft_staat_erop(db):
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=3)

    dias = _steun(db)

    namen = [n["naam"] for d in dias for n in d["namen"]]
    assert namen == ["Twee Terug", "Vorig Seizoen"]  # op alfabet
    # Wie al betaald heeft, nooit betaald heeft, te lang geleden stopte, gearchiveerd of afgezegd is: niet.
    assert dias[0]["totaal"] == 2 and dias[0]["pagina"] is None


def test_het_bereik_van_het_scherm_bepaalt_wie_er_nog_meetelt(db):
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=2)  # dit seizoen en het vorige
    assert [n["naam"] for d in _steun(db) for n in d["namen"]] == ["Vorig Seizoen"]


def test_twaalf_per_dia_en_gelijk_verdeeld(db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Betaalt Nu"), HUIDIG)
    for i in range(13):
        _bijdrage(db, _lid(db, f"Lid {i:02d}"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2)

    dias = _steun(db)

    assert [len(d["namen"]) for d in dias] == [7, 6]  # niet 12 + 1
    assert [d["pagina"] for d in dias] == ["1/2", "2/2"]
    assert all(d["totaal"] == 13 for d in dias)

    _zet(db, club_van_20_onbetaald_per_slide=24)
    assert [len(d["namen"]) for d in _steun(db)] == [13]
    _zet(db, club_van_20_onbetaald_per_slide=12)
    assert len(_steun(db)) == 2


def test_precies_twaalf_is_een_dia(db):
    _alleen_club_van_20(db)
    for i in range(12):
        _bijdrage(db, _lid(db, f"Lid {i:02d}"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2)
    assert [len(d["namen"]) for d in _steun(db)] == [12]


def test_zonder_ontbrekende_leden_geen_dia(db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Betaalt Nu"), HUIDIG)
    assert _steun(db) == []


def test_de_dia_kan_uit(db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Vorig Seizoen"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2, club_van_20_toon_onbetaald=0)
    assert _steun(db) == []


def test_de_dia_staat_voor_de_werving_en_krijgt_de_qr_code(db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Vorig Seizoen"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2, club_van_20_toon_werving=1)

    types = [s["type"] for s in bouw_slides(db, _instellingen(db), qr_svg="<svg></svg>")]

    assert types.index("club_van_20_onbetaald") < types.index("club_van_20_werving")
    assert _steun(db, qr_svg="<svg>qr</svg>")[0]["qr_svg"] == "<svg>qr</svg>"


def test_onbetaalde_leden_zonder_betaalde_seizoenen_worden_overgeslagen():
    leden = [
        {"naam": "B", "betaald": False, "seizoenen": 1, "lang": False},
        {"naam": "a", "betaald": False, "seizoenen": 3, "lang": False},
        {"naam": "C", "betaald": True, "seizoenen": 5, "lang": False},
        {"naam": "D", "betaald": False, "seizoenen": 0, "lang": False},
    ]
    assert [lid["naam"] for lid in onbetaalde_leden(leden)] == ["a", "B"]


# ---------- Het scherm zelf ----------


def test_het_scherm_toont_de_dramatische_dia_met_alle_namen(client, db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Betaalt Nu"), HUIDIG)
    _bijdrage(db, _lid(db, "Vorig Seizoen"), VORIG)
    _bijdrage(db, _lid(db, "Een Heel Lange Naam Van Iemand"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2)

    tekst = client.get("/kiosk/scherm").data.decode()

    assert "Leden? Steun de club!" in tekst
    assert "2 leden hebben dit seizoen" in tekst
    assert "slide-club_van_20_onbetaald" in tekst
    deel = tekst.split("slide-club_van_20_onbetaald")[1]
    assert "Vorig Seizoen" in deel and "Een Heel Lange Naam Van Iemand" in deel
    assert "c20-bordje--lang" in deel  # lange namen krijgen hun eigen opmaak
    assert "Scan &amp; doe weer mee" in deel  # QR-code naar de publieke pagina


def test_een_enkel_lid_krijgt_een_correcte_zin(client, db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Vorig Seizoen"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2)
    assert "1 lid heeft dit seizoen" in client.get("/kiosk/scherm").data.decode()


def test_instelling_opslaan_en_tonen(ingelogde_client, db):
    _alleen_club_van_20(db)
    pagina = ingelogde_client.get("/club-van-20/instellingen").data.decode()
    assert "Leden? Steun de club!" in pagina and 'name="club_van_20_onbetaald_per_slide"' in pagina

    ingelogde_client.post(
        "/club-van-20/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "club_van_20_titel": "Club van 20", "club_van_20_onbetaald_per_slide": "16"},
    )
    rij = _instellingen(db)
    assert rij["club_van_20_onbetaald_per_slide"] == 16
    assert rij["club_van_20_toon_onbetaald"] == 0  # vinkje niet meegestuurd = uit

    ingelogde_client.post(
        "/club-van-20/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "club_van_20_toon_onbetaald": "1", "club_van_20_onbetaald_per_slide": "999"},
    )
    rij = _instellingen(db)
    assert rij["club_van_20_toon_onbetaald"] == 1 and rij["club_van_20_onbetaald_per_slide"] == 24  # begrensd


def test_standaard_staat_de_dia_aan_met_twaalf_per_dia(db):
    rij = _instellingen(db)
    assert rij["club_van_20_toon_onbetaald"] == 1 and rij["club_van_20_onbetaald_per_slide"] == 12
