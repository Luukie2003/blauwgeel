from datetime import datetime, timedelta

import mail
from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from aanmeldingen import (
    MAX_PER_UUR_PER_IP,
    bardienst_suggesties,
    ip_hash,
    maak_aanmelding,
    schoon_tekst,
    splits_naam,
    valideer_aanmelding,
)
from club_van_20 import huidig_seizoen

MOLLIE = "https://payment-links.mollie.com/payment/test123"


def _zet(db, **velden):
    for veld, waarde in velden.items():
        db.execute(f"UPDATE kiosk_scherm_instellingen SET {veld} = ? WHERE id = 1", (waarde,))
    db.commit()


def _moment(dagen):
    return (datetime.now() + timedelta(days=dagen)).strftime("%Y-%m-%dT%H:%M")


def _open(db, mollie=True):
    """Aanmelden open: aftelmoment ligt in het verleden."""
    _zet(db, club_van_20_aankondiging_aftellen_tot=_moment(-1), club_van_20_betaallink=MOLLIE if mollie else None)


def _formulier(client, **veranderd):
    data = {
        "csrf_token": _csrf(client),
        "betaalwijze": "contant",
        "bardienst": "Piet",
        "naam": "Jan de Vries",
        "bordje": "Jan & Co",
        "website": "",
    }
    data.update(veranderd)
    return client.post("/club-van-20/aanmelden", data=data)


def _aanmeldingen(db):
    return db.execute("SELECT * FROM club_van_20_aanmeldingen ORDER BY id").fetchall()


def _aanmelding(db, naam="Jan de Vries", bordje="Jan & Co", betaalwijze="contant", bardienst="Piet"):
    waarden = {"naam": naam, "bordje": bordje, "betaalwijze": betaalwijze, "bardienst": bardienst}
    aanmelding_id, _ = maak_aanmelding(db, waarden, huidig_seizoen(), 20, "test-ip")
    return aanmelding_id


# ---------- Publieke pagina en formulier ----------


def test_aanmeldknop_verschijnt_pas_op_het_aftelmoment(client, db):
    _zet(db, club_van_20_aankondiging_aftellen_tot=_moment(2))
    voor = client.get("/club-van-20/doe-mee").data.decode()
    assert 'id="aanmeldknop"' in voor
    knop = voor[voor.index('id="aanmeldknop"') : voor.index('id="aanmeldknop"') + 200]
    assert "hidden" in knop and "data-opent=" in knop

    _zet(db, club_van_20_aankondiging_aftellen_tot=_moment(-1))
    na = client.get("/club-van-20/doe-mee").data.decode()
    knop = na[na.index('id="aanmeldknop"') : na.index('id="aanmeldknop"') + 200]
    assert "hidden" not in knop
    assert "/club-van-20/aanmelden" in knop


def test_aanmelden_uit_geen_knop_en_oude_betaalknop_terug(client, db):
    _zet(db, club_van_20_aanmelden_aan=0, club_van_20_betaallink=MOLLIE)
    tekst = client.get("/club-van-20/doe-mee").data.decode()
    assert 'id="aanmeldknop"' not in tekst
    assert f'href="{MOLLIE}"' in tekst  # zoals voorheen: directe betaalknop

    _zet(db, club_van_20_aanmelden_aan=1)
    tekst = client.get("/club-van-20/doe-mee").data.decode()
    assert f'href="{MOLLIE}"' not in tekst  # nu via het formulier


def test_formulier_nog_niet_open_en_post_wordt_geweigerd(client, db):
    _zet(db, club_van_20_aankondiging_aftellen_tot=_moment(2))
    resp = client.get("/club-van-20/aanmelden")
    assert resp.status_code == 200 and "nog niet open" in resp.data.decode()
    assert 'name="bordje"' not in resp.data.decode()

    _formulier(client)
    assert _aanmeldingen(db) == []


def test_formulier_uit_toont_melding(client, db):
    _zet(db, club_van_20_aanmelden_aan=0)
    tekst = client.get("/club-van-20/aanmelden").data.decode()
    assert "kan nu niet via de site" in tekst and 'name="bordje"' not in tekst


