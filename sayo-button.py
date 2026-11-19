#!/usr/bin/env python3
"""
Handle single / double / long presses from a SayoDevice single-key keyboard.

The keyboard is programmed (on sayodevice.com) to send one plain key, F19. This script
times the press and release of that key to tell the three gestures apart, then calls
on_single(), on_double() or on_long().

Backends:
  * macOS (development):  pynput  -> listens to ALL keyboards (can't tell them apart)
  * Linux / Raspberry Pi: evdev   -> reads (and grabs) just your keyboard

Setup:
  Mac:  pip install pynput          (grant your terminal "Input Monitoring" permission)
  Pi:   pip install evdev           (run with sudo, or add your user to the 'input' group)

Usage:
  python sayo-button --learn                    # print the key name the button sends
  python sayo-button                            # Mac: run normally (Esc quits)
  python sayo-button --list                     # Pi: list input devices
  python sayo-button --device "name"            # Pi: run, matching device by name/vid:pid/path
  KEYPAD_DEVICE="name" python sayo-button         # Pi: same as --device (used by the service)
"""

import argparse
import os
import platform
import selectors
import sys
import threading

import requests

# ---------------------------------------------------------------------------
# 1. SETTINGS
# ---------------------------------------------------------------------------
KEY = "f19"             # the key the keyboard is programmed to send (see --learn)
LONG_PRESS_S = 0.5      # held at least this long = long press
DOUBLE_PRESS_S = 0.3    # second tap within this window = double press


# ---------------------------------------------------------------------------
# 2. HANDLERS
#    SINGLE_PRESS_URL, DOUBLE_PRESS_URL, LONG_PRESS_URL: each gesture sends a
#    POST to its URL if set; otherwise it just prints.
# ---------------------------------------------------------------------------
URL_TIMEOUT = 5  # seconds

PRESS_URLS = {
    label: os.environ.get(var, "")
    for label, var in (
        ("Single press", "SINGLE_PRESS_URL"),
        ("Double press", "DOUBLE_PRESS_URL"),
        ("Long press", "LONG_PRESS_URL"),
    )
}


def post_url(url, label):
    try:
        resp = requests.post(url, timeout=URL_TIMEOUT)
        print(f"{label}: POST {url} -> HTTP {resp.status_code}")
    except requests.RequestException as e:
        print(f"{label}: POST {url} failed: {e}")


def make_handler(label):
    url = PRESS_URLS[label]

    def handler():
        if not url:
            print(label)
            return
        # Run in its own thread so a slow URL never blocks the key listener.
        threading.Thread(target=post_url, args=(url, label), daemon=True).start()
    return handler


on_single = make_handler("Single press")
on_double = make_handler("Double press")
on_long = make_handler("Long press")


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------
def normalise(name):
    """Lowercase, no 'KEY_' prefix, no underscores: KEY_F19 -> 'f19'."""
    name = str(name).lower()
    if name.startswith("key_"):
        name = name[4:]
    return name.replace("_", "")


class Gestures:
    """Turns raw key press/release events for KEY into single/double/long events."""

    def __init__(self, learn=False):
        self.learn = learn
        self.lock = threading.Lock()
        self.long_timer = None
        self.single_timer = None
        self.long_fired = False

    def press(self, raw_name):
        name = normalise(raw_name)
        if self.learn:
            print(f"key name: {name!r}")
            return
        if name != KEY:
            return
        with self.lock:
            self.long_fired = False
            self.long_timer = threading.Timer(LONG_PRESS_S, self._on_long_timeout)
            self.long_timer.daemon = True
            self.long_timer.start()

    def release(self, raw_name):
        if self.learn or normalise(raw_name) != KEY:
            return
        with self.lock:
            if self.long_timer is not None:
                self.long_timer.cancel()
                self.long_timer = None
            if self.long_fired:                 # long press already reported
                self.long_fired = False
                return
            if self.single_timer is not None:   # second tap inside the window
                self.single_timer.cancel()
                self.single_timer = None
                handler = on_double
            else:                               # first tap: wait to see if a second follows
                self.single_timer = threading.Timer(DOUBLE_PRESS_S, self._on_single_timeout)
                self.single_timer.daemon = True
                self.single_timer.start()
                return
        handler()

    def _on_long_timeout(self):
        with self.lock:
            self.long_fired = True
            if self.single_timer is not None:   # tap + hold counts as just a long press
                self.single_timer.cancel()
                self.single_timer = None
        on_long()

    def _on_single_timeout(self):
        with self.lock:
            if self.single_timer is None:
                return
            self.single_timer = None
        on_single()


