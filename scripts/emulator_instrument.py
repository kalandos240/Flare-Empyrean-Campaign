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
    # Mark actual save-slot UI entry and the engine's own SaveLoad::loadGame()
    # call. These are not included in release APKs.
    inject(
        src / "GameStateLoad.cpp",
        '\tif (items == NULL)\n',
        '\tUtils::logInfo("FlarePort QA: load-game menu opened");\n\tif (items == NULL)\n',
    )
    inject(
        src / "GameStateLoad.cpp",
        '\tsave_load->loadGame();\n\tloaded = true;',
        '\tsave_load->loadGame();\n\tUtils::logInfo("FlarePort QA: native character save loaded");\n\tloaded = true;',
    )

    # Test-only observability: a directional joystick event must also move
    # the real hero in the native game world (not just change pixels).
    inject(
        src / "MenuTouchControls.cpp",
        '\t// checking for MAIN1 is redundant, as the touch event itself triggers that\n',
        '\tstatic bool qa_direction_logged = false;\n'
        '\tif (!qa_direction_logged && (inpt->pressing[Input::LEFT] || inpt->pressing[Input::RIGHT] || inpt->pressing[Input::UP] || inpt->pressing[Input::DOWN])) {\n'
        '\t\tqa_direction_logged = true;\n'
        '\t\tUtils::logInfo("FlarePort QA: virtual joystick directional input received");\n'
        '\t}\n'
        '\t// checking for MAIN1 is redundant, as the touch event itself triggers that\n',
    )
    inject(
        src / "GameStatePlay.cpp",
        '\t\tpc->logic();\n',
        '\t\tpc->logic();\n'
        '\t\tstatic int qa_hero_frames = 0;\n'
        '\t\tstatic bool qa_hero_position_ready = false;\n'
        '\t\tstatic bool qa_hero_moved = false;\n'
        '\t\tstatic FPoint qa_hero_start;\n'
        '\t\tif (!qa_hero_position_ready) {\n'
        '\t\t\tif (++qa_hero_frames >= 120) {\n'
        '\t\t\t\tqa_hero_start = pc->stats.pos;\n'
        '\t\t\t\tqa_hero_position_ready = true;\n'
        '\t\t\t\tUtils::logInfo("FlarePort QA: hero position baseline %.2f %.2f", qa_hero_start.x, qa_hero_start.y);\n'
        '\t\t\t}\n'
        '\t\t}\n'
        '\t\telse if (!qa_hero_moved) {\n'
        '\t\t\tconst float qa_dx = pc->stats.pos.x - qa_hero_start.x;\n'
        '\t\t\tconst float qa_dy = pc->stats.pos.y - qa_hero_start.y;\n'
        '\t\t\tif (qa_dx * qa_dx + qa_dy * qa_dy > 0.25f) {\n'
        '\t\t\t\tqa_hero_moved = true;\n'
        '\t\t\t\tUtils::logInfo("FlarePort QA: hero moved %.2f %.2f", qa_dx, qa_dy);\n'
        '\t\t\t}\n'
        '\t\t}\n',
    )

    # These logs prove that the original touch HUD can open the actual
    # inventory and enqueue a normal primary/secondary combat action.
    inject(
        src / "MenuManager.cpp",
        '\tmenus_open = (inv->visible || pow->visible || chr->visible || questlog->visible || vendor->visible || talker->visible || book->visible || console_open);',
        '\tmenus_open = (inv->visible || pow->visible || chr->visible || questlog->visible || vendor->visible || talker->visible || book->visible || console_open);\n'
        '\tstatic bool qa_inventory_was_visible = false;\n'
        '\tif (inv->visible && !qa_inventory_was_visible)\n'
        '\t\tUtils::logInfo("FlarePort QA: original inventory menu opened");\n'
        '\telse if (!inv->visible && qa_inventory_was_visible)\n'
        '\t\tUtils::logInfo("FlarePort QA: original inventory menu closed");\n'
        '\tqa_inventory_was_visible = inv->visible;\n',
    )
    inject(
        src / "MenuActionBar.cpp",
        '\t\t\t\taction_queue.push_back(action);',
        '\t\t\t\tif (i == 10 || i == 11)\n'
        '\t\t\t\t\tUtils::logInfo("FlarePort QA: touch combat action queued for slot %u", i);\n'
        '\t\t\t\taction_queue.push_back(action);',
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


    # Distinguish slow/backlogged cutscenes from ignored screen taps.
    # Log only genuine clicks handled by the original Next button.
    inject(
        src / "GameStateCutscene.cpp",
        '\telse if (button_advance->checkClick()) {\n\t\tskip = SKIP_NEXT;',
        '\telse if (button_advance->checkClick()) {\n'
        '\t\tUtils::logInfo("FlarePort QA: intro next arrow accepted");\n'
        '\t\tskip = SKIP_NEXT;',
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
