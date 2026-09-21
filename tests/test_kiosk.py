import io
import json
import re
from datetime import date, timedelta

from conftest import stel_csrf_token_in as _csrf
from helpers import voeg_maanden_toe
from test_secties_rechten import _login, _maak_vrijwilliger

from app import bereken_club_van_20_status

_KLEINE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _voeg_product_toe(db, naam, categorie="Bier", prijs=2.0, toon_op_kiosk=0, actief=1):
    db.execute(
        """INSERT INTO producten (naam, categorie, eenheid, voorraad, min_voorraad,
               bestel_hoeveelheid, verkoopprijs, actief, toon_op_kiosk)
           VALUES (?, ?, 'stuks', 0, 0, 0, ?, ?, ?)""",
        (naam, categorie, prijs, actief, toon_op_kiosk),
    )
    db.commit()
    return db.execute("SELECT id FROM producten WHERE naam = ?", (naam,)).fetchone()["id"]


def _voeg_sponsor_toe(db, titel, actief=1, sjabloon="titel_tekst_groot", volgorde=0, duur=8):
    db.execute(
        """INSERT INTO kiosk_sponsoren
               (sjabloon, titel, tekst, weergave_duur_seconden, volgorde, actief, aangemaakt_op)
           VALUES (?, ?, 'Bedankt voor de steun!', ?, ?, ?, '2026-01-01 10:00')""",
        (sjabloon, titel, duur, volgorde, actief),
    )
    db.commit()


def _voeg_wedstrijd_toe(db, datum, omschrijving="1e - Test", thuis=1):
    db.execute(
        "INSERT INTO wedstrijden (team, datum, omschrijving, thuis) VALUES ('1e', ?, ?, ?)",
        (datum, omschrijving, thuis),
    )
    db.commit()


def _voeg_actie_toe(db, product_id, tekst="Happy hour!", actief=1):
    db.execute(
        "INSERT INTO kiosk_acties (product_id, tekst, actief, aangemaakt_op) VALUES (?, ?, ?, '2026-01-01 10:00')",
        (product_id, tekst, actief),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM kiosk_acties WHERE product_id = ?", (product_id,)
    ).fetchone()["id"]


def _voeg_sjabloon_custom_toe(db, naam, elementen=None, achtergrond_kleur="#0f1f4d"):
    db.execute(
        """INSERT INTO kiosk_sjablonen_custom
               (naam, achtergrond_kleur, overlay_donker, elementen, aangemaakt_op)
           VALUES (?, ?, 1, ?, '2026-01-01 10:00')""",
        (naam, achtergrond_kleur, json.dumps(elementen or [])),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM kiosk_sjablonen_custom WHERE naam = ?", (naam,)
    ).fetchone()["id"]


def _voeg_lid_toe(db, naam, status="actief", startdatum="2026-01-01", einddatum="2027-01-01", extra_groot=0):
    db.execute(
        """INSERT INTO club_van_20_leden
               (naam, status, startdatum, einddatum, extra_groot, aangemaakt_op)
           VALUES (?, ?, ?, ?, ?, '2026-01-01 10:00')""",
        (naam, status, startdatum, einddatum, extra_groot),
    )
    db.commit()
    return db.execute("SELECT id FROM club_van_20_leden WHERE naam = ?", (naam,)).fetchone()["id"]


# ---------- Onderdeel 1: Prijzenscherm ----------


def test_prijzenscherm_is_publiek_en_toont_alleen_gekozen_producten(client, db):
    _voeg_product_toe(db, "Getoond Biertje", toon_op_kiosk=1)
    _voeg_product_toe(db, "Verborgen Biertje", toon_op_kiosk=0)

    resp = client.get("/kiosk/prijzen")

    assert resp.status_code == 200
    assert b"Getoond Biertje" in resp.data
    assert b"Verborgen Biertje" not in resp.data


