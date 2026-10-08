#!/bin/bash
# Maakt een nieuwe virtualenv ("venv") met dezelfde Python-versie als op
# PythonAnywhere (3.13), zodat wat lokaal werkt ook op de server werkt.
#
#   bash scripts/maak_venv.sh
#
# Is Python 3.13 nog niet geïnstalleerd, installeer het dan eerst, bijvoorbeeld:
#   brew install python@3.13
# Een bestaande venv wordt hernoemd naar venv-oud (dan kun je terug als er iets mis gaat).
set -e
cd "$(dirname "$0")/.."

GEWENST="python3.13"
if ! command -v "$GEWENST" >/dev/null 2>&1; then
    echo "$GEWENST niet gevonden. Installeer het eerst (bijv. 'brew install python@3.13')." >&2
    exit 1
fi

if [ -d venv ]; then
    rm -rf venv-oud
    mv venv venv-oud
    echo "Bestaande venv hernoemd naar venv-oud."
fi

"$GEWENST" -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements-dev.txt
echo
venv/bin/python --version
echo "Klaar. Draai de tests met: venv/bin/python -m pytest"
