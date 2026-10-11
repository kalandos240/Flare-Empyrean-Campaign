#!/usr/bin/env bash
# Minimal automated boot test for a separate x86_64 emulator-only APK.
set -euo pipefail

APK="${1:?Provide the debug APK to test}"
PACKAGE="com.kalandos240.flareempyrean"
ACTIVITY="org.flare.app.LaunchActivity"
LOGFILE="${RUNNER_TEMP:-/tmp}/flare-android-smoke.log"

adb wait-for-device
adb shell settings put system screen_off_timeout 1800000 || true
adb install -r "$APK"
adb logcat -c
adb shell am start -W -n "$PACKAGE/$ACTIVITY"

seen_native=0
for attempt in $(seq 1 90); do
  sleep 8
  adb logcat -d -v time > "$LOGFILE"
  if grep -E 'Active mods:.*(empyrean_campaign|fantasycore)' "$LOGFILE"; then
    seen_native=1
    break
  fi
  if grep -E 'FATAL EXCEPTION|Fatal signal|Process .*com.kalandos240.flareempyrean.*has died|Unable to start activity' "$LOGFILE"; then
    echo 'Found an Android crash while starting Flare:' >&2
    grep -n -A 28 -B 5 -E 'FATAL EXCEPTION|Fatal signal|Unable to start activity' "$LOGFILE" | tail -150 >&2 || true
    exit 1
  fi
  if [[ $((attempt % 6)) -eq 0 ]]; then
    echo "Checking Flare initialization ... ${attempt} / 90"
    adb shell dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity|mTopResumedActivity|org.flare.app' | tail -8 || true
  fi
done

if [[ "$seen_native" != 1 ]]; then
  echo "Never observed the native engine's Active mods log message." >&2
  grep -E 'FlarePort|SDL|main:|ModManager|flare|FATAL EXCEPTION' "$LOGFILE" | tail -100 >&2 || true
  exit 1
fi

sleep 12
adb logcat -d -v time > "$LOGFILE"
if grep -E 'FATAL EXCEPTION|Fatal signal' "$LOGFILE"; then
  echo "Native initialization started but an Android crash followed." >&2
  grep -n -A 25 -B 5 -E 'FATAL EXCEPTION|Fatal signal' "$LOGFILE" | tail -120 >&2 || true
  exit 1
fi

if ! adb shell pidof "$PACKAGE" >/dev/null 2>&1; then
  echo "The Flare process terminated after loading mods." >&2
  exit 1
fi

if ! adb shell dumpsys activity activities | grep -q 'org.flare.app.FLARE'; then
  echo "The SDL game activity never appeared after the first-launch installer." >&2
  exit 1
fi

# Capture the original title, then tap "Играть" using coordinates
# normalized to the emulator screenshot's *actual* pixel dimensions.
DIAGNOSTICS="${RUNNER_TEMP:-/tmp}"
TITLE_SCREEN="$DIAGNOSTICS/flare-native-start.png"
CHARACTER_SCREEN="$DIAGNOSTICS/flare-character-creation.png"
adb exec-out screencap -p > "$TITLE_SCREEN"

read -r tap_x tap_y < <(python - "$TITLE_SCREEN" <<'PY'
import struct
import sys
with open(sys.argv[1], "rb") as png:
    header = png.read(24)
if header[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit("Android screenshot is not PNG")
width, height = struct.unpack(">II", header[16:24])
print(round(width * 0.607), round(height * 0.725))
PY
)
echo "Touching Flare Play button at $tap_x, $tap_y"
adb shell input touchscreen tap "$tap_x" "$tap_y"

character_open=0
for attempt in $(seq 1 30); do
  sleep 3
  adb logcat -d -v time > "$LOGFILE"
  if grep -q 'FlarePort QA: character creator opened' "$LOGFILE"; then
    character_open=1
    break
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOGFILE"; then
    echo 'Game crashed while opening the character creator.' >&2
    exit 1
  fi
done

adb exec-out screencap -p > "$CHARACTER_SCREEN"
if [[ "$character_open" != 1 ]]; then
  echo 'Touching Play did not open the original character creator.' >&2
  grep -E 'FlarePort QA|FlarePort|SDL/APP|FATAL EXCEPTION' "$LOGFILE" | tail -100 >&2 || true
  exit 1
fi
python scripts/assert_screen_change.py "$TITLE_SCREEN" "$CHARACTER_SCREEN"
adb shell pidof "$PACKAGE" >/dev/null

# Confirm the installed campaign and Russian touchscreen settings.
DATA="/sdcard/Android/data/$PACKAGE/files"
adb shell "test -f '$DATA/mods/mods.txt' && test -d '$DATA/mods/empyrean_campaign'"
adb shell "test -d '$DATA/userdata/saves'"
adb shell "test -f '$DATA/config/flare-game/settings.txt'"
adb shell "cat '$DATA/config/flare-game/settings.txt'" | tr -d '\r' | grep -q '^language=ru$'
adb shell "cat '$DATA/config/flare-game/settings.txt'" | tr -d '\r' | grep -q '^touch_controls=1$'

# Verify that application-owned save files and custom settings survive a relaunch.
# This sentinel is strictly limited to the disposable emulator.
SAVES_SENTINEL="$DATA/userdata/saves/.flare-ci-persistence-test"
adb shell "printf 'test-save-2026' > '$SAVES_SENTINEL'"
adb shell "sed -i '/^pause_on_focus_loss=/d' '$DATA/config/flare-game/settings.txt'"
adb shell "printf '\\npause_on_focus_loss=0\\n' >> '$DATA/config/flare-game/settings.txt'"

# A second launch must not re-extract the campaign or reset user data.
MARKER="$DATA/.installed-empyrean-2026-10-11-v2"
adb shell "test -f '$MARKER'"
MARKER_BEFORE="$(adb shell stat -c '%Y' "$MARKER" | tr -d '\r')"
adb shell am force-stop "$PACKAGE"
adb shell am start -W -n "$PACKAGE/$ACTIVITY"
sleep 20
adb shell pidof "$PACKAGE" >/dev/null
MARKER_AFTER="$(adb shell stat -c '%Y' "$MARKER" | tr -d '\r')"
adb shell "cat '$SAVES_SENTINEL'" | tr -d '\r' | grep -qx 'test-save-2026'
adb shell "cat '$DATA/config/flare-game/settings.txt'" | tr -d '\r' | grep -qx 'pause_on_focus_loss=0'
if [[ "$MARKER_BEFORE" != "$MARKER_AFTER" ]]; then
  echo 'Reopening Flare unexpectedly re-extracted campaign assets.' >&2
  exit 1
fi
adb exec-out screencap -p > "$DIAGNOSTICS/flare-relaunch.png"
adb logcat -d -v time > "$LOGFILE"
if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOGFILE"; then
  echo 'Game crashed after relaunch.' >&2
  exit 1
fi

echo 'Flare touchscreen Play opened the original character creator.'
echo 'Campaign assets, custom settings and a simulated save persisted through relaunch.'
echo 'Gameplay, combat, character saves still need further automated or device QA.'
