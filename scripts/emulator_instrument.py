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

    # Emulator-only markers: distinguish a rendered title, accepted Play click
    # and a failing game-state transition. No QA hooks ship in the RuStore APK.
    inject(
        src / "GameStateTitle.cpp",
        "void GameStateTitle::render() {\n",
        'void GameStateTitle::render() {\n'
        '\tstatic bool qa_title_render_logged = false;\n'
        '\tif (!qa_title_render_logged) {\n'
        '\t\tqa_title_render_logged = true;\n'
        '\t\tUtils::logInfo("FlarePort QA: original title screen rendered");\n'
        '\t}\n',
    )
    inject(
        src / "GameStateTitle.cpp",
        '\t\tbool play_clicked = button_play->checkClick();\n',
        '\t\tbool play_clicked = button_play->checkClick();\n'
        '\t\tif (play_clicked)\n'
        '\t\t\tUtils::logInfo("FlarePort QA: original title Play accepted");\n',
    )

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

    # Emit diagnostics only when the third ring really claims an SDL finger.
    inject(
        src / "MenuTouchControls.cpp",
        '\t\t\tskill_finger_id = id;\n',
        '\t\t\tskill_finger_id = id;\n'
        '\t\t\tUtils::logInfo("FlarePort QA: skill ring accepted MAIN1 slot 10");\n',
    )

    # The left right-hand ring is now a dedicated native interaction input
    # (ACCEPT) instead of an additional attack slot. Test the real callback.
    inject(
        src / "MenuTouchControls.cpp",
        '\t\t\tinteract_pulse = true;\n',
        '\t\t\tinteract_pulse = true;\n'
        '\t\t\tUtils::logInfo("FlarePort QA: dedicated interact button pressed ACCEPT");\n',
    )

    # Emulator-only death trigger goes through the real Avatar state machine.
    inject(
        src / "GameStatePlay.cpp",
        "#include <cassert>\n",
        "#include <cassert>\n#include <cstdio>\n#include <fstream>\n",
    )
    inject(
        src / "GameStatePlay.cpp",
        '\t\tpc->logic();\n',
        '\t\t{\n'
        '\t\t\tconst std::string death_marker = settings->path_user + "saves/.flare-ci-trigger-death";\n'
        '\t\t\tstd::ifstream death_signal(death_marker.c_str());\n'
        '\t\t\tif (death_signal.good() && pc->stats.alive) {\n'
        '\t\t\t\tdeath_signal.close();\n'
        '\t\t\t\tstd::remove(death_marker.c_str());\n'
        '\t\t\t\tpc->stats.hp = 0;\n'
        '\t\t\t\tUtils::logInfo("FlarePort QA: lethal damage triggered in actual Avatar");\n'
        '\t\t\t}\n'
        '\t\t}\n'
        '\t\tpc->logic();\n',
    )
    inject(
        src / "MenuManager.cpp",
        '\tgame_over->logic();\n',
        '\tgame_over->logic();\n'
        '\tstatic bool qa_gameover_logged = false;\n'
        '\tif (game_over->visible && !qa_gameover_logged) {\n'
        '\t\tUtils::logInfo("FlarePort QA: original Game Over dialog displayed");\n'
        '\t\tqa_gameover_logged = true;\n'
        '\t}\n'
        '\tif (!game_over->visible) qa_gameover_logged = false;\n',
    )
    inject(
        src / "MenuGameOver.cpp",
        '\tif (button_continue->checkClick()) {\n',
        '\tif (button_continue->checkClick()) {\n'
        '\t\tUtils::logInfo("FlarePort QA: Game Over Continue tapped");\n',
    )
    inject(
        src / "MenuGameOver.cpp",
        '\telse if (button_exit->checkClick()) {\n',
        '\telse if (button_exit->checkClick()) {\n'
        '\t\tUtils::logInfo("FlarePort QA: Game Over Exit tapped");\n',
    )
    inject(
        src / "GameStatePlay.cpp",
        '\tif (pc->respawn) {\n',
        '\tif (pc->respawn) {\n'
        '\t\tUtils::logInfo("FlarePort QA: original hero respawn reached");\n',
    )

    # Test-only observability: a directional joystick event must also move
    # the real hero in the native game world (not just change pixels).
    inject(
        src / "MenuTouchControls.cpp",
        '\t// Movement and action-zone taps must not also activate MAIN1/slot 10.\n',
        '\tstatic bool qa_direction_logged = false;\n'
        '\tif (!qa_direction_logged && (inpt->pressing[Input::LEFT] || inpt->pressing[Input::RIGHT] || inpt->pressing[Input::UP] || inpt->pressing[Input::DOWN])) {\n'
        '\t\tqa_direction_logged = true;\n'
        '\t\tUtils::logInfo("FlarePort QA: virtual joystick directional input received");\n'
        '\t}\n'
        '\t// Movement and action-zone taps must not also activate MAIN1/slot 10.\n',
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

    # Native action bar has distinct character, powers and quest-log screens.
    # Observe transitions using the real menu visibility flags.
    inject(
        src / "MenuManager.cpp",
        '\t\tqa_inventory_was_visible = inv->visible;\n',
        '\t\tqa_inventory_was_visible = inv->visible;\n'
        '\t\tstatic bool qa_character_seen = false;\n'
        '\t\tstatic bool qa_powers_seen = false;\n'
        '\t\tstatic bool qa_questlog_seen = false;\n'
        '\t\tif (chr->visible != qa_character_seen)\n'
        '\t\t\tUtils::logInfo("FlarePort QA: character panel %s", chr->visible ? "opened" : "closed");\n'
        '\t\tif (pow->visible != qa_powers_seen)\n'
        '\t\t\tUtils::logInfo("FlarePort QA: powers panel %s", pow->visible ? "opened" : "closed");\n'
        '\t\tif (questlog->visible != qa_questlog_seen)\n'
        '\t\t\tUtils::logInfo("FlarePort QA: questlog panel %s", questlog->visible ? "opened" : "closed");\n'
        '\t\tqa_character_seen = chr->visible;\n'
        '\t\tqa_powers_seen = pow->visible;\n'
        '\t\tqa_questlog_seen = questlog->visible;\n',
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

    # Observe the original Android Back / CANCEL -> pause menu transition.
    # Only injected into disposable emulator native sources.
    inject(
        src / "MenuManager.cpp",
        '\tpause = (eset->misc.menus_pause && menus_open) || exit->visible || console_open || book->visible;',
        '\tpause = (eset->misc.menus_pause && menus_open) || exit->visible || console_open || book->visible;\n'
        '\tstatic bool qa_pause_was_visible = false;\n'
        '\tif (qa_pause_was_visible != exit->visible) {\n'
        '\t\tUtils::logInfo("FlarePort QA: original pause menu %s", exit->visible ? "opened" : "closed");\n'
        '\t\tqa_pause_was_visible = exit->visible;\n'
        '\t}\n',
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
