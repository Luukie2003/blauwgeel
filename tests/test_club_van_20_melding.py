"""De melding op alle schermen bij een nieuw lid of een verlenging van de Club van 20 (met een wachtrij)."""

from conftest import stel_csrf_token_in as _csrf
from test_club_van_20 import HUIDIG, VORIG, _alleen_club_van_20, _bijdrage, _lid, _zet

from club_van_20 import parse_import, sla_bijdrage_op, voer_import_uit, welkom_wachtrij
from club_van_20.administratie import MELDING_BEWAARTIJD, MELDING_DUBBEL_SECONDEN, registreer_melding
from club_van_20.scherm import WELKOM_MAX_LEEFTIJD, WELKOM_MAX_WACHTRIJ

NU = 1_800_000_000


def _meldingen(db):
    return [dict(r) for r in db.execute("SELECT * FROM club_van_20_meldingen ORDER BY id").fetchall()]


def _instellingen(db):
    return db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()


def _wachtrij(db, na=0, nu=None):
    return welkom_wachtrij(db, _instellingen(db), na, nu)


def _melding(db, naam="Lid", soort="nieuw", seizoenen=1, nu=NU):
    db.execute(
        """INSERT INTO club_van_20_meldingen (lid_id, naam, soort, seizoen, seizoenen, aangemaakt_op)
           VALUES (NULL, ?, ?, ?, ?, ?)""",
        (naam, soort, HUIDIG, seizoenen, nu),
    )
    db.commit()


# ---------- Wanneer is er een melding? ----------


def test_een_eerste_betaling_is_een_nieuw_lid(db):
    lid_id = _lid(db, "Nieuw Lid")

    sla_bijdrage_op(db, lid_id, HUIDIG, "betaald")

    [melding] = _meldingen(db)
    assert (melding["lid_id"], melding["naam"], melding["soort"], melding["seizoen"], melding["seizoenen"]) == (
        lid_id, "Nieuw Lid", "nieuw", HUIDIG, 1,
    )


def test_een_lid_dat_eerder_betaalde_verlengt(db):
    lid_id = _lid(db, "Trouw Lid")
    _bijdrage(db, lid_id, VORIG)

    sla_bijdrage_op(db, lid_id, HUIDIG, "betaald")

    [melding] = _meldingen(db)
    assert (melding["soort"], melding["seizoenen"]) == ("verlengd", 2)


def test_seizoenen_van_voor_de_administratie_tellen_mee(db):
    lid_id = _lid(db, "Oudgediende", eerdere_seizoenen=5)  # 5 seizoenen van vóór de administratie

    sla_bijdrage_op(db, lid_id, HUIDIG, "betaald")

    [melding] = _meldingen(db)
    assert (melding["soort"], melding["seizoenen"]) == ("verlengd", 6)


def test_geen_melding_zolang_het_geen_betaling_is(db):
    lid_id = _lid(db, "Nog Niet")
    for status in ("gevraagd", "toegezegd", "afgezegd", "niet_gevraagd"):
        sla_bijdrage_op(db, lid_id, HUIDIG, status)
    assert _meldingen(db) == []


def test_geen_melding_voor_een_ander_seizoen_of_een_bestaande_betaling(db):
    lid_id = _lid(db, "Oud Nieuws")
    sla_bijdrage_op(db, lid_id, VORIG, "betaald")  # een correctie van vorig seizoen
    assert _meldingen(db) == []

    sla_bijdrage_op(db, lid_id, HUIDIG, "betaald")
    assert len(_meldingen(db)) == 1
    sla_bijdrage_op(db, lid_id, HUIDIG, "betaald", betaalwijze="bank")  # alleen een gegeven aangepast
    assert len(_meldingen(db)) == 1


def test_per_ongeluk_terugzetten_en_opnieuw_betalen_geeft_geen_tweede_melding(db):
    lid_id = _lid(db, "Klikker")
    sla_bijdrage_op(db, lid_id, HUIDIG, "betaald")
    sla_bijdrage_op(db, lid_id, HUIDIG, "gevraagd")
    sla_bijdrage_op(db, lid_id, HUIDIG, "betaald")
    assert len(_meldingen(db)) == 1

    # Maar ruim een uur later wel weer.
    registreer_melding(db, lid_id, HUIDIG, nu=_meldingen(db)[0]["aangemaakt_op"] + MELDING_DUBBEL_SECONDEN + 1)
    assert len(_meldingen(db)) == 2


def test_oude_meldingen_worden_opgeruimd(db):
    _melding(db, "Oud", nu=NU - MELDING_BEWAARTIJD - 1)
    lid_id = _lid(db, "Nu")

    registreer_melding(db, lid_id, HUIDIG, nu=NU)

    assert [m["naam"] for m in _meldingen(db)] == ["Nu"]


def test_een_import_van_oude_gegevens_geeft_geen_meldingen(db):
    voer_import_uit(db, parse_import(f"Naambordje,{HUIDIG}\nGeimporteerd,20\n")["rijen"])
    assert db.execute("SELECT COUNT(*) FROM club_van_20_leden").fetchone()[0] == 1
    assert _meldingen(db) == []


