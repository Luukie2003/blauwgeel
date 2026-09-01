import io

from conftest import stel_csrf_token_in as _csrf

from app import STEM_AFBEELDINGEN_MAP, stemming_is_open

_KLEINE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def test_publiek_overzicht_toont_ook_gesloten_en_verlopen_stemmingen(ingelogde_client, db):
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
    assert b"Gesloten stemming" in resp.data
    assert b"Verlopen stemming" in resp.data
    assert resp.data.count(b"Gesloten") >= 2  # badge bij de 2 niet-open stemmingen
    assert open_id  # sanity, id werd gebruikt


def test_publiek_overzicht_toont_scores_bij_gesloten_stemming_met_toon_uitslag(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(
        ingelogde_client, titel="Gesloten met scores", opties=("Fust A", "Fust B"), extra={"toon_uitslag": "1"}
    )
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Iemand")
    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/sluiten", data={"csrf_token": _csrf(ingelogde_client)}
    )

    resp = ingelogde_client.get("/stem")
    assert b"Gesloten met scores" in resp.data
    assert b"Fust A" in resp.data
    assert b"100%" in resp.data


def test_publiek_overzicht_toont_scores_bij_gesloten_stemming_ondanks_uitgeschakelde_toon_uitslag(
    ingelogde_client, db
):
    """toon_uitslag verbergt de tussenstand alleen zolang een stemming nog
    open is (om stemmers onderling niet te beinvloeden). Eenmaal gesloten
    mag iedereen de einduitslag altijd zien, ongeacht deze instelling."""
    stemvraag_id = _maak_stemvraag(ingelogde_client, titel="Gesloten toch scores", opties=("Fust A", "Fust B"))
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde LIMIT 1", (stemvraag_id,)
    ).fetchone()
    _stem(ingelogde_client, stemvraag_id, optie["id"], naam="Iemand")
    ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/sluiten", data={"csrf_token": _csrf(ingelogde_client)}
    )

    resp = ingelogde_client.get("/stem")
    assert b"Gesloten toch scores" in resp.data
    assert b"Fust A" in resp.data

    detail = ingelogde_client.get(f"/stem/{stemvraag_id}")
    assert b"Fust A" in detail.data
    assert b"100%" in detail.data


def test_publiek_overzicht_zonder_login_bereikbaar(client, db):
    resp = client.get("/stem")
    assert resp.status_code == 200


def test_publiek_overzicht_mengt_geen_opties_of_scores_tussen_stemmingen(ingelogde_client, db):
    """Regressietest voor de query-batching in stem_overzicht_publiek(): bij
    meerdere gesloten stemmingen tegelijk moet elke stemming zijn eigen
    opties en percentages tonen, niet die van een andere stemming."""
    eerste_id = _maak_stemvraag(ingelogde_client, titel="Bier peiling", opties=("Pils", "Weizen"))
    eerste_opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (eerste_id,)
    ).fetchall()
    _stem(ingelogde_client, eerste_id, eerste_opties[0]["id"], naam="Stemmer Een")

    tweede_id = _maak_stemvraag(ingelogde_client, titel="Snack peiling", opties=("Bitterbal", "Kaassoufflé"))
    tweede_opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (tweede_id,)
    ).fetchall()
    _stem(ingelogde_client, tweede_id, tweede_opties[1]["id"], naam="Stemmer Twee")

    for vraag_id in (eerste_id, tweede_id):
        ingelogde_client.post(
            f"/stemmen/{vraag_id}/sluiten", data={"csrf_token": _csrf(ingelogde_client)}
        )

    body = ingelogde_client.get("/stem").data.decode()
    bier_start = body.index("Bier peiling")
    snack_start = body.index("Snack peiling")
    bier_kaart = body[bier_start:snack_start] if bier_start < snack_start else body[bier_start:]
    snack_kaart = body[snack_start:bier_start] if snack_start < bier_start else body[snack_start:]

    assert "Pils" in bier_kaart and "Weizen" in bier_kaart
    assert "Bitterbal" not in bier_kaart and "Kaassoufflé" not in bier_kaart
    assert "100%" in bier_kaart  # 1 stem, allemaal op Pils

    assert "Bitterbal" in snack_kaart and "Kaassoufflé" in snack_kaart
    assert "Pils" not in snack_kaart and "Weizen" not in snack_kaart
    assert "100%" in snack_kaart  # 1 stem, op Kaassoufflé


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


