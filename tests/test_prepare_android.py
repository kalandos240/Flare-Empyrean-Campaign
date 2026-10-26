import tempfile
import unittest
from xml.etree import ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from scripts.prepare_android import (
    CONTENT_VERSION,
    MANIFEST,
    PACKAGE_ID,
    patch_sdl_makefiles,
    prepare,
    replace_cpp_function,
)


class PrepareAndroidTests(unittest.TestCase):
    def test_replace_cpp_function_preserves_following_code(self):
        source = (
            "void Platform::setPaths() {\n"
            "  if (true) { old(); }\n"
            "}\n"
            "void another() { keep(); }\n"
        )
        changed = replace_cpp_function(
            source, "void Platform::setPaths()", "void Platform::setPaths() { new_path(); }"
        )
        self.assertIn("new_path();", changed)
        self.assertNotIn("old();", changed)
        self.assertIn("void another() { keep(); }", changed)

    def test_end_to_end_preparation_with_fixture_content(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            engine = parent / "engine"
            game = parent / "game"
            app = engine / "flare-android-project/app"
            jni = app / "src/main/jni"
            (jni / "SDL2_image").mkdir(parents=True)
            (jni / "SDL2_mixer").mkdir(parents=True)
            (app / "src/main/res/values").mkdir(parents=True)
            (engine / "src").mkdir(parents=True)
            (engine / "distribution").mkdir(parents=True)
            # The pinned upstream checkout provides this official transparent
            # Flare launcher logo; fake it for fixture-only packaging tests.
            Image.new("RGBA", (256, 256), (255, 150, 0, 120)).save(
                engine / "distribution/flare_logo_icon.png"
            )
            (engine / "mods/default").mkdir(parents=True)
            (game / "mods/fantasycore").mkdir(parents=True)
            (game / "mods/empyrean_campaign").mkdir(parents=True)

            (engine / "flare-android-project/gradle.properties").write_text("android.useAndroidX=false\n")
            (app / "build.gradle").write_text("old")
            (jni / "Application.mk").write_text("APP_ABI := armeabi-v7a arm64-v8a x86 x86_64\n")
            (engine / "src/GameStatePlay.cpp").write_text(
                "\tsecond_timer.setDuration(settings->max_frames_per_sec);\n"
                "\t\tsnd->stopMusic();\n"
                "\t\tshowLoading();\n"
                "\t\tsetRequestedGameState(new GameStateTitle());\n"
                "\n\t\tsave_load->setGameSlot(0);\n"
            )
            # The Android port copies its real native touch implementation
            # into the detached engine checkout on every preparation.
            (engine / "src/InputState.h").write_text(
                "class InputState {\npublic:\nprotected:\n\tPoint scaleMouse(unsigned x, unsigned y);\n};\n"
            )
            (engine / "src/MenuTouchControls.cpp").write_text("upstream touch implementation")
            (engine / "src/MenuTouchControls.h").write_text("upstream touch header")
            (engine / "src/MenuManager.cpp").write_text("\ttouch_controls = new MenuTouchControls();\n")
            (engine / "src/GameStateTitle.cpp").write_text(
                "label_version->setText(VersionInfo::createVersionStringFull());\n"
            )
            (engine / "src/GameStateCutscene.cpp").write_text(
                "void GameStateCutscene::logic() {\n"
                "\tif (scene_index < scenes.size())\n"
                "\t\tstatus = scenes[scene_index]->logic();\n"
                "}\n"
                "void GameStateCutscene::render() {\n"
                "\t\telse if (status == Scene::PREV && scene_index > 0) {\n"
                "\t\t\tscenes[scene_index]->reset();\n"
                "\t\t\tscene_index--;\n"
                "\t\t\tscenes[scene_index]->reset();\n"
                "\t\t}\n"
                "\t}\n"
                "}\n"
            )
            (engine / "src/PlatformAndroid.cpp").write_text(
                "void Platform::setPaths() { old(); }\nvoid other() {}\n"
            )
            (jni / "SDL2_image/Android.mk").write_text(
                "SUPPORT_JPG := true\nSUPPORT_WEBP := true\n"
            )
            (jni / "SDL2_mixer/Android.mk").write_text(
                "SUPPORT_MOD_MIKMOD := true\nSUPPORT_MP3_SMPEG := true\n"
            )
            (engine / "mods/default/d.txt").write_text("engine assets")
            (game / "mods/fantasycore/f.txt").write_text("core assets")
            (game / "mods/empyrean_campaign/e.txt").write_text("campaign assets")
            (engine / "COPYING").write_text("GPL-3.0")
            (game / "LICENSE.txt").write_text("CC-BY-SA-3.0")

            project = prepare(engine, game)
            self.assertEqual(project, engine / "flare-android-project")
            catalog_icon = engine / "flare-android-project/rustore-icon-512.png"
            with Image.open(catalog_icon) as store_icon:
                self.assertEqual(store_icon.size, (512, 512))
                self.assertEqual(store_icon.mode, "RGB")
                for density, size in (("mdpi", 48), ("hdpi", 72),
                                      ("xhdpi", 96), ("xxhdpi", 144),
                                      ("xxxhdpi", 192)):
                    installed_icon = app / f"src/main/res/drawable-{density}/ic_launcher.png"
                    with Image.open(installed_icon) as launcher:
                        self.assertEqual(launcher.size, (size, size))
                        self.assertEqual(launcher.mode, "RGB")
                        self.assertEqual(
                            launcher.tobytes(),
                            store_icon.resize((size, size), Image.Resampling.LANCZOS).tobytes(),
                        )
            self.assertIn(PACKAGE_ID, (app / "build.gradle").read_text())
            self.assertIn("targetSdk 35", (app / "build.gradle").read_text())
            self.assertIn("minSdk 26", (app / "build.gradle").read_text())
            self.assertIn("versionCode 4", (app / "build.gradle").read_text())
            self.assertIn("versionName '0.2.2'", (app / "build.gradle").read_text())
            self.assertIn("FLARE_RELEASE_KEYSTORE_PATH", (app / "build.gradle").read_text())
            self.assertIn("FLARE_RELEASE_KEYSTORE_PASSWORD", (app / "build.gradle").read_text())
            self.assertIn("keyAlias 'flare'", (app / "build.gradle").read_text())
            self.assertIn('label_version->setText("Android 8.0+")',
                          (engine / "src/GameStateTitle.cpp").read_text())
            cutscene_source = (engine / "src/GameStateCutscene.cpp").read_text()
            self.assertIn("scene_index < scenes.size() && status == Scene::NO_CHANGE", cutscene_source)
            self.assertIn("status = Scene::NO_CHANGE;", cutscene_source)
            self.assertEqual(cutscene_source.count("status = Scene::NO_CHANGE;"), 1)

            self.assertNotIn("minSdk 24", (app / "build.gradle").read_text())
            self.assertEqual((jni / "Application.mk").read_text(), "APP_ABI := armeabi-v7a arm64-v8a\n")
            prepare(engine, game, abis="x86_64")
            self.assertEqual((jni / "Application.mk").read_text(), "APP_ABI := x86_64\n")
            with self.assertRaises(ValueError):
                prepare(engine, game, abis="INVALID_ABI")
            source = engine / "src"
            self.assertIn("touchFingerCount() const", (source / "InputState.h").read_text())
            self.assertEqual((source / "InputState.h").read_text().count("touchFingerCount() const"), 1)
            self.assertIn("move_finger_id", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("new MenuTouchControls(this)", (source / "MenuManager.cpp").read_text())
            self.assertIn('setText("Атаковать")', (source / "MenuTouchControls.cpp").read_text())
            self.assertIn('setText("Использовать")', (source / "MenuTouchControls.cpp").read_text())
            self.assertIn('setText("Навык")', (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("skill_finger_id != -1", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("Input::ACCEPT", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("touchFingerId", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("touchFingerPosition", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("checkAllowMain1()", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("menu->menus_open || menu->pause", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("skill_center.x = (main1_center.x + main2_center.x) / 2", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("hotbar_finger_id = id;", (source / "MenuTouchControls.cpp").read_text())
            self.assertIn("getExternalFilesDir", (app / "src/main/java/org/flare/app/LaunchActivity.java").read_text())
            launcher = (app / "src/main/java/org/flare/app/LaunchActivity.java").read_text()
            self.assertIn(CONTENT_VERSION, launcher)
            self.assertIn("campaign-info.properties", launcher)
            self.assertIn("getUsableSpace()", launcher)
            self.assertIn("reportProgress(", launcher)
            self.assertIn("language=ru", launcher)
            self.assertIn("touch_controls=1", launcher)
            self.assertIn("!settingsFile.exists()", launcher)
            self.assertIn(".pending", launcher)
            self.assertIn("isCurrentInstall(marker)", launcher)
            self.assertIn("extractedBytes != requiredBytes", launcher)
            self.assertIn("pending.renameTo(destination)", launcher)
            self.assertIn(".flare-installing", launcher)
            self.assertIn("seenEntries.add(entryName)", launcher)
            self.assertIn("CampaignPathValidator.resolve(root, entryName)", launcher)
            self.assertIn("CampaignPathValidator.resolve(root, entryName + \".flare-installing\")", launcher)
            self.assertIn("pending.createNewFile()", launcher)
            self.assertTrue((app / "src/main/java/org/flare/app/CampaignPathValidator.java").is_file())
            validator = (app / "src/main/java/org/flare/app/CampaignPathValidator.java").read_text()
            self.assertIn("Files.isSymbolicLink(cursor)", validator)
            self.assertIn("renameTo(marker)", launcher)
            self.assertNotIn("MANAGE_EXTERNAL_STORAGE", (app / "src/main/AndroidManifest.xml").read_text())
            self.assertNotIn("WRITE_EXTERNAL_STORAGE", (app / "src/main/AndroidManifest.xml").read_text())
            self.assertIn("SDL_AndroidGetExternalStoragePath", (engine / "src/PlatformAndroid.cpp").read_text())
            self.assertIn("void other() {}", (engine / "src/PlatformAndroid.cpp").read_text())
            self.assertIn("SUPPORT_JPG := false", (jni / "SDL2_image/Android.mk").read_text())
            self.assertIn("SUPPORT_WEBP := false", (jni / "SDL2_image/Android.mk").read_text())
            self.assertIn("SUPPORT_MOD_MIKMOD := false", (jni / "SDL2_mixer/Android.mk").read_text())
            self.assertIn("SUPPORT_MP3_SMPEG := false", (jni / "SDL2_mixer/Android.mk").read_text())

            # Production build: no advertising SDK, network permission or JNI hook.
            default_gradle = (app / "build.gradle").read_text()
            default_manifest = (app / "src/main/AndroidManifest.xml").read_text()
            self.assertNotIn("com.my.target:mytarget-sdk", default_gradle)
            self.assertIn("android.useAndroidX=false", (engine / "flare-android-project/gradle.properties").read_text())
            self.assertNotIn("android.permission.INTERNET", default_manifest)
            self.assertFalse((app / "src/main/java/org/flare/app/VkAdsBridge.java").exists())
            self.assertNotIn("onGameSessionEnded", (engine / "src/GameStatePlay.cpp").read_text())
            self.assertNotIn("onGameSessionStarted", (engine / "src/GameStatePlay.cpp").read_text())

            with ZipFile(app / "src/main/assets/campaign.zip") as archive:
                paths = set(archive.namelist())
                total_bytes = sum(entry.file_size for entry in archive.infolist())
                props = dict(
                    line.split("=", 1)
                    for line in (app / "src/main/assets/campaign-info.properties").read_text().splitlines()
                )
                self.assertEqual(int(props["files"]), len(paths))
                self.assertEqual(int(props["bytes"]), total_bytes)
                self.assertIn("mods/default/d.txt", paths)
                self.assertIn("mods/fantasycore/f.txt", paths)
                self.assertIn("mods/empyrean_campaign/e.txt", paths)
                self.assertIn("mods/mods.txt", paths)
                self.assertIn("mods/game.txt", paths)
                self.assertIn("licenses/flare-engine-GPL-3.0.txt", paths)
                self.assertIn("licenses/flare-game-CC-BY-SA-3.0.txt", paths)
                self.assertEqual(
                    archive.read("mods/mods.txt").decode(),
                    "fantasycore\nempyrean_campaign\n",
                )

            with self.assertRaises(ValueError):
                prepare(engine, game, vk_interstitial_slot=-1)
            # Opt-in source generation and dependency wiring, no live ad requests.
            prepare(engine, game, abis="x86_64", vk_interstitial_slot=314159)
            self.assertIn("com.my.target:mytarget-sdk:5.52.5", (app / "build.gradle").read_text())
            self.assertIn("android.useAndroidX=true", (engine / "flare-android-project/gradle.properties").read_text())
            self.assertIn("android.permission.INTERNET", (app / "src/main/AndroidManifest.xml").read_text())
            self.assertIn("new VkAdsBridge(this, 314159)", (app / "src/main/java/org/flare/app/FLARE.java").read_text())
            self.assertTrue((app / "src/main/java/org/flare/app/VkAdsBridge.java").is_file())
            cpp = (engine / "src/GameStatePlay.cpp").read_text()
            self.assertIn('GetMethodID(clazz, "onGameSessionEnded", "()V")', cpp)
            self.assertIn('GetMethodID(vk_class, "onGameSessionStarted", "()V")', cpp)
            self.assertIn("onGameSessionStarted", (app / "src/main/java/org/flare/app/FLARE.java").read_text())
            self.assertIn("save_load->setGameSlot(0);", cpp)
            self.assertIn("setPrivacyReady", (app / "src/main/java/org/flare/app/VkAdsBridge.java").read_text())
            vk_activity = (app / "src/main/java/org/flare/app/FLARE.java").read_text()
            self.assertIn("showAdPrivacyChoices()", vk_activity)
            self.assertIn('setTitle("VK Реклама: конфиденциальность")', vk_activity)
            self.assertIn("vkAds.setPrivacyReady(true)", vk_activity)
            self.assertIn("vkAds.setPrivacyReady(false)", vk_activity)
            self.assertIn("setCancelable(false)", vk_activity)
            self.assertNotIn("showAdPrivacyChoices()", (app / "src/main/java/org/flare/app/LaunchActivity.java").read_text())
            self.assertIn("if (save_on_exit)", cpp)

            # Re-running preparation with the same ad slot must not duplicate
            # C++ JNI hooks or require a clean checkout.
            prepare(engine, game, vk_interstitial_slot=314159)
            cpp = (engine / "src/GameStatePlay.cpp").read_text()
            self.assertEqual(cpp.count('GetMethodID(clazz, "onGameSessionEnded", "()V")'), 1)
            self.assertEqual(cpp.count('GetMethodID(vk_class, "onGameSessionStarted", "()V")'), 1)
            self.assertEqual(cpp.count('#include "SDL_system.h"'), 1)

            # Most importantly, turning ads OFF must restore the offline build.
            prepare(engine, game, vk_interstitial_slot=0)
            self.assertIn("android.useAndroidX=false", (engine / "flare-android-project/gradle.properties").read_text())
            self.assertNotIn("mytarget-sdk", (app / "build.gradle").read_text())
            self.assertNotIn("android.permission.INTERNET", (app / "src/main/AndroidManifest.xml").read_text())
            self.assertFalse((app / "src/main/java/org/flare/app/VkAdsBridge.java").exists())
            self.assertNotIn("VkAdsBridge", (app / "src/main/java/org/flare/app/FLARE.java").read_text())
            self.assertNotIn("onGameSessionEnded", (engine / "src/GameStatePlay.cpp").read_text())
            self.assertNotIn("onGameSessionStarted", (engine / "src/GameStatePlay.cpp").read_text())
            self.assertNotIn('#include "SDL_system.h"', (engine / "src/GameStatePlay.cpp").read_text())

            # And an opted-in build remains possible after an offline one.
            prepare(engine, game, vk_interstitial_slot=314159)
            self.assertIn("android.useAndroidX=true", (engine / "flare-android-project/gradle.properties").read_text())
            self.assertTrue((app / "src/main/java/org/flare/app/VkAdsBridge.java").is_file())
            self.assertEqual(
                (engine / "src/GameStatePlay.cpp").read_text().count('GetMethodID(clazz, "onGameSessionEnded", "()V")'),
                1,
            )
            self.assertEqual(
                (engine / "src/GameStatePlay.cpp").read_text().count('GetMethodID(vk_class, "onGameSessionStarted", "()V")'),
                1,
            )


            # Yandex-only configuration, including safe replacement of VK.
            with self.assertRaises(ValueError):
                prepare(engine, game, yandex_interstitial_unit="demo-interstitial-yandex")
            with self.assertRaises(ValueError):
                prepare(engine, game, yandex_interstitial_unit='R-M-123"; System.exit(0)')
            prepare(engine, game, yandex_interstitial_unit="R-M-CI-PLACEHOLDER")
            yandex = app / "src/main/java/org/flare/app/YandexAdsBridge.java"
            self.assertTrue(yandex.exists())
            self.assertFalse((app / "src/main/java/org/flare/app/VkAdsBridge.java").exists())
            self.assertIn("com.yandex.android:mobileads:8.5.0", (app / "build.gradle").read_text())
            self.assertNotIn("mytarget-sdk", (app / "build.gradle").read_text())
            self.assertIn("android.useAndroidX=true", (engine / "flare-android-project/gradle.properties").read_text())
            yandex_manifest = (app / "src/main/AndroidManifest.xml").read_text()
            self.assertIn('com.yandex.mobile.ads.AUTOMATIC_SDK_INITIALIZATION', yandex_manifest)
            self.assertIn('android:value="false"', yandex_manifest)
            self.assertIn("android.permission.INTERNET", yandex_manifest)
            ET.fromstring(yandex_manifest)  # Compile test must reject malformed Android XML.
            yandex_activity = (app / "src/main/java/org/flare/app/FLARE.java").read_text()
            self.assertIn("new YandexAdsBridge(this, \"R-M-CI-PLACEHOLDER\")", yandex_activity)
            self.assertIn('setTitle("Яндекс Реклама: конфиденциальность")', yandex_activity)
            self.assertIn("yandexAds.setPrivacyReady(true)", yandex_activity)
            self.assertIn("yandexAds.setPrivacyReady(false)", yandex_activity)
            self.assertNotIn("VkAdsBridge", yandex_activity)
            self.assertIn("setPrivacyReady", yandex.read_text())
            self.assertIn("YandexAds.setUserConsent(true)", yandex.read_text())
            self.assertIn("new InterstitialAdLoader(activity)", yandex.read_text())
            self.assertIn("onGameSessionEnded", (engine / "src/GameStatePlay.cpp").read_text())

            # Combining both networks never queues TWO fullscreen ads on exit.
            prepare(engine, game, vk_interstitial_slot=314159,
                    yandex_interstitial_unit="R-M-CI-PLACEHOLDER")
            combined_activity = (app / "src/main/java/org/flare/app/FLARE.java").read_text()
            self.assertIn('getSharedPreferences("flare_ads", MODE_PRIVATE)', combined_activity)
            self.assertIn('putBoolean("next_vk", !currentNetworkVk)', combined_activity)
            self.assertIn("if (currentNetworkVk && vkAds != null)", combined_activity)
            self.assertIn("if (!currentNetworkVk && yandexAds != null)", combined_activity)
            self.assertIn("vkAds.setPrivacyReady(true)", combined_activity)
            self.assertIn("yandexAds.setPrivacyReady(true)", combined_activity)
            self.assertIn('setTitle("Реклама VK и Яндекса: конфиденциальность")', combined_activity)
            combined_gradle = (app / "build.gradle").read_text()
            self.assertIn("mytarget-sdk:5.52.5", combined_gradle)
            self.assertIn("mobileads:8.5.0", combined_gradle)
            ET.fromstring((app / "src/main/AndroidManifest.xml").read_text())
            native = (engine / "src/GameStatePlay.cpp").read_text()
            self.assertEqual(native.count('GetMethodID(clazz, "onGameSessionEnded", "()V")'), 1)
            prepare(engine, game, vk_interstitial_slot=314159,
                    yandex_interstitial_unit="R-M-CI-PLACEHOLDER")
            self.assertEqual((engine / "src/GameStatePlay.cpp").read_text().count(
                'GetMethodID(clazz, "onGameSessionEnded", "()V")'), 1)

            # Clear BOTH network SDKs, manifest metadata, JNI hooks and permissions.
            prepare(engine, game)
            self.assertFalse(yandex.exists())
            self.assertFalse((app / "src/main/java/org/flare/app/VkAdsBridge.java").exists())
            self.assertNotIn("mobileads", (app / "build.gradle").read_text())
            self.assertNotIn("mytarget-sdk", (app / "build.gradle").read_text())
            self.assertNotIn("INTERNET", (app / "src/main/AndroidManifest.xml").read_text())
            self.assertNotIn("AUTOMATIC_SDK_INITIALIZATION", (app / "src/main/AndroidManifest.xml").read_text())
            self.assertNotIn("onGameSessionEnded", (engine / "src/GameStatePlay.cpp").read_text())
            self.assertIn("android.useAndroidX=false",
                          (engine / "flare-android-project/gradle.properties").read_text())


    def test_android_8_smoke_reaches_native_character_creation(self):
        root = Path(__file__).resolve().parents[1]
        smoke = (root / "scripts/emulator_smoke.sh").read_text()
        workflow = (root / ".github/workflows/android-smoke.yml").read_text()
        # The runner invokes a *single shell command*: matrix API 26 sets
        # creator-only mode, while API 30 runs the complete campaign test.
        self.assertIn("FLARE_SMOKE_CREATOR_ONLY=${{ matrix.api_level == 26 && '1' || '0' }}", workflow)
        self.assertIn("api_level: [26, 30]", workflow)
        self.assertIn("FlarePort QA: gameplay state constructed", smoke)
        self.assertIn("FLARE_SMOKE_CREATOR_ONLY", smoke)
        self.assertNotIn("FLARE_SMOKE_BOOT_ONLY", smoke)
        self.assertLess(
            smoke.index("FlarePort QA: gameplay state constructed"),
            smoke.index('if [[ "${FLARE_SMOKE_CREATOR_ONLY:-0}" == 1 ]]'),
        )

    def test_android_back_pause_regression_is_wired(self):
        root = Path(__file__).resolve().parents[1]
        smoke = (root / "scripts/emulator_smoke.sh").read_text()
        back = (root / "scripts/emulator_back_test.sh").read_text()
        workflow = (root / ".github/workflows/android-smoke.yml").read_text()
        instrument = (root / "scripts/emulator_instrument.py").read_text()
        self.assertIn("bash scripts/emulator_back_test.sh", smoke)
        self.assertIn("KEYCODE_BACK", back)
        self.assertIn("check_back_transition opened", back)
        self.assertIn("check_back_transition closed", back)
        self.assertIn("FlarePort QA: original pause menu $expected", back)
        self.assertIn("flare-back-test.log", workflow)
        self.assertIn("qa_pause_was_visible", instrument)
        self.assertIn("src / \"MenuManager.cpp\"", instrument)

    def test_respawn_marker_targets_health_reset_not_hud_log(self):
        src = (Path(__file__).resolve().parents[1] / "scripts/emulator_instrument.py").read_text()
        self.assertIn("'\\tif (pc->respawn) {\\n\\t\\tpc->stats.alive = true;\\n'", src)
        self.assertIn('FlarePort QA: original hero respawn reached', src)
        self.assertNotIn("'\\tif (pc->respawn) {\\n',", src)

    def test_death_end_to_end_uses_test_only_request(self):
        root = Path(__file__).resolve().parents[1]
        receiver = (root / "android/QaReceiver.java").read_text()
        engine = (root / "scripts/emulator_instrument.py").read_text()
        script = (root / "scripts/emulator_death_test.sh").read_text()
        workflow = (root / ".github/workflows/android-smoke.yml").read_text()
        self.assertIn('trigger-death', receiver)
        self.assertIn('pc->stats.hp = 0', engine)
        self.assertIn('original Game Over dialog displayed', engine)
        self.assertIn('original Game Over dialog displayed', script)
        self.assertIn('bash scripts/emulator_death_test.sh', (root / "scripts/emulator_smoke.sh").read_text())
        self.assertIn('flare-death-screen.png', workflow)
        self.assertIn('original hero respawn reached', engine)
        self.assertIn('original hero respawn reached', script)
        self.assertIn('continue center %d %d viewport %d %d', engine)
        self.assertIn('continue center (\\d+)', script)
        self.assertNotIn('height * 322 / 1000', script)
        self.assertIn('Game Over Continue tapped', engine)
        self.assertIn('flare-death-respawn.png', workflow)

    def test_menu_instrumentation_matches_original_visibility_indent(self):
        instrument = (Path(__file__).resolve().parents[1] / "scripts/emulator_instrument.py").read_text()
        self.assertIn("'\\tqa_inventory_was_visible = inv->visible;\\n'", instrument)
        self.assertNotIn("'\\t\\tqa_inventory_was_visible = inv->visible;\\n'", instrument)

    def test_original_menu_buttons_are_covered(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts/emulator_menus_test.sh").read_text()
        instrument = (root / "scripts/emulator_instrument.py").read_text()
        self.assertIn("character panel %s", instrument)
        self.assertIn("powers panel %s", instrument)
        self.assertIn("questlog panel %s", instrument)
        for menu in ("character", "powers", "questlog"):
            self.assertIn(menu, script)
        self.assertIn("bash scripts/emulator_menus_test.sh", (root / "scripts/emulator_smoke.sh").read_text())
        instrument = (root / "scripts/emulator_instrument.py").read_text()
        hud = (root / "scripts/emulator_hud_test.sh").read_text()
        self.assertIn("attack ring claimed real SDL finger", instrument)
        self.assertIn("slot10 input fired", instrument)
        self.assertIn("attack ring claimed real SDL finger", hud)
        self.assertIn("slot10 input fired", hud)

    def test_emulator_intro_progress_has_native_state_markers(self):
        root = Path(__file__).resolve().parents[1]
        instrument = (root / "scripts/emulator_instrument.py").read_text()
        smoke = (root / "scripts/emulator_smoke.sh").read_text()
        for marker in (
            "FlarePort QA: scene advance",
            "FlarePort QA: original scene completed",
            "FlarePort QA: cutscene scene index advanced",
        ):
            self.assertIn(marker, instrument)
        self.assertIn("FlarePort QA: scene advance", smoke)

    def test_manifest_launch_is_exported_and_sdl_is_private(self):
        self.assertIn('android:name="org.flare.app.LaunchActivity"', MANIFEST)
        self.assertIn('android:exported="true"', MANIFEST)
        self.assertIn('android:exported="false"', MANIFEST)


if __name__ == "__main__":
    unittest.main()
