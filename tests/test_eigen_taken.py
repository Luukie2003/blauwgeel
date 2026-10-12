"""Eigen taken in 'Wat moet er nu?': toevoegen, koppelen aan mensen, de pagina openen en de vraag 'Taak afgerond?'."""

import re
from datetime import date, timedelta

import mail
from conftest import stel_csrf_token_in as _csrf
from test_secties_rechten import _login, _maak_vrijwilliger

from eigen_taken import (
    TAAK_SOORTEN,
    doel,
    endpoint_toegankelijk,
    maak_taak,
    rond_af,
    taken_voor_gebruiker,
    vraag_kandidaten,
)

ADMIN = 1  # het seed-account 'admin'


def _id(db, naam):
    return db.execute("SELECT id FROM gebruikers WHERE naam = ?", (naam,)).fetchone()[0]


def _vrijwilliger(app, db, naam="bakker", secties="voorraad"):
    _maak_vrijwilliger(db, naam, secties)
    client = app.test_client()
    _login(client, naam)
    return client, _id(db, naam)


def _taak(db, titel="Prijzenlijst nalopen", soort="preset:prijzen", ids=(ADMIN,), iedereen=True, deadline=None, omschrijving=""):
    taak_id, fout = maak_taak(db, titel, omschrijving, soort, deadline, list(ids), iedereen, "admin")
    assert fout is None, fout
    return taak_id


def _dashboard(client):
    return client.get("/").data.decode()


# ---------- De catalogus ----------


def test_elke_taaksoort_verwijst_naar_bestaande_pagina_s(app):
    eindpunten = {r.endpoint: r.methods for r in app.url_map.iter_rules()}
    for sleutel, soort in TAAK_SOORTEN.items():
        assert soort["endpoint"] in eindpunten, f"{sleutel}: pagina {soort['endpoint']} bestaat niet"
        assert "GET" in eindpunten[soort["endpoint"]]
        for actie in soort["afronden_op"]:
            assert actie in eindpunten and "POST" in eindpunten[actie], f"{sleutel}: {actie} is geen opslaan-actie"


def test_een_pagina_uit_het_menu_telt_al_zijn_acties_mee():
    gekozen = doel("pagina:kassa_tellen")
    assert gekozen["endpoint"] == "kassa_tellen" and "kassa_telling_goedkeuren" in gekozen["afronden_op"]
    assert doel("pagina:bestaat_niet") is None and doel("eigen") is None and doel("preset:bestaat_niet") is None


# ---------- Een taak maken ----------


def test_een_taak_vraagt_om_een_naam_en_minstens_een_persoon(db):
    assert maak_taak(db, " ", "", "eigen", None, [ADMIN], True, "admin")[1] == "Geef de taak een naam."
    assert "minstens één persoon" in maak_taak(db, "X", "", "eigen", None, [], True, "admin")[1]
    assert "geen geldige datum" in maak_taak(db, "X", "", "eigen", "morgen", [ADMIN], True, "admin")[1]
    assert "Kies waar" in maak_taak(db, "X", "", "pagina:bestaat_niet", None, [ADMIN], True, "admin")[1]
    assert "bestaat niet (meer)" in maak_taak(db, "X", "", "eigen", None, [999], True, "admin")[1]
    assert db.execute("SELECT COUNT(*) FROM taken").fetchone()[0] == 0


def test_iemand_zonder_toegang_tot_de_pagina_kan_de_taak_niet_krijgen(app, db):
    _maak_vrijwilliger(db, "keukenhulp", "keuken")
    _maak_vrijwilliger(db, "bakker", "voorraad")
    fout = maak_taak(db, "Prijzen", "", "preset:prijzen", None, [_id(db, "bakker")], True, "admin")[1]
    assert "bakker heeft geen toegang tot 'Prijzenlijst nalopen'" in fout  # de prijzenpagina is alleen voor beheerders
    assert "keukenhulp heeft geen toegang" in maak_taak(db, "Tellen", "", "preset:voorraad_tellen", None, [_id(db, "keukenhulp")], True, "admin")[1]
    assert maak_taak(db, "Tellen", "", "preset:voorraad_tellen", None, [_id(db, "bakker")], True, "admin")[1] is None


def test_toegang_volgt_dezelfde_regels_als_de_site():
    assert endpoint_toegankelijk("producten_prijzen", "beheerder", "")
    assert not endpoint_toegankelijk("producten_prijzen", "vrijwilliger", "voorraad")
    assert endpoint_toegankelijk("tellen", "vrijwilliger", "voorraad") and not endpoint_toegankelijk("tellen", "vrijwilliger", "keuken")
    assert endpoint_toegankelijk("dashboard", "vrijwilliger", "")