def test_formulier_toont_mollie_alleen_met_link(client, db):
    _open(db, mollie=True)
    tekst = client.get("/club-van-20/aanmelden").data.decode()
    assert 'value="mollie"' in tekst and 'value="contant"' in tekst and MOLLIE in tekst
    assert 'maxlength="24"' in tekst

    _open(db, mollie=False)
    tekst = client.get("/club-van-20/aanmelden").data.decode()
    assert 'value="mollie"' not in tekst and 'value="contant"' in tekst


def test_contant_aanmelden_maakt_een_concept(client, db):
    _open(db)
    resp = _formulier(client)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/club-van-20/aanmelden/bedankt")

    (a,) = _aanmeldingen(db)
    assert (a["naam"], a["bordje"], a["betaalwijze"], a["bardienst"], a["status"]) == (
        "Jan de Vries", "Jan & Co", "contant", "Piet", "nieuw",
    )
    assert a["seizoen"] == huidig_seizoen() and a["bedrag"] == 20
    # Nog geen lid, dus ook niet op de publieke pagina.
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 0
    assert "Jan &amp; Co" not in client.get("/club-van-20/doe-mee").data.decode()

    bedankt = client.get("/club-van-20/aanmelden/bedankt").data.decode()
    assert "Bedankt" in bedankt and "Jan &amp; Co" in bedankt and "bij Piet" in bedankt


def test_mollie_aanmelden_heeft_geen_bardienst_nodig(client, db):
    _open(db)
    resp = _formulier(client, betaalwijze="mollie", bardienst="iets anders")
    assert resp.status_code == 302
    (a,) = _aanmeldingen(db)
    assert a["betaalwijze"] == "mollie" and a["bardienst"] is None


def test_mollie_kiezen_zonder_link_mag_niet(client, db):
    _open(db, mollie=False)
    resp = _formulier(client, betaalwijze="mollie")
    assert resp.status_code == 400 and "Kies hoe je betaalt" in resp.data.decode()
    assert _aanmeldingen(db) == []


def test_contant_zonder_bardienst_wordt_geweigerd_en_invoer_blijft_staan(client, db):
    _open(db)
    resp = _formulier(client, bardienst="  ")
    tekst = resp.data.decode()
    assert resp.status_code == 400
    assert "wie er bardienst had" in tekst
    assert 'value="Jan de Vries"' in tekst and 'value="Jan &amp; Co"' in tekst
    assert _aanmeldingen(db) == []


def test_bordje_langer_dan_het_maximum_wordt_geweigerd(client, db):
    _open(db)
    _zet(db, club_van_20_bordje_max_tekens=10)
    resp = _formulier(client, bordje="Elf tekens!")
    assert resp.status_code == 400 and "hooguit 10 tekens" in resp.data.decode()
    assert _aanmeldingen(db) == []
    assert _formulier(client, bordje="Tien teken").status_code == 302
    assert len(_aanmeldingen(db)) == 1


def test_naam_en_bordje_zijn_verplicht(client, db):
    _open(db)
    tekst = _formulier(client, naam="", bordje="").data.decode()
    assert "Vul je naam in" in tekst and "Vul in wat er op het bordje moet komen" in tekst
    assert "minstens een letter of cijfer" in _formulier(client, bordje="!!!").data.decode()
    assert _aanmeldingen(db) == []


def test_honeypot_vangt_bots_zonder_melding(client, db):
    _open(db)
    resp = _formulier(client, website="http://spam.example")
    assert resp.status_code == 302  # lijkt gelukt, maar er wordt niets opgeslagen
    assert _aanmeldingen(db) == []


def test_dubbel_versturen_geeft_een_aanmelding(client, db):
    _open(db)
    _formulier(client)
    _formulier(client, naam="jan de vries", bordje="JAN & CO")
    assert len(_aanmeldingen(db)) == 1
    # Een ander bordje van dezelfde persoon is wel een nieuwe aanmelding.
    _formulier(client, bordje="Jan senior")
    assert len(_aanmeldingen(db)) == 2


