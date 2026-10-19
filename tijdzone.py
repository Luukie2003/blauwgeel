"""De hele app rekent in Nederlandse tijd (Europe/Amsterdam), ook op een server die in UTC draait.

PythonAnywhere (en GitHub Actions) draaien in UTC. De app gebruikt overal de klok van het proces (now_str(),
datetime.now(), date.today()) voor wat er wordt opgeslagen en getoond: het logboek, boekingen, tellingen, de kassa.
Zonder dit stonden al die tijden 1 uur (winter) of 2 uur (zomer) te vroeg. Door de tijdzone van het proces bij het
starten op Europe/Amsterdam te zetten, klopt dat overal in één keer, ook met zomer- en wintertijd.

Importeren zet de tijdzone: app.py, helpers/tijd.py en de losse scripts (noodstop.py, backup.py, weer.py) doen dat.
"""

import os
import time

TIJDZONE = "Europe/Amsterdam"


def zet_nederlandse_tijd():
    os.environ["TZ"] = TIJDZONE
    if hasattr(time, "tzset"):  # niet op Windows; daar draait de site niet
        time.tzset()


zet_nederlandse_tijd()
