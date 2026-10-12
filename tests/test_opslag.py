"""Beheer > Opslag: wat de site aan schijfruimte gebruikt, de waarschuwing op het dashboard en het opruimen."""

import os
import re

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_kiosk_video import _mp4
from test_secties_rechten import _login, _maak_vrijwilliger

import helpers.video as video_module
import opslag
from helpers import sla_video_op
from opslag import (
    KRITIEK_PCT,
    WAARSCHUWING_PCT,
    bereken_opslag,
    bewaar_quota_mb,
    groottetekst,
    lees_quota_mb,
    ongebruikte_videos,
    opslag_status,
    verwijder_ongebruikte_videos,
)

MB = 1024 * 1024


@pytest.fixture(autouse=True)
def _zonder_bewaren(monkeypatch):
    monkeypatch.setattr(opslag, "CACHE_AAN", False)
    opslag.wis_cache()


def _bestand(basis, pad, grootte):
    """Een bestand van precies 'grootte' bytes (spaarzaam aangemaakt: kost geen echte schijfruimte)."""
    doel = basis / pad
    doel.parent.mkdir(parents=True, exist_ok=True)
    with open(doel, "wb") as f:
        f.truncate(grootte)
    return doel


# ---------- Meten ----------


def test_groottes_in_gewoon_nederlands():
    assert groottetekst(0) == "0 kB" and groottetekst(300) == "1 kB" and groottetekst(45 * 1024) == "45 kB"
    assert groottetekst(int(12.34 * MB)) == "12,3 MB" and groottetekst(int(1.5 * 1024 * MB)) == "1,5 GB"


def test_de_ruimte_wordt_per_onderdeel_gemeten(tmp_path):
    _bestand(tmp_path, "voorraad.db", 2 * MB)
    _bestand(tmp_path, "backups/voorraad-2026-10-01.db", 3 * MB)
    _bestand(tmp_path, "backups/voorraad-2026-10-02.db", 3 * MB)
    _bestand(tmp_path, "static/kiosk_videos/a.mp4", 10 * MB)
    _bestand(tmp_path, "static/kiosk_afbeeldingen/s.png", 1 * MB)
    _bestand(tmp_path, "static/club_logos/l.png", 100 * 1024)
    _bestand(tmp_path, "app.py", 50 * 1024)
    _bestand(tmp_path, "venv/lib/enorm.so", 500 * MB)  # telt niet mee
    _bestand(tmp_path, ".claude/worktrees/kopie.db", 500 * MB)  # telt niet mee

    uitkomst = bereken_opslag(tmp_path, 100)

    per_naam = {o["naam"]: o for o in uitkomst["onderdelen"]}
    assert per_naam["Back-ups"]["bytes"] == 6 * MB and per_naam["Back-ups"]["aantal"] == 2
    assert per_naam["Video's (kantine-tv)"]["bytes"] == 10 * MB
    assert per_naam["Database"]["bytes"] == 2 * MB
    assert per_naam["Programma en overig"]["bytes"] == 50 * 1024
    assert "Productfoto's" not in per_naam  # lege onderdelen blijven weg
    assert [o["naam"] for o in uitkomst["onderdelen"]][0] == "Video's (kantine-tv)"  # grootste eerst
    assert uitkomst["totaal"] == 10 * MB + 6 * MB + 2 * MB + 1 * MB + 100 * 1024 + 50 * 1024
    assert uitkomst["grootste"][0] == {"bytes": 10 * MB, "pad": "static/kiosk_videos/a.mp4"}
    assert [f["bytes"] for f in uitkomst["grootste"]] == sorted((f["bytes"] for f in uitkomst["grootste"]), reverse=True)
    assert abs(sum(o["aandeel"] for o in uitkomst["onderdelen"]) - 100) < 0.01


def test_de_drempels(tmp_path):
    _bestand(tmp_path, "x.bin", 100 * MB)
    assert bereken_opslag(tmp_path, 1000)["niveau"] == "ok"
    assert bereken_opslag(tmp_path, int(100 / (WAARSCHUWING_PCT / 100)) - 1)["niveau"] == "let_op"  # net boven 80%
    assert bereken_opslag(tmp_path, int(100 / (KRITIEK_PCT / 100)) - 1)["niveau"] == "kritiek"
    assert bereken_opslag(tmp_path, 50)["percentage"] == 200  # meer dan vol kan ook (en breekt niets)


