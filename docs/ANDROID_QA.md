# Flare: Empyrean Campaign — Android / RuStore device acceptance checklist

**Status:** The Gradle/NDK CI build is a build verification, not gameplay certification.
The separate [Android emulator smoke workflow](../.github/workflows/android-smoke.yml)
builds an x86_64 testing APK, installs the campaign in an emulator, and checks
for the native engine's active-mods log entry and process survival. It uploads
a startup screenshot and log for review. Passing this check **does not** prove
that touch gameplay, all assets, and saving work on ARM devices.

Please test the debug APK on a physical Android phone and record its model,
Android version and reproducible issues in a GitHub issue.

## First launch and filesystem

- [ ] Start with a clean installation. Confirm that the Russian progress screen
      reports extraction progress and the game opens automatically afterwards.
- [ ] Check the launch without Wi-Fi/mobile data. No network connection should
      be required for the built-in Empyrean Campaign.
- [ ] Verify that the original **Empyrean Campaign** map, characters, textures,
      effects, fonts and sound assets are all present.
- [ ] Confirm that Russian text renders (including Cyrillic characters in menus,
      dialogs, quests, inventory and character screens).
- [ ] Launch again: asset extraction should be skipped when installation is complete.
- [ ] Force-stop during first-launch extraction and relaunch. Extraction must retry
      or resume safely, never treat an incomplete install as complete.
- [ ] Test low disk space (ideally in a virtual device or disposable test install).
      The launcher should explain the problem rather than crashing.
- [ ] Check `Android/data/com.kalandos240.flareempyrean/files/mods` contains
      `default`, `fantasycore`, `empyrean_campaign`, `game.txt`, and `mods.txt`.
- [ ] Confirm saves are under `userdata/saves` and options are under
      `config/flare-game`. These directories must not be overwritten by updating assets.

## Gameplay and touch

- [ ] Create a character, enter the campaign, move using the on-screen control.
- [ ] Test primary/secondary attack, powers, inventory, equipment, chests, vendors,
      dialogue, maps, journal and combat with only the touchscreen.
- [ ] Check touch targets and UI readability on narrow phones and 20:9 displays.
- [ ] Verify screen rotation is limited to landscape and content is not hidden
      by a notch or Android gesture navigation.
- [ ] Switch the game language and control preferences, exit, and reopen: the
      user's chosen settings should override first-run defaults.
- [ ] Test gamepad and Bluetooth controller (optional, if supported by SDL).

## Save, lifecycle and stability

- [ ] Create a save, obtain loot, exit the game and relaunch: player, inventory,
      experience and quest state must persist.
- [ ] Press Home and reopen after 30 seconds; check for input/audio freeze.
- [ ] Lock/unlock the device during gameplay. Check pause/resume and sound.
- [ ] Switch to another app, return, and save after the transition.
- [ ] Test the Android Back button/gesture at menu, gameplay and dialogue screens.
- [ ] Try 20+ minutes of combat, changing zones and loading a saved game.
- [ ] Test on Android 7+ (minimum API 24) and Android 15+ where devices are available.
- [ ] Record peak RAM, smoothness, asset unpacking time and actual disk usage.

## Store publication gates

- [ ] Download the current successful APK artifact from GitHub Actions.
- [ ] Run the CI manifest/architecture/permissions audit successfully.
- [ ] Sign the release using a protected store key (never check credentials into Git).
- [ ] Review complete license credits and provide corresponding source for GPL parts.
- [ ] Prepare real gameplay screenshots, icon, descriptions and content rating
      appropriate to the game (fantasy violence, blood/mild gore).
- [ ] Check store packaging size; RuStore's current published APK/AAB upload limit
      is 5 GB, not 100 MB: https://www.rustore.ru/help/developers/publishing-and-verifying-apps/app-publication
- [ ] Test installation and updates via RuStore before public release.

## A good bug report includes

Android model and version, build SHA / GitHub Actions run ID, exact screen/map,
steps to reproduce, expected behavior, actual behavior, and `adb logcat` excerpts
(with any personal data removed).
