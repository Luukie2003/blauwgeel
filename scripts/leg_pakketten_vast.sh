#!/bin/bash
# Legt de exacte versies van alle pakketten vast in requirements-vast.txt.
#
#   bash scripts/leg_pakketten_vast.sh
#
# Installeert requirements.txt (de minimumversies die wij kiezen) in een schone, tijdelijke omgeving en
# schrijft op wat daar uitkomt. Daarmee draaien de tests, de CI en de server precies dezelfde versies, ook
# voor pakketten die we niet zelf kiezen (Werkzeug, Jinja2, ...). Draai dit na elke wijziging in
# requirements.txt. Dependabot werkt de vastgezette versies ook bij.
set -e
cd "$(dirname "$0")/.."

PYTHON="python3.13"
command -v "$PYTHON" >/dev/null 2>&1 || { echo "$PYTHON niet gevonden." >&2; exit 1; }

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
"$PYTHON" -m venv "$TEMP/venv"
"$TEMP/venv/bin/pip" install -q --upgrade pip
"$TEMP/venv/bin/pip" install -q -r requirements.txt

{
    echo "# Exacte versies van alle pakketten waar de site op draait (gegenereerd, niet met de hand wijzigen)."
    echo "# Maak opnieuw met: bash scripts/leg_pakketten_vast.sh. Waarom: zie die scripttekst."
    "$TEMP/venv/bin/pip" freeze
} > requirements-vast.txt

echo "requirements-vast.txt bijgewerkt:"
tail -n +3 requirements-vast.txt
