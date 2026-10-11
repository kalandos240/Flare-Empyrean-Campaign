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

echo 'Flare: Empyrean Campaign native engine started with the real campaign on Android emulator.'
echo 'This is a smoke check only: touchscreen gameplay/save/load still need device QA.'
