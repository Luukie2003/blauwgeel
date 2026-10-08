"""Opslaan en verkleinen van geuploade afbeeldingen (producten, stemopties, clublogo's, kiosk)."""

import io
import secrets
from pathlib import Path

from helpers.basis import BASE_DIR
from helpers.tijd import now_str


STEM_AFBEELDINGEN_MAP = BASE_DIR / "static" / "stem_afbeeldingen"


PRODUCT_AFBEELDINGEN_MAP = BASE_DIR / "static" / "product_afbeeldingen"


KIOSK_AFBEELDINGEN_MAP = BASE_DIR / "static" / "kiosk_afbeeldingen"


CLUB_LOGO_MAP = BASE_DIR / "static" / "club_logos"


TOEGESTANE_AFBEELDING_EXTENSIES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


AFBEELDING_MAX_AFMETING = 1600  # px, langste zijde


def _verkleind(bestand, extensie):
    """Verkleint/comprimeert een geuploade foto tot een redelijke maximale
    afmeting, zodat een foto rechtstreeks van een telefooncamera (soms
    2-3MB per stuk) niet onverkleind op de server belandt -- zie het
    gebruik/performance-onderzoek. Geeft de nieuwe bytes terug, of None als
    verkleinen niet lukte/niet van toepassing is (dan valt sla_afbeelding_op
    hieronder terug op de oorspronkelijke upload i.p.v. te crashen).
    .gif slaan we bewust over: Pillow bewaart zonder extra werk alleen de
    eerste frame, en dat zou een geanimeerd logo stilzetten."""
    if extensie == ".gif":
        return None
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        afbeelding = ImageOps.exif_transpose(Image.open(bestand))
        afbeelding.thumbnail((AFBEELDING_MAX_AFMETING, AFBEELDING_MAX_AFMETING), Image.LANCZOS)
        buffer = io.BytesIO()
        if extensie in (".jpg", ".jpeg"):
            if afbeelding.mode not in ("RGB", "L"):
                afbeelding = afbeelding.convert("RGB")
            afbeelding.save(buffer, format="JPEG", quality=85, optimize=True)
        elif extensie == ".webp":
            afbeelding.save(buffer, format="WEBP", quality=85)
        else:
            afbeelding.save(buffer, format="PNG", optimize=True)
    except Exception:
        # Onherkenbare/kapotte afbeeldingsdata mag de upload niet laten
        # crashen -- dan slaat sla_afbeelding_op de oorspronkelijke bytes op,
        # net als voorheen.
        return None
    return buffer.getvalue()


def sla_afbeelding_op(bestand, doelmap):
    """Slaat een geuploade afbeelding veilig op in doelmap (een willekeurige
    bestandsnaam, alleen bekende afbeeldingsextensies) en geeft de
    bestandsnaam terug. None als er niets bruikbaars is geupload."""
    if not bestand or not bestand.filename:
        return None
    extensie = Path(bestand.filename).suffix.lower()
    if extensie not in TOEGESTANE_AFBEELDING_EXTENSIES:
        return None
    doelmap.mkdir(parents=True, exist_ok=True)
    bestandsnaam = f"{secrets.token_hex(16)}{extensie}"
    verkleind = _verkleind(bestand, extensie)
    if verkleind is not None:
        (doelmap / bestandsnaam).write_bytes(verkleind)
    else:
        bestand.seek(0)
        bestand.save(doelmap / bestandsnaam)
    return bestandsnaam


def sla_stemoptie_afbeelding_op(bestand):
    return sla_afbeelding_op(bestand, STEM_AFBEELDINGEN_MAP)


def bewaar_bier(db, naam, afbeelding):
    """Bewaart een stemoptie-naam + foto in de bieren-bibliotheek zodat hij
    bij een volgende stemming hergebruikt kan worden. Bestond de naam al, dan
    wordt alleen de foto bijgewerkt (en enkel als er een nieuwe is)."""
    if not naam or not afbeelding:
        return
    db.execute(
        """INSERT INTO bieren (naam, afbeelding, aangemaakt_op) VALUES (?, ?, ?)
           ON CONFLICT(naam) DO UPDATE SET afbeelding = excluded.afbeelding""",
        (naam, afbeelding, now_str()),
    )


def sla_club_logo_op(bestand):
    return sla_afbeelding_op(bestand, CLUB_LOGO_MAP)


def bewaar_club_logo(db, club, afbeelding):
    """Zelfde register-idee als bewaar_bier hierboven, maar dan voor
    clublogo's op de standen-dia's (zie kiosk_stand_teams/kiosk_stand_poules
    in routes/kiosk.py): 1 keer een logo uploaden voor bijv. "Oranje Nassau",
    en elk team van die club (welke poule dan ook, dit of een volgend
    seizoen) gebruikt 'm automatisch. Bestond de club al, dan wordt alleen
    het logo bijgewerkt (en enkel als er een nieuwe is)."""
    if not club or not afbeelding:
        return
    db.execute(
        """INSERT INTO kiosk_club_logos (club, afbeelding, aangemaakt_op) VALUES (?, ?, ?)
           ON CONFLICT(club) DO UPDATE SET afbeelding = excluded.afbeelding""",
        (club, afbeelding, now_str()),
    )