def test_de_beheerpagina_en_een_taak_toevoegen_via_het_formulier(ingelogde_client, app, db):
    _, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    tekst = ingelogde_client.get("/taken").data.decode()
    assert "Nieuwe taak" in tekst and "Prijzenlijst nalopen" in tekst and "bakker" in tekst

    resp = ingelogde_client.post(
        "/taken/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client), "soort": "preset:product_toevoegen", "titel": "Nieuwe Bozu toevoegen",
            "omschrijving": "Smaak Mango", "voor_wie": "@admin", "wie_rondt_af": "een",
        },
        follow_redirects=True,
    )
    assert "Taak toegevoegd" in resp.data.decode() and "Nieuwe Bozu toevoegen" in resp.data.decode()
    rij = db.execute("SELECT * FROM taken").fetchone()
    assert (rij["titel"], rij["soort"], rij["iedereen"], rij["aangemaakt_door"]) == ("Nieuwe Bozu toevoegen", "preset:product_toevoegen", 0, "admin")


def test_een_fout_bij_het_toevoegen_wordt_getoond(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/taken/nieuw", data={"csrf_token": _csrf(ingelogde_client), "soort": "eigen", "titel": "Zonder mensen"}, follow_redirects=True
    )
    assert "Tag minstens één persoon" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM taken").fetchone()[0] == 0


# ---------- In 'Wat moet er nu?' ----------


def test_de_taak_staat_alleen_bij_de_gekozen_mensen(ingelogde_client, app, db):
    klant, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    _taak(db, "Voorraad tellen voor het weekend", soort="preset:voorraad_tellen", ids=[bakker], omschrijving="Ook de kelder")
    assert "Voorraad tellen voor het weekend" in _dashboard(klant) and "Ook de kelder" in _dashboard(klant)
    assert "Voorraad tellen voor het weekend" not in _dashboard(ingelogde_client)  # de beheerder staat er niet bij


def test_de_andere_mensen_en_de_deadline_staan_erbij_en_te_laat_is_urgent(ingelogde_client, app, db):
    klant, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    gisteren = (date.today() - timedelta(days=1)).isoformat()
    _taak(db, "Tellen", soort="preset:voorraad_tellen", ids=[ADMIN, bakker], deadline=gisteren)
    tekst = _dashboard(klant)
    assert "Samen met admin" in tekst and "(te laat)" in tekst
    assert re.search(r'class="taak taak-urgent taak-eigen"', tekst)
    from helpers.status import bouw_taken

    assert bouw_taken(db, "vrijwilliger", "voorraad", bakker)[0]["titel"] == "Tellen"  # dringend: bovenaan


def test_de_beheerder_krijgt_een_knop_om_een_taak_toe_te_voegen(ingelogde_client, app, db):
    assert 'href="/taken"' in _dashboard(ingelogde_client)
    klant, _ = _vrijwilliger(app, db)
    assert "Taak toevoegen" not in _dashboard(klant)


def test_de_taak_leidt_naar_zijn_pagina(ingelogde_client, db):
    taak_id = _taak(db, soort="preset:prijzen")
    assert f'href="/taken/{taak_id}/openen"' in _dashboard(ingelogde_client)
    resp = ingelogde_client.get(f"/taken/{taak_id}/openen")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/producten/prijzen")


def test_een_taak_van_een_ander_kun_je_niet_openen(app, db):
    klant, _ = _vrijwilliger(app, db)
    taak_id = _taak(db, ids=[ADMIN])
    resp = klant.get(f"/taken/{taak_id}/openen", follow_redirects=True)
    assert "staat niet (meer) open voor jou" in resp.data.decode()


# ---------- De vraag 'Taak afgerond?' ----------


