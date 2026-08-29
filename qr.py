"""Genereert een scanbare QR-code als inline SVG voor de stemlinks. Gebruikt
de SVG-image-factory van qrcode -- geen Pillow nodig, geen externe dienst
(handig, want er is geen internetverbinding nodig om 'm te tonen/printen)."""

import io

import qrcode
import qrcode.image.svg


def qr_svg(inhoud):
    afbeelding = qrcode.make(
        inhoud, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2
    )
    buffer = io.BytesIO()
    afbeelding.save(buffer)
    return buffer.getvalue().decode("utf-8")
