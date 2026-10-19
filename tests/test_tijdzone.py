"""De app rekent in Nederlandse tijd, ook op een server in UTC zoals PythonAnywhere (zie tijdzone.py)."""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent


def _nl_nu():
    return datetime.now(ZoneInfo("Europe/Amsterdam")).replace(tzinfo=None)


def _scheelt_minder_dan_een_minuut(tekst):
    return abs((datetime.strptime(tekst, "%Y-%m-%d %H:%M") - _nl_nu()).total_seconds()) < 90


def test_op_een_server_in_utc_toch_nederlandse_tijd():
    """Zoals op PythonAnywhere: het proces start in UTC. De site, de console van de noodstop en de back-up rekenen
    daarna toch in Nederlandse tijd (met zomer- en wintertijd)."""
    code = (
        "import app, noodstop, backup\n"
        "from datetime import date, datetime\n"
        "from helpers import now_str\n"
        "print(now_str()); print(noodstop._nu()); print(date.today().isoformat())\n"
    )
    uit = subprocess.run([sys.executable, "-c", code], cwd=REPO, env={**os.environ, "TZ": "UTC"},
                         capture_output=True, text=True, check=True).stdout.split()
    regels = [" ".join(uit[0:2]), " ".join(uit[2:4]), uit[4]]
    assert _scheelt_minder_dan_een_minuut(regels[0]), regels
    assert _scheelt_minder_dan_een_minuut(regels[1]), regels
    assert regels[2] == _nl_nu().date().isoformat()


def test_in_de_tests_ook():
    from helpers import now_str

    assert _scheelt_minder_dan_een_minuut(now_str())
