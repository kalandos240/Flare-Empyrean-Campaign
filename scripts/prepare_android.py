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
VK_ADS_SDK_VERSION = "5.52.5"
YANDEX_ADS_SDK_VERSION = "8.5.0"

APP_GRADLE = """plugins {
    id 'com.android.application'
}

android {
    namespace 'org.flare.app'
    compileSdk 35

    defaultConfig {
        applicationId 'com.kalandos240.flareempyrean'
        minSdk 26
        targetSdk 35
        versionCode 4
        versionName '0.2.2'
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

def patch_android_title_branding(engine: Path) -> None:
    """Keep the in-game title mobile-specific; never alter license credits."""
    title_file = engine / "src/GameStateTitle.cpp"
    if not title_file.is_file():
        raise FileNotFoundError(f"Missing native title screen: {title_file}")
    source = title_file.read_text(encoding="utf-8")
    desktop_version = "label_version->setText(VersionInfo::createVersionStringFull());"
    mobile_version = 'label_version->setText("Android 8.0+");'
    if desktop_version in source:
        if source.count(desktop_version) != 1:
            raise ValueError("Unexpected original game title layout")
        source = source.replace(desktop_version, mobile_version)
        title_file.write_text(source, encoding="utf-8")
    elif mobile_version not in source:
        raise ValueError("Cannot find title version field in pinned Flare engine")


def patch_android_cutscene_status(engine: Path) -> None:
    """Keep native scene transitions latched across several logic ticks.

    Fixed-timestep engines may call logic() repeatedly before render().
    In upstream Flare the previous Scene::NEXT / DONE status gets replaced by
    NO_CHANGE before render() can advance to the next scene. The final
    cinematic Close button can consequently remain on-screen forever.
    This Android-specific fix does not skip campaign story or change timing.
    """
    path = engine / "src/GameStateCutscene.cpp"
    if not path.is_file():
        raise FileNotFoundError(f"Missing upstream native cutscene state: {path}")
    source = path.read_text(encoding="utf-8")
    edits = [
        (
            "\tif (scene_index < scenes.size())\n"
            "\t\tstatus = scenes[scene_index]->logic();",
            "\t// Preserve a pending transition until render() has consumed it.\n"
            "\tif (scene_index < scenes.size() && status == Scene::NO_CHANGE)\n"
            "\t\tstatus = scenes[scene_index]->logic();",
        ),
        (
            "\t\telse if (status == Scene::PREV && scene_index > 0) {\n"
            "\t\t\tscenes[scene_index]->reset();\n"
            "\t\t\tscene_index--;\n"
            "\t\t\tscenes[scene_index]->reset();\n"
            "\t\t}\n"
            "\t}\n}\n",
            "\t\telse if (status == Scene::PREV && scene_index > 0) {\n"
            "\t\t\tscenes[scene_index]->reset();\n"
            "\t\t\tscene_index--;\n"
            "\t\t\tscenes[scene_index]->reset();\n"
            "\t\t}\n"
            "\t\t// A transition is consumed exactly once, after native render.\n"
            "\t\tstatus = Scene::NO_CHANGE;\n"
            "\t}\n}\n",
        ),
    ]
    for original, updated in edits:
        if source.count(original) == 1:
            source = source.replace(original, updated)
        elif source.count(updated) != 1:
            raise ValueError(f"Unexpected native cutscene structure: {path}")
    path.write_text(source, encoding="utf-8")


def patch_android_touch_controls(engine: Path) -> None:
    """Use finger-specific floating controls only in this Android port."""
    source = engine / "src"
    state = source / "InputState.h"
    if not state.is_file():
        raise FileNotFoundError(f"Missing upstream touch input interface: {state}")
    original = state.read_text(encoding="utf-8")
    methods = (
        "\t// Separate contacts enable moving and attacking simultaneously.\n"
        "\tsize_t touchFingerCount() const { return touch_fingers.size(); }\n"
        "\tlong int touchFingerId(size_t i) const { return touch_fingers[i].id; }\n"
        "\tPoint touchFingerPosition(size_t i) const { return touch_fingers[i].pos; }\n\n"
    )
    anchor = "protected:\n\tPoint scaleMouse("
    if methods not in original:
        if original.count(anchor) != 1:
            raise ValueError("Unexpected upstream InputState touch interface")
        original = original.replace(anchor, methods + anchor)
        state.write_text(original, encoding="utf-8")

    replacement = Path(__file__).resolve().parents[1] / "android/native"
    for filename in ("MenuTouchControls.cpp", "MenuTouchControls.h"):
        target = source / filename
        if not target.is_file():
            raise FileNotFoundError(f"Missing upstream touch control source: {target}")
        target.write_text((replacement / filename).read_text(encoding="utf-8"), encoding="utf-8")

    # MenuManager is game-specific and is NOT a SharedResources global.
    manager_file = source / "MenuManager.cpp"
    manager_source = manager_file.read_text(encoding="utf-8")
    original_ctor = "\ttouch_controls = new MenuTouchControls();"
    android_ctor = "\ttouch_controls = new MenuTouchControls(this);"
    if android_ctor not in manager_source:
        if manager_source.count(original_ctor) != 1:
            raise ValueError("Cannot find original MenuTouchControls creation")
        manager_source = manager_source.replace(original_ctor, android_ctor)
        manager_file.write_text(manager_source, encoding="utf-8")


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

def prepare(engine: Path, game: Path, abis: str = "armeabi-v7a arm64-v8a", vk_interstitial_slot: int = 0,
            yandex_interstitial_unit: str = "") -> Path:
    supported = {"armeabi-v7a", "arm64-v8a", "x86_64", "x86"}
    requested = abis.split()
    if not requested or any(abi not in supported for abi in requested) or len(set(requested)) != len(requested):
        raise ValueError(f"Unsupported or repeated Android ABI: {abis!r}")
    if type(vk_interstitial_slot) is not int or vk_interstitial_slot < 0 or vk_interstitial_slot > 2147483647:
        raise ValueError("VK interstitial slot must be an integer from 0 to 2147483647")
    if not isinstance(yandex_interstitial_unit, str) or (
            yandex_interstitial_unit and
            (not re.fullmatch(r"[A-Za-z0-9_-]{3,128}", yandex_interstitial_unit)
             or yandex_interstitial_unit == "demo-interstitial-yandex")):
        raise ValueError("Yandex interstitial unit must be a real ad unit ID (not a demo ID)")
    ads_enabled = bool(vk_interstitial_slot or yandex_interstitial_unit)
    engine = engine.resolve()
    game = game.resolve()
    project = engine / "flare-android-project"
    if not (project / "app/build.gradle").is_file():
        raise FileNotFoundError("Official Flare Android project was not found")

    app = project / "app"
    java = app / "src/main/java/org/flare/app"
    java.mkdir(parents=True, exist_ok=True)

    # Always normalize a previously prepared checkout before changing ad mode.
    # Switching an opt-in VK build back to an offline release must not leave
    # AndroidX, the myTarget Java imports, or native JNI hooks behind.
    gradle_properties = project / "gradle.properties"
    options = gradle_properties.read_text(encoding="utf-8")
    option_pattern = r"(?m)^android\.useAndroidX=(?:true|false)$"
    if len(re.findall(option_pattern, options)) != 1:
        raise ValueError("Expected exactly one upstream AndroidX configuration")
    options = re.sub(
        option_pattern,
        f"android.useAndroidX={'true' if ads_enabled else 'false'}",
        options,
    )
    gradle_properties.write_text(options, encoding="utf-8")

    ads_source = (Path(__file__).resolve().parents[1] / "android/VkAdsBridge.java").read_text(encoding="utf-8")
    ads_java = java / "VkAdsBridge.java"
    yandex_source = (Path(__file__).resolve().parents[1] / "android/YandexAdsBridge.java").read_text(encoding="utf-8")
    yandex_java = java / "YandexAdsBridge.java"
    if not yandex_interstitial_unit and yandex_java.exists():
        if yandex_java.read_text(encoding="utf-8") != yandex_source:
            raise ValueError("Refusing to delete a modified Yandex Ads Java bridge")
        yandex_java.unlink()
    if not vk_interstitial_slot and ads_java.exists():
        if ads_java.read_text(encoding="utf-8") != ads_source:
            raise ValueError("Refusing to delete a modified VK Ads Java bridge")
        ads_java.unlink()

    gradle_source = APP_GRADLE
    manifest_source = MANIFEST
    activity_source = FLARE_ACTIVITY
    if ads_enabled:
        # Offline release never includes advertising SDKs. In opt-in builds
        # network auto-initialization is disabled until explicit consent.
        deps = []
        if vk_interstitial_slot:
            deps.append(f"    implementation 'com.my.target:mytarget-sdk:{VK_ADS_SDK_VERSION}'")
            ads_java.write_text(ads_source, encoding="utf-8")
        if yandex_interstitial_unit:
            deps.append(f"    implementation 'com.yandex.android:mobileads:{YANDEX_ADS_SDK_VERSION}'")
            yandex_java.write_text(yandex_source, encoding="utf-8")
        gradle_source += (
            "\n// Opt-in VK/myTarget and/or Yandex Mobile Ads interstitials.\n"
            "dependencies {\n" + "\n".join(deps) + "\n}\n"
        )
        manifest_source = manifest_source.replace(
            "    <application",
            '    <uses-permission android:name="android.permission.INTERNET" />\n\n    <application',
            1,
        )
        if yandex_interstitial_unit:
            manifest_source = manifest_source.replace(
                '        <activity android:name="org.flare.app.LaunchActivity"',
                '        <meta-data android:name="com.yandex.mobile.ads.AUTOMATIC_SDK_INITIALIZATION"\n'
                '            android:value="false" />\n'
                '        <activity android:name="org.flare.app.LaunchActivity"',
                1,
            )
        activity_source = activity_source.replace(
            "import org.libsdl.app.SDLActivity;",
            "import android.os.Bundle;\nimport android.app.AlertDialog;\nimport org.libsdl.app.SDLActivity;",
        )
        activity_source = activity_source.replace(
            "public class FLARE extends SDLActivity {",
            "public class FLARE extends SDLActivity {\n"
            + ("    private VkAdsBridge vkAds;\n" if vk_interstitial_slot else "")
            + ("    private YandexAdsBridge yandexAds;\n" if yandex_interstitial_unit else "")
            + "    private boolean nextNetworkVk = true;\n"
            + "    private boolean currentNetworkVk = false;\n"
            + "    @Override protected void onCreate(Bundle state) {\n"
            + "        super.onCreate(state);\n"
            + (f"        vkAds = new VkAdsBridge(this, {vk_interstitial_slot});\n" if vk_interstitial_slot else "")
            + (f'        yandexAds = new YandexAdsBridge(this, "{yandex_interstitial_unit}");\n'
               if yandex_interstitial_unit else "")
            + "        showAdPrivacyChoices();\n"
            + "    }\n"
            + "    private void showAdPrivacyChoices() {\n"
            + "        if (isFinishing() || isDestroyed()) return;\n"
            + "        new AlertDialog.Builder(this)\n"
            + f'            .setTitle("{("Реклама VK и Яндекса" if vk_interstitial_slot and yandex_interstitial_unit else "VK Реклама" if vk_interstitial_slot else "Яндекс Реклама")}: конфиденциальность")\n'
            + f'            .setMessage("Рекламные сети {("VK/myTarget и Яндекс" if vk_interstitial_slot and yandex_interstitial_unit else "VK/myTarget" if vk_interstitial_slot else "Яндекса")} могут обрабатывать данные устройства,\\n"\n'
            + '                + "рекламный идентификатор и события рекламы. Вы можете отказаться\\n"\n'
            + '                + "и играть без рекламных запросов. Выбор можно изменить\\n"\n'
            + '                + "при следующем запуске. До разрешения сеть не запрашивается.")\n'
            + '            .setPositiveButton("Разрешить рекламу", (dialog, which) -> {\n'
            + ('                if (vkAds != null) vkAds.setPrivacyReady(true);\n' if vk_interstitial_slot else "")
            + ('                if (yandexAds != null) yandexAds.setPrivacyReady(true);\n' if yandex_interstitial_unit else "")
            + '            })\n'
            + '            .setNegativeButton("Без рекламы", (dialog, which) -> {\n'
            + ('                if (vkAds != null) vkAds.setPrivacyReady(false);\n' if vk_interstitial_slot else "")
            + ('                if (yandexAds != null) yandexAds.setPrivacyReady(false);\n' if yandex_interstitial_unit else "")
            + '            })\n'
            + '            .setCancelable(false).show();\n'
            + '    }\n'
            + '    /** Called by the native engine on entering gameplay. */\n'
            + '    public void onGameSessionStarted() {\n'
            + '        runOnUiThread(() -> {\n'
            + ("            currentNetworkVk = getSharedPreferences(\"flare_ads\", MODE_PRIVATE).getBoolean(\"next_vk\", true);\n"
               "            getSharedPreferences(\"flare_ads\", MODE_PRIVATE).edit().putBoolean(\"next_vk\", !currentNetworkVk).apply();\n"
               if vk_interstitial_slot and yandex_interstitial_unit
               else ("            currentNetworkVk = true;\n" if vk_interstitial_slot else "            currentNetworkVk = false;\n"))
            + ('            if (currentNetworkVk && vkAds != null) vkAds.onGameSessionStarted();\n' if vk_interstitial_slot else "")
            + ('            if (!currentNetworkVk && yandexAds != null) yandexAds.onGameSessionStarted();\n' if yandex_interstitial_unit else "")
            + '        });\n'
            + '    }\n'
            + '    /** No more than one network may show after a saved session. */\n'
            + '    public void onGameSessionEnded() {\n'
            + '        runOnUiThread(() -> {\n'
            + ('            if (currentNetworkVk && vkAds != null) vkAds.onGameSessionEnded();\n' if vk_interstitial_slot else "")
            + ('            if (!currentNetworkVk && yandexAds != null) yandexAds.onGameSessionEnded();\n' if yandex_interstitial_unit else "")
            + '        });\n'
            + '    }\n',
            1,
        )

    (app / "build.gradle").write_text(gradle_source, encoding="utf-8")
    (app / "src/main/AndroidManifest.xml").write_text(manifest_source, encoding="utf-8")
    (java / "FLARE.java").write_text(activity_source, encoding="utf-8")
    (java / "LaunchActivity.java").write_text(
        (Path(__file__).resolve().parents[1] / "android/LaunchActivity.java").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (java / "CampaignPathValidator.java").write_text(
        (Path(__file__).resolve().parents[1] / "android/CampaignPathValidator.java").read_text(encoding="utf-8"),
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

    # Revert only the exact location of our previously injected native callback.
    # This makes repeated preparation and ad-on -> ad-off -> ad-on safe.
    gameplay = engine / "src/GameStatePlay.cpp"
    gameplay_source = gameplay.read_text(encoding="utf-8")
    native_header = '#ifdef __ANDROID__\n#include <jni.h>\n#include "SDL_system.h"\n#endif\n'
    # Revert the exact generated gameplay clock hook between build variants.
    start_marker = "\t// FlareVKAds session start begin\n"
    stop_marker = "\t// FlareVKAds session start end\n"
    if start_marker in gameplay_source:
        if gameplay_source.count(start_marker) != 1 or gameplay_source.count(stop_marker) != 1:
            raise ValueError("Malformed VK session start hook")
        start = gameplay_source.index(start_marker)
        stop = gameplay_source.index(stop_marker, start) + len(stop_marker)
        if 'GetMethodID(vk_class, "onGameSessionStarted", "()V")' not in gameplay_source[start:stop]:
            raise ValueError("Unexpected VK session start hook")
        gameplay_source = gameplay_source[:start] + gameplay_source[stop:]
    elif stop_marker in gameplay_source:
        raise ValueError("Incomplete VK session start hook")

    ad_begin = '\t\tsetRequestedGameState(new GameStateTitle());\n#ifdef __ANDROID__\n'
    ad_end = '\n#endif\n\n\t\tsave_load->setGameSlot(0);'
    if gameplay_source.count(ad_begin) > 1:
        raise ValueError("Ambiguous previously injected VK Ads exit callback")
    if ad_begin in gameplay_source:
        start = gameplay_source.index(ad_begin)
        if ad_end not in gameplay_source[start:]:
            raise ValueError("Incomplete previously injected VK Ads callback")
        end = gameplay_source.index(ad_end, start) + len(ad_end)
        injected = gameplay_source[start:end]
        if 'GetMethodID(clazz, "onGameSessionEnded", "()V")' not in injected:
            raise ValueError("Refusing to replace an unknown native exit callback")
        gameplay_source = (
            gameplay_source[:start]
            + '\t\tsetRequestedGameState(new GameStateTitle());\n\n\t\tsave_load->setGameSlot(0);'
            + gameplay_source[end:]
        )
        if not gameplay_source.startswith(native_header):
            raise ValueError("Previously prepared VK callback is missing JNI includes")
        gameplay_source = gameplay_source[len(native_header):]
    elif gameplay_source.startswith(native_header):
        raise ValueError("Orphaned VK Ads JNI include without a known callback")

    if ads_enabled:
        start_anchor = "\tsecond_timer.setDuration(settings->max_frames_per_sec);"
        if gameplay_source.count(start_anchor) != 1:
            raise ValueError("Cannot find Flare gameplay session start")
        native_start = (
            "\t// FlareVKAds session start begin\n"
            "#ifdef __ANDROID__\n"
            "\tJNIEnv* vk_env = static_cast<JNIEnv*>(SDL_AndroidGetJNIEnv());\n"
            "\tif (vk_env) {\n"
            "\t\tjobject vk_activity = static_cast<jobject>(SDL_AndroidGetActivity());\n"
            "\t\tif (vk_activity) {\n"
            "\t\t\tjclass vk_class = vk_env->GetObjectClass(vk_activity);\n"
            "\t\t\tjmethodID vk_method = vk_env->GetMethodID(vk_class, \"onGameSessionStarted\", \"()V\");\n"
            "\t\t\tif (vk_method) vk_env->CallVoidMethod(vk_activity, vk_method);\n"
            "\t\t\tvk_env->DeleteLocalRef(vk_class);\n"
            "\t\t\tvk_env->DeleteLocalRef(vk_activity);\n"
            "\t\t}\n"
            "\t}\n"
            "#endif\n"
            "\t// FlareVKAds session start end\n"
        )
        gameplay_source = gameplay_source.replace(start_anchor, native_start + start_anchor)
        exit_anchor = (
            "\t\tsnd->stopMusic();\n"
            "\t\tshowLoading();\n"
            "\t\tsetRequestedGameState(new GameStateTitle());\n"
            "\n\t\tsave_load->setGameSlot(0);"
        )
        if gameplay_source.count(exit_anchor) != 1:
            raise ValueError("Cannot identify official saved-game exit-to-title transition")
        android_ad_call = (
            "\t\tsnd->stopMusic();\n"
            "\t\tshowLoading();\n"
            "\t\tsetRequestedGameState(new GameStateTitle());\n"
            "#ifdef __ANDROID__\n"
            "\t\t// Skip the ad signal if the native game did not save on exit.\n"
            "\t\tif (save_on_exit) {\n"
            "\t\t// Do not show an ad until AFTER the native session was saved.\n"
            "\t\tJNIEnv* env = static_cast<JNIEnv*>(SDL_AndroidGetJNIEnv());\n"
            "\t\tif (env) {\n"
            "\t\t\tjobject activity = static_cast<jobject>(SDL_AndroidGetActivity());\n"
            "\t\t\tif (activity) {\n"
            "\t\t\t\tjclass clazz = env->GetObjectClass(activity);\n"
            "\t\t\t\tjmethodID method = env->GetMethodID(clazz, \"onGameSessionEnded\", \"()V\");\n"
            "\t\t\t\tif (method) env->CallVoidMethod(activity, method);\n"
            "\t\t\t\tenv->DeleteLocalRef(clazz);\n"
            "\t\t\t\tenv->DeleteLocalRef(activity);\n"
            "\t\t\t}\n"
            "\t\t}\n"
            "\t\t}\n"
            "#endif\n"
            "\n\t\tsave_load->setGameSlot(0);"
        )
        gameplay_source = gameplay_source.replace(exit_anchor, android_ad_call)
        gameplay_source = native_header + gameplay_source

    gameplay.write_text(gameplay_source, encoding="utf-8")

    patch_android_touch_controls(engine)
    patch_android_title_branding(engine)
    patch_android_cutscene_status(engine)
    patch_sdl_makefiles(app / "src/main/jni")

    # Store defaults to ARM ABIs; --abis x86_64 enables separate emulator smoke builds.
    application_mk = app / "src/main/jni/Application.mk"
    application_config = application_mk.read_text(encoding="utf-8")
    application_config, replacements = re.subn(
        r"(?m)^APP_ABI\s*:=.*$", "APP_ABI := " + " ".join(requested), application_config
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
    parser.add_argument("--abis", default="armeabi-v7a arm64-v8a",
                        help="Whitespace-separated Android native ABIs. Use x86_64 for emulator tests.")
    parser.add_argument("--vk-interstitial-slot", type=int, default=0,
                        help="Optional VK Ads numeric slot ID. 0 disables VK SDK.")
    parser.add_argument("--yandex-interstitial-unit", default="",
                        help="Optional real Yandex Mobile Ads ad unit ID. Empty disables Yandex SDK.")
    args = parser.parse_args()
    project = prepare(args.engine, args.game, args.abis, args.vk_interstitial_slot,
                      args.yandex_interstitial_unit)
    print(f"Prepared Flare Android project: {project}")

if __name__ == "__main__":
    main()
