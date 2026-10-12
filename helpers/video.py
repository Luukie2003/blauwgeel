"""Opslaan en controleren van geuploade video's voor een dia op de Kantine-tv."""

import os
import re
import secrets
import shutil
import struct
import subprocess
from pathlib import Path

from helpers.basis import BASE_DIR


KIOSK_VIDEOS_MAP = BASE_DIR / "static" / "kiosk_videos"


# mp4 (H.264) speelt overal af, ook op de Chromecast; .mov komt van een iPhone (H.264 gaat goed, HEVC niet altijd).
TOEGESTANE_VIDEO_EXTENSIES = {".mp4", ".m4v", ".mov", ".webm"}


# De hosting heeft beperkte schijfruimte en het scherm streamt het bestand elke keer opnieuw: houd het compact.
VIDEO_MAX_BYTES = 80 * 1024 * 1024


# Een formulier met een video is groter dan de gewone uploadlimiet van de site (zie app.py).
VIDEO_UPLOAD_MAX_BYTES = VIDEO_MAX_BYTES + 5 * 1024 * 1024


# De formulieren waar een video bij kan (zie routes/kiosk/sponsoren_sjablonen.py).
VIDEO_UPLOAD_ENDPOINTS = {"kiosk_sponsor_nieuw", "kiosk_sponsor_bewerken"}


_VIDEO_BESTANDSNAAM = re.compile(r"^[0-9a-f]{32}\.(mp4|m4v|mov|webm)$")


def _herkenbaar(begin, extensie):
    """Klopt het begin van het bestand met wat de extensie belooft? Voorkomt dat iets anders dan een video
    als video in de map belandt."""
    if extensie == ".webm":
        return begin[:4] == b"\x1a\x45\xdf\xa3"  # EBML-kop van webm/matroska
    return begin[4:8] == b"ftyp"  # mp4/mov: het eerste blok is altijd 'ftyp'


def mp4_duur(pad):
    """De lengte in seconden van een mp4/mov (uit het 'mvhd'-blok in 'moov'), of None als dat niet lukt
    (ook voor webm). Leest alleen blokkoppen en het moov-blok, nooit het hele bestand."""
    try:
        with open(pad, "rb") as f:
            f.seek(0, 2)
            totaal = f.tell()
            positie = 0
            while positie + 8 <= totaal:
                f.seek(positie)
                kop = f.read(8)
                grootte, soort = struct.unpack(">I4s", kop)
                kopgrootte = 8
                if grootte == 1:  # 64-bits grootte
                    grootte = struct.unpack(">Q", f.read(8))[0]
                    kopgrootte = 16
                elif grootte == 0:  # tot het einde van het bestand
                    grootte = totaal - positie
                if grootte < kopgrootte:
                    return None
                if soort == b"moov":
                    if grootte > 32 * 1024 * 1024:
                        return None
                    inhoud = f.read(grootte - kopgrootte)
                    return _duur_uit_moov(inhoud)
                positie += grootte
    except (OSError, struct.error):
        return None
    return None


def _duur_uit_moov(moov):
    """Zoek 'mvhd' in de inhoud van het moov-blok en geef de duur in seconden (of None)."""
    positie = 0
    while positie + 8 <= len(moov):
        grootte, soort = struct.unpack(">I4s", moov[positie : positie + 8])
        if grootte < 8:
            return None
        if soort == b"mvhd":
            deel = moov[positie + 8 : positie + grootte]
            if not deel:
                return None
            if deel[0] == 1:  # versie 1: 64-bits tijden en duur
                tijdschaal, duur = struct.unpack(">IQ", deel[20:32])
            else:  # versie 0
                tijdschaal, duur = struct.unpack(">II", deel[12:20])
            return duur / tijdschaal if tijdschaal else None
        positie += grootte
    return None


