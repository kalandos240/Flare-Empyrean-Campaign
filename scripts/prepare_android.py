#!/usr/bin/env python3
"""Prepare an app-scoped Flare: Empyrean Campaign Android build.

Runs against the official flare-engine and flare-game checkouts. The app includes
campaign data, installs it on first launch and never needs broad storage access.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

PACKAGE_ID = "com.kalandos240.flareempyrean"
CONTENT_VERSION = "empyrean-2026-10-11-v2"

APP_GRADLE = """plugins {
    id 'com.android.application'
}

android {
    namespace 'org.flare.app'
    compileSdk 35

    defaultConfig {
        applicationId 'com.kalandos240.flareempyrean'
        minSdk 24
        targetSdk 35
        versionCode 1
        versionName '0.1.0'
    }

    sourceSets {
        main {
            jniLibs.srcDirs = ['src/main/libs']
        }
    }

    buildTypes {
        release {
            minifyEnabled false
        }
    }
}

// The upstream project uses Android.mk, not Gradle's externalNativeBuild.
tasks.register('ndkBuild', Exec) {
    def ndkHome = System.getenv('ANDROID_NDK_HOME') ?: System.getenv('ANDROID_NDK_ROOT')
    def isWindows = System.getProperty('os.name').toLowerCase().contains('windows')
    def ndkExecutable = isWindows ? 'ndk-build.cmd' : 'ndk-build'
    def executable = ndkHome ? new File(ndkHome, ndkExecutable).absolutePath : ndkExecutable
    commandLine executable, '-C', file('src/main').absolutePath, '-j4'
}
tasks.named('preBuild') {
    dependsOn tasks.named('ndkBuild')
}
"""

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-feature android:glEsVersion="0x00020000" android:required="true" />

    <application
        android:label="@string/app_name"
        android:icon="@drawable/ic_launcher"
        android:allowBackup="false"
        android:hardwareAccelerated="true"
        android:theme="@android:style/Theme.Material.Light.NoActionBar">

        <activity android:name="org.flare.app.LaunchActivity"
            android:configChanges="keyboardHidden|orientation|screenSize"
            android:screenOrientation="sensorLandscape"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <activity android:name="org.flare.app.FLARE"
            android:configChanges="keyboardHidden|orientation|screenSize"
            android:screenOrientation="sensorLandscape"
            android:windowSoftInputMode="stateAlwaysHidden"
            android:theme="@android:style/Theme.NoTitleBar.Fullscreen"
            android:exported="false" />
    </application>
</manifest>
"""

FLARE_ACTIVITY = """package org.flare.app;

import org.libsdl.app.SDLActivity;

/** SDL game activity; the launcher has already installed the campaign. */
public class FLARE extends SDLActivity {
    @Override
    protected String[] getLibraries() {
        return new String[] { "SDL2", "SDL2_image", "SDL2_mixer", "SDL2_ttf", "main" };
    }
}
"""

PATHS_METHOD = """void Platform::setPaths() {
    // Scoped storage: SDL returns the app-specific external files directory.
    // No MANAGE_EXTERNAL_STORAGE/WRITE_EXTERNAL_STORAGE permission is required.
    const char* app_data = SDL_AndroidGetExternalStoragePath();
    if (!app_data || !app_data[0]) {
        Utils::logError("Platform: Android app-specific storage is not available: %s", SDL_GetError());
        return;
    }

    settings->path_data = std::string(app_data);
    settings->path_user = settings->path_data + "/userdata";
    settings->path_conf = settings->path_data + "/config";

    Filesystem::createDir(settings->path_user);
    Filesystem::createDir(settings->path_conf);
    Filesystem::createDir(settings->path_user + "/mods");
    Filesystem::createDir(settings->path_user + "/saves");

    settings->path_conf += "/";
    settings->path_user += "/";
    settings->path_data += "/";

    std::ofstream nomedia(settings->path_user + ".nomedia", std::ios::out);
}
"""

def replace_cpp_function(source: str, signature: str, replacement: str) -> str:
    """Replace a brace-delimited C++ function; refuse unexpected upstream layouts."""
    start = source.index(signature)
    opening = source.index("{", start + len(signature))
    level = 0
    for position in range(opening, len(source)):
        if source[position] == "{":
            level += 1
        elif source[position] == "}":
            level -= 1
            if level == 0:
                return source[:start] + replacement + source[position + 1:]
    raise ValueError("Unclosed C++ function: " + signature)

