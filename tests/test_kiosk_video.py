"""Een video op een dia van de Kantine-tv: bestand controleren en opslaan, de dia op het scherm, opruimen."""

import io
import re
import struct
from pathlib import Path

import pytest
from conftest import stel_csrf_token_in as _csrf
from werkzeug.datastructures import FileStorage

import helpers.video as video_module
from helpers import VIDEO_ZWAAR_MBIT, mp4_duur, sla_video_op, verwijder_video, video_info, zwaarte_melding


def _blok(soort, inhoud=b""):
    return struct.pack(">I4s", 8 + len(inhoud), soort) + inhoud


def _mp4(seconden=5.5, versie=0, moov_achteraan=False, extra=b""):
    """Een minimale mp4: 'ftyp', 'mdat' en een 'moov' met een 'mvhd' met de gevraagde lengte."""
    schaal = 1000
    if versie == 1:
        mvhd = struct.pack(">B3xQQIQ", 1, 0, 0, schaal, int(seconden * schaal)) + b"\0" * 80
    else:
        mvhd = struct.pack(">B3xIIII", 0, 0, 0, schaal, int(seconden * schaal)) + b"\0" * 80
    moov = _blok(b"moov", _blok(b"trak", b"\0" * 16) + _blok(b"mvhd", mvhd))
    ftyp = _blok(b"ftyp", b"isom\0\0\2\0isomiso2")
    mdat = _blok(b"mdat", b"\0" * 64)
    delen = [ftyp, mdat, moov] if moov_achteraan else [ftyp, moov, mdat]
    return b"".join(delen) + extra


WEBM = b"\x1a\x45\xdf\xa3" + b"\0" * 64


def _bestand(inhoud, naam="film.mp4"):
    return FileStorage(stream=io.BytesIO(inhoud), filename=naam)


@pytest.fixture
def videomap(tmp_path, monkeypatch):
    """De uploads van deze tests komen in een wegwerpmap, niet in static/kiosk_videos."""
    map_ = tmp_path / "kiosk_videos"
    monkeypatch.setattr(video_module, "KIOSK_VIDEOS_MAP", map_)
    return map_


def _bestanden(map_):
    return sorted(p.name for p in map_.glob("*")) if map_.exists() else []


# ---------- De lengte uit het bestand ----------


def test_de_lengte_uit_het_mvhd_blok(tmp_path):
    for naam, inhoud in {
        "v0.mp4": _mp4(5.5),
        "v1.mp4": _mp4(12.25, versie=1),
        "moov_achteraan.mp4": _mp4(7, moov_achteraan=True),
    }.items():
        (tmp_path / naam).write_bytes(inhoud)
    assert mp4_duur(tmp_path / "v0.mp4") == 5.5
    assert mp4_duur(tmp_path / "v1.mp4") == 12.25  # 64-bits variant
    assert mp4_duur(tmp_path / "moov_achteraan.mp4") == 7  # niet-"faststart" bestanden ook


def test_de_lengte_is_none_als_die_niet_te_lezen_is(tmp_path):
    (tmp_path / "leeg.mp4").write_bytes(b"")
    (tmp_path / "afval.mp4").write_bytes(b"\xff" * 100)
    (tmp_path / "zonder_moov.mp4").write_bytes(_blok(b"ftyp", b"isom") + _blok(b"mdat", b"\0" * 32))
    (tmp_path / "kapot.mp4").write_bytes(_blok(b"ftyp", b"isom") + struct.pack(">I4s", 10**9, b"moov") + b"\0" * 20)
    for naam in ("leeg.mp4", "afval.mp4", "zonder_moov.mp4", "kapot.mp4", "bestaat_niet.mp4"):
        assert mp4_duur(tmp_path / naam) is None


# ---------- Opslaan en controleren ----------


def test_een_mp4_wordt_veilig_opgeslagen(videomap):
    naam, duur, fout = sla_video_op(_bestand(_mp4(4), "Mijn Film (def).MP4"))

    assert fout is None and duur == 4
    assert re.fullmatch(r"[0-9a-f]{32}\.mp4", naam)  # willekeurige naam, kleine letters
    assert (videomap / naam).read_bytes() == _mp4(4)


