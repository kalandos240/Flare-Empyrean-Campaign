#!/usr/bin/env bash
# Original Flare bottom toolbar: character, powers, journal.
# Independent x86_64 emulator QA; never included in a RuStore APK.
set -euo pipefail
PACKAGE="com.kalandos240.flareempyrean"
OUT="$RUNNER_TEMP"
LOG="$OUT/flare-menus-test.log"
BEFORE="$OUT/flare-after-joystick.png"

if [[ ! -s "$BEFORE" ]]; then
  echo 'Loaded gameplay and movement test required first.' >&2
  exit 1
fi
read -r width height < <(python - "$BEFORE" <<'PY'
import struct
import sys
with open(sys.argv[1], 'rb') as f:
    data = f.read(24)
if data[:8] != b'\x89PNG\r\n\x1a\n':
    raise SystemExit("Invalid Android screenshot")
print(*struct.unpack(">II", data[16:24]))
PY
)

# The 1280px-wide original action bar is horizontally centered on Pixel 5.
# Character/inventory/powers/journal icons are at local x=992/1056/1120/1184.
# Relative proportions allow for other landscape screen dimensions.
tap_menu() {
  local name="$1"
  local x_permille="$2"
  local x=$((width * x_permille / 1000))
  local y=$((height * 966 / 1000))
  for phase in opened closed; do
    adb logcat -c || true
    adb shell input touchscreen tap "$x" "$y"
    local found=0
    for attempt in $(seq 1 14); do
      sleep 2
      adb logcat -d -v time > "$LOG"
      if grep -Fq "FlarePort QA: $name panel $phase" "$LOG"; then
        found=1
        break
      fi
      if ! adb shell pidof "$PACKAGE" >/dev/null 2>&1; then
        echo 'Game process exited while testing original menu.' >&2
        return 1
      fi
    done
    adb exec-out screencap -p > "$OUT/flare-menu-$name-$phase.png"
    if (( found == 0 )); then
      echo "Original $name menu did not transition to $phase." >&2
      grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOG" | tail -90 >&2 || true
      return 1
    fi
  done
}
# Pixel5 2340x1080: character center ~1522, powers 1650, log 1714.
tap_menu character 650
tap_menu powers 705
tap_menu questlog 733
adb shell pidof "$PACKAGE" >/dev/null
echo 'PASSED: character, powers and quest log opened and closed using Android touch.'