def test_te_veel_aanmeldingen_vanaf_een_ip_worden_tijdelijk_geweigerd(client, app, db):
    _open(db)
    ip_h = ip_hash("127.0.0.1", app.secret_key)
    for i in range(MAX_PER_UUR_PER_IP):
        maak_aanmelding(
            db,
            {"naam": f"Naam {i}", "bordje": f"Bordje {i}", "betaalwijze": "contant", "bardienst": "Piet"},
            huidig_seizoen(), 20, ip_h,
        )
    resp = _formulier(client)
    assert resp.status_code == 400 and "te veel aanmeldingen" in resp.data.decode()
    assert len(_aanmeldingen(db)) == MAX_PER_UUR_PER_IP


def test_zonder_csrf_token_gaat_het_niet(client, db):
    _open(db)
    client.post(
        "/club-van-20/aanmelden",
        data={"betaalwijze": "contant", "bardienst": "Piet", "naam": "Jan", "bordje": "Jan"},
    )
    assert _aanmeldingen(db) == []


# ---------- Hulpfuncties ----------


def test_invoer_wordt_schoongemaakt():
    assert schoon_tekst("  Jan \t  de​ Vries\x00 ") == "Jan de Vries"
    waarden, fouten = valideer_aanmelding(
        {"betaalwijze": "contant", "bardienst": "Piet", "naam": "Jan  de   Vries", "bordje": " Jan\n& Co "},
        {"club_van_20_bordje_max_tekens": 24},
        mollie_beschikbaar=False,
    )
    assert fouten == {} and waarden["naam"] == "Jan de Vries" and waarden["bordje"] == "Jan & Co"


def test_naam_splitsen():
    assert splits_naam("Jan van der Berg") == ("Jan", "van der Berg")
    assert splits_naam("Oeltras") == ("Oeltras", "")


def test_bardienst_suggesties_uit_het_rooster(db):
    vandaag = datetime.now().date()
    for dagen, namen in ((0, "Piet, Klaas en Marie"), (3, "Piet"), (30, "Oud Lid")):
        db.execute(
            "INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op) VALUES (?, '19:00', '23:00', ?, '2026-01-01 10:00')",
            ((vandaag - timedelta(days=dagen)).isoformat(), namen),
        )
    db.commit()
    assert bardienst_suggesties(db) == ["Piet", "Klaas", "Marie"]


# ---------- Concepttabel voor beheerders ----------


def test_concepttabel_is_niet_openbaar(client, db):
    _aanmelding(db)
    resp = client.get("/club-van-20/aanmeldingen")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_concepttabel_voor_vrijwilliger_zonder_sectie(client, db):
    _maak_vrijwilliger(db, "kassa_only", "kassa")
    _login(client, "kassa_only")
    resp = client.get("/club-van-20/aanmeldingen", follow_redirects=True)
    assert resp.request.path == "/"


def test_concepttabel_toont_openstaande_aanmeldingen_en_teller(ingelogde_client, db):
    _aanmelding(db)
    _aanmelding(db, naam="Els Bakker", bordje="Els", betaalwijze="mollie", bardienst=None)
    tekst = ingelogde_client.get("/club-van-20/aanmeldingen").data.decode()
    assert "Wachten op goedkeuring (2)" in tekst
    assert "Jan &amp; Co" in tekst and "Bardienst: Piet" in tekst and "Els Bakker" in tekst
    # Teller in de zijbalk en banner op het ledenoverzicht.
    assert '<span class="nav-badge"' in tekst
    overzicht = ingelogde_client.get("/club-van-20").data.decode()
    assert "2</strong> aanmeldingen wachten op goedkeuring" in overzicht


