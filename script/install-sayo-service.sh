#!/usr/bin/env bash
# Install and start the sayo-button systemd service.
# Run on the Pi as your normal user (it uses sudo): script/install-sayo-service.sh
# The unit file's /home/pi/home-audio-buttons paths and User=pi are rewritten
# to this directory and the current user.
set -euo pipefail

cd "$(dirname "$0")/.."
DIR="$(pwd)"
USER_NAME="$(id -un)"
NAME=sayo-button

[ -f .env ] || { echo "Missing $DIR/.env" >&2; exit 1; }
[ -x .venv/bin/python ] || { echo "Missing .venv - run script/install-deps.sh first" >&2; exit 1; }

sed -e "s|/home/pi/home-audio-buttons|$DIR|g" \
    -e "s|^User=.*|User=$USER_NAME|" \
    "resources/$NAME.service" | sudo tee "/etc/systemd/system/$NAME.service" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$NAME"
sudo systemctl restart "$NAME"

systemctl --no-pager status "$NAME" || true
echo
echo "Logs: journalctl -u $NAME -f"
