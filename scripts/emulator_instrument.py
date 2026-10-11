#!/usr/bin/env python3
"""Opt-in diagnostic logging for the Android emulator only.

This modifies the detached upstream build checkout, never the release sources.
It gives our screenshot-based smoke tests stable signals for menu transitions.
"""
from pathlib import Path
import argparse


def inject(path: Path, anchor: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(anchor) != 1:
        raise ValueError(f"Unexpected upstream layout for {path}: {anchor!r}")
    path.write_text(text.replace(anchor, replacement), encoding="utf-8")


def instrument(source_dir: Path) -> None:
    src = source_dir / "src"
    inject(
        src / "GameStateNew.cpp",
        '{\n\t// set up buttons\n',
        '{\n\tUtils::logInfo("FlarePort QA: character creator opened");\n\t// set up buttons\n',
    )
    inject(
        src / "GameStateNew.cpp",
        '\tif (button_create->checkClick()) {\n\t\t// start the new game\n',
        '\tif (button_create->checkClick()) {\n\t\tUtils::logInfo("FlarePort QA: create character pressed");\n\t\t// start the new game\n',
    )
    inject(
        src / "GameStatePlay.cpp",
        '{\n\tsecond_timer.setDuration(settings->max_frames_per_sec);',
        '{\n\tUtils::logInfo("FlarePort QA: gameplay state constructed");\n\tsecond_timer.setDuration(settings->max_frames_per_sec);',
    )
    # Only the emulator test build gets an exported receiver for its own files.
    # Scoped Android/data cannot be inspected by adb shell on Android 11+.
    project = source_dir / "flare-android-project/app/src/main"
    test_receiver = Path(__file__).resolve().parents[1] / "android/QaReceiver.java"
    target_receiver = project / "java/org/flare/app/QaReceiver.java"
    target_receiver.write_text(test_receiver.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = project / "AndroidManifest.xml"
    manifest_text = manifest.read_text(encoding="utf-8")
    receiver_tag = '''        <receiver android:name="org.flare.app.QaReceiver"
            android:exported="true" />
'''
    if manifest_text.count("    </application>") != 1:
        raise ValueError("Cannot add test receiver to Flare Android manifest")
    manifest.write_text(
        manifest_text.replace("    </application>", receiver_tag + "    </application>"),
        encoding="utf-8",
    )


    # The intro cutscene must *finish* before we claim playable gameplay.
    # This diagnostic marker is never injected into production APK/AAB builds.
    inject(
        src / "GameStateCutscene.cpp",
        'if (scenes.empty() || scene_index >= scenes.size()) {',
        'if (scenes.empty() || scene_index >= scenes.size()) {\n\t\tUtils::logInfo("FlarePort QA: intro cutscene finished");',
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, type=Path)
    args = ap.parse_args()
    instrument(args.engine)
