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
# Fantasycore original Game Over modal is centered, offset vertically by -192
# game units; its Continue button is around screen center x, y = 0.32 h.
read -r width height < <(python - "$SCREEN" <<'PY'
import struct
import sys
with open(sys.argv[1], 'rb') as f:
    h = f.read(24)
if h[:8] != b'\x89PNG\r\n\x1a\n':
    raise SystemExit("Invalid Game Over screenshot")
print(*struct.unpack(">II", h[16:24]))
PY
)
continue_x=$((width * 500 / 1000))
continue_y=$((height * 322 / 1000))
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
