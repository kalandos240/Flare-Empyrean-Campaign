package org.flare.app;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;

public final class CampaignPathValidatorTest {
    private static int checks;

    private static void accepts(File root, String name) throws IOException {
        CampaignPathValidator.resolve(root, name);
        checks++;
    }

    private static void rejects(File root, String name) throws IOException {
        try {
            CampaignPathValidator.resolve(root, name);
            throw new AssertionError("Unsafe ZIP path accepted: " + name);
        } catch (IOException correct) {
            checks++;
        }
    }

    public static void main(String[] args) throws Exception {
        Path folder = Files.createTempDirectory("flare-zip-test-");
        File root = folder.toFile();
        try {
            Files.createDirectories(folder.resolve("mods/default"));
            Files.createDirectories(folder.resolve("licenses"));
            Files.createDirectories(folder.resolve("userdata/saves"));
            accepts(root, "mods/default/hero.png");
            accepts(root, "mods/default/");
            accepts(root, "mods/mods.txt");
            accepts(root, "licenses/credits.txt");
            accepts(root, "mods/default/hero.png.flare-installing");
            rejects(root, "mods/");
            rejects(root, "mods/../userdata/saves/avatar.txt");
            rejects(root, "mods/default/../../userdata/saves/avatar.txt");
            rejects(root, "mods/./default/file");
            rejects(root, "mods//default/file");
            rejects(root, "mods/default//");
            rejects(root, "/mods/default/file");
            rejects(root, "mods\\..\\userdata\\saves\\avatar.txt");
            rejects(root, "../mods/default/file");
            rejects(root, "userdata/saves/avatar.txt");
            rejects(root, "licenses/../userdata/saves/avatar.txt");
            rejects(root, "mods/default/./file");
            rejects(root, "mods/default/../default/file");
            rejects(root, "mods/../../saves/file");
            rejects(root, "mods/default/file\0name");
            Path redirect = folder.resolve("mods/default/redirect");
            Files.createSymbolicLink(redirect, folder.resolve("userdata/saves"));
            rejects(root, "mods/default/redirect/avatar.txt");
            Path pending = folder.resolve("mods/default/hero.png.flare-installing");
            Files.createSymbolicLink(pending, folder.resolve("userdata/saves/avatar.txt"));
            rejects(root, "mods/default/hero.png.flare-installing");
            Files.delete(pending);
            // Broken symlinks must also be rejected (getCanonicalPath alone
            // can incorrectly treat these as ordinary nonexistent files).
            Files.createSymbolicLink(pending, folder.resolve("userdata/saves/not-created.txt"));
            rejects(root, "mods/default/hero.png.flare-installing");
            Files.delete(pending);
            Path intermediate = folder.resolve("mods/default/shortcut");
            Files.createSymbolicLink(intermediate, folder.resolve("userdata/saves/missing-dir"));
            rejects(root, "mods/default/shortcut/deep/file.png");
        } finally {
            try (java.util.stream.Stream<Path> paths = Files.walk(folder)) {
                paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                    try { Files.deleteIfExists(path); }
                    catch (IOException e) { throw new IllegalStateException(e); }
                });
            }
        }
        System.out.println("PASSED: " + checks + " Java archive path checks");
    }
}
