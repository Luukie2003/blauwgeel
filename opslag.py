"""Hoeveel schijfruimte de site gebruikt (database, back-ups, uploads, programma) en wat het meeste inneemt.

De hosting rekent per account met een vaste hoeveelheid schijfruimte. Video's en foto's nemen die snel in; dit overzicht
laat zien waar het zit, waarschuwt op het dashboard als het bijna vol is en ruimt video's op die bij geen enkele dia
meer horen. Gemeten wordt de map van de site zelf; de hosting telt soms meer mee (bijvoorbeeld geïnstalleerde
pakketten), dus het getal bij "Beschikbaar" is een schatting die je zelf instelt."""

import os
import time
from pathlib import Path

from flask import current_app

import helpers.video as video_module
from helpers import BASE_DIR

STANDAARD_QUOTA_MB = 1024
WAARSCHUWING_PCT = 80
KRITIEK_PCT = 95
AANTAL_GROOTSTE = 10
CACHE_SECONDEN = 300
CACHE_AAN = True

# Mappen die niet meetellen: lokaal staan er een virtuele omgeving en werkmappen, op de server niet.
NEGEER = {"venv", ".claude", "node_modules"}

# (naam, paden relatief aan de map van de site). Wat nergens onder valt, is "Programma en overig".
ONDERDELEN = [
    ("Database", ["voorraad.db", "voorraad.db-wal", "voorraad.db-shm"]),
    ("Back-ups", ["backups"]),
    ("Video's (kantine-tv)", ["static/kiosk_videos"]),
    ("Foto's kantine-tv (sponsors, achtergronden)", ["static/kiosk_afbeeldingen"]),
    ("Productfoto's", ["static/product_afbeeldingen"]),
    ("Clublogo's", ["static/club_logos"]),
    ("Stemfoto's", ["static/stem_afbeeldingen"]),
]
OVERIG = "Programma en overig"

_cache = {}


def opslag_map():
    """De map die gemeten wordt (in de tests een lege wegwerpmap)."""
    return Path(current_app.config.get("OPSLAG_MAP", BASE_DIR))


def groottetekst(bytes_):
    """'1,3 GB', '12,3 MB' of '45 kB', met een komma zoals in het Nederlands."""
    if bytes_ >= 1024 ** 3:
        waarde, eenheid = bytes_ / 1024 ** 3, "GB"
    elif bytes_ >= 1024 ** 2:
        waarde, eenheid = bytes_ / 1024 ** 2, "MB"
    else:
        return f"{max(1, round(bytes_ / 1024)) if bytes_ else 0} kB"
    return f"{waarde:.1f}".replace(".", ",") + f" {eenheid}"


def _onderdeel_van(relatief):
    for naam, paden in ONDERDELEN:
        for pad in paden:
            if relatief == pad or relatief.startswith(pad + "/"):
                return naam
    return OVERIG


def bereken_opslag(basis, quota_mb):
    """Meet de map 'basis': {'totaal', 'quota', 'percentage', 'niveau', 'onderdelen', 'grootste'}.
    niveau is 'ok', 'let_op' (vanaf WAARSCHUWING_PCT) of 'kritiek' (vanaf KRITIEK_PCT)."""
    basis = Path(basis)
    per_onderdeel = {naam: [0, 0] for naam, _ in ONDERDELEN}
    per_onderdeel[OVERIG] = [0, 0]
    bestanden = []
    for map_, submappen, namen in os.walk(basis):
        submappen[:] = [m for m in submappen if m not in NEGEER]
        for naam in namen:
            pad = Path(map_) / naam
            try:
                if pad.is_symlink():
                    continue
                grootte = pad.stat().st_size
            except OSError:
                continue
            relatief = pad.relative_to(basis).as_posix()
            teller = per_onderdeel[_onderdeel_van(relatief)]
            teller[0] += grootte
            teller[1] += 1
            bestanden.append((grootte, relatief))
    totaal = sum(g for g, _ in per_onderdeel.values())
    quota = max(1, quota_mb) * 1024 * 1024
    percentage = totaal / quota * 100
    bestanden.sort(reverse=True)
    return {
        "totaal": totaal,
        "quota": quota,
        "percentage": percentage,
        "niveau": "kritiek" if percentage >= KRITIEK_PCT else "let_op" if percentage >= WAARSCHUWING_PCT else "ok",
        "onderdelen": sorted(
            (
                {"naam": naam, "bytes": g, "aantal": n, "aandeel": g / totaal * 100 if totaal else 0}
                for naam, (g, n) in per_onderdeel.items()
                if n
            ),
            key=lambda o: -o["bytes"],
        ),
        "grootste": [{"bytes": g, "pad": p} for g, p in bestanden[:AANTAL_GROOTSTE]],
    }


def lees_quota_mb(db):
    rij = db.execute("SELECT opslag_quota_mb FROM instellingen WHERE id = 1").fetchone()
    return rij["opslag_quota_mb"] if rij and rij["opslag_quota_mb"] else STANDAARD_QUOTA_MB


def opslag_status(db, vers=False):
    """bereken_opslag voor de site, hooguit CACHE_SECONDEN oud (het dashboard vraagt dit bij elk bezoek)."""
    basis, quota_mb = opslag_map(), lees_quota_mb(db)
    sleutel = (str(basis), quota_mb)
    if CACHE_AAN and not vers:
        bewaard = _cache.get(sleutel)
        if bewaard and time.monotonic() - bewaard[0] < CACHE_SECONDEN:
            return bewaard[1]
    uitkomst = bereken_opslag(basis, quota_mb)
    _cache[sleutel] = (time.monotonic(), uitkomst)
    return uitkomst


def wis_cache():
    _cache.clear()


def bewaar_quota_mb(db, quota_mb):
    db.execute("UPDATE instellingen SET opslag_quota_mb = ? WHERE id = 1", (max(50, min(1_000_000, quota_mb)),))
    db.commit()
    wis_cache()


# ---------- Video's ----------


def video_gebruik(db):
    """{bestandsnaam: {'titel', 'actief'}} van de video's die bij een dia horen."""
    return {
        r["video"]: {"titel": r["titel"] or "zonder titel", "actief": bool(r["actief"])}
        for r in db.execute("SELECT titel, actief, video FROM kiosk_sponsoren WHERE video IS NOT NULL").fetchall()
    }


def ongebruikte_videos(db):
    """[(bestandsnaam, bytes)] van video's in de videomap die bij geen enkele dia horen (bijv. na een mislukte
    upload). Alleen bestanden die de site zelf heeft gemaakt."""
    map_ = Path(video_module.KIOSK_VIDEOS_MAP)
    if not map_.exists():
        return []
    gebruikt = video_gebruik(db)
    return [
        (pad.name, pad.stat().st_size)
        for pad in sorted(map_.iterdir())
        if video_module.eigen_videobestand(pad.name) and pad.name not in gebruikt
    ]


def verwijder_ongebruikte_videos(db):
    """Haalt ongebruikte video's weg; geeft (aantal, bytes) terug."""
    weg = ongebruikte_videos(db)
    for naam, _ in weg:
        video_module.verwijder_video(naam)
    wis_cache()
    return len(weg), sum(g for _, g in weg)
