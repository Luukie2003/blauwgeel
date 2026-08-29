"""Genereert een scanbare QR-code voor de stemlinks -- als inline SVG voor
op de website, en als PNG voor in de geprinte poster (fpdf2 kan geen SVG
plakken). Beide zonder Pillow: de SVG-factory van qrcode heeft niks extra
nodig, de PNG-factory (PyPNGImage) leunt op het kleine, pure-Python pypng."""

import io

import qrcode
import qrcode.image.svg
from qrcode.image.pure import PyPNGImage


def qr_svg(inhoud):
    afbeelding = qrcode.make(
        inhoud, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2
    )
    buffer = io.BytesIO()
    afbeelding.save(buffer)
    return buffer.getvalue().decode("utf-8")


def qr_png_bytes(inhoud):
    afbeelding = qrcode.make(inhoud, image_factory=PyPNGImage, box_size=10, border=2)
    buffer = io.BytesIO()
    afbeelding.save(buffer)
    return buffer.getvalue()