def test_goedkeuren_maakt_lid_met_betaalde_bijdrage(ingelogde_client, db):
    aanmelding_id = _aanmelding(db)
    resp = ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "betaling_gecontroleerd": "1",
            "modus": "nieuw",
            "bordje": "Jan & Co",
            "voornaam": "Jan",
            "achternaam": "de Vries",
            "team": "Za1",
            "telefoon": "0612345678",
            "email": "",
            "bedrag": "20",
            "betaalwijze": "contant",
            "betaald_op": "2026-10-05",
        },
    )
    assert resp.status_code == 302
    lid = db.execute("SELECT * FROM club_van_20_leden WHERE naam = 'Jan & Co'").fetchone()
    assert (lid["voornaam"], lid["achternaam"], lid["team"], lid["telefoon"], lid["email"], lid["status"]) == (
        "Jan", "de Vries", "Za1", "0612345678", None, "actief",
    )
    b = db.execute("SELECT * FROM club_van_20_bijdragen WHERE lid_id = ?", (lid["id"],)).fetchone()
    assert (b["seizoen"], b["status"], b["bedrag"], b["betaalwijze"], b["betaald_door"], b["betaald_op"]) == (
        huidig_seizoen(), "betaald", 20, "contant", "Jan de Vries", "2026-10-05",
    )
    assert "bardienst: Piet" in b["notitie"]
    a = db.execute("SELECT * FROM club_van_20_aanmeldingen WHERE id = ?", (aanmelding_id,)).fetchone()
    assert (a["status"], a["lid_id"], a["behandeld_door"]) == ("goedgekeurd", lid["id"], "admin")

    # Nu staat het bordje op de publieke pagina (en dus op het scherm).
    assert "Jan &amp; Co" in ingelogde_client.get("/club-van-20/doe-mee").data.decode()
    # En het staat niet meer in de wachtrij.
    assert "Wachten op goedkeuring (0)" in ingelogde_client.get("/club-van-20/aanmeldingen").data.decode()


def test_goedkeuren_vereist_betalingscontrole(ingelogde_client, db):
    aanmelding_id = _aanmelding(db)
    ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={"csrf_token": _csrf(ingelogde_client), "modus": "nieuw", "bordje": "Jan & Co"},
    )
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 0
    assert db.execute("SELECT status FROM club_van_20_aanmeldingen").fetchone()["status"] == "nieuw"


def test_goedkeuren_met_lege_gegevens_mag(ingelogde_client, db):
    aanmelding_id = _aanmelding(db)
    ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={"csrf_token": _csrf(ingelogde_client), "betaling_gecontroleerd": "1", "modus": "nieuw", "bordje": "Jan & Co"},
    )
    lid = db.execute("SELECT * FROM club_van_20_leden").fetchone()
    assert lid["naam"] == "Jan & Co" and lid["team"] is None and lid["telefoon"] is None
    b = db.execute("SELECT * FROM club_van_20_bijdragen").fetchone()
    assert b["status"] == "betaald" and b["bedrag"] == 20 and b["betaalwijze"] == "contant"


def test_goedkeuren_bestaand_lid_verlengt_zonder_dubbel_lid(ingelogde_client, db):
    db.execute(
        "INSERT INTO club_van_20_leden (naam, team, status, aangemaakt_op) VALUES ('Jan & Co', 'Zo2', 'actief', '2025-01-01 10:00')"
    )
    db.commit()
    lid_id = db.execute("SELECT id FROM club_van_20_leden").fetchone()["id"]
    aanmelding_id = _aanmelding(db)
    ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "betaling_gecontroleerd": "1",
            "modus": "bestaand",
            "lid_id": str(lid_id),
            "bordje": "Jan & Co",
            "team": "Za1",  # staat al op Zo2: blijft staan
            "telefoon": "0611111111",  # was leeg: wordt aangevuld
        },
    )
    leden = db.execute("SELECT * FROM club_van_20_leden").fetchall()
    assert len(leden) == 1
    assert (leden[0]["team"], leden[0]["telefoon"]) == ("Zo2", "0611111111")
    assert db.execute("SELECT status FROM club_van_20_bijdragen WHERE lid_id = ?", (lid_id,)).fetchone()["status"] == "betaald"
    assert db.execute("SELECT lid_id FROM club_van_20_aanmeldingen").fetchone()["lid_id"] == lid_id


def test_bestaand_lid_wordt_herkend_in_de_concepttabel(ingelogde_client, db):
    db.execute(
        "INSERT INTO club_van_20_leden (naam, voornaam, achternaam, status, aangemaakt_op) VALUES ('Janus', 'Jan', 'de Vries', 'actief', '2025-01-01 10:00')"
    )
    db.commit()
    _aanmelding(db, bordje="Jan & Co")  # zelfde persoon, ander bordje
    tekst = ingelogde_client.get("/club-van-20/aanmeldingen").data.decode()
    assert "bestaand lid: Janus" in tekst


