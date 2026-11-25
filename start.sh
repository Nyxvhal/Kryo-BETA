#!/usr/bin/env sh
# Starts Kryo on Linux and macOS: finds python3 by itself,
# installs dependencies into the user folder, no admin rights needed.
set -e
cd "$(dirname "$0")"

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      PY="$candidate"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is required. Install it and run this script again:"
  echo "  Linux:  sudo apt install python3 python3-pip   (or the equivalent for your system)"
  echo "  macOS:  brew install python"
  exit 1
fi

exec "$PY" run.py "$@"