def test_een_lege_map_en_alleen_de_tien_grootste(tmp_path):
    leeg = bereken_opslag(tmp_path, 100)
    assert leeg["totaal"] == 0 and leeg["onderdelen"] == [] and leeg["grootste"] == [] and leeg["niveau"] == "ok"
    for i in range(15):
        _bestand(tmp_path, f"static/kiosk_afbeeldingen/f{i:02d}.png", (i + 1) * 1024)
    assert len(bereken_opslag(tmp_path, 100)["grootste"]) == 10


def test_symbolische_links_tellen_niet_dubbel(tmp_path):
    echt = _bestand(tmp_path, "static/kiosk_videos/a.mp4", 5 * MB)
    os.symlink(echt, tmp_path / "snelkoppeling.mp4")
    assert bereken_opslag(tmp_path, 100)["totaal"] == 5 * MB


def test_het_resultaat_wordt_even_bewaard_maar_ververst_op_verzoek(app, db, monkeypatch):
    monkeypatch.setattr(opslag, "CACHE_AAN", True)
    opslag.wis_cache()
    basis = app.config["OPSLAG_MAP"]
    _bestand(basis, "a.bin", 1 * MB)
    eerst = opslag_status(db)["totaal"]
    _bestand(basis, "b.bin", 2 * MB)

    assert opslag_status(db)["totaal"] == eerst  # nog het bewaarde resultaat
    assert opslag_status(db, vers=True)["totaal"] == eerst + 2 * MB
    assert opslag_status(db)["totaal"] == eerst + 2 * MB  # en dat is nu het bewaarde


# ---------- Instelling ----------


def test_standaard_en_begrensde_hoeveelheid(db):
    assert lees_quota_mb(db) == 1024
    bewaar_quota_mb(db, 2048)
    assert lees_quota_mb(db) == 2048
    bewaar_quota_mb(db, 1)
    assert lees_quota_mb(db) == 50
    bewaar_quota_mb(db, 10**9)
    assert lees_quota_mb(db) == 1_000_000


# ---------- Ongebruikte video's ----------


@pytest.fixture
def videomap(tmp_path, monkeypatch):
    map_ = tmp_path / "videos"
    monkeypatch.setattr(video_module, "KIOSK_VIDEOS_MAP", map_)
    return map_


def _dia_met_video(db, naam, titel="Film", actief=1):
    db.execute(
        "INSERT INTO kiosk_sponsoren (sjabloon, titel, aangemaakt_op, video, actief) VALUES ('video_volledig', ?, '2026-10-01', ?, ?)",
        (titel, naam, actief),
    )
    db.commit()


def test_alleen_video_s_zonder_dia_zijn_ongebruikt(db, videomap):
    gebruikt, _, _ = sla_video_op(_bestandsopslag(_mp4(3)))
    wees1, _, _ = sla_video_op(_bestandsopslag(_mp4(4)))
    wees2, _, _ = sla_video_op(_bestandsopslag(_mp4(5), "x.mp4"))
    (videomap / "mijn-eigen-notitie.txt").write_text("niet van de site")
    _dia_met_video(db, gebruikt)

    assert sorted(n for n, _ in ongebruikte_videos(db)) == sorted([wees1, wees2])

    aantal, bytes_ = verwijder_ongebruikte_videos(db)

    assert aantal == 2 and bytes_ == len(_mp4(4)) + len(_mp4(5))
    assert sorted(p.name for p in videomap.iterdir()) == sorted([gebruikt, "mijn-eigen-notitie.txt"])  # de rest blijft
    assert ongebruikte_videos(db) == [] and verwijder_ongebruikte_videos(db) == (0, 0)


def _bestandsopslag(inhoud, naam="film.mp4"):
    import io

    from werkzeug.datastructures import FileStorage

    return FileStorage(stream=io.BytesIO(inhoud), filename=naam)


def test_zonder_videomap_is_er_niets_ongebruikt(db, videomap):
    assert ongebruikte_videos(db) == []


# ---------- De pagina ----------


def test_de_pagina_toont_wat_de_ruimte_inneemt(ingelogde_client, app, db, videomap):
    basis = app.config["OPSLAG_MAP"]
    _bestand(basis, "static/kiosk_videos/pad.mp4", 7 * MB)
    _bestand(basis, "backups/voorraad-2026-10-01.db", 2 * MB)

    tekst = ingelogde_client.get("/opslag").data.decode()

    assert "9,0 MB van 1024 MB in gebruik" in tekst
    assert "Video&#39;s (kantine-tv)" in tekst or "Video's (kantine-tv)" in tekst
    assert "static/kiosk_videos/pad.mp4" in tekst and "hoort bij geen dia" in tekst
    assert "ruim voldoende" in tekst
    assert "ffmpeg ontbreekt" in tekst or "automatisch verkleind" in tekst  # zegt of verkleinen kan