def test_webm_wordt_geaccepteerd_zonder_lengte(videomap):
    naam, duur, fout = sla_video_op(_bestand(WEBM, "clip.webm"))
    assert fout is None and duur is None and naam.endswith(".webm")


def test_geen_bestand_gekozen_is_geen_fout(videomap):
    assert sla_video_op(None) == (None, None, None)
    assert sla_video_op(_bestand(b"", "")) == (None, None, None)
    assert _bestanden(videomap) == []


@pytest.mark.parametrize(
    "naam, inhoud",
    [
        ("film.exe", _mp4()),  # verkeerd type
        ("film.html", b"<script>alert(1)</script>"),
        ("film.mp4", b"<html><body>geen video</body></html>"),  # lijkt een video, is het niet
        ("film.webm", _mp4()),  # mp4-inhoud met een webm-naam
        ("film.mp4", b""),
    ],
)
def test_wat_geen_video_is_wordt_geweigerd_en_niet_bewaard(videomap, naam, inhoud):
    opgeslagen, duur, fout = sla_video_op(_bestand(inhoud, naam))
    assert opgeslagen is None and duur is None and fout
    assert _bestanden(videomap) == []


def test_een_te_grote_video_wordt_geweigerd_en_weggehaald(videomap, monkeypatch):
    monkeypatch.setattr(video_module, "VIDEO_MAX_BYTES", 1000)
    opgeslagen, _, fout = sla_video_op(_bestand(_mp4(extra=b"\0" * 2000)))
    assert opgeslagen is None and "te groot" in fout
    assert _bestanden(videomap) == []  # ook niet half opgeslagen


def test_verwijderen_raakt_alleen_eigen_bestanden(videomap, tmp_path):
    naam, _, _ = sla_video_op(_bestand(_mp4()))
    vreemd = tmp_path / "belangrijk.txt"
    vreemd.write_text("niet weggooien")
    verwijder_video("../belangrijk.txt")
    verwijder_video("belangrijk.txt")
    verwijder_video(None)
    verwijder_video("niet_van_ons.mp4")
    assert vreemd.exists() and _bestanden(videomap) == [naam]

    verwijder_video(naam)
    verwijder_video(naam)  # twee keer is niet erg
    assert _bestanden(videomap) == []


# ---------- De routes ----------


def _formulier(client, video=None, **velden):
    data = {
        "csrf_token": _csrf(client),
        "sjabloon": "video_volledig",
        "titel": "Sponsorfilm",
        "weergave_duur_seconden": "8",
        "volgorde": "0",
        "actief": "1",
        "video_hele_duur": "1",
    }
    data.update(velden)
    if video is not None:
        data["video"] = (io.BytesIO(video[0]), video[1])
    return data


def _dia(db):
    return db.execute("SELECT * FROM kiosk_sponsoren ORDER BY id DESC").fetchone()


def _nieuw(client, **kwargs):
    return client.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data=_formulier(client, **kwargs),
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_een_videodia_toevoegen(ingelogde_client, db, videomap):
    resp = _nieuw(ingelogde_client, video=(_mp4(6.5), "film.mp4"))

    dia = _dia(db)
    assert (dia["sjabloon"], dia["titel"], dia["video_duur"], dia["video_hele_duur"], dia["video_geluid"]) == (
        "video_volledig", "Sponsorfilm", 6.5, 1, 0,
    )
    assert _bestanden(videomap) == [dia["video"]]
    assert "Video" in resp.data.decode()  # in de lijst met dia's


def test_een_ongeldige_video_laat_de_dia_wel_opslaan_met_een_melding(ingelogde_client, db, videomap):
    resp = _nieuw(ingelogde_client, video=(b"<html>dit is geen video</html>", "film.mp4"))

    tekst = resp.data.decode()
    assert "De video is niet opgeslagen" in tekst and "geen echte video" in tekst
    dia = _dia(db)
    assert dia["titel"] == "Sponsorfilm" and dia["video"] is None
    assert _bestanden(videomap) == []