def test_bordje_van_bestaand_lid_aanpassen(ingelogde_client, db):
    db.execute("INSERT INTO club_van_20_leden (naam, status, aangemaakt_op) VALUES ('Janus', 'actief', '2025-01-01 10:00')")
    db.commit()
    lid_id = db.execute("SELECT id FROM club_van_20_leden").fetchone()["id"]
    aanmelding_id = _aanmelding(db, bordje="Jan & Co")
    ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={
            "csrf_token": _csrf(ingelogde_client), "betaling_gecontroleerd": "1", "modus": "bestaand",
            "lid_id": str(lid_id), "bordje": "Jan & Co", "bordje_aanpassen": "1",
        },
    )
    assert db.execute("SELECT naam FROM club_van_20_leden").fetchone()["naam"] == "Jan & Co"


def test_nieuw_lid_met_bezet_bordje_wordt_niet_aangemaakt(ingelogde_client, db):
    db.execute("INSERT INTO club_van_20_leden (naam, status, aangemaakt_op) VALUES ('jan & co', 'actief', '2025-01-01 10:00')")
    db.commit()
    aanmelding_id = _aanmelding(db)
    resp = ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={"csrf_token": _csrf(ingelogde_client), "betaling_gecontroleerd": "1", "modus": "nieuw", "bordje": "Jan & Co"},
        follow_redirects=True,
    )
    assert "Er is al een lid met naambordje" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 1
    assert db.execute("SELECT status FROM club_van_20_aanmeldingen").fetchone()["status"] == "nieuw"
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_bijdragen").fetchone()["n"] == 0


def test_afwijzen_bewaart_de_aanmelding_zonder_lid(ingelogde_client, db):
    aanmelding_id = _aanmelding(db)
    ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/afwijzen",
        data={"csrf_token": _csrf(ingelogde_client), "reden": "Geen betaling gevonden"},
    )
    a = db.execute("SELECT * FROM club_van_20_aanmeldingen").fetchone()
    assert (a["status"], a["opmerking"], a["behandeld_door"]) == ("afgewezen", "Geen betaling gevonden", "admin")
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 0
    tekst = ingelogde_client.get("/club-van-20/aanmeldingen").data.decode()
    assert "afgewezen" in tekst and "Geen betaling gevonden" in tekst


