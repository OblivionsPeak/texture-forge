#!/usr/bin/env bash
# macOS / Linux launcher. Same idea as the .bat: private venv, install once, run.
set -e
cd "$(dirname "$0")"

PY=$(command -v python3 || command -v python) || {
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/"
  exit 1
}

[ -x .venv/bin/python ] || { echo "First run - creating a private environment..."; "$PY" -m venv .venv; }
VPY=.venv/bin/python

if [ ! -f .venv/.deps-ok ]; then
  echo "Installing dependencies..."
  "$VPY" -m pip install --quiet --upgrade pip
  "$VPY" -m pip install --quiet -r requirements.txt
  touch .venv/.deps-ok
fi

echo "Starting - Texture Forge will open in your browser."
( sleep 3; (command -v open >/dev/null && open http://localhost:4796) || \
            (command -v xdg-open >/dev/null && xdg-open http://localhost:4796) ) &
exec "$VPY" app.py
