"""Eenmalig hulpscript om productfoto's te downloaden en te koppelen.

Gebruik: python3 scripts/zet_product_afbeelding.py <product_id> <image_url>

Downloadt de afbeelding, controleert of het een geldige, redelijk grote
afbeelding is (min. 400px breed/hoog), slaat 'm op in
static/product_afbeeldingen/ met dezelfde willekeurige-bestandsnaam-conventie
als de reguliere upload (sla_afbeelding_op in app.py), en zet de kolom
producten.afbeelding. Geen onderdeel van de applicatie zelf.
"""
import secrets
import sqlite3
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
DOELMAP = BASE_DIR / "static" / "product_afbeeldingen"
DB_PAD = BASE_DIR / "voorraad.db"
MIN_AFMETING = 300

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def main():
    product_id = int(sys.argv[1])
    url = sys.argv[2]

    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()

    img = Image.open(BytesIO(data))
    breedte, hoogte = img.size
    if breedte < MIN_AFMETING and hoogte < MIN_AFMETING:
        print(f"AFGEWEZEN: te klein ({breedte}x{hoogte}) -- {url}")
        sys.exit(1)

    formaat = (img.format or "JPEG").lower()
    # webp altijd naar jpeg converteren (verliest transparantie, maar is
    # overal gegarandeerd te tonen); de extensie wordt PAS na deze keuze
    # bepaald zodat bestandsnaam en werkelijk opgeslagen formaat altijd matchen.
    if formaat == "webp":
        formaat = "jpeg"
        img = img.convert("RGB")

    extensie = {"jpeg": ".jpg", "png": ".png", "gif": ".gif"}.get(formaat, ".jpg")
    DOELMAP.mkdir(parents=True, exist_ok=True)
    bestandsnaam = f"{secrets.token_hex(16)}{extensie}"
    if formaat == "jpeg" and (img.format or "").lower() != "jpeg":
        img.save(DOELMAP / bestandsnaam, "JPEG", quality=90)
    else:
        (DOELMAP / bestandsnaam).write_bytes(data)

    db = sqlite3.connect(DB_PAD)
    db.execute("UPDATE producten SET afbeelding = ? WHERE id = ?", (bestandsnaam, product_id))
    db.commit()
    db.close()

    print(f"OK: product {product_id} -> {bestandsnaam} ({breedte}x{hoogte}, {formaat})")


if __name__ == "__main__":
    main()
