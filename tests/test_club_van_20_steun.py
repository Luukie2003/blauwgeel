"""De "Leden? Steun de club!"-dia: wie dit seizoen nog niet betaald heeft maar eerder wel."""

from conftest import stel_csrf_token_in as _csrf
from test_club_van_20 import HUIDIG, TWEE_TERUG, VORIG, _alleen_club_van_20, _bijdrage, _lid, _zet

from club_van_20 import bouw_slides, onbetaalde_leden, verschuif_seizoen
from club_van_20 import kleine_teksten
from club_van_20.scherm import onbetaald_raster


def _instellingen(db):
    return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()


STANDAARD_KLEINE_TEKSTEN = [
    "Wel drinken bestellen maar niet die 20 euro betalen?",
    "Elke week de kantine tot de laatste cent leeg kopen, maar de club van 20 is te veel?",
    "Scan de QR of regel de betaling bij de bar",
]


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


def _steun_namen(db):
    return [n["naam"] for d in _steun(db) for n in d["namen"]]


def test_de_eigen_instelling_bepaalt_wie_er_nog_meetelt(db):
    _alleen_club_van_20(db)
    _leden(db)

    _zet(db, club_van_20_steun_seizoenen=2)  # dit seizoen en het vorige
    assert _steun_namen(db) == ["Vorig Seizoen"]
    _zet(db, club_van_20_steun_seizoenen=3)
    assert _steun_namen(db) == ["Twee Terug", "Vorig Seizoen"]
    _zet(db, club_van_20_steun_seizoenen=0)  # ooit betaald
    assert _steun_namen(db) == ["Lang Weg", "Twee Terug", "Vorig Seizoen"]


def test_standaard_gaan_de_laatste_drie_seizoenen_mee(db):
    assert _instellingen(db)["club_van_20_steun_seizoenen"] == 3


def test_de_dia_staat_los_van_wie_er_op_de_naammuur_staat(client, db):
    """Was: de muur op "alleen wie dit seizoen betaald heeft" zetten haalde ook de Steun-de-club-dia weg."""
    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_zichtbaar_seizoenen=1, club_van_20_markeer_onbetaald=0)

    assert _steun_namen(db) == ["Twee Terug", "Vorig Seizoen"]
    tekst = client.get("/kiosk/scherm").data.decode()
    muur = tekst.split("slide-club_van_20_onbetaald")[0]
    steun = tekst.split("slide-club_van_20_onbetaald")[1]
    assert "Betaalt Nu" in muur and "Vorig Seizoen" not in muur and "Twee Terug" not in muur  # de muur: alleen betaald
    assert "Vorig Seizoen" in steun and "Twee Terug" in steun  # de onbetaalden: alleen op de dia


def test_de_tijdelijke_herinnering_verruimt_ook_de_dia(db):
    from datetime import timedelta

    from helpers import vandaag_amsterdam

    _alleen_club_van_20(db)
    _leden(db)
    _zet(db, club_van_20_steun_seizoenen=2)
    assert _steun_namen(db) == ["Vorig Seizoen"]

    tot = (vandaag_amsterdam() + timedelta(days=7)).isoformat()
    _zet(db, club_van_20_onbetaald_tot=tot, club_van_20_onbetaald_seizoenen=0)  # herinnering: iedereen die ooit betaalde
    assert _steun_namen(db) == ["Lang Weg", "Twee Terug", "Vorig Seizoen"]