def test_na_het_opslaan_van_de_prijzen_vraagt_de_site_of_de_taak_klaar_is(ingelogde_client, db):
    taak_id = _taak(db, "Prijzenlijst nalopen", soort="preset:prijzen")
    resp = ingelogde_client.post("/producten/prijzen", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    tekst = resp.data.decode()
    assert "Taak &ldquo;Prijzenlijst nalopen&rdquo; afgerond?" in tekst
    assert f'action="/taken/{taak_id}/afronden"' in tekst and "Ja, afgerond" in tekst and "Nog niet" in tekst
    # De vraag komt één keer.
    assert "afgerond?" not in ingelogde_client.get("/producten/prijzen").data.decode()


def test_ja_afgerond_sluit_de_taak(ingelogde_client, db):
    taak_id = _taak(db)
    ingelogde_client.post("/producten/prijzen", data={"csrf_token": _csrf(ingelogde_client)})
    resp = ingelogde_client.post(
        f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(ingelogde_client), "terug": "/producten/prijzen"}, follow_redirects=True
    )
    assert 'Taak "Prijzenlijst nalopen" is klaar' in resp.data.decode().replace("&#34;", '"')
    rij = db.execute("SELECT * FROM taken WHERE id = ?", (taak_id,)).fetchone()
    assert rij["afgerond_op"] is not None and rij["afgerond_door"] == "admin"
    assert "Prijzenlijst nalopen" not in _dashboard(ingelogde_client)


def test_nog_niet_laat_de_taak_staan(ingelogde_client, db):
    taak_id = _taak(db)
    ingelogde_client.post(
        f"/taken/{taak_id}/nog-niet", data={"csrf_token": _csrf(ingelogde_client), "terug": "/producten/prijzen"}
    )
    assert db.execute("SELECT afgerond_op FROM taken WHERE id = ?", (taak_id,)).fetchone()[0] is None
    assert "Prijzenlijst nalopen" in _dashboard(ingelogde_client)


def test_een_taak_zonder_pagina_vraagt_het_meteen(ingelogde_client, db):
    taak_id = _taak(db, "Kerstboom ophalen", soort="eigen")
    resp = ingelogde_client.get(f"/taken/{taak_id}/openen", follow_redirects=True)
    assert "Taak &ldquo;Kerstboom ophalen&rdquo; afgerond?" in resp.data.decode()


def test_zonder_taak_geen_vraag(ingelogde_client):
    resp = ingelogde_client.post("/producten/prijzen", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "afgerond?" not in resp.data.decode()


def test_een_ander_opslaan_roept_de_vraag_niet_op(ingelogde_client, db):
    _taak(db, soort="preset:prijzen")
    resp = ingelogde_client.post(
        "/bijzonderheden", data={"csrf_token": _csrf(ingelogde_client), "tekst": "Even een bericht"}, follow_redirects=True
    )
    assert "afgerond?" not in resp.data.decode()


def test_mislukt_het_opslaan_dan_vraagt_de_site_niets(ingelogde_client, db):
    _taak(db, "Tellen", soort="preset:voorraad_tellen")
    resp = ingelogde_client.post("/tellen", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)  # niets ingevuld
    tekst = resp.data.decode()
    assert "Geen aantallen ingevuld" in tekst and "afgerond?" not in tekst


def test_het_werkt_ook_voor_andere_dingen_zoals_een_nieuw_product(ingelogde_client, db):
    _taak(db, "Nieuw product toevoegen", soort="preset:product_toevoegen")
    resp = ingelogde_client.post(
        "/producten/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client), "naam": "Mango Bozu", "categorie": "Bier", "eenheid": "Blik",
            "voorraad": "0", "min_voorraad": "0", "bestel_hoeveelheid": "0", "verkoopprijs": "3.50",
        },
        follow_redirects=True,
    )
    assert "Taak &ldquo;Nieuw product toevoegen&rdquo; afgerond?" in resp.data.decode()