def patch_sdl_makefiles(jni: Path) -> None:
    # Disable codecs disabled by the upstream Android instructions.
    for name, toggles in {
        "SDL2_image": ("SUPPORT_JPG", "SUPPORT_WEBP"),
        "SDL2_mixer": ("SUPPORT_MOD_MIKMOD", "SUPPORT_MP3_SMPEG"),
    }.items():
        makefile = jni / name / "Android.mk"
        if not makefile.exists():
            raise FileNotFoundError(f"Required SDL submodule is missing: {makefile}")
        content = makefile.read_text(encoding="utf-8")
        for variable in toggles:
            content = re.sub(
                rf"(?m)^({variable}\s*[:?+]?=\s*)(?:true|1)\b",
                r"\g<1>false",
                content,
            )
        makefile.write_text(content, encoding="utf-8")

def pack_campaign(engine: Path, game: Path, destination: Path) -> None:
    game_mods = ["fantasycore", "empyrean_campaign"]
    directory_sources = [
        (engine / "mods" / "default", "mods/default"),
        *((game / "mods" / mod, "mods/" + mod) for mod in game_mods),
    ]
    for directory, _ in directory_sources:
        if not directory.is_dir():
            raise FileNotFoundError(f"Missing Flare mod: {directory}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=5, allowZip64=True) as output:
        for source_directory, target_directory in directory_sources:
            for path in sorted(source_directory.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(source_directory).as_posix()
                    output.write(path, f"{target_directory}/{relative}")

        output.writestr("mods/mods.txt", "fantasycore\nempyrean_campaign\n")
        output.writestr("mods/game.txt", "flare-game\n")
        output.write(engine / "COPYING", "licenses/flare-engine-GPL-3.0.txt")
        output.write(game / "LICENSE.txt", "licenses/flare-game-CC-BY-SA-3.0.txt")
        for source, target in [
            (engine / "CREDITS.engine.txt", "licenses/CREDITS.engine.txt"),
            (game / "CREDITS.txt", "licenses/CREDITS.game.txt"),
        ]:
            if source.is_file():
                output.write(source, target)

        file_list = output.infolist()
        manifest = f"files={len(file_list)}\nbytes={sum(item.file_size for item in file_list)}\n"

    (destination.parent / "campaign-info.properties").write_text(manifest, encoding="ascii")

def prepare(engine: Path, game: Path) -> Path:
    engine = engine.resolve()
    game = game.resolve()
    project = engine / "flare-android-project"
    if not (project / "app/build.gradle").is_file():
        raise FileNotFoundError("Official Flare Android project was not found")

    app = project / "app"
    java = app / "src/main/java/org/flare/app"
    java.mkdir(parents=True, exist_ok=True)

    (app / "build.gradle").write_text(APP_GRADLE, encoding="utf-8")
    (app / "src/main/AndroidManifest.xml").write_text(MANIFEST, encoding="utf-8")
    (java / "FLARE.java").write_text(FLARE_ACTIVITY, encoding="utf-8")
    (java / "LaunchActivity.java").write_text(
        (Path(__file__).resolve().parents[1] / "android/LaunchActivity.java").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    strings = app / "src/main/res/values/strings.xml"
    strings.write_text(
        '<resources><string name="app_name">Flare: Empyrean Campaign</string></resources>\n',
        encoding="utf-8",
    )

    platform_file = engine / "src/PlatformAndroid.cpp"
    platform_file.write_text(
        replace_cpp_function(
            platform_file.read_text(encoding="utf-8"),
            "void Platform::setPaths()",
            PATHS_METHOD,
        ),
        encoding="utf-8",
    )

    patch_sdl_makefiles(app / "src/main/jni")

    # Store delivery only needs the two ARM ABIs; emulators can be built separately.
    application_mk = app / "src/main/jni/Application.mk"
    application_config = application_mk.read_text(encoding="utf-8")
    application_config, replacements = re.subn(
        r"(?m)^APP_ABI\\s*:=.*$", "APP_ABI := armeabi-v7a arm64-v8a", application_config
    )
    if replacements != 1:
        raise ValueError("APP_ABI missing from official Android project")
    application_mk.write_text(application_config, encoding="utf-8")

    pack_campaign(engine, game, app / "src/main/assets/campaign.zip")
    return project

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--game", type=Path, required=True)
    args = parser.parse_args()
    project = prepare(args.engine, args.game)
    print(f"Prepared Flare Android project: {project}")

if __name__ == "__main__":
    main()
