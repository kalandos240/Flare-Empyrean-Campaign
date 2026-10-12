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

# The mod-loader log precedes the actual rendered title on some cold boots.
# Do not send synthetic input until the native title has drawn at least once.
title_ready=0
for attempt in $(seq 1 40); do
  sleep 3
  adb logcat -d -v time > "$LOGFILE"
  if grep -q 'FlarePort QA: original title screen rendered' "$LOGFILE"; then
    title_ready=1
    break
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOGFILE"; then
    echo 'Native initialization crashed before rendering the title.' >&2
    grep -n -A 25 -B 5 -E 'FATAL EXCEPTION|Fatal signal' "$LOGFILE" | tail -120 >&2 || true
    exit 1
  fi
done
if [[ "$title_ready" != 1 ]]; then
  adb exec-out screencap -p > "${RUNNER_TEMP:-/tmp}/flare-title-not-ready.png"
  echo 'Flare loaded mods, but the original title screen did not render.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION|Fatal signal' "$LOGFILE" | tail -100 >&2 || true
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

# Both supported emulator APIs must demonstrate that the *original* Android
# title Play action opens the original native character creator by touch.
# Android 8 stops after the creator successfully constructs a gameplay state;
# Android 11 continues through the full intro and save/load regression.

read -r tap_x tap_y create_x create_y < <(python - "$TITLE_SCREEN" <<'PY'
import struct
import sys
with open(sys.argv[1], "rb") as png:
    header = png.read(24)
if header[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit("Android screenshot is not PNG")
width, height = struct.unpack(">II", header[16:24])
print(round(width * 0.607), round(height * 0.725),
      round(width * 0.337), round(height * 0.91))
PY
)
# Some headless emulators drop the first ADB tap on a cold title screen.
# Retry only if the original engine did NOT accept it. If Play was accepted,
# wait for character creation rather than sending another click into gameplay.
character_open=0
play_accepted=0
for play_attempt in $(seq 1 5); do
  echo "Touching Flare Play ($play_attempt/5) at $tap_x,$tap_y"
  adb shell input touchscreen tap "$tap_x" "$tap_y"
  for poll in $(seq 1 10); do
    sleep 2
    adb logcat -d -v time > "$LOGFILE"
    if grep -q 'FlarePort QA: character creator opened' "$LOGFILE"; then
      character_open=1
      break
    fi
    if grep -q 'FlarePort QA: original title Play accepted' "$LOGFILE"; then
      play_accepted=1
    fi
    if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOGFILE" || ! adb shell pidof "$PACKAGE" >/dev/null 2>&1; then
      echo 'Android game crashed or exited after tapping Play.' >&2
      exit 1
    fi
  done

  if [[ "$character_open" == 1 ]]; then
    break
  fi
  adb exec-out screencap -p > "$DIAGNOSTICS/flare-play-attempt-$play_attempt.png"
  if [[ "$play_accepted" == 1 ]]; then
    echo 'Native Play handler accepted input; waiting for a slow state transition.'
    for poll in $(seq 1 10); do
      sleep 2
      adb logcat -d -v time > "$LOGFILE"
      if grep -q 'FlarePort QA: character creator opened' "$LOGFILE"; then
        character_open=1
        break
      fi
      if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOGFILE"; then
        echo 'Game crashed after Play was accepted.' >&2
        exit 1
      fi
    done
    break
  fi
  echo "Engine did not acknowledge ADB Play tap $play_attempt."
done
adb exec-out screencap -p > "$CHARACTER_SCREEN"
if [[ "$character_open" != 1 ]]; then
  if [[ "$play_accepted" == 1 ]]; then
    echo 'REGRESSION: native Play accepted but character creation never opened.' >&2
  else
    echo 'INPUT FAILURE: title visible but all synthetic Play taps ignored.' >&2
  fi
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOGFILE" | tail -100 >&2 || true
  exit 1
fi
python scripts/assert_screen_change.py "$TITLE_SCREEN" "$CHARACTER_SCREEN"
adb shell pidof "$PACKAGE" >/dev/null

# Preset heroes have a non-empty default name. Press original "Создать" to
# exercise the native transition from character creation into gameplay.
read -r create_x create_y < <(python - "$CHARACTER_SCREEN" <<'PY'
import struct
import sys
with open(sys.argv[1], "rb") as png:
    png.seek(16)
    width, height = struct.unpack(">II", png.read(8))
print(round(width * 0.337), round(height * 0.908))
PY
)
echo "Creating the default hero by touch at $create_x, $create_y"
adb shell input touchscreen tap "$create_x" "$create_y"
gameplay_open=0
for attempt in $(seq 1 35); do
  sleep 3
  adb logcat -d -v time > "$LOGFILE"
  if grep -q 'FlarePort QA: gameplay state constructed' "$LOGFILE" \
      && grep -q 'FlarePort QA: create character pressed' "$LOGFILE"; then
    gameplay_open=1
    break
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOGFILE"; then
    echo 'Android game crashed during character creation.' >&2
    exit 1
  fi
done
if [[ "$gameplay_open" != 1 ]]; then
  echo 'Original Create button did not construct the gameplay state.' >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOGFILE" | tail -95 >&2 || true
  exit 1
fi

# API 26 compatibility check: native title, real touchscreen Play/Create,
# game-state construction and visible intro. The API 30 job tests save/load.
if [[ "${FLARE_SMOKE_CREATOR_ONLY:-0}" == 1 ]]; then
  sleep 5
  adb exec-out screencap -p > "$DIAGNOSTICS/flare-intro.png"
  adb shell pidof "$PACKAGE" >/dev/null
  echo 'PASSED: Android 8 original touchscreen character creation and native gameplay-state construction.'
  exit 0
fi

# The official campaign starts with a mandatory illustrated backstory after
# creating the hero. Record it separately: it is not the playable map!
sleep 10
adb exec-out screencap -p > "$DIAGNOSTICS/flare-intro.png"
read -r skip_x skip_y < <(python - "$DIAGNOSTICS/flare-intro.png" <<'PY'
import struct
import sys
with open(sys.argv[1], 'rb') as image:
    image.seek(16)
    width, height = struct.unpack('>II', image.read(8))
print(round(width * .978), round(height * .04))
PY
)
# The title screen also creates an empty intro cutscene; discard its old logs.
# Otherwise that earlier completion could make this check pass after a single tap.
adb logcat -c
intro_finished=0
last_next_count=0
# On resource-constrained GitHub emulators input events may take several frames
# to process. Verify actual Next-button clicks, not just ADB tap completion.
for page in $(seq 1 32); do
  echo "Advancing backstory tap $page at $skip_x,$skip_y"
  adb shell input touchscreen tap "$skip_x" "$skip_y"
  sleep 3
  adb logcat -d -v time > "$LOGFILE"
  if grep -q 'FlarePort QA: intro cutscene finished' "$LOGFILE"; then
    intro_finished=1
    break
  fi
  next_count="$(grep -c 'FlarePort QA: intro next arrow accepted' "$LOGFILE" || true)"
  if (( page % 4 == 0 )); then
    echo "Original cutscene Next button accepted $next_count taps so far."
    adb exec-out screencap -p > "$DIAGNOSTICS/flare-intro-progress.png"
  fi
  if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOGFILE"; then
    echo 'The game crashed while playing its opening cutscene.' >&2
    exit 1
  fi
done
if [[ "$intro_finished" != 1 ]]; then
  adb exec-out screencap -p > "$DIAGNOSTICS/flare-intro-stuck.png"
  echo "Backstory not completed; original Next accepted $next_count taps." >&2
  grep -E 'FlarePort QA|SDL/APP|FATAL EXCEPTION' "$LOGFILE" | tail -80 >&2 || true
  exit 1
fi

sleep 12
adb exec-out screencap -p > "$DIAGNOSTICS/flare-gameplay.png"
adb shell pidof "$PACKAGE" >/dev/null
echo 'Original hero created, opening cutscene finished and gameplay returned.'


# Android 11 blocks both the generic ADB UID and run-as from browsing
# /sdcard/Android/data. Instead use the emulator-only receiver, which executes
# within the game app and is never included in RuStore builds.
qa_probe() {
  local operation="$1"
  adb logcat -c
  adb shell am broadcast -n "$PACKAGE/org.flare.app.QaReceiver" \
    --es operation "$operation"
  sleep 2
  adb logcat -d -v time > "$LOGFILE"
  if ! grep -q "QA $operation PASS" "$LOGFILE"; then
    echo "App-owned Android storage QA failed: $operation" >&2
    grep -E 'FlareQA|FATAL EXCEPTION|Fatal signal' "$LOGFILE" | tail -50 >&2 || true
    exit 1
  fi
}

qa_probe inspect
qa_probe prepare

# Flare's native SDLInputState explicitly saves on SDL_WINDOWEVENT_MINIMIZED
# for mobile platforms. Home is an actual Android lifecycle transition;
# the resulting avatar.txt is the engine's real serialized character.
echo 'Pressing Android Home to trigger Flare native autosave'
adb shell input keyevent KEYCODE_HOME
sleep 8
adb logcat -d -v time > "$LOGFILE"
if ! grep -q 'InputState: Minimizing app, saving' "$LOGFILE"; then
  echo 'Expected native mobile save-on-minimize event not observed.' >&2
  grep -E 'InputState:|SDL/APP|FATAL EXCEPTION|Fatal signal' "$LOGFILE" | tail -100 >&2 || true
  exit 1
fi
qa_probe avatar

adb shell am force-stop "$PACKAGE"
adb shell am start -W -n "$PACKAGE/$ACTIVITY"
sleep 25
adb shell pidof "$PACKAGE" >/dev/null
qa_probe verify
qa_probe avatar
adb exec-out screencap -p > "$DIAGNOSTICS/flare-relaunch.png"
adb logcat -d -v time > "$LOGFILE"
if grep -Eq 'FATAL EXCEPTION|Fatal signal' "$LOGFILE"; then
  echo 'Game crashed after relaunch.' >&2
  exit 1
fi

echo 'Flare touchscreen Play opened the original character creator.'
echo 'Campaign assets, test-only save sentinel and custom settings persisted through relaunch.'
echo 'The native avatar save was written on Android Home and preserved after relaunch.'
echo 'Next: load this saved character through Flare original menu.'
bash scripts/emulator_load_test.sh
bash scripts/emulator_movement_test.sh
bash scripts/emulator_hud_test.sh
bash scripts/emulator_back_test.sh
bash scripts/emulator_death_test.sh

echo 'Touch controls, pause, save/load and original Game Over screen have emulator checks; real enemy hits and physical-device input still need QA.'
