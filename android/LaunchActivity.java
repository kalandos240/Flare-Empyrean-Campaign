package org.flare.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.widget.TextView;

import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Installs the bundled original game data before launching the native Flare
 * engine. Saves/config live separately and are never overwritten by updates.
 */
public final class LaunchActivity extends Activity {
    private static final String TAG = "FlarePort";
    private static final String DATA_VERSION = "empyrean-2026-10-11-v2";
    private static final long EXTRA_FREE_BYTES = 64L * 1024 * 1024;
    private TextView message;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        message = new TextView(this);
        message.setGravity(Gravity.CENTER);
        message.setPadding(32, 24, 32, 24);
        message.setTextSize(18f);
        message.setText("Подготовка Flare: Empyrean Campaign…");
        setContentView(message);

        Thread worker = new Thread(() -> {
            try {
                installGameData();
                runOnUiThread(() -> {
                    if (!isFinishing() && !isDestroyed()) {
                        startActivity(new Intent(this, FLARE.class));
                        finish();
                    }
                });
            } catch (Exception error) {
                Log.e(TAG, "Cannot install game content", error);
                runOnUiThread(() -> {
                    if (!isFinishing() && !isDestroyed()) {
                        message.setText("Не удалось подготовить игровые файлы:\n"
                                + error.getMessage()
                                + "\n\nОсвободите место и перезапустите игру.");
                    }
                });
            }
        }, "flare-assets-installer");
        worker.start();
    }

    private Properties readManifest() throws IOException {
        Properties properties = new Properties();
        try (InputStream input = getAssets().open("campaign-info.properties")) {
            properties.load(input);
        }
        return properties;
    }

    private void reportProgress(int completed, int total) {
        if (total <= 0) {
            return;
        }
        int percent = Math.min(100, (int) (100L * completed / total));
        runOnUiThread(() -> {
            if (!isFinishing() && !isDestroyed()) {
                message.setText("Распаковка кампании: " + percent + "%\n"
                        + completed + " / " + total + " файлов");
            }
        });
    }

    /** Seed only missing preferences; never replace a player's settings. */
    private void initializeRussianTouchDefaults(File root) throws IOException {
        File settingsDir = new File(root, "config/flare-game");
        if (!settingsDir.isDirectory() && !settingsDir.mkdirs()) {
            throw new IOException("Не удалось создать каталог настроек игры");
        }
        File settingsFile = new File(settingsDir, "settings.txt");
        if (!settingsFile.exists()) {
            String defaults = "language=ru\n"
                    + "setup_language=1\n"
                    + "touch_controls=1\n"
                    + "mouse_move=0\n"
                    + "setup_mousemove=1\n"
                    + "pause_on_focus_loss=1\n";
            try (FileOutputStream output = new FileOutputStream(settingsFile)) {
                output.write(defaults.getBytes("UTF-8"));
            }
        }
    }

    private void installGameData() throws IOException {
        // The native SDL Android path points to the same app-owned directory.
        File root = getExternalFilesDir(null);
        if (root == null) {
            throw new IOException("Недоступно хранилище приложения");
        }

        File marker = new File(root, ".installed-" + DATA_VERSION);
        File mods = new File(root, "mods");
        // A crash during marker creation must not masquerade as a full install.
        if (marker.isFile()
                && marker.length() == DATA_VERSION.length()
                && new File(mods, "mods.txt").isFile()
                && new File(mods, "game.txt").isFile()
                && new File(mods, "default").isDirectory()
                && new File(mods, "fantasycore").isDirectory()
                && new File(mods, "empyrean_campaign").isDirectory()) {
            initializeRussianTouchDefaults(root);
            return;
        }

        Properties info = readManifest();
        int totalFiles;
        long requiredBytes;
        try {
            totalFiles = Integer.parseInt(info.getProperty("files", ""));
            requiredBytes = Long.parseLong(info.getProperty("bytes", ""));
        } catch (NumberFormatException e) {
            throw new IOException("Повреждён список игровых ресурсов", e);
        }
        if (totalFiles <= 0 || requiredBytes <= 0) {
            throw new IOException("Некорректный размер игровых ресурсов");
        }

        boolean freshInstall = !new File(mods, "default").isDirectory()
                && !new File(mods, "fantasycore").isDirectory()
                && !new File(mods, "empyrean_campaign").isDirectory();

        if (freshInstall && root.getUsableSpace() < requiredBytes + EXTRA_FREE_BYTES) {
            throw new IOException("Недостаточно свободного места для игровых файлов");
        }

        final String rootPrefix = root.getCanonicalPath() + File.separator;
        byte[] buffer = new byte[64 * 1024];
        int extractedFiles = 0;

        // A failed/incomplete extraction never receives the completion marker.
        if (marker.exists() && !marker.delete()) {
            throw new IOException("Не удалось обновить отметку об установке");
        }

        try (InputStream input = getAssets().open("campaign.zip");
             ZipInputStream zip = new ZipInputStream(input)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                String entryName = entry.getName();
                // Campaign data may only populate these app-owned directories.
                if (!entryName.startsWith("mods/")
                        && !entryName.startsWith("licenses/")) {
                    throw new IOException("Неожиданный ресурс: " + entryName);
                }
                File destination = new File(root, entryName);
                if (!destination.getCanonicalPath().startsWith(rootPrefix)) {
                    throw new IOException("Недопустимый путь в игровом архиве");
                }

                if (entry.isDirectory()) {
                    if (!destination.isDirectory() && !destination.mkdirs()) {
                        throw new IOException("Не удалось создать каталог " + destination);
                    }
                } else {
                    File parent = destination.getParentFile();
                    if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
                        throw new IOException("Не удалось создать каталог " + parent);
                    }
                    try (BufferedOutputStream output =
                             new BufferedOutputStream(new FileOutputStream(destination))) {
                        int count;
                        while ((count = zip.read(buffer)) != -1) {
                            output.write(buffer, 0, count);
                        }
                    }
                    extractedFiles++;
                    if (extractedFiles % 32 == 0 || extractedFiles == totalFiles) {
                        reportProgress(extractedFiles, totalFiles);
                    }
                }
                zip.closeEntry();
            }
        }

        if (extractedFiles != totalFiles
                || !new File(mods, "mods.txt").isFile()
                || !new File(mods, "game.txt").isFile()
                || !new File(mods, "default").isDirectory()
                || !new File(mods, "fantasycore").isDirectory()
                || !new File(mods, "empyrean_campaign").isDirectory()) {
            throw new IOException("Распаковка кампании завершилась не полностью");
        }

        reportProgress(totalFiles, totalFiles);
        initializeRussianTouchDefaults(root);
        // Never write to the saved-game directories.
        File temporaryMarker = new File(root, marker.getName() + ".pending");
        try (FileOutputStream output = new FileOutputStream(temporaryMarker)) {
            output.write(DATA_VERSION.getBytes("UTF-8"));
            output.getFD().sync();
        }
        if (!temporaryMarker.renameTo(marker)) {
            throw new IOException("Не удалось завершить установку игровых файлов");
        }
    }
}