def test_prijzenscherm_instellingen_vereist_login(client, db):
    resp = client.get("/kiosk/prijzen/instellingen")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_prijzenscherm_instellingen_bulk_toggle_werkt(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Nieuw Op Kiosk", toon_op_kiosk=0)

    resp = ingelogde_client.post(
        "/kiosk/prijzen/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), f"toon_{product_id}": "on"},
    )
    assert resp.status_code == 302

    rij = db.execute("SELECT toon_op_kiosk FROM producten WHERE id = ?", (product_id,)).fetchone()
    assert rij["toon_op_kiosk"] == 1

    scherm = ingelogde_client.get("/kiosk/prijzen")
    assert b"Nieuw Op Kiosk" in scherm.data


def test_product_formulier_slaat_kiosk_vlaggen_op(ingelogde_client, db):
    """toon_op_kiosk en kiosk_uitverkocht zijn ook los per product te zetten
    op het gewone productformulier, naast de bulk-schermen hierboven."""
    product_id = _voeg_product_toe(db, "Via Formulier", toon_op_kiosk=0)
    product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()

    resp = ingelogde_client.post(
        f"/producten/{product_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": product["naam"],
            "categorie": product["categorie"],
            "eenheid": product["eenheid"],
            "voorraad": product["voorraad"],
            "min_voorraad": product["min_voorraad"],
            "bestel_hoeveelheid": product["bestel_hoeveelheid"],
            "verkoopprijs": product["verkoopprijs"],
            "besteleenheid_factor": 1,
            "actief": "on",
            "toon_op_kiosk": "on",
            "kiosk_uitverkocht": "on",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302

    bijgewerkt = db.execute(
        "SELECT toon_op_kiosk, kiosk_uitverkocht FROM producten WHERE id = ?", (product_id,)
    ).fetchone()
    assert bijgewerkt["toon_op_kiosk"] == 1
    assert bijgewerkt["kiosk_uitverkocht"] == 1


def test_product_formulier_slaat_prijsopties_op(ingelogde_client, db):
    """Losse porties uit 1 product (bijv. pitcher/glas uit een fust) zijn op
    het productformulier te beheren via de parallelle optie_naam/optie_prijs-
    velden (zie prijsopties-lijst in product_form.html)."""
    product_id = _voeg_product_toe(db, "Fust Jupiler", prijs=80.0, toon_op_kiosk=1)
    product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()

    resp = ingelogde_client.post(
        f"/producten/{product_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": product["naam"],
            "categorie": product["categorie"],
            "eenheid": product["eenheid"],
            "voorraad": product["voorraad"],
            "min_voorraad": product["min_voorraad"],
            "bestel_hoeveelheid": product["bestel_hoeveelheid"],
            "verkoopprijs": product["verkoopprijs"],
            "besteleenheid_factor": 1,
            "actief": "on",
            "toon_op_kiosk": "on",
            "optie_naam": ["Jupiler pitcher", "Jupiler glas"],
            "optie_prijs": ["12.00", "2.00"],
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302

    opties = db.execute(
        "SELECT naam, prijs FROM product_prijsopties WHERE product_id = ? ORDER BY volgorde",
        (product_id,),
    ).fetchall()
    assert [dict(o) for o in opties] == [
        {"naam": "Jupiler pitcher", "prijs": 12.0},
        {"naam": "Jupiler glas", "prijs": 2.0},
    ]


def test_product_formulier_slaat_kiosk_categorie_override_op(ingelogde_client, db):
    """kiosk_categorie is een optionele override, alleen voor de indeling op
    het prijzenscherm (bijv. een fust in categorie 'Telling' onder 'Bier'
    tonen) -- de echte categorie blijft ongemoeid."""
    product_id = _voeg_product_toe(db, "Testfust Hertog Jan", categorie="Telling", toon_op_kiosk=1)
    product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()

    resp = ingelogde_client.post(
        f"/producten/{product_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": product["naam"],
            "categorie": product["categorie"],
            "eenheid": product["eenheid"],
            "voorraad": product["voorraad"],
            "min_voorraad": product["min_voorraad"],
            "bestel_hoeveelheid": product["bestel_hoeveelheid"],
            "verkoopprijs": product["verkoopprijs"],
            "besteleenheid_factor": 1,
            "actief": "on",
            "toon_op_kiosk": "on",
            "kiosk_categorie": "Bier",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302

    bijgewerkt = db.execute(
        "SELECT categorie, kiosk_categorie FROM producten WHERE id = ?", (product_id,)
    ).fetchone()
    assert bijgewerkt["categorie"] == "Telling"
    assert bijgewerkt["kiosk_categorie"] == "Bier"


def test_prijzenscherm_groepeert_op_kiosk_categorie_override(client, db):
    """Prijsopties van een fust in 'Telling' met een kiosk_categorie-override
    verschijnen onder de overrule-categorie i.p.v. onder 'Telling'."""
    product_id = _voeg_product_toe(db, "Testfust Radler", categorie="Telling", toon_op_kiosk=1)
    db.execute("UPDATE producten SET kiosk_categorie = 'Bier' WHERE id = ?", (product_id,))
    db.execute(
        """INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES
               (?, 'Radler pitcher', 12.0, 0), (?, 'Radler glas', 2.0, 1)""",
        (product_id, product_id),
    )
    _voeg_product_toe(db, "Radler Fles", categorie="Bier", prijs=2.2, toon_op_kiosk=1)
    db.commit()

    resp = client.get("/kiosk/prijzen")
    tekst = resp.data.decode()

    assert resp.status_code == 200
    assert "Telling" not in tekst
    bier_index = tekst.index(">Bier<")
    assert bier_index < tekst.index("Radler glas") < tekst.index("Radler pitcher")


def test_product_formulier_negeert_lege_prijsoptie_regels(ingelogde_client, db):
    """Een leeggelaten extra rij in de bouwer (bijv. na op '+ Optie
    toevoegen' te klikken zonder 'm in te vullen) mag geen kale optie
    opleveren."""
    product_id = _voeg_product_toe(db, "Fust Radler", toon_op_kiosk=1)
    product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()

    ingelogde_client.post(
        f"/producten/{product_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": product["naam"],
            "categorie": product["categorie"],
            "eenheid": product["eenheid"],
            "voorraad": product["voorraad"],
            "min_voorraad": product["min_voorraad"],
            "bestel_hoeveelheid": product["bestel_hoeveelheid"],
            "verkoopprijs": product["verkoopprijs"],
            "besteleenheid_factor": 1,
            "actief": "on",
            "optie_naam": ["Radler glas", ""],
            "optie_prijs": ["2.00", "0.00"],
        },
        content_type="multipart/form-data",
    )

    opties = db.execute(
        "SELECT naam FROM product_prijsopties WHERE product_id = ?", (product_id,)
    ).fetchall()
    assert [o["naam"] for o in opties] == ["Radler glas"]


def test_product_formulier_kan_prijsopties_weer_verwijderen(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Fust Test", toon_op_kiosk=1)
    product = db.execute("SELECT * FROM producten WHERE id = ?", (product_id,)).fetchone()
    db.execute(
        "INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES (?, 'Glas', 2.0, 0)",
        (product_id,),
    )
    db.commit()

    ingelogde_client.post(
        f"/producten/{product_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": product["naam"],
            "categorie": product["categorie"],
            "eenheid": product["eenheid"],
            "voorraad": product["voorraad"],
            "min_voorraad": product["min_voorraad"],
            "bestel_hoeveelheid": product["bestel_hoeveelheid"],
            "verkoopprijs": product["verkoopprijs"],
            "besteleenheid_factor": 1,
            "actief": "on",
        },
        content_type="multipart/form-data",
    )

    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM product_prijsopties WHERE product_id = ?", (product_id,)
    ).fetchone()["n"]
    assert aantal == 0


def test_product_toon_op_kiosk_wisselen_via_ajax(ingelogde_client, db):
    """Het losse schuifje op de Kiosk-pagina in de PDA-weergave -- 1 tik,
    direct opgeslagen, geen 'Alles opslaan' nodig."""
    product_id = _voeg_product_toe(db, "Los Te Wisselen", toon_op_kiosk=0)

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/toon",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["toon_op_kiosk"] == 1
    assert "staat nu op het prijzenscherm" in data["melding"]

    rij = db.execute("SELECT toon_op_kiosk FROM producten WHERE id = ?", (product_id,)).fetchone()
    assert rij["toon_op_kiosk"] == 1

    # Nog een keer tikken zet 'm weer uit.
    resp2 = ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/toon",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp2.get_json()["toon_op_kiosk"] == 0


def test_product_toon_op_kiosk_wisselen_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_kiosk", "voorraad")
    _login(client, "vrijwilliger_kiosk")
    product_id = _voeg_product_toe(db, "Vrijwilliger Mag Niet", toon_op_kiosk=0)

    resp = client.post(
        f"/kiosk/prijzen/product/{product_id}/toon",
        data={"csrf_token": _csrf(client)},
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT toon_op_kiosk FROM producten WHERE id = ?", (product_id,)).fetchone()
    assert rij["toon_op_kiosk"] == 0


def test_kiosk_pagina_toont_kaartjes_in_pda_weergave(ingelogde_client, db):
    _voeg_product_toe(db, "PDA Kaartje Product", toon_op_kiosk=1)
    ingelogde_client.get("/weergave/pda")

    resp = ingelogde_client.get("/kiosk/prijzen/instellingen")

    assert resp.status_code == 200
    assert b"pda-kaartje" in resp.data
    assert b"PDA Kaartje Product" in resp.data
    assert b"Alles opslaan" not in resp.data


def test_kiosk_tegel_op_pda_start_alleen_voor_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_start", "voorraad")
    _login(client, "vrijwilliger_start")
    client.get("/weergave/pda")

    resp = client.get("/")
    assert b"Kiosk" not in resp.data


def test_product_uitverkocht_wisselen_via_ajax(ingelogde_client, db):
    """De UITVERKOCHT-knop op de Kiosk-pagina in de PDA-weergave."""
    product_id = _voeg_product_toe(db, "Op Is Op", toon_op_kiosk=1)

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["kiosk_uitverkocht"] == 1
    assert "uitverkocht" in data["melding"]

    rij = db.execute(
        "SELECT kiosk_uitverkocht FROM producten WHERE id = ?", (product_id,)
    ).fetchone()
    assert rij["kiosk_uitverkocht"] == 1

    # Nog een keer tikken maakt 'm weer beschikbaar.
    resp2 = ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp2.get_json()["kiosk_uitverkocht"] == 0


def test_product_uitverkocht_wisselen_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_uitverkocht", "voorraad")
    _login(client, "vrijwilliger_uitverkocht")
    product_id = _voeg_product_toe(db, "Vrijwilliger Mag Niet Uitverkopen", toon_op_kiosk=1)

    resp = client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(client)},
    )
    assert resp.status_code == 302
    rij = db.execute(
        "SELECT kiosk_uitverkocht FROM producten WHERE id = ?", (product_id,)
    ).fetchone()
    assert rij["kiosk_uitverkocht"] == 0


def test_prijzenscherm_toont_uitverkocht_duidelijk(client, db):
    product_id = _voeg_product_toe(db, "Bijna Op", toon_op_kiosk=1)
    db.execute("UPDATE producten SET kiosk_uitverkocht = 1 WHERE id = ?", (product_id,))
    db.commit()

    resp = client.get("/kiosk/prijzen")

    assert resp.status_code == 200
    assert b"Bijna Op" in resp.data
    assert b"Uitverkocht" in resp.data
    assert b"prijs-regel--uitverkocht" in resp.data


def test_prijzenscherm_toont_prijsopties_i_p_v_eigen_prijs(client, db):
    """Een fust hoort niet in zijn geheel op de prijslijst -- heeft een
    product prijsopties, dan tonen die losse regels i.p.v. de eigen
    verkoopprijs van het product zelf (zie _prijzen_categorieen)."""
    product_id = _voeg_product_toe(db, "Fust Jupiler", categorie="Bier", prijs=80.0, toon_op_kiosk=1)
    db.execute(
        """INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES
               (?, 'Jupiler pitcher', 12.0, 0), (?, 'Jupiler glas', 2.0, 1)""",
        (product_id, product_id),
    )
    db.commit()

    resp = client.get("/kiosk/prijzen")
    tekst = resp.data.decode()

    assert resp.status_code == 200
    assert "Jupiler pitcher" in tekst
    assert "&euro; 12.00" in tekst
    assert "Jupiler glas" in tekst
    assert "&euro; 2.00" in tekst
    # De naam/prijs van het fust-product zelf mag niet los verschijnen.
    assert "Fust Jupiler<" not in tekst
    assert "&euro; 80.00" not in tekst


def test_uitverkocht_popup_toont_productnaam_niet_portienaam(client, db):
    """De uitverkocht-popup moet het product tonen (bijv. "Jupiler"), niet de
    portienaam van een prijsoptie (bijv. "Klein glas") -- en maar 1x, ook al
    zijn er meerdere uitverkochte porties van hetzelfde product."""
    product_id = _voeg_product_toe(db, "Jupiler", categorie="Bier", toon_op_kiosk=1)
    db.execute(
        """INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES
               (?, 'Klein glas', 2.0, 0), (?, 'Groot glas', 3.0, 1)""",
        (product_id, product_id),
    )
    db.execute("UPDATE producten SET kiosk_uitverkocht = 1 WHERE id = ?", (product_id,))
    db.commit()

    resp = client.get("/kiosk/prijzen")
    tekst = resp.data.decode()

    match = re.search(r"bekendeUitverkocht = (\[.*?\]);", tekst)
    assert match is not None
    uitverkocht_namen = json.loads(match.group(1))
    assert uitverkocht_namen == ["Jupiler"]


def test_prijzenscherm_prijsopties_tonen_uitverkocht_als_fust_leeg_is(client, db):
    """Wordt het hele fust als uitverkocht gemarkeerd, dan geldt dat voor elke
    portie die eruit getapt wordt -- er is geen los voorraadniveau per
    pitcher/glas."""
    product_id = _voeg_product_toe(db, "Fust Leeg", toon_op_kiosk=1)
    db.execute(
        "INSERT INTO product_prijsopties (product_id, naam, prijs, volgorde) VALUES (?, 'Glas', 2.0, 0)",
        (product_id,),
    )
    db.execute("UPDATE producten SET kiosk_uitverkocht = 1 WHERE id = ?", (product_id,))
    db.commit()

    resp = client.get("/kiosk/prijzen")
    tekst = resp.data.decode()

    assert "Glas" in tekst
    assert "Uitverkocht" in tekst
    assert "&euro; 2.00" not in tekst


def test_prijzenscherm_versie_verandert_bij_uitverkocht_wisselen(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Versie Product", toon_op_kiosk=1)

    versie_voor = ingelogde_client.get("/kiosk/prijzen/versie").get_json()["versie"]
    ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    versie_na = ingelogde_client.get("/kiosk/prijzen/versie").get_json()["versie"]

    assert versie_voor != versie_na


def test_prijzen_versie_geeft_uitverkocht_namenlijst_voor_de_pop_up(ingelogde_client, db):
    """De grote UITVERKOCHT-pop-up op het prijzenscherm vergelijkt deze
    lijst tussen twee polls om een NIEUW uitverkocht product te detecteren."""
    product_id = _voeg_product_toe(db, "Pop-up Product", toon_op_kiosk=1)

    voor = ingelogde_client.get("/kiosk/prijzen/versie").get_json()
    assert voor["uitverkocht"] == []

    ingelogde_client.post(
        f"/kiosk/prijzen/product/{product_id}/uitverkocht",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    na = ingelogde_client.get("/kiosk/prijzen/versie").get_json()
    assert na["uitverkocht"] == ["Pop-up Product"]


def test_kiosk_pda_pagina_toont_uitverkocht_knop(ingelogde_client, db):
    _voeg_product_toe(db, "Kaartje Met Knop", toon_op_kiosk=1)
    ingelogde_client.get("/weergave/pda")

    resp = ingelogde_client.get("/kiosk/prijzen/instellingen")

    assert resp.status_code == 200
    assert b"Uitverkocht" in resp.data
    assert b"btn-uitverkocht" in resp.data


# ---------- Acties (onderdeel van het prijzenscherm) ----------


def test_actie_aanmaken_bewerken_en_verwijderen(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Actieproduct", prijs=3.5)

    resp = ingelogde_client.post(
        "/kiosk/prijzen/acties/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": str(product_id),
            "tekst": "Happy hour: 1 euro korting!",
            "actief": "on",
        },
    )
    assert resp.status_code == 302
    actie = db.execute(
        "SELECT * FROM kiosk_acties WHERE product_id = ?", (product_id,)
    ).fetchone()
    assert actie is not None
    assert actie["tekst"] == "Happy hour: 1 euro korting!"
    assert actie["actief"] == 1

    lijst = ingelogde_client.get("/kiosk/prijzen/acties")
    assert b"Actieproduct" in lijst.data
    assert b"Happy hour" in lijst.data

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/acties/{actie['id']}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "product_id": str(product_id),
            "tekst": "Nu nog goedkoper!",
        },
    )
    assert resp.status_code == 302
    bijgewerkt = db.execute(
        "SELECT * FROM kiosk_acties WHERE id = ?", (actie["id"],)
    ).fetchone()
    assert bijgewerkt["tekst"] == "Nu nog goedkoper!"
    assert bijgewerkt["actief"] == 0  # checkbox niet meegestuurd -> uit

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/acties/{actie['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM kiosk_acties WHERE id = ?", (actie["id"],)).fetchone() is None


def test_actie_aanmaken_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_actie", "voorraad")
    _login(client, "vrijwilliger_actie")
    product_id = _voeg_product_toe(db, "Beschermd Actieproduct")

    resp = client.post(
        "/kiosk/prijzen/acties/nieuw",
        data={"csrf_token": _csrf(client), "product_id": str(product_id), "actief": "on"},
    )
    assert resp.status_code == 302
    assert db.execute(
        "SELECT * FROM kiosk_acties WHERE product_id = ?", (product_id,)
    ).fetchone() is None


def test_actie_toon_wisselen_via_ajax(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "Toggle Actieproduct")
    actie_id = _voeg_actie_toe(db, product_id, actief=0)

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/acties/{actie_id}/toon",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["actief"] == 1
    rij = db.execute("SELECT actief FROM kiosk_acties WHERE id = ?", (actie_id,)).fetchone()
    assert rij["actief"] == 1


def test_actie_toon_wisselen_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_actietoggle", "voorraad")
    product_id = _voeg_product_toe(db, "Beschermd Toggle Product")
    actie_id = _voeg_actie_toe(db, product_id, actief=0)
    _login(client, "vrijwilliger_actietoggle")

    resp = client.post(
        f"/kiosk/prijzen/acties/{actie_id}/toon",
        data={"csrf_token": _csrf(client)},
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT actief FROM kiosk_acties WHERE id = ?", (actie_id,)).fetchone()
    assert rij["actief"] == 0


def test_prijzenscherm_bevat_actiegegevens_voor_de_pop_up(client, db):
    product_id = _voeg_product_toe(db, "Zichtbaar Actieproduct", prijs=4.25)
    _voeg_actie_toe(db, product_id, tekst="Nu in de aanbieding!", actief=1)
    _voeg_product_toe(db, "Verborgen Actieproduct")  # geen actie -> mag niet meekomen

    resp = client.get("/kiosk/prijzen")

    assert resp.status_code == 200
    assert b"Zichtbaar Actieproduct" in resp.data
    assert b"Nu in de aanbieding" in resp.data


def test_kiosk_pda_pagina_toont_acties_sectie(ingelogde_client, db):
    product_id = _voeg_product_toe(db, "PDA Actieproduct")
    _voeg_actie_toe(db, product_id, tekst="PDA actietekst", actief=1)
    ingelogde_client.get("/weergave/pda")

    resp = ingelogde_client.get("/kiosk/prijzen/instellingen")

    assert resp.status_code == 200
    assert b"PDA Actieproduct" in resp.data
    assert b"PDA actietekst" in resp.data


# ---------- Onderdeel 2: Sponsoren/leden beheren ----------


def test_sponsor_aanmaken_vereist_kantine_tv_sectie(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_kiosk", "voorraad")
    _login(client, "vrijwilliger_kiosk")

    resp = client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data={
            "csrf_token": _csrf(client),
            "sjabloon": "titel_tekst_groot",
            "titel": "Stiekeme Sponsor",
        },
    )
    assert resp.status_code == 302
    volg_resp = client.get(resp.headers["Location"])
    assert b"niet beschikbaar voor jouw account" in volg_resp.data
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_sponsoren").fetchone()["n"] == 0


def test_sponsor_aanmaken_bewerken_en_verwijderen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "sjabloon": "titel_tekst_groot",
            "titel": "Testsponsor",
            "tekst": "Bedankt voor de steun",
            "weergave_duur_seconden": "6",
            "volgorde": "2",
            "actief": "on",
        },
    )
    assert resp.status_code == 302
    sponsor = db.execute("SELECT * FROM kiosk_sponsoren WHERE titel = 'Testsponsor'").fetchone()
    assert sponsor is not None
    assert sponsor["weergave_duur_seconden"] == 6

    bewerk_pagina = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{sponsor['id']}/bewerken")
    assert bewerk_pagina.status_code == 200
    assert b"Testsponsor" in bewerk_pagina.data

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{sponsor['id']}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "sjabloon": "titel_tekst_groot",
            "titel": "Testsponsor Bijgewerkt",
            "weergave_duur_seconden": "6",
            "volgorde": "2",
        },
    )
    assert resp.status_code == 302
    bijgewerkt = db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (sponsor["id"],)).fetchone()
    assert bijgewerkt["titel"] == "Testsponsor Bijgewerkt"
    assert bijgewerkt["actief"] == 0  # checkbox niet meegestuurd -> uit

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{sponsor['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM kiosk_sponsoren WHERE id = ?", (sponsor["id"],)).fetchone() is None


def test_sponsor_formulier_toont_mededeling_sjabloon_en_voorbeeldtekst(ingelogde_client, db):
    resp = ingelogde_client.get("/kiosk/sponsoren-leden/sponsoren/nieuw")
    assert resp.status_code == 200
    assert b"Mededeling" in resp.data
    assert b"mededeling_groot" in resp.data
    # Voorbeeldtekst zit als JSON in de placeholder-script, voor alle sjablonen.
    assert b"Kantinedienst gezocht" in resp.data


def test_kantine_scherm_toont_mededeling_label(client, db):
    _voeg_sponsor_toe(db, "Kantinedienst gezocht!", sjabloon="mededeling_groot")

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"Kantinedienst gezocht!" in resp.data
    assert b"mededeling-label" in resp.data
    assert b">Mededeling<" in resp.data


def test_lid_toevoegen_en_verwijderen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Jan Jansen"},
    )
    assert resp.status_code == 302
    lid = db.execute("SELECT * FROM club_van_20_leden WHERE naam = 'Jan Jansen'").fetchone()
    assert lid is not None

    overzicht = ingelogde_client.get("/kiosk/sponsoren-leden")
    assert b"Jan Jansen" in overzicht.data

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/leden/{lid['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid["id"],)).fetchone() is None


def test_lid_nieuw_krijgt_automatisch_start_en_einddatum(ingelogde_client, db):
    """Startdatum = vandaag, einddatum = vandaag + de ingestelde standaard
    looptijd (12 maanden, zie kiosk_scherm_instellingen)."""
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Piet Pietersen"},
    )
    assert resp.status_code == 302

    lid = db.execute(
        "SELECT * FROM club_van_20_leden WHERE naam = 'Piet Pietersen'"
    ).fetchone()
    vandaag = date.today().isoformat()
    assert lid["status"] == "actief"
    assert lid["startdatum"] == vandaag
    assert lid["einddatum"] == voeg_maanden_toe(vandaag, 12)


def test_lid_status_wisselen_via_ajax(ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Nog Niet Betaald"},
    )
    lid = db.execute(
        "SELECT * FROM club_van_20_leden WHERE naam = 'Nog Niet Betaald'"
    ).fetchone()

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/leden/{lid['id']}/status",
        data={"csrf_token": _csrf(ingelogde_client), "status": "niet_betaald"},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["status"] == "niet_betaald"

    rij = db.execute(
        "SELECT status FROM club_van_20_leden WHERE id = ?", (lid["id"],)
    ).fetchone()
    assert rij["status"] == "niet_betaald"


def test_lid_status_wisselen_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_lidstatus", "voorraad")
    db.execute(
        "INSERT INTO club_van_20_leden (naam, status, startdatum, einddatum, aangemaakt_op) "
        "VALUES ('Test Lid', 'actief', '2026-01-01', '2027-01-01', '2026-01-01 10:00')"
    )
    db.commit()
    lid_id = db.execute(
        "SELECT id FROM club_van_20_leden WHERE naam = 'Test Lid'"
    ).fetchone()["id"]
    _login(client, "vrijwilliger_lidstatus")

    resp = client.post(
        f"/kiosk/sponsoren-leden/leden/{lid_id}/status",
        data={"csrf_token": _csrf(client), "status": "inactief"},
    )
    assert resp.status_code == 302
    rij = db.execute("SELECT status FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
    assert rij["status"] == "actief"


def test_club_van_20_status_telt_alleen_actieve_leden_die_binnenkort_aflopen(db):
    over_10_dagen = (date.today() + timedelta(days=10)).isoformat()
    over_1_jaar = (date.today() + timedelta(days=365)).isoformat()
    _voeg_lid_toe(db, "Loopt Binnenkort Af", status="actief", einddatum=over_10_dagen)
    _voeg_lid_toe(db, "Loopt Nog Lang Niet Af", status="actief", einddatum=over_1_jaar)
    _voeg_lid_toe(db, "Al Gestopt (inactief)", status="inactief", einddatum=over_10_dagen)
    _voeg_lid_toe(db, "Niet Betaald Telt Niet Mee", status="niet_betaald", einddatum=over_10_dagen)

    status = bereken_club_van_20_status(db)

    assert status["aantal"] == 1
    assert status["leden"][0]["naam"] == "Loopt Binnenkort Af"
    assert status["ok"] is False


def test_club_van_20_status_is_ok_zonder_aflopende_leden(db):
    over_1_jaar = (date.today() + timedelta(days=365)).isoformat()
    _voeg_lid_toe(db, "Ruim Op Tijd", status="actief", einddatum=over_1_jaar)

    status = bereken_club_van_20_status(db)

    assert status["aantal"] == 0
    assert status["ok"] is True


def test_dashboard_toont_club_van_20_tegel_alleen_voor_beheerder(client, db):
    over_10_dagen = (date.today() + timedelta(days=10)).isoformat()
    _voeg_lid_toe(db, "Bijna Verlopen", status="actief", einddatum=over_10_dagen)

    csrf = _csrf(client)
    client.post("/login", data={"naam": "admin", "wachtwoord": "kantine123", "csrf_token": csrf})
    resp = client.get("/")
    assert b"Club van 20" in resp.data
    assert b"Bijna Verlopen" in resp.data
    client.get("/logout")

    _maak_vrijwilliger(db, "vrijwilliger_dashboard", "voorraad")
    _login(client, "vrijwilliger_dashboard")
    resp = client.get("/")
    assert b"Club van 20" not in resp.data


def test_kantine_scherm_verbergt_inactieve_leden_maar_toont_niet_betaald(client, db):
    db.executemany(
        "INSERT INTO club_van_20_leden (naam, status, startdatum, einddatum, aangemaakt_op) "
        "VALUES (?, ?, '2026-01-01', '2027-01-01', '2026-01-01 10:00')",
        [
            ("Actief Lid", "actief"),
            ("Inactief Lid", "inactief"),
            ("Wanbetaler", "niet_betaald"),
        ],
    )
    db.commit()

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()

    assert resp.status_code == 200
    assert "Actief Lid" in tekst
    assert "Inactief Lid" not in tekst
    # Niet betaald blijft zichtbaar (als herinnering om te betalen), maar
    # dan met de lichtrode waarschuwingsklasse i.p.v. de gewone chip-stijl.
    assert "Wanbetaler" in tekst
    positie = tekst.find("Wanbetaler")
    fragment = tekst[max(0, positie - 200) : positie]
    assert "naam-chip--niet-betaald" in fragment


def test_sponsoren_leden_pagina_toont_status_en_looptijd(ingelogde_client, db):
    ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Weergave Test"},
    )

    resp = ingelogde_client.get("/kiosk/sponsoren-leden")

    assert resp.status_code == 200
    assert b"lid-status-select" in resp.data
    assert b"lid-naam" in resp.data
    assert b"Niet betaald" in resp.data


def test_lid_bewerken_wijzigt_naam_looptijd_en_extra_groot(ingelogde_client, db):
    lid_id = _voeg_lid_toe(db, "Oud Lid", startdatum="2020-01-01", einddatum="2021-01-01")

    formulier = ingelogde_client.get(f"/kiosk/sponsoren-leden/leden/{lid_id}/bewerken")
    assert formulier.status_code == 200
    assert b"Oud Lid" in formulier.data

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/leden/{lid_id}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Nieuwe Naam",
            "status": "inactief",
            "startdatum": "2022-06-15",
            "einddatum": "2028-06-15",
            "extra_groot": "on",
        },
    )
    assert resp.status_code == 302

    lid = db.execute("SELECT * FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
    assert lid["naam"] == "Nieuwe Naam"
    assert lid["status"] == "inactief"
    assert lid["startdatum"] == "2022-06-15"
    assert lid["einddatum"] == "2028-06-15"
    assert lid["extra_groot"] == 1


def test_lid_bewerken_vereist_beheerder(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_lidbewerken", "voorraad")
    lid_id = _voeg_lid_toe(db, "Beschermd Lid")
    _login(client, "vrijwilliger_lidbewerken")

    resp = client.post(
        f"/kiosk/sponsoren-leden/leden/{lid_id}/bewerken",
        data={
            "csrf_token": _csrf(client),
            "naam": "Gehackte Naam",
            "status": "actief",
            "startdatum": "2026-01-01",
            "einddatum": "2027-01-01",
        },
    )
    assert resp.status_code == 302
    lid = db.execute("SELECT naam FROM club_van_20_leden WHERE id = ?", (lid_id,)).fetchone()
    assert lid["naam"] == "Beschermd Lid"


def test_jaren_lid_berekent_volledige_jaren():
    from helpers import bereken_jaren_lid

    vaste_vandaag = date(2026, 6, 15)
    assert bereken_jaren_lid(None, vandaag=vaste_vandaag) == 0
    assert bereken_jaren_lid("2026-06-15", vandaag=vaste_vandaag) == 0
    # Verjaardag van de startdatum (10 juni) is dit jaar al geweest -> vol 10 jaar.
    assert bereken_jaren_lid("2016-06-10", vandaag=vaste_vandaag) == 10
    # Verjaardag (20 juni) moet dit jaar nog komen -> nog geen 5 volle jaren.
    assert bereken_jaren_lid("2021-06-20", vandaag=vaste_vandaag) == 4


def test_kantine_scherm_toont_sterren_per_jaar_lid(client, db):
    tien_jaar_geleden = date(date.today().year - 10, 1, 1).isoformat()
    _voeg_lid_toe(db, "Trouw Lid", startdatum=tien_jaar_geleden, einddatum="2099-01-01")

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert "★" * 10 in resp.data.decode("utf-8")
    assert b"Trouw Lid" in resp.data


def test_kantine_scherm_toont_extra_grote_naam(client, db):
    _voeg_lid_toe(db, "Grote Naam", extra_groot=1)
    _voeg_lid_toe(db, "Gewone Naam", extra_groot=0)

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # De extra-grote klasse hoort bij het kaartje van "Grote Naam", niet bij "Gewone Naam".
    groot_klasse = 'class="naam-chip naam-chip--groot"'
    assert groot_klasse in html
    groot_positie = html.index(groot_klasse)
    assert "Grote Naam" in html[groot_positie : groot_positie + 200]
    assert "Gewone Naam" not in html[groot_positie : groot_positie + 200]


# ---------- Onderdeel 3: Kantine scherm ----------


def test_scherm_instellingen_opslaan(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            # toon_sponsoren bewust niet meegestuurd -> uit
            "sponsoren_volgorde": "1",
            "toon_club_van_20": "on",
            "club_van_20_volgorde": "1",
            "club_van_20_titel": "Onze Club van 20",
            "club_van_20_namen_per_slide": "2",
            "club_van_20_looptijd_maanden": "6",
            # toon_wedstrijden bewust niet meegestuurd -> uit
            "wedstrijden_volgorde": "3",
        },
    )
    assert resp.status_code == 302

    instellingen = db.execute("SELECT * FROM kiosk_scherm_instellingen WHERE id = 1").fetchone()
    assert instellingen["toon_sponsoren"] == 0
    assert instellingen["toon_club_van_20"] == 1
    assert instellingen["club_van_20_titel"] == "Onze Club van 20"
    assert instellingen["club_van_20_namen_per_slide"] == 2
    assert instellingen["club_van_20_looptijd_maanden"] == 6
    assert instellingen["toon_wedstrijden"] == 0

    # Een nieuw lid gebruikt meteen de zojuist opgeslagen looptijd.
    ingelogde_client.post(
        "/kiosk/sponsoren-leden/leden/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "naam": "Looptijd Test"},
    )
    lid = db.execute(
        "SELECT * FROM club_van_20_leden WHERE naam = 'Looptijd Test'"
    ).fetchone()
    vandaag = date.today().isoformat()
    assert lid["startdatum"] == vandaag
    assert lid["einddatum"] == voeg_maanden_toe(vandaag, 6)


def test_kantine_scherm_is_publiek_en_toont_alleen_actieve_sponsoren(client, db):
    _voeg_sponsor_toe(db, "Actieve Sponsor", actief=1)
    _voeg_sponsor_toe(db, "Inactieve Sponsor", actief=0)

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"Actieve Sponsor" in resp.data
    assert b"Inactieve Sponsor" not in resp.data


def test_kantine_scherm_toont_vast_clubbeeldmerk_op_elke_dia(client, db):
    """Los van welke dia er toevallig getoond wordt (sponsor, mededeling,
    Club van 20, wedstrijden) staat er altijd hetzelfde vaste clubbadge --
    zit dus buiten de per-dia-rendering, niet per sjabloon herhaald."""
    _voeg_sponsor_toe(db, "Willekeurige Sponsor")

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"club-badge" in resp.data
    assert b"S.V. BLAUW-GEEL 1915" in resp.data


def test_kantine_scherm_verdeelt_leden_over_meerdere_slides(client, db):
    db.execute(
        "UPDATE kiosk_scherm_instellingen SET club_van_20_namen_per_slide = 2 WHERE id = 1"
    )
    for naam in ["Aad", "Bram", "Cor"]:
        db.execute(
            "INSERT INTO club_van_20_leden (naam, aangemaakt_op) VALUES (?, '2026-01-01 10:00')",
            (naam,),
        )
    db.commit()

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    for naam in ["Aad", "Bram", "Cor"]:
        assert naam.encode() in resp.data
    assert b"1/2" in resp.data
    assert b"2/2" in resp.data


def test_kantine_scherm_verbergt_wedstrijden_blok_zonder_wedstrijden(client, db):
    resp = client.get("/kiosk/scherm")
    assert resp.status_code == 200
    assert b"Komende thuiswedstrijden" not in resp.data


def test_kantine_scherm_toont_wedstrijden_blok_indien_aanwezig(client, db):
    from datetime import date, timedelta

    morgen = (date.today() + timedelta(days=1)).isoformat()
    _voeg_wedstrijd_toe(db, morgen, "1e - Kiosk tegenstander")

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"Komende thuiswedstrijden" in resp.data
    assert b"Kiosk tegenstander" in resp.data
    # Datumbadge (dag/nummer/maand) en de eerstvolgende-markering, zie
    # bereken_komende_thuiswedstrijden (helpers.py) en kiosk_scherm.html.
    assert b"datumbadge" in resp.data
    assert b"wedstrijd-dag--eerstvolgende" in resp.data
    assert b"Eerstvolgende" in resp.data


def test_kantine_scherm_toont_club_van_20_animatie_klassen(client, db):
    _voeg_lid_toe(db, "Animatie Test")

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"animation-delay" in resp.data


def test_kantine_scherm_toont_lege_staat_als_alles_uit_staat(client, db):
    db.execute(
        """UPDATE kiosk_scherm_instellingen
           SET toon_sponsoren = 0, toon_club_van_20 = 0, toon_wedstrijden = 0
           WHERE id = 1"""
    )
    db.commit()

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert "nog niets ingesteld".encode() in resp.data


# ---------- Navigatie (zijbalk i.p.v. het accountmenu) ----------


def test_kiosk_zijbalk_groep_zichtbaar_voor_beheerder(ingelogde_client, db):
    resp = ingelogde_client.get("/")
    assert resp.status_code == 200
    assert b"Kantine-tv" in resp.data


def test_kiosk_zijbalk_groep_verborgen_voor_vrijwilliger(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_zijbalk", "voorraad")
    _login(client, "vrijwilliger_zijbalk")

    resp = client.get("/")

    assert resp.status_code == 200
    assert b"Kantine-tv" not in resp.data


def test_kiosk_route_blijft_beschermd_ook_al_staat_die_nu_in_de_zijbalk(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_kiosk_route", "voorraad")
    _login(client, "vrijwilliger_kiosk_route")

    resp = client.get("/kiosk", follow_redirects=True)

    assert resp.status_code == 200
    assert b"niet beschikbaar voor jouw account" in resp.data


# ---------- Onderdeel 2b: Eigen sjablonen (drag-and-drop bouwer) ----------


def test_sjabloon_aanmaken_bewerken_en_verwijderen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sjablonen/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Testsjabloon",
            "achtergrond_kleur": "#112233",
            "overlay_donker": "on",
            "elementen_json": json.dumps(
                [
                    {
                        "type": "titel",
                        "x": 10,
                        "y": 10,
                        "breedte": 30,
                        "hoogte": 20,
                        "kleur": "#ffffff",
                        "uitlijning": "midden",
                        "lettergrootte": "groot",
                    }
                ]
            ),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    sjabloon = db.execute(
        "SELECT * FROM kiosk_sjablonen_custom WHERE naam = 'Testsjabloon'"
    ).fetchone()
    assert sjabloon is not None
    assert sjabloon["achtergrond_kleur"] == "#112233"
    elementen = json.loads(sjabloon["elementen"])
    assert len(elementen) == 1
    assert elementen[0]["type"] == "titel"
    assert elementen[0]["lettergrootte"] == "groot"

    bewerk_pagina = ingelogde_client.get(
        f"/kiosk/sponsoren-leden/sjablonen/{sjabloon['id']}/bewerken"
    )
    assert bewerk_pagina.status_code == 200
    assert b"Testsjabloon" in bewerk_pagina.data

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sjablonen/{sjabloon['id']}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Testsjabloon Bijgewerkt",
            "achtergrond_kleur": "#445566",
            "elementen_json": "[]",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    bijgewerkt = db.execute(
        "SELECT * FROM kiosk_sjablonen_custom WHERE id = ?", (sjabloon["id"],)
    ).fetchone()
    assert bijgewerkt["naam"] == "Testsjabloon Bijgewerkt"
    assert bijgewerkt["achtergrond_kleur"] == "#445566"
    assert bijgewerkt["overlay_donker"] == 0  # checkbox niet meegestuurd -> uit

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sjablonen/{sjabloon['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert (
        db.execute(
            "SELECT * FROM kiosk_sjablonen_custom WHERE id = ?", (sjabloon["id"],)
        ).fetchone()
        is None
    )


def test_sjabloon_aanmaken_vereist_kantine_tv_sectie(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_sjabloon", "voorraad")
    _login(client, "vrijwilliger_sjabloon")

    resp = client.post(
        "/kiosk/sponsoren-leden/sjablonen/nieuw",
        data={
            "csrf_token": _csrf(client),
            "naam": "Stiekem sjabloon",
            "elementen_json": "[]",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    volg_resp = client.get(resp.headers["Location"])
    assert b"niet beschikbaar voor jouw account" in volg_resp.data
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_sjablonen_custom").fetchone()["n"] == 0


def test_bouwer_pagina_vereist_kantine_tv_sectie(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_bouwer", "voorraad")
    _login(client, "vrijwilliger_bouwer")

    resp = client.get("/kiosk/sponsoren-leden/sjablonen/nieuw")
    assert resp.status_code == 302
    volg_resp = client.get(resp.headers["Location"])
    assert b"niet beschikbaar voor jouw account" in volg_resp.data


def test_sjabloon_verwijderen_zet_gebruikende_sponsor_terug_op_standaard(ingelogde_client, db):
    sjabloon_id = _voeg_sjabloon_custom_toe(db, "Wordt verwijderd")
    db.execute(
        """INSERT INTO kiosk_sponsoren
               (sjabloon, custom_sjabloon_id, titel, weergave_duur_seconden,
                volgorde, actief, aangemaakt_op)
           VALUES ('aangepast', ?, 'Sponsor met eigen sjabloon', 8, 0, 1, '2026-01-01 10:00')""",
        (sjabloon_id,),
    )
    db.commit()
    sponsor = db.execute(
        "SELECT id FROM kiosk_sponsoren WHERE titel = 'Sponsor met eigen sjabloon'"
    ).fetchone()

    resp = ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sjablonen/{sjabloon_id}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert (
        db.execute(
            "SELECT * FROM kiosk_sjablonen_custom WHERE id = ?", (sjabloon_id,)
        ).fetchone()
        is None
    )
    bijgewerkte_sponsor = db.execute(
        "SELECT sjabloon, custom_sjabloon_id FROM kiosk_sponsoren WHERE id = ?",
        (sponsor["id"],),
    ).fetchone()
    assert bijgewerkte_sponsor["sjabloon"] == "afbeelding_volledig"
    assert bijgewerkte_sponsor["custom_sjabloon_id"] is None


def test_sjabloon_elementen_json_valideert_en_klemt(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sjablonen/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Validatietest",
            "achtergrond_kleur": "geen-geldige-kleur",
            "elementen_json": json.dumps(
                [
                    {"type": "onbekend_type", "x": 5, "y": 5, "breedte": 10, "hoogte": 10},
                    {
                        "type": "titel",
                        "x": 500,
                        "y": -50,
                        "breedte": 30,
                        "hoogte": 20,
                        "kleur": "niet-hex",
                        "uitlijning": "ergens",
                        "lettergrootte": "gigantisch",
                    },
                ]
            ),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    sjabloon = db.execute(
        "SELECT * FROM kiosk_sjablonen_custom WHERE naam = 'Validatietest'"
    ).fetchone()
    assert sjabloon["achtergrond_kleur"] == "#0f1f4d"  # ongeldige kleur -> standaard
    elementen = json.loads(sjabloon["elementen"])
    assert len(elementen) == 1  # element met onbekend type is overgeslagen
    element = elementen[0]
    assert element["x"] == 100  # geklemd op 100 (was 500)
    assert element["y"] == 0  # geklemd op 0 (was -50)
    assert element["kleur"] == "#ffffff"  # ongeldige kleur -> standaard
    assert element["uitlijning"] == "links"  # onbekende waarde -> standaard
    assert element["lettergrootte"] == "normaal"  # onbekende waarde -> standaard


def test_sjabloon_elementen_json_kapotte_json_geeft_lege_lijst(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sjablonen/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "naam": "Kapotte JSON",
            "elementen_json": "dit is geen json{{{",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    sjabloon = db.execute(
        "SELECT * FROM kiosk_sjablonen_custom WHERE naam = 'Kapotte JSON'"
    ).fetchone()
    assert json.loads(sjabloon["elementen"]) == []


def test_sponsoren_leden_pagina_toont_eigen_sjablonen(ingelogde_client, db):
    _voeg_sjabloon_custom_toe(
        db,
        "Zichtbaar Sjabloon",
        elementen=[
            {
                "type": "titel",
                "x": 0,
                "y": 0,
                "breedte": 10,
                "hoogte": 10,
                "kleur": "#fff",
                "uitlijning": "links",
                "lettergrootte": "normaal",
            }
        ],
    )

    resp = ingelogde_client.get("/kiosk/sponsoren-leden")

    assert resp.status_code == 200
    assert b"Zichtbaar Sjabloon" in resp.data
    assert b"Ongebruikt" in resp.data


def test_kantine_scherm_rendert_eigen_sjabloon_met_sponsorinhoud(client, db):
    sjabloon_id = _voeg_sjabloon_custom_toe(
        db,
        "Canvas sjabloon",
        elementen=[
            {
                "type": "titel",
                "x": 10,
                "y": 10,
                "breedte": 30,
                "hoogte": 15,
                "kleur": "#ffffff",
                "uitlijning": "midden",
                "lettergrootte": "groot",
            },
            {
                "type": "vrije_tekst",
                "x": 10,
                "y": 30,
                "breedte": 30,
                "hoogte": 15,
                "kleur": "#ffff00",
                "uitlijning": "rechts",
                "lettergrootte": "klein",
                "inhoud": "Vast label",
            },
        ],
    )
    db.execute(
        """INSERT INTO kiosk_sponsoren
               (sjabloon, custom_sjabloon_id, titel, weergave_duur_seconden,
                volgorde, actief, aangemaakt_op)
           VALUES ('aangepast', ?, 'Canvas Sponsor Titel', 8, 0, 1, '2026-01-01 10:00')""",
        (sjabloon_id,),
    )
    db.commit()

    resp = client.get("/kiosk/scherm")
    tekst = resp.data.decode()

    assert resp.status_code == 200
    assert "slide-aangepast" in tekst
    assert "Canvas Sponsor Titel" in tekst  # titel-element toont de sponsor's eigen titel
    assert "Vast label" in tekst  # vrije_tekst-element toont zijn eigen vaste inhoud
    # 'midden'/'rechts' moeten omgezet zijn naar geldige CSS text-align-waarden,
    # nooit als het Nederlandse woord zelf in de CSS belanden.
    assert "text-align:center;" in tekst
    assert "text-align:right;" in tekst
    assert "text-align:midden" not in tekst
    assert "text-align:rechts" not in tekst


def test_kantine_scherm_slaat_sponsor_over_als_gekoppeld_sjabloon_verwijderd_is(client, db):
    """Randgeval: een sponsor met een custom_sjabloon_id die niet meer bestaat
    (kiosk_sjabloon_verwijderen ruimt dit normaal zelf op bij sponsoren die
    het sjabloon gebruiken -- dit test de defensieve fallback ernaast, voor
    het geval de data toch inconsistent raakt)."""
    db.execute(
        """INSERT INTO kiosk_sponsoren
               (sjabloon, custom_sjabloon_id, titel, weergave_duur_seconden,
                volgorde, actief, aangemaakt_op)
           VALUES ('aangepast', 9999, 'Wees sponsor', 8, 0, 1, '2026-01-01 10:00')"""
    )
    db.commit()

    resp = client.get("/kiosk/scherm")

    assert resp.status_code == 200
    assert b"Wees sponsor" not in resp.data
    assert b"nog niets ingesteld" in resp.data


def test_sponsor_slaat_overgang_tekst_grootte_en_achtergrond_op(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "sjabloon": "mededeling_groot",
            "titel": "Kantinedienst gezocht",
            "overgang": "inzoomen",
            "tekst_grootte": "xl",
            "achtergrond_afbeelding": (io.BytesIO(_KLEINE_PNG), "achtergrond.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    sponsor = db.execute(
        "SELECT * FROM kiosk_sponsoren WHERE titel = 'Kantinedienst gezocht'"
    ).fetchone()
    assert sponsor["overgang"] == "inzoomen"
    assert sponsor["tekst_grootte"] == "xl"
    assert sponsor["achtergrond_afbeelding"] is not None

    resp = ingelogde_client.get("/kiosk/scherm")
    tekst = resp.data.decode()
    assert "overgang-inzoomen" in tekst
    assert "tekst-xl" in tekst
    assert "mededeling-achtergrond-img" in tekst


def test_sponsor_achtergrond_afbeelding_alleen_voor_mededeling(ingelogde_client, db):
    """Een achtergrondfoto is alleen bedoeld voor de mededeling-lay-out --
    bij een ander sjabloon wordt een geuploade achtergrondfoto genegeerd,
    zodat 'm niet als 'spook'-achtergrond blijft hangen als iemand later
    terugschakelt naar mededeling."""
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "sjabloon": "titel_tekst_groot",
            "titel": "Gewone sponsor",
            "achtergrond_afbeelding": (io.BytesIO(_KLEINE_PNG), "achtergrond.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    sponsor = db.execute(
        "SELECT * FROM kiosk_sponsoren WHERE titel = 'Gewone sponsor'"
    ).fetchone()
    assert sponsor["achtergrond_afbeelding"] is None


def test_scherm_instellingen_accepteert_ajax_en_geeft_json(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/scherm/instellingen",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "toon_sponsoren": "on",
            "sponsoren_volgorde": "1",
            "toon_club_van_20": "on",
            "club_van_20_volgorde": "2",
            "club_van_20_titel": "Club van 20",
            "club_van_20_namen_per_slide": "40",
            "club_van_20_looptijd_maanden": "12",
            "toon_wedstrijden": "on",
            "wedstrijden_volgorde": "3",
        },
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True


def test_scherm_instellingen_get_stuurt_door_naar_dias_pagina(ingelogde_client, db):
    """Er is geen losse instellingenpagina meer -- de instellingen staan nu
    op dezelfde pagina als de dia's zelf (kiosk_sponsoren_leden), dus een
    oude bladwijzer naar /kiosk/scherm/instellingen stuurt gewoon door."""
    resp = ingelogde_client.get("/kiosk/scherm/instellingen")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/kiosk/sponsoren-leden")


def test_dias_pagina_toont_diashow_instellingen_en_live_voorbeeld(ingelogde_client, db):
    resp = ingelogde_client.get("/kiosk/sponsoren-leden")
    assert resp.status_code == 200
    assert b'id="scherm-preview"' in resp.data
    assert b"js-ajax-form" in resp.data
    assert b"Diashow instellen" in resp.data


def test_kiosk_schermen_staan_zichzelf_toe_te_framen(ingelogde_client, db):
    """X-Frame-Options staat standaard op DENY (zie beveiligingsheaders in
    app.py) -- de 3 kiosk-schermen zijn de bewuste uitzondering (SAMEORIGIN),
    puur zodat de instellingenpagina en de Kiosk-hub 'm in een
    live-voorbeeld-iframe kunnen tonen. Andere pagina's mogen niet
    ge-framed kunnen worden."""
    assert ingelogde_client.get("/kiosk/scherm").headers["X-Frame-Options"] == "SAMEORIGIN"
    assert ingelogde_client.get("/kiosk/prijzen").headers["X-Frame-Options"] == "SAMEORIGIN"
    assert ingelogde_client.get("/kiosk/tv").headers["X-Frame-Options"] == "SAMEORIGIN"

    assert ingelogde_client.get("/").headers["X-Frame-Options"] == "DENY"


# ---------- Bardienst (onderdeel van het prijzenscherm) ----------


def _voeg_bardienst_toe(db, datum, start_tijd="15:00", eind_tijd="17:00", namen="Luuk & Femke"):
    db.execute(
        """INSERT INTO kiosk_bardiensten (datum, start_tijd, eind_tijd, namen, aangemaakt_op)
           VALUES (?, ?, ?, ?, '2026-01-01 10:00')""",
        (datum, start_tijd, eind_tijd, namen),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM kiosk_bardiensten WHERE datum = ? AND start_tijd = ?", (datum, start_tijd)
    ).fetchone()["id"]


def test_bardienst_aanmaken_bewerken_en_verwijderen(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/prijzen/bardienst/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "datum": "2026-09-20",
            "start_tijd": "15:00",
            "eind_tijd": "17:00",
            "namen": "Luuk & Femke",
        },
    )
    assert resp.status_code == 302
    bardienst = db.execute(
        "SELECT * FROM kiosk_bardiensten WHERE namen = 'Luuk & Femke'"
    ).fetchone()
    assert bardienst is not None
    assert bardienst["datum"] == "2026-09-20"
    assert bardienst["start_tijd"] == "15:00"
    assert bardienst["eind_tijd"] == "17:00"

    overzicht = ingelogde_client.get("/kiosk/prijzen/bardienst")
    assert overzicht.status_code == 200
    assert b"Luuk &amp; Femke" in overzicht.data

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/bardienst/{bardienst['id']}/bewerken",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "datum": "2026-09-20",
            "start_tijd": "17:00",
            "eind_tijd": "19:00",
            "namen": "Bart & Peter",
        },
    )
    assert resp.status_code == 302
    bijgewerkt = db.execute(
        "SELECT * FROM kiosk_bardiensten WHERE id = ?", (bardienst["id"],)
    ).fetchone()
    assert bijgewerkt["namen"] == "Bart & Peter"
    assert bijgewerkt["start_tijd"] == "17:00"

    resp = ingelogde_client.post(
        f"/kiosk/prijzen/bardienst/{bardienst['id']}/verwijderen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    assert resp.status_code == 302
    assert (
        db.execute("SELECT * FROM kiosk_bardiensten WHERE id = ?", (bardienst["id"],)).fetchone()
        is None
    )


def test_bardienst_aanmaken_vereist_kantine_tv_sectie(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_bardienst", "voorraad")
    _login(client, "vrijwilliger_bardienst")

    resp = client.post(
        "/kiosk/prijzen/bardienst/nieuw",
        data={
            "csrf_token": _csrf(client),
            "datum": "2026-09-20",
            "start_tijd": "15:00",
            "eind_tijd": "17:00",
            "namen": "Stiekeme Bardienst",
        },
    )
    assert resp.status_code == 302
    volg_resp = client.get(resp.headers["Location"])
    assert b"niet beschikbaar voor jouw account" in volg_resp.data
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_bardiensten").fetchone()["n"] == 0


def test_bardienst_zonder_namen_geeft_foutmelding(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/prijzen/bardienst/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "datum": "2026-09-20",
            "start_tijd": "15:00",
            "eind_tijd": "17:00",
            "namen": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Vul in wie er bardienst heeft" in resp.data
    assert db.execute("SELECT COUNT(*) AS n FROM kiosk_bardiensten").fetchone()["n"] == 0


def test_prijzenscherm_stuurt_gisteren_vandaag_en_morgen_mee(client, db):
    """De server haalt bewust een venster van 3 dagen op (i.p.v. alleen
    exact vandaag): de server draait op UTC terwijl het scherm in
    Europe/Amsterdam staat, dus 'vandaag' kan rond middernacht een paar uur
    verschillen. Welke dienst nu precies actief is, bepaalt de JS zelf aan
    de hand van datum+klok van het scherm (zie test_kiosk_prijzen* hieronder
    voor een dienst die middernacht overschrijdt)."""
    gisteren = (date.today() - timedelta(days=1)).isoformat()
    vandaag = date.today().isoformat()
    morgen = (date.today() + timedelta(days=1)).isoformat()
    eergisteren = (date.today() - timedelta(days=2)).isoformat()
    _voeg_bardienst_toe(db, gisteren, "22:00", "23:59", "Gister Team")
    _voeg_bardienst_toe(db, vandaag, "15:00", "17:00", "Luuk & Femke")
    _voeg_bardienst_toe(db, morgen, "15:00", "17:00", "Morgen Team")
    _voeg_bardienst_toe(db, eergisteren, "15:00", "17:00", "Te Ver Terug")

    resp = client.get("/kiosk/prijzen")
    tekst = resp.data.decode()

    assert resp.status_code == 200
    # De namen zitten in de JSON voor de JS (bardiensten_vandaag|tojson),
    # waar Jinja '&' veiligheidshalve als & escaped -- vandaar niet op
    # de letterlijke tekens zoeken, maar op de losse woorden.
    assert "Gister Team" in tekst
    assert "Luuk" in tekst and "Femke" in tekst
    assert "Morgen Team" in tekst
    assert "Te Ver Terug" not in tekst
    assert "bardienst-balk" in tekst


def test_prijzenscherm_versie_verandert_bij_bardienst_wijziging(client, db):
    resp1 = client.get("/kiosk/prijzen/versie")
    versie1 = resp1.get_json()["versie"]

    _voeg_bardienst_toe(db, date.today().isoformat())

    resp2 = client.get("/kiosk/prijzen/versie")
    versie2 = resp2.get_json()["versie"]
    assert versie1 != versie2


# ---------- Gedeeld scherm (/kiosk/tv) ----------


def test_kiosk_tv_toont_standaard_de_prijzenlijst(client, db):
    resp = client.get("/kiosk/tv")
    assert resp.status_code == 200
    assert b"Prijslijst" in resp.data


def test_kiosk_tv_wisselen_schakelt_tussen_prijzen_en_dias(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/tv/wisselen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    instellingen = db.execute(
        "SELECT actief_tv_scherm FROM kiosk_scherm_instellingen WHERE id = 1"
    ).fetchone()
    assert instellingen["actief_tv_scherm"] == "dias"

    tv_resp = ingelogde_client.get("/kiosk/tv")
    assert b"Prijslijst" not in tv_resp.data

    ingelogde_client.post("/kiosk/tv/wisselen", data={"csrf_token": _csrf(ingelogde_client)})
    instellingen = db.execute(
        "SELECT actief_tv_scherm FROM kiosk_scherm_instellingen WHERE id = 1"
    ).fetchone()
    assert instellingen["actief_tv_scherm"] == "prijzen"


def test_kiosk_tv_wisselen_via_ajax_geeft_json_met_modus(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/kiosk/tv/wisselen",
        data={"csrf_token": _csrf(ingelogde_client)},
        headers={"X-Requested-With": "fetch"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["modus"] == "dias"


def test_kiosk_tv_wisselen_vereist_kantine_tv_sectie(client, db):
    _maak_vrijwilliger(db, "vrijwilliger_tv", "voorraad")
    _login(client, "vrijwilliger_tv")

    resp = client.post("/kiosk/tv/wisselen", data={"csrf_token": _csrf(client)})
    assert resp.status_code == 302
    volg_resp = client.get(resp.headers["Location"])
    assert b"niet beschikbaar voor jouw account" in volg_resp.data
    instellingen = db.execute(
        "SELECT actief_tv_scherm FROM kiosk_scherm_instellingen WHERE id = 1"
    ).fetchone()
    assert instellingen["actief_tv_scherm"] == "prijzen"


def test_kiosk_tv_versie_verandert_bij_wisselen(ingelogde_client, db):
    resp1 = ingelogde_client.get("/kiosk/tv/versie")
    versie1 = resp1.get_json()["versie"]

    ingelogde_client.post("/kiosk/tv/wisselen", data={"csrf_token": _csrf(ingelogde_client)})

    resp2 = ingelogde_client.get("/kiosk/tv/versie")
    versie2 = resp2.get_json()["versie"]
    assert versie1 != versie2


def test_hub_pagina_toont_drie_schermen_en_instellen_snelkoppelingen(ingelogde_client, db):
    resp = ingelogde_client.get("/kiosk")
    assert resp.status_code == 200
    assert b"Scherm 1" in resp.data
    assert b"Scherm 2" in resp.data
    assert b"Scherm 3" in resp.data
    assert b"Wisselscherm" in resp.data
    assert b"Bardienst" in resp.data
    # De beknopte "Instellen"-snelkoppelingen naar Acties/Sponsoren/Club van 20.
    assert b'href="/kiosk/prijzen/acties"' in resp.data
    assert b"#dias-tabel" in resp.data
    assert b"#club-van-20" in resp.data
