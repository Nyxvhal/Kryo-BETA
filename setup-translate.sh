#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .translate-venv
.translate-venv/bin/python -m pip install 'argostranslate==1.11.0' 'langdetect==1.0.9'
.translate-venv/bin/python tools/setup_translate.py "${1:-en}" "${2:-ru}"
