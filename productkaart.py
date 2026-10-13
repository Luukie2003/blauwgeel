"""De productkaart netjes houden: vaste schrijfwijzen voor eenheden, een unieke artikelcode, en welke producten in de
gewone telling horen.

Eenheden waren vrije tekst, waardoor er 'Fles' en 'Flesje', 'stuks' en 'Blik' en 'Karton' en 'Doos' door elkaar
stonden. Op de productkaart kies je nu uit een vaste lijst (met 'Anders' voor een uitzondering); wat je typt en in de
lijst voorkomt, krijgt de schrijfwijze uit de lijst. De gegevenscontrole (gegevenscontrole.py) wijst aan wat er niet in
staat."""

# Op deze volgorde in de keuzelijst; de meest gebruikte bovenaan.
EENHEDEN = ["Fles", "Blik", "Zakje", "Reep", "Stuks", "Portie", "Fust", "Glas", "Pitcher", "Los", "Tray"]
BESTELEENHEDEN = ["Krat", "Doos", "Karton", "Tray", "Zak", "Pak", "Fust", "Fles", "Los"]
ANDERS = "__anders__"

# De keuken heeft een eigen module met een eigen telling (zie keuken.py); die producten staan niet in de gewone telling.
KEUKEN_CATEGORIE = "Keuken"

# Welke producten in de gewone telling (Voorraad tellen, de looplijst) horen: actief, niet uitgezet met 'Niet tellen'
# (bijvoorbeeld een kassaknop zonder eigen voorraad) en niet van de keuken.
TELLEN_VOORWAARDE = f"actief = 1 AND COALESCE(niet_tellen, 0) = 0 AND categorie != '{KEUKEN_CATEGORIE}'"


def in_gewone_telling(product):
    """Hetzelfde als TELLEN_VOORWAARDE, voor een productrij die al is opgehaald."""
    try:
        niet_tellen = product["niet_tellen"]
    except (IndexError, KeyError):
        niet_tellen = 0
    return bool(product["actief"]) and not niet_tellen and product["categorie"] != KEUKEN_CATEGORIE


def normaliseer(tekst, lijst):
    """De schrijfwijze uit 'lijst' als 'tekst' daar (hoofdletters niet meegeteld) in staat, anders de tekst zoals hij
    is ingevuld, zonder spaties eromheen. Lege tekst geeft ''."""
    tekst = " ".join((tekst or "").split())
    for naam in lijst:
        if naam.lower() == tekst.lower():
            return naam
    return tekst


def eenheid_uit_formulier(form, veld, lijst):
    """De eenheid uit de keuzelijst 'veld', of uit het tekstvak '<veld>_anders' als daar 'Anders' is gekozen. Oudere
    formulieren (snel toevoegen, bulk bewerken) sturen gewoon tekst in 'veld': die werkt ook."""
    keuze = form.get(veld, "")
    if keuze == ANDERS:
        keuze = form.get(f"{veld}_anders", "")
    return normaliseer(keuze, lijst)


def artikelcode_in_gebruik(db, artikelcode, behalve_id=None):
    """De naam van een ander product met deze artikelcode, of None. Hoofdletters en spaties tellen niet mee."""
    code = (artikelcode or "").strip()
    if not code:
        return None
    rij = db.execute(
        "SELECT naam FROM producten WHERE UPPER(TRIM(artikelcode)) = UPPER(?) AND id != ? LIMIT 1",
        (code, behalve_id or 0),
    ).fetchone()
    return rij["naam"] if rij else None
