"""De handterminal-weergave van de site is weg (2.23.0): op de Zebra werkt de app, en een telefoon krijgt de gewone site in de
clubstijl. Een oude bladwijzer of een oud cookie doet niets meer."""

TELEFOON_UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"


def test_telefoon_krijgt_de_gewone_site(ingelogde_client):
    for cookie in (None, "pda"):
        if cookie:
            ingelogde_client.set_cookie("weergave", cookie)
        tekst = ingelogde_client.get("/", headers={"User-Agent": TELEFOON_UA}).data.decode()
        assert "pda-" not in tekst and "handterminal-weergave" not in tekst.lower()


def test_geen_weergave_cookie_meer(client):
    antwoord = client.get("/login", headers={"User-Agent": TELEFOON_UA})
    assert not any(c.startswith("weergave=") for c in antwoord.headers.getlist("Set-Cookie"))


def test_een_oude_bladwijzer_gaat_terug_en_ruimt_het_cookie_op(ingelogde_client):
    ingelogde_client.set_cookie("weergave", "pda")
    for adres in ("/weergave/pda", "/weergave/desktop"):
        antwoord = ingelogde_client.get(adres)
        assert antwoord.status_code == 302
        assert any(c.startswith("weergave=;") for c in antwoord.headers.getlist("Set-Cookie"))
