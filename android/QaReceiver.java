package org.flare.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;

/**
 * Emulator-only QA bridge. NEVER included in a release APK.
 *
 * ADB cannot read Android/data on modern Android, even with run-as, so
 * assertions execute inside the app UID and emit a single logcat result.
 */
public final class QaReceiver extends BroadcastReceiver {
    private static final String TAG = "FlareQA";
    private static final String VERSION = "empyrean-2026-10-11-v2";
    private static final String SENTINEL = "emulator-save-file-" + VERSION;
    private static final String PREF_MARK = "# flare-emulator-custom-pref";

    @Override
    public void onReceive(Context context, Intent intent) {
        String op = intent.getStringExtra("operation");
        if (op == null) {
            Log.e(TAG, "QA missing operation FAIL");
            return;
        }
        try {
            File root = context.getExternalFilesDir(null);
            if (root == null) {
                throw new IllegalStateException("App-scoped external storage unavailable");
            }
            File mods = new File(root, "mods");
            File saves = new File(root, "userdata/saves");
            File settings = new File(root, "config/flare-game/settings.txt");
            File marker = new File(root, ".installed-" + VERSION);

            if (!new File(mods, "mods.txt").isFile()
                    || !new File(mods, "default").isDirectory()
                    || !new File(mods, "fantasycore").isDirectory()
                    || !new File(mods, "empyrean_campaign").isDirectory()
                    || !saves.isDirectory() || !settings.isFile() || !marker.isFile()) {
                throw new IllegalStateException("Required game/data/user paths not found");
            }

            String settingsText = read(settings);
            if (!settingsText.contains("language=ru")
                    || !settingsText.contains("touch_controls=1")) {
                throw new IllegalStateException("Russian/touch preferences missing");
            }

            if ("inspect".equals(op)) {
                checkNoIncompleteAssets(mods);
                checkNoIncompleteAssets(new File(root, "licenses"));
                Log.i(TAG, "QA inspect PASS; app-specific game data and settings readable, no partial files");
            } else if ("prepare".equals(op)) {
                File testFile = new File(saves, ".flare-ci-persistence-test");
                write(testFile, SENTINEL + "|" + marker.lastModified(), false);
                if (!settingsText.contains(PREF_MARK)) {
                    write(settings, "\n" + PREF_MARK + "\n", true);
                }
                Log.i(TAG, "QA prepare PASS; app-owned save sentinel and settings marker written");
            } else if ("avatar".equals(op)) {
                // Only a genuine engine save creates avatar.txt in the campaign
                // save slot. This is not the simulated sentinel used above.
                File avatar = new File(saves, "empyrean/1/avatar.txt");
                if (!avatar.isFile() || avatar.length() < 32) {
                    throw new IllegalStateException("The native Empyrean character save is missing");
                }
                File baseline = new File(saves, ".flare-ci-avatar-baseline");
                byte[] savedAvatar = Files.readAllBytes(avatar.toPath());
                if (baseline.isFile()) {
                    if (!Arrays.equals(savedAvatar, Files.readAllBytes(baseline.toPath()))) {
                        throw new IllegalStateException("The real avatar save changed on relaunch");
                    }
                } else {
                    try (FileOutputStream output = new FileOutputStream(baseline)) {
                        output.write(savedAvatar);
                        output.getFD().sync();
                    }
                }
                Log.i(TAG, "QA avatar PASS; real engine character saved and persisted");
            } else if ("verify".equals(op)) {
                File testFile = new File(saves, ".flare-ci-persistence-test");
                if (!testFile.isFile()
                        || !read(testFile).equals(SENTINEL + "|" + marker.lastModified())
                        || !settingsText.contains(PREF_MARK)) {
                    throw new IllegalStateException("User files or installation marker changed");
                }
                Log.i(TAG, "QA verify PASS; same campaign marker, save sentinel and settings after relaunch");
            } else {
                Log.e(TAG, "QA unknown operation: " + op + " FAIL");
            }
        } catch (Exception error) {
            Log.e(TAG, "QA " + op + " FAIL", error);
        }
    }

    /** Ensure the installer committed every extracted file on a clean install. */
    private static void checkNoIncompleteAssets(File directory) {
        File[] children = directory.listFiles();
        if (children == null) {
            throw new IllegalStateException("Cannot inspect installed assets: " + directory);
        }
        for (File child : children) {
            if (child.getName().endsWith(".flare-installing")) {
                throw new IllegalStateException("Incomplete asset remains: " + child);
            }
            if (child.isDirectory()) {
                checkNoIncompleteAssets(child);
            }
        }
    }

    private static String read(File path) throws Exception {
        return new String(Files.readAllBytes(path.toPath()), StandardCharsets.UTF_8).trim();
    }

    private static void write(File path, String data, boolean append) throws Exception {
        try (FileOutputStream output = new FileOutputStream(path, append)) {
            output.write(data.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
    }
}
