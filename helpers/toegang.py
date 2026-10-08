"""Rollen, secties (rechten) en wachtwoord-tokens."""

import hashlib
import secrets
from datetime import datetime, timedelta


def genereer_wachtwoord_token(db, gebruiker_id, geldig_uren):
    """Maakt een eenmalige, tijdelijke link-token om een wachtwoord in te
    stellen (gebruikt voor zowel account-activatie als wachtwoord-vergeten).
    Er wordt alleen een hash van de token opgeslagen -- niet de token zelf --
    zodat een gelekte database-backup geen bruikbare inlogtokens bevat."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    verloopt = (datetime.now() + timedelta(hours=geldig_uren)).strftime("%Y-%m-%d %H:%M")
    db.execute(
        "UPDATE gebruikers SET reset_token_hash = ?, reset_token_verloopt = ? WHERE id = ?",
        (token_hash, verloopt, gebruiker_id),
    )
    db.commit()
    return token


def vind_gebruiker_bij_token(db, token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    gebruiker = db.execute(
        "SELECT * FROM gebruikers WHERE reset_token_hash = ?", (token_hash,)
    ).fetchone()
    if gebruiker is None or not gebruiker["reset_token_verloopt"]:
        return None
    verloopt = datetime.strptime(gebruiker["reset_token_verloopt"], "%Y-%m-%d %H:%M")
    if verloopt < datetime.now():
        return None
    return gebruiker


# Fijnmazige rechten voor vrijwilligers: naast de rol (beheerder/vrijwilliger)
# heeft elk account een los aan/uit-vinkje per sectie. Beheerders hebben altijd
# overal toegang, ongeacht wat er in hun secties-kolom staat -- die kolom doet
# er voor hen simpelweg niet toe. "Algemeen" (dashboard, bijzonderheden e.d.)
# heeft bewust geen sectie: dat blijft voor iedereen zichtbaar, zoals nu.
SECTIES = ["voorraad", "kassa", "keuken", "stemmen", "kantine_tv", "club_van_20", "club"]


SECTIE_LABELS = {
    "voorraad": "Voorraad",
    "kassa": "Kassa",
    "keuken": "Keuken",
    "stemmen": "Stemmen",
    "kantine_tv": "Kantine-tv",
    "club_van_20": "Club van 20",
    "club": "Club instellingen",
}


def secties_lijst(secties_tekst):
    """Zet de opgeslagen 'voorraad,kassa'-tekst om in een set van geldige
    sectiesleutels. Onbekende/verouderde waarden worden genegeerd."""
    if not secties_tekst:
        return set()
    return {s for s in secties_tekst.split(",") if s in SECTIES}


def heeft_sectie_toegang(rol, secties_tekst, sectie):
    if rol == "beheerder":
        return True
    return sectie in secties_lijst(secties_tekst)
