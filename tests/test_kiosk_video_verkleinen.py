"""Een zware video bij het uploaden automatisch verkleinen (als ffmpeg op de server staat)."""

import io
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import stel_csrf_token_in as _csrf
from test_kiosk_video import WEBM, _bestand, _bestanden, _dia, _mp4
from werkzeug.datastructures import FileStorage

import helpers.video as video_module
from helpers import ffmpeg_beschikbaar, mp4_duur, sla_video_op


@pytest.fixture
def videomap(tmp_path, monkeypatch):
    map_ = tmp_path / "kiosk_videos"
    monkeypatch.setattr(video_module, "KIOSK_VIDEOS_MAP", map_)
    return map_


def _nep_ffmpeg(tmp_path, monkeypatch, uitvoer=None, gedrag="kopieer"):
    """Een nep-'ffmpeg': een scriptje dat het laatste argument (het uitvoerbestand) vult met 'uitvoer' (bytes), mislukt
    of niets doet, en de argumenten naar een logbestand schrijft."""
    klein = tmp_path / "klein.mp4"
    klein.write_bytes(uitvoer if uitvoer is not None else _mp4(5))
    log = tmp_path / "ffmpeg-argumenten.txt"
    script = tmp_path / "ffmpeg"
    acties = {"kopieer": f'cp "{klein}" "$laatste"', "mislukt": "exit 1", "niets": "exit 0"}
    script.write_text(f'#!/bin/sh\nfor laatste; do :; done\necho "$@" > "{log}"\n{acties[gedrag]}\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FFMPEG_PAD", str(script))
    return log


ZWAAR = _mp4(5, extra=b"\0" * (6 * 1024 * 1024))  # 6 MB voor 5 seconden: ongeveer 10 Mbit/s
LICHT = _mp4(60, extra=b"\0" * (6 * 1024 * 1024))  # 6 MB voor een minuut: ruim onder de grens


def test_zonder_ffmpeg_of_zonder_vinkje_blijft_de_video_zoals_hij_was(videomap, tmp_path, monkeypatch):
    monkeypatch.delenv("FFMPEG_PAD", raising=False)
    monkeypatch.setattr(video_module.shutil, "which", lambda _: None)
    assert not ffmpeg_beschikbaar()
    meldingen = []
    naam, duur, fout = sla_video_op(_bestand(ZWAAR), verkleinen=True, meldingen=meldingen)
    assert fout is None and (videomap / naam).read_bytes() == ZWAAR and meldingen == []

    log = _nep_ffmpeg(tmp_path, monkeypatch)
    naam2, _, _ = sla_video_op(_bestand(ZWAAR), verkleinen=False, meldingen=meldingen)  # niet aangevinkt
    assert (videomap / naam2).read_bytes() == ZWAAR and not log.exists()


def test_een_zware_video_wordt_vervangen_door_de_verkleinde(videomap, tmp_path, monkeypatch):
    log = _nep_ffmpeg(tmp_path, monkeypatch)
    meldingen = []

    naam, duur, fout = sla_video_op(_bestand(ZWAAR, "Opname van mijn telefoon.MOV"), verkleinen=True, meldingen=meldingen)

    assert fout is None and naam.endswith(".mp4")  # altijd een mp4, ook als het een mov was
    assert (videomap / naam).read_bytes() == _mp4(5)  # het verkleinde bestand
    assert _bestanden(videomap) == [naam]  # het origineel is weg: er blijft 1 bestand over
    assert duur == 5
    assert re.fullmatch(r"De video is automatisch verkleind van 6\.\d MB naar 0\.0 MB\.", meldingen[0])
    argumenten = log.read_text()
    assert "scale=" in argumenten and "libx264" in argumenten and "+faststart" in argumenten and "-crf 26" in argumenten
    assert "-maxrate 4M" in argumenten


def test_een_lichte_video_blijft_zoals_hij_is(videomap, tmp_path, monkeypatch):
    log = _nep_ffmpeg(tmp_path, monkeypatch)
    meldingen = []
    naam, _, _ = sla_video_op(_bestand(LICHT), verkleinen=True, meldingen=meldingen)
    assert (videomap / naam).read_bytes() == LICHT and meldingen == [] and not log.exists()  # ffmpeg niet eens gestart


def test_als_ffmpeg_mislukt_blijft_het_origineel_staan(videomap, tmp_path, monkeypatch):
    _nep_ffmpeg(tmp_path, monkeypatch, gedrag="mislukt")
    meldingen = []
    naam, duur, fout = sla_video_op(_bestand(ZWAAR), verkleinen=True, meldingen=meldingen)
    assert fout is None and (videomap / naam).read_bytes() == ZWAAR and _bestanden(videomap) == [naam]
    assert "lukte niet" in meldingen[0]

    _nep_ffmpeg(tmp_path, monkeypatch, gedrag="niets")  # 'gelukt' maar geen bestand gemaakt
    naam2, _, _ = sla_video_op(_bestand(ZWAAR), verkleinen=True, meldingen=meldingen)
    assert (videomap / naam2).read_bytes() == ZWAAR and len(_bestanden(videomap)) == 2


def test_geen_duidelijke_winst_houdt_het_origineel(videomap, tmp_path, monkeypatch):
    _nep_ffmpeg(tmp_path, monkeypatch, uitvoer=ZWAAR)  # even groot als het origineel
    meldingen = []
    naam, _, _ = sla_video_op(_bestand(ZWAAR), verkleinen=True, meldingen=meldingen)
    assert (videomap / naam).read_bytes() == ZWAAR and _bestanden(videomap) == [naam]
    assert "geen duidelijke winst" in meldingen[0]


def test_een_te_lange_video_wordt_niet_verkleind(videomap, tmp_path, monkeypatch):
    log = _nep_ffmpeg(tmp_path, monkeypatch)
    monkeypatch.setattr(video_module, "VIDEO_VERKLEIN_MAX_SECONDEN", 4)  # onze testvideo duurt 5 s
    meldingen = []
    naam, _, _ = sla_video_op(_bestand(ZWAAR), verkleinen=True, meldingen=meldingen)
    assert (videomap / naam).read_bytes() == ZWAAR and not log.exists()
    assert "te lang om automatisch te verkleinen" in meldingen[0]


def test_webm_zonder_bekende_lengte_wordt_verkleind_als_hij_groot_is(videomap, tmp_path, monkeypatch):
    log = _nep_ffmpeg(tmp_path, monkeypatch)
    klein = _bestand(WEBM, "klein.webm")
    naam, _, _ = sla_video_op(klein, verkleinen=True, meldingen=[])
    assert naam.endswith(".webm") and not log.exists()  # klein: laat maar

    groot = WEBM + b"\0" * (7 * 1024 * 1024)
    meldingen = []
    naam, _, _ = sla_video_op(_bestand(groot, "groot.webm"), verkleinen=True, meldingen=meldingen)
    assert naam.endswith(".mp4") and log.exists() and "automatisch verkleind" in meldingen[0]


def test_ffmpeg_pad_komt_uit_de_omgeving_of_het_systeem(tmp_path, monkeypatch):
    monkeypatch.setenv("FFMPEG_PAD", "/ergens/ffmpeg")
    assert video_module.ffmpeg_pad() == "/ergens/ffmpeg"
    monkeypatch.delenv("FFMPEG_PAD")
    monkeypatch.setattr(video_module.shutil, "which", lambda naam: f"/usr/bin/{naam}")
    assert video_module.ffmpeg_pad() == "/usr/bin/ffmpeg"


# ---------- Het formulier ----------


def test_het_vinkje_staat_er_alleen_als_ffmpeg_er_is(ingelogde_client, tmp_path, monkeypatch):
    monkeypatch.delenv("FFMPEG_PAD", raising=False)
    monkeypatch.setattr(video_module.shutil, "which", lambda _: None)
    zonder = ingelogde_client.get("/kiosk/sponsoren-leden/sponsoren/nieuw").data.decode()
    assert 'name="video_verkleinen"' not in zonder and "ffmpeg ontbreekt" in zonder

    _nep_ffmpeg(tmp_path, monkeypatch)
    met = ingelogde_client.get("/kiosk/sponsoren-leden/sponsoren/nieuw").data.decode()
    assert re.search(r'name="video_verkleinen"[^>]*checked', met) and "ffmpeg ontbreekt" not in met


def test_uploaden_met_het_vinkje_verkleint_en_meldt_het(ingelogde_client, db, videomap, tmp_path, monkeypatch):
    _nep_ffmpeg(tmp_path, monkeypatch)

    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client), "sjabloon": "video_volledig", "titel": "Zware film", "actief": "1",
            "video_hele_duur": "1", "video_verkleinen": "on", "video": (io.BytesIO(ZWAAR), "film.mov"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    tekst = resp.data.decode()
    assert "automatisch verkleind van" in tekst
    assert "Let op: deze video is zwaar" not in tekst  # de bewaarde video is licht
    dia = _dia(db)
    assert dia["video"].endswith(".mp4") and dia["video_duur"] == 5
    assert _bestanden(videomap) == [dia["video"]]


def test_uploaden_zonder_het_vinkje_laat_de_video_zoals_hij_is_met_de_zwaar_waarschuwing(ingelogde_client, db, videomap, tmp_path, monkeypatch):
    _nep_ffmpeg(tmp_path, monkeypatch)
    resp = ingelogde_client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data={
            "csrf_token": _csrf(ingelogde_client), "sjabloon": "video_volledig", "titel": "Zware film", "actief": "1",
            "video": (io.BytesIO(ZWAAR), "film.mp4"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Let op: deze video is zwaar" in resp.data.decode()
    assert (videomap / _dia(db)["video"]).read_bytes() == ZWAAR


# ---------- Met de echte ffmpeg (alleen als die er is) ----------

ECHT = os.environ.get("FFMPEG_PAD") or shutil.which("ffmpeg")


@pytest.mark.skipif(not ECHT or not Path(ECHT).exists(), reason="ffmpeg niet beschikbaar")
def test_met_de_echte_ffmpeg_wordt_een_zware_staande_video_klein_en_blijft_afspeelbaar(videomap, tmp_path, monkeypatch):
    monkeypatch.setenv("FFMPEG_PAD", str(ECHT))
    zwaar = tmp_path / "zwaar.mp4"
    subprocess.run(
        [str(ECHT), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30", "-f", "lavfi",
         "-i", "sine=frequency=440", "-t", "3", "-c:v", "libx264", "-b:v", "18M", "-pix_fmt", "yuv420p", "-c:a", "aac", str(zwaar)],
        check=True,
    )
    assert zwaar.stat().st_size > 5 * 1024 * 1024
    meldingen = []

    naam, duur, fout = sla_video_op(
        FileStorage(stream=io.BytesIO(zwaar.read_bytes()), filename="telefoon.mp4"), verkleinen=True, meldingen=meldingen
    )

    assert fout is None and naam.endswith(".mp4") and _bestanden(videomap) == [naam]
    nieuw = videomap / naam
    assert nieuw.stat().st_size < zwaar.stat().st_size / 5
    assert abs(duur - 3) < 0.5 and abs(mp4_duur(nieuw) - 3) < 0.5
    info = subprocess.run([str(ECHT), "-hide_banner", "-i", str(nieuw)], capture_output=True, text=True).stderr
    assert "720x1280" in info and "Audio: aac" in info  # staand blijft staand, geluid blijft
    assert "automatisch verkleind" in meldingen[0]
