#!/usr/bin/env python3
"""
Handle events from a 3-button + knob USB mini keyboard.

These devices normally show up as an ordinary USB keyboard, so each button/knob
action arrives as a key press. This script maps those key names to events and
calls your handler functions.

Backends:
  * macOS (development):  pynput  -> listens to ALL keyboards (can't tell them apart)
  * Linux / Raspberry Pi: evdev   -> reads (and grabs) just your keypad

Setup:
  Mac:  pip install pynput          (grant Terminal "Input Monitoring" permission)
  Pi:   pip install evdev           (run with sudo, or add your user to the 'input' group)

Usage:
  python keypad.py --learn                    # discover what each button/knob sends
  python keypad.py                            # Mac: run normally
  python keypad.py --list                     # Pi: list input devices
  python keypad.py --device "keypad name"     # Pi: run, matching device by name/path
"""

import argparse
import platform
import selectors
import sys

# ---------------------------------------------------------------------------
# 1. KEY -> EVENT MAPPING  (edit after running --learn)
#    Key names are normalised: lowercase, no "KEY_" prefix, no underscores.
#    e.g. KEY_VOLUMEUP -> "volumeup", KEY_ENTER -> "enter", "a" -> "a"
# ---------------------------------------------------------------------------
KEYMAP = {
    "f13": "button1",
    "f14": "button2",
    "f15": "button3",
    "f16": "knob_cw",      # knob turned clockwise
    "f17": "knob_ccw",     # knob turned counter-clockwise
    "f18": "knob_press",   # knob pushed in
}


# ---------------------------------------------------------------------------
# 2. YOUR HANDLERS  (put your real logic here)
# ---------------------------------------------------------------------------
def on_button1():
    print("Button 1 pressed")


def on_button2():
    print("Button 2 pressed")


def on_button3():
    print("Button 3 pressed")


def on_knob_cw():
    print("Knob turned clockwise")


def on_knob_ccw():
    print("Knob turned counter-clockwise")


def on_knob_press():
    print("Knob pressed")


HANDLERS = {
    "button1": on_button1,
    "button2": on_button2,
    "button3": on_button3,
    "knob_cw": on_knob_cw,
    "knob_ccw": on_knob_ccw,
    "knob_press": on_knob_press,
}


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------
# pynput names media keys differently from evdev; fold them together.
ALIASES = {
    "mediavolumeup": "volumeup",
    "mediavolumedown": "volumedown",
    "mediavolumemute": "mute",
    "mediaplaypause": "playpause",
    "medianext": "nextsong",
    "mediaprevious": "previoussong",
}


def normalise(name):
    name = str(name).lower()
    if name.startswith("key_"):
        name = name[4:]
    name = name.replace("_", "")
    return ALIASES.get(name, name)


def make_dispatcher(learn):
    def dispatch(raw_name):
        name = normalise(raw_name)
        if learn:
            print(f"key name: {name!r}")
            return
        event = KEYMAP.get(name)
        if event is None:
            print(f"(unmapped key: {name!r})")
            return
        handler = HANDLERS.get(event)
        if handler:
            handler()
    return dispatch


# --- macOS / other: pynput --------------------------------------------------
def run_pynput(dispatch, raw=False):
    from pynput import keyboard

    MODS = ("ctrl", "shift", "alt", "cmd")
    held = set()   # non-modifier keys currently down (used to ignore auto-repeat)
    mods = set()   # modifiers currently down

    def key_name(key):
        return getattr(key, "char", None) or getattr(key, "name", None) or str(key)

    def mod_of(name):
        for m in MODS:
            if name.startswith(m):
                return m
        return None

    def on_press(key):
        name = key_name(key)
        if raw:
            print(f"  press   {key!r}  vk={getattr(key, 'vk', None)}  mods_held={sorted(mods)}\r")
        if name == "esc":     # quit key (Ctrl-C is disabled, see below)
            return False
        m = mod_of(name)
        if m:
            mods.add(m)
            return
        if name in held:      # auto-repeat while held: ignore
            return
        held.add(name)
        prefix = "+".join(sorted(mods))
        dispatch(f"{prefix}+{name}" if prefix else name)

    def on_release(key):
        name = key_name(key)
        if raw:
            print(f"  release {key!r}  vk={getattr(key, 'vk', None)}\r")
        m = mod_of(name)
        if m:
            mods.discard(m)
        else:
            held.discard(name)

    # Stop the keypad's keystrokes from echoing into the terminal, and stop a
    # pad button that sends Ctrl+C from killing the script.
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
            termios.tcflush(fd, termios.TCIFLUSH)   # discard stray typed keys
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)


# --- Linux / Raspberry Pi: evdev -------------------------------------------
def list_devices():
    import evdev
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        print(f"{path}\t{d.name}\t(vid:pid {d.info.vendor:04x}:{d.info.product:04x})")


def run_evdev(dispatch, hint, grab):
    import evdev
    from evdev import ecodes

    if not hint:
        sys.exit("Specify --device NAME_OR_PATH (use --list to see devices).")

    devices = []
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        if hint.lower() in d.name.lower() or hint == path:
            devices.append(d)
    if not devices:
        sys.exit(f"No input device matching {hint!r}. Try --list.")

    sel = selectors.DefaultSelector()
    for d in devices:
        # Many keypads expose several nodes (keyboard + media keys); we read all.
        if grab:
            try:
                d.grab()  # stop keystrokes leaking into the Pi's console/desktop
            except OSError as e:
                print(f"Warning: couldn't grab {d.path}: {e}")
        sel.register(d, selectors.EVENT_READ)
        print(f"Listening on {d.path} ({d.name})")

    # Same naming as the Mac backend: ctrl / shift / alt / cmd (cmd = Super/Meta key)
    MOD_NAMES = {
        "KEY_LEFTCTRL": "ctrl", "KEY_RIGHTCTRL": "ctrl",
        "KEY_LEFTSHIFT": "shift", "KEY_RIGHTSHIFT": "shift",
        "KEY_LEFTALT": "alt", "KEY_RIGHTALT": "alt",
        "KEY_LEFTMETA": "cmd", "KEY_RIGHTMETA": "cmd",
    }
    mods = set()

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
                    mod = MOD_NAMES.get(name)
                    if mod:
                        if ev.value == 1:
                            mods.add(mod)
                        else:
                            mods.discard(mod)
                        continue
                    if ev.value == 1:  # key down
                        base = normalise(name)
                        prefix = "+".join(sorted(mods))
                        dispatch(f"{prefix}+{base}" if prefix else base)
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
    p.add_argument("--device", help="(Linux) device name substring or /dev/input/eventN path")
    p.add_argument("--no-grab", action="store_true", help="(Linux) don't grab the device exclusively")
    args = p.parse_args()

    on_linux = platform.system() == "Linux"

    if args.list:
        if not on_linux:
            sys.exit("--list is only for Linux (the Pi).")
        list_devices()
        return

    dispatch = make_dispatcher(args.learn)
    try:
        if on_linux:
            run_evdev(dispatch, args.device, grab=not args.no_grab)
        else:
            run_pynput(dispatch, raw=args.raw)
    except KeyboardInterrupt:
        print("\nBye")


if __name__ == "__main__":
    main()
