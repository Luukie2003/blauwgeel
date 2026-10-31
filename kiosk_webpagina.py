"""Een webpagina als dia (1.81.0, sjabloon webpagina), zoals de tussenstand van Shout-out!.

De site haalt de pagina zelf op en geeft hem door aan de tv's, zonder wat daar niet hoort (KIOSK_WEBPAGINA_VERBERGEN,
zoals het blok met de QR-code om mee te spelen). Het doorgeven gebeurt afgeschermd (CSP hieronder, met sandbox): de
scripts van die site draaien dan niet als deze site, en kunnen niet bij inloggegevens of pagina's van het beheer. De
pagina haalt zijn gegevens zelf op; alleen de opmaak komt hiervandaan, en die bewaart elk serverproces een paar minuten.
Lukt het ophalen niet, dan toont de tv de pagina zoals hij is (routes/kiosk/scherm.py)."""

import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from markupsafe import escape

from helpers import KIOSK_WEBPAGINA_SITES, KIOSK_WEBPAGINA_VERBERGEN

BEWAAR_SECONDEN = 300
MAX_BYTES = 3 * 1024 * 1024
_SITES = " ".join(f"https://{site}" for site in KIOSK_WEBPAGINA_SITES)

# Voor de doorgegeven pagina: sandbox zonder allow-same-origin, dus een eigen, afgeschermde herkomst (ook als iemand het
# adres los opent). Wat de pagina zelf ophaalt (lettertypes, gegevens, plaatjes) mag via https.
CSP = (
    "sandbox allow-scripts; default-src 'none'; "
    f"script-src 'unsafe-inline' {_SITES}; style-src 'unsafe-inline' https:; font-src https: data:; "
    f"img-src https: data: blob:; media-src https: data: blob:; connect-src https: wss:; base-uri {_SITES}"
)

_BEWAARD = {}


class _GeenDoorverwijzing(urllib.request.HTTPRedirectHandler):
    """Niet meegaan naar een ander adres: alleen de sites uit KIOSK_WEBPAGINA_SITES worden opgehaald."""

    def redirect_request(self, *args, **kwargs):
        return None


def toegestaan(adres):
    """Of dit adres op een tv mag: https en een site uit KIOSK_WEBPAGINA_SITES."""
    deel = urlsplit(adres or "")
    return deel.scheme == "https" and deel.hostname in KIOSK_WEBPAGINA_SITES


def zonder_extra(html, adres):
    """De pagina met direct na <head> een <base> (zodat verwijzingen naar de site zelf blijven gaan) en de stijl die
    verbergt wat op de tv niet hoort."""
    extra = f'<base href="{escape(adres)}">'
    verbergen = KIOSK_WEBPAGINA_VERBERGEN.get(urlsplit(adres).hostname)
    if verbergen:
        extra += f"<style>{verbergen}{{display:none!important}}</style>"
    kop = re.search(r"<head\b[^>]*>", html, re.IGNORECASE)
    return html[: kop.end()] + extra + html[kop.end():] if kop else extra + html


def opgehaald(adres, nu=None):
    """De pagina op adres zoals de tv hem krijgt (zie zonder_extra), of None als hij niet op te halen is. Lukt het
    ophalen even niet, dan de vorige versie."""
    if not toegestaan(adres):
        return None
    nu = time.monotonic() if nu is None else nu
    bewaard = _BEWAARD.get(adres)
    if bewaard and nu - bewaard[0] < BEWAAR_SECONDEN:
        return bewaard[1]
    try:
        verzoek = urllib.request.Request(adres, headers={"User-Agent": "KantineBlauwGeel (kantine-tv)"})
        with urllib.request.build_opener(_GeenDoorverwijzing).open(verzoek, timeout=6) as antwoord:
            if "html" not in (antwoord.headers.get("Content-Type") or ""):
                return None
            ruw = antwoord.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return bewaard[1] if bewaard else None
    if len(ruw) > MAX_BYTES:
        return None
    pagina = zonder_extra(ruw.decode("utf-8", errors="replace"), adres)
    _BEWAARD[adres] = (nu, pagina)
    return pagina