# --- macOS / other: pynput --------------------------------------------------
def run_pynput(gestures, raw=False):
    from pynput import keyboard

    down = set()   # keys currently held (also stops auto-repeat)

    def key_name(key):
        return getattr(key, "char", None) or getattr(key, "name", None) or str(key)

    def on_press(key):
        name = key_name(key)
        if raw:
            print(f"  press   {key!r}  vk={getattr(key, 'vk', None)}\r")
        if name == "esc":     # quit key (Ctrl-C is disabled, see below)
            return False
        if name in down:      # auto-repeat while held: ignore
            return
        down.add(name)
        gestures.press(name)

    def on_release(key):
        name = key_name(key)
        if raw:
            print(f"  release {key!r}  vk={getattr(key, 'vk', None)}\r")
        if name in down:
            down.discard(name)
            gestures.release(name)

    # Stop the keyboard's keystrokes echoing into the terminal and stop Ctrl-C
    # from killing the script; Esc quits instead.
    import termios
    fd = sys.stdin.fileno() if sys.stdin.isatty() else None
    old_attrs = None
    if fd is not None:
        old_attrs = termios.tcgetattr(fd)
        new_attrs = termios.tcgetattr(fd)
        new_attrs[3] &= ~(termios.ECHO | termios.ISIG | termios.ICANON)
        termios.tcsetattr(fd, termios.TCSADRAIN, new_attrs)

    print("Listening. Press Esc to quit. Note: this hears ALL keyboards on this Mac.")
    try:
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
    finally:
        if fd is not None:
            termios.tcflush(fd, termios.TCIFLUSH)
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)


# --- Linux / Raspberry Pi: evdev -------------------------------------------
def list_devices():
    import evdev
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        print(f"{path}\t{d.name}\t(vid:pid {d.info.vendor:04x}:{d.info.product:04x})")


def run_evdev(gestures, hint, grab):
    import evdev
    from evdev import ecodes

    if not hint:
        sys.exit("Specify --device NAME_OR_PATH (use --list to see devices).")

    devices = []
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        vidpid = f"{d.info.vendor:04x}:{d.info.product:04x}"
        if hint.lower() in d.name.lower() or hint.lower() == vidpid or hint == path:
            devices.append(d)
    if not devices:
        sys.exit(f"No input device matching {hint!r}. Try --list.")

    sel = selectors.DefaultSelector()
    for d in devices:
        # Some keyboards expose several nodes; we read all that match.
        if grab:
            try:
                d.grab()  # stop keystrokes leaking into the Pi's console/desktop
            except OSError as e:
                print(f"Warning: couldn't grab {d.path}: {e}")
        sel.register(d, selectors.EVENT_READ)
        print(f"Listening on {d.path} ({d.name})")

    try:
        while True:
            for key, _ in sel.select():
                for ev in key.fileobj.read():
                    if ev.type != ecodes.EV_KEY or ev.value == 2:  # skip auto-repeat
                        continue
                    name = ecodes.KEY.get(ev.code) or ecodes.BTN.get(ev.code)
                    if isinstance(name, (list, tuple)):
                        name = name[0]
                    name = name or f"code{ev.code}"
                    if ev.value == 1:
                        gestures.press(name)
                    elif ev.value == 0:
                        gestures.release(name)
    finally:
        for d in devices:
            try:
                d.ungrab()
            except OSError:
                pass


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--learn", action="store_true", help="print the key name of each press")
    p.add_argument("--raw", action="store_true", help="(Mac) print every raw press/release for debugging")
    p.add_argument("--list", action="store_true", help="(Linux) list input devices")
    p.add_argument("--device", default=os.environ.get("KEYPAD_DEVICE"),
                   help="(Linux) device name substring, vid:pid, or /dev/input/eventN path "
                        "(default: $KEYPAD_DEVICE)")
    p.add_argument("--no-grab", action="store_true", help="(Linux) don't grab the device exclusively")
    args = p.parse_args()

    on_linux = platform.system() == "Linux"

    if args.list:
        if not on_linux:
            sys.exit("--list is only for Linux (the Pi).")
        list_devices()
        return

    if not args.learn:
        for label, url in PRESS_URLS.items():
            print(f"{label} -> {'POST ' + url if url else '(print only)'}")

    gestures = Gestures(args.learn)
    try:
        if on_linux:
            run_evdev(gestures, args.device, grab=not args.no_grab)
        else:
            run_pynput(gestures, raw=args.raw)
    except KeyboardInterrupt:
        print("\nBye")


if __name__ == "__main__":
    main()