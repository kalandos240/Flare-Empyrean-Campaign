# Flare: Empyrean Campaign — RuStore Android port

Independent **work-in-progress** Android packaging of the original open-source action RPG.

This repository contains the **port-specific source changes and build recipe**, not a
copy of hundreds of megabytes of upstream source and game assets. The build obtains
two pinned upstream revisions and creates an Android app from them:

- Engine: [flareteam/flare-engine](https://github.com/flareteam/flare-engine),
  commit `1969baeb89ebf94cf22e2bc2ed4e3d8413714d4f`.
- Game: [flareteam/flare-game](https://github.com/flareteam/flare-game),
  commit `af6eee6d339ac98011864bfe89da837fe7769c28`.

## Implemented for the initial Android port

- Uses the official Flare Android/SDL2 native code rather than replacing the gameplay.
- Packages the `default`, `fantasycore` and `empyrean_campaign` mods into the app.
- Provides a first-launch installer that unpacks original game files off the UI thread, reports progress and checks available disk space.
- Redirects the engine's config and saves to **app-specific Android storage**, separate from campaign assets; updates do not overwrite player saves.
- Removes broad `WRITE_EXTERNAL_STORAGE` and `MANAGE_EXTERNAL_STORAGE` permissions.
- Adds a separate Android launcher and explicit Android 12+ activity visibility settings.
- Targets ARMv7 and ARM64 to avoid large unused x86 shared libraries in RuStore builds.
- Includes a machine-readable campaign file count/uncompressed-size manifest and APK permission/ABI audits in CI.
- Configures app identifier `com.kalandos240.flareempyrean`, Android 8.0+ (min API 26) and target API 35.
- Uses the original Russian localization and gameplay, with an Android-specific **floating** left joystick, clearly labeled **«Атака»** (native MAIN2) and **«Действие»** (native ACCEPT: speak, pick up, use) rings. Input is tracked by individual fingers so movement and attacks can overlap.
- Includes automated Python packaging tests and an Android GitHub Actions build.

**Status:** Preliminary native Android port. The APK/AAB build and on-device gameplay
must pass testing before any submission to RuStore; a CI artifact is *not* a signed store release.

## Build and test

On each push to the port branch, [GitHub Actions](../../actions/workflows/android.yml)
runs packaging tests, downloads the pinned source revisions (including SDL git
submodules), generates `campaign.zip` and its size manifest, builds a debug APK
and an unsigned release AAB. It checks APK permissions, package identifier,
architecture support, and bundled game data. When successful, get the binaries from the workflow **Artifacts**.

For local builds:

1. Install Java 17, Android SDK API 35, Android NDK 27 and Android Studio/Gradle.
2. Clone the upstream engine, including its SDL submodules, and the game at the SHAs above.
3. Execute:

   ```bash
   python scripts/prepare_android.py --engine /path/to/flare-engine --game /path/to/flare-game
   cd /path/to/flare-engine/flare-android-project
   ./gradlew :app:assembleDebug
   ```

4. Install the debug APK on a real Android phone, then test initialization,
   touch controls, combat, map transitions, saves, relaunch, and Android back/home behavior.

The assets installer writes only `mods/` and `licenses/`. The engine writes
`config/` and `userdata/saves/` in Android's per-app external-files directory.
Android may delete app data when uninstalling the game, so preserve saves before removal.

## Licensing and RuStore publishing

The original engine is licensed under **GPL-3.0-or-later**. The game art and data
are under **CC-BY-SA 3.0**, with separate OFL fonts. Credits and applicable
license files are embedded in the game's data archive; credits for SDL and all
redistributed dependencies also need review before release.

Distribution (including commercial distribution) is permitted subject to the
actual license terms: copyright notices and attribution, corresponding source
availability, and share-alike obligations. Link to this build recipe and its
upstream sources in the RuStore description.

RuStore accepts signed **APK and AAB** packages, but requires a unique application
ID and signing credentials. This project deliberately does **not** store signing
keys or publish automatically. A signed release, real-device QA, accessibility,
store screenshots, privacy documentation and a complete license audit remain to do.

## Limitations / next steps

- Complete CI validation for the updated Android assets installer, and inspect APK/AAB sizes.
- Validate installation times and APK size on physical devices.
- Check Android 15 edge-to-edge layout, display cutouts, touch target sizes and input.
- Test save persistence, lifecycle pause/resume and crash recovery.
- Implement secure release signing and RuStore submission metadata.

This independent port is not affiliated with the original Flare developers.
