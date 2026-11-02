# Flare: Empyrean Campaign — безопасная подпись APK для RuStore

Весь секретный материал остаётся у владельца репозитория и в защищённых GitHub Actions Secrets. Не загружайте `.jks` в код, Issues, Pull Requests или чат. Base64 **не шифрует** ключ.

## Однократная настройка на Windows

Проверьте, что файл `flare-release.jks` сохранён и пароль известен.
В PowerShell выполните команду в той папке, где находится ваш файл:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path '.\flare-release.jks').Path)) | Set-Clipboard
```

Откройте приватную страницу настроек секретов репозитория:
https://github.com/kalandos240/Flare-Empyrean-Campaign/settings/secrets/actions

Нажмите **New repository secret**, добавьте:

- **FLARE_KEYSTORE_BASE64** — вставьте содержимое буфера обмена, то есть Base64 файла JKS.
- **FLARE_KEYSTORE_PASSWORD** — пароль созданного JKS-файла.

Alias уже зафиксирован в сборке как `flare` в соответствии с командой создания ключа. Для PKCS12 пароль ключа и хранилища одинаковый.

После вставки удалите Base64 из буфера обмена:

```powershell
Set-Clipboard -Value ''
```

Не сообщайте никому пароли и не показывайте значение секретов на скриншотах.
Сделайте **защищённую резервную копию** ключа и пароля.

## Сборка и проверка

Ветка: `port/rustore-android-foundation`. Workflow: `.github/workflows/android.yml`.

При следующем запуске workflow с обоими Secrets GitHub соберёт подписанный APK и проверит его через `apksigner verify`. Готовый файл публикуется как prerelease
`android-v0.2.2-rustore-signed` в Releases.

Если хотя бы одного секрета нет, подписанная сборка пропускается; обычный debug APK создаётся как прежде.

Используйте только подписанный APK для отправки в RuStore. Файл `0.2.2-debug.apk` подписан **другим** ключом и не обновится поверх релизной установки. Перед самой первой публикацией убедитесь, что в кабинете RuStore не остался отладочный APK. При удалении debug-версии Android может удалить её данные и сохранения.

Пакет: `com.kalandos240.flareempyrean`; versionCode: `4`; versionName: `0.2.2`.
