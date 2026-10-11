package org.flare.app;

import android.app.Activity;
import android.util.Log;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

/**
 * EMULATOR-ONLY integration test hook, injected by emulator_instrument.py.
 *
 * This class is NEVER copied to the RuStore/ARM release application. It uses
 * the actual Android app's filesystem identity instead of adb shell/run-as,
 * both of which are denied access to Android/data on Android 11+.
 */
public final class QaProbe {
    private static final String TAG = "FlarePort";
    private static final String MARKER = ".installed-empyrean-2026-10-11-v2";

    private QaProbe() {}

    public static void verifyOrSeed(Activity activity) throws IOException {
        File root = activity.getExternalFilesDir(null);
        if (root == null) {
            throw new IOException("FlarePort QA: app-specific storage not available");
        }

        File installMarker = new File(root, MARKER);
        File campaign = new File(root, "mods/mods.txt");
        File core = new File(root, "mods/fantasycore");
        File empyrean = new File(root, "mods/empyrean_campaign");
        File config = new File(root, "config/flare-game/settings.txt");
        File saves = new File(root, "userdata/saves");
        if (!installMarker.isFile() || !campaign.isFile() || !core.isDirectory()
                || !empyrean.isDirectory() || !config.isFile() || !saves.isDirectory()) {
            throw new IOException("FlarePort QA: mandatory campaign/config/save paths absent");
        }
        String settings = new String(Files.readAllBytes(config.toPath()), StandardCharsets.UTF_8);
        if (!settings.contains("language=ru") || !settings.contains("touch_controls=1")) {
            throw new IOException("FlarePort QA: Russian touch control defaults absent");
        }

        File sentinel = new File(saves, ".flare-ci-launcher-check");
        String expected = "test-save|" + installMarker.lastModified();
        if (sentinel.isFile()) {
            String actual = new String(Files.readAllBytes(sentinel.toPath()), StandardCharsets.UTF_8);
            String currentSettings = new String(Files.readAllBytes(config.toPath()),
                                                StandardCharsets.UTF_8);
            if (!expected.equals(actual) || !currentSettings.contains("pause_on_focus_loss=0")) {
                throw new IOException("FlarePort QA: user data/config or install marker changed");
            }
            Log.i(TAG, "FlarePort QA: scoped data persisted");
            return;
        }

        if (!settings.contains("pause_on_focus_loss=1")) {
            throw new IOException("FlarePort QA: unexpected initial settings");
        }
        Files.write(config.toPath(),
                    settings.replace("pause_on_focus_loss=1", "pause_on_focus_loss=0")
                            .getBytes(StandardCharsets.UTF_8));
        Files.write(sentinel.toPath(), expected.getBytes(StandardCharsets.UTF_8));
        Log.i(TAG, "FlarePort QA: scoped data seeded");
    }
}
