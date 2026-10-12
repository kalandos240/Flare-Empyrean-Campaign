# Flare: Empyrean Campaign — Android / RuStore device acceptance checklist

**Status:** The Gradle/NDK CI build is a build verification, not gameplay certification.
The separate [Android emulator smoke workflow](../.github/workflows/android-smoke.yml)
builds an x86_64 testing APK, installs the campaign in an emulator, and checks
for the native engine's active-mods log entry and process survival. It uploads
a startup screenshot and log for review. Passing this check **does not** prove
that touch gameplay, all assets, and saving work on ARM devices.

Please test the debug APK on a physical Android phone and record its model,
Android version and reproducible issues in a GitHub issue.

## Cold-start Play regression (2026-10-12)

- [Emulator run #38246160209](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38246160209) failed at the first synthetic **Играть** tap: all pinned Flare mods loaded, but the test did not observe character creation. It did not report an Android native crash. On the same commit, the ARM package build and optional VK SDK compilation both passed.
- Emulator-only instrumentation now distinguishes a rendered original title screen, an accepted original Play click, and the subsequent character-creation state. The smoke test waits until the title renders, retries **only unacknowledged** synthetic taps, and uploads screenshots on unsuccessful attempts. Accepted clicks followed by stalled state transitions are reported as regressions, not retried blindly.
- This diagnostic/test hardening does not by itself prove a gameplay fix. Review the subsequent CI run before considering the test reliable. The production ARM build contains no QA markers.

## Verified CI evidence (2026-10-11)

- [ARM release/debug build #38157326908](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38157326908) — successful APK and AAB packaging.
- [x86_64 Android emulator smoke #38157366384](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38157366384) — successful. On Android API 30, the actual Flare engine logs
  `Active mods: default, fantasycore (1.15.01), empyrean_campaign (1.15.01)`
  and remains running with the SDL game activity.
- Emulator screenshot in the workflow's `flare-emulator-diagnostics` artifact shows
  the fully rendered original title screen, artwork, and **Russian** menu labels.
- The engine logs an app-owned config path:
  `/storage/emulated/0/Android/data/com.kalandos240.flareempyrean/files/config/flare-game/`
  and separate `userdata/` and game data paths.
- [ARM APK/AAB build #38159434292](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38159434292) — successful release packaging following touchscreen character-creation changes.
- [Android emulator character creation #38159434369](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38159434369) — confirmed touchscreen **Play** and **Create** pressed, with original Russian character creation and illustrated Empyrean opening backstory displayed. Its later file-inspection step failed due Android 11 ADB scoped-storage restrictions, not a reported native engine crash.
- The screenshot originally named `flare-gameplay.png` in this run is an **intro cutscene** (floating Empyrean city), *not* proof that the playable map is ready. The current emulator test now skips the backstory and captures a separate map screenshot.
- Emulator-only tests use a temporary exported `QaReceiver` to inspect files through the app's own UID. This receiver is **not** included in the RuStore APK or AAB.
- [RuStore ARM debug APK and release AAB #38160493213](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38160493213) — **passed** with the current release-preparation code.
- [Android 11 emulator full campaign start #38160493210](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38160493210) — **passed**: touchscreen Play > character Create, all 8 pages of original introductory cutscene, then actual opening map **Прибытие** with original Russian dialogue, health/mana bars, minimap and inventory/skill toolbar. This is confirmed by the original gameplay screenshot in the `flare-emulator-diagnostics` artifact.
- In that run, Android Home triggered the engine's original `SDL_WINDOWEVENT_MINIMIZED` save handler, which wrote **userdata/saves/empyrean/1/avatar.txt**. The emulator-only in-app QA receiver verified the real avatar bytes remained identical after the app was force-stopped and relaunched. Custom settings and simulated sentinel also survived.
- **Still unverified:** moving/combat with touch controls, character loading through the original Load menu, device audio, real ARM-device performance, and installation from the RuStore client. Android emulator save persistence is verified, but full game progress regression tests remain to be written.

## Saved-character reload evidence (2026-10-12)

- [Android emulator load regression #38179244218](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38179244218) **passed**: the actual `userdata/saves/empyrean/1/avatar.txt` survives force-stop/relaunch; touching **Играть** opens the original Russian saved-game menu; touching **Загрузить игру** calls native `SaveLoad::loadGame()` and renders the original **Прибытие** map again.
- The diagnostic screenshot `flare-loaded-gameplay.png` also shows the original Flare touch-control circles at the bottom left/right after the map loads. Joystick movement is being checked separately and is **not yet certified**.
- The first test failure [#38178363395](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38178363395) was a QA coordinate miss above the Load button. Fixed by measuring the real button in the screenshot; the later test above passed.

## Verified original touchscreen movement (2026-10-12)

- [Android emulator regression #38235332631](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38235332631) **passed** with pinned upstream Flare and the original Empyrean campaign. The same run recreated the character, completed the original opening cinematic, wrote/preserved the real native avatar save on Android Home, reloaded the saved character via the Russian **Загрузить игру** menu, and exercised the on-screen joystick.
- The test instrumented the unmodified upstream gameplay **only in the disposable emulator checkout** to verify both a real directional input and a measurable delta in `pc->stats.pos`: `PASSED: original Flare virtual joystick moved the real saved hero.`
- Screenshot and log artifacts: `flare-after-joystick.png`, `flare-loaded-gameplay.png`, `flare-joystick-test.log`, downloadable from that run. The normal RuStore ARM package does **not** include the test receiver or C++ log instrumentation.
- **Still unverified:** real-device touch ergonomics, attacks/combat, abilities, inventory/quests, long-term stability, FPS/battery, Android Back and lock/unlock cycles, and signed release installation.

## Verified touchscreen movement and release audit (2026-10-12)

- [Full Android emulator flow #38235332631](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38235332631) **passed**: first-run install, Russian title, touchscreen character creation, all eight backstory stages, first playable map, engine autosave on Home, restart, original saved-game menu, native `SaveLoad::loadGame()`, and **virtual-joystick hero movement** on a real loaded map. The test-only engine logs both `virtual joystick directional input received` and `hero moved 0.35 -0.35` (distance over half a tile), with before/after gameplay screenshots in the workflow artifact.
- [RuStore ARM debug APK / unsigned release AAB #38235670534](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38235670534) **passed** including an audit that rejects any accidentally packaged exported emulator-only `QaReceiver`.
- The preceding [emulator run #38179949594](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38179949594) failed during cutscene progression (before joystick testing). The successful replacement now records genuine Next-button acceptance and captures screenshots when a slow emulator is delayed.
- **Still open:** touch attacks, skill actions, inventory and quest UI, combat, real-device ARM testing, audio lifecycle, full progression and store signing/publication. A passing emulator movement test does not imply these areas have been certified.

## Asset installer hardening (2026-10-12)

- The install marker is checked by **exact UTF-8 version contents**, not only by its filename and byte length. A corrupted or mismatched marker causes asset reinstallation.
- Each asset is first unpacked to a same-directory `.flare-installing` file, then renamed into place after the ZIP entry finishes. An interrupted or out-of-space extraction cannot leave a half-written *destination file* for that entry. An interrupted whole update still needs another installation pass; this is not a transaction for the entire campaign.
- The installer rejects duplicate ZIP entry names and ensures the total number of files **and actual decompressed byte count** equal the bundled manifest. Unexpected size growth fails before a completion marker is written.
- Emulator-only `QaReceiver.inspect` now checks that no temporary asset remains after successful first installation. The receiver remains prohibited in release APKs.
- These checks are **not** a physical-device certification. Test low-disk-space interruption and interrupted updates on a disposable device.

## Campaign archive path isolation (2026-10-12)

- The installer uses a pure Java validator for both installed ZIP entries and their temporary `.flare-installing` paths. Only children of `mods/` and `licenses/` are accepted. Other app-private paths (especially `userdata/saves/`) are explicitly inaccessible to the installer.
- Traversal like `mods/../userdata/saves/avatar.txt`, dot segments, duplicate separators, backslashes, null bytes, and symlink redirects are rejected.
- A standalone JVM regression test checks these cases, including existing symlink redirects to save files. Temporary resources use exclusive `createNewFile()` creation so even dangling symlinks cannot be followed by `FileOutputStream`. A broken directory link fails the installer's `mkdirs()` check.
- **Minimum Android 8.0 (API 26)**. The production validator uses `java.nio.file.Files.isSymbolicLink()` to reject existing and dangling symlinks at every archive path component, plus exclusive temporary file creation as defense in depth.
- This protects against malformed campaign archives but does not replace physical-device install/upgrade QA.

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

## Touch-control verification (2026-10-12)

- [Successful original-joystick test #38235332631](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38235332631) confirms a full touch-only character creation and save/load cycle, followed by a 2.6-second drag of the **original left virtual movement ring**. Native `MenuTouchControls` received directional input and `Avatar::stats.pos` changed by **(+0.35, −0.35) map units**. The original map and full HUD were captured in `flare-after-joystick.png`.
- The earlier failed [joystick smoke #38179949594](https://github.com/kalandos240/Flare-Empyrean-Campaign/actions/runs/38179949594) stopped at the intro cutscene *before* testing movement. New diagnostic Next-button instrumentation and retries produced the successful run above.
- The next emulator scenario opens/closes the native inventory with the HUD button, compares screenshots, and tests primary melee/power queueing via the right virtual button. It does **not** constitute a real enemy-combat test until one is separately implemented and verified.
- The RuStore production build includes a CI guard against the emulator-only exported `QaReceiver`; this test bridge is **not distributed**.

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
- [ ] Test on **Android 8.0+ (minimum API 26)** and Android 15+ where devices are available. Android 7.x (API 24–25) is intentionally unsupported.
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
