#!/usr/bin/env bash
# ---- JobRadar launcher for macOS / Linux ----
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
echo "Installing/updating dependencies..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo "Starting JobRadar..."
python -m app.main