def test_een_videodia_zonder_video_krijgt_een_waarschuwing_en_staat_niet_op_het_scherm(ingelogde_client, client, db, videomap):
    resp = _nieuw(ingelogde_client)
    assert "nog geen video gekozen" in resp.data.decode()
    assert _scherm_dia(client) is None  # een videodia zonder video heeft niets te tonen
    assert "Sponsorfilm" not in client.get("/kiosk/scherm").data.decode()


def test_een_video_vervangen_verwijdert_de_oude(ingelogde_client, db, videomap):
    _nieuw(ingelogde_client, video=(_mp4(3), "een.mp4"))
    dia = _dia(db)
    oud = dia["video"]

    ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{dia['id']}/bewerken",
        data=_formulier(ingelogde_client, video=(_mp4(9), "twee.mp4")),
        content_type="multipart/form-data",
    )

    nieuw = _dia(db)
    assert nieuw["video"] != oud and nieuw["video_duur"] == 9
    assert _bestanden(videomap) == [nieuw["video"]]  # de oude is weg


def test_opslaan_zonder_nieuw_bestand_houdt_de_video(ingelogde_client, db, videomap):
    _nieuw(ingelogde_client, video=(_mp4(3), "een.mp4"))
    dia = _dia(db)
    ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{dia['id']}/bewerken",
        data=_formulier(ingelogde_client, titel="Nieuwe titel"),
        content_type="multipart/form-data",
    )
    assert (_dia(db)["video"], _dia(db)["titel"]) == (dia["video"], "Nieuwe titel")
    assert _bestanden(videomap) == [dia["video"]]


def test_een_video_verwijderen(ingelogde_client, db, videomap):
    _nieuw(ingelogde_client, video=(_mp4(3), "een.mp4"))
    dia = _dia(db)
    ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{dia['id']}/bewerken",
        data=_formulier(ingelogde_client, video_verwijderen="on"),
        content_type="multipart/form-data",
    )
    assert _dia(db)["video"] is None and _dia(db)["video_duur"] is None
    assert _bestanden(videomap) == []


def test_een_andere_layout_kiezen_laat_de_video_staan(ingelogde_client, db, videomap):
    _nieuw(ingelogde_client, video=(_mp4(3), "een.mp4"))
    dia = _dia(db)
    ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{dia['id']}/bewerken",
        data=_formulier(ingelogde_client, sjabloon="titel_tekst_groot"),
        content_type="multipart/form-data",
    )
    assert (_dia(db)["sjabloon"], _dia(db)["video"]) == ("titel_tekst_groot", dia["video"])  # terugschakelen kan
    assert _bestanden(videomap) == [dia["video"]]


def test_de_dia_verwijderen_ruimt_de_video_op(ingelogde_client, db, videomap):
    _nieuw(ingelogde_client, video=(_mp4(3), "een.mp4"))
    dia = _dia(db)
    ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{dia['id']}/verwijderen", data={"csrf_token": _csrf(ingelogde_client)}
    )
    assert db.execute("SELECT COUNT(*) FROM kiosk_sponsoren").fetchone()[0] == 0
    assert _bestanden(videomap) == []


def test_het_formulier_heeft_de_videolayout_en_de_videovelden(ingelogde_client, db, videomap):
    nieuw = ingelogde_client.get("/kiosk/sponsoren-leden/sponsoren/nieuw").data.decode()
    assert 'value="video_volledig"' in nieuw and 'name="video"' in nieuw and 'name="video_geluid"' in nieuw
    assert 'name="video_hele_duur"' in nieuw and "Maximaal 80 MB" in nieuw

    _nieuw(ingelogde_client, video=(_mp4(3), "een.mp4"))
    bewerken = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{_dia(db)['id']}/bewerken").data.decode()
    assert 'name="video_verwijderen"' in bewerken and "Huidige video (3 seconden" in bewerken


# ---------- Op het scherm ----------


def _scherm_dia(client):
    tekst = client.get("/kiosk/scherm").data.decode()
    return re.search(r'<section class="slide slide-sponsor sjabloon-video_volledig[^>]*data-duur="([^"]+)".*?</section>', tekst, re.S)


