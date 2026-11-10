#!/usr/bin/env bash
# Emulator-only test of original Avatar death and Game Over UI.
set -euo pipefail
PACKAGE="com.kalandos240.flareempyrean"
OUT="$RUNNER_TEMP"
LOG="$OUT/flare-death-test.log"
SCREEN="$OUT/flare-death-screen.png"

adb shell pidof "$PACKAGE" >/dev/null
adb logcat -c || true
adb shell am broadcast -n "$PACKAGE/org.flare.app.QaReceiver" \
  --es operation trigger-death
adb logcat -d -v time > "$LOG"
if ! grep -q 'QA trigger-death PASS' "$LOG"; then
  echo "Emulator-only death scenario could not be armed." >&2
  exit 1
fi
shown=0
for attempt in $(seq 1 65); do
  sleep 3
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: original Game Over dialog displayed' "$LOG"; then
    shown=1
    break
  fi
  if ! adb shell pidof "$PACKAGE" >/dev/null 2>&1 ||
     grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOG"; then
    echo 'The native engine crashed during defeat.' >&2
    exit 1
  fi
done
adb exec-out screencap -p > "$SCREEN"
if (( shown == 0 )); then
  echo 'Original Flare Game Over dialog never appeared.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -95 >&2 || true
  exit 1
fi
adb shell pidof "$PACKAGE" >/dev/null
# Extract the actual centered native button coordinates. The screenshot may
# be a different resolution from the game's logical viewport.
read -r continue_x continue_y < <(python - "$LOG" "$SCREEN" <<'PY'
import re
import struct
import sys
from pathlib import Path

logs = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
match = re.search(r"FlarePort QA: continue center (\d+) (\d+) viewport (\d+) (\d+)", logs)
if not match:
    raise SystemExit("No original Game Over Continue button center logged")
x, y, view_w, view_h = map(int, match.groups())
with open(sys.argv[2], "rb") as image:
    header = image.read(24)
if header[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit("Invalid Game Over screenshot")
screen_w, screen_h = struct.unpack(">II", header[16:24])
if min(view_w, view_h, screen_w, screen_h) == 0 or not (0 <= x < view_w and 0 <= y < view_h):
    raise SystemExit("Invalid Game Over Continue coordinates")
print(round(x * screen_w / view_w), round(y * screen_h / view_h))
PY
)
echo "Tapping actual Game Over Continue button at $continue_x,$continue_y"
adb logcat -c || true
adb shell input touchscreen tap "$continue_x" "$continue_y"
respawn=0
for attempt in $(seq 1 45); do
  sleep 3
  adb logcat -d -v time > "$LOG"
  if grep -q 'FlarePort QA: original hero respawn reached' "$LOG"; then
    respawn=1
    break
  fi
  if ! adb shell pidof "$PACKAGE" >/dev/null 2>&1; then
    echo 'Native game stopped after Game Over Continue.' >&2
    exit 1
  fi
done
adb exec-out screencap -p > "$OUT/flare-death-respawn.png"
if (( respawn == 0 )); then
  echo 'Game Over Continue did not respawn the original hero.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -75 >&2 || true
  exit 1
fi
# Verify persistent files survive both the death and the real respawn flow.
adb logcat -c || true
adb shell am broadcast -n "$PACKAGE/org.flare.app.QaReceiver" --es operation verify
sleep 3
adb logcat -d -v time > "$LOG"
if ! grep -q 'QA verify PASS' "$LOG"; then
  echo 'App-scoped save/config files damaged during original death/respawn.' >&2
  exit 1
fi
echo 'PASSED: real Avatar death, Game Over Continue, hero respawn and save sentinel.'
echo 'This trigger simulates lethal HP, not actual enemy damage.'
