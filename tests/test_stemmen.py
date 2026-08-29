import io

from conftest import stel_csrf_token_in as _csrf

from app import STEM_AFBEELDINGEN_MAP, stemming_is_open


def _maak_stemvraag(client, titel="Welk fust voor het weizen?", opties=("Fust A", "Fust B", "Fust C"), extra=None):
    data = {"csrf_token": _csrf(client), "titel": titel}
    for i, tekst in enumerate(opties, start=1):
        data[f"optie{i}"] = tekst
    if extra:
        data.update(extra)
    resp = client.post("/stemmen/nieuw", data=data, follow_redirects=False)
    assert resp.status_code == 302
    return int(resp.headers["Location"].rsplit("/", 1)[-1])


def _stem(client, stemvraag_id, optie_id, naam="Jan Jansen", opmerking=None):
    client.get(f"/stem/{stemvraag_id}")  # zorgt voor het stem_kiezer-cookie
    data = {"csrf_token": _csrf(client), "optie_id": optie_id, "naam": naam}
    if opmerking is not None:
        data["opmerking"] = opmerking
    return client.post(f"/stem/{stemvraag_id}", data=data)


def test_stemvraag_aanmaken(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["titel"] == "Welk fust voor het weizen?"
    assert vraag["actief"] == 1
    opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    assert [o["tekst"] for o in opties] == ["Fust A", "Fust B", "Fust C"]


def test_stemvraag_met_minder_dan_2_opties_wordt_geweigerd(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/stemmen/nieuw",
        data={"csrf_token": _csrf(ingelogde_client), "titel": "Test", "optie1": "Enige optie"},
    )
    assert resp.status_code == 302
    aantal = db.execute("SELECT COUNT(*) AS n FROM stemvragen").fetchone()["n"]
    assert aantal == 0


def test_lege_opties_worden_genegeerd(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, opties=("Fust A", "", "Fust B", "  "))
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemopties WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 2


def test_tien_opties_kunnen_worden_aangemaakt(ingelogde_client, db):
    opties = tuple(f"Optie {i}" for i in range(1, 11))
    stemvraag_id = _maak_stemvraag(ingelogde_client, opties=opties)
    rijen = db.execute(
        "SELECT tekst FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    assert [r["tekst"] for r in rijen] == list(opties)


def test_elfde_optie_wordt_genegeerd(ingelogde_client, db):
    data = {"csrf_token": _csrf(ingelogde_client), "titel": "Test elf opties"}
    for i in range(1, 12):
        data[f"optie{i}"] = f"Optie {i}"
    resp = ingelogde_client.post("/stemmen/nieuw", data=data, follow_redirects=False)
    stemvraag_id = int(resp.headers["Location"].rsplit("/", 1)[-1])
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemopties WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 10


def test_publieke_pagina_bereikbaar_zonder_extra_login(ingelogde_client, db):
    """De publieke stempagina staat in OPEN_ENDPOINTS -- geen redirect naar
    /login, ongeacht of de bezoeker al ingelogd is."""
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.get(f"/stem/{stemvraag_id}")
    assert resp.status_code == 200
    assert b"Welk fust voor het weizen?" in resp.data


def test_niet_bestaande_stemvraag_geeft_404(client):
    resp = client.get("/stem/99999")
    assert resp.status_code == 404


def test_naam_is_verplicht(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    ingelogde_client.get(f"/stem/{stemvraag_id}")
    resp = ingelogde_client.post(
        f"/stem/{stemvraag_id}",
        data={"csrf_token": _csrf(ingelogde_client), "optie_id": optie["id"], "naam": "  "},
    )
    assert b"Vul je naam in" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 0


def test_stemmen_zet_een_stem_weg_met_naam(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()

    resp = _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Jan Jansen")
    assert resp.status_code == 200
    assert b"Bedankt voor je stem" in resp.data

    stem = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchone()
    assert stem["naam"] == "Jan Jansen"
    assert stem["afgekeurd"] == 0


def test_dubbel_stemmen_via_zelfde_cookie_wordt_geweerd(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Jan Jansen")

    resp = _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Piet Pietersen")
    assert b"al gestemd" in resp.data

    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 1


def test_dubbel_stemmen_op_naam_wordt_geweerd_ook_met_ander_cookie(ingelogde_client, db):
    """De naam-check moet ook een omweg via het wissen van het
    stem_kiezer-cookie afvangen."""
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Jan Jansen")
    ingelogde_client.delete_cookie("stem_kiezer")

    resp = _stem(ingelogde_client, stemvraag_id, optie["id"], naam="jan jansen")  # zelfde naam, andere case
    assert b"al gestemd" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 1


def test_gesloten_stemming_accepteert_geen_nieuwe_stem(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/sluiten", data={"csrf_token": _csrf(ingelogde_client)}
    )

    resp = _stem(ingelogde_client, stemvraag_id, optie["id"])
    assert b"is gesloten" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 0


def test_verwijderen_verwijdert_ook_opties_en_stemmen(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone() is None
    assert (
        db.execute(
            "SELECT COUNT(*) AS n FROM stemopties WHERE stemvraag_id = ?", (stemvraag_id,)
        ).fetchone()["n"]
        == 0
    )


def test_detailpagina_toont_qr_code(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.get(f"/stemmen/{stemvraag_id}")
    assert resp.status_code == 200
    assert b"<svg" in resp.data
    assert f"/stem/{stemvraag_id}".encode() in resp.data


def test_poster_pdf_wordt_gegenereerd(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.get(f"/stemmen/{stemvraag_id}/poster.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_afkeuren_telt_niet_meer_mee_in_uitslag(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Jan Jansen")
    stem = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchone()

    resp = ingelogde_client.post(
        f"/stemmen/stem/{stem['id']}/afkeuren", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    stem = db.execute("SELECT * FROM stemmen WHERE id = ?", (stem["id"],)).fetchone()
    assert stem["afgekeurd"] == 1

    detail = ingelogde_client.get(f"/stemmen/{stemvraag_id}")
    assert b">0 (0%)<" in detail.data or b"0 (0%)" in detail.data


def test_afkeuren_maakt_naam_weer_vrij_om_te_stemmen(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Jan Jansen")
    stem = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchone()
    ingelogde_client.post(
        f"/stemmen/stem/{stem['id']}/afkeuren", data={"csrf_token": _csrf(ingelogde_client)}
    )
    ingelogde_client.delete_cookie("stem_kiezer")

    resp = _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Jan Jansen")
    assert b"Bedankt voor je stem" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 2  # oude (afgekeurde) + nieuwe stem


def test_afkeuren_en_opnieuw_stemmen_vanaf_zelfde_toestel_crasht_niet(ingelogde_client, db):
    """Regressietest voor een crash in productie: dezelfde kiezer_sleutel
    (cookie) botst met de UNIQUE-constraint als iemand na een afkeuring
    opnieuw stemt zonder z'n cookie te wissen. Moet de bestaande (afgekeurde)
    rij bijwerken in plaats van te crashen."""
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    _stem(ingelogde_client, stemvraag_id, opties[0]["id"], naam="Jan Jansen")
    stem = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchone()
    ingelogde_client.post(
        f"/stemmen/stem/{stem['id']}/afkeuren", data={"csrf_token": _csrf(ingelogde_client)}
    )

    resp = _stem(ingelogde_client, stemvraag_id, opties[1]["id"], naam="Jan Jansen")
    assert resp.status_code == 200
    assert b"Bedankt voor je stem" in resp.data

    stemmen = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchall()
    assert len(stemmen) == 1  # bestaande rij bijgewerkt, geen crash of dubbele rij
    assert stemmen[0]["afgekeurd"] == 0
    assert stemmen[0]["stemoptie_id"] == opties[1]["id"]


def test_afbeelding_bij_optie_wordt_opgeslagen(ingelogde_client, db):
    kleine_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    resp = ingelogde_client.post(
        "/stemmen/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "titel": "Met plaatje",
            "optie1": "Fust A",
            "optie2": "Fust B",
            "afbeelding1": (io.BytesIO(kleine_png), "fust_a.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    stemvraag_id = int(resp.headers["Location"].rsplit("/", 1)[-1])
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? AND tekst = 'Fust A'", (stemvraag_id,)
    ).fetchone()
    assert optie["afbeelding"] is not None
    assert optie["afbeelding"].endswith(".png")

    afbeelding_pad = STEM_AFBEELDINGEN_MAP / optie["afbeelding"]
    assert afbeelding_pad.exists()
    afbeelding_pad.unlink()  # niet laten rondslingeren na de test


def test_sluit_op_kan_worden_meegegeven_bij_aanmaken(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/stemmen/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "titel": "Met einddatum",
            "optie1": "Fust A",
            "optie2": "Fust B",
            "sluit_op": "2099-01-01",
        },
    )
    stemvraag_id = int(resp.headers["Location"].rsplit("/", 1)[-1])
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["sluit_op"] == "2099-01-01 23:59"


def test_einddatum_kan_worden_ingesteld_op_bestaande_stemming(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/einddatum",
        data={"csrf_token": _csrf(ingelogde_client), "sluit_op": "2099-06-15"},
    )
    assert resp.status_code == 302
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["sluit_op"] == "2099-06-15 23:59"


def test_einddatum_kan_weer_verwijderd_worden(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/einddatum",
        data={"csrf_token": _csrf(ingelogde_client), "sluit_op": "2099-06-15"},
    )
    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/einddatum",
        data={"csrf_token": _csrf(ingelogde_client), "sluit_op": ""},
    )
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["sluit_op"] is None


def test_stemming_is_open_houdt_rekening_met_einddatum(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert stemming_is_open(vraag) is True

    db.execute("UPDATE stemvragen SET sluit_op = ? WHERE id = ?", ("2000-01-01 23:59", stemvraag_id))
    db.commit()
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert stemming_is_open(vraag) is False

    db.execute("UPDATE stemvragen SET sluit_op = ? WHERE id = ?", ("2099-01-01 23:59", stemvraag_id))
    db.commit()
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert stemming_is_open(vraag) is True


def test_verlopen_stemming_accepteert_geen_nieuwe_stem(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    db.execute("UPDATE stemvragen SET sluit_op = ? WHERE id = ?", ("2000-01-01 23:59", stemvraag_id))
    db.commit()

    resp = _stem(ingelogde_client, stemvraag_id, optie["id"])
    assert b"is gesloten" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 0


def test_publiek_overzicht_toont_open_stemmingen(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, titel="Welke actie voor de zomer?")
    resp = ingelogde_client.get("/stem")
    assert resp.status_code == 200
    assert b"Welke actie voor de zomer?" in resp.data
    assert f"/stem/{stemvraag_id}".encode() in resp.data


def test_publiek_overzicht_verbergt_gesloten_en_verlopen_stemmingen(ingelogde_client, db):
    open_id = _maak_stemvraag(ingelogde_client, titel="Open stemming")
    gesloten_id = _maak_stemvraag(ingelogde_client, titel="Gesloten stemming")
    verlopen_id = _maak_stemvraag(ingelogde_client, titel="Verlopen stemming")
    ingelogde_client.post(
        f"/stemmen/{gesloten_id}/sluiten", data={"csrf_token": _csrf(ingelogde_client)}
    )
    db.execute("UPDATE stemvragen SET sluit_op = ? WHERE id = ?", ("2000-01-01 23:59", verlopen_id))
    db.commit()

    resp = ingelogde_client.get("/stem")
    assert b"Open stemming" in resp.data
    assert b"Gesloten stemming" not in resp.data
    assert b"Verlopen stemming" not in resp.data
    assert open_id  # sanity, id werd gebruikt


def test_publiek_overzicht_zonder_login_bereikbaar(client, db):
    resp = client.get("/stem")
    assert resp.status_code == 200


def test_uitslag_wordt_verborgen_als_toon_uitslag_uit_staat(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)  # geen toon_uitslag meegegeven -> uit
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    resp = _stem(ingelogde_client, stemvraag_id, optie["id"])
    assert b"Bedankt voor je stem" in resp.data
    assert b"stem tot nu toe" not in resp.data and b"stemmen tot nu toe" not in resp.data


def test_uitslag_wordt_getoond_als_toon_uitslag_aan_staat(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, extra={"toon_uitslag": "1"})
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    resp = _stem(ingelogde_client, stemvraag_id, optie["id"])
    assert b"Bedankt voor je stem" in resp.data
    assert b"stem tot nu toe" in resp.data or b"stemmen tot nu toe" in resp.data


def test_opmerkingveld_niet_getoond_zonder_opmerking_toegestaan(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.get(f"/stem/{stemvraag_id}")
    assert b'name="opmerking"' not in resp.data


def test_opmerking_wordt_opgeslagen_als_toegestaan(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, extra={"opmerking_toegestaan": "1"})
    resp = ingelogde_client.get(f"/stem/{stemvraag_id}")
    assert b'name="opmerking"' in resp.data
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], opmerking="Liever kleinere flesjes")
    stem = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchone()
    assert stem["opmerking"] == "Liever kleinere flesjes"


def test_opmerking_wordt_genegeerd_zonder_opmerking_toegestaan(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], opmerking="Dit zou niet opgeslagen moeten worden")
    stem = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchone()
    assert stem["opmerking"] is None


def test_instellingen_kunnen_achteraf_gewijzigd_worden(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "toon_uitslag": "1", "opmerking_toegestaan": "1"},
    )
    assert resp.status_code == 302
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["toon_uitslag"] == 1
    assert vraag["opmerking_toegestaan"] == 1

    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/instellingen",
        data={"csrf_token": _csrf(ingelogde_client)},
    )
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["toon_uitslag"] == 0
    assert vraag["opmerking_toegestaan"] == 0


def test_goedkeuren_telt_weer_mee(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Jan Jansen")
    stem = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchone()
    ingelogde_client.post(
        f"/stemmen/stem/{stem['id']}/afkeuren", data={"csrf_token": _csrf(ingelogde_client)}
    )
    ingelogde_client.post(
        f"/stemmen/stem/{stem['id']}/goedkeuren", data={"csrf_token": _csrf(ingelogde_client)}
    )
    stem = db.execute("SELECT * FROM stemmen WHERE id = ?", (stem["id"],)).fetchone()
    assert stem["afgekeurd"] == 0
