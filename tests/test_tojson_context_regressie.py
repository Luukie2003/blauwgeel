"""Regressietest voor "TypeError: Object of type Undefined is not JSON
serializable", die op 2026-09-11 05:30 in het PythonAnywhere-errorlog van
kantineblauwgeel.nl stond.

Uitgezocht via de echte traceback (niet uit deze repo af te leiden): de
kortstondige livestream-functie op het prijzenscherm (commit 506f9be,
"Livestream op het prijzenscherm") zette `{{ stream_url|tojson }}` in
kiosk_prijzen_scherm.html neer, terwijl de route `stream_url` niet in elk
render_template-pad meegaf -- Jinja maakt daar dan een Undefined-object van,
en dat object kan |tojson (== json.dumps) niet serialiseren. Diezelfde
livestream-functie is de volgende ochtend alweer vervangen door echt
Chromecasten (commit 7bd148a); `stream_url` bestaat sindsdien nergens meer
in de code, dus er valt aan die specifieke variabele niets meer te
patchen.

In plaats daarvan dekt deze test de klasse van de fout af: elke pagina die
een Jinja-variabele met |tojson serialiseert, moet zonder crash renderen.
Met TESTING=True (zie conftest.py) propageert Flask zo'n TypeError gewoon
i.p.v. 'm in een 500-response te verstoppen, dus een vergeten
render_template-kwarg -- nu of ooit in de toekomst, voor eender welke van
deze pagina's -- laat deze test meteen falen i.p.v. pas via een
productie-errorlog aan het licht te komen. (Zie ook: elke render_template
in routes/kiosk.py en routes/producten.py geeft z'n |tojson-variabelen
inmiddels altijd mee, gecontroleerd tegen elke |tojson-plek in templates/.)
"""

TOJSON_PAGINAS = [
    # (pad, vereist_login, methode)
    ("/kiosk/prijzen", False),
    ("/kiosk/tv", False),
    ("/kiosk/scherm", False),
    ("/kiosk/sponsoren-leden/sponsoren/nieuw", True),
    ("/kiosk/sponsoren-leden/sjablonen/nieuw", True),
    ("/bijzonderheden", True),
    ("/producten/nieuw", True),
]


def test_paginas_met_tojson_renderen_zonder_ontbrekende_context(client, ingelogde_client, db):
    for pad, vereist_login in TOJSON_PAGINAS:
        c = ingelogde_client if vereist_login else client
        resp = c.get(pad)
        assert resp.status_code == 200, f"{pad} gaf {resp.status_code} i.p.v. 200"