def test_een_video_van_een_dia_toont_de_naam_van_de_dia(ingelogde_client, app, db, videomap):
    naam = "a" * 32 + ".mp4"
    _bestand(app.config["OPSLAG_MAP"], f"static/kiosk_videos/{naam}", 3 * MB)
    _dia_met_video(db, naam, titel="Sponsorfilm", actief=0)
    tekst = ingelogde_client.get("/opslag").data.decode()
    assert 'Video van dia "Sponsorfilm"' in tekst.replace("&#34;", '"') and "dia staat uit" in tekst


def test_de_hoeveelheid_instellen_via_de_pagina(ingelogde_client, db):
    ingelogde_client.post("/opslag", data={"csrf_token": _csrf(ingelogde_client), "quota_mb": "2000"})
    assert lees_quota_mb(db) == 2000
    resp = ingelogde_client.post("/opslag", data={"csrf_token": _csrf(ingelogde_client), "quota_mb": "veel"}, follow_redirects=True)
    assert "als getal" in resp.data.decode() and lees_quota_mb(db) == 2000


def test_opruimen_via_de_pagina(ingelogde_client, db, videomap):
    wees, _, _ = sla_video_op(_bestandsopslag(_mp4(4)))
    assert wees in ingelogde_client.get("/opslag").data.decode()  # staat in de lijst met ongebruikte video's

    resp = ingelogde_client.post("/opslag/video-opruimen", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)

    assert "1 ongebruikte video verwijderd" in resp.data.decode()
    assert not (videomap / wees).exists()
    resp = ingelogde_client.post("/opslag/video-opruimen", data={"csrf_token": _csrf(ingelogde_client)}, follow_redirects=True)
    assert "geen ongebruikte video" in resp.data.decode()


def test_alleen_beheerders_komen_bij_opslag(client, db):
    _maak_vrijwilliger(db, "vrijwilliger", "voorraad")
    _login(client, "vrijwilliger")
    assert "alleen voor beheerders" in client.get("/opslag", follow_redirects=True).data.decode()
    resp = client.post("/opslag/video-opruimen", data={"csrf_token": _csrf(client)}, follow_redirects=True)
    assert "alleen voor beheerders" in resp.data.decode()


def test_de_pagina_staat_in_het_menu_van_beheerders(ingelogde_client):
    menu = ingelogde_client.get("/").data.decode()
    assert re.search(r'href="/opslag"[^>]*>\s*Opslag', menu)


# ---------- De melding op het dashboard ----------


def _vul_tot(app, db, procent):
    quota = lees_quota_mb(db)
    _bestand(app.config["OPSLAG_MAP"], "static/kiosk_videos/groot.mp4", int(quota * MB * procent / 100))


def test_geen_melding_zolang_er_ruimte_is(ingelogde_client, app, db):
    _vul_tot(app, db, 50)
    assert "Opslag voor" not in ingelogde_client.get("/").data.decode()


def test_vanaf_80_procent_staat_er_een_taak_op_het_dashboard(ingelogde_client, app, db):
    _vul_tot(app, db, 85)
    tekst = ingelogde_client.get("/").data.decode()
    assert "Opslag voor 85% vol" in tekst and "/opslag" in tekst


def test_vanaf_95_procent_is_de_taak_urgent_en_staat_bovenaan(ingelogde_client, app, db):
    from helpers.status import bouw_taken

    _vul_tot(app, db, 97)
    taken = bouw_taken(db, "beheerder", None)
    opslag_taak = next(t for t in taken if t["titel"].startswith("Opslag voor"))
    assert opslag_taak["urgent"] is True
    assert all(t["urgent"] for t in taken[: taken.index(opslag_taak) + 1])  # urgent staat vóór alles wat niet urgent is


def test_vrijwilligers_krijgen_de_opslagtaak_niet(app, db):
    from helpers.status import bouw_taken

    _vul_tot(app, db, 97)
    assert not any(t["titel"].startswith("Opslag voor") for t in bouw_taken(db, "vrijwilliger", "voorraad"))
