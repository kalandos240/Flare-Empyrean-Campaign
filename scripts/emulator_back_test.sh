#!/usr/bin/env bash
# Emulator-only QA: Flare's original Android Back -> Input::CANCEL binding.
set -euo pipefail
PACKAGE="com.kalandos240.flareempyrean"
OUT="$RUNNER_TEMP"
BEFORE="$OUT/flare-combat-touch.png"
PAUSED="$OUT/flare-back-pause.png"
RESUMED="$OUT/flare-back-resume.png"
LOG="$OUT/flare-back-test.log"

if [[ ! -s "$BEFORE" ]]; then
  echo 'The original touch HUD must be tested before Android Back.' >&2
  exit 1
fi

check_back_transition() {
  local expected="$1"
  adb logcat -c
  adb shell input keyevent KEYCODE_BACK
  for attempt in $(seq 1 20); do
    sleep 2
    adb logcat -d -v time > "$LOG"
    if grep -Fq "FlarePort QA: original pause menu $expected" "$LOG"; then
      adb shell pidof "$PACKAGE" >/dev/null
      return 0
    fi
    if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOG" ||
       ! adb shell pidof "$PACKAGE" >/dev/null 2>&1; then
      echo "Game crashed or exited after Android Back ($expected)." >&2
      return 1
    fi
  done
  echo "Original pause menu did not transition to $expected after Back." >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -100 >&2 || true
  return 1
}

echo 'Android Back should open original Flare pause menu, not exit.'
check_back_transition opened
adb exec-out screencap -p > "$PAUSED"

python - "$BEFORE" "$PAUSED" <<'PY'
from PIL import Image
import sys

with Image.open(sys.argv[1]) as before, Image.open(sys.argv[2]) as after:
    if before.size != after.size:
        raise SystemExit("Pause menu unexpectedly changed game resolution")
    w, h = before.size
    region = (round(w*.25), round(h*.15), round(w*.75), round(h*.88))
    a, b = [image.convert('RGB').crop(region) for image in (before, after)]
    x, y = a.load(), b.load()
    changed = total = 0
    for j in range(0, a.height, 6):
        for i in range(0, a.width, 6):
            changed += max(abs(x[i, j][k] - y[i, j][k]) for k in range(3)) > 38
            total += 1
    ratio = changed / total
    print(f"Android Back pause overlay changed {ratio:.1%} of sampled pixels")
    if ratio < .05:
        raise SystemExit("Pause menu was logged but did not visibly render")
PY

echo 'Second Android Back should close original Flare pause menu.'
check_back_transition closed
adb exec-out screencap -p > "$RESUMED"
adb shell pidof "$PACKAGE" >/dev/null
echo 'PASSED: Android Back opens/closes original pause menu; game remains alive.'