def test_het_werkt_ook_voor_een_pagina_uit_het_menu(ingelogde_client, db):
    _taak(db, "Producten nalopen", soort="pagina:producten_lijst")  # alle opslaan-acties van Producten tellen mee
    resp = ingelogde_client.post("/producten/bulk-bewerken", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "Taak &ldquo;Producten nalopen&rdquo; afgerond?" in resp.data.decode()


def test_meerdere_taken_voor_dezelfde_actie_staan_samen_in_een_pop_up(ingelogde_client, db):
    _taak(db, "Eerste taak", soort="preset:prijzen")
    _taak(db, "Tweede taak", soort="preset:prijzen")
    tekst = ingelogde_client.post("/producten/prijzen", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True).data.decode()
    assert "Eerste taak" in tekst and "Tweede taak" in tekst and tekst.count("Ja, afgerond") == 2


# ---------- Wie rondt af ----------


def test_iedereen_moet_het_zelf_afronden(app, db):
    klant, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    taak_id = _taak(db, "Tellen", soort="preset:voorraad_tellen", ids=[ADMIN, bakker], iedereen=True)

    eerste = rond_af(db, taak_id, ADMIN, "admin")
    assert eerste["klaar"] is False
    assert db.execute("SELECT afgerond_op FROM taken WHERE id = ?", (taak_id,)).fetchone()[0] is None
    assert [t["id"] for t in taken_voor_gebruiker(db, ADMIN)] == []  # voor admin is het klaar
    assert [t["id"] for t in taken_voor_gebruiker(db, bakker)] == [taak_id]  # bakker moet nog

    tweede = rond_af(db, taak_id, bakker, "bakker")
    assert tweede["klaar"] is True
    assert db.execute("SELECT afgerond_door FROM taken WHERE id = ?", (taak_id,)).fetchone()[0] == "bakker"


def test_een_van_hen_is_genoeg(app, db):
    _, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    taak_id = _taak(db, "Tellen", soort="preset:voorraad_tellen", ids=[ADMIN, bakker], iedereen=False)
    assert rond_af(db, taak_id, ADMIN, "admin")["klaar"] is True
    assert taken_voor_gebruiker(db, bakker) == []  # staat ook bij de ander niet meer open


def test_het_bericht_zegt_wie_het_nog_moet_doen(ingelogde_client, app, db):
    _, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    taak_id = _taak(db, "Tellen", soort="preset:voorraad_tellen", ids=[ADMIN, bakker])
    resp = ingelogde_client.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "voor jou afgerond. Nog te doen door: bakker" in resp.data.decode().replace("&#34;", '"')


def test_alleen_een_toegewezen_persoon_kan_afronden_en_alleen_een_beheerder_voor_iedereen(app, db):
    klant, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    taak_id = _taak(db, "Tellen", soort="preset:voorraad_tellen", ids=[ADMIN])
    resp = klant.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(klant)}, follow_redirects=True)
    assert "staat niet (meer) open voor jou" in resp.data.decode()
    voor_iedereen = klant.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(klant), "voor_iedereen": "1"}, follow_redirects=True)
    assert "staat niet (meer) open voor jou" in voor_iedereen.data.decode()
    assert db.execute("SELECT afgerond_op FROM taken WHERE id = ?", (taak_id,)).fetchone()[0] is None


def test_de_beheerder_kan_een_taak_voor_iedereen_afronden(ingelogde_client, app, db):
    _, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    taak_id = _taak(db, "Tellen", soort="preset:voorraad_tellen", ids=[ADMIN, bakker])
    ingelogde_client.post(f"/taken/{taak_id}/afronden", data={"csrf_token": _csrf(ingelogde_client), "voor_iedereen": "1"})
    assert db.execute("SELECT afgerond_op FROM taken WHERE id = ?", (taak_id,)).fetchone()[0] is not None
    assert taken_voor_gebruiker(db, bakker) == []


def test_terug_gaat_alleen_naar_een_pagina_op_de_site(ingelogde_client, db):
    taak_id = _taak(db)
    for onveilig in ("//evil.example/x", "https://evil.example", "\\\\evil"):
        resp = ingelogde_client.post(f"/taken/{taak_id}/nog-niet", data={"csrf_token": _csrf(ingelogde_client), "terug": onveilig})
        assert resp.headers["Location"].endswith("/") and "evil" not in resp.headers["Location"]


# ---------- Beheren ----------


def test_een_taak_verwijderen(ingelogde_client, db):
    taak_id = _taak(db)
    resp = ingelogde_client.post(f"/taken/{taak_id}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "Taak verwijderd" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM taken").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM taak_toewijzingen").fetchone()[0] == 0


def test_een_verwijderd_account_laat_de_taak_netjes_achter(app, db):
    _, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    taak_id = _taak(db, "Tellen", soort="preset:voorraad_tellen", ids=[ADMIN, bakker])
    db.execute("DELETE FROM gebruikers WHERE id = ?", (bakker,))
    db.commit()
    assert db.execute("SELECT COUNT(*) FROM taak_toewijzingen WHERE taak_id = ?", (taak_id,)).fetchone()[0] == 1
    assert rond_af(db, taak_id, ADMIN, "admin")["klaar"] is True  # de enige die nog over is


def test_de_beheerpagina_toont_wie_het_al_heeft_gedaan(ingelogde_client, app, db):
    _, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    taak_id = _taak(db, "Tellen", soort="preset:voorraad_tellen", ids=[ADMIN, bakker])
    rond_af(db, taak_id, ADMIN, "admin")
    tekst = ingelogde_client.get("/taken").data.decode()
    assert "Openstaande taken" in tekst and "&#10003; @admin" in tekst and "Iedereen moet het doen" in tekst
    rond_af(db, taak_id, bakker, "bakker")
    tekst = ingelogde_client.get("/taken").data.decode()
    assert "Recent afgerond" in tekst and "Er staan geen eigen taken open" in tekst


