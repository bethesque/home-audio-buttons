#!/usr/bin/env bash
# Create .venv and install the project's Python dependencies into it.
# Run on the Pi from anywhere: script/install-deps.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# venv support, plus headers/compiler in case evdev has to build from source.
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev gcc

if [ ! -x .venv/bin/python ]; then
  /usr/bin/python3 -m venv .venv
fi

.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

echo "Dependencies installed into $(pwd)/.venv"
