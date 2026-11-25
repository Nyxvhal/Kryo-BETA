#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .karaoke-venv
.karaoke-venv/bin/python -m pip install --upgrade pip
case "${1:-align}" in
 light) req=requirements-karaoke.txt;;
 separation) req=requirements-karaoke-separation.txt;;
 *) req=requirements-karaoke-align.txt;;
esac
.karaoke-venv/bin/python -m pip install -r "$req"
echo 'Karaoke worker installed. Restart the player. Models download on first generation.'