# ---------- Alle manieren om een lid te laten betalen ----------


def test_bijdrage_opslaan_in_het_overzicht_geeft_een_melding(ingelogde_client, db):
    lid_id = _lid(db, "Via Overzicht")
    ingelogde_client.post(
        f"/club-van-20/leden/{lid_id}/bijdrage",
        data={"csrf_token": _csrf(ingelogde_client), "seizoen": HUIDIG, "status": "betaald"},
    )
    assert [m["naam"] for m in _meldingen(db)] == ["Via Overzicht"]


def test_bulk_betaald_zetten_geeft_een_melding_per_lid(ingelogde_client, db):
    ids = [_lid(db, f"Bulk {i}") for i in range(3)]
    ingelogde_client.post(
        "/club-van-20/bulk",
        data={"csrf_token": _csrf(ingelogde_client), "seizoen": HUIDIG, "status": "betaald", "lid_ids": [str(i) for i in ids]},
    )
    assert sorted(m["naam"] for m in _meldingen(db)) == ["Bulk 0", "Bulk 1", "Bulk 2"]


def test_een_nieuw_lid_toevoegen_dat_al_betaald_heeft_geeft_een_melding(ingelogde_client, db):
    ingelogde_client.post(
        "/club-van-20/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Aan De Bar", "status_seizoen": "betaald"},
    )
    [melding] = _meldingen(db)
    assert (melding["naam"], melding["soort"]) == ("Aan De Bar", "nieuw")

    ingelogde_client.post(
        "/club-van-20/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Nog Niet Betaald", "status_seizoen": "gevraagd"},
    )
    assert len(_meldingen(db)) == 1


def test_een_goedgekeurde_aanmelding_geeft_een_melding(ingelogde_client, db):
    from test_club_van_20_aanmeldingen import _aanmelding

    aanmelding_id = _aanmelding(db)
    ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={"csrf_token": _csrf(ingelogde_client), "betaling_gecontroleerd": "1", "modus": "nieuw", "bordje": "Jan & Co"},
    )
    [melding] = _meldingen(db)
    assert (melding["naam"], melding["soort"]) == ("Jan & Co", "nieuw")


# ---------- De wachtrij van een scherm ----------


def test_een_scherm_dat_voor_het_eerst_kijkt_krijgt_niets_maar_wel_de_stand(db):
    _melding(db, "Een")
    _melding(db, "Twee")
    antwoord = _wachtrij(db, na=None, nu=NU)
    assert antwoord["meldingen"] == [] and antwoord["laatste"] == 2


def test_elk_scherm_krijgt_elke_melding_oudste_eerst(db):
    _melding(db, "Een")
    _melding(db, "Twee")
    _melding(db, "Drie", soort="verlengd", seizoenen=7)

    scherm_a = _wachtrij(db, na=0, nu=NU)
    scherm_b = _wachtrij(db, na=0, nu=NU)  # een tweede scherm leegt de wachtrij van het eerste niet

    assert [m["naam"] for m in scherm_a["meldingen"]] == ["Een", "Twee", "Drie"]
    assert scherm_a == scherm_b
    assert _wachtrij(db, na=1, nu=NU)["meldingen"][0]["naam"] == "Twee"  # alleen wat dit scherm nog niet toonde
    assert _wachtrij(db, na=3, nu=NU)["meldingen"] == []


def test_de_melding_bevat_sterren_en_glans(db):
    _melding(db, "Nieuw", soort="nieuw", seizoenen=1)
    _melding(db, "Een ster", soort="verlengd", seizoenen=3)
    _melding(db, "Twee sterren", soort="verlengd", seizoenen=7)

    nieuw, een, twee = _wachtrij(db, nu=NU)["meldingen"]

    assert (nieuw["sterren"], nieuw["glans"], nieuw["soort"]) == (0, False, "nieuw")
    assert (een["sterren"], een["glans"], een["seizoenen"]) == (1, False, 3)
    assert (twee["sterren"], twee["glans"]) == (2, True)  # vanaf 2 sterren glanst het bordje, zoals op de muur


def test_te_oude_meldingen_komen_niet_meer_in_beeld(db):
    _melding(db, "Te oud", nu=NU - WELKOM_MAX_LEEFTIJD - 1)
    _melding(db, "Vers", nu=NU - 60)
    assert [m["naam"] for m in _wachtrij(db, nu=NU)["meldingen"]] == ["Vers"]


def test_bij_een_stortvloed_alleen_de_nieuwste_tien(db):
    for i in range(WELKOM_MAX_WACHTRIJ + 5):
        _melding(db, f"Lid {i:02d}")

    namen = [m["naam"] for m in _wachtrij(db, nu=NU)["meldingen"]]

    assert len(namen) == WELKOM_MAX_WACHTRIJ
    assert namen == [f"Lid {i:02d}" for i in range(5, WELKOM_MAX_WACHTRIJ + 5)]  # nog steeds oudste eerst


