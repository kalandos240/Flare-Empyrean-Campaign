import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

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
            self.assertIn(PACKAGE_ID, (app / "build.gradle").read_text())
            self.assertIn("targetSdk 35", (app / "build.gradle").read_text())
            self.assertIn("minSdk 26", (app / "build.gradle").read_text())
            self.assertNotIn("minSdk 24", (app / "build.gradle").read_text())
            self.assertEqual((jni / "Application.mk").read_text(), "APP_ABI := armeabi-v7a arm64-v8a\n")
            prepare(engine, game, abis="x86_64")
            self.assertEqual((jni / "Application.mk").read_text(), "APP_ABI := x86_64\n")
            with self.assertRaises(ValueError):
                prepare(engine, game, abis="INVALID_ABI")
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

    def test_manifest_launch_is_exported_and_sdl_is_private(self):
        self.assertIn('android:name="org.flare.app.LaunchActivity"', MANIFEST)
        self.assertIn('android:exported="true"', MANIFEST)
        self.assertIn('android:exported="false"', MANIFEST)


if __name__ == "__main__":
    unittest.main()
