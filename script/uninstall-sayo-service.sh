#!/usr/bin/env bash
# Stop, disable and remove the sayo-button systemd service.
# Run on the Pi as your normal user (it uses sudo): script/uninstall-sayo-service.sh
# Leaves .venv, .env and the code in place.
set -euo pipefail

NAME=sayo-button
UNIT="/etc/systemd/system/$NAME.service"

sudo systemctl disable --now "$NAME" 2>/dev/null || true

if [ -f "$UNIT" ]; then
  sudo rm "$UNIT"
  echo "Removed $UNIT"
else
  echo "$UNIT not found (already uninstalled?)"
fi

sudo systemctl daemon-reload
sudo systemctl reset-failed "$NAME" 2>/dev/null || true

echo "$NAME service uninstalled"