def test_uit_zetten_en_de_duur(db):
    _melding(db, "Een")
    _zet(db, club_van_20_toon_welkom=0)
    assert _wachtrij(db, nu=NU)["meldingen"] == [] and _wachtrij(db, nu=NU)["laatste"] == 1

    _zet(db, club_van_20_toon_welkom=1, club_van_20_welkom_duur=1)
    assert _wachtrij(db, nu=NU)["duur"] == 5  # niet korter dan 5 seconden
    _zet(db, club_van_20_welkom_duur=600)
    assert _wachtrij(db, nu=NU)["duur"] == 60


def test_een_scherm_dat_verder_is_dan_de_server_wordt_gelijkgezet(db):
    _melding(db, "Een")
    antwoord = _wachtrij(db, na=999, nu=NU)  # bijv. na het terugzetten van een back-up
    assert antwoord["meldingen"] == [] and antwoord["laatste"] == 1


# ---------- Het eindpunt en de schermen ----------


def test_het_eindpunt_is_publiek_en_wordt_niet_gecachet(client, db):
    _melding(db, "Publiek", nu=10**10)  # ver in de toekomst: nooit "te oud"

    leeg = client.get("/kiosk/welkom")
    assert leeg.status_code == 200 and leeg.get_json()["meldingen"] == []
    assert leeg.headers["Cache-Control"] == "no-store"

    antwoord = client.get("/kiosk/welkom?na=0").get_json()
    assert [m["naam"] for m in antwoord["meldingen"]] == ["Publiek"]
    assert client.get("/kiosk/welkom?na=abc").get_json()["meldingen"] == []  # onzin telt als "nog niet gekeken"


def test_alle_schermen_hebben_de_melding(client, db):
    for pad in ("/kiosk/scherm", "/kiosk/prijzen", "/kiosk/tv"):
        tekst = client.get(pad).data.decode()
        assert 'id="welkom-melding"' in tekst and "/kiosk/welkom" in tekst, pad
        assert "kiosk_welkom_stijl.css" in tekst, pad
        assert "kioskWelkomBezig" in tekst, pad  # de versiepoll wacht met herladen tot de melding klaar is


def test_alle_schermen_herladen_pas_na_de_melding(client, db):
    """Een nieuw lid verandert de ledenlijst en dus de versie: zonder uitstel zou het scherm herladen en de
    melding wegdrukken. Beide soorten schermen moeten dat uitstel kennen."""
    for pad in ("/kiosk/scherm", "/kiosk/prijzen"):
        tekst = client.get(pad).data.decode()
        assert "window.kioskWelkomBezig && window.kioskWelkomBezig()" in tekst, pad


# ---------- Instellingen en testmelding ----------


def test_standaard_staat_de_melding_aan_met_12_seconden(db):
    rij = _instellingen(db)
    assert rij["club_van_20_toon_welkom"] == 1 and rij["club_van_20_welkom_duur"] == 12


def test_melding_instellingen_opslaan(ingelogde_client, db):
    _alleen_club_van_20(db)
    pagina = ingelogde_client.get("/club-van-20/instellingen").data.decode()
    assert 'name="club_van_20_toon_welkom"' in pagina and 'name="club_van_20_welkom_duur"' in pagina
    assert "Test: nieuw lid" in pagina and "Test: verlenging" in pagina

    def bewaar(**velden):
        ingelogde_client.post("/club-van-20/instellingen", data={"csrf_token": _csrf(ingelogde_client), **velden})
        rij = _instellingen(db)
        return rij["club_van_20_toon_welkom"], rij["club_van_20_welkom_duur"]

    assert bewaar(club_van_20_welkom_duur="20") == (0, 20)  # vinkje niet meegestuurd = uit
    assert bewaar(club_van_20_toon_welkom="1", club_van_20_welkom_duur="1") == (1, 5)
    assert bewaar(club_van_20_toon_welkom="1", club_van_20_welkom_duur="999") == (1, 60)


def test_testmelding_komt_op_de_schermen_zonder_lid(ingelogde_client, client, db):
    ingelogde_client.post("/club-van-20/melding-testen", data={"csrf_token": _csrf(ingelogde_client), "soort": "nieuw"})
    ingelogde_client.post("/club-van-20/melding-testen", data={"csrf_token": _csrf(ingelogde_client), "soort": "verlengd"})

    nieuw, verlengd = _meldingen(db)

    assert (nieuw["naam"], nieuw["soort"], nieuw["lid_id"], nieuw["seizoenen"]) == ("Testmelding", "nieuw", None, 1)
    assert (verlengd["soort"], verlengd["seizoenen"]) == ("verlengd", 7)
    assert [m["soort"] for m in client.get("/kiosk/welkom?na=0").get_json()["meldingen"]] == ["nieuw", "verlengd"]
    assert db.execute("SELECT COUNT(*) FROM club_van_20_leden").fetchone()[0] == 0


def test_testmelding_vereist_een_account(client, db):
    resp = client.post("/club-van-20/melding-testen", data={"soort": "nieuw"})
    assert resp.status_code in (302, 400, 401, 403)
    assert _meldingen(db) == []