def test_de_videodia_op_het_scherm(ingelogde_client, client, db, videomap):
    _nieuw(ingelogde_client, video=(_mp4(6.5), "film.mp4"), titel="Onze sponsor")
    dia = _dia(db)

    gevonden = _scherm_dia(client)

    assert gevonden is not None
    assert gevonden.group(1) == "6.5"  # de dia blijft staan zolang de video duurt
    html = gevonden.group(0)
    # De bron staat in data-bron (het scherm haalt 'm zelf binnen), niet in src: anders begint de browser zelf te laden.
    assert f'data-bron="/static/kiosk_videos/{dia["video"]}"' in html and ' src="' not in html
    assert f'data-bytes="{len(_mp4(6.5))}"' in html
    assert " muted " in html and " loop " in html and "playsinline" in html and "data-geluid" not in html
    assert "Onze sponsor" in html and 'class="onderschrift"' in html


def test_met_geluid_en_met_vaste_duur(ingelogde_client, client, db, videomap):
    _nieuw(ingelogde_client, video=(_mp4(6.5), "film.mp4"), video_geluid="on", video_hele_duur="")
    ingelogde_client.post(
        f"/kiosk/sponsoren-leden/sponsoren/{_dia(db)['id']}/bewerken",
        data=_formulier(ingelogde_client, video_geluid="on", video_hele_duur="", weergave_duur_seconden="15"),
        content_type="multipart/form-data",
    )

    gevonden = _scherm_dia(client)

    assert gevonden.group(1) == "15"  # de ingestelde duur, een kortere video begint opnieuw (loop)
    assert 'data-geluid="1"' in gevonden.group(0)


def test_een_video_zonder_leesbare_lengte_gebruikt_de_ingestelde_duur(ingelogde_client, client, db, videomap):
    _nieuw(ingelogde_client, video=(WEBM, "film.webm"), weergave_duur_seconden="11")
    assert _scherm_dia(client).group(1) == "11"


def test_het_scherm_haalt_video_s_eerst_binnen_en_slaat_een_nog_ladende_dia_over(client, db):
    tekst = client.get("/kiosk/scherm").data.decode()
    assert "function laadVideo" in tekst and "URL.createObjectURL" in tekst  # eerst helemaal binnenhalen
    assert "VIDEO_MAX_IN_GEHEUGEN" in tekst  # een te groot bestand laat de browser zelf streamen
    assert "function videoKlaar" in tekst and "if (videoKlaar(kandidaat)) return kandidaat;" in tekst  # overslaan tot klaar
    assert "if (!videoKlaar(huidige)) huidige = volgende();" in tekst  # niet beginnen met een zwart scherm
    assert "setTimeout(function () { laadVideo(v); }, 30000)" in tekst  # mislukt het ophalen: opnieuw proberen


def test_de_beveiligingsregels_laten_een_video_uit_het_geheugen_toe(client, db):
    """Zonder media-src met blob: weigert de browser de binnengehaalde video ("URL safety check")."""
    beleid = client.get("/kiosk/scherm").headers["Content-Security-Policy"]
    assert "media-src 'self' blob:" in beleid
    assert "default-src 'self'" in beleid and "script-src 'self' 'unsafe-inline'" in beleid  # de rest blijft zoals het was


def test_het_scherm_pauzeert_en_start_de_video_bij_het_wisselen(client, db):
    tekst = client.get("/kiosk/scherm").data.decode()
    assert "function speelVideo" in tekst and "pauzeerVideos(slide)" in tekst and "speelVideo(slide)" in tekst
    assert "speelVideo(slides[0])" in tekst  # ook als de video de enige dia is


# ---------- Zware video's ----------


def test_een_zware_video_krijgt_een_waarschuwing(ingelogde_client, db, videomap):
    # 6 MB voor 5 seconden: ruim boven de 8 Mbit/s.
    resp = _nieuw(ingelogde_client, video=(_mp4(5, extra=b"\0" * (6 * 1024 * 1024)), "zwaar.mp4"))

    tekst = resp.data.decode()
    assert "Let op: deze video is zwaar" in tekst and "720p" in tekst
    assert _dia(db)["video"] is not None  # hij wordt wel opgeslagen: het is een advies, geen verbod