def test_vrijwilligers_kunnen_geen_taken_beheren(app, db):
    klant, _ = _vrijwilliger(app, db)
    for pad in ("/taken",):
        assert "alleen voor beheerders" in klant.get(pad, follow_redirects=True).data.decode()
    for pad in ("/taken/nieuw", "/taken/1/verwijderen"):
        assert "alleen voor beheerders" in klant.post(pad, data={"csrf_token": _csrf(klant)}, follow_redirects=True).data.decode()


def test_taken_staat_in_het_menu_van_de_beheerder_maar_niet_van_een_vrijwilliger(ingelogde_client, app, db):
    assert re.search(r'href="/taken"[^>]*>\s*Taken', ingelogde_client.get("/producten").data.decode())
    klant, _ = _vrijwilliger(app, db)
    assert not re.search(r'href="/taken"[^>]*>\s*Taken', klant.get("/").data.decode())


def test_vraag_kandidaten_kijkt_alleen_naar_taken_van_die_persoon(app, db):
    _, bakker = _vrijwilliger(app, db, "bakker", "voorraad")
    _taak(db, "Alleen admin", soort="preset:prijzen", ids=[ADMIN])
    assert [t["titel"] for t in vraag_kandidaten(db, ADMIN, "producten_prijzen")] == ["Alleen admin"]
    assert vraag_kandidaten(db, bakker, "producten_prijzen") == []
    assert vraag_kandidaten(db, ADMIN, "tellen") == []


def test_het_handterminal_scherm_toont_de_vraag_ook(ingelogde_client, db):
    taak_id = _taak(db, "Kerstboom ophalen", soort="eigen")
    ingelogde_client.get("/weergave/pda")
    ingelogde_client.get(f"/taken/{taak_id}/openen")
    tekst = ingelogde_client.get("/").data.decode()
    assert "pda-kop-menuknop" in tekst and 'class="app-zijbalk"' not in tekst  # echt de handterminal-weergave
    assert "Kerstboom ophalen" in tekst and "afgerond?" in tekst


# ---------- Mensen taggen met een @ ----------


def _nieuwe_taak_via_formulier(client, **velden):
    data = {"csrf_token": _csrf(client), "soort": "eigen", "titel": "Kerstboom ophalen", "voor_wie": "@admin"}
    data.update(velden)
    return client.post("/taken/nieuw", data=data, follow_redirects=True)


def _mensen(db):
    return sorted(
        r[0] for r in db.execute("SELECT g.naam FROM taak_toewijzingen tz JOIN gebruikers g ON g.id = tz.gebruiker_id")
    )


def test_het_formulier_heeft_een_veld_om_mensen_te_taggen(ingelogde_client, app, db):
    _vrijwilliger(app, db, "bakker", "voorraad")
    tekst = ingelogde_client.get("/taken").data.decode()
    assert 'name="voor_wie"' in tekst and "data-tag-autocomplete" in tekst
    assert 'id="gebruikersnamen-data"' in tekst and "bakker" in tekst and "admin" in tekst  # de namen voor de aanvuller
    assert 'type="checkbox" name="gebruiker"' not in tekst


def test_getagde_mensen_krijgen_de_taak(ingelogde_client, app, db):
    _vrijwilliger(app, db, "bakker", "voorraad")
    resp = _nieuwe_taak_via_formulier(ingelogde_client, soort="preset:voorraad_tellen", titel="Tellen", voor_wie="@admin @bakker")
    assert "Taak toegevoegd voor admin, bakker" in resp.data.decode()
    assert _mensen(db) == ["admin", "bakker"]


def test_tags_zijn_niet_hoofdlettergevoelig_en_dubbele_tags_tellen_een_keer(ingelogde_client, app, db):
    _vrijwilliger(app, db, "bakker", "voorraad")
    _nieuwe_taak_via_formulier(ingelogde_client, soort="preset:voorraad_tellen", voor_wie="@BAKKER, @bakker en @Admin")
    assert _mensen(db) == ["admin", "bakker"]


