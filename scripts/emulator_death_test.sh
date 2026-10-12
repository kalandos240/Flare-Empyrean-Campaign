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
echo 'PASSED: real Avatar death transition and original Game Over UI.'
echo 'This trigger simulates lethal HP, not actual enemy damage.'