# Automatisch verkleinen (als ffmpeg op de server staat): een zware video (bijv. een opname van een iPhone of Mac van
# 15-20 Mbit/s) wordt een mp4 van hooguit 720p en ongeveer 3 Mbit/s. Zo laadt hij snel op de tv en kost hij weinig ruimte.
VIDEO_VERKLEIN_VANAF_MBIT = 4.5  # lichter dan dit blijft zoals het is
VIDEO_VERKLEIN_ONBEKEND_VANAF_BYTES = 6 * 1024 * 1024  # als de lengte niet te lezen is (webm): groter dan dit
VIDEO_MAX_ZIJDE = 1280  # px, de langste zijde (720p liggend of staand)
VIDEO_VERKLEIN_MAX_SECONDEN = 120  # langere video's verkleinen kost te veel rekentijd op de server
VIDEO_VERKLEIN_TIMEOUT = 240  # seconden; daarna stoppen we en blijft het origineel staan


def ffmpeg_pad():
    """Waar ffmpeg staat: de omgevingsvariabele FFMPEG_PAD (voor tests/ontwikkeling) of anders het commando 'ffmpeg'."""
    return os.environ.get("FFMPEG_PAD") or shutil.which("ffmpeg")


def ffmpeg_beschikbaar():
    return bool(ffmpeg_pad())


def _verklein_commando(ffmpeg, pad_in, pad_uit):
    zijde = VIDEO_MAX_ZIJDE
    return [
        ffmpeg, "-v", "error", "-y", "-i", str(pad_in),
        # De langste zijde hooguit 1280 px, de verhouding blijft gelijk (ook voor staande telefoonvideo's).
        "-vf", f"scale=w='if(gt(iw,ih),min({zijde},iw),-2)':h='if(gt(iw,ih),-2,min({zijde},ih))'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-maxrate", "4M", "-bufsize", "8M",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "96k", "-ac", "2",
        str(pad_uit),
    ]


def _mb(bytes_):
    return bytes_ / (1024 * 1024)


def _verklein(pad, duur, doelmap, meldingen):
    """Probeert het bestand op 'pad' te verkleinen. Geeft (nieuwe_naam, nieuwe_duur) als dat lukte en het bestand echt
    kleiner werd (het origineel is dan weggehaald), anders None (het origineel blijft staan)."""
    ffmpeg = ffmpeg_pad()
    grootte = pad.stat().st_size
    mbit = grootte * 8 / duur / 1_000_000 if duur else None
    if mbit is not None and mbit <= VIDEO_VERKLEIN_VANAF_MBIT:
        return None  # is al licht genoeg
    if mbit is None and grootte <= VIDEO_VERKLEIN_ONBEKEND_VANAF_BYTES:
        return None
    if duur and duur > VIDEO_VERKLEIN_MAX_SECONDEN:
        meldingen.append(
            f"De video duurt {duur:.0f} seconden: dat is te lang om automatisch te verkleinen "
            f"(maximaal {VIDEO_VERKLEIN_MAX_SECONDEN}). Hij is zoals hij was bewaard."
        )
        return None
    nieuwe_naam = f"{secrets.token_hex(16)}.mp4"
    nieuw_pad = Path(doelmap) / nieuwe_naam
    try:
        resultaat = subprocess.run(
            _verklein_commando(ffmpeg, pad, nieuw_pad), capture_output=True, timeout=VIDEO_VERKLEIN_TIMEOUT
        )
        gelukt = resultaat.returncode == 0 and nieuw_pad.exists() and nieuw_pad.stat().st_size > 0
    except (OSError, subprocess.SubprocessError):  # ffmpeg niet te starten, of te lang bezig
        gelukt = False
    if not gelukt or nieuw_pad.stat().st_size >= grootte * 0.9:
        nieuw_pad.unlink(missing_ok=True)
        meldingen.append(
            "De video is niet kleiner te maken (of het werd geen duidelijke winst): hij is zoals hij was bewaard."
            if gelukt else "Automatisch verkleinen lukte niet: de video is zoals hij was bewaard."
        )
        return None
    nieuwe_duur = mp4_duur(nieuw_pad) or duur
    meldingen.append(
        f"De video is automatisch verkleind van {_mb(grootte):.1f} MB naar {_mb(nieuw_pad.stat().st_size):.1f} MB."
    )
    pad.unlink(missing_ok=True)
    return nieuwe_naam, nieuwe_duur


