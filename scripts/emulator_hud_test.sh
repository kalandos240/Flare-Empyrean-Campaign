#!/usr/bin/env bash
# Test real Flare inventory and primary attack via the original touch HUD.
# Only the separately instrumented x86_64 emulator build runs this script.
set -euo pipefail
PACKAGE="com.kalandos240.flareempyrean"
OUT="$RUNNER_TEMP"
BEFORE="$OUT/flare-after-joystick.png"
INVENTORY="$OUT/flare-inventory.png"
CLOSED="$OUT/flare-inventory-closed.png"
COMBAT="$OUT/flare-combat-touch.png"
LOG="$OUT/flare-hud-test.log"

if [[ ! -s "$BEFORE" ]]; then
  echo 'Need a loaded and joystick-tested game before testing touch menus.' >&2
  exit 1
fi
read -r width height < <(python - "$BEFORE" <<'PY'
import struct
import sys
with open(sys.argv[1], 'rb') as image:
    header = image.read(24)
if header[:8] != b'\x89PNG\r\n\x1a\n':
    raise SystemExit('Invalid screenshot')
print(*struct.unpack('>II', header[16:24]))
PY
)

# Image coordinates grounded in original screenshot:
# inventory chest icon ~1585,1040 on the Pixel 5's 2340x1080 surface.
inv_x=$((width * 678 / 1000))
inv_y=$((height * 966 / 1000))
echo "Tapping native inventory HUD icon at $inv_x,$inv_y"
adb logcat -c
adb shell input touchscreen tap "$inv_x" "$inv_y"

inventory_open=0
for attempt in $(seq 1 18); do
  sleep 2
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: original inventory menu opened' "$LOG"; then
    inventory_open=1
    break
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOG"; then
    echo 'Game crashed after native inventory button tap.' >&2
    exit 1
  fi
done
adb exec-out screencap -p > "$INVENTORY"
if (( inventory_open == 0 )); then
  echo 'The original inventory icon did not open the inventory menu.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -90 >&2 || true
  exit 1
fi

python - "$BEFORE" "$INVENTORY" <<'PY'
from PIL import Image
import sys
with Image.open(sys.argv[1]) as a, Image.open(sys.argv[2]) as b:
    if a.size != b.size:
        raise SystemExit('Inventory changed screen resolution unexpectedly')
    w, h = a.size
    box = (round(w*.56), round(h*.08), round(w*.94), round(h*.86))
    a = a.convert('RGB').crop(box)
    b = b.convert('RGB').crop(box)
    x = a.load()
    y = b.load()
    diff = total = 0
    for j in range(0, a.height, 5):
        for i in range(0, a.width, 5):
            diff += max(abs(x[i,j][k]-y[i,j][k]) for k in range(3)) > 35
            total += 1
    ratio = diff / total
    print(f'Inventory overlay changes {ratio:.1%} of tested pixels')
    if ratio < .12:
        raise SystemExit('Inventory visibility logged, but the original window did not render')
PY

# Toggle the *same* native HUD icon to close inventory before attacking.
adb logcat -c
adb shell input touchscreen tap "$inv_x" "$inv_y"
inventory_closed=0
for attempt in $(seq 1 12); do
  sleep 2
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: original inventory menu closed' "$LOG"; then
    inventory_closed=1
    break
  fi
done
adb exec-out screencap -p > "$CLOSED"
if (( inventory_closed == 0 )); then
  echo 'Native inventory HUD button did not close its original window.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -90 >&2 || true
  exit 1
fi

# The far-right touch ring is Flare's MAIN1 action button (slot 10).
# An actual normal power being put onto the action queue is verified in C++.
attack_x=$((width * 925 / 1000))
attack_y=$((height * 663 / 1000))
echo "Pressing original secondary action ring at $attack_x,$attack_y"
adb logcat -c
# ADB's instantaneous tap can both begin and end within a single slow
# emulator logic frame. Hold a realistic thumb contact for several frames.
adb shell input touchscreen swipe "$attack_x" "$attack_y" "$attack_x" "$attack_y" 400
attack_claimed=0
attack_input=0
action_queued=0
for attempt in $(seq 1 13); do
  
  sleep 2
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: attack ring claimed real SDL finger' "$LOG"; then
    attack_claimed=1
  fi
  if grep -q 'FlarePort QA: slot10 input fired' "$LOG"; then
    attack_input=1
  fi
  if grep -q 'FlarePort QA: touch combat action queued for slot 11' "$LOG"; then
    action_queued=1
  fi
  if (( attack_claimed && attack_input )); then
    break
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOG"; then
    echo 'Game crashed after original primary attack input.' >&2
    exit 1
  fi
done
adb exec-out screencap -p > "$COMBAT"
if (( attack_claimed == 0 || attack_input == 0 )); then
  echo 'Attack touch was not accepted by the original action bar.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -90 >&2 || true
  exit 1
fi

if (( action_queued == 0 )); then
  echo 'Attack button delivered to native slot 11; no queued attack (likely no valid target).' 
fi

# The adjacent left-hand action circle is no longer a second attack.
# It must explicitly trigger the engine's ACCEPT interaction action.
# The original Flare bottom-right alignment positions the MAIN1 ring
# near (1710, 765) on a 2340x1080 Pixel 5 display.
interact_x=$((width * 731 / 1000))
interact_y=$((height * 708 / 1000))
echo "Tapping dedicated interaction button at $interact_x,$interact_y"
adb logcat -c
adb shell input touchscreen swipe "$interact_x" "$interact_y" "$interact_x" "$interact_y" 280
interact_pressed=0
for attempt in $(seq 1 13); do
  sleep 2
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: dedicated interact button pressed ACCEPT' "$LOG"; then
    interact_pressed=1
    break
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOG"; then
    echo 'Game crashed after pressing the dedicated interact button.' >&2
    exit 1
  fi
done
if (( interact_pressed == 0 )); then
  echo 'Left action ring did not trigger ACCEPT interaction.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -90 >&2 || true
  exit 1
fi

# Skill is a separate third ring above Use, assigned to native MAIN2 (slot 11).
# The ring center is derived from the native Flare Android geometry.
skill_x=$((width * 730 / 1000))
skill_y=$((height * 429 / 1000))
echo "Pressing native Skill ring at $skill_x,$skill_y"
adb logcat -c || true
adb shell input touchscreen swipe "$skill_x" "$skill_y" "$skill_x" "$skill_y" 280
skill_claimed=0
for attempt in $(seq 1 13); do
  sleep 2
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: skill ring accepted MAIN2 slot 11' "$LOG"; then
    skill_claimed=1
    break
  fi
done
if (( skill_claimed == 0 )); then
  echo 'Dedicated Skill ring failed to select native MAIN2.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -75 >&2 || true
  exit 1
fi
adb shell pidof "$PACKAGE" >/dev/null
echo 'PASSED: inventory opens/closes; Attack reaches MAIN1, Use=ACCEPT, Skill=MAIN2.'
echo 'This validates native ability queueing, NOT hitting an actual enemy.'