def test_een_lichte_video_krijgt_geen_waarschuwing(ingelogde_client, db, videomap):
    resp = _nieuw(ingelogde_client, video=(_mp4(60, extra=b"\0" * (6 * 1024 * 1024)), "licht.mp4"))
    assert "zwaar" not in resp.data.decode().lower().replace("zwaar:", "")  # geen melding, geen markering


def test_de_zwaarte_van_een_video(videomap):
    zwaar, _, _ = sla_video_op(_bestand(_mp4(5, extra=b"\0" * (6 * 1024 * 1024))))
    licht, _, _ = sla_video_op(_bestand(_mp4(60, extra=b"\0" * (6 * 1024 * 1024))))

    info = video_info(zwaar, 5)
    assert info["zwaar"] and info["mbit"] > VIDEO_ZWAAR_MBIT and round(info["mb"]) == 6
    assert "6.0 MB voor 5 seconden" in zwaarte_melding(info, 5)
    assert not video_info(licht, 60)["zwaar"] and zwaarte_melding(video_info(licht, 60), 60) is None
    assert video_info(zwaar, None)["mbit"] is None and not video_info(zwaar, None)["zwaar"]  # lengte onbekend (webm)
    assert video_info("bestaat_niet.mp4", 5) is None and video_info(None, 5) is None


def test_het_formulier_toont_grootte_en_zwaarte_van_de_huidige_video(ingelogde_client, db, videomap):
    _nieuw(ingelogde_client, video=(_mp4(5, extra=b"\0" * (6 * 1024 * 1024)), "zwaar.mp4"))
    tekst = ingelogde_client.get(f"/kiosk/sponsoren-leden/sponsoren/{_dia(db)['id']}/bewerken").data.decode()
    assert "6.0 MB" in tekst and "Mbit/s" in tekst and "Zwaar: het scherm moet" in tekst


# ---------- De uploadlimiet ----------


def test_een_video_mag_groter_dan_de_gewone_uploadlimiet(ingelogde_client, db, videomap):
    groot = _mp4(5, extra=b"\0" * (25 * 1024 * 1024))  # ruim boven de 20 MB van de rest van de site
    _nieuw(ingelogde_client, video=(groot, "groot.mp4"))
    assert _dia(db)["video"] is not None and len(_bestanden(videomap)) == 1


def test_een_ander_formulier_blijft_bij_20_mb(ingelogde_client, db, videomap):
    resp = ingelogde_client.post(
        "/kiosk/scherm/standen/club-logo",
        data={"csrf_token": _csrf(ingelogde_client), "logo": (io.BytesIO(b"\0" * (25 * 1024 * 1024)), "x.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "te groot om te uploaden (maximaal 20 MB)" in resp.data.decode()


def test_zonder_account_geldt_de_ruimere_limiet_niet(app, db, videomap):
    anoniem = app.test_client()  # niet ingelogd: een vreemde mag de server niet 85 MB laten verwerken
    resp = anoniem.post(
        "/kiosk/sponsoren-leden/sponsoren/nieuw",
        data=_formulier(anoniem, video=(_mp4(extra=b"\0" * (25 * 1024 * 1024)), "groot.mp4")),
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "te groot om te uploaden (maximaal 20 MB)" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM kiosk_sponsoren").fetchone()[0] == 0
    assert _bestanden(videomap) == []


def test_een_te_grote_video_geeft_een_nette_melding(ingelogde_client, db, videomap, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "VIDEO_UPLOAD_MAX_BYTES", 1024 * 1024)
    resp = _nieuw(ingelogde_client, video=(_mp4(extra=b"\0" * (2 * 1024 * 1024)), "groot.mp4"))
    assert "te groot om te uploaden (maximaal 1 MB)" in resp.data.decode()
    assert db.execute("SELECT COUNT(*) FROM kiosk_sponsoren").fetchone()[0] == 0
    assert _bestanden(videomap) == []


def test_video_uploads_komen_nooit_in_git():
    gitignore = (Path(__file__).resolve().parent.parent / ".gitignore").read_text()
    assert "static/kiosk_videos/" in gitignore