def test_twaalf_per_dia_en_gelijk_verdeeld(db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Betaalt Nu"), HUIDIG)
    for i in range(13):
        _bijdrage(db, _lid(db, f"Lid {i:02d}"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2, club_van_20_onbetaald_per_slide=12)

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
    _zet(db, club_van_20_zichtbaar_seizoenen=2, club_van_20_onbetaald_per_slide=12)
    assert [len(d["namen"]) for d in _steun(db)] == [12]


def test_standaard_gaan_er_vierentwintig_op_een_dia_en_51_leden_worden_3_dias(db):
    _alleen_club_van_20(db)
    for i in range(51):
        _bijdrage(db, _lid(db, f"Lid {i:02d}"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2)

    dias = _steun(db)

    assert [len(d["namen"]) for d in dias] == [17, 17, 17]  # gelijk verdeeld, niet 24 + 24 + 3
    _bijdrage(db, _lid(db, "Een erbij"), VORIG)
    assert [len(d["namen"]) for d in _steun(db)] == [18, 18, 16]  # 52 leden: nog steeds 3 dia's


def test_een_dia_met_veel_namen_wordt_compacter_maar_houdt_vier_kolommen():
    ruim = onbetaald_raster(12)
    assert ruim["kolommen"] == 4 and ruim["rij"] is None and ruim["schaal"] == 1  # zoals altijd: grote kop en letter
    for aantal in range(1, 13):
        assert onbetaald_raster(aantal) == ruim

    vorige_letter = ruim["letter"]
    for aantal in range(13, 25):
        raster = onbetaald_raster(aantal)
        # Smaller dan 4 kolommen: namen als "Aaltje Hofstra" worden afgekapt.
        assert raster["kolommen"] == 4 and raster["schaal"] < 1
        assert raster["letter"] <= vorige_letter  # meer rijen: nooit grotere letters
        vorige_letter = raster["letter"]
        # De rijen (met vaste hoogte) moeten onder de kop en boven de QR-code/kleine teksten passen: ruim 540 --u.
        rijen = -(-aantal // 4)
        assert rijen * raster["rij"] + (rijen - 1) * 20 * raster["schaal"] <= 540


def test_de_kleine_tekst_onder_de_dia(db):
    _alleen_club_van_20(db)
    _bijdrage(db, _lid(db, "Vorig Seizoen"), VORIG)
    _zet(db, club_van_20_zichtbaar_seizoenen=2)

    assert _steun(db)[0]["kleintjes"] == STANDAARD_KLEINE_TEKSTEN

    _zet(db, club_van_20_onbetaald_tekst="  Even afrekenen?  ")
    assert _steun(db)[0]["kleintjes"] == ["Even afrekenen?"]
    _zet(db, club_van_20_onbetaald_tekst="")
    assert _steun(db)[0]["kleintjes"] == []


def test_kleine_teksten_zijn_regels_met_een_maximum():
    assert kleine_teksten(None) == [] and kleine_teksten("") == [] and kleine_teksten("  \n \n") == []
    assert kleine_teksten(" een \n\n twee\r\ndrie ") == ["een", "twee", "drie"]  # lege regels vallen weg, ook \r\n
    assert kleine_teksten("1\n2\n3\n4\n5") == ["1", "2", "3"]  # meer past er niet onder de namen
    assert kleine_teksten("x" * 500) == ["x" * 140]


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
    for regel in STANDAARD_KLEINE_TEKSTEN:  # de kleine teksten eronder, elk op een eigen regel
        assert f"<p>{regel}</p>" in deel


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


def test_het_bereik_van_de_dia_opslaan_en_begrenzen(ingelogde_client, db):
    _alleen_club_van_20(db)
    pagina = ingelogde_client.get("/club-van-20/instellingen").data.decode()
    assert 'name="club_van_20_steun_seizoenen"' in pagina and "Wie staat er op die dia?" in pagina

    def bewaar(waarde):
        ingelogde_client.post(
            "/club-van-20/instellingen",
            data={"csrf_token": _csrf(ingelogde_client), "club_van_20_steun_seizoenen": waarde},
        )
        return _instellingen(db)["club_van_20_steun_seizoenen"]

    assert bewaar("4") == 4
    assert bewaar("0") == 0
    assert bewaar("999") == 20
    assert bewaar("-5") == 0


def test_de_kleine_tekst_opslaan_leeg_laten_en_begrenzen(ingelogde_client, db):
    _alleen_club_van_20(db)

    def bewaar(tekst):
        ingelogde_client.post(
            "/club-van-20/instellingen",
            data={"csrf_token": _csrf(ingelogde_client), "club_van_20_onbetaald_tekst": tekst},
        )
        return _instellingen(db)["club_van_20_onbetaald_tekst"]

    assert bewaar("  Ook jij?  ") == "Ook jij?"
    assert bewaar("Eerste\r\n\r\nTweede\nDerde\nVierde") == "Eerste\nTweede\nDerde"  # lege regels weg, max. 3
    assert bewaar("") == ""  # leeg = geen tekst onder de dia
    assert bewaar("x" * 500) == "x" * 140
    pagina = ingelogde_client.get("/club-van-20/instellingen").data.decode()
    assert 'name="club_van_20_onbetaald_tekst"' in pagina


def test_standaard_staat_de_dia_aan_met_vierentwintig_per_dia(db):
    rij = _instellingen(db)
    assert rij["club_van_20_toon_onbetaald"] == 1 and rij["club_van_20_onbetaald_per_slide"] == 24
    assert rij["club_van_20_onbetaald_tekst"].split("\n") == STANDAARD_KLEINE_TEKSTEN