def test_een_aanmelding_kan_maar_een_keer_behandeld_worden(ingelogde_client, db):
    aanmelding_id = _aanmelding(db)
    data = {"csrf_token": _csrf(ingelogde_client), "betaling_gecontroleerd": "1", "modus": "nieuw", "bordje": "Jan & Co"}
    ingelogde_client.post(f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren", data=data)
    resp = ingelogde_client.post(f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren", data=data, follow_redirects=True)
    assert "al behandeld" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden").fetchone()["n"] == 1
    ingelogde_client.post(f"/club-van-20/aanmeldingen/{aanmelding_id}/afwijzen", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT status FROM club_van_20_aanmeldingen").fetchone()["status"] == "goedgekeurd"


def test_instellingen_voor_aanmelden_opslaan(ingelogde_client, db):
    pagina = ingelogde_client.get("/club-van-20/instellingen").data.decode()
    assert "Aanmelden via de website" in pagina and "club_van_20_bordje_max_tekens" in pagina

    # Het formulier stuurt alle velden mee; alleen deze zijn hier van belang.
    veld_data = {
        "csrf_token": _csrf(ingelogde_client),
        "club_van_20_bordje_max_tekens": "30",
        "club_van_20_betaallink": MOLLIE,
    }
    ingelogde_client.post("/club-van-20/instellingen", data=veld_data)
    i = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert i["club_van_20_aanmelden_aan"] == 0  # vinkje niet meegestuurd = uit
    assert i["club_van_20_bordje_max_tekens"] == 30 and i["club_van_20_betaallink"] == MOLLIE

    ingelogde_client.post("/club-van-20/instellingen", data={**veld_data, "club_van_20_aanmelden_aan": "on", "club_van_20_bordje_max_tekens": "3"})
    i = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert i["club_van_20_aanmelden_aan"] == 1 and i["club_van_20_bordje_max_tekens"] == 5  # ondergrens


# ---------- Melding per mail ----------


def _gebruiker(db, naam, email, rol="beheerder", secties="voorraad", mail_aan=1, actief=1):
    db.execute(
        """INSERT INTO gebruikers (naam, wachtwoord_hash, rol, secties, email, mail_club_aanmelding, actief, aangemaakt_op)
           VALUES (?, 'x', ?, ?, ?, ?, ?, '2026-01-01 10:00')""",
        (naam, rol, secties, email, mail_aan, actief),
    )
    db.commit()


def _vang_mails(monkeypatch):
    verstuurd = []
    monkeypatch.setattr(
        mail, "stuur_mail", lambda onderwerp, tekst, naar=None, **kw: verstuurd.append((naar, onderwerp, tekst))
    )
    return verstuurd


def test_nieuwe_aanmelding_mailt_wie_dat_heeft_aangevinkt(client, db, monkeypatch):
    _open(db)
    _gebruiker(db, "luuk", "luuk@example.com")
    _gebruiker(db, "club_vrijwilliger", "club@example.com", rol="vrijwilliger", secties="club_van_20")
    # Krijgen geen mail: niet aangevinkt, geen adres, geen toegang tot de Club van 20, geblokkeerd.
    _gebruiker(db, "niet_aangevinkt", "nee@example.com", mail_aan=0)
    _gebruiker(db, "zonder_adres", "", mail_aan=1)
    _gebruiker(db, "kassa_vrijwilliger", "kassa@example.com", rol="vrijwilliger", secties="kassa")
    _gebruiker(db, "geblokkeerd", "weg@example.com", actief=0)
    verstuurd = _vang_mails(monkeypatch)

    _formulier(client)

    assert sorted(v[0] for v in verstuurd) == ["club@example.com", "luuk@example.com"]
    _, onderwerp, tekst = verstuurd[0]
    assert onderwerp == "Nieuwe Club van 20-aanmelding: Jan & Co"
    assert "Naam: Jan de Vries" in tekst and "Betaling: Contant aan de bar" in tekst and "Bardienst: Piet" in tekst
    assert "/club-van-20/aanmeldingen" in tekst and "wacht nu 1 aanmelding op goedkeuring" in tekst


def test_melding_valt_terug_op_het_meldingsadres(client, db, monkeypatch):
    _open(db)
    db.execute("UPDATE instellingen SET notificatie_email = 'bestuur@example.com' WHERE id = 1")
    db.commit()
    verstuurd = _vang_mails(monkeypatch)
    _formulier(client, betaalwijze="mollie")
    assert [v[0] for v in verstuurd] == ["bestuur@example.com"]
    assert "Betaling: Online betalen" in verstuurd[0][2] and "Bardienst" not in verstuurd[0][2]


def test_dubbele_aanmelding_en_mislukte_validatie_mailen_niet(client, db, monkeypatch):
    _open(db)
    _gebruiker(db, "luuk", "luuk@example.com")
    verstuurd = _vang_mails(monkeypatch)
    _formulier(client, bordje="")  # ongeldig
    _formulier(client)
    _formulier(client)  # dubbel
    assert len(verstuurd) == 1


def test_mislukte_mail_laat_de_aanmelding_niet_mislukken(client, db, monkeypatch):
    _open(db)
    _gebruiker(db, "luuk", "luuk@example.com")

    def kapot(*args, **kwargs):
        raise RuntimeError("smtp is stuk")

    monkeypatch.setattr(mail, "stuur_mail", kapot)
    resp = _formulier(client)
    assert resp.status_code == 302
    assert len(_aanmeldingen(db)) == 1


def test_voorkeur_mail_bij_aanmelding_opslaan(ingelogde_client, db):
    pagina = ingelogde_client.get("/account/voorkeuren").data.decode()
    assert "Mail ontvangen bij een nieuwe Club van 20-aanmelding" in pagina

    ingelogde_client.post(
        "/account/voorkeuren", data={"csrf_token": _csrf(ingelogde_client), "mail_club_aanmelding": "on"}
    )
    assert db.execute("SELECT mail_club_aanmelding FROM gebruikers WHERE naam = 'admin'").fetchone()[0] == 1
    ingelogde_client.post("/account/voorkeuren", data={"csrf_token": _csrf(ingelogde_client)})
    assert db.execute("SELECT mail_club_aanmelding FROM gebruikers WHERE naam = 'admin'").fetchone()[0] == 0
