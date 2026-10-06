"""De handterminal-weergave (PDA) na de uitbreiding: startscherm met statusregels,
voorraadlijst, tellingen in de handterminal-schil, bestel-advies om te bekijken,
aanmeldingen goedkeuren, en een looplijst die je kunt pauzeren en hervatten."""

from datetime import datetime, timedelta

from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger
from test_voorspelling import _bouw_geschiedenis, _product

from voorspelling import (
    telling_ver_van_verwachting,
    verwachte_verkoop_sinds_telling,
    verwachte_voorraad,
)


def _pda(client):
    client.get("/weergave/pda")
    return client


def _product_rij(db, naam, voorraad, minimum, categorie="Bier", actief=1):
    cur = db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad, verkoopprijs, actief)
           VALUES (?, ?, 'stuks', ?, ?, 2.0, ?)""",
        (naam, categorie, voorraad, minimum, actief),
    )
    db.commit()
    return cur.lastrowid


def _alleen_eigen_producten(db):
    """De testdatabase heeft zelf ook producten; voor de looplijst willen we er precies onze eigen."""
    db.execute("UPDATE producten SET actief = 0")
    db.commit()


def _heeft_pda_schil(tekst):
    return "pda-kop-menuknop" in tekst and 'class="app-zijbalk"' not in tekst


# ---------- Startscherm ----------


def test_start_toont_wat_aandacht_nodig_heeft(ingelogde_client, db):
    _product_rij(db, "Laag Bier", 1, 10)
    _product_rij(db, "Genoeg Bier", 50, 10)
    db.execute("INSERT INTO mededelingen (tekst, naam, datum, urgent) VALUES ('Koelkast stuk', 'x', '2026-10-01 10:00', 1)")
    db.execute("INSERT INTO bestellingen (status, aangemaakt_op) VALUES ('besteld', '2026-10-01 10:00')")
    db.commit()

    tekst = _pda(ingelogde_client).get("/").data.decode()

    laag = db.execute("SELECT COUNT(*) AS n FROM producten WHERE actief = 1 AND voorraad < min_voorraad").fetchone()["n"]
    assert laag >= 1
    assert f"{laag} {'product' if laag == 1 else 'producten'} onder het minimum" in tekst
    assert "/voorraadoverzicht?alleen=laag" in tekst
    assert "1 bestelling om in te boeken" in tekst
    assert "Prikbord: 1 open" in tekst and "1 urgent" in tekst
    assert "Nog nooit geteld" in tekst
    assert "Vet vervangen" in tekst  # beheerder heeft ook de keuken-sectie


def test_start_menu_heeft_de_nieuwe_ingangen_voor_een_beheerder(ingelogde_client):
    tekst = _pda(ingelogde_client).get("/").data.decode()
    for label in ["Voorraad", "Prognose", "Tellingen", "Keuken", "Kluis", "Aanmeldingen", "Scannen", "Kiosk"]:
        assert f'pda-menu-label">{label}<' in tekst, label
    assert "Tips &amp; functies" in tekst


def test_start_toont_een_vrijwilliger_alleen_wat_bij_de_rechten_past(client, db):
    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    _product_rij(db, "Laag Bier", 1, 10)
    _login(client, "keukenhulp")

    tekst = _pda(client).get("/").data.decode()

    assert "Vet vervangen" in tekst and 'pda-menu-label">Keuken<' in tekst
    assert "onder het minimum" not in tekst and "Voorraad op orde" not in tekst
    for label in ["Voorraad", "Tellen", "Kluis", "Aanmeldingen", "Prognose"]:
        assert f'pda-menu-label">{label}<' not in tekst, label


# ---------- Voorraadlijst ----------


def test_voorraadlijst_in_de_handterminal_schil(ingelogde_client, db):
    _product_rij(db, "Laag Bier", 1, 10)
    _product_rij(db, "Genoeg Bier", 50, 10)
    _product_rij(db, "Oud Product", 5, 1, actief=0)

    resp = _pda(ingelogde_client).get("/voorraadoverzicht?alleen=laag")
    tekst = resp.data.decode()

    assert _heeft_pda_schil(tekst)
    assert "Laag Bier" in tekst and "Genoeg Bier" in tekst
    assert "Oud Product" not in tekst
    assert "pda-voorraad-rij--laag" in tekst
    assert "var alleenLaag = true;" in tekst
    assert "Voorraadwaarde per categorie" not in tekst


def test_voorraadoverzicht_op_desktop_blijft_zoals_het_was(ingelogde_client, db):
    ingelogde_client.get("/weergave/desktop")
    tekst = ingelogde_client.get("/voorraadoverzicht").data.decode()
    assert "Voorraadwaarde per categorie" in tekst and "pda-kop-menuknop" not in tekst


def test_keuken_in_de_handterminal_toont_alleen_keuken_producten(client, db):
    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    _product_rij(db, "Frituurvet", 3, 1, categorie="Keuken")
    _product_rij(db, "Heineken", 30, 10, categorie="Bier")
    _login(client, "keukenhulp")

    tekst = _pda(client).get("/keuken").data.decode()

    assert _heeft_pda_schil(tekst)
    assert "Frituurvet" in tekst and "Heineken" not in tekst
    # Geen voorraad-rechten: geen links naar productpagina's en geen productzoeker.
    assert 'href="/producten/' not in tekst and 'id="pda-zoek-invoer"' not in tekst


# ---------- Tellingen ----------


def _maak_telling(client, db):
    pid = _product_rij(db, "Getelde Cola", 20, 5)
    resp = client.post(
        "/tellen", data={"csrf_token": _csrf(client), f"geteld_{pid}": "12", "opmerking": "", "datum": ""}
    )
    assert resp.status_code == 302
    return resp.headers["Location"], pid


def test_telling_detail_en_overzicht_in_de_handterminal_schil(ingelogde_client, db):
    pad, _ = _maak_telling(ingelogde_client, db)
    _pda(ingelogde_client)

    detail = ingelogde_client.get(pad).data.decode()
    assert _heeft_pda_schil(detail)
    assert "Getelde Cola" in detail and "Corrigeren" in detail and "Verkooprapport (PDF)" in detail

    overzicht = ingelogde_client.get("/tellingen").data.decode()
    assert _heeft_pda_schil(overzicht)
    assert "Alle tellingen" in overzicht and "Omzet per week" in overzicht


def test_telling_detail_op_desktop_blijft_de_tabel(ingelogde_client, db):
    pad, _ = _maak_telling(ingelogde_client, db)
    ingelogde_client.get("/weergave/desktop")
    tekst = ingelogde_client.get(pad).data.decode()
    assert "Voorraad voor telling" in tekst and "pda-kop-menuknop" not in tekst


# ---------- Bestellijst ----------


def test_bestellijst_in_de_handterminal_toont_wat_er_besteld_moet_worden(ingelogde_client, db):
    _product_rij(db, "Bijna Op", 2, 10)
    db.execute(
        "INSERT INTO bestellijst_meldingen (tekst, bron, aangemaakt_op) VALUES ('Wc-papier', 'verbruiksvoorwerp', '2026-10-01 10:00')"
    )
    db.commit()

    tekst = _pda(ingelogde_client).get("/bestellijst").data.decode()

    assert "Nu bestellen" in tekst and "Bijna Op" in tekst
    assert "Wc-papier" in tekst and "Afhandelen" in tekst
    # Een bestelling klaarzetten blijft op de computer.
    assert "Bestelling aanmaken" not in tekst and "Voorgesteld om te bestellen" not in tekst


# ---------- Aanmeldingen ----------


def _aanmelding(db, naam="Jan Jansen", bordje="Jan & Co"):
    from aanmeldingen import maak_aanmelding
    from club_van_20 import huidig_seizoen

    aanmelding_id, _ = maak_aanmelding(
        db,
        {"naam": naam, "bordje": bordje, "betaalwijze": "contant", "bardienst": "Piet"},
        huidig_seizoen(),
        20,
        "test-ip",
    )
    return aanmelding_id


def test_aanmelding_goedkeuren_op_de_handterminal(ingelogde_client, db):
    aanmelding_id = _aanmelding(db)
    tekst = _pda(ingelogde_client).get("/club-van-20/aanmeldingen").data.decode()

    assert _heeft_pda_schil(tekst)
    assert "Jan &amp; Co" in tekst and "Contant" in tekst and "bardienst: Piet" in tekst

    # Zonder het vinkje "betaling gecontroleerd" gebeurt er niets.
    resp = ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={"csrf_token": _csrf(ingelogde_client), "modus": "nieuw", "bordje": "Jan & Co",
              "voornaam": "Jan", "achternaam": "Jansen", "bedrag": "20", "betaalwijze": "contant"},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT status FROM club_van_20_aanmeldingen").fetchone()["status"] == "nieuw"

    ingelogde_client.post(
        f"/club-van-20/aanmeldingen/{aanmelding_id}/goedkeuren",
        data={"csrf_token": _csrf(ingelogde_client), "betaling_gecontroleerd": "1", "modus": "nieuw",
              "bordje": "Jan & Co", "voornaam": "Jan", "achternaam": "Jansen", "bedrag": "20",
              "betaalwijze": "contant"},
    )
    assert db.execute("SELECT status FROM club_van_20_aanmeldingen").fetchone()["status"] == "goedgekeurd"
    assert db.execute("SELECT COUNT(*) AS n FROM club_van_20_leden WHERE naam = 'Jan & Co'").fetchone()["n"] == 1


def test_aanmeldingen_op_desktop_houden_de_tabel(ingelogde_client, db):
    _aanmelding(db)
    ingelogde_client.get("/weergave/desktop")
    tekst = ingelogde_client.get("/club-van-20/aanmeldingen").data.decode()
    assert "js-keur" in tekst and "pda-kop-menuknop" not in tekst


# ---------- Verwachte voorraad (model) ----------


def _geschiedenis_tot_voor_twee_dagen(db):
    """10 wekelijkse tellingen van een product dat 10 per dag verkoopt, de laatste 2 dagen geleden."""
    laatste = (datetime.now() - timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
    tijden = [laatste - timedelta(days=7 * (9 - i)) for i in range(10)]
    pid = _product(db, "Snelle Pils", voorraad=50)
    _bouw_geschiedenis(db, {pid: 10}, tijdstippen=tijden, geteld=50)
    return pid, laatste


def test_verwachte_verkoop_sinds_de_laatste_telling(db):
    pid, laatste = _geschiedenis_tot_voor_twee_dagen(db)

    verwachting = verwachte_verkoop_sinds_telling(db, nu=laatste + timedelta(days=2))

    assert 12 < verwachting[pid]["verwacht"] < 30  # zo'n 2 dagen van 10
    assert verwachting[pid]["laag"] <= verwachting[pid]["verwacht"] <= verwachting[pid]["hoog"]
    assert verwachting[pid]["ruim_laag"] <= verwachting[pid]["laag"]
    assert verwachting[pid]["waarnemingen"] >= 3
    stand = verwachte_voorraad(verwachting[pid], 50)
    assert stand["laag"] <= stand["verwacht"] <= stand["hoog"] <= 50


def test_zonder_genoeg_tellingen_geen_verwachting(db):
    _product(db, "Nieuw Product")
    assert verwachte_verkoop_sinds_telling(db) == {}
    assert verwachte_voorraad(None, 10) is None
    assert telling_ver_van_verwachting(None, 10, 3) is None


def test_telling_ver_van_de_verwachting_wordt_gesignaleerd(db):
    pid, laatste = _geschiedenis_tot_voor_twee_dagen(db)
    verwachting = verwachte_verkoop_sinds_telling(db, nu=laatste + timedelta(days=2))[pid]

    verwacht = verwachte_voorraad(verwachting, 50)["verwacht"]
    assert telling_ver_van_verwachting(verwachting, 50, verwacht) is None
    assert telling_ver_van_verwachting(verwachting, 50, 0) == "minder"
    assert telling_ver_van_verwachting(verwachting, 50, 90) == "meer"


def test_looplijst_toont_de_verwachting_en_het_controlescherm_waarschuwt(ingelogde_client, db):
    _alleen_eigen_producten(db)
    pid, _ = _geschiedenis_tot_voor_twee_dagen(db)
    # Geregistreerd 100, verwacht verbruik zo'n 20 (marge ruim): 0 geteld is dan duidelijk te weinig,
    # los van het tijdstip van de dag waarop de test draait.
    db.execute("UPDATE producten SET voorraad = 100 WHERE id = ?", (pid,))
    db.commit()
    c = _pda(ingelogde_client)
    c.get("/tellen/lopen/starten")

    pagina = c.get("/tellen/lopen").data.decode()
    assert "Verwacht nu ongeveer" in pagina

    # Veel minder geteld dan verwacht: het controlescherm vraagt om nog eens tellen.
    for waarde in ("0", "0"):  # bar, daarna voorraadhok
        c.post("/tellen/lopen", data={"csrf_token": _csrf(c), "geteld": waarde, "actie": "volgende"})
    controle = c.get("/tellen/lopen/controleren").data.decode()
    assert "Veel minder dan verwacht" in controle and "Nog eens tellen?" in controle


# ---------- Looplijst pauzeren en hervatten ----------


def _loop_stap(client, waarde, actie="volgende"):
    return client.post("/tellen/lopen", data={"csrf_token": _csrf(client), "geteld": waarde, "actie": actie})


def _nieuw_toestel(app):
    client = app.test_client()
    resp = client.post(
        "/login", data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": _csrf(client)}
    )
    assert resp.status_code == 302
    client.get("/weergave/pda")
    return client


def test_looplijst_pauzeren_en_op_een_ander_toestel_hervatten(app, ingelogde_client, db):
    _alleen_eigen_producten(db)
    eerste = _product_rij(db, "Alpha", 10, 1)
    tweede = _product_rij(db, "Beta", 10, 1)
    c = _pda(ingelogde_client)
    c.get("/tellen/lopen/starten")
    _loop_stap(c, "5")  # Alpha, bar
    resp = _loop_stap(c, "7", actie="pauzeren")  # Beta, bar: bewaren en stoppen
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/tellen")

    rij = db.execute("SELECT * FROM loop_voortgang").fetchone()
    assert rij["fase"] == "bar" and rij["indx"] == 1 and rij["review"] is None
    assert f'"{tweede}": "7"' in rij["bar"] and f'"{eerste}": "5"' in rij["bar"]

    tellen = c.get("/tellen").data.decode()
    assert "Looplijst onderbroken" in tellen and "product 2 van 2" in tellen and "Doorgaan" in tellen

    # Op een ander toestel (nieuwe sessie) pak je 'm op waar je was, met de ingevulde waarde.
    ander = _nieuw_toestel(app)
    assert "Doorgaan" in ander.get("/tellen").data.decode()
    pagina = ander.get("/tellen/lopen").data.decode()
    assert "Product 2 van 2" in pagina and 'value="7"' in pagina


def test_looplijst_bewaard_tot_en_met_het_controlescherm_en_wissen_bij_bevestigen(app, ingelogde_client, db):
    _alleen_eigen_producten(db)
    _product_rij(db, "Alpha", 10, 1)
    _product_rij(db, "Beta", 10, 1)
    c = _pda(ingelogde_client)
    c.get("/tellen/lopen/starten")
    for waarde in ("3", "4", "1", "2"):  # bar Alpha/Beta, hok Alpha/Beta
        _loop_stap(c, waarde)
    assert db.execute("SELECT review FROM loop_voortgang").fetchone()["review"] is not None

    ander = _nieuw_toestel(app)
    resp = ander.get("/tellen/lopen")
    assert resp.status_code == 302 and "controleren" in resp.headers["Location"]
    controle = ander.get("/tellen/lopen/controleren").data.decode()
    assert "Telling controleren" in controle

    ander.post("/tellen/lopen/controleren", data={"csrf_token": _csrf(ander), "actie": "bevestigen",
                                                  **{f"totaal_{r['id']}": "5" for r in db.execute("SELECT id FROM producten")}})
    assert db.execute("SELECT COUNT(*) AS n FROM loop_voortgang").fetchone()["n"] == 0
    assert db.execute("SELECT COUNT(*) AS n FROM tellingen").fetchone()["n"] == 1


def test_looplijst_stoppen_en_opnieuw_beginnen_wissen_de_bewaarde_stand(ingelogde_client, db):
    _alleen_eigen_producten(db)
    _product_rij(db, "Alpha", 10, 1)
    _product_rij(db, "Beta", 10, 1)
    c = _pda(ingelogde_client)
    c.get("/tellen/lopen/starten")
    _loop_stap(c, "3")
    assert db.execute("SELECT COUNT(*) AS n FROM loop_voortgang").fetchone()["n"] == 1

    c.post("/tellen/lopen", data={"csrf_token": _csrf(c), "actie": "stoppen"})
    assert db.execute("SELECT COUNT(*) AS n FROM loop_voortgang").fetchone()["n"] == 0
    assert "Looplijst onderbroken" not in c.get("/tellen").data.decode()

    _loop_stap(c, "3")
    assert db.execute("SELECT COUNT(*) AS n FROM loop_voortgang").fetchone()["n"] == 1
    c.get("/tellen/lopen/starten")  # opnieuw beginnen
    assert db.execute("SELECT COUNT(*) AS n FROM loop_voortgang").fetchone()["n"] == 0


def test_verlopen_bewaarde_looplijst_wordt_niet_meer_aangeboden(ingelogde_client, db):
    _alleen_eigen_producten(db)
    _product_rij(db, "Alpha", 10, 1)
    c = _pda(ingelogde_client)
    c.get("/tellen/lopen/starten")
    _loop_stap(c, "3", actie="pauzeren")
    oud = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
    db.execute("UPDATE loop_voortgang SET bijgewerkt_op = ?", (oud,))
    db.commit()
    with c.session_transaction() as sessie:
        for sleutel in ("loop_fase", "loop_index", "loop_bar", "loop_hok", "loop_review"):
            sessie.pop(sleutel, None)

    assert "Looplijst onderbroken" not in c.get("/tellen").data.decode()
    assert db.execute("SELECT COUNT(*) AS n FROM loop_voortgang").fetchone()["n"] == 0
    assert c.get("/tellen/lopen/hervatten").status_code == 302


def test_looplijst_hervatten_hoort_bij_de_voorraad_sectie(client, db):
    _maak_vrijwilliger(db, "kassahulp", "kassa")
    _login(client, "kassahulp")
    resp = client.get("/tellen/lopen/hervatten")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
