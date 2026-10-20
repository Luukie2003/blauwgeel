"""Achtergrond voor het startscherm van de Zebra TC51 (720×1280), in de stijl van de handterminal-app: navy met geel,
het clublogo, en twee vakken om apps in te zetten: "Betaling" (de PayPal-app) en "Beheer" (Kantine Handterminal).
Daarnaast dezelfde achtergrond zonder de vakken, voor het ontgrendelscherm.

    venv/bin/python android-apps/achtergrond-tc51/maak_achtergrond.py

Schuif de vakken met BETALING_Y/BEHEER_Y als ze niet precies op de rijen van de launcher vallen."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HIER = Path(__file__).resolve().parent
LOGO = HIER.parent / "handterminal/src/main/res/drawable-nodpi/clublogo.png"
UIT = HIER / "tc51-achtergrond.png"
UIT_ONTGRENDEL = HIER / "tc51-ontgrendelscherm.png"

S = 3  # eerst groter tekenen, dan verkleinen: gladde randen
B, H = 720, 1280

# Dezelfde kleuren als res/values/colors.xml van de app.
NAVY = (0x1C, 0x2B, 0x4A)
NAVY_DONKER = (0x0F, 0x1A, 0x30)
NAVY_LICHT = (0x2A, 0x3D, 0x63)
GEEL = (0xFC, 0xD4, 0x2F)
TEKST_ZACHT = (0xA9, 0xB3, 0xCC)

# Bovenkant van de vakken (in pixels van het scherm), hoogte per vak.
BETALING_Y = 330
BEHEER_Y = 690
VAK_H = 300
MARGE = 28

LETTER = "/System/Library/Fonts/Avenir Next.ttc"


def font(grootte, index=0):
    # Avenir Next.ttc: 0 = Bold, 2 = Demi Bold, 7 = Regular (macOS)
    return ImageFont.truetype(LETTER, grootte * S, index=index)


def verloop(img):
    """Van boven naar beneden: navy_licht → navy → navy_donker, zoals achtergrond_inlog.xml."""
    d = ImageDraw.Draw(img)
    h = img.height
    for y in range(h):
        t = y / (h - 1)
        if t < 0.5:
            a, b, f = NAVY_LICHT, NAVY, t / 0.5
        else:
            a, b, f = NAVY, NAVY_DONKER, (t - 0.5) / 0.5
        d.line([(0, y), (img.width, y)], fill=tuple(round(a[i] + (b[i] - a[i]) * f) for i in range(3)))


def vak(laag, y, titel):
    d = ImageDraw.Draw(laag)
    x0, y0, x1, y1 = MARGE * S, y * S, (B - MARGE) * S, (y + VAK_H) * S
    # Vlak zoals de knoppen op navy in de app (knop_op_navy, knop_op_navy_rand), met een gele streep links.
    d.rounded_rectangle([x0, y0, x1, y1], radius=26 * S, fill=(255, 255, 255, 16), outline=(255, 255, 255, 56), width=2 * S)
    d.rounded_rectangle([x0 + 12 * S, y0 + 40 * S, x0 + 18 * S, y1 - 40 * S], radius=3 * S, fill=GEEL + (255,))
    # Label: gele pil met navy tekst, op de bovenrand.
    f = font(24)
    tb = d.textbbox((0, 0), titel.upper(), font=f)
    pw, ph = tb[2] - tb[0] + 44 * S, 46 * S
    px, py = x0 + 30 * S, y0 - ph // 2
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=ph // 2, fill=GEEL + (255,))
    d.text((px + pw / 2, py + ph / 2), titel.upper(), font=f, fill=NAVY + (255,), anchor="mm")


def maak(uit, met_vakken):
    img = Image.new("RGB", (B * S, H * S))
    verloop(img)
    img = img.convert("RGBA")

    logo = Image.open(LOGO).convert("RGBA")

    # Groot, vaag clublogo als watermerk onderaan (achter het dock).
    w = 720 * S
    groot = logo.resize((w, w), Image.LANCZOS)
    alfa = groot.getchannel("A").point(lambda v: v * 0.07)
    groot.putalpha(alfa)
    img.alpha_composite(groot, (int(B * S * 0.32), int(H * S * 0.66)))

    laag = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(laag)

    # Kop: logo in een gele kring (zoals logo_kring.xml), de naam en een gele streep.
    k = 132 * S
    kx, ky = MARGE * S + 4 * S, 92 * S
    d.ellipse([kx, ky, kx + k, ky + k], fill=(255, 255, 255, 26), outline=GEEL + (255,), width=3 * S)
    klein = logo.resize((k - 24 * S, k - 24 * S), Image.LANCZOS)
    laag.alpha_composite(klein, (kx + 12 * S, ky + 10 * S))
    tx = kx + k + 26 * S
    d.text((tx, ky + 40 * S), "Kantine", font=font(44), fill=(255, 255, 255, 255), anchor="ls")
    d.text((tx, ky + 92 * S), "Blauw-Geel", font=font(44), fill=GEEL + (255,), anchor="ls")
    d.text((tx, ky + 124 * S), "HANDTERMINAL", font=font(17, 2), fill=TEKST_ZACHT + (255,), anchor="ls")

    if met_vakken:
        vak(laag, BETALING_Y, "Betaling")
        vak(laag, BEHEER_Y, "Beheer")
    img.alpha_composite(laag)

    img.convert("RGB").resize((B, H), Image.LANCZOS).save(uit, optimize=True)
    print(uit)


def main():
    maak(UIT, met_vakken=True)
    maak(UIT_ONTGRENDEL, met_vakken=False)


if __name__ == "__main__":
    main()
