# Keypad key mapping setup

Notes for programming the mini USB keypad (3 buttons + 1 knob, USB ID `1189:8890`) and
mapping its keys to events in `keypad.py`.

## How it works

The keypad is a normal USB keyboard. Out of the box every control sent a plain `c`, so the
controls couldn't be told apart. The fix is to reprogram the keypad so each control sends its
own unique key. The mapping is stored **on the keypad**, so this is a one-off job.

| Control | Key sent | Event name in `keypad.py` |
|---|---|---|
| Button 1 | `f13` | `button1` |
| Button 2 | `f14` | `button2` |
| Button 3 | `f15` | `button3` |
| Knob clockwise | `f16` | `knob_cw` |
| Knob counter-clockwise | `f17` | `knob_ccw` |
| Knob pressed in | `f18` | `knob_press` |

F13 to F18 are used because normal keyboards don't have them, so they never clash with
anything else.

## Part 1: Program the keypad (done on the Mac)

Programming needs a USB cable and the tool below. The Mac is easier than the Pi Zero because
a prebuilt binary is available.

### 1. Download the tool

Tool: [ch57x-keyboard-tool](https://github.com/kriomant/ch57x-keyboard-tool) (open source,
supports `1189:8890`).

Download `ch57x-keyboard-tool-universal-apple-darwin.tar.gz` from the
[releases page](https://github.com/kriomant/ch57x-keyboard-tool/releases), then unpack it:

```
cd ~/Downloads
mkdir ch57x
tar xzf ch57x-keyboard-tool-universal-apple-darwin.tar.gz -C ch57x
cd ch57x
```

### 2. Let macOS run it

macOS blocks downloaded programs it can't verify. Clear the flag:

```
xattr -dr com.apple.quarantine .
```

### 3. Install libusb

The tool needs the `libusb` library from Homebrew:

```
brew install libusb
```

Check that the tool now runs:

```
./ch57x-keyboard-tool --help
```

### 4. Create the mapping file

Save this as `mapping.yaml` in the same folder:

```yaml
orientation: normal
rows: 1
columns: 3
knobs: 1

layers:
  - buttons:
      - ["f13", "f14", "f15"]
    knobs:
      - ccw: "f17"
        press: "f18"
        cw: "f16"
```

To see every key name the tool accepts:

```
./ch57x-keyboard-tool show-keys
```

### 5. Validate the file

```
./ch57x-keyboard-tool validate < mapping.yaml
```

Expected output: `config is valid`. This only checks the file; it doesn't need the
keypad connected.

### 6. Upload to the keypad

Plug the keypad into the **Mac** (if macOS asks "Allow accessory to connect?", click Allow),
then run:

```
sudo ./ch57x-keyboard-tool upload < mapping.yaml
```

No output means success. Wait a couple of seconds before unplugging.

> Note: `validate` and `upload` read the file from **stdin**, so use `< mapping.yaml`.

## Part 2: Use it on the Raspberry Pi

### 1. Install the dependency

In the project's virtual environment:

```
python3 -m venv .venv
source .venv/bin/activate
pip install evdev
```

(The pip package is `evdev`. `python3-evdev` is the apt package name and won't work in pip.)

### 2. Find the keypad

```
sudo .venv/bin/python keypad.py --list
```

The keypad appears as several entries named `HID 1189:8890`. That's normal: one physical
device exposes several input nodes, and the script reads all that match.

### 3. Check what each control sends

```
sudo .venv/bin/python keypad.py --device "1189:8890" --learn
```

Press each control once. You should see `f13` to `f18`, one per control.

### 4. Check the mapping in `keypad.py`

The `KEYMAP` near the top of the script should read:

```python
KEYMAP = {
    "f13": "button1",
    "f14": "button2",
    "f15": "button3",
    "f16": "knob_cw",
    "f17": "knob_ccw",
    "f18": "knob_press",
}
```

### 5. Run it

```
sudo .venv/bin/python keypad.py --device "1189:8890"
```

Press Ctrl-C to quit. Put your own logic in the handler functions
(`on_button1()`, `on_knob_cw()`, and so on).

## Notes and troubleshooting

- **Use `sudo` with the venv's Python.** Plain `sudo python3` uses the system Python, which
  won't see packages installed in the venv. Use `sudo .venv/bin/python ...`, or add your
  user to the `input` group (`sudo usermod -aG input $USER`, then log out and back in) to
  avoid `sudo`.
- **`CH57x keyboard device not found`** when uploading: the keypad isn't plugged into the
  machine running the tool.
- **`Library not loaded ... libusb`**: run `brew install libusb`.
- **macOS "can't verify" warning**: run the `xattr` command in Part 1, step 2.
- **Developing on the Mac:** `keypad.py` uses `pynput` on macOS. It listens to every
  keyboard, and may not see modifier keys unless the terminal has Accessibility and Input
  Monitoring permission. Using plain F-keys (as here) avoids the modifier problem.
- **Changing the mapping later:** edit `mapping.yaml`, run `validate`, then `upload` again
  with the keypad plugged into the Mac, and update `KEYMAP` to match.