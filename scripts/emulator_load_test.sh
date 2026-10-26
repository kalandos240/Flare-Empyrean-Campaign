#!/usr/bin/env bash
# Emulator-only touch test: open the real saved character from Flare's UI.
# Run after the main smoke script created/saved slot 1 and relaunched the app.
set -euo pipefail
PACKAGE="com.kalandos240.flareempyrean"
OUT="$RUNNER_TEMP"
LOG="$OUT/flare-load-test.log"
TITLE="$OUT/flare-relaunch.png"
MENU="$OUT/flare-load-menu.png"
PLAY="$OUT/flare-loaded-gameplay.png"

if [[ ! -s "$TITLE" ]]; then
  echo "Missing relaunch screenshot: $TITLE" >&2
  exit 1
fi

read -r width height < <(python - "$TITLE" <<'PY'
import struct
import sys
with open(sys.argv[1], 'rb') as image:
    header = image.read(24)
if header[:8] != b'\x89PNG\r\n\x1a\n':
    raise SystemExit('Expected PNG for touch coordinate calculation')
print(*struct.unpack('>II', header[16:24]))
PY
)
if (( width < 1200 || height < 600 )); then
  echo "Unexpected game screen resolution: $width x $height" >&2
  exit 1
fi

# Original "Играть" button. With a saved avatar, Flare opens GameStateLoad.
adb logcat -c
tap_x=$((width * 607 / 1000))
tap_y=$((height * 725 / 1000))
echo "Opening saved-game menu by touchscreen: $tap_x $tap_y"
adb shell input touchscreen tap "$tap_x" "$tap_y"

opened=0
for attempt in $(seq 1 24); do
  sleep 2
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: load-game menu opened' "$LOG"; then
    opened=1
    break
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOG"; then
    echo 'App crashed while opening the original save list.' >&2
    exit 1
  fi
done
adb exec-out screencap -p > "$MENU"
if (( opened == 0 )); then
  echo 'Play after relaunch failed to enter original GameStateLoad.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -100 >&2 || true
  exit 1
fi

# Original fantasycore/menus/gameload.txt positions the button at
# (1050,480) relative to a centered 1632px frame; its sprite is offset
# from this anchor. The Android emulator screenshot confirms the actual
# interactive button center at ~1580x564 on a 2340x1080 screen.
button_x=$(((width - 1632) / 2 + 1226))
button_y=$((height * 522 / 1000))
echo "Pressing original Load Game button: $button_x $button_y"
adb logcat -c
adb shell input touchscreen tap "$button_x" "$button_y"

loaded=0
for attempt in $(seq 1 35); do
  sleep 2
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: native character save loaded' "$LOG"; then
    loaded=1
    break
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOG"; then
    echo 'App crashed while loading an Empyrean character.' >&2
    exit 1
  fi
done
sleep 6
adb exec-out screencap -p > "$PLAY"
if (( loaded == 0 )); then
  echo 'Touching Load Game did not invoke native SaveLoad::loadGame().' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -100 >&2 || true
  exit 1
fi
if ! adb shell pidof "$PACKAGE" >/dev/null; then
  echo 'Native game process died after loading the saved avatar.' >&2
  exit 1
fi
echo 'PASSED: saved character was loaded through original Russian touchscreen UI.'