def sla_video_op(bestand, doelmap=None, verkleinen=False, meldingen=None):
    """Slaat een geuploade video op onder een willekeurige naam. Geeft (bestandsnaam, duur_in_seconden, None)
    of (None, None, foutmelding); (None, None, None) als er geen bestand gekozen is. De duur is None als
    die niet te lezen is (bijv. bij webm). Met verkleinen=True en ffmpeg op de server wordt een zware video
    kleiner gemaakt (zie _verklein); wat daarbij gebeurde komt als tekst in de lijst 'meldingen'."""
    if not bestand or not bestand.filename:
        return None, None, None
    meldingen = meldingen if meldingen is not None else []
    doelmap = Path(doelmap or KIOSK_VIDEOS_MAP)
    extensie = Path(bestand.filename).suffix.lower()
    if extensie not in TOEGESTANE_VIDEO_EXTENSIES:
        return None, None, "Dit bestandstype kan niet: gebruik een video als mp4 (liefst), mov of webm."
    begin = bestand.stream.read(16)
    bestand.stream.seek(0)
    if not _herkenbaar(begin, extensie):
        return None, None, "Dit lijkt geen echte video: probeer een mp4-bestand."
    doelmap.mkdir(parents=True, exist_ok=True)
    naam = f"{secrets.token_hex(16)}{extensie}"
    pad = doelmap / naam
    bestand.save(pad)
    if pad.stat().st_size > VIDEO_MAX_BYTES:
        pad.unlink(missing_ok=True)
        return None, None, f"De video is te groot (maximaal {VIDEO_MAX_BYTES // (1024 * 1024)} MB). Maak 'm kleiner of korter."
    duur = mp4_duur(pad) if extensie != ".webm" else None
    if verkleinen and ffmpeg_beschikbaar():
        verkleind = _verklein(pad, duur, doelmap, meldingen)
        if verkleind:
            naam, duur = verkleind
    return naam, duur, None


# Boven zoveel Mbit/s is een video zwaar voor een gewone verbinding (een iPhone- of schermopname is al gauw 15-20).
VIDEO_ZWAAR_MBIT = 8


def eigen_videobestand(bestandsnaam):
    """Is dit een bestandsnaam zoals sla_video_op ze maakt (en dus van de site zelf)?"""
    return bool(bestandsnaam and _VIDEO_BESTANDSNAAM.match(bestandsnaam))


def video_info(bestandsnaam, duur, doelmap=None):
    """{'mb', 'mbit', 'zwaar'} van een opgeslagen video (mbit is None als de lengte onbekend is), of None als het
    bestand er niet is. Voor de waarschuwing bij een te zware video."""
    if not bestandsnaam or not _VIDEO_BESTANDSNAAM.match(bestandsnaam):
        return None
    try:
        bytes_ = (Path(doelmap or KIOSK_VIDEOS_MAP) / bestandsnaam).stat().st_size
    except OSError:
        return None
    mbit = bytes_ * 8 / duur / 1_000_000 if duur else None
    return {"bytes": bytes_, "mb": bytes_ / (1024 * 1024), "mbit": mbit, "zwaar": bool(mbit and mbit > VIDEO_ZWAAR_MBIT)}


def zwaarte_melding(info, duur):
    """De waarschuwing voor een te zware video (of None)."""
    if not info or not info["zwaar"]:
        return None
    return (
        f"Let op: deze video is zwaar ({info['mb']:.1f} MB voor {duur:.0f} seconden, ongeveer {info['mbit']:.0f} Mbit/s). "
        "Het scherm moet 'm eerst helemaal binnenhalen en dat duurt op een trage verbinding even; tot die tijd slaat "
        "het de dia over. Handiger: maak 'm kleiner, bijvoorbeeld 720p en rond de 3 Mbit/s "
        "(op een Mac: QuickTime Player, Bestand, Exporteer als, 720p)."
    )


def verwijder_video(bestandsnaam, doelmap=None):
    """Haalt een opgeslagen video weg (alleen bestanden die door sla_video_op zijn gemaakt)."""
    if not bestandsnaam or not _VIDEO_BESTANDSNAAM.match(bestandsnaam):
        return
    (Path(doelmap or KIOSK_VIDEOS_MAP) / bestandsnaam).unlink(missing_ok=True)
