#!/usr/bin/env bash
# Original Flare movement test: swipe its *rendered* left virtual joystick.
# Emulator only. Requires the real saved hero to be loaded first.
set -euo pipefail
PACKAGE="com.kalandos240.flareempyrean"
OUT="$RUNNER_TEMP"
BEFORE="$OUT/flare-loaded-gameplay.png"
AFTER="$OUT/flare-after-joystick.png"
LOG="$OUT/flare-joystick-test.log"

if [[ ! -s "$BEFORE" ]]; then
  echo 'Cannot test mobile movement before a saved hero is loaded.' >&2
  exit 1
fi

read -r start_x start_y finish_x finish_y < <(python - "$BEFORE" <<'PY'
import struct
import sys
with open(sys.argv[1], 'rb') as image:
    header = image.read(24)
if header[:8] != b'\x89PNG\r\n\x1a\n':
    raise SystemExit('Unexpected Android screen format')
width, height = struct.unpack('>II', header[16:24])
# At 2340x1080: joystick ring center is ~270x687, confirmed in screenshot.
# Hold inside the ring and drag toward its upper-right quadrant.
print(round(width * 0.115), round(height * 0.636),
      round(width * 0.180), round(height * 0.550))
PY
)

echo "Dragging original virtual movement control: $start_x,$start_y -> $finish_x,$finish_y"
adb logcat -c
adb shell input touchscreen swipe "$start_x" "$start_y" "$finish_x" "$finish_y" 2600
sleep 5
adb exec-out screencap -p > "$AFTER"
adb logcat -d -v time > "$LOG"

if ! adb shell pidof "$PACKAGE" >/dev/null 2>&1; then
  echo 'Flare crashed while moving with the original virtual joystick.' >&2
  exit 1
fi
if ! grep -q 'FlarePort QA: virtual joystick directional input received' "$LOG"; then
  echo 'Original on-screen joystick did not produce a directional input.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION|Fatal signal' "$LOG" | tail -80 >&2 || true
  exit 1
fi
if ! grep -q 'FlarePort QA: hero moved' "$LOG"; then
  echo 'Joystick input occurred, but the hero position did not change enough.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION|Fatal signal' "$LOG" | tail -80 >&2 || true
  exit 1
fi
echo 'PASSED: original Flare virtual joystick moved the real saved hero.'
