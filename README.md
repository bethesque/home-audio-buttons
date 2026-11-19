# Installation

## For keypad with 3 button and 1 dial

```
ssh <pi>
git clone https://github.com/bethesque/home-audio-buttons.git
cd home-audio-buttons
script/install-deps.sh

```

```
source .venv/bin/activate
python buttons.py --list
```

Get the string that says something like "HID 1189:8890"

```
vi .env

BUTTON_1_URL="http://travcal:8082/audio/toggle"
BUTTON_2_URL="http://nas.dixon.net.au:8442/alarm/snooze"
BUTTON_3_URL="http://nas.dixon.net.au:8442/alarm/stop"
HA_TOKEN="..."
HA_URL="http://nas.dixon.net.au:8123"
KEYPAD_DEVICE="HID 1189:8890"
```

```
script/install-service.sh
```

## 1 button keypad for Ferny

Configured using https://sayodevice.com/ in Chrome. Set single key press to `F19`


```
ssh <pi>
git clone https://github.com/bethesque/home-audio-buttons.git
cd home-audio-buttons
script/install-deps.sh

```

```
vi .env

SINGLE_PRESS_URL="http://bigpi:80/alarm/stop"
DOUBLE_PRESS_URL="http://bigpi:80/alarm/snooze"
KEYPAD_DEVICE="SayoDevice"
```

```
script/install-sayo-service.sh
```