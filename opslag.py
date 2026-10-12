"""Hoeveel schijfruimte de site gebruikt (database, back-ups, uploads, programma) en wat het meeste inneemt.

De hosting rekent per account met een vaste hoeveelheid schijfruimte. Video's en foto's nemen die snel in; dit overzicht
laat zien waar het zit, waarschuwt op het dashboard als het bijna vol is en ruimt video's op die bij geen enkele dia
meer horen. Gemeten wordt de map van de site zelf; de hosting telt soms meer mee (bijvoorbeeld geïnstalleerde
pakketten), dus het getal bij "Beschikbaar" is een schatting die je zelf instelt.

Alle bestanden langslopen duurt op de server enkele seconden. Het dashboard doet dat daarom nooit zelf: de dagelijkse
back-uptaak (backup.py) en de pagina Beheer > Opslag meten en bewaren het totaal in de database, het dashboard leest
alleen dat getal. Bovenin staat daarom alleen de standaardbibliotheek, want backup.py draait zonder virtualenv."""

import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
STANDAARD_QUOTA_MB = 1024
WAARSCHUWING_PCT = 80
KRITIEK_PCT = 95
AANTAL_GROOTSTE = 10

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


def opslag_map():
    """De map die gemeten wordt (in de tests een lege wegwerpmap)."""
    from flask import current_app

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


def _vulgraad(totaal, quota_mb):
    """(quota in bytes, percentage, niveau): niveau is 'ok', 'let_op' (vanaf WAARSCHUWING_PCT) of 'kritiek'."""
    quota = max(1, quota_mb) * 1024 * 1024
    percentage = totaal / quota * 100
    niveau = "kritiek" if percentage >= KRITIEK_PCT else "let_op" if percentage >= WAARSCHUWING_PCT else "ok"
    return quota, percentage, niveau


def bereken_opslag(basis, quota_mb):
    """Meet de map 'basis': {'totaal', 'quota', 'percentage', 'niveau', 'onderdelen', 'grootste'}."""
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
    quota, percentage, niveau = _vulgraad(totaal, quota_mb)
    bestanden.sort(reverse=True)
    return {
        "totaal": totaal,
        "quota": quota,
        "percentage": percentage,
        "niveau": niveau,
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
    return rij[0] if rij and rij[0] else STANDAARD_QUOTA_MB


def meet_en_bewaar(db, basis):
    """Meet de map 'basis' en bewaart het totaal in de database (zodat het dashboard het kan tonen zonder
    zelf alle bestanden langs te lopen). db mag een gewone sqlite3-verbinding zijn."""
    uitkomst = bereken_opslag(basis, lees_quota_mb(db))
    db.execute(
        "UPDATE instellingen SET opslag_gemeten_bytes = ?, opslag_gemeten_op = ? WHERE id = 1",
        (uitkomst["totaal"], datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    db.commit()
    return uitkomst


def opslag_status(db):
    """Meet de site nu (dat kan enkele seconden duren) en bewaart het totaal voor het dashboard."""
    return meet_en_bewaar(db, opslag_map())


def laatst_gemeten(db):
    """{'totaal', 'quota', 'percentage', 'niveau', 'gemeten_op'} van de laatste meting, zonder iets te meten,
    of None als er nog niet gemeten is. Het percentage volgt de huidige instelling van "Beschikbaar"."""
    rij = db.execute("SELECT opslag_gemeten_bytes, opslag_gemeten_op FROM instellingen WHERE id = 1").fetchone()
    if not rij or rij[0] is None:
        return None
    quota, percentage, niveau = _vulgraad(rij[0], lees_quota_mb(db))
    return {"totaal": rij[0], "quota": quota, "percentage": percentage, "niveau": niveau, "gemeten_op": rij[1]}


def bewaar_quota_mb(db, quota_mb):
    db.execute("UPDATE instellingen SET opslag_quota_mb = ? WHERE id = 1", (max(50, min(1_000_000, quota_mb)),))
    db.commit()


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
    import helpers.video as video_module

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
    import helpers.video as video_module

    weg = ongebruikte_videos(db)
    for naam, _ in weg:
        video_module.verwijder_video(naam)
    return len(weg), sum(g for _, g in weg)