def test_aantal_keuzes_standaard_1(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["aantal_keuzes"] == 1


def test_aantal_keuzes_kan_worden_ingesteld_bij_aanmaken(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, extra={"aantal_keuzes": "2"})
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["aantal_keuzes"] == 2


def test_meerdere_keuzes_kunnen_gestemd_worden(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, extra={"aantal_keuzes": "2"})
    opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    resp = _stem(ingelogde_client, stemvraag_id, [opties[0]["id"], opties[1]["id"]])
    assert b"Bedankt voor je stem" in resp.data
    stemmen = db.execute("SELECT * FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)).fetchall()
    assert len(stemmen) == 2
    assert {s["stemoptie_id"] for s in stemmen} == {opties[0]["id"], opties[1]["id"]}


def test_minder_dan_maximum_keuzes_mag_ook(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, extra={"aantal_keuzes": "3"})
    opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    resp = _stem(ingelogde_client, stemvraag_id, [opties[0]["id"]])
    assert b"Bedankt voor je stem" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 1


def test_meer_dan_maximum_keuzes_wordt_geweigerd(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, extra={"aantal_keuzes": "2"})
    opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    resp = _stem(ingelogde_client, stemvraag_id, [o["id"] for o in opties])  # 3 opties, max is 2
    assert b"Kies maximaal 2 opties" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 0


def test_dubbel_stemmen_geweerd_bij_meerdere_keuzes(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, extra={"aantal_keuzes": "2"})
    opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    _stem(ingelogde_client, stemvraag_id, [opties[0]["id"], opties[1]["id"]])
    resp = _stem(ingelogde_client, stemvraag_id, [opties[2]["id"]])
    assert b"al gestemd" in resp.data
    aantal = db.execute(
        "SELECT COUNT(*) AS n FROM stemmen WHERE stemvraag_id = ?", (stemvraag_id,)
    ).fetchone()["n"]
    assert aantal == 2


def test_percentage_gaat_uit_van_aantal_stemmers_niet_aantal_keuzes(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, extra={"aantal_keuzes": "2", "toon_uitslag": "1"})
    opties = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? ORDER BY volgorde", (stemvraag_id,)
    ).fetchall()
    _stem(ingelogde_client, stemvraag_id, [opties[0]["id"], opties[1]["id"]], naam="Een Stemmer")
    detail = ingelogde_client.get(f"/stemmen/{stemvraag_id}")
    # 1 stemmer koos 2 opties -> elke gekozen optie moet 100% zijn, niet 50%.
    assert detail.data.count(b"(100%)") == 2


def test_aantal_keuzes_kan_achteraf_gewijzigd_worden(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client)
    resp = ingelogde_client.post(
        f"/stemmen/{stemvraag_id}/instellingen",
        data={"csrf_token": _csrf(ingelogde_client), "aantal_keuzes": "3"},
    )
    assert resp.status_code == 302
    vraag = db.execute("SELECT * FROM stemvragen WHERE id = ?", (stemvraag_id,)).fetchone()
    assert vraag["aantal_keuzes"] == 3


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


def test_bier_met_foto_wordt_opgeslagen_in_bibliotheek(ingelogde_client, db):
    resp = ingelogde_client.post(
        "/stemmen/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client),
            "titel": "Seizoensbier",
            "optie1": "Weihenstephaner",
            "optie2": "Fust B",
            "afbeelding1": (io.BytesIO(_KLEINE_PNG), "weihen.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    bier = db.execute("SELECT * FROM bieren WHERE naam = 'Weihenstephaner'").fetchone()
    assert bier is not None
    assert bier["afbeelding"] is not None
    (STEM_AFBEELDINGEN_MAP / bier["afbeelding"]).unlink()


def test_optie_zonder_foto_maar_bekende_naam_hergebruikt_bibliotheekfoto(ingelogde_client, db):
    _maak_stemvraag(
        ingelogde_client,
        titel="Eerste stemming",
        opties=("Weihenstephaner", "Fust B"),
        extra={"afbeelding1": (io.BytesIO(_KLEINE_PNG), "weihen.png")},
    )
    bier = db.execute("SELECT * FROM bieren WHERE naam = 'Weihenstephaner'").fetchone()
    bekende_afbeelding = bier["afbeelding"]

    tweede_id = _maak_stemvraag(
        ingelogde_client, titel="Tweede stemming", opties=("Weihenstephaner", "Fust C")
    )
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? AND tekst = 'Weihenstephaner'", (tweede_id,)
    ).fetchone()
    assert optie["afbeelding"] == bekende_afbeelding
    (STEM_AFBEELDINGEN_MAP / bekende_afbeelding).unlink()


def test_naam_matching_voor_hergebruik_is_niet_hoofdlettergevoelig(ingelogde_client, db):
    _maak_stemvraag(
        ingelogde_client,
        titel="Eerste stemming",
        opties=("Weihenstephaner", "Fust B"),
        extra={"afbeelding1": (io.BytesIO(_KLEINE_PNG), "weihen.png")},
    )
    bier = db.execute("SELECT * FROM bieren WHERE naam = 'Weihenstephaner'").fetchone()

    tweede_id = _maak_stemvraag(
        ingelogde_client, titel="Tweede stemming", opties=("weihenstephaner", "Fust C")
    )
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? AND tekst = 'weihenstephaner'", (tweede_id,)
    ).fetchone()
    assert optie["afbeelding"] == bier["afbeelding"]
    (STEM_AFBEELDINGEN_MAP / bier["afbeelding"]).unlink()


def test_optie_zonder_foto_en_onbekende_naam_blijft_zonder_foto(ingelogde_client, db):
    stemvraag_id = _maak_stemvraag(ingelogde_client, opties=("Onbekend Biertje", "Fust B"))
    optie = db.execute(
        "SELECT * FROM stemopties WHERE stemvraag_id = ? AND tekst = 'Onbekend Biertje'", (stemvraag_id,)
    ).fetchone()
    assert optie["afbeelding"] is None


def test_bieren_lijst_toont_opgeslagen_bieren(ingelogde_client, db):
    _maak_stemvraag(
        ingelogde_client,
        opties=("Weihenstephaner", "Fust B"),
        extra={"afbeelding1": (io.BytesIO(_KLEINE_PNG), "weihen.png")},
    )
    bier = db.execute("SELECT * FROM bieren WHERE naam = 'Weihenstephaner'").fetchone()

    resp = ingelogde_client.get("/stemmen/bieren")
    assert b"Weihenstephaner" in resp.data
    (STEM_AFBEELDINGEN_MAP / bier["afbeelding"]).unlink()


def test_bier_verwijderen_uit_bibliotheek(ingelogde_client, db):
    _maak_stemvraag(
        ingelogde_client,
        opties=("Weihenstephaner", "Fust B"),
        extra={"afbeelding1": (io.BytesIO(_KLEINE_PNG), "weihen.png")},
    )
    bier = db.execute("SELECT * FROM bieren WHERE naam = 'Weihenstephaner'").fetchone()
    (STEM_AFBEELDINGEN_MAP / bier["afbeelding"]).unlink()

    resp = ingelogde_client.post(
        f"/stemmen/bieren/{bier['id']}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert resp.status_code == 302
    assert db.execute("SELECT * FROM bieren WHERE id = ?", (bier["id"],)).fetchone() is None
