"""Kleine hulpjes voor verzoeken en antwoorden: CSRF, AJAX, CSV, veilige redirects, weergavemodus."""

import csv
import io
import re
import secrets

from flask import Response, request, session


WEERGAVE_TELEFOON_PATROON = re.compile(r"iPhone|iPod|Android.+Mobile", re.IGNORECASE)


def csv_response(bestandsnaam, kop, rijen):
    """Bouwt een CSV-downloadresponse. kop: lijst kolomnamen, rijen: lijst
    van lijsten/tuples in dezelfde volgorde. Puntkomma als scheidingsteken
    en een UTF-8 BOM vooraan, want dat is wat Excel met een Nederlandse
    landinstelling verwacht om het bestand meteen goed te openen."""
    buffer = io.StringIO()
    schrijver = csv.writer(buffer, delimiter=";")
    schrijver.writerow(kop)
    schrijver.writerows(rijen)
    return Response(
        "﻿" + buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={bestandsnaam}"},
    )


def csrf_token():
    """Geeft het CSRF-token voor de huidige sessie terug, en maakt er een aan
    als die nog niet bestaat. Wordt zowel gebruikt om het verborgen
    formuliersveld te vullen (via de context_processor) als om binnenkomende
    POSTs tegen te controleren (csrf_beschermen)."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def is_ajax_verzoek():
    """Detecteert of dit verzoek via de JS-laag (fetch, zie base.html) is
    verstuurd i.p.v. een gewone formulier-submit -- zulke routes geven dan
    JSON terug in plaats van een redirect, zodat de pagina niet hoeft te
    herladen voor een simpele statuswijziging."""
    return request.headers.get("X-Requested-With") == "fetch"


def veilig_redirect_pad(pad, fallback):
    """Voorkomt een open redirect via de 'next'-parameter na het inloggen:
    alleen een pad op de eigen site wordt geaccepteerd. //evil.nl en
    /\\evil.nl worden door sommige browsers als protocol-relatieve URL naar
    een externe site geïnterpreteerd, dus die worden expliciet geweigerd."""
    if not pad or not pad.startswith("/") or pad.startswith("//") or pad.startswith("/\\"):
        return fallback
    return pad


def bepaal_weergave_modus():
    """'pda' of 'desktop'. Het weergave-cookie (per toestel/browser, geen
    accountinstelling) wint altijd zodra het gezet is -- ook als iemand
    'm handmatig heeft omgezet. Pas als het cookie nog volledig ontbreekt
    (allereerste bezoek op dit toestel) wordt er op basis van de
    User-Agent geraden, en zet beveiligingsheaders() dat resultaat meteen
    vast in een cookie zodat het daarna 'onthouden' blijft."""
    cookie_waarde = request.cookies.get("weergave")
    if cookie_waarde in ("pda", "desktop"):
        return cookie_waarde
    return "pda" if WEERGAVE_TELEFOON_PATROON.search(request.headers.get("User-Agent", "")) else "desktop"
