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

            (app / "build.gradle").write_text("old")
            (jni / "Application.mk").write_text("APP_ABI := armeabi-v7a arm64-v8a x86 x86_64\n")
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
            self.assertEqual((jni / "Application.mk").read_text(), "APP_ABI := armeabi-v7a arm64-v8a\n")
            self.assertIn("getExternalFilesDir", (app / "src/main/java/org/flare/app/LaunchActivity.java").read_text())
            launcher = (app / "src/main/java/org/flare/app/LaunchActivity.java").read_text()
            self.assertIn(CONTENT_VERSION, launcher)
            self.assertIn("campaign-info.properties", launcher)
            self.assertIn("getUsableSpace()", launcher)
            self.assertIn("reportProgress(", launcher)
            self.assertNotIn("MANAGE_EXTERNAL_STORAGE", (app / "src/main/AndroidManifest.xml").read_text())
            self.assertNotIn("WRITE_EXTERNAL_STORAGE", (app / "src/main/AndroidManifest.xml").read_text())
            self.assertIn("SDL_AndroidGetExternalStoragePath", (engine / "src/PlatformAndroid.cpp").read_text())
            self.assertIn("void other() {}", (engine / "src/PlatformAndroid.cpp").read_text())
            self.assertIn("SUPPORT_JPG := false", (jni / "SDL2_image/Android.mk").read_text())
            self.assertIn("SUPPORT_WEBP := false", (jni / "SDL2_image/Android.mk").read_text())
            self.assertIn("SUPPORT_MOD_MIKMOD := false", (jni / "SDL2_mixer/Android.mk").read_text())
            self.assertIn("SUPPORT_MP3_SMPEG := false", (jni / "SDL2_mixer/Android.mk").read_text())

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

    def test_manifest_launch_is_exported_and_sdl_is_private(self):
        self.assertIn('android:name="org.flare.app.LaunchActivity"', MANIFEST)
        self.assertIn('android:exported="true"', MANIFEST)
        self.assertIn('android:exported="false"', MANIFEST)


if __name__ == "__main__":
    unittest.main()
