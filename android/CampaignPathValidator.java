package org.flare.app;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** Validates bundled ZIP entries without giving the installer access to saves. */
final class CampaignPathValidator {
    private CampaignPathValidator() {}

    static File resolve(File root, String name) throws IOException {
        if (root == null || name == null || name.isEmpty()
                || name.indexOf('\\') >= 0 || name.indexOf('\0') >= 0
                || name.startsWith("/")) {
            throw new IOException("Недопустимый путь в игровом архиве");
        }
        String[] parts = name.split("/", -1);
        if (parts.length < 2
                || (!"mods".equals(parts[0]) && !"licenses".equals(parts[0]))
                || (parts.length == 2 && parts[1].isEmpty())) {
            throw new IOException("Неожиданный ресурс: " + name);
        }
        for (int i = 0; i < parts.length; i++) {
            boolean finalDirSlash = i == parts.length - 1 && parts[i].isEmpty() && name.endsWith("/");
            if ((!finalDirSlash && parts[i].isEmpty())
                    || ".".equals(parts[i]) || "..".equals(parts[i])) {
                throw new IOException("Запрещён относительный путь: " + name);
            }
        }
        String rootPath = root.getCanonicalPath() + File.separator + parts[0];
        if (!new File(root, parts[0]).getCanonicalPath().equals(rootPath)) {
            throw new IOException("Подменён каталог игровых ресурсов: " + name);
        }
        // Canonical paths alone do not reliably detect dangling symlinks.
        // Walk every existing component, including the destination itself,
        // so an attacker cannot redirect extraction even when the link target
        // has not been created yet.
        Path cursor = root.toPath().toAbsolutePath().normalize();
        if (Files.isSymbolicLink(cursor)) {
            throw new IOException("Недопустимая символическая ссылка в каталоге установки");
        }
        for (String part : parts) {
            if (part.isEmpty()) continue; // allowed trailing directory slash
            cursor = cursor.resolve(part);
            if (Files.isSymbolicLink(cursor)) {
                throw new IOException("Символическая ссылка в пути игрового архива: " + name);
            }
        }
        File target = new File(root, name);
        if (!target.getCanonicalPath().startsWith(rootPath + File.separator)) {
            throw new IOException("Путь ресурса выходит за разрешённый каталог: " + name);
        }
        return target;
    }
}
