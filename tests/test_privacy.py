from datetime import datetime, timedelta

from conftest import stel_csrf_token_in as _csrf

from aanmeldingen import ruim_op

from test_club_van_20_aanmeldingen import _aanmelding, _aanmeldingen, _formulier, _open


def _zet_contact(db, contact):
    db.execute("UPDATE instellingen SET privacy_contact = ? WHERE id = 1", (contact,))
    db.commit()


def test_privacyverklaring_is_openbaar_en_compleet(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    tekst = resp.data.decode()
    for onderdeel in (
        "Privacyverklaring",
        "Wie is verantwoordelijk?",
        "Aanmelden voor de Club van 20",
        "De ledenlijst van de Club van 20",
        "Accounts van vrijwilligers",
        "Cookies en tracking",
        "Met wie delen we gegevens?",
        "Jouw rechten",
        "Autoriteit Persoonsgegevens",
        "Mollie",
        "PythonAnywhere",
    ):
        assert onderdeel in tekst, onderdeel
    assert "laatst bijgewerkt op 1 oktober 2026" in tekst


def test_privacyverklaring_zonder_streepjes_en_zonder_mollie_gedeelte(client):
    import html
    import re

    pagina = client.get("/privacy").data.decode()
    tekst = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>", "", pagina, flags=re.S)))
    # Geen gedachtestreepjes of losse/dubbele streepjes als leesteken, en geen
    # "hangende" streepjes zoals "advertentie- of analysecookies".
    for streep in ("\u2014", "\u2013", " - ", "--"):
        assert streep not in tekst, repr(streep)
    assert not re.search(r"\w- ", tekst) and not re.search(r"\w-,", tekst)
    # Het aparte stukje over Mollie bij "Met wie delen we gegevens?" is weg.
    assert "Mollie-dashboard" not in tekst and "privacyverklaring van Mollie" not in tekst
    assert "PythonAnywhere" in tekst


def test_contactadres_is_instelbaar(client, db):
    assert "Spreek een bestuurslid aan of vraag het aan de bar" in client.get("/privacy").data.decode()

    _zet_contact(db, "bestuur@example.nl")
    tekst = client.get("/privacy").data.decode()
    assert 'href="mailto:bestuur@example.nl"' in tekst
    assert "Spreek een bestuurslid aan" not in tekst

    _zet_contact(db, "het secretariaat in de kantine")
    tekst = client.get("/privacy").data.decode()
    assert "Neem contact op via het secretariaat in de kantine" in tekst and "mailto:" not in tekst


def test_contactadres_opslaan_bij_instellingen(ingelogde_client, db):
    assert "privacy_contact" in ingelogde_client.get("/instellingen").data.decode()
    ingelogde_client.post(
        "/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "privacy_contact": "  privacy@example.nl "},
    )
    assert db.execute("SELECT privacy_contact FROM instellingen").fetchone()[0] == "privacy@example.nl"


def test_links_naar_de_privacyverklaring_staan_waar_gegevens_worden_verzameld(client, db, ingelogde_client):
    _open(db)
    assert "/privacy" in client.get("/club-van-20/aanmelden").data.decode()
    assert "/privacy" in client.get("/club-van-20/doe-mee").data.decode()
    assert "/privacy" in client.get("/club-van-20/aanmelden/bedankt").data.decode()
    assert "/privacy" in ingelogde_client.get("/tips").data.decode()  # footer van de beheersite


def test_oude_gegevens_worden_opgeruimd(db):
    nu = datetime.now()

    def tijd(dagen):
        return (nu - timedelta(days=dagen)).strftime("%Y-%m-%d %H:%M")

    verse = _aanmelding(db, naam="Vers", bordje="Vers")
    oude = _aanmelding(db, naam="Oud", bordje="Oud")
    afgewezen_oud = _aanmelding(db, naam="Weg Oud", bordje="Weg Oud")
    afgewezen_recent = _aanmelding(db, naam="Weg Recent", bordje="Weg Recent")
    goedgekeurd_oud = _aanmelding(db, naam="Goed Oud", bordje="Goed Oud")
    for aanmelding_id in (verse, oude, afgewezen_oud, afgewezen_recent, goedgekeurd_oud):
        db.execute("UPDATE club_van_20_aanmeldingen SET ip_hash = 'abc' WHERE id = ?", (aanmelding_id,))
    db.execute("UPDATE club_van_20_aanmeldingen SET aangemaakt_op = ? WHERE id = ?", (tijd(40), oude))
    db.execute(
        "UPDATE club_van_20_aanmeldingen SET status = 'afgewezen', aangemaakt_op = ?, behandeld_op = ? WHERE id = ?",
        (tijd(400), tijd(380), afgewezen_oud),
    )
    db.execute(
        "UPDATE club_van_20_aanmeldingen SET status = 'afgewezen', behandeld_op = ? WHERE id = ?",
        (tijd(10), afgewezen_recent),
    )
    db.execute(
        "UPDATE club_van_20_aanmeldingen SET status = 'goedgekeurd', aangemaakt_op = ?, behandeld_op = ? WHERE id = ?",
        (tijd(900), tijd(890), goedgekeurd_oud),
    )
    db.execute("INSERT INTO paginabezoeken (endpoint, weergave_modus, datum) VALUES ('oud', 'desktop', ?)", (tijd(800),))
    db.execute("INSERT INTO paginabezoeken (endpoint, weergave_modus, datum) VALUES ('nieuw', 'desktop', ?)", (tijd(100),))
    db.commit()

    ruim_op(db)

    rest = {r["id"]: r for r in _aanmeldingen(db)}
    assert afgewezen_oud not in rest  # afgewezen langer dan een jaar geleden
    assert {verse, oude, afgewezen_recent, goedgekeurd_oud} <= set(rest)
    assert rest[verse]["ip_hash"] == "abc" and rest[afgewezen_recent]["ip_hash"] == "abc"
    assert rest[oude]["ip_hash"] is None and rest[goedgekeurd_oud]["ip_hash"] is None
    assert [r["endpoint"] for r in db.execute("SELECT endpoint FROM paginabezoeken").fetchall()] == ["nieuw"]


def test_aanmelden_ruimt_onderweg_op(client, db):
    _open(db)
    oud = _aanmelding(db, naam="Oud", bordje="Oud")
    db.execute("UPDATE club_van_20_aanmeldingen SET ip_hash = 'abc', aangemaakt_op = '2020-01-01 10:00' WHERE id = ?", (oud,))
    db.commit()
    _formulier(client)
    assert db.execute("SELECT ip_hash FROM club_van_20_aanmeldingen WHERE id = ?", (oud,)).fetchone()[0] is None
