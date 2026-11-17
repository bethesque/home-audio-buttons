#!/usr/bin/env python3
"""
Control Home Assistant from the keypad.

Uses keypad.py to listen for button/knob presses and sends the knob turns and
press to a Home Assistant media player as volume up / down / play-pause.
Buttons POST to BUTTON_1_URL, BUTTON_2_URL, BUTTON_3_URL if those are set.

Usage (same options as keypad.py):
  source .env && python buttons.py
  python buttons.py --device "keypad name"    # Pi
"""

import os
import queue
import sys
import threading

import requests

import keypad

# ---------------------------------------------------------------------------
# HOME ASSISTANT
#    Configure with environment variables:
#      HA_URL     e.g. http://homeassistant.local:8123
#      HA_TOKEN   long-lived access token (Profile -> Security in HA)
#      HA_ENTITY  media player to control (default: media_player.travcal)
# ---------------------------------------------------------------------------
class HomeAssistant:
    """Sends media_player actions to Home Assistant from a background thread,
    so a slow request never blocks the key listener."""

    # (connect, read) seconds. HA only replies once the player has acted, and
    # play/pause can take several seconds through Music Assistant.
    TIMEOUT = (3, 15)
    MAX_PENDING = 3  # drop extra knob ticks beyond this so volume stops when you stop

    def __init__(self, url, token, entity):
        self.url = url.rstrip("/")
        self.token = token
        self.entity = entity
        self.queue = queue.Queue(maxsize=self.MAX_PENDING)
        # Reuse one connection for all requests (fast knob ticks).
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def submit(self, action):
        try:
            self.queue.put_nowait(action)
        except queue.Full:
            pass  # falling behind on a fast spin: drop this tick

    def _request(self, method, path, body=None):
        resp = self.session.request(method, f"{self.url}{path}",
                                    json=body, timeout=self.TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _call(self, service, **data):
        self._request("POST", f"/api/services/media_player/{service}",
                      {"entity_id": self.entity, **data})

    def _do(self, action):
        self._call(action)
        print(action.replace("_", " ").capitalize())

    def _worker(self):
        while True:
            action = self.queue.get()
            try:
                self._do(action)
            except requests.HTTPError as e:
                r = e.response
                print(f"HA error for {action}: HTTP {r.status_code} {r.reason}")
            except (requests.RequestException, ValueError) as e:
                print(f"HA unreachable for {action}: {e}")


ha = HomeAssistant(
    url=os.environ.get("HA_URL", ""),
    token=os.environ.get("HA_TOKEN", ""),
    entity=os.environ.get("HA_ENTITY", "media_player.travcal"),
)


# ---------------------------------------------------------------------------
# BUTTON URLS
#    BUTTON_1_URL, BUTTON_2_URL, BUTTON_3_URL: each button sends a POST to its
#    URL if set; unset buttons keep keypad.py's print-only handler.
# ---------------------------------------------------------------------------
BUTTON_COUNT = 3
BUTTON_TIMEOUT = 5  # seconds


def post_url(url, label):
    try:
        resp = requests.post(url, timeout=BUTTON_TIMEOUT)
        print(f"{label}: POST {url} -> HTTP {resp.status_code}")
    except requests.RequestException as e:
        print(f"{label}: POST {url} failed: {e}")


def make_button_handler(n, url):
    # Run in its own thread so a slow URL never blocks the key listener.
    def handler():
        threading.Thread(target=post_url, args=(url, f"Button {n}"), daemon=True).start()
    return handler


BUTTON_URLS = {
    n: os.environ[f"BUTTON_{n}_URL"]
    for n in range(1, BUTTON_COUNT + 1)
    if os.environ.get(f"BUTTON_{n}_URL")
}


# ---------------------------------------------------------------------------
# HANDLERS  (override keypad.py's print-only defaults)
# ---------------------------------------------------------------------------
keypad.HANDLERS.update({
    f"button{n}": make_button_handler(n, url) for n, url in BUTTON_URLS.items()
})
keypad.HANDLERS.update({
    "knob_cw": lambda: ha.submit("volume_up"),
    "knob_ccw": lambda: ha.submit("volume_down"),
    "knob_press": lambda: ha.submit("media_play_pause"),
})


def main():
    # --learn / --list / --help don't talk to Home Assistant.
    if not {"--learn", "--list", "-h", "--help"} & set(sys.argv[1:]):
        if not ha.url or not ha.token:
            sys.exit("Set HA_URL and HA_TOKEN (and optionally HA_ENTITY) first.")
        ha.start()
        print(f"Controlling {ha.entity} via {ha.url}")
        for n, url in BUTTON_URLS.items():
            print(f"Button {n} -> POST {url}")
    keypad.main()


if __name__ == "__main__":
    main()