def test_een_onbekend_account_taggen_geeft_een_foutmelding_en_maakt_niets(ingelogde_client, db):
    resp = _nieuwe_taak_via_formulier(ingelogde_client, voor_wie="@admin @nietbestaand")
    assert "Dit account ken ik niet: @nietbestaand" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM taken").fetchone()[0] == 0


def test_een_geblokkeerd_account_kun_je_niet_taggen(ingelogde_client, app, db):
    _vrijwilliger(app, db, "bakker", "voorraad")
    db.execute("UPDATE gebruikers SET actief = 0 WHERE naam = 'bakker'")
    db.commit()
    resp = _nieuwe_taak_via_formulier(ingelogde_client, voor_wie="@bakker")
    assert "Dit account ken ik niet: @bakker" in resp.data.decode()


def test_zonder_tag_geen_taak(ingelogde_client, db):
    resp = _nieuwe_taak_via_formulier(ingelogde_client, voor_wie="gewoon een naam")
    assert "Tag minstens één persoon met een @" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM taken").fetchone()[0] == 0


def test_een_tag_in_de_naam_of_toelichting_telt_ook_mee(ingelogde_client, app, db):
    _vrijwilliger(app, db, "bakker", "voorraad")
    _nieuwe_taak_via_formulier(
        ingelogde_client, soort="preset:voorraad_tellen", titel="Tellen samen met @bakker", voor_wie="@admin",
        omschrijving="Mail je bevindingen naar info@club.nl",
    )  # het e-mailadres is geen tag en geeft dus ook geen fout
    assert _mensen(db) == ["admin", "bakker"]


def test_iemand_zonder_toegang_taggen_zegt_waarom(ingelogde_client, app, db):
    _vrijwilliger(app, db, "bakker", "voorraad")
    resp = _nieuwe_taak_via_formulier(ingelogde_client, soort="preset:prijzen", titel="Prijzen", voor_wie="@admin @bakker")
    assert "bakker heeft geen toegang tot" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM taken").fetchone()[0] == 0


def test_getagde_mensen_met_een_mailadres_krijgen_een_mail(ingelogde_client, app, db, monkeypatch):
    _vrijwilliger(app, db, "bakker", "voorraad")
    _vrijwilliger(app, db, "keukenhulp", "voorraad")
    db.execute("UPDATE gebruikers SET email = 'bakker@example.com' WHERE naam = 'bakker'")
    db.execute("UPDATE gebruikers SET email = 'admin@example.com' WHERE naam = 'admin'")  # de maker zelf: geen mail
    db.commit()  # keukenhulp heeft geen e-mailadres
    verstuurd = []
    monkeypatch.setattr(mail, "stuur_mail", lambda onderwerp, tekst, naar=None, **kw: verstuurd.append((naar, onderwerp, tekst)))

    _nieuwe_taak_via_formulier(
        ingelogde_client, soort="preset:voorraad_tellen", titel="Tellen voor het weekend", voor_wie="@admin @bakker @keukenhulp",
        omschrijving="Ook de kelder", deadline="2026-12-24",
    )

    assert [v[0] for v in verstuurd] == ["bakker@example.com"]
    _, onderwerp, tekst = verstuurd[0]
    assert onderwerp == "Je bent getagd op een taak: Tellen voor het weekend"
    assert "admin heeft je getagd" in tekst and "Ook de kelder" in tekst and "Uiterlijk 24-12-2026" in tekst


def test_een_mislukte_taak_stuurt_geen_mail(ingelogde_client, app, db, monkeypatch):
    _vrijwilliger(app, db, "bakker", "voorraad")
    db.execute("UPDATE gebruikers SET email = 'bakker@example.com' WHERE naam = 'bakker'")
    db.commit()
    verstuurd = []
    monkeypatch.setattr(mail, "stuur_mail", lambda *a, **kw: verstuurd.append(a))
    _nieuwe_taak_via_formulier(ingelogde_client, titel=" ", voor_wie="@bakker")
    assert verstuurd == []


def test_de_aanvuller_voor_tags_staat_in_de_gedeelde_javascript_en_het_prikbord_gebruikt_hem_nog(ingelogde_client, app):
    from pathlib import Path

    js = (Path(app.root_path) / "static" / "gedeeld.js").read_text()
    assert "data-tag-autocomplete" in js and "gebruikersnamen-data" in js
    prikbord = ingelogde_client.get("/bijzonderheden").data.decode()
    assert 'id="gebruikersnamen-data"' in prikbord and "data-tag-autocomplete" in prikbord
    assert "var gebruikersnamenEl" not in prikbord  # het script zit niet meer dubbel in de pagina
